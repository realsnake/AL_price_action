from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select

from database import async_session
from models import Trade
from services.bars_cache import MARKET_TZ, _is_trading_day, _session_close_for
from services.research_profile import canonical_timestamp, market_time, session_day
from services.trade_executor import refresh_trade_statuses


FILLED_STATUSES = {"filled", "partially_filled"}


@dataclass(frozen=True)
class PaperReviewResult:
    session_date: str
    output_dir: Path
    markdown_path: Path
    json_path: Path
    trades_csv_path: Path
    round_trips_csv_path: Path
    trade_count: int
    filled_trade_count: int
    realized_pnl: float
    recommendation: str


def default_review_session_date(now: datetime | None = None) -> str:
    """Return the US market session that should be reviewed after close."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    local = current.astimezone(MARKET_TZ)
    candidate = local.date()

    if _is_trading_day(candidate) and local >= _session_close_for(candidate):
        return candidate.isoformat()

    return _previous_trading_day(candidate).isoformat()


async def write_daily_paper_review(
    *,
    session_date: str | None = None,
    output_root: str | Path,
    refresh_limit: int = 500,
) -> PaperReviewResult:
    review_date = session_date or default_review_session_date()
    start_utc, end_utc = _session_bounds_utc(review_date)

    await refresh_trade_statuses(limit=refresh_limit)
    trades = await _load_trades_before(end_utc)
    review = build_paper_review(
        session_date=review_date,
        trades=trades,
        start_utc=start_utc,
        end_utc=end_utc,
    )

    output_dir = Path(output_root) / review_date
    output_dir.mkdir(parents=True, exist_ok=True)

    trades_csv_path = output_dir / "trades.csv"
    round_trips_csv_path = output_dir / "round_trips.csv"
    json_path = output_dir / "review.json"
    markdown_path = output_dir / "review.md"

    _write_trades_csv(trades_csv_path, review["daily_trades"])
    _write_round_trips_csv(round_trips_csv_path, review["round_trips"])
    json_path.write_text(
        json.dumps(review, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    markdown_path.write_text(_render_markdown(review), encoding="utf-8")

    return PaperReviewResult(
        session_date=review_date,
        output_dir=output_dir,
        markdown_path=markdown_path,
        json_path=json_path,
        trades_csv_path=trades_csv_path,
        round_trips_csv_path=round_trips_csv_path,
        trade_count=review["totals"]["orders"],
        filled_trade_count=review["totals"]["filled_orders"],
        realized_pnl=review["totals"]["realized_pnl"],
        recommendation=review["recommendation"],
    )


def build_paper_review(
    *,
    session_date: str,
    trades: list[dict[str, Any]],
    start_utc: datetime | None = None,
    end_utc: datetime | None = None,
) -> dict[str, Any]:
    if start_utc is None or end_utc is None:
        start_utc, end_utc = _session_bounds_utc(session_date)

    ordered_trades = sorted(
        trades,
        key=lambda trade: (
            _trade_datetime_utc(trade).isoformat(),
            int(trade.get("id") or 0),
        ),
    )
    daily_trades = [
        _serialize_review_trade(trade)
        for trade in ordered_trades
        if start_utc <= _trade_datetime_utc(trade) < end_utc
    ]

    summaries: dict[str, dict[str, Any]] = {}
    lots: dict[tuple[str, str], deque[dict[str, Any]]] = defaultdict(deque)
    round_trips: list[dict[str, Any]] = []
    unmatched_sell_qty: Counter[str] = Counter()

    for trade in ordered_trades:
        trade_time = _trade_datetime_utc(trade)
        if trade_time >= end_utc:
            continue

        strategy = _strategy_label(trade)
        summary = summaries.setdefault(strategy, _empty_strategy_summary(strategy))
        is_daily = start_utc <= trade_time < end_utc
        if is_daily:
            _add_order_to_summary(summary, trade)

        if not _is_filled_trade(trade):
            continue

        key = (str(trade.get("symbol") or ""), strategy)
        side = str(trade.get("side") or "").lower()
        qty = int(trade.get("quantity") or 0)
        price = float(trade.get("price") or 0.0)
        if qty <= 0 or price <= 0:
            continue

        if side == "buy":
            lots[key].append(
                {
                    "remaining_qty": qty,
                    "entry_price": price,
                    "entry_time": _trade_datetime_utc(trade).isoformat(),
                    "entry_reason": trade.get("signal_reason") or "",
                    "entry_trade_id": trade.get("id"),
                }
            )
            continue

        if side != "sell":
            continue

        remaining_to_close = qty
        while remaining_to_close > 0 and lots[key]:
            lot = lots[key][0]
            matched_qty = min(remaining_to_close, int(lot["remaining_qty"]))
            pnl = (price - float(lot["entry_price"])) * matched_qty

            if is_daily:
                summary["realized_pnl"] += pnl
                round_trips.append(
                    {
                        "strategy": strategy,
                        "symbol": trade.get("symbol") or "",
                        "quantity": matched_qty,
                        "entry_trade_id": lot["entry_trade_id"],
                        "exit_trade_id": trade.get("id"),
                        "entry_time": lot["entry_time"],
                        "exit_time": trade_time.isoformat(),
                        "entry_price": round(float(lot["entry_price"]), 4),
                        "exit_price": round(price, 4),
                        "pnl": round(pnl, 2),
                        "entry_reason": lot["entry_reason"],
                        "exit_reason": trade.get("signal_reason") or "",
                    }
                )

            lot["remaining_qty"] = int(lot["remaining_qty"]) - matched_qty
            remaining_to_close -= matched_qty
            if int(lot["remaining_qty"]) <= 0:
                lots[key].popleft()

        if remaining_to_close > 0 and is_daily:
            summary["unmatched_sell_qty"] += remaining_to_close
            unmatched_sell_qty[strategy] += remaining_to_close

    for (symbol, strategy), open_lots in lots.items():
        summary = summaries.setdefault(strategy, _empty_strategy_summary(strategy))
        open_qty = sum(int(lot["remaining_qty"]) for lot in open_lots)
        if open_qty > 0:
            summary["open_positions"].append({"symbol": symbol, "quantity": open_qty})

    for summary in summaries.values():
        summary["realized_pnl"] = round(summary["realized_pnl"], 2)
        summary["gross_buy"] = round(summary["gross_buy"], 2)
        summary["gross_sell"] = round(summary["gross_sell"], 2)
        summary["symbols"] = sorted(summary["symbols"])
        summary["status_counts"] = dict(sorted(summary["status_counts"].items()))

    strategy_rows = sorted(
        summaries.values(),
        key=lambda item: (item["strategy"] == "manual", item["strategy"]),
    )
    totals = _build_totals(strategy_rows)
    recommendation = _build_recommendation(
        totals=totals,
        unmatched_sell_qty=unmatched_sell_qty,
    )

    return {
        "session_date": session_date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "timezone": str(MARKET_TZ),
        "totals": totals,
        "recommendation": recommendation,
        "strategy_summaries": strategy_rows,
        "daily_trades": daily_trades,
        "round_trips": round_trips,
    }


async def _load_trades_before(end_utc: datetime) -> list[dict[str, Any]]:
    end_naive = end_utc.astimezone(timezone.utc).replace(tzinfo=None)
    async with async_session() as session:
        result = await session.execute(
            select(Trade)
            .where(Trade.created_at < end_naive)
            .order_by(Trade.created_at.asc(), Trade.id.asc())
        )
        trades = result.scalars().all()
    return [_trade_model_to_dict(trade) for trade in trades]


def _trade_model_to_dict(trade: Trade) -> dict[str, Any]:
    return {
        "id": trade.id,
        "symbol": trade.symbol,
        "side": trade.side,
        "quantity": trade.quantity,
        "price": trade.price,
        "strategy": trade.strategy,
        "signal_reason": trade.signal_reason,
        "status": trade.status,
        "alpaca_order_id": trade.alpaca_order_id,
        "created_at": trade.created_at.isoformat() if trade.created_at else None,
    }


def _empty_strategy_summary(strategy: str) -> dict[str, Any]:
    return {
        "strategy": strategy,
        "orders": 0,
        "filled_orders": 0,
        "buy_qty": 0,
        "sell_qty": 0,
        "gross_buy": 0.0,
        "gross_sell": 0.0,
        "realized_pnl": 0.0,
        "unmatched_sell_qty": 0,
        "open_positions": [],
        "symbols": set(),
        "status_counts": Counter(),
    }


def _add_order_to_summary(summary: dict[str, Any], trade: dict[str, Any]) -> None:
    summary["orders"] += 1
    status = str(trade.get("status") or "unknown")
    side = str(trade.get("side") or "").lower()
    qty = int(trade.get("quantity") or 0)
    price = float(trade.get("price") or 0.0)
    symbol = str(trade.get("symbol") or "")

    summary["status_counts"][status] += 1
    summary["symbols"].add(symbol)
    if _is_filled_trade(trade):
        summary["filled_orders"] += 1
        if side == "buy":
            summary["buy_qty"] += qty
            summary["gross_buy"] += qty * price
        elif side == "sell":
            summary["sell_qty"] += qty
            summary["gross_sell"] += qty * price


def _build_totals(strategy_rows: list[dict[str, Any]]) -> dict[str, Any]:
    open_positions = [
        {**position, "strategy": row["strategy"]}
        for row in strategy_rows
        for position in row["open_positions"]
    ]
    return {
        "orders": sum(row["orders"] for row in strategy_rows),
        "filled_orders": sum(row["filled_orders"] for row in strategy_rows),
        "buy_qty": sum(row["buy_qty"] for row in strategy_rows),
        "sell_qty": sum(row["sell_qty"] for row in strategy_rows),
        "gross_buy": round(sum(row["gross_buy"] for row in strategy_rows), 2),
        "gross_sell": round(sum(row["gross_sell"] for row in strategy_rows), 2),
        "realized_pnl": round(sum(row["realized_pnl"] for row in strategy_rows), 2),
        "unmatched_sell_qty": sum(row["unmatched_sell_qty"] for row in strategy_rows),
        "open_positions": open_positions,
    }


def _build_recommendation(
    *,
    totals: dict[str, Any],
    unmatched_sell_qty: Counter[str],
) -> str:
    if totals["orders"] == 0:
        return "NO_TRADES_RECORDED"
    if totals["unmatched_sell_qty"] > 0:
        strategies = ", ".join(sorted(unmatched_sell_qty))
        return f"CHECK_PAIRING: unmatched sell quantity in {strategies}"
    if totals["open_positions"]:
        return "CHECK_OPEN_POSITION"
    if totals["realized_pnl"] < 0:
        return "LOSS_DAY_REVIEW_REQUIRED"
    return "OK_CONTINUE_OBSERVING"


def _serialize_review_trade(trade: dict[str, Any]) -> dict[str, Any]:
    timestamp = canonical_timestamp(trade.get("created_at") or "")
    return {
        "id": trade.get("id"),
        "created_at": timestamp,
        "market_time": market_time(timestamp).isoformat(),
        "session_date": session_day(timestamp),
        "symbol": trade.get("symbol") or "",
        "strategy": _strategy_label(trade),
        "side": trade.get("side") or "",
        "quantity": int(trade.get("quantity") or 0),
        "price": float(trade.get("price") or 0.0),
        "status": trade.get("status") or "",
        "signal_reason": trade.get("signal_reason") or "",
        "alpaca_order_id": trade.get("alpaca_order_id") or "",
    }


def _write_trades_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "id",
        "created_at",
        "market_time",
        "session_date",
        "symbol",
        "strategy",
        "side",
        "quantity",
        "price",
        "status",
        "signal_reason",
        "alpaca_order_id",
    ]
    _write_csv(path, fieldnames, rows)


def _write_round_trips_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "strategy",
        "symbol",
        "quantity",
        "entry_trade_id",
        "exit_trade_id",
        "entry_time",
        "exit_time",
        "entry_price",
        "exit_price",
        "pnl",
        "entry_reason",
        "exit_reason",
    ]
    _write_csv(path, fieldnames, rows)


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def _render_markdown(review: dict[str, Any]) -> str:
    totals = review["totals"]
    pnl = totals["realized_pnl"]
    lines = [
        f"# Paper trade review: {review['session_date']}",
        "",
        "## Summary",
        "",
        f"- Recommendation: `{review['recommendation']}`",
        f"- Realized PnL: {'+' if pnl >= 0 else ''}{pnl:.2f}",
        f"- Orders: {totals['orders']} total, {totals['filled_orders']} filled",
        f"- Buy/Sell quantity: {totals['buy_qty']} / {totals['sell_qty']}",
        f"- Open positions: {len(totals['open_positions'])}",
        "",
        "## Strategy Breakdown",
        "",
        "| Strategy | Orders | Filled | Buy Qty | Sell Qty | Realized PnL | Open | Statuses |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in review["strategy_summaries"]:
        open_qty = sum(position["quantity"] for position in row["open_positions"])
        statuses = ", ".join(
            f"{status}:{count}" for status, count in row["status_counts"].items()
        )
        lines.append(
            "| "
            f"{row['strategy']} | {row['orders']} | {row['filled_orders']} | "
            f"{row['buy_qty']} | {row['sell_qty']} | {row['realized_pnl']:+.2f} | "
            f"{open_qty} | {statuses or '-'} |"
        )

    lines.extend(["", "## Round Trips", ""])
    if review["round_trips"]:
        lines.append("| Strategy | Qty | Entry | Exit | PnL | Exit Reason |")
        lines.append("| --- | ---: | ---: | ---: | ---: | --- |")
        for trade in review["round_trips"]:
            lines.append(
                "| "
                f"{trade['strategy']} | {trade['quantity']} | "
                f"{trade['entry_price']:.2f} | {trade['exit_price']:.2f} | "
                f"{trade['pnl']:+.2f} | {trade['exit_reason']} |"
            )
    else:
        lines.append("No completed round trips were recorded for this session.")

    lines.extend(["", "## Raw Files", "", "- `trades.csv`", "- `round_trips.csv`", "- `review.json`", ""])
    return "\n".join(lines)


def _strategy_label(trade: dict[str, Any]) -> str:
    return str(trade.get("strategy") or "manual")


def _is_filled_trade(trade: dict[str, Any]) -> bool:
    return str(trade.get("status") or "").lower() in FILLED_STATUSES


def _trade_datetime_utc(trade: dict[str, Any]) -> datetime:
    value = trade.get("created_at")
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _session_bounds_utc(session_date: str) -> tuple[datetime, datetime]:
    day = date.fromisoformat(session_date)
    start = datetime.combine(day, time.min, tzinfo=MARKET_TZ)
    end = start + timedelta(days=1)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def _previous_trading_day(candidate: date) -> date:
    current = candidate - timedelta(days=1)
    while not _is_trading_day(current):
        current -= timedelta(days=1)
    return current
