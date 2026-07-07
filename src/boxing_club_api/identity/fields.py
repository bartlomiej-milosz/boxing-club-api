"""Normalize account fields before validation, lookup and persistence."""


def normalize_email(value: str) -> str:
    """Trim and lowercase an email, raising ValueError for invalid or oversized input."""
    email = value.strip().lower()
    local, separator, domain = email.partition("@")
    if (
        not separator
        or not local
        or not domain
        or "@" in domain
        or len(email) > 254
        or any(character.isspace() or character == "\x00" for character in email)
    ):
        raise ValueError("Enter a valid email address of at most 254 characters.")
    return email


def normalize_name(value: str) -> str:
    """Trim a name, raising ValueError when empty, oversized or containing a NUL."""
    name = value.strip()
    if not 1 <= len(name) <= 100 or "\x00" in name:
        raise ValueError("Names must have between 1 and 100 characters.")
    return name
