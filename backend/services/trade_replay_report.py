from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from html import escape
from pathlib import Path

from services.phase1_exit import compute_ema_series
from services.research_profile import canonical_timestamp, market_time, session_day


SVG_WIDTH = 1440
SVG_HEIGHT = 860
BROOKS_COMBO_LABEL = "QQQ 5m Brooks 组合"
PLOT_LEFT = 64
PLOT_TOP = 56
PLOT_WIDTH = 980
PLOT_HEIGHT = 520
PLOT_RIGHT = PLOT_LEFT + PLOT_WIDTH
PLOT_BOTTOM = PLOT_TOP + PLOT_HEIGHT
SIDEBAR_LEFT = 1088
SIDEBAR_WIDTH = 300
SIDEBAR_TOP = 96


@dataclass(frozen=True)
class ReplayReportResult:
    output_dir: Path
    report_path: Path
    summary_path: Path
    chart_paths: list[Path]
    trade_count: int
    trade_day_count: int
    strategy: str
    symbol: str
    timeframe: str
    period: str


def write_trade_replay_report(
    *,
    strategy_name: str,
    symbol: str,
    timeframe: str,
    research_profile: str | None,
    bars: list[dict],
    trades: list[dict],
    output_dir: str | Path,
    stop_loss_pct: float,
    take_profit_pct: float,
    max_trade_days: int | None = None,
) -> ReplayReportResult:
    normalized_bars = [{**bar, "time": canonical_timestamp(bar["time"])} for bar in bars]
    ema20_values = compute_ema_series(normalized_bars, 20)
    normalized_bars = [
        {**bar, "ema20": ema20_values[index]}
        for index, bar in enumerate(normalized_bars)
    ]
    normalized_trades = [_normalize_trade(trade) for trade in trades]
    day_bars = _group_bars_by_day(normalized_bars)
    grouped_trades = _group_trades_by_day(normalized_trades)
    ordered_days = sorted(grouped_trades.keys())
    if max_trade_days is not None:
        ordered_days = ordered_days[-max_trade_days:]

    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)

    chart_paths: list[Path] = []
    summary_rows: list[dict[str, str]] = []
    report_entries: list[dict] = []
    for day in ordered_days:
        trades_for_day = grouped_trades[day]
        bars_for_day = day_bars.get(day, [])
        if not bars_for_day:
            continue

        svg_name = f"{day}.svg"
        svg_path = root / svg_name
        svg_path.write_text(
            _render_trade_day_svg(
                day=day,
                bars=bars_for_day,
                trades=trades_for_day,
                strategy_name=strategy_name,
                symbol=symbol,
                timeframe=timeframe,
                stop_loss_pct=stop_loss_pct,
                take_profit_pct=take_profit_pct,
            ),
            encoding="utf-8",
        )
        chart_paths.append(svg_path)
        report_entries.append(
            {
                "day": day,
                "svg_name": svg_name,
                "trade_count": len(trades_for_day),
                "trades": trades_for_day,
            }
        )

        for index, trade in enumerate(trades_for_day, start=1):
            summary_rows.append(
                {
                    "交易日": day,
                    "序号": str(index),
                    "开仓时间": trade["entry_time"],
                    "出场时间": trade["exit_time"],
                    "方向": _describe_side(trade["side"]),
                    "开仓价": f'{trade["entry_price"]:.2f}',
                    "出场价": f'{trade["exit_price"]:.2f}',
                    "止损价": f'{trade["stop_loss"]:.2f}',
                    "止盈价": (
                        f'{trade["target_price"]:.2f}'
                        if trade["target_price"] is not None
                        else ""
                    ),
                    "数量": str(trade["quantity"]),
                    "盈亏": f'{trade["pnl"]:.2f}',
                    "盈亏比例": f'{trade["pnl_pct"]:.2f}',
                    "开仓理由": _describe_entry_reason(trade["reason"]),
                    "止损理由": _describe_stop_reason(
                        trade["stop_reason"],
                        stop_loss_pct,
                    ),
                    "止盈理由": _describe_target_reason(
                        trade["target_reason"],
                        take_profit_pct,
                    ),
                    "实际出场理由": _describe_exit_reason(trade["exit_reason"]),
                    "图表文件": svg_name,
                }
            )

    summary_path = root / "summary.csv"
    _write_summary_csv(summary_path, summary_rows)

    report_path = root / "report.html"
    report_path.write_text(
        _render_report_html(
            strategy_name=strategy_name,
            symbol=symbol,
            timeframe=timeframe,
            research_profile=research_profile,
            period=_build_period(normalized_bars),
            summary_rows=summary_rows,
            report_entries=list(reversed(report_entries)),
        ),
        encoding="utf-8",
    )

    return ReplayReportResult(
        output_dir=root,
        report_path=report_path,
        summary_path=summary_path,
        chart_paths=chart_paths,
        trade_count=len(summary_rows),
        trade_day_count=len(chart_paths),
        strategy=strategy_name,
        symbol=symbol,
        timeframe=timeframe,
        period=_build_period(normalized_bars),
    )


