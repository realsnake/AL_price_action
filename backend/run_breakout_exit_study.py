from __future__ import annotations

import csv
import html
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

from services.phase1_exit import BREAKOUT_EXIT_POLICIES
from services.phase1_exit import PULLBACK_COUNT_EXIT_POLICIES
from services.research_validation import build_strategy_validation_report
from services.research_profile import filter_bars_for_research_profile, get_research_profile
from services.strategy_engine import get_strategy


STRATEGY = os.getenv("STUDY_STRATEGY", "brooks_breakout_pullback")
SYMBOL = os.getenv("STUDY_SYMBOL", "QQQ")
TIMEFRAME = os.getenv("STUDY_TIMEFRAME", "5m")
START = os.getenv("STUDY_START", "2024-01-01")
END = os.getenv("STUDY_END", "2026-03-26")
RESEARCH_PROFILE = os.getenv("STUDY_RESEARCH_PROFILE", "qqq_5m_phase1")
FIXED_QUANTITY = int(os.getenv("STUDY_FIXED_QUANTITY", "100"))
STOP_LOSS_PCT = float(os.getenv("STUDY_STOP_LOSS_PCT", "2.0"))
TAKE_PROFIT_PCT = float(os.getenv("STUDY_TAKE_PROFIT_PCT", "4.0"))
RISK_PER_TRADE_PCT = float(os.getenv("STUDY_RISK_PER_TRADE_PCT", "2.0"))
SLIPPAGE_BPS = float(os.getenv("STUDY_SLIPPAGE_BPS", "1.0"))
LIMIT = (
    None
    if os.getenv("STUDY_LIMIT", "").strip().lower() in {"", "none", "all"}
    else int(os.getenv("STUDY_LIMIT", "50000"))
)


def policies_for_strategy(strategy_name: str) -> tuple[str, ...]:
    if strategy_name == "brooks_pullback_count":
        return PULLBACK_COUNT_EXIT_POLICIES
    return BREAKOUT_EXIT_POLICIES


POLICIES = [
    value.strip()
    for value in os.getenv(
        "STUDY_EXIT_POLICIES",
        ",".join(policies_for_strategy(STRATEGY)),
    ).split(",")
    if value.strip()
]
PARAMS = json.loads(os.getenv("STUDY_PARAMS_JSON", "{}"))
OUTPUT_ROOT = os.getenv("STUDY_OUTPUT_ROOT", "reports/exit_studies")
DB_PATH = Path(os.getenv("STUDY_DB_PATH", Path(__file__).with_name("trader.db")))


