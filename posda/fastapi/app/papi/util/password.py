import string
import random
import hashlib
import base64

import bcrypt

BCRYPT_ROUNDS = 12

def make_salt(length: int=8) -> str:
    """Make a simple random salt

    This was adapted from perl Passwords.pm
    """

    chars = [
        '.',
        '/',
        *string.digits,
        *string.ascii_letters,
    ]

    salt = random.choices(chars, k=length)

    return ''.join(salt)

def encode(password: str) -> str:
    """Hash a password with bcrypt.

    New passwords are always stored in bcrypt format.
    """
    return bcrypt.hashpw(
        password.encode(),
        bcrypt.gensalt(rounds=BCRYPT_ROUNDS),
    ).decode()

def _encode(salt: str, password: str) -> str:
    m = hashlib.sha256()

    m.update(salt.encode())
    m.update(password.encode())

    digest = base64.b64encode(m.digest()).decode()

    # to be exactly compatible with the perl implementation, we must
    # drop any padding characters in the base64!
    digest = digest.replace("=", '')

    return f"{salt},{digest}"

def is_valid(hashed_password: str, candidate_password: str) -> bool:
    if hashed_password.startswith("$2"):
        try:
            return bcrypt.checkpw(
                candidate_password.encode(),
                hashed_password.encode(),
            )
        except ValueError:
            return False

    salt, _ = hashed_password.split(',')

    hashed_candidate = _encode(salt, candidate_password)

    return hashed_password == hashed_candidate

def needs_rehash(hashed_password: str) -> bool:
    """Return True if the stored hash is not in the current bcrypt format."""
    return not hashed_password.startswith("$2")


def test():
    print("running some simple tests")

    salt = make_salt()
    print("A sample salt:", salt)
    assert len(salt) == 8
    assert len(make_salt(3)) == 3
    assert len(make_salt(9)) == 9

    admin_encoded = "aJE5lY8D,2wUueoiymAn8HsfbdAp0kPfTiODV7kpeNUttYTgQGbE"
    print(_encode(salt, "some test"))
    tencode = _encode("aJE5lY8D", "admin")
    print(tencode)
    assert tencode == admin_encoded

    assert is_valid(admin_encoded, "admin")
    assert not needs_rehash(encode("admin"))

if __name__ == '__main__':
    test()
