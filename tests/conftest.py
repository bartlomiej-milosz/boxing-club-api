import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--postgres",
        action="store_true",
        help="Start a disposable PostgreSQL container for integration tests.",
    )
