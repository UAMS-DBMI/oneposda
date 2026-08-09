// Streaming zip and tar.gz downloads, replacing the Python
// zipstream/asynctar helpers (and mirroring the Go internal/archive
// package). Bun has no stdlib archive writers, so the formats are
// produced directly.

import { createReadStream, statSync, readdirSync } from "node:fs";
import { createGzip } from "node:zlib";
import { Readable } from "node:stream";
import { StreamResponse } from "./httpx";

// --- crc32 ------------------------------------------------------------

const crcTable = new Uint32Array(256);
for (let n = 0; n < 256; n++) {
  let c = n;
  for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
  crcTable[n] = c >>> 0;
}

function crc32Update(crc: number, buf: Uint8Array): number {
  let c = crc ^ 0xffffffff;
  for (let i = 0; i < buf.length; i++) {
    c = crcTable[(c ^ buf[i]!) & 0xff]! ^ (c >>> 8);
  }
  return (c ^ 0xffffffff) >>> 0;
}

async function fileCrc32(path: string): Promise<number> {
  let crc = 0;
  for await (const chunk of createReadStream(path)) {
    crc = crc32Update(crc, chunk as Uint8Array);
  }
  return crc;
}

// --- binary helpers ---------------------------------------------------

class ByteWriter {
  private parts: Uint8Array[] = [];
  u16(v: number): this {
    const b = new Uint8Array(2);
    new DataView(b.buffer).setUint16(0, v, true);
    this.parts.push(b);
    return this;
  }
  u32(v: number): this {
    const b = new Uint8Array(4);
    new DataView(b.buffer).setUint32(0, v >>> 0, true);
    this.parts.push(b);
    return this;
  }
  u64(v: number | bigint): this {
    const b = new Uint8Array(8);
    new DataView(b.buffer).setBigUint64(0, BigInt(v), true);
    this.parts.push(b);
    return this;
  }
  bytes(v: Uint8Array): this {
    this.parts.push(v);
    return this;
  }
  done(): Uint8Array {
    const total = this.parts.reduce((n, p) => n + p.length, 0);
    const out = new Uint8Array(total);
    let off = 0;
    for (const p of this.parts) {
      out.set(p, off);
      off += p.length;
    }
    return out;
  }
}

// --- zip --------------------------------------------------------------

const ZIP64_LIMIT = 0xffffffff;

interface ZipEntry {
  name: Uint8Array;
  crc: number;
  size: number;
  offset: number;
  dosTime: number;
  dosDate: number;
  mode: number;
}

function dosDateTime(mtime: Date): { dosTime: number; dosDate: number } {
  const y = Math.max(1980, mtime.getFullYear());
  return {
    dosDate: ((y - 1980) << 9) | ((mtime.getMonth() + 1) << 5) | mtime.getDate(),
    dosTime:
      (mtime.getHours() << 11) |
      (mtime.getMinutes() << 5) |
      (mtime.getSeconds() >> 1),
  };
}

function zipLocalHeader(e: ZipEntry): Uint8Array {
  const zip64 = e.size >= ZIP64_LIMIT;
  const w = new ByteWriter();
  w.u32(0x04034b50)
    .u16(zip64 ? 45 : 20) // version needed
    .u16(0x0800) // utf-8 names
    .u16(0) // method: STORED
    .u16(e.dosTime)
    .u16(e.dosDate)
    .u32(e.crc)
    .u32(zip64 ? ZIP64_LIMIT : e.size)
    .u32(zip64 ? ZIP64_LIMIT : e.size)
    .u16(e.name.length)
    .u16(zip64 ? 20 : 0)
    .bytes(e.name);
  if (zip64) {
    w.u16(0x0001).u16(16).u64(e.size).u64(e.size);
  }
  return w.done();
}

