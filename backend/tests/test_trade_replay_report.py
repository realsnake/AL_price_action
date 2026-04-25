from pathlib import Path

from services.trade_replay_report import write_trade_replay_report


def _bar(
    ts: str,
    open_: float,
    high: float,
    low: float,
    close: float,
    volume: int = 1000,
) -> dict:
    return {
        "time": ts,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


def test_write_trade_replay_report_creates_svg_html_and_summary(tmp_path: Path):
    bars = [
        _bar("2025-01-03T14:30:00+00:00", 100.0, 100.6, 99.8, 100.4),
        _bar("2025-01-03T14:35:00+00:00", 100.4, 101.4, 100.2, 101.1),
        _bar("2025-01-03T14:40:00+00:00", 101.1, 101.3, 100.9, 101.0),
        _bar("2025-01-03T14:45:00+00:00", 101.0, 101.8, 100.95, 101.7),
        _bar("2025-01-03T14:50:00+00:00", 101.7, 102.3, 101.6, 102.0),
    ]
    trades = [
        {
            "entry_time": "2025-01-03T14:45:00+00:00",
            "exit_time": "2025-01-03T14:50:00+00:00",
            "side": "long",
            "entry_price": 101.7,
            "exit_price": 102.0,
            "stop_loss": 99.67,
            "target_price": 105.77,
            "quantity": 100,
            "pnl": 30.0,
            "pnl_pct": 0.29,
            "reason": "Bull BO pullback: held above 101.10",
            "exit_reason": "session_close",
            "stop_reason": "fixed_pct_stop_loss",
            "target_reason": "fixed_pct_take_profit",
        }
    ]

    result = write_trade_replay_report(
        strategy_name="brooks_small_pb_trend",
        symbol="QQQ",
        timeframe="5m",
        research_profile="qqq_5m_phase1",
        bars=bars,
        trades=trades,
        output_dir=tmp_path,
        stop_loss_pct=2.0,
        take_profit_pct=4.0,
    )

    assert result.report_path.exists()
    assert result.summary_path.exists()
    assert len(result.chart_paths) == 1
    svg_text = result.chart_paths[0].read_text(encoding="utf-8")
    assert "开仓理由" in svg_text
    assert "止损理由" in svg_text
    assert "止盈理由" in svg_text
    assert "实际出场理由" in svg_text
    assert "EMA20 趋势线" in svg_text
    assert 'class="ema20"' in svg_text
    assert "开仓" in svg_text
    assert "出场" in svg_text

    summary_text = result.summary_path.read_text(encoding="utf-8")
    assert "交易日,序号,开仓时间" in summary_text
    assert "2025-01-03.svg" in summary_text

    report_html = result.report_path.read_text(encoding="utf-8")
    assert "交易回放报告" in report_html
    assert "2025-01-03.svg" in report_html


def test_write_trade_replay_report_describes_breakout_2_5r_break_even_policy_in_chinese(tmp_path: Path):
    bars = [
        _bar("2025-03-23T14:30:00+00:00", 100.0, 100.8, 99.7, 100.6),
        _bar("2025-03-23T14:35:00+00:00", 100.6, 101.4, 100.5, 101.2),
        _bar("2025-03-23T14:40:00+00:00", 101.2, 102.1, 101.0, 101.9),
        _bar("2025-03-23T14:45:00+00:00", 101.9, 103.3, 101.8, 103.0),
    ]
    trades = [
        {
            "entry_time": "2025-03-23T14:40:00+00:00",
            "exit_time": "2025-03-23T14:45:00+00:00",
            "side": "long",
            "entry_price": 101.9,
            "exit_price": 103.0,
            "stop_loss": 101.9,
            "target_price": 103.15,
            "quantity": 100,
            "pnl": 110.0,
            "pnl_pct": 1.08,
            "reason": "Bull BO pullback: held above 101.20",
            "exit_reason": "take_profit",
            "stop_reason": "breakout_target_2_5r_break_even_after_0_75r",
            "target_reason": "breakout_target_2_5r_break_even_after_0_75r",
        }
    ]

    result = write_trade_replay_report(
        strategy_name="brooks_breakout_pullback",
        symbol="QQQ",
        timeframe="5m",
        research_profile="qqq_5m_phase1",
        bars=bars,
        trades=trades,
        output_dir=tmp_path,
        stop_loss_pct=2.0,
        take_profit_pct=4.0,
    )

    summary_text = result.summary_path.read_text(encoding="utf-8")
    assert "达到 0.75R 后止损抬到保本位" in summary_text
    assert "固定 2.5R 止盈" in summary_text


def test_write_trade_replay_report_describes_pullback_count_dynamic_exit_in_chinese(tmp_path: Path):
    bars = [
        _bar("2025-03-24T14:30:00+00:00", 100.0, 100.8, 99.7, 100.5),
        _bar("2025-03-24T14:35:00+00:00", 100.5, 100.7, 99.9, 100.1),
        _bar("2025-03-24T14:40:00+00:00", 100.1, 101.2, 100.0, 101.0),
        _bar("2025-03-24T14:45:00+00:00", 101.0, 102.3, 100.9, 102.0),
        _bar("2025-03-24T14:50:00+00:00", 102.0, 102.2, 101.0, 101.1),
    ]
    trades = [
        {
            "entry_time": "2025-03-24T14:40:00+00:00",
            "exit_time": "2025-03-24T14:50:00+00:00",
            "side": "long",
            "entry_price": 101.0,
            "exit_price": 101.1,
            "stop_loss": 99.9,
            "target_price": None,
            "quantity": 100,
            "pnl": 10.0,
            "pnl_pct": 0.1,
            "reason": "H2 buy: leg 2 pullback reversal in bull trend",
            "exit_reason": "phase1_pullback_count_confirmed_swing_low_break_after_1r",
            "stop_reason": "phase1_structural_below_h2_pullback_low",
            "target_reason": None,
        }
    ]

    result = write_trade_replay_report(
        strategy_name="brooks_pullback_count",
        symbol="QQQ",
        timeframe="5m",
        research_profile="qqq_5m_phase1",
        bars=bars,
        trades=trades,
        output_dir=tmp_path,
        stop_loss_pct=2.0,
        take_profit_pct=4.0,
    )

    summary_text = result.summary_path.read_text(encoding="utf-8")
    svg_text = result.chart_paths[0].read_text(encoding="utf-8")
    assert "H2 多头回调计数：第 2 段回调后重新向上" in summary_text
    assert "跌破 H2 回调低点" in summary_text
    assert "这个 QQQ 5m Brooks 组合里没有固定止盈" in summary_text
    assert "达到 1R 后跌破确认摆动低点并收回 EMA20 下方" in summary_text
    assert "H2 多头回调计数" in svg_text
    assert "EMA20 趋势线" in svg_text
    assert "H2 买点" in svg_text
    assert "第 2 段回调反转" in svg_text
