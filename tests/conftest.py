"""Configure opt-in test resources for this directory and its descendants."""

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register the opt-in PostgreSQL flag without starting database infrastructure."""
    parser.addoption(
        "--postgres",
        action="store_true",
        help="Start a disposable PostgreSQL container for integration tests.",
    )