function zipCentralDirectory(entries: ZipEntry[], endOffset: number): Uint8Array {
  const w = new ByteWriter();
  let size = 0;
  for (const e of entries) {
    const zip64 = e.size >= ZIP64_LIMIT || e.offset >= ZIP64_LIMIT;
    const extra = new ByteWriter();
    if (zip64) {
      const fields = new ByteWriter();
      if (e.size >= ZIP64_LIMIT) fields.u64(e.size).u64(e.size);
      if (e.offset >= ZIP64_LIMIT) fields.u64(e.offset);
      const body = fields.done();
      extra.u16(0x0001).u16(body.length).bytes(body);
    }
    const extraBytes = extra.done();
    const rec = new ByteWriter()
      .u32(0x02014b50)
      .u16((3 << 8) | 45) // made by: unix, spec 4.5
      .u16(zip64 ? 45 : 20)
      .u16(0x0800)
      .u16(0)
      .u16(e.dosTime)
      .u16(e.dosDate)
      .u32(e.crc)
      .u32(e.size >= ZIP64_LIMIT ? ZIP64_LIMIT : e.size)
      .u32(e.size >= ZIP64_LIMIT ? ZIP64_LIMIT : e.size)
      .u16(e.name.length)
      .u16(extraBytes.length)
      .u16(0)
      .u16(0)
      .u16(0)
      .u32(e.mode << 16)
      .u32(e.offset >= ZIP64_LIMIT ? ZIP64_LIMIT : e.offset)
      .bytes(e.name)
      .bytes(extraBytes)
      .done();
    w.bytes(rec);
    size += rec.length;
  }

  const needZip64End =
    entries.length >= 0xffff || size >= ZIP64_LIMIT || endOffset >= ZIP64_LIMIT;
  if (needZip64End) {
    w.u32(0x06064b50)
      .u64(44)
      .u16((3 << 8) | 45)
      .u16(45)
      .u32(0)
      .u32(0)
      .u64(entries.length)
      .u64(entries.length)
      .u64(size)
      .u64(endOffset);
    w.u32(0x07064b50).u32(0).u64(endOffset + size).u32(1);
  }
  w.u32(0x06054b50)
    .u16(0)
    .u16(0)
    .u16(Math.min(entries.length, 0xffff))
    .u16(Math.min(entries.length, 0xffff))
    .u32(Math.min(size, ZIP64_LIMIT))
    .u32(Math.min(endOffset, ZIP64_LIMIT))
    .u16(0);
  return w.done();
}

/**
 * Stream the given files as an uncompressed (STORED, like zipstream's
 * default) zip archive. Member names are the full paths with leading
 * slashes stripped, matching Python's zipfile.write default arcname.
 * A file that cannot be read aborts the stream (the client sees a
 * truncated archive), matching the Go/Python behavior.
 */
export function streamZip(files: string[], downloadName: string): Response {
  async function* generate(): AsyncGenerator<Uint8Array> {
    const entries: ZipEntry[] = [];
    let offset = 0;
    for (const path of files) {
      const st = statSync(path);
      const entry: ZipEntry = {
        name: new TextEncoder().encode(path.replace(/^\/+/, "")),
        crc: await fileCrc32(path),
        size: st.size,
        offset,
        mode: st.mode & 0o7777,
        ...dosDateTime(st.mtime),
      };
      const header = zipLocalHeader(entry);
      yield header;
      offset += header.length;
      for await (const chunk of createReadStream(path)) {
        yield chunk as Uint8Array;
      }
      offset += st.size;
      entries.push(entry);
    }
    yield zipCentralDirectory(entries, offset);
  }

  return archiveResponse(generate(), "application/zip", downloadName);
}

// --- tar.gz -----------------------------------------------------------

function tarNumeric(v: number, length: number): Uint8Array {
  const s = v.toString(8).padStart(length - 1, "0") + "\0";
  return new TextEncoder().encode(s);
}

function tarChecksum(block: Uint8Array): number {
  let sum = 0;
  for (const b of block) sum += b;
  return sum;
}