def _render_trade_day_svg(
    *,
    day: str,
    bars: list[dict],
    trades: list[dict],
    strategy_name: str,
    symbol: str,
    timeframe: str,
    stop_loss_pct: float,
    take_profit_pct: float,
) -> str:
    lows = [float(bar["low"]) for bar in bars]
    highs = [float(bar["high"]) for bar in bars]
    ema20_values = [
        float(bar["ema20"])
        for bar in bars
        if bar.get("ema20") is not None and float(bar["ema20"]) > 0
    ]
    annotated_prices = lows + highs + ema20_values
    for trade in trades:
        annotated_prices.extend(
            [
                float(trade["entry_price"]),
                float(trade["exit_price"]),
                float(trade["stop_loss"]),
            ]
        )
        if trade["target_price"] is not None:
            annotated_prices.append(float(trade["target_price"]))

    min_price = min(annotated_prices)
    max_price = max(annotated_prices)
    price_padding = max((max_price - min_price) * 0.08, 0.5)
    chart_min = min_price - price_padding
    chart_max = max_price + price_padding
    candle_gap = PLOT_WIDTH / max(len(bars), 1)
    candle_width = max(min(candle_gap * 0.58, 14.0), 3.0)

    def x_for_bar(index: int) -> float:
        return PLOT_LEFT + candle_gap * index + candle_gap / 2

    def y_for_price(price: float) -> float:
        if chart_max == chart_min:
            return PLOT_TOP + PLOT_HEIGHT / 2
        return PLOT_TOP + (chart_max - price) / (chart_max - chart_min) * PLOT_HEIGHT

    bar_index_by_time = {bar["time"]: idx for idx, bar in enumerate(bars)}

    svg: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{SVG_WIDTH}" height="{SVG_HEIGHT}" viewBox="0 0 {SVG_WIDTH} {SVG_HEIGHT}">',
        "<defs>",
        '<style><![CDATA[',
        ".bg { fill: #0f1117; }",
        ".panel { fill: #151c2b; stroke: #283247; stroke-width: 1; }",
        ".grid { stroke: #243047; stroke-width: 1; }",
        ".axis { fill: #8a98b3; font: 12px ui-monospace, SFMono-Regular, Menlo, monospace; }",
        ".title { fill: #edf2ff; font: 700 26px ui-sans-serif, -apple-system, BlinkMacSystemFont, sans-serif; }",
        ".subtitle { fill: #9fb0cb; font: 14px ui-sans-serif, -apple-system, BlinkMacSystemFont, sans-serif; }",
        ".label { fill: #dce7ff; font: 600 13px ui-sans-serif, -apple-system, BlinkMacSystemFont, sans-serif; }",
        ".value { fill: #aab7cf; font: 13px ui-sans-serif, -apple-system, BlinkMacSystemFont, sans-serif; }",
        ".up { fill: #18c77a; stroke: #18c77a; }",
        ".down { fill: #f15b5d; stroke: #f15b5d; }",
        ".ema20 { fill: none; stroke: #f3c969; stroke-width: 2.6; stroke-linejoin: round; stroke-linecap: round; }",
        ".ema-label { fill: #f3c969; font: 700 13px ui-sans-serif, -apple-system, BlinkMacSystemFont, sans-serif; }",
        ".setup-pointer { stroke: #ffd166; stroke-width: 2; }",
        ".setup-badge { fill: #271c08; stroke: #ffd166; stroke-width: 1.4; }",
        ".setup-title { fill: #fff3bd; font: 800 14px ui-sans-serif, -apple-system, BlinkMacSystemFont, sans-serif; }",
        ".setup-detail { fill: #ffd166; font: 12px ui-sans-serif, -apple-system, BlinkMacSystemFont, sans-serif; }",
        ".entry { stroke: #46a0ff; stroke-width: 2; stroke-dasharray: 8 6; }",
        ".exit { stroke: #b270ff; stroke-width: 2; stroke-dasharray: 8 6; }",
        ".stop { stroke: #ff6b6b; stroke-width: 2; stroke-dasharray: 10 6; }",
        ".target { stroke: #2ec98f; stroke-width: 2; stroke-dasharray: 10 6; }",
        ".legend-box { fill: #101829; stroke: #27334a; stroke-width: 1; rx: 14; }",
        ".legend-title { fill: #f1f5ff; font: 700 14px ui-sans-serif, -apple-system, BlinkMacSystemFont, sans-serif; }",
        ".legend-text { fill: #c8d4ea; font: 13px ui-sans-serif, -apple-system, BlinkMacSystemFont, sans-serif; }",
        ".legend-muted { fill: #8ea1c0; font: 12px ui-sans-serif, -apple-system, BlinkMacSystemFont, sans-serif; }",
        "]]></style>",
        "</defs>",
        '<rect class="bg" x="0" y="0" width="1440" height="860" />',
        f'<text class="title" x="{PLOT_LEFT}" y="34">{escape(symbol)} {escape(timeframe)} 标注回放</text>',
        (
            f'<text class="subtitle" x="{PLOT_LEFT}" y="60">'
            f"{escape(strategy_name)} | {escape(day)} | {len(trades)} 笔交易"
            "</text>"
        ),
        f'<rect class="panel" x="{PLOT_LEFT}" y="{PLOT_TOP}" width="{PLOT_WIDTH}" height="{PLOT_HEIGHT}" rx="18" />',
        f'<rect class="panel" x="{SIDEBAR_LEFT}" y="{SIDEBAR_TOP}" width="{SIDEBAR_WIDTH}" height="680" rx="18" />',
    ]

    for step in range(6):
        price = chart_min + (chart_max - chart_min) * step / 5
        y = y_for_price(price)
        svg.append(f'<line class="grid" x1="{PLOT_LEFT}" y1="{y:.2f}" x2="{PLOT_RIGHT}" y2="{y:.2f}" />')
        svg.append(f'<text class="axis" x="{PLOT_RIGHT + 12}" y="{y + 4:.2f}">{price:.2f}</text>')

    label_indexes = _time_label_indexes(len(bars))
    for index in label_indexes:
        x = x_for_bar(index)
        svg.append(f'<line class="grid" x1="{x:.2f}" y1="{PLOT_TOP}" x2="{x:.2f}" y2="{PLOT_BOTTOM}" />')
        label = market_time(bars[index]["time"]).strftime("%H:%M")
        svg.append(f'<text class="axis" x="{x - 18:.2f}" y="{PLOT_BOTTOM + 24}">{label}</text>')

    for index, bar in enumerate(bars):
        x = x_for_bar(index)
        open_price = float(bar["open"])
        close_price = float(bar["close"])
        high_price = float(bar["high"])
        low_price = float(bar["low"])
        y_open = y_for_price(open_price)
        y_close = y_for_price(close_price)
        y_high = y_for_price(high_price)
        y_low = y_for_price(low_price)
        is_up = close_price >= open_price
        cls = "up" if is_up else "down"
        body_top = min(y_open, y_close)
        body_height = max(abs(y_close - y_open), 1.8)
        svg.append(f'<line class="{cls}" x1="{x:.2f}" y1="{y_high:.2f}" x2="{x:.2f}" y2="{y_low:.2f}" stroke-width="1.4" />')
        svg.append(
            f'<rect class="{cls}" x="{x - candle_width / 2:.2f}" y="{body_top:.2f}" '
            f'width="{candle_width:.2f}" height="{body_height:.2f}" rx="1.5" />'
        )

    ema20_points = [
        (
            x_for_bar(index),
            y_for_price(float(bar["ema20"])),
            float(bar["ema20"]),
        )
        for index, bar in enumerate(bars)
        if bar.get("ema20") is not None and float(bar["ema20"]) > 0
    ]
    if len(ema20_points) >= 2:
        points = " ".join(f"{x:.2f},{y:.2f}" for x, y, _ in ema20_points)
        last_x, last_y, last_value = ema20_points[-1]
        label_x = min(last_x + 8, PLOT_RIGHT - 92)
        label_y = max(PLOT_TOP + 18, min(PLOT_BOTTOM - 8, last_y - 8))
        svg.append(f'<polyline class="ema20" points="{points}" />')
        svg.append(
            f'<text class="ema-label" x="{label_x:.2f}" y="{label_y:.2f}">EMA20 {last_value:.2f}</text>'
        )

    sidebar_y = SIDEBAR_TOP + 26
    svg.extend(
        [
            f'<text class="legend-title" x="{SIDEBAR_LEFT + 20}" y="{sidebar_y}">交易回放</text>',
            f'<text class="legend-muted" x="{SIDEBAR_LEFT + 20}" y="{sidebar_y + 24}">{escape(symbol)} | {escape(timeframe)} | {escape(day)}</text>',
            f'<line class="ema20" x1="{SIDEBAR_LEFT + 20}" y1="{sidebar_y + 48}" x2="{SIDEBAR_LEFT + 72}" y2="{sidebar_y + 48}" />',
            f'<text class="legend-text" x="{SIDEBAR_LEFT + 82}" y="{sidebar_y + 53}">EMA20 趋势线</text>',
        ]
    )

    for trade_index, trade in enumerate(trades, start=1):
        entry_idx = bar_index_by_time.get(trade["entry_time"])
        exit_idx = bar_index_by_time.get(trade["exit_time"])
        if entry_idx is None or exit_idx is None:
            continue

        entry_x = x_for_bar(entry_idx)
        exit_x = x_for_bar(exit_idx)
        entry_y = y_for_price(float(trade["entry_price"]))
        exit_y = y_for_price(float(trade["exit_price"]))
        stop_y = y_for_price(float(trade["stop_loss"]))

        svg.append(f'<line class="entry" x1="{entry_x:.2f}" y1="{PLOT_TOP}" x2="{entry_x:.2f}" y2="{PLOT_BOTTOM}" />')
        svg.append(f'<line class="exit" x1="{exit_x:.2f}" y1="{PLOT_TOP}" x2="{exit_x:.2f}" y2="{PLOT_BOTTOM}" />')
        svg.append(f'<line class="stop" x1="{entry_x:.2f}" y1="{stop_y:.2f}" x2="{exit_x:.2f}" y2="{stop_y:.2f}" />')
        svg.append(f'<circle cx="{entry_x:.2f}" cy="{entry_y:.2f}" r="5.5" fill="#46a0ff" />')
        svg.append(f'<circle cx="{exit_x:.2f}" cy="{exit_y:.2f}" r="5.5" fill="#b270ff" />')
        svg.append(
            f'<text class="label" x="{max(entry_x - 34, PLOT_LEFT + 6):.2f}" y="{entry_y - 10:.2f}" fill="#46a0ff">开仓</text>'
        )
        svg.append(
            f'<text class="label" x="{max(exit_x - 24, PLOT_LEFT + 6):.2f}" y="{exit_y - 10:.2f}" fill="#b270ff">出场</text>'
        )
        svg.append(
            f'<text class="legend-text" x="{PLOT_RIGHT - 120}" y="{stop_y - 8:.2f}" fill="#ff6b6b">止损 {trade["stop_loss"]:.2f}</text>'
        )

        setup_marker = _extract_pullback_count_marker(trade["reason"])
        if setup_marker is not None:
            entry_bar = bars[entry_idx]
            if setup_marker["direction"] == "long":
                anchor_y = y_for_price(float(entry_bar["high"]))
                badge_y = max(PLOT_TOP + 10, anchor_y - 58)
                pointer_end_y = badge_y + 44
            else:
                anchor_y = y_for_price(float(entry_bar["low"]))
                badge_y = min(PLOT_BOTTOM - 58, anchor_y + 16)
                pointer_end_y = badge_y
            badge_x = min(max(entry_x + 12, PLOT_LEFT + 8), PLOT_RIGHT - 168)
            pointer_end_x = badge_x + 18
            svg.append(
                f'<line class="setup-pointer" x1="{entry_x:.2f}" y1="{anchor_y:.2f}" '
                f'x2="{pointer_end_x:.2f}" y2="{pointer_end_y:.2f}" />'
            )
            svg.append(
                f'<rect class="setup-badge" x="{badge_x:.2f}" y="{badge_y:.2f}" width="156" height="44" rx="12" />'
            )
            svg.append(
                f'<text class="setup-title" x="{badge_x + 12:.2f}" y="{badge_y + 18:.2f}">'
                f'{escape(setup_marker["label"])}'
                "</text>"
            )
            svg.append(
                f'<text class="setup-detail" x="{badge_x + 12:.2f}" y="{badge_y + 36:.2f}">'
                f'{escape(setup_marker["detail"])}'
                "</text>"
            )

        if trade["target_price"] is not None:
            target_y = y_for_price(float(trade["target_price"]))
            svg.append(f'<line class="target" x1="{entry_x:.2f}" y1="{target_y:.2f}" x2="{exit_x:.2f}" y2="{target_y:.2f}" />')
            svg.append(
                f'<text class="legend-text" x="{PLOT_RIGHT - 132}" y="{target_y - 8:.2f}" fill="#2ec98f">止盈 {trade["target_price"]:.2f}</text>'
            )

        box_y = sidebar_y + 76 + (trade_index - 1) * 156
        svg.append(
            f'<rect class="legend-box" x="{SIDEBAR_LEFT + 16}" y="{box_y}" width="{SIDEBAR_WIDTH - 32}" height="142" />'
        )
        svg.append(
            f'<text class="legend-title" x="{SIDEBAR_LEFT + 32}" y="{box_y + 24}">交易 {trade_index}</text>'
        )
        meta_line = (
            f'{market_time(trade["entry_time"]).strftime("%H:%M")} -> '
            f'{market_time(trade["exit_time"]).strftime("%H:%M")} | '
            f'{_describe_side(trade["side"])} | {trade["quantity"]}股 | '
            f'{"+" if trade["pnl"] >= 0 else ""}{trade["pnl"]:.2f}'
        )
        svg.append(
            f'<text class="legend-muted" x="{SIDEBAR_LEFT + 32}" y="{box_y + 44}">{escape(meta_line)}</text>'
        )
        note_y = box_y + 68
        notes = [
            ("开仓理由", _describe_entry_reason(trade["reason"]), "#46a0ff"),
            ("止损理由", _describe_stop_reason(trade["stop_reason"], stop_loss_pct), "#ff6b6b"),
            ("止盈理由", _describe_target_reason(trade["target_reason"], take_profit_pct), "#2ec98f"),
            ("实际出场理由", _describe_exit_reason(trade["exit_reason"]), "#b270ff"),
        ]
        for title, text, color in notes:
            svg.append(
                f'<text class="label" x="{SIDEBAR_LEFT + 32}" y="{note_y}" fill="{color}">{escape(title)}</text>'
            )
            svg.append(
                f'<text class="legend-text" x="{SIDEBAR_LEFT + 130}" y="{note_y}">{escape(_truncate(text, 28))}</text>'
            )
            note_y += 22

    svg.append("</svg>")
    return "".join(svg)


