"""Password hashing.

New hashes are argon2. Bcrypt hashes imported from Yorick (Parse stored
bcryptjs `$2a$` hashes) still verify, and are replaced with argon2 the first
time their owner signs in.
"""

from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from pwdlib.hashers.bcrypt import BcryptHasher

_hasher = PasswordHash((Argon2Hasher(), BcryptHasher()))

# Checked against when no account matches, so a wrong email takes as long as a
# wrong password and sign-in does not reveal which emails have accounts.
_DUMMY_HASH = _hasher.hash("not a real password")

MIN_PASSWORD_LENGTH = 10


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> tuple[bool, str | None]:
    """Whether `password` matches, and a replacement hash if the stored one is outdated."""
    if password_hash is None:
        _hasher.verify(password, _DUMMY_HASH)
        return False, None
    return _hasher.verify_and_update(password, password_hash)