function tarHeader(
  name: string,
  size: number,
  mode: number,
  mtime: number,
  typeflag: string,
): Uint8Array {
  const block = new Uint8Array(512);
  const enc = new TextEncoder();
  const put = (s: Uint8Array, off: number) => block.set(s, off);
  put(enc.encode(name).slice(0, 100), 0);
  put(tarNumeric(mode, 8), 100);
  put(tarNumeric(0, 8), 108); // uid
  put(tarNumeric(0, 8), 116); // gid
  put(tarNumeric(size, 12), 124);
  put(tarNumeric(mtime, 12), 136);
  put(enc.encode("        "), 148); // checksum placeholder: spaces
  put(enc.encode(typeflag), 156);
  put(enc.encode("ustar\0" + "00"), 257);
  const checksum = tarChecksum(block);
  put(enc.encode(checksum.toString(8).padStart(6, "0") + "\0 "), 148);
  return block;
}

function tarPad(size: number): Uint8Array {
  const rem = size % 512;
  return new Uint8Array(rem === 0 ? 0 : 512 - rem);
}

/** PAX extended header for names too long for a ustar header. */
function paxHeader(name: string): Uint8Array[] {
  const enc = new TextEncoder();
  const record = (key: string, value: string): string => {
    // "%d %s=%s\n" where %d counts the whole record, itself included
    const baseBytes = enc.encode(` ${key}=${value}\n`).length;
    let len = baseBytes + 1;
    while (String(len).length + baseBytes !== len) {
      len = String(len).length + baseBytes;
    }
    return `${len} ${key}=${value}\n`;
  };
  const body = enc.encode(record("path", name));
  return [
    tarHeader("./PaxHeaders/" + name.slice(0, 85), body.length, 0o644, 0, "x"),
    body,
    tarPad(body.length),
  ];
}

async function* generateTar(dir: string): AsyncGenerator<Uint8Array> {
  const files: string[] = [];
  const walk = (d: string): void => {
    for (const entry of readdirSync(d, { withFileTypes: true }).sort((a, b) =>
      a.name < b.name ? -1 : 1,
    )) {
      const full = `${d}/${entry.name}`;
      if (entry.isDirectory()) walk(full);
      else files.push(full);
    }
  };
  walk(dir);

  for (const path of files) {
    // stat (not lstat) so symlinks are archived as regular files
    // (tarfile dereference=True).
    const st = statSync(path);
    if (!st.isFile()) continue;
    const rel = path.slice(dir.length).replace(/^\/+/, "");
    if (new TextEncoder().encode(rel).length > 100) {
      for (const chunk of paxHeader(rel)) yield chunk;
    }
    yield tarHeader(
      rel.slice(0, 100),
      st.size,
      st.mode & 0o7777,
      Math.floor(st.mtimeMs / 1000),
      "0",
    );
    for await (const chunk of createReadStream(path)) {
      yield chunk as Uint8Array;
    }
    yield tarPad(st.size);
  }
  yield new Uint8Array(1024); // two zero blocks terminate the archive
}

/**
 * Walk dir and stream its contents as a tar.gz archive, with member
 * names relative to dir.
 */
export function streamTarGz(dir: string, downloadName: string): Response {
  const gz = createGzip({ level: 9 });
  const body = Readable.toWeb(
    Readable.from(generateTar(dir)).pipe(gz),
  ) as unknown as ReadableStream<Uint8Array>;
  return new StreamResponse(body, {
    headers: {
      "Content-Type": "application/gzip",
      "Content-Disposition": `attachment; filename="${downloadName}"`,
    },
  });
}

function archiveResponse(
  gen: AsyncGenerator<Uint8Array>,
  contentType: string,
  downloadName: string,
): Response {
  const body = Readable.toWeb(Readable.from(gen)) as unknown as ReadableStream<Uint8Array>;
  return new StreamResponse(body, {
    headers: {
      "Content-Type": contentType,
      "Content-Disposition": `attachment; filename="${downloadName}"`,
    },
  });
}
