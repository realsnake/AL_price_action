from __future__ import annotations

from datetime import datetime
from datetime import timezone

from services.paper_review import build_paper_review, default_review_session_date


def _trade(
    id_: int,
    created_at: str,
    side: str,
    quantity: int,
    price: float,
    strategy: str = "brooks_pullback_count",
    status: str = "filled",
    reason: str = "phase1",
) -> dict:
    return {
        "id": id_,
        "symbol": "QQQ",
        "side": side,
        "quantity": quantity,
        "price": price,
        "strategy": strategy,
        "signal_reason": reason,
        "status": status,
        "alpaca_order_id": f"order-{id_}",
        "created_at": created_at,
    }


def test_build_paper_review_pairs_filled_orders_by_strategy():
    review = build_paper_review(
        session_date="2026-04-24",
        trades=[
            _trade(1, "2026-04-24T14:00:00+00:00", "buy", 25, 660.0),
            _trade(2, "2026-04-24T15:30:00+00:00", "sell", 25, 662.5, reason="exit:session_close"),
            _trade(3, "2026-04-24T16:00:00+00:00", "buy", 100, 661.0, "brooks_small_pb_trend"),
            _trade(4, "2026-04-24T17:00:00+00:00", "sell", 100, 660.5, "brooks_small_pb_trend"),
        ],
    )

    assert review["totals"]["orders"] == 4
    assert review["totals"]["filled_orders"] == 4
    assert review["totals"]["realized_pnl"] == 12.5
    assert review["recommendation"] == "OK_CONTINUE_OBSERVING"

    by_strategy = {row["strategy"]: row for row in review["strategy_summaries"]}
    assert by_strategy["brooks_pullback_count"]["realized_pnl"] == 62.5
    assert by_strategy["brooks_small_pb_trend"]["realized_pnl"] == -50.0
    assert len(review["round_trips"]) == 2


def test_build_paper_review_flags_open_position():
    review = build_paper_review(
        session_date="2026-04-24",
        trades=[
            _trade(1, "2026-04-24T14:00:00+00:00", "buy", 25, 660.0),
        ],
    )

    assert review["totals"]["open_positions"] == [
        {"symbol": "QQQ", "quantity": 25, "strategy": "brooks_pullback_count"}
    ]
    assert review["recommendation"] == "CHECK_OPEN_POSITION"


def test_default_review_session_date_uses_last_closed_us_session():
    assert (
        default_review_session_date(datetime(2026, 4, 25, 2, 0, tzinfo=timezone.utc))
        == "2026-04-24"
    )
    assert (
        default_review_session_date(datetime(2026, 4, 25, 23, 0, tzinfo=timezone.utc))
        == "2026-04-24"
    )
