"""Represent expected operation failures with stable public HTTP details."""


class ApplicationError(Exception):
    """Expected failure whose code and message are safe to expose to an API caller."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        super().__init__(message)