def main() -> None:
    profile = get_research_profile(RESEARCH_PROFILE)
    bars = _load_cached_bars(
        symbol=SYMBOL,
        timeframe=TIMEFRAME,
        start=START,
        end=END,
        limit=LIMIT,
    )
    bars = filter_bars_for_research_profile(bars, profile)
    strategy = get_strategy(STRATEGY, PARAMS or None)
    signals = strategy.generate_signals(SYMBOL, bars)

    reports = [
        build_strategy_validation_report(
            strategy_name=STRATEGY,
            bars=bars,
            symbol=SYMBOL,
            timeframe=TIMEFRAME,
            research_profile=RESEARCH_PROFILE,
            fixed_quantity=FIXED_QUANTITY,
            stop_loss_pct=STOP_LOSS_PCT,
            take_profit_pct=TAKE_PROFIT_PCT,
            risk_per_trade_pct=RISK_PER_TRADE_PCT,
            slippage_bps=SLIPPAGE_BPS,
            exit_policy=policy,
            signals=signals,
            strategy=strategy,
        )
        for policy in POLICIES
    ]

    ranked_rows = [_flatten_report(report) for report in reports]
    ranked_rows.sort(key=_ranking_key, reverse=True)
    for idx, row in enumerate(ranked_rows, start=1):
        row["rank"] = idx

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = Path(OUTPUT_ROOT) / STRATEGY / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)

    study_path = output_dir / "study.json"
    summary_path = output_dir / "summary.csv"
    report_path = output_dir / "report.html"

    study_payload = {
        "strategy": STRATEGY,
        "symbol": SYMBOL,
        "timeframe": TIMEFRAME,
        "period": f"{START} ~ {END}",
        "research_profile": RESEARCH_PROFILE,
        "recent_gate": {
            "last_12_trade_days_pnl_gt": 0,
            "latest_3m_return_pct_gt": 0,
        },
        "rank_method": (
            "Keep only recent-gate-eligible winners (last 12 tradedays pnl > 0 and latest 3m "
            "return > 0), then sort by profit factor desc, max drawdown asc, positive-month "
            "ratio desc, rolling 3m ratio desc, rolling 6m ratio desc, latest 3m return desc, "
            "recent 12 tradeday pnl desc, total return desc."
        ),
        "winner": next((row for row in ranked_rows if row["passes_recent_gate"]), None),
        "rows": ranked_rows,
        "reports": reports,
    }
    study_path.write_text(json.dumps(study_payload, indent=2), encoding="utf-8")

    with summary_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "rank",
                "exit_policy",
                "policy_label",
                "signals",
                "trades",
                "return_pct",
                "profit_factor",
                "win_rate",
                "max_dd_pct",
                "positive_month_ratio",
                "positive_3m_ratio",
                "positive_6m_ratio",
                "recent_trade_days",
                "recent_trade_days_period",
                "recent_trade_day_pnl",
                "recent_trade_day_return_pct",
                "latest_3m_label",
                "latest_3m_return_pct",
                "passes_recent_gate",
                "avg_hold_min",
                "median_hold_min",
                "exit_reasons",
            ],
        )
        writer.writeheader()
        writer.writerows(ranked_rows)

    report_path.write_text(
        _build_html_report(
            ranked_rows=ranked_rows,
            output_dir=output_dir,
        ),
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "strategy": STRATEGY,
                "symbol": SYMBOL,
                "timeframe": TIMEFRAME,
                "research_profile": RESEARCH_PROFILE,
                "bar_count": len(bars),
                "winner": ranked_rows[0] if ranked_rows else None,
                "output_dir": str(output_dir.resolve()),
                "report_html": str(report_path.resolve()),
                "summary_csv": str(summary_path.resolve()),
                "study_json": str(study_path.resolve()),
            },
            indent=2,
        )
    )


def _flatten_report(report: dict) -> dict:
    combined = report["combined"]
    monthly_summary = report["monthly"]["summary"]
    rolling = report["rolling"]
    recent = report.get("recent", {})
    recent_trade_days = recent.get("last_12_trade_days", {})
    latest_3m = recent.get("latest_3m", {})
    positive_month_ratio = _ratio(
        monthly_summary.get("positive_months", 0),
        monthly_summary.get("total_months", 0),
    )
    positive_3m_ratio = _ratio(
        rolling.get("3m", {}).get("summary", {}).get("positive_windows", 0),
        rolling.get("3m", {}).get("summary", {}).get("count", 0),
    )
    positive_6m_ratio = _ratio(
        rolling.get("6m", {}).get("summary", {}).get("positive_windows", 0),
        rolling.get("6m", {}).get("summary", {}).get("count", 0),
    )
    return {
        "rank": 0,
        "exit_policy": report["exit_policy"],
        "policy_label": policy_label(report["exit_policy"]),
        "signals": combined["signals"],
        "trades": combined["trades"],
        "return_pct": combined["return_pct"],
        "profit_factor": combined["profit_factor"],
        "win_rate": combined["win_rate"],
        "max_dd_pct": combined["max_dd_pct"],
        "positive_month_ratio": round(positive_month_ratio, 4),
        "positive_3m_ratio": round(positive_3m_ratio, 4),
        "positive_6m_ratio": round(positive_6m_ratio, 4),
        "recent_trade_days": recent_trade_days.get("days", 0),
        "recent_trade_days_period": recent_trade_days.get("period", ""),
        "recent_trade_day_pnl": recent_trade_days.get("pnl", 0.0),
        "recent_trade_day_return_pct": recent_trade_days.get("return_pct", 0.0),
        "latest_3m_label": latest_3m.get("label", ""),
        "latest_3m_return_pct": latest_3m.get("return_pct", 0.0),
        "passes_recent_gate": bool(recent.get("gate_passed")),
        "avg_hold_min": combined["avg_hold_min"],
        "median_hold_min": combined["median_hold_min"],
        "exit_reasons": json.dumps(combined["exit_reasons"], ensure_ascii=False, sort_keys=True),
    }


