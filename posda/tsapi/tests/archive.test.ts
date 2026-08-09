import { describe, expect, test } from "bun:test";
import { mkdtempSync, mkdirSync, writeFileSync, symlinkSync } from "node:fs";
import { tmpdir } from "node:os";
import { streamTarGz, streamZip } from "../src/archive";

async function responseBytes(res: Response): Promise<Uint8Array> {
  return new Uint8Array(await res.arrayBuffer());
}

function run(cmd: string[], stdin?: Uint8Array): { out: string; code: number } {
  const proc = Bun.spawnSync(cmd, { stdin });
  return { out: proc.stdout.toString(), code: proc.exitCode };
}

describe("streamZip", () => {
  test("produces a valid STORED zip with full-path member names", async () => {
    const dir = mkdtempSync(`${tmpdir()}/ziptest`);
    writeFileSync(`${dir}/a.txt`, "hello zip");
    writeFileSync(`${dir}/b.bin`, new Uint8Array([0, 1, 2, 255]));

    const res = streamZip([`${dir}/a.txt`, `${dir}/b.bin`], "test.zip");
    expect(res.headers.get("Content-Type")).toBe("application/zip");
    expect(res.headers.get("Content-Disposition")).toBe(
      'attachment; filename="test.zip"',
    );

    const zipPath = `${dir}/out.zip`;
    writeFileSync(zipPath, await responseBytes(res));

    // unzip validates CRCs and lists the archive members.
    const check = run(["unzip", "-t", zipPath]);
    expect(check.code).toBe(0);
    expect(check.out).toContain(`${dir.replace(/^\/+/, "")}/a.txt`);

    const extract = run(["unzip", "-p", zipPath, `${dir.replace(/^\/+/, "")}/a.txt`]);
    expect(extract.out).toBe("hello zip");
  });

  test("empty file list yields a valid empty archive", async () => {
    const res = streamZip([], "empty.zip");
    const bytes = await responseBytes(res);
    // Just the end-of-central-directory record.
    expect(bytes.length).toBe(22);
  });
});

describe("streamTarGz", () => {
  test("archives a directory tree with relative names", async () => {
    const dir = mkdtempSync(`${tmpdir()}/tartest`);
    mkdirSync(`${dir}/sub`);
    writeFileSync(`${dir}/root.txt`, "at root");
    writeFileSync(`${dir}/sub/nested.txt`, "nested content");
    symlinkSync(`${dir}/root.txt`, `${dir}/link.txt`);
    const longName = "d".repeat(120);
    mkdirSync(`${dir}/${longName}`);
    writeFileSync(`${dir}/${longName}/long.txt`, "long path");

    const res = streamTarGz(dir, "test.tar.gz");
    expect(res.headers.get("Content-Type")).toBe("application/gzip");

    const tarPath = `${dir}.tar.gz`;
    writeFileSync(tarPath, await responseBytes(res));

    const list = run(["tar", "-tzf", tarPath]);
    expect(list.code).toBe(0);
    expect(list.out).toContain("root.txt");
    expect(list.out).toContain("sub/nested.txt");
    // Symlinks are archived as regular files (dereference=True).
    expect(list.out).toContain("link.txt");
    expect(list.out).toContain(`${longName}/long.txt`);

    const extract = run(["tar", "-xzf", tarPath, "-O", "sub/nested.txt"]);
    expect(extract.out).toBe("nested content");
    const viaLink = run(["tar", "-xzf", tarPath, "-O", "link.txt"]);
    expect(viaLink.out).toBe("at root");
  });
});
