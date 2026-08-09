// Safely parses the error_message strings stored by the public-copy
// process. The Python implementation eval()s these strings
// (papi/util/evil.py); they look like:
//
//   ('Failed to submit ...', File(subprocess_invocation_id='6191',
//      file_id='45567767', collection='OPC Radiomics', ...),
//    [SubmitFailedError((500, b'...')), ...])
//
// This module extracts the File(...) keyword arguments and the string
// form of the first error without evaluating anything.

/** Mirrors the evil.File namedtuple. */
export interface EvilFile {
  subprocessInvocationId: string;
  fileId: string;
  collection: string;
  site: string;
  siteId: string;
  batch: string;
  filename: string;
  thirdPartyAnalysisUrl: string | null;
}

/**
 * Extract the File record and the first error's string form from an
 * error_message value. Throws when the message is not in the expected
 * shape (the Python eval() would blow up the whole request there).
 */
export function parse(message: string): [EvilFile, string] {
  const [fileArgs, rest] = balancedSection(message, "File(");
  const kwargs = parseKwargs(fileArgs);

  const file: EvilFile = {
    subprocessInvocationId: kwargs.get("subprocess_invocation_id") ?? "",
    fileId: kwargs.get("file_id") ?? "",
    collection: kwargs.get("collection") ?? "",
    site: kwargs.get("site") ?? "",
    siteId: kwargs.get("site_id") ?? "",
    batch: kwargs.get("batch") ?? "",
    filename: kwargs.get("filename") ?? "",
    thirdPartyAnalysisUrl: kwargs.get("third_party_analysis_url") || null,
  };
  return [file, firstErrorString(rest)];
}

/**
 * Find marker in s and return the balanced-paren content following it,
 * plus everything after the closing paren.
 */
function balancedSection(s: string, marker: string): [string, string] {
  const start = s.indexOf(marker);
  if (start < 0) throw new Error(`marker ${JSON.stringify(marker)} not found`);
  let i = start + marker.length;
  let depth = 1;
  let inString = false;
  for (; i < s.length; i++) {
    const c = s[i]!;
    if (inString) {
      if (c === "\\") i++;
      else if (c === "'") inString = false;
      continue;
    }
    switch (c) {
      case "'":
        inString = true;
        break;
      case "(":
      case "[":
        depth++;
        break;
      case ")":
      case "]":
        depth--;
        if (depth === 0) {
          return [s.slice(start + marker.length, i), s.slice(i + 1)];
        }
        break;
    }
  }
  throw new Error(`unbalanced parens after ${JSON.stringify(marker)}`);
}

/**
 * Parse "a='x', b=None, c='y'" into a map. Values are single-quoted
 * Python string literals, None, or bare tokens.
 */
function parseKwargs(s: string): Map<string, string> {
  const out = new Map<string, string>();
  let i = 0;
  while (i < s.length) {
    // skip separators
    while (i < s.length && (s[i] === "," || s[i] === " " || s[i] === "\n")) {
      i++;
    }
    if (i >= s.length) break;
    const eq = s.indexOf("=", i);
    if (eq < 0) break;
    const key = s.slice(i, eq).trim();
    i = eq + 1;

    if (i < s.length && s[i] === "'") {
      // quoted string with backslash escapes
      let value = "";
      i++;
      while (i < s.length) {
        const c = s[i]!;
        if (c === "\\" && i + 1 < s.length) {
          value += s[i + 1];
          i += 2;
          continue;
        }
        if (c === "'") {
          i++;
          break;
        }
        value += c;
        i++;
      }
      out.set(key, value);
    } else {
      let end = s.indexOf(",", i);
      if (end < 0) end = s.length;
      const token = s.slice(i, end).trim();
      if (token !== "None") out.set(key, token);
      i = end;
    }
  }
  return out;
}

/**
 * Approximates str(error_list[0]) for the trailing
 * "[SomeError((...)), ...]" list: for an exception with a single tuple
 * argument, Python's str() prints the tuple, whose repr matches the
 * source text.
 */
function firstErrorString(rest: string): string {
  let inner: string;
  try {
    [inner] = balancedSection(rest, "Error(");
  } catch {
    return "";
  }
  inner = inner.trim();
  if (inner.endsWith(",")) inner = inner.slice(0, -1);
  return inner;
}

/** Mirrors Python's urllib.parse.quote_plus closely enough. */
export function quotePlus(s: string): string {
  return encodeURIComponent(s)
    .replace(/[!'()*]/g, (c) => `%${c.charCodeAt(0).toString(16).toUpperCase()}`)
    .replaceAll("%20", "+");
}

/** Ports File.get_curl_command. */
export function curlCommand(f: EvilFile): string {
  const bits = [
    `project=${quotePlus(f.collection)}`,
    `siteName=${quotePlus(f.site)}`,
    `siteID=${quotePlus(f.siteId)}`,
    `batch=${quotePlus(f.batch)}`,
    `uri=${f.filename}`,
  ];
  if (f.thirdPartyAnalysisUrl !== null) {
    bits.push(`third_party_analysis_url=${f.thirdPartyAnalysisUrl}`);
  }
  return (
    `curl -H "Authorization:Bearer $TOKEN" ` +
    `-k "https://$HOSTNAME/nbia-api/services/submitDICOM" ` +
    `-d "${bits.join("&")}" `
  );
}

/** Shorten s to max characters, like Python's [:max] slicing. */
export function truncate(s: string, max: number): string {
  return s.length <= max ? s : s.slice(0, max);
}