def _ranking_key(row: dict) -> tuple[float, float, float, float, float, float, float, float, float]:
    return (
        1.0 if row["passes_recent_gate"] else 0.0,
        float(row["profit_factor"]),
        -float(row["max_dd_pct"]),
        float(row["positive_month_ratio"]),
        float(row["positive_3m_ratio"]),
        float(row["positive_6m_ratio"]),
        float(row["latest_3m_return_pct"]),
        float(row["recent_trade_day_pnl"]),
        float(row["return_pct"]),
    )


def _ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def _load_cached_bars(
    *,
    symbol: str,
    timeframe: str,
    start: str,
    end: str | None,
    limit: int | None,
) -> list[dict]:
    if not DB_PATH.exists():
        raise RuntimeError(f"Study DB does not exist: {DB_PATH}")

    query = [
        "select timestamp, open, high, low, close, volume",
        "from bars_cache",
        "where symbol = ? and timeframe = ? and timestamp >= ?",
    ]
    params: list[object] = [symbol.upper(), timeframe, _sqlite_timestamp(start)]
    if end:
        query.append("and timestamp <= ?")
        params.append(_sqlite_timestamp(end, end_of_day=True))
    query.append("order by timestamp asc")
    if limit is not None:
        query.append("limit ?")
        params.append(limit)

    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(" ".join(query), params).fetchall()

    return [
        {
            "time": _normalize_sqlite_timestamp(timestamp),
            "open": float(open_),
            "high": float(high),
            "low": float(low),
            "close": float(close),
            "volume": int(volume),
        }
        for timestamp, open_, high, low, close, volume in rows
    ]


def _sqlite_timestamp(value: str, *, end_of_day: bool = False) -> str:
    normalized = value.strip().replace("T", " ")
    if len(normalized) == 10:
        suffix = "23:59:59" if end_of_day else "00:00:00"
        return f"{normalized} {suffix}"
    return normalized.replace("Z", "").split("+")[0]


def _normalize_sqlite_timestamp(value: str) -> str:
    raw = value.replace(" ", "T")
    if "+" not in raw:
        raw = f"{raw}+00:00"
    return raw


def policy_label(policy: str) -> str:
    mapping = {
        "breakout_session_close": "收盘平仓",
        "breakout_target_1r": "固定 1R 止盈",
        "breakout_target_1_5r": "固定 1.5R 止盈",
        "breakout_target_2r": "固定 2R 止盈",
        "breakout_target_2_5r_break_even_after_0_75r": "0.75R 后保本 + 固定 2.5R 止盈",
        "breakout_measured_move": "breakout bar measured move 止盈",
        "breakout_break_even_after_1r": "1R 后提到保本",
        "breakout_pullback_low_after_1r": "1R 后提到 pullback low",
        "breakout_swing_ema_after_1r": "1R 后 swing low / EMA20 动态离场",
        "pullback_count_session_close": "收盘平仓",
        "pullback_count_target_1r": "固定 1R 止盈",
        "pullback_count_target_1_5r": "固定 1.5R 止盈",
        "pullback_count_target_2r": "固定 2R 止盈",
        "pullback_count_target_2r_break_even_after_0_75r": "0.75R 后保本 + 固定 2R 止盈",
        "pullback_count_break_even_after_1r": "1R 后提到保本",
        "pullback_count_pullback_low_after_1r": "1R 后提到 H2 pullback low",
        "pullback_count_swing_ema_after_1r": "1R 后 swing low / EMA20 动态离场",
    }
    return mapping.get(policy, policy)


