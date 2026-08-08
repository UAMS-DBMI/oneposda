// Package evilparse safely parses the error_message strings stored by
// the public-copy process. The Python implementation eval()s these
// strings (papi/util/evil.py); they look like:
//
//	('Failed to submit ...', File(subprocess_invocation_id='6191',
//	   file_id='45567767', collection='OPC Radiomics', ...),
//	 [SubmitFailedError((500, b'...')), ...])
//
// This package extracts the File(...) keyword arguments and the string
// form of the first error without evaluating anything.
package evilparse

import (
	"fmt"
	"net/url"
	"strings"
)

// File mirrors the evil.File namedtuple.
type File struct {
	SubprocessInvocationID string
	FileID                 string
	Collection             string
	Site                   string
	SiteID                 string
	Batch                  string
	Filename               string
	ThirdPartyAnalysisURL  *string
}

// Parse extracts the File record and the first error's string form
// from an error_message value.
func Parse(message string) (*File, string, error) {
	fileArgs, rest, err := balancedSection(message, "File(")
	if err != nil {
		return nil, "", err
	}

	kwargs, err := parseKwargs(fileArgs)
	if err != nil {
		return nil, "", err
	}

	f := &File{
		SubprocessInvocationID: kwargs["subprocess_invocation_id"],
		FileID:                 kwargs["file_id"],
		Collection:             kwargs["collection"],
		Site:                   kwargs["site"],
		SiteID:                 kwargs["site_id"],
		Batch:                  kwargs["batch"],
		Filename:               kwargs["filename"],
	}
	if v, ok := kwargs["third_party_analysis_url"]; ok && v != "" {
		f.ThirdPartyAnalysisURL = &v
	}

	return f, firstErrorString(rest), nil
}

// balancedSection finds marker in s and returns the balanced-paren
// content following it, plus everything after the closing paren.
func balancedSection(s, marker string) (string, string, error) {
	start := strings.Index(s, marker)
	if start < 0 {
		return "", "", fmt.Errorf("marker %q not found", marker)
	}
	i := start + len(marker)
	depth := 1
	inString := false
	for ; i < len(s); i++ {
		c := s[i]
		if inString {
			if c == '\\' {
				i++
			} else if c == '\'' {
				inString = false
			}
			continue
		}
		switch c {
		case '\'':
			inString = true
		case '(', '[':
			depth++
		case ')', ']':
			depth--
			if depth == 0 {
				return s[start+len(marker) : i], s[i+1:], nil
			}
		}
	}
	return "", "", fmt.Errorf("unbalanced parens after %q", marker)
}

// parseKwargs parses "a='x', b=None, c='y'" into a map. Values are
// single-quoted Python string literals, None, or bare tokens.
func parseKwargs(s string) (map[string]string, error) {
	out := map[string]string{}
	i := 0
	for i < len(s) {
		// skip separators
		for i < len(s) && (s[i] == ',' || s[i] == ' ' || s[i] == '\n') {
			i++
		}
		if i >= len(s) {
			break
		}
		eq := strings.IndexByte(s[i:], '=')
		if eq < 0 {
			break
		}
		key := strings.TrimSpace(s[i : i+eq])
		i += eq + 1

		if i < len(s) && s[i] == '\'' {
			// quoted string with backslash escapes
			var b strings.Builder
			i++
			for i < len(s) {
				c := s[i]
				if c == '\\' && i+1 < len(s) {
					b.WriteByte(s[i+1])
					i += 2
					continue
				}
				if c == '\'' {
					i++
					break
				}
				b.WriteByte(c)
				i++
			}
			out[key] = b.String()
		} else {
			end := strings.IndexByte(s[i:], ',')
			if end < 0 {
				end = len(s) - i
			}
			token := strings.TrimSpace(s[i : i+end])
			if token != "None" {
				out[key] = token
			}
			i += end
		}
	}
	return out, nil
}

// firstErrorString approximates str(error_list[0]) for the trailing
// "[SomeError((...)), ...]" list: for an exception with a single tuple
// argument, Python's str() prints the tuple, whose repr matches the
// source text.
func firstErrorString(rest string) string {
	inner, _, err := balancedSection(rest, "Error(")
	if err != nil {
		return ""
	}
	inner = strings.TrimSpace(inner)
	inner = strings.TrimSuffix(inner, ",")
	return inner
}

// QuotePlus mirrors Python's urllib.parse.quote_plus closely enough
// for the values that appear here.
func QuotePlus(s string) string {
	return url.QueryEscape(s)
}

// CurlCommand ports File.get_curl_command.
func (f *File) CurlCommand() string {
	bits := []string{
		"project=" + QuotePlus(f.Collection),
		"siteName=" + QuotePlus(f.Site),
		"siteID=" + QuotePlus(f.SiteID),
		"batch=" + QuotePlus(f.Batch),
		"uri=" + f.Filename,
	}
	if f.ThirdPartyAnalysisURL != nil {
		bits = append(bits, "third_party_analysis_url="+*f.ThirdPartyAnalysisURL)
	}
	return `curl -H "Authorization:Bearer $TOKEN" ` +
		`-k "https://$HOSTNAME/nbia-api/services/submitDICOM" ` +
		`-d "` + strings.Join(bits, "&") + `" `
}

// Truncate shortens s to max characters, like Python's [:max] slicing.
func Truncate(s string, max int) string {
	if len(s) <= max {
		return s
	}
	return s[:max]
}
