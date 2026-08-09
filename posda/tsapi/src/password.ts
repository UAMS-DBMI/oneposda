// Perl-compatible password hashing (Passwords.pm):
// "salt,base64(sha256(salt + password))" with base64 padding stripped.

// '.', '/', digits, then ASCII letters — matching the Perl/Python code.
const saltChars =
  "./0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ";

export function makeSalt(length: number): string {
  const bytes = new Uint8Array(length);
  crypto.getRandomValues(bytes);
  let out = "";
  for (const b of bytes) out += saltChars[b % saltChars.length]!;
  return out;
}

function encodeWithSalt(salt: string, password: string): string {
  const digest = new Bun.CryptoHasher("sha256")
    .update(salt + password)
    .digest("base64")
    .replaceAll("=", "");
  return `${salt},${digest}`;
}

/** Hash a password with a fresh 8-character salt. */
export function encodePassword(password: string): string {
  return encodeWithSalt(makeSalt(8), password);
}

/** Check a candidate password against a stored "salt,digest" hash. */
export function passwordIsValid(hashed: string, candidate: string): boolean {
  const comma = hashed.indexOf(",");
  if (comma < 0) return false;
  return encodeWithSalt(hashed.slice(0, comma), candidate) === hashed;
}
