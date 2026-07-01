from pwdlib import PasswordHash

MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 128
_password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        raise ValueError("Password must have between 12 and 128 characters.")
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _password_hash.verify(password, password_hash)
