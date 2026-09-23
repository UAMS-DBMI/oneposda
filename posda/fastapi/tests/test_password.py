import bcrypt

from papi.util import password


def test_encode_returns_bcrypt():
    hashed = password.encode("hunter2")
    assert hashed.startswith("$2b$12$")
    assert not password.needs_rehash(hashed)


def test_is_valid_bcrypt_roundtrip():
    hashed = password.encode("correct horse battery staple")
    assert password.is_valid(hashed, "correct horse battery staple")
    assert not password.is_valid(hashed, "wrong password")


def test_is_valid_legacy_sha256():
    legacy = "aJE5lY8D,2wUueoiymAn8HsfbdAp0kPfTiODV7kpeNUttYTgQGbE"
    assert password.is_valid(legacy, "admin")
    assert not password.is_valid(legacy, "nope")


def test_needs_rehash():
    legacy = "aJE5lY8D,2wUueoiymAn8HsfbdAp0kPfTiODV7kpeNUttYTgQGbE"
    assert password.needs_rehash(legacy)
    assert not password.needs_rehash(password.encode("admin"))


def test_is_valid_bcrypt_2a_prefix():
    # $2a$ hashes (as produced by the Perl side) must also verify.
    hashed = bcrypt.hashpw(b"secret", bcrypt.gensalt(rounds=12, prefix=b"2a")).decode()
    assert hashed.startswith("$2a$")
    assert password.is_valid(hashed, "secret")
    assert not password.is_valid(hashed, "other")


def test_is_valid_malformed_bcrypt():
    assert not password.is_valid("$2b$12$not-a-real-hash", "x")
