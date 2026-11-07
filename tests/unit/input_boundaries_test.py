"""Exercise pure integer and UTC normalization boundaries independently of PostgreSQL."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from boxing_club_api.core.clock import as_utc
from boxing_club_api.core.errors import ApplicationError
from boxing_club_api.core.pagination import MAX_OFFSET, page_offset


@pytest.mark.parametrize("size", [1, 20, 100])
def test_offset_accepts_the_largest_representable_page_for_the_selected_size(size: int) -> None:
    assert page_offset(MAX_OFFSET // size, size) == MAX_OFFSET // size * size
    with pytest.raises(ApplicationError) as failure:
        page_offset(MAX_OFFSET // size + 1, size)
    assert failure.value.status_code == 422
    assert failure.value.code == "VALIDATION_ERROR"


@pytest.mark.parametrize(
    "value",
    [
        datetime.min,
        datetime.min.replace(tzinfo=timezone(timedelta(hours=1))),
        datetime.max.replace(tzinfo=timezone(-timedelta(hours=1))),
    ],
)
def test_utc_normalization_rejects_naive_and_overflowing_instants(value: datetime) -> None:
    with pytest.raises(ApplicationError) as failure:
        as_utc(value)
    assert failure.value.status_code == 422


def test_utc_normalization_preserves_supported_extremes_and_converts_offsets() -> None:
    assert as_utc(datetime.min.replace(tzinfo=UTC)) == datetime.min.replace(tzinfo=UTC)
    assert as_utc(datetime.max.replace(tzinfo=UTC)) == datetime.max.replace(tzinfo=UTC)
    assert as_utc(datetime(2030, 1, 1, 12, tzinfo=timezone(timedelta(hours=2)))) == datetime(
        2030, 1, 1, 10, tzinfo=UTC
    )