def _build_html_report(*, ranked_rows: list[dict], output_dir: Path) -> str:
    winner = next((row for row in ranked_rows if row["passes_recent_gate"]), None)
    winner_html = ""
    if winner is not None:
        winner_html = (
            f"<div class='winner'>"
            f"<h2>当前胜出方案</h2>"
            f"<p><strong>{html.escape(winner['policy_label'])}</strong> "
            f"({html.escape(winner['exit_policy'])})</p>"
            f"<p>PF {winner['profit_factor']} · Max DD {winner['max_dd_pct']}% · "
            f"Return {winner['return_pct']}% · 正收益月份占比 {winner['positive_month_ratio']:.2%}</p>"
            f"<p>最近 12 个有成交交易日：{winner['recent_trade_days_period']} · "
            f"净盈亏 {'+' if winner['recent_trade_day_pnl'] >= 0 else ''}{winner['recent_trade_day_pnl']:.2f} · "
            f"收益 {winner['recent_trade_day_return_pct']}%</p>"
            f"<p>最近 3 个月窗口 {html.escape(winner['latest_3m_label'])}："
            f"{winner['latest_3m_return_pct']}%</p>"
            f"</div>"
        )
    elif ranked_rows:
        winner_html = (
            "<div class='winner' style='border-color: rgba(255, 159, 67, 0.35); background: rgba(255, 159, 67, 0.08);'>"
            "<h2>当前没有满足近期门槛的方案</h2>"
            "<p>这轮不会自动升默认策略。门槛是：最近 12 个有成交交易日净盈亏大于 0，且最近 3 个月窗口收益大于 0。</p>"
            "</div>"
        )

    rows_html = "\n".join(
        (
            "<tr>"
            f"<td>{row['rank']}</td>"
            f"<td>{html.escape(row['policy_label'])}</td>"
            f"<td><code>{html.escape(row['exit_policy'])}</code></td>"
            f"<td>{'通过' if row['passes_recent_gate'] else '未通过'}</td>"
            f"<td>{row['signals']}</td>"
            f"<td>{row['trades']}</td>"
            f"<td>{row['return_pct']}</td>"
            f"<td>{row['profit_factor']}</td>"
            f"<td>{row['max_dd_pct']}</td>"
            f"<td>{row['positive_month_ratio']:.2%}</td>"
            f"<td>{row['positive_3m_ratio']:.2%}</td>"
            f"<td>{row['positive_6m_ratio']:.2%}</td>"
            f"<td>{'+' if row['recent_trade_day_pnl'] >= 0 else ''}{row['recent_trade_day_pnl']:.2f}</td>"
            f"<td>{row['latest_3m_return_pct']:.2f}%</td>"
            f"<td>{row['avg_hold_min']}</td>"
            f"<td>{html.escape(row['exit_reasons'])}</td>"
            "</tr>"
        )
        for row in ranked_rows
    )

    return f"""<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <title>breakout exit study</title>
    <style>
      body {{
        margin: 0;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        background: #0b1220;
        color: #e8eefb;
      }}
      main {{
        max-width: 1200px;
        margin: 0 auto;
        padding: 32px 24px 48px;
      }}
      h1, h2 {{
        margin: 0 0 12px;
      }}
      p {{
        color: #aeb8d0;
      }}
      .winner {{
        margin: 20px 0 28px;
        padding: 16px 18px;
        border: 1px solid rgba(78, 205, 196, 0.35);
        border-radius: 14px;
        background: rgba(78, 205, 196, 0.08);
      }}
      table {{
        width: 100%;
        border-collapse: collapse;
        background: rgba(255, 255, 255, 0.03);
        border-radius: 14px;
        overflow: hidden;
      }}
      th, td {{
        padding: 10px 12px;
        border-bottom: 1px solid rgba(255, 255, 255, 0.08);
        text-align: left;
        font-size: 14px;
      }}
      th {{
        color: #9fb0d6;
        background: rgba(255, 255, 255, 0.04);
      }}
      code {{
        font-size: 12px;
        color: #ffd49a;
      }}
      .meta {{
        margin-top: 10px;
        font-size: 13px;
      }}
    </style>
  </head>
    <body>
      <main>
      <h1>brooks_breakout_pullback Exit Study</h1>
      <p>同一批 `QQQ 5m qqq_5m_phase1` breakout 信号，只替换 exit policy。先过近期门槛：最近 12 个有成交交易日净盈亏必须大于 0，且最近 3 个月窗口收益必须大于 0；然后再按稳健性排序。</p>
      <div class="meta">输出目录：{html.escape(str(output_dir.resolve()))}</div>
      {winner_html}
      <table>
        <thead>
          <tr>
            <th>排名</th>
            <th>方案</th>
            <th>策略 ID</th>
            <th>近期门槛</th>
            <th>信号</th>
            <th>交易</th>
            <th>收益%</th>
            <th>PF</th>
            <th>最大回撤%</th>
            <th>正收益月份</th>
            <th>正收益 3m</th>
            <th>正收益 6m</th>
            <th>最近12交易日净盈亏</th>
            <th>最近3个月收益%</th>
            <th>平均持仓(min)</th>
            <th>出场分布</th>
          </tr>
        </thead>
        <tbody>
          {rows_html}
        </tbody>
      </table>
    </main>
  </body>
</html>"""


if __name__ == "__main__":
    main()
