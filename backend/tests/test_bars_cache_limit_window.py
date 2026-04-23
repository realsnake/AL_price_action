from datetime import datetime, timezone

from services import bars_cache


class _Row:
    def __init__(self, ts: str):
        self.timestamp = datetime.fromisoformat(ts.replace("Z", "+00:00"))


def test_first_expected_daily_timestamp_aligns_to_market_day_bar_timestamp():
    start_dt = datetime(2025, 4, 18, tzinfo=timezone.utc)

    assert bars_cache._first_expected_daily_timestamp(start_dt) == datetime(
        2025, 4, 21, 4, 0, tzinfo=timezone.utc
    )


def test_cache_satisfies_request_when_window_exhausted_before_limit():
    rows = [
        _Row("2025-04-21T04:00:00+00:00"),
        _Row("2025-04-22T04:00:00+00:00"),
        _Row("2025-04-23T04:00:00+00:00"),
    ]
    start_dt = datetime(2025, 4, 18, tzinfo=timezone.utc)
    end_dt = datetime(2025, 4, 24, 0, 0, tzinfo=timezone.utc)

    cache_hit, fetch_start = bars_cache._cache_satisfies_request(
        rows=rows,
        timeframe="1D",
        start_dt=start_dt,
        end_dt=end_dt,
        limit=500,
        explicit_end=False,
    )

    assert cache_hit is True
    assert fetch_start is None