def _write_summary_csv(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = [
        "交易日",
        "序号",
        "开仓时间",
        "出场时间",
        "方向",
        "开仓价",
        "出场价",
        "止损价",
        "止盈价",
        "数量",
        "盈亏",
        "盈亏比例",
        "开仓理由",
        "止损理由",
        "止盈理由",
        "实际出场理由",
        "图表文件",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _render_report_html(
    *,
    strategy_name: str,
    symbol: str,
    timeframe: str,
    research_profile: str | None,
    period: str,
    summary_rows: list[dict[str, str]],
    report_entries: list[dict],
) -> str:
    total_pnl = sum(float(row["盈亏"]) for row in summary_rows)
    wins = sum(1 for row in summary_rows if float(row["盈亏"]) > 0)
    losses = sum(1 for row in summary_rows if float(row["盈亏"]) <= 0)
    strategy_summary = _render_strategy_summary(strategy_name)

    cards = []
    for entry in report_entries:
        trade_list = "".join(
            [
                (
                    "<li>"
                    f'{escape(trade["entry_time"])} -> {escape(trade["exit_time"])} | '
                    f'盈亏 {"+" if trade["pnl"] >= 0 else ""}{trade["pnl"]:.2f} | '
                    f'{escape(_describe_exit_reason(trade["exit_reason"]))}'
                    "</li>"
                )
                for trade in entry["trades"]
            ]
        )
        cards.append(
            (
                '<section class="card">'
                f'<div class="card-meta"><h2>{escape(entry["day"])}</h2><p>{entry["trade_count"]} 笔交易</p></div>'
                f'<img src="{escape(entry["svg_name"])}" alt="{escape(entry["day"])} 标注回放" />'
                f"<ul>{trade_list}</ul>"
                "</section>"
            )
        )

    rows = []
    for row in summary_rows:
        rows.append(
            "<tr>"
            f'<td>{escape(row["交易日"])}</td>'
            f'<td>{escape(row["开仓时间"])}</td>'
            f'<td>{escape(row["出场时间"])}</td>'
            f'<td>{escape(row["方向"])}</td>'
            f'<td>{escape(row["开仓价"])}</td>'
            f'<td>{escape(row["出场价"])}</td>'
            f'<td>{escape(row["盈亏"])}</td>'
            f'<td>{escape(row["实际出场理由"])}</td>'
            f'<td><a href="{escape(row["图表文件"])}">{escape(row["图表文件"])}</a></td>'
            "</tr>"
        )

    return f"""<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <title>{escape(strategy_name)} 交易回放报告</title>
    <style>
      body {{
        margin: 0;
        font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, sans-serif;
        background: #0f1117;
        color: #e8edf8;
      }}
      main {{
        max-width: 1320px;
        margin: 0 auto;
        padding: 32px 28px 64px;
      }}
      .hero {{
        display: grid;
        grid-template-columns: 1.4fr 1fr;
        gap: 16px;
        align-items: start;
      }}
      .panel {{
        background: #141c2a;
        border: 1px solid #2a3447;
        border-radius: 20px;
        padding: 20px 22px;
      }}
      h1 {{
        margin: 0 0 10px;
        font-size: 32px;
      }}
      .muted {{
        color: #9ab0ce;
      }}
      .stats {{
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 12px;
      }}
      .stat {{
        background: #0f1521;
        border: 1px solid #243047;
        border-radius: 16px;
        padding: 14px 16px;
      }}
      .stat b {{
        display: block;
        font-size: 22px;
        margin-top: 6px;
      }}
      .strategy-summary {{
        margin-top: 18px;
      }}
      .strategy-summary h2 {{
        margin: 0 0 12px;
      }}
      .strategy-summary p {{
        margin: 0;
        color: #c9d7ef;
        line-height: 1.7;
      }}
      .strategy-grid {{
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 12px;
        margin-top: 16px;
      }}
      .strategy-point {{
        background: #0f1521;
        border: 1px solid #243047;
        border-radius: 16px;
        padding: 14px 16px;
      }}
      .strategy-point span {{
        display: block;
        color: #9ab0ce;
        font-size: 12px;
        margin-bottom: 8px;
      }}
      .strategy-point b {{
        color: #f4f7ff;
        font-size: 14px;
        line-height: 1.55;
      }}
      table {{
        width: 100%;
        border-collapse: collapse;
        margin-top: 18px;
      }}
      th, td {{
        text-align: left;
        padding: 10px 12px;
        border-bottom: 1px solid #263148;
        font-size: 14px;
      }}
      a {{
        color: #79b8ff;
      }}
      .cards {{
        display: grid;
        gap: 18px;
        margin-top: 22px;
      }}
      .card {{
        background: #141c2a;
        border: 1px solid #2a3447;
        border-radius: 20px;
        padding: 18px;
      }}
      .card img {{
        width: 100%;
        height: auto;
        display: block;
        margin-top: 12px;
        border-radius: 16px;
        border: 1px solid #2a3447;
        background: #0f1117;
      }}
      .card-meta {{
        display: flex;
        justify-content: space-between;
        align-items: baseline;
        gap: 12px;
      }}
      .card h2 {{
        margin: 0;
      }}
      .card ul {{
        margin: 14px 0 0;
        padding-left: 20px;
        color: #c9d7ef;
      }}
    </style>
  </head>
  <body>
    <main>
      <section class="hero">
        <div class="panel">
          <h1>{escape(strategy_name)} 交易回放报告</h1>
          <p class="muted">{escape(symbol)} | {escape(timeframe)} | {escape(period)} | 研究配置 {escape(research_profile or "none")}</p>
          <p class="muted">这批报告会为每个有成交的交易日生成一张标注回放图。每张 SVG 都会标出开仓、止损、存在时的止盈，以及实际出场，并附上对应理由。</p>
        </div>
        <div class="panel stats">
          <div class="stat"><span class="muted">交易日</span><b>{len(report_entries)}</b></div>
          <div class="stat"><span class="muted">交易笔数</span><b>{len(summary_rows)}</b></div>
          <div class="stat"><span class="muted">盈利 / 亏损</span><b>{wins} / {losses}</b></div>
          <div class="stat"><span class="muted">净盈亏</span><b>{"+" if total_pnl >= 0 else ""}{total_pnl:.2f}</b></div>
        </div>
      </section>

      {strategy_summary}

      <section class="panel" style="margin-top: 18px;">
        <h2 style="margin: 0;">summary.csv</h2>
        <table>
          <thead>
            <tr>
              <th>交易日</th>
              <th>开仓时间</th>
              <th>出场时间</th>
              <th>方向</th>
              <th>开仓价</th>
              <th>出场价</th>
              <th>盈亏</th>
              <th>实际出场理由</th>
              <th>图表</th>
            </tr>
          </thead>
          <tbody>
            {''.join(rows)}
          </tbody>
        </table>
      </section>

      <div class="cards">
        {''.join(cards)}
      </div>
    </main>
  </body>
</html>
"""


def _render_strategy_summary(strategy_name: str) -> str:
    summaries = {
        "brooks_pullback_count": {
            "title": "策略摘要：H2 多头回调计数",
            "overview": (
                "这个策略专门找 QQQ 5 分钟图里的多头趋势回调延续机会。它不是追任意上涨，"
                "而是先确认价格在强势多头环境里，然后等待第二段回调结束，只有反转 K 线重新向上突破前一根高点时才做多。"
            ),
            "points": [
                ("交易方向", f"只做多，适配 {BROOKS_COMBO_LABEL} 的美股常规交易时段。"),
                ("入场条件", "H2 回调反转：第二段回调后出现强阳线，并突破上一根 K 线高点。"),
                ("过滤条件", "价格在 EMA20 上方、EMA20 向上、收盘高于当日开盘，并高于 session VWAP 缓冲。"),
                ("出场逻辑", "结构止损放在 H2 回调低点下方；无固定止盈，达到 1R 后用 swing low / EMA20 动态离场，或收盘平仓。"),
            ],
        },
        "brooks_breakout_pullback": {
            "title": "策略摘要：突破后的回调买入",
            "overview": (
                "这个策略寻找多头突破后的第一次有效回调。它要求突破先建立趋势强度，随后价格回踩但不破坏结构，"
                "再在回调恢复向上时做多。"
            ),
            "points": [
                ("交易方向", f"只做多，运行在 {BROOKS_COMBO_LABEL} 研究配置。"),
                ("入场条件", "多头突破后回调守住结构，再重新向上确认。"),
                ("过滤条件", "关注趋势、突破质量和回调防守，不交易弱突破或破坏结构的回调。"),
                ("出场逻辑", "结构止损放在 breakout/pullback 低点下方，默认 0.75R 后保本并以 2.5R 目标管理。"),
            ],
        },
        "brooks_small_pb_trend": {
            "title": "策略摘要：小回调趋势延续",
            "overview": (
                "这个策略寻找强趋势中的浅回调延续。它更偏向趋势跟随，要求回调幅度小、趋势结构仍然完整，"
                "在价格恢复顺趋势推进时做多。"
            ),
            "points": [
                ("交易方向", f"只做多，运行在 {BROOKS_COMBO_LABEL} 研究配置。"),
                ("入场条件", "强趋势内的小回调结束后，价格重新顺趋势向上。"),
                ("过滤条件", "关注趋势延续质量，避免在深回调或趋势破坏后追入。"),
                ("出场逻辑", "结构止损放在信号回调低点下方；达到 1R 后用确认回调低点和 EMA20 动态离场。"),
            ],
        },
    }
    summary = summaries.get(strategy_name)
    if summary is None:
        return (
            '<section class="panel strategy-summary">'
            "<h2>策略摘要</h2>"
            f"<p>{escape(strategy_name)} 的策略说明尚未配置。</p>"
            "</section>"
        )

    points_html = "".join(
        (
            '<div class="strategy-point">'
            f"<span>{escape(label)}</span>"
            f"<b>{escape(text)}</b>"
            "</div>"
        )
        for label, text in summary["points"]
    )
    return (
        '<section class="panel strategy-summary">'
        f"<h2>{escape(summary['title'])}</h2>"
        f"<p>{escape(summary['overview'])}</p>"
        f'<div class="strategy-grid">{points_html}</div>'
        "</section>"
    )


def _group_bars_by_day(bars: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for bar in bars:
        grouped.setdefault(session_day(bar["time"]), []).append(bar)
    return grouped


def _group_trades_by_day(trades: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for trade in trades:
        grouped.setdefault(session_day(trade["entry_time"]), []).append(trade)
    return grouped


def _normalize_trade(trade: dict) -> dict:
    normalized = dict(trade)
    normalized["entry_time"] = canonical_timestamp(trade["entry_time"])
    normalized["exit_time"] = canonical_timestamp(trade["exit_time"])
    return normalized


def _time_label_indexes(count: int) -> list[int]:
    if count <= 1:
        return [0]
    indexes = [0, count - 1]
    for ratio in (0.2, 0.4, 0.6, 0.8):
        candidate = min(count - 1, max(0, int(round((count - 1) * ratio))))
        indexes.append(candidate)
    return sorted(set(indexes))


def _build_period(bars: list[dict]) -> str:
    if len(bars) < 2:
        return bars[0]["time"][:10] if bars else ""
    return f'{bars[0]["time"][:10]} ~ {bars[-1]["time"][:10]}'


def _describe_stop_reason(reason: str | None, stop_loss_pct: float) -> str:
    breakout_be = _match_breakout_break_even_reason(reason)
    if breakout_be is not None:
        return f"达到 {breakout_be}R 后止损抬到保本位"
    breakout_target_be = _match_breakout_target_break_even_reason(reason)
    if breakout_target_be is not None:
        _target_r, trigger_r = breakout_target_be
        return f"达到 {trigger_r}R 后止损抬到保本位"
    breakout_pullback_low = _match_breakout_pullback_low_reason(reason)
    if breakout_pullback_low is not None:
        return f"达到 {breakout_pullback_low}R 后止损抬到 pullback low"

    mapping = {
        "fixed_pct_stop_loss": f"固定 {stop_loss_pct:.1f}% 止损",
        "phase1_structural_below_signal_pullback_low": "跌破信号回调低点",
        "phase1_structural_below_breakout_pullback_low": "跌破 breakout / pullback 结构低点",
        "phase1_structural_below_h2_pullback_low": "跌破 H2 回调低点",
        "breakout_break_even_after_1r": "达到 1R 后止损抬到保本位",
        "breakout_target_2_5r_break_even_after_0_75r": "达到 0.75R 后止损抬到保本位",
        "breakout_pullback_low_after_1r": "达到 1R 后止损抬到 pullback low",
        "pullback_count_break_even_after_1r": "达到 1R 后止损抬到保本位",
        "pullback_count_target_2r_break_even_after_0_75r": "达到 0.75R 后止损抬到保本位",
        "pullback_count_pullback_low_after_1r": "达到 1R 后止损抬到 H2 回调低点",
    }
    return mapping.get(reason or "", reason or "未记录止损理由")


def _describe_target_reason(reason: str | None, take_profit_pct: float) -> str:
    if reason is None:
        return f"这个 {BROOKS_COMBO_LABEL}里没有固定止盈"
    breakout_target_be = _match_breakout_target_break_even_reason(reason)
    if breakout_target_be is not None:
        target_r, _trigger_r = breakout_target_be
        return f"固定 {target_r}R 止盈"
    breakout_target = _match_breakout_target_reason(reason)
    if breakout_target is not None:
        return f"固定 {breakout_target}R 止盈"

    mapping = {
        "fixed_pct_take_profit": f"固定 {take_profit_pct:.1f}% 止盈",
        "breakout_target_1r": "固定 1R 止盈",
        "breakout_target_1_5r": "固定 1.5R 止盈",
        "breakout_target_2r": "固定 2R 止盈",
        "breakout_target_2_5r_break_even_after_0_75r": "固定 2.5R 止盈",
        "breakout_measured_move": "breakout bar measured move 止盈",
        "pullback_count_target_1r": "固定 1R 止盈",
        "pullback_count_target_1_5r": "固定 1.5R 止盈",
        "pullback_count_target_2r": "固定 2R 止盈",
        "pullback_count_target_2r_break_even_after_0_75r": "固定 2R 止盈",
    }
    return mapping.get(reason, reason)


def _match_breakout_target_break_even_reason(reason: str | None) -> tuple[str, str] | None:
    if reason is None:
        return None
    match = re.fullmatch(
        r"breakout_target_([0-9_]+)r_break_even_after_([0-9_]+)r",
        reason,
    )
    if not match:
        return None
    return _format_r_label(match.group(1)), _format_r_label(match.group(2))


def _match_breakout_target_reason(reason: str | None) -> str | None:
    if reason is None:
        return None
    match = re.fullmatch(r"breakout_target_([0-9_]+)r", reason)
    if not match:
        return None
    return _format_r_label(match.group(1))


def _match_breakout_break_even_reason(reason: str | None) -> str | None:
    if reason is None:
        return None
    match = re.fullmatch(r"breakout_break_even_after_([0-9_]+)r", reason)
    if not match:
        return None
    return _format_r_label(match.group(1))


def _match_breakout_pullback_low_reason(reason: str | None) -> str | None:
    if reason is None:
        return None
    match = re.fullmatch(r"breakout_pullback_low_after_([0-9_]+)r", reason)
    if not match:
        return None
    return _format_r_label(match.group(1))


def _format_r_label(value: str) -> str:
    return value.replace("_", ".")


def _describe_exit_reason(reason: str) -> str:
    mapping = {
        "session_close": "收盘平仓",
        "stop_loss": "触发止损",
        "take_profit": "触发止盈",
        "end_of_data": "数据结束时平仓",
        "phase1_confirmed_swing_low_break_after_1r": "达到 1R 后跌破确认摆动低点",
        "phase1_breakout_confirmed_swing_low_break_after_1r": "达到 1R 后跌破确认摆动低点并收回 EMA20 下方",
        "phase1_pullback_count_confirmed_swing_low_break_after_1r": "达到 1R 后跌破确认摆动低点并收回 EMA20 下方",
    }
    return mapping.get(reason, reason.replace("_", " "))


def _describe_side(side: str) -> str:
    mapping = {
        "long": "做多",
        "short": "做空",
    }
    return mapping.get(side, side)


def _describe_entry_reason(reason: str) -> str:
    breakout_match = re.match(r"Bull BO pullback: held above ([0-9.]+)", reason)
    if breakout_match:
        return f"多头 BO 回踩成立：守住 {breakout_match.group(1)} 上方"

    small_pb_match = re.match(r"Small PB bull trend: .* above ([0-9.]+)", reason)
    if small_pb_match:
        return f"小回调多头趋势：站稳 {small_pb_match.group(1)} 上方"

    pullback_count_match = re.match(r"H([0-9]+) buy: leg ([0-9]+) pullback reversal in bull trend", reason)
    if pullback_count_match:
        return (
            f"H{pullback_count_match.group(1)} 多头回调计数："
            f"第 {pullback_count_match.group(2)} 段回调后重新向上"
        )

    return reason


def _extract_pullback_count_marker(reason: str) -> dict[str, str] | None:
    buy_match = re.match(
        r"H([0-9]+) buy: leg ([0-9]+) pullback reversal in bull trend",
        reason,
    )
    if buy_match:
        return {
            "direction": "long",
            "label": f"H{buy_match.group(1)} 买点",
            "detail": f"第 {buy_match.group(2)} 段回调反转",
        }

    sell_match = re.match(
        r"L([0-9]+) sell: leg ([0-9]+) rally reversal in bear trend",
        reason,
    )
    if sell_match:
        return {
            "direction": "short",
            "label": f"L{sell_match.group(1)} 卖点",
            "detail": f"第 {sell_match.group(2)} 段反弹反转",
        }

    return None


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."
