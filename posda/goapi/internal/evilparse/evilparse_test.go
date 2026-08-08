package evilparse

import "testing"

// The sample message from evil.py's self-test.
const sample = `('Failed to submit the file; error details follow', File(subprocess_invocation_id='6191', file_id='45567767', collection='OPC Radiomics', site='UHN', site_id='86663098', batch='0', filename='/nas/public/storage-from-posda/cb/c7/e2/cbc7e2e57b5e8f0998718d6bdaabddb6.dcm'), [SubmitFailedError((500, b'Server was not able to process your request'),), SubmitFailedError((500, b'Server was not able to process your request'),), SubmitFailedError((500, b'Server was not able to process your request'),), SubmitFailedError((500, b'Server was not able to process your request'),), SubmitFailedError((500, b'Server was not able to process your request'),)])`

func TestParse(t *testing.T) {
	file, firstErr, err := Parse(sample)
	if err != nil {
		t.Fatal(err)
	}
	if file.SubprocessInvocationID != "6191" {
		t.Errorf("subprocess_invocation_id = %q", file.SubprocessInvocationID)
	}
	if file.FileID != "45567767" {
		t.Errorf("file_id = %q", file.FileID)
	}
	if file.Collection != "OPC Radiomics" {
		t.Errorf("collection = %q", file.Collection)
	}
	if file.Site != "UHN" || file.SiteID != "86663098" || file.Batch != "0" {
		t.Errorf("site fields: %q %q %q", file.Site, file.SiteID, file.Batch)
	}
	if file.ThirdPartyAnalysisURL != nil {
		t.Errorf("third_party_analysis_url should be nil")
	}
	// Matches Python's str(SubmitFailedError((500, b'...'),)).
	wantErr := "(500, b'Server was not able to process your request')"
	if firstErr != wantErr {
		t.Errorf("first error = %q, want %q", firstErr, wantErr)
	}
}

// Expected output produced by running evil.py's __main__.
func TestCurlCommand(t *testing.T) {
	file, _, err := Parse(sample)
	if err != nil {
		t.Fatal(err)
	}
	want := `curl -H "Authorization:Bearer $TOKEN" ` +
		`-k "https://$HOSTNAME/nbia-api/services/submitDICOM" ` +
		`-d "project=OPC+Radiomics&siteName=UHN&siteID=86663098&batch=0&uri=/nas/public/storage-from-posda/cb/c7/e2/cbc7e2e57b5e8f0998718d6bdaabddb6.dcm" `
	if got := file.CurlCommand(); got != want {
		t.Errorf("curl command mismatch:\ngot  %q\nwant %q", got, want)
	}
}

func TestParseWithEscapedQuote(t *testing.T) {
	msg := `('msg', File(subprocess_invocation_id='1', file_id='2', collection='it\'s a test', site='S', site_id='3', batch='0', filename='/f'), [SubmitFailedError((500, b'x'),)])`
	file, _, err := Parse(msg)
	if err != nil {
		t.Fatal(err)
	}
	if file.Collection != "it's a test" {
		t.Errorf("collection = %q", file.Collection)
	}
}
