import { describe, expect, test } from "bun:test";
import { curlCommand, parse, truncate } from "../src/evilparse";

// The sample message from evil.py's self-test.
const sample = `('Failed to submit the file; error details follow', File(subprocess_invocation_id='6191', file_id='45567767', collection='OPC Radiomics', site='UHN', site_id='86663098', batch='0', filename='/nas/public/storage-from-posda/cb/c7/e2/cbc7e2e57b5e8f0998718d6bdaabddb6.dcm'), [SubmitFailedError((500, b'Server was not able to process your request'),), SubmitFailedError((500, b'Server was not able to process your request'),), SubmitFailedError((500, b'Server was not able to process your request'),), SubmitFailedError((500, b'Server was not able to process your request'),), SubmitFailedError((500, b'Server was not able to process your request'),)])`;

describe("evilparse", () => {
  test("parses the File record", () => {
    const [file, firstErr] = parse(sample);
    expect(file.subprocessInvocationId).toBe("6191");
    expect(file.fileId).toBe("45567767");
    expect(file.collection).toBe("OPC Radiomics");
    expect(file.site).toBe("UHN");
    expect(file.siteId).toBe("86663098");
    expect(file.batch).toBe("0");
    expect(file.thirdPartyAnalysisUrl).toBeNull();
    // Matches Python's str(SubmitFailedError((500, b'...'),)).
    expect(firstErr).toBe(
      "(500, b'Server was not able to process your request')",
    );
  });

  test("curl command matches evil.py __main__ output", () => {
    const [file] = parse(sample);
    expect(curlCommand(file)).toBe(
      `curl -H "Authorization:Bearer $TOKEN" ` +
        `-k "https://$HOSTNAME/nbia-api/services/submitDICOM" ` +
        `-d "project=OPC+Radiomics&siteName=UHN&siteID=86663098&batch=0&uri=/nas/public/storage-from-posda/cb/c7/e2/cbc7e2e57b5e8f0998718d6bdaabddb6.dcm" `,
    );
  });

  test("escaped quotes inside values", () => {
    const msg = `('msg', File(subprocess_invocation_id='1', file_id='2', collection='it\\'s a test', site='S', site_id='3', batch='0', filename='/f'), [SubmitFailedError((500, b'x'),)])`;
    const [file] = parse(msg);
    expect(file.collection).toBe("it's a test");
  });

  test("malformed message throws", () => {
    expect(() => parse("nothing useful here")).toThrow();
  });

  test("truncate", () => {
    expect(truncate("abcdef", 3)).toBe("abc");
    expect(truncate("ab", 3)).toBe("ab");
  });
});
