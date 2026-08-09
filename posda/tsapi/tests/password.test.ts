import { describe, expect, test } from "bun:test";
import { encodePassword, makeSalt, passwordIsValid } from "../src/password";

// Vectors from the Python password.py self-test (which itself matches
// the Perl Passwords.pm implementation).
describe("password hashing", () => {
  const hashed = "aJE5lY8D,2wUueoiymAn8HsfbdAp0kPfTiODV7kpeNUttYTgQGbE";

  test("known Perl vector validates", () => {
    expect(passwordIsValid(hashed, "admin")).toBeTrue();
  });
  test("wrong password fails", () => {
    expect(passwordIsValid(hashed, "wrong")).toBeFalse();
  });
  test("malformed hash fails", () => {
    expect(passwordIsValid("garbage-no-comma", "admin")).toBeFalse();
  });
  test("fresh encode round-trips", () => {
    expect(passwordIsValid(encodePassword("some test"), "some test")).toBeTrue();
  });
  test("salt length", () => {
    for (const n of [3, 8, 9]) {
      expect(makeSalt(n)).toHaveLength(n);
    }
  });
});
