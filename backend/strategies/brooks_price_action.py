from __future__ import annotations

from datetime import datetime
from strategies.base import BaseStrategy, Signal, SignalType
from services.strategy_engine import register_strategy


# ═══════════════════════════════════════════════════════════════════════════════
# Helper functions
# ═══════════════════════════════════════════════════════════════════════════════

def _body(bar: dict) -> float:
    return abs(bar["close"] - bar["open"])


def _range(bar: dict) -> float:
    return bar["high"] - bar["low"]


def _is_bull(bar: dict) -> bool:
    return bar["close"] > bar["open"]


def _is_bear(bar: dict) -> bool:
    return bar["close"] < bar["open"]


def _is_doji(bar: dict, threshold: float = 0.3) -> bool:
    r = _range(bar)
    if r == 0:
        return True
    return _body(bar) / r < threshold


def _body_ratio(bar: dict) -> float:
    r = _range(bar)
    if r == 0:
        return 0
    return _body(bar) / r


def _is_strong(bar: dict, threshold: float = 0.6) -> bool:
    return _body_ratio(bar) > threshold


def _is_inside(curr: dict, prev: dict) -> bool:
    return curr["high"] <= prev["high"] and curr["low"] >= prev["low"]


def _is_outside(curr: dict, prev: dict) -> bool:
    return curr["high"] > prev["high"] and curr["low"] < prev["low"]


def _upper_tail(bar: dict) -> float:
    return bar["high"] - max(bar["open"], bar["close"])


def _lower_tail(bar: dict) -> float:
    return min(bar["open"], bar["close"]) - bar["low"]


def _mid(bar: dict) -> float:
    return (bar["high"] + bar["low"]) / 2


def _ema(closes: list[float], period: int) -> list[float]:
    result = [0.0] * len(closes)
    if len(closes) < period:
        return result
    mult = 2.0 / (period + 1)
    result[period - 1] = sum(closes[:period]) / period
    for i in range(period, len(closes)):
        result[i] = (closes[i] - result[i - 1]) * mult + result[i - 1]
    return result


def _atr(bars: list[dict], period: int = 14) -> list[float]:
    """Average True Range."""
    result = [0.0] * len(bars)
    if len(bars) < period + 1:
        return result
    trs = []
    for i in range(1, len(bars)):
        tr = max(
            bars[i]["high"] - bars[i]["low"],
            abs(bars[i]["high"] - bars[i - 1]["close"]),
            abs(bars[i]["low"] - bars[i - 1]["close"]),
        )
        trs.append(tr)
    # Simple moving average for first ATR
    if len(trs) >= period:
        result[period] = sum(trs[:period]) / period
        for i in range(period + 1, len(bars)):
            result[i] = (result[i - 1] * (period - 1) + trs[i - 1]) / period
    return result


def _swing_highs(bars: list[dict], lb: int = 3) -> list[tuple[int, float]]:
    result = []
    for i in range(lb, len(bars) - lb):
        if all(bars[i]["high"] >= bars[i + d]["high"] for d in range(-lb, lb + 1) if d != 0):
            result.append((i, bars[i]["high"]))
    return result


def _swing_lows(bars: list[dict], lb: int = 3) -> list[tuple[int, float]]:
    result = []
    for i in range(lb, len(bars) - lb):
        if all(bars[i]["low"] <= bars[i + d]["low"] for d in range(-lb, lb + 1) if d != 0):
            result.append((i, bars[i]["low"]))
    return result


def _make_signal(symbol: str, stype: SignalType, bar: dict, qty: int, reason: str) -> Signal:
    return Signal(
        symbol=symbol, signal_type=stype,
        price=bar["close"], quantity=qty,
        reason=reason,
        timestamp=datetime.fromisoformat(bar["time"]),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# TREND STRATEGIES
# ═══════════════════════════════════════════════════════════════════════════════

# ─── 1. H1/H2/H3/H4 & L1/L2/L3/L4 Pullback Count ─────────────────────────

@register_strategy
class PullbackCountStrategy(BaseStrategy):
    name = "brooks_pullback_count"
    description = (
        "H1-H4 / L1-L4: Count pullback legs in a trend. "
        "H2/L2 is highest probability. H1 in strong trends, H3/H4 = weakening trend."
    )

    def default_params(self) -> dict:
        return {"ema_period": 20, "quantity": 1}

    def generate_signals(self, symbol: str, bars: list[dict]) -> list[Signal]:
        ema_p = self.params.get("ema_period", 20)
        qty = self.params.get("quantity", 1)
        if len(bars) < ema_p + 5:
            return []

        closes = [b["close"] for b in bars]
        ema = _ema(closes, ema_p)
        signals = []

        # Track pullback legs
        bull_legs = 0  # count of pullback legs in bull trend
        bear_legs = 0
        prev_was_pullback_bull = False
        prev_was_pullback_bear = False

        for i in range(ema_p + 1, len(bars)):
            if ema[i] == 0:
                continue

            curr = bars[i]
            prev = bars[i - 1]
            in_bull = closes[i] > ema[i] and ema[i] > ema[max(0, i - 5)]
            in_bear = closes[i] < ema[i] and ema[i] < ema[max(0, i - 5)]

            # Bull trend: count pullback legs
            if in_bull:
                bear_legs = 0
                is_pullback = _is_bear(curr) or curr["low"] < prev["low"]
                if is_pullback and not prev_was_pullback_bull:
                    bull_legs += 1
                prev_was_pullback_bull = is_pullback

                # Signal on reversal back up after pullback
                if bull_legs >= 1 and not is_pullback and prev_was_pullback_bull is False and _is_bull(curr) and _is_strong(curr, 0.4):
                    if curr["close"] > prev["high"]:
                        label = f"H{min(bull_legs, 4)}"
                        signals.append(_make_signal(
                            symbol, SignalType.BUY, curr, qty,
                            f"{label} buy: leg {bull_legs} pullback reversal in bull trend"
                        ))
                        bull_legs = 0
            elif in_bear:
                bull_legs = 0
                is_rally = _is_bull(curr) or curr["high"] > prev["high"]
                if is_rally and not prev_was_pullback_bear:
                    bear_legs += 1
                prev_was_pullback_bear = is_rally

                if bear_legs >= 1 and not is_rally and prev_was_pullback_bear is False and _is_bear(curr) and _is_strong(curr, 0.4):
                    if curr["close"] < prev["low"]:
                        label = f"L{min(bear_legs, 4)}"
                        signals.append(_make_signal(
                            symbol, SignalType.SELL, curr, qty,
                            f"{label} sell: leg {bear_legs} rally reversal in bear trend"
                        ))
                        bear_legs = 0
            else:
                bull_legs = 0
                bear_legs = 0

        return signals


# ─── 2. Spike and Channel ──────────────────────────────────────────────────

@register_strategy
class SpikeAndChannelStrategy(BaseStrategy):
    name = "brooks_spike_channel"
    description = (
        "Spike and Channel: Strong spike (2-5 consecutive trend bars) followed by "
        "a channel. Trade pullbacks within the channel. Fade channel line overshoot."
    )

    def default_params(self) -> dict:
        return {"spike_bars": 3, "ema_period": 20, "quantity": 1}

    def generate_signals(self, symbol: str, bars: list[dict]) -> list[Signal]:
        spike_n = self.params.get("spike_bars", 3)
        ema_p = self.params.get("ema_period", 20)
        qty = self.params.get("quantity", 1)
        if len(bars) < ema_p + spike_n + 10:
            return []

        closes = [b["close"] for b in bars]
        ema = _ema(closes, ema_p)
        signals = []

        for i in range(ema_p + spike_n + 5, len(bars)):
            if ema[i] == 0:
                continue

            # Detect bull spike: spike_n consecutive strong bull bars
            spike_start = i - spike_n - 5
            spike_end = spike_start + spike_n
            if spike_end >= i:
                continue

            bull_spike = all(
                _is_bull(bars[j]) and _is_strong(bars[j], 0.5)
                for j in range(spike_start, spike_end)
            )

            if bull_spike:
                # After spike, look for channel (higher highs and higher lows)
                channel_bars = bars[spike_end:i]
                if len(channel_bars) < 3:
                    continue
                in_channel = all(
                    channel_bars[k]["low"] >= channel_bars[max(0, k - 2)]["low"] * 0.998
                    for k in range(1, len(channel_bars))
                )
                # Current bar is pullback in channel
                if in_channel and _is_bear(bars[i - 1]) and _is_bull(bars[i]):
                    if bars[i]["close"] > bars[i - 1]["high"]:
                        signals.append(_make_signal(
                            symbol, SignalType.BUY, bars[i], qty,
                            f"Spike & Channel: bull pullback buy in channel after spike"
                        ))

            # Detect bear spike
            bear_spike = all(
                _is_bear(bars[j]) and _is_strong(bars[j], 0.5)
                for j in range(spike_start, spike_end)
            )

            if bear_spike:
                channel_bars = bars[spike_end:i]
                if len(channel_bars) < 3:
                    continue
                in_channel = all(
                    channel_bars[k]["high"] <= channel_bars[max(0, k - 2)]["high"] * 1.002
                    for k in range(1, len(channel_bars))
                )
                if in_channel and _is_bull(bars[i - 1]) and _is_bear(bars[i]):
                    if bars[i]["close"] < bars[i - 1]["low"]:
                        signals.append(_make_signal(
                            symbol, SignalType.SELL, bars[i], qty,
                            f"Spike & Channel: bear rally sell in channel after spike"
                        ))

        return signals


# ─── 3. Small Pullback Trend ───────────────────────────────────────────────

@register_strategy
class SmallPullbackTrendStrategy(BaseStrategy):
    name = "brooks_small_pb_trend"
    description = (
        "Small Pullback Trend: Very strong trend where pullbacks are shallow "
        "(1-3 bars, never touching EMA). Buy any small dip in bull SPT. "
        "These are the strongest trends - don't fade them."
    )

    def default_params(self) -> dict:
        return {"ema_period": 20, "min_trend_bars": 8, "quantity": 1}

    def generate_signals(self, symbol: str, bars: list[dict]) -> list[Signal]:
        ema_p = self.params.get("ema_period", 20)
        min_tb = self.params.get("min_trend_bars", 8)
        qty = self.params.get("quantity", 1)
        if len(bars) < ema_p + min_tb + 3:
            return []

        closes = [b["close"] for b in bars]
        ema = _ema(closes, ema_p)
        signals = []

        for i in range(ema_p + min_tb, len(bars)):
            if ema[i] == 0:
                continue

            window = bars[i - min_tb:i]

            # Bull SPT: most bars close above EMA, never touch or cross below significantly
            bull_above = sum(1 for b in window if b["close"] > ema[i - min_tb + window.index(b)] if ema[i - min_tb + window.index(b)] > 0)
            all_above_ema = all(
                b["low"] >= ema[i - min_tb + j] * 0.995
                for j, b in enumerate(window) if ema[i - min_tb + j] > 0
            )

            if bull_above >= min_tb - 1 and all_above_ema:
                # Small pullback: 1-2 bear bars then bull bar
                if _is_bear(bars[i - 1]) and _is_bull(bars[i]) and bars[i]["close"] > bars[i - 1]["high"]:
                    signals.append(_make_signal(
                        symbol, SignalType.BUY, bars[i], qty,
                        f"Small PB Trend: buy dip in strong bull trend (never touched EMA)"
                    ))

            # Bear SPT
            bear_below = sum(1 for j, b in enumerate(window) if b["close"] < ema[i - min_tb + j] and ema[i - min_tb + j] > 0)
            all_below_ema = all(
                b["high"] <= ema[i - min_tb + j] * 1.005
                for j, b in enumerate(window) if ema[i - min_tb + j] > 0
            )

            if bear_below >= min_tb - 1 and all_below_ema:
                if _is_bull(bars[i - 1]) and _is_bear(bars[i]) and bars[i]["close"] < bars[i - 1]["low"]:
                    signals.append(_make_signal(
                        symbol, SignalType.SELL, bars[i], qty,
                        f"Small PB Trend: sell rally in strong bear trend (never touched EMA)"
                    ))

        return signals


# ─── 4. Broad Channel / Staircase ──────────────────────────────────────────

@register_strategy
class BroadChannelStrategy(BaseStrategy):
    name = "brooks_broad_channel"
    description = (
        "Broad Channel (Staircase): Trend moves in a wide channel with deep pullbacks "
        "to EMA. Buy at EMA support in bull channel, sell at EMA resistance in bear."
    )

    def default_params(self) -> dict:
        return {"ema_period": 20, "quantity": 1}

    def generate_signals(self, symbol: str, bars: list[dict]) -> list[Signal]:
        ema_p = self.params.get("ema_period", 20)
        qty = self.params.get("quantity", 1)
        if len(bars) < ema_p + 10:
            return []

        closes = [b["close"] for b in bars]
        ema = _ema(closes, ema_p)
        signals = []

        for i in range(ema_p + 5, len(bars)):
            if ema[i] == 0:
                continue

            curr = bars[i]
            prev = bars[i - 1]
            # Bull broad channel: making HH and HL, EMA rising
            ema_rising = ema[i] > ema[i - 5]
            ema_falling = ema[i] < ema[i - 5]

            # Touch EMA from above and bounce
            if ema_rising:
                touched_ema = prev["low"] <= ema[i - 1] * 1.003 and prev["low"] >= ema[i - 1] * 0.990
                bounce = _is_bull(curr) and curr["close"] > prev["high"]
                if touched_ema and bounce and _is_strong(curr, 0.4):
                    signals.append(_make_signal(
                        symbol, SignalType.BUY, curr, qty,
                        f"Broad Channel: bounce off EMA support at {ema[i]:.2f}"
                    ))

            # Touch EMA from below and reject
            if ema_falling:
                touched_ema = prev["high"] >= ema[i - 1] * 0.997 and prev["high"] <= ema[i - 1] * 1.010
                reject = _is_bear(curr) and curr["close"] < prev["low"]
                if touched_ema and reject and _is_strong(curr, 0.4):
                    signals.append(_make_signal(
                        symbol, SignalType.SELL, curr, qty,
                        f"Broad Channel: reject off EMA resistance at {ema[i]:.2f}"
                    ))

        return signals


# ─── 5. Trend from the Open ────────────────────────────────────────────────

@register_strategy
class TrendFromOpenStrategy(BaseStrategy):
    name = "brooks_trend_from_open"
    description = (
        "Trend from the Open: First bar is a strong trend bar that sets direction. "
        "For daily charts: strong gap + follow-through. Enter on first pullback."
    )

    def default_params(self) -> dict:
        return {"ema_period": 20, "quantity": 1}

    def generate_signals(self, symbol: str, bars: list[dict]) -> list[Signal]:
        ema_p = self.params.get("ema_period", 20)
        qty = self.params.get("quantity", 1)
        if len(bars) < ema_p + 5:
            return []

        closes = [b["close"] for b in bars]
        ema = _ema(closes, ema_p)
        signals = []

        for i in range(ema_p + 3, len(bars)):
            if ema[i] == 0 or i < 2:
                continue

            # Gap up + strong first bar + continuation
            prev_close = bars[i - 3]["close"]
            first = bars[i - 2]
            second = bars[i - 1]
            entry = bars[i]

            # Bull gap open trend
            gap_up = first["open"] > prev_close * 1.003
            if (gap_up and _is_bull(first) and _is_strong(first, 0.5) and
                _is_bull(second)):
                # First pullback entry
                if _is_bear(second) or second["low"] < first["low"]:
                    if _is_bull(entry) and entry["close"] > second["high"]:
                        signals.append(_make_signal(
                            symbol, SignalType.BUY, entry, qty,
                            f"Trend from Open: gap up + strong bar, buy first pullback"
                        ))

            # Bear gap open trend
            gap_down = first["open"] < prev_close * 0.997
            if (gap_down and _is_bear(first) and _is_strong(first, 0.5) and
                _is_bear(second)):
                if _is_bull(second) or second["high"] > first["high"]:
                    if _is_bear(entry) and entry["close"] < second["low"]:
                        signals.append(_make_signal(
                            symbol, SignalType.SELL, entry, qty,
                            f"Trend from Open: gap down + strong bar, sell first rally"
                        ))

        return signals


# ─── 6. Trend Channel Line Overshoot ───────────────────────────────────────

@register_strategy
class ChannelOvershootStrategy(BaseStrategy):
    name = "brooks_channel_overshoot"
    description = (
        "Channel Line Overshoot: When price overshoots the trend channel line "
        "(climactic move beyond the channel), it typically reverses back. "
        "Fade the overshoot with a reversal bar confirmation."
    )

    def default_params(self) -> dict:
        return {"channel_period": 15, "quantity": 1}

    def generate_signals(self, symbol: str, bars: list[dict]) -> list[Signal]:
        ch_p = self.params.get("channel_period", 15)
        qty = self.params.get("quantity", 1)
        if len(bars) < ch_p + 5:
            return []

        signals = []

        for i in range(ch_p + 1, len(bars)):
            window = bars[i - ch_p:i]
            highs = [b["high"] for b in window]
            lows = [b["low"] for b in window]
            ch_high = max(highs)
            ch_low = min(lows)
            ch_range = ch_high - ch_low
            if ch_range == 0:
                continue

            curr = bars[i]
            prev = bars[i - 1]

            # Overshoot above channel
            if prev["high"] > ch_high and prev["close"] > ch_high:
                overshoot = (prev["high"] - ch_high) / ch_range
                if overshoot > 0.1 and _is_bear(curr) and _is_strong(curr, 0.4):
                    if curr["close"] < ch_high:
                        signals.append(_make_signal(
                            symbol, SignalType.SELL, curr, qty,
                            f"Channel overshoot: climax above {ch_high:.2f}, reversing"
                        ))

            # Overshoot below channel
            if prev["low"] < ch_low and prev["close"] < ch_low:
                overshoot = (ch_low - prev["low"]) / ch_range
                if overshoot > 0.1 and _is_bull(curr) and _is_strong(curr, 0.4):
                    if curr["close"] > ch_low:
                        signals.append(_make_signal(
                            symbol, SignalType.BUY, curr, qty,
                            f"Channel overshoot: climax below {ch_low:.2f}, reversing"
                        ))

        return signals


# ─── 7. Always In ──────────────────────────────────────────────────────────

@register_strategy
class AlwaysInStrategy(BaseStrategy):
    name = "brooks_always_in"
    description = (
        "Always In: Determine if market is Always-In-Long or Always-In-Short "
        "based on EMA direction + last strong signal bar. Trade with the AI direction. "
        "Flip only on strong reversal signal."
    )

    def default_params(self) -> dict:
        return {"ema_period": 20, "quantity": 1}

    def generate_signals(self, symbol: str, bars: list[dict]) -> list[Signal]:
        ema_p = self.params.get("ema_period", 20)
        qty = self.params.get("quantity", 1)
        if len(bars) < ema_p + 5:
            return []

        closes = [b["close"] for b in bars]
        ema = _ema(closes, ema_p)
        signals = []
        ai_direction = None  # "long" or "short"

        for i in range(ema_p + 1, len(bars)):
            if ema[i] == 0:
                continue

            curr = bars[i]

            # Determine AI direction
            new_dir = None
            if closes[i] > ema[i] and ema[i] > ema[i - 1] and _is_bull(curr) and _is_strong(curr, 0.5):
                new_dir = "long"
            elif closes[i] < ema[i] and ema[i] < ema[i - 1] and _is_bear(curr) and _is_strong(curr, 0.5):
                new_dir = "short"

            if new_dir and new_dir != ai_direction:
                ai_direction = new_dir
                if ai_direction == "long":
                    signals.append(_make_signal(
                        symbol, SignalType.BUY, curr, qty,
                        f"Always-In-Long: strong bull bar above rising EMA"
                    ))
                else:
                    signals.append(_make_signal(
                        symbol, SignalType.SELL, curr, qty,
                        f"Always-In-Short: strong bear bar below falling EMA"
                    ))

        return signals


# ═══════════════════════════════════════════════════════════════════════════════
# REVERSAL STRATEGIES
# ═══════════════════════════════════════════════════════════════════════════════

# ─── 8. Inside Bar Breakout ─────────────────────────────────────────────────

@register_strategy
class InsideBarBreakoutStrategy(BaseStrategy):
    name = "brooks_inside_bar"
    description = (
        "Inside Bar / ii / iii Breakout: Trade breakout of inside bar patterns. "
        "ii (double inside) and iii (triple inside) are stronger signals."
    )

    def default_params(self) -> dict:
        return {"ema_period": 20, "quantity": 1}

    def generate_signals(self, symbol: str, bars: list[dict]) -> list[Signal]:
        ema_p = self.params.get("ema_period", 20)
        qty = self.params.get("quantity", 1)
        if len(bars) < ema_p + 4:
            return []

        closes = [b["close"] for b in bars]
        ema = _ema(closes, ema_p)
        signals = []

        for i in range(ema_p + 3, len(bars)):
            if ema[i] == 0:
                continue

            # Check for iii, ii, or single inside bar
            pattern = ""
            mother_idx = i - 2
            if (i >= 4 and _is_inside(bars[i - 2], bars[i - 3]) and
                _is_inside(bars[i - 3], bars[i - 4])):
                pattern = "iii"
                mother_idx = i - 4
            elif _is_inside(bars[i - 1], bars[i - 2]) and _is_inside(bars[i - 2], bars[i - 3]):
                pattern = "ii"
                mother_idx = i - 3
            elif _is_inside(bars[i - 1], bars[i - 2]):
                pattern = "iB"
                mother_idx = i - 2
            else:
                continue

            mother = bars[mother_idx]
            curr = bars[i]
            trend_bull = closes[i] > ema[i]

            if curr["close"] > mother["high"] and _is_bull(curr):
                if trend_bull or pattern in ("ii", "iii"):
                    signals.append(_make_signal(
                        symbol, SignalType.BUY, curr, qty,
                        f"{pattern} bull breakout above {mother['high']:.2f}"
                    ))

            elif curr["close"] < mother["low"] and _is_bear(curr):
                if not trend_bull or pattern in ("ii", "iii"):
                    signals.append(_make_signal(
                        symbol, SignalType.SELL, curr, qty,
                        f"{pattern} bear breakout below {mother['low']:.2f}"
                    ))

        return signals


# ─── 9. Two-Bar Reversal ───────────────────────────────────────────────────

@register_strategy
class TwoBarReversalStrategy(BaseStrategy):
    name = "brooks_two_bar_reversal"
    description = (
        "Two-Bar Reversal: Strong bear bar + strong bull bar (or vice versa) "
        "at swing point. Second bar closes beyond first bar's open."
    )

    def default_params(self) -> dict:
        return {"ema_period": 20, "min_body_ratio": 0.5, "quantity": 1}

    def generate_signals(self, symbol: str, bars: list[dict]) -> list[Signal]:
        ema_p = self.params.get("ema_period", 20)
        min_ratio = self.params.get("min_body_ratio", 0.5)
        qty = self.params.get("quantity", 1)
        if len(bars) < ema_p + 5:
            return []

        closes = [b["close"] for b in bars]
        ema = _ema(closes, ema_p)
        signals = []

        for i in range(ema_p + 1, len(bars)):
            if ema[i] == 0:
                continue
            prev, curr = bars[i - 1], bars[i]
            if _range(prev) == 0 or _range(curr) == 0:
                continue

            if (_is_bear(prev) and _is_bull(curr) and
                _body_ratio(prev) > min_ratio and _body_ratio(curr) > min_ratio and
                curr["close"] > prev["open"]):
                recent_low = min(b["low"] for b in bars[max(0, i - 10):i])
                if prev["low"] <= recent_low * 1.005:
                    signals.append(_make_signal(
                        symbol, SignalType.BUY, curr, qty,
                        f"Bullish 2-bar reversal at swing low {prev['low']:.2f}"
                    ))

            if (_is_bull(prev) and _is_bear(curr) and
                _body_ratio(prev) > min_ratio and _body_ratio(curr) > min_ratio and
                curr["close"] < prev["open"]):
                recent_high = max(b["high"] for b in bars[max(0, i - 10):i])
                if prev["high"] >= recent_high * 0.995:
                    signals.append(_make_signal(
                        symbol, SignalType.SELL, curr, qty,
                        f"Bearish 2-bar reversal at swing high {prev['high']:.2f}"
                    ))

        return signals


# ─── 10. Wedge / Three-Push Reversal ───────────────────────────────────────

@register_strategy
class WedgeReversalStrategy(BaseStrategy):
    name = "brooks_wedge"
    description = (
        "Wedge (3-Push) Reversal: Three consecutive pushes with diminishing momentum. "
        "Classic exhaustion pattern."
    )

    def default_params(self) -> dict:
        return {"lookback": 20, "quantity": 1}

    def generate_signals(self, symbol: str, bars: list[dict]) -> list[Signal]:
        qty = self.params.get("quantity", 1)
        if len(bars) < 15:
            return []

        signals = []
        sh = _swing_highs(bars, 2)
        sl = _swing_lows(bars, 2)

        for k in range(2, len(sh)):
            _, h1 = sh[k - 2]
            _, h2 = sh[k - 1]
            i3, h3 = sh[k]
            if not (h3 > h2 > h1):
                continue
            if h2 - h1 <= h3 - h2:
                continue  # not diminishing
            rev_idx = i3 + 1
            if rev_idx >= len(bars):
                continue
            rev = bars[rev_idx]
            if _is_bear(rev) and _is_strong(rev, 0.4):
                signals.append(_make_signal(
                    symbol, SignalType.SELL, rev, qty,
                    f"Bearish wedge: 3 pushes to {h3:.2f}, momentum fading"
                ))

        for k in range(2, len(sl)):
            _, l1 = sl[k - 2]
            _, l2 = sl[k - 1]
            i3, l3 = sl[k]
            if not (l3 < l2 < l1):
                continue
            if l1 - l2 <= l2 - l3:
                continue
            rev_idx = i3 + 1
            if rev_idx >= len(bars):
                continue
            rev = bars[rev_idx]
            if _is_bull(rev) and _is_strong(rev, 0.4):
                signals.append(_make_signal(
                    symbol, SignalType.BUY, rev, qty,
                    f"Bullish wedge: 3 pushes to {l3:.2f}, momentum fading"
                ))

        signals.sort(key=lambda s: s.timestamp)
        return signals


# ─── 11. Double Top / Double Bottom ────────────────────────────────────────

@register_strategy
class DoubleTopBottomStrategy(BaseStrategy):
    name = "brooks_double_top_bottom"
    description = (
        "Double Top / Double Bottom: Two tests of the same price level that fail. "
        "The second test creates a lower high (DT) or higher low (DB). "
        "Requires strong reversal bar on second test."
    )

    def default_params(self) -> dict:
        return {"tolerance_pct": 0.5, "lookback": 20, "quantity": 1}

    def generate_signals(self, symbol: str, bars: list[dict]) -> list[Signal]:
        tol = self.params.get("tolerance_pct", 0.5) / 100
        lb = self.params.get("lookback", 20)
        qty = self.params.get("quantity", 1)
        if len(bars) < lb + 5:
            return []

        signals = []
        sh = _swing_highs(bars, 2)
        sl = _swing_lows(bars, 2)

        # Double Top
        for k in range(1, len(sh)):
            i1, h1 = sh[k - 1]
            i2, h2 = sh[k]
            if abs(i2 - i1) < 5 or abs(i2 - i1) > lb:
                continue
            if abs(h2 - h1) / h1 > tol:
                continue  # not at same level
            # Second high should be equal or slightly lower
            rev_idx = i2 + 1
            if rev_idx >= len(bars):
                continue
            rev = bars[rev_idx]
            if _is_bear(rev) and _is_strong(rev, 0.4):
                signals.append(_make_signal(
                    symbol, SignalType.SELL, rev, qty,
                    f"Double Top at {h1:.2f}/{h2:.2f}, reversal confirmed"
                ))

        # Double Bottom
        for k in range(1, len(sl)):
            i1, l1 = sl[k - 1]
            i2, l2 = sl[k]
            if abs(i2 - i1) < 5 or abs(i2 - i1) > lb:
                continue
            if abs(l2 - l1) / l1 > tol:
                continue
            rev_idx = i2 + 1
            if rev_idx >= len(bars):
                continue
            rev = bars[rev_idx]
            if _is_bull(rev) and _is_strong(rev, 0.4):
                signals.append(_make_signal(
                    symbol, SignalType.BUY, rev, qty,
                    f"Double Bottom at {l1:.2f}/{l2:.2f}, reversal confirmed"
                ))

        signals.sort(key=lambda s: s.timestamp)
        return signals


# ─── 12. Climactic Reversal ────────────────────────────────────────────────

@register_strategy
class ClimacticReversalStrategy(BaseStrategy):
    name = "brooks_climactic_reversal"
    description = (
        "Climactic Reversal: Consecutive large trend bars (buying/selling climax) "
        "followed by exhaustion. Bars get increasingly large then suddenly reverse. "
        "Often at end of trends with extreme volume."
    )

    def default_params(self) -> dict:
        return {"climax_bars": 3, "quantity": 1}

    def generate_signals(self, symbol: str, bars: list[dict]) -> list[Signal]:
        climax_n = self.params.get("climax_bars", 3)
        qty = self.params.get("quantity", 1)
        if len(bars) < climax_n + 5:
            return []

        atr = _atr(bars)
        signals = []

        for i in range(climax_n + 1, len(bars)):
            if atr[i] == 0:
                continue

            # Buying climax: consecutive large bull bars then bear reversal
            climax_window = bars[i - climax_n:i]
            all_bull = all(_is_bull(b) for b in climax_window)
            all_large = all(_range(b) > atr[i] * 1.2 for b in climax_window)

            if all_bull and all_large:
                curr = bars[i]
                if _is_bear(curr) and _is_strong(curr, 0.4):
                    signals.append(_make_signal(
                        symbol, SignalType.SELL, curr, qty,
                        f"Buying climax exhaustion: {climax_n} large bull bars then reversal"
                    ))

            # Selling climax
            all_bear = all(_is_bear(b) for b in climax_window)
            if all_bear and all_large:
                curr = bars[i]
                if _is_bull(curr) and _is_strong(curr, 0.4):
                    signals.append(_make_signal(
                        symbol, SignalType.BUY, curr, qty,
                        f"Selling climax exhaustion: {climax_n} large bear bars then reversal"
                    ))

        return signals


# ─── 13. Final Flag ────────────────────────────────────────────────────────

@register_strategy
class FinalFlagStrategy(BaseStrategy):
    name = "brooks_final_flag"
    description = (
        "Final Flag: Late-trend pullback that looks like a continuation but fails. "
        "A flag (small trading range) forms after extended trend, breakout of flag "
        "in trend direction fails and reverses."
    )

    def default_params(self) -> dict:
        return {"ema_period": 20, "flag_bars": 5, "quantity": 1}

    def generate_signals(self, symbol: str, bars: list[dict]) -> list[Signal]:
        ema_p = self.params.get("ema_period", 20)
        flag_n = self.params.get("flag_bars", 5)
        qty = self.params.get("quantity", 1)
        if len(bars) < ema_p + flag_n + 10:
            return []

        closes = [b["close"] for b in bars]
        ema = _ema(closes, ema_p)
        signals = []

        for i in range(ema_p + flag_n + 5, len(bars)):
            if ema[i] == 0:
                continue

            # Check for extended bull trend before flag
            trend_window = bars[i - flag_n - 10:i - flag_n]
            if len(trend_window) < 8:
                continue
            bull_trend = sum(1 for b in trend_window if _is_bull(b)) >= 6

            if bull_trend:
                # Flag: tight range (small bars, overlapping)
                flag = bars[i - flag_n:i - 1]
                flag_range = max(b["high"] for b in flag) - min(b["low"] for b in flag)
                avg_bar_range = sum(_range(b) for b in flag) / len(flag)
                is_tight = flag_range < avg_bar_range * 3 if avg_bar_range > 0 else False

                if is_tight:
                    # Breakout attempt then failure
                    prev = bars[i - 1]
                    curr = bars[i]
                    flag_high = max(b["high"] for b in flag)
                    if prev["high"] > flag_high and _is_bear(curr) and curr["close"] < flag_high:
                        signals.append(_make_signal(
                            symbol, SignalType.SELL, curr, qty,
                            f"Final Flag: bull flag BO failed at {flag_high:.2f}, trend exhaustion"
                        ))

            # Bear version
            bear_trend = sum(1 for b in trend_window if _is_bear(b)) >= 6
            if bear_trend:
                flag = bars[i - flag_n:i - 1]
                flag_range = max(b["high"] for b in flag) - min(b["low"] for b in flag)
                avg_bar_range = sum(_range(b) for b in flag) / len(flag)
                is_tight = flag_range < avg_bar_range * 3 if avg_bar_range > 0 else False

                if is_tight:
                    prev = bars[i - 1]
                    curr = bars[i]
                    flag_low = min(b["low"] for b in flag)
                    if prev["low"] < flag_low and _is_bull(curr) and curr["close"] > flag_low:
                        signals.append(_make_signal(
                            symbol, SignalType.BUY, curr, qty,
                            f"Final Flag: bear flag BO failed at {flag_low:.2f}, trend exhaustion"
                        ))

        return signals


# ─── 14. Expanding Triangle ────────────────────────────────────────────────

@register_strategy
class ExpandingTriangleStrategy(BaseStrategy):
    name = "brooks_expanding_triangle"
    description = (
        "Expanding Triangle: Higher highs AND lower lows - volatility expanding. "
        "Third or fourth reversal from the widening range boundary is tradeable. "
        "Fade the latest extreme."
    )

    def default_params(self) -> dict:
        return {"lookback": 15, "quantity": 1}

    def generate_signals(self, symbol: str, bars: list[dict]) -> list[Signal]:
        lb = self.params.get("lookback", 15)
        qty = self.params.get("quantity", 1)
        if len(bars) < lb + 5:
            return []

        signals = []
        sh = _swing_highs(bars, 2)
        sl = _swing_lows(bars, 2)

        # Need at least 2 swing highs and 2 swing lows
        for hi in range(1, len(sh)):
            for li in range(1, len(sl)):
                i_h1, h1 = sh[hi - 1]
                i_h2, h2 = sh[hi]
                i_l1, l1 = sl[li - 1]
                i_l2, l2 = sl[li]

                # Expanding: higher high AND lower low
                if not (h2 > h1 and l2 < l1):
                    continue
                # All within reasonable distance
                indices = sorted([i_h1, i_h2, i_l1, i_l2])
                if indices[-1] - indices[0] > lb * 2:
                    continue

                # Most recent swing determines trade direction
                latest_idx = max(i_h2, i_l2)
                if latest_idx >= len(bars) - 1:
                    continue
                rev = bars[latest_idx + 1]

                if i_l2 > i_h2:
                    # Latest was a swing low - buy
                    if _is_bull(rev) and _is_strong(rev, 0.4):
                        signals.append(_make_signal(
                            symbol, SignalType.BUY, rev, qty,
                            f"Expanding Triangle: buy reversal from lower low {l2:.2f}"
                        ))
                elif i_h2 > i_l2:
                    if _is_bear(rev) and _is_strong(rev, 0.4):
                        signals.append(_make_signal(
                            symbol, SignalType.SELL, rev, qty,
                            f"Expanding Triangle: sell reversal from higher high {h2:.2f}"
                        ))

        # Deduplicate by timestamp
        seen = set()
        unique = []
        for s in signals:
            key = (s.timestamp, s.signal_type)
            if key not in seen:
                seen.add(key)
                unique.append(s)
        unique.sort(key=lambda s: s.timestamp)
        return unique


# ─── 15. Parabolic Wedge ──────────────────────────────────────────────────

@register_strategy
class ParabolicWedgeStrategy(BaseStrategy):
    name = "brooks_parabolic_wedge"
    description = (
        "Parabolic Wedge: Accelerating trend where each leg is steeper than the last. "
        "Bars get bigger and trend accelerates parabolically. "
        "Unsustainable - reversal is violent when it comes."
    )

    def default_params(self) -> dict:
        return {"lookback": 10, "quantity": 1}

    def generate_signals(self, symbol: str, bars: list[dict]) -> list[Signal]:
        lb = self.params.get("lookback", 10)
        qty = self.params.get("quantity", 1)
        if len(bars) < lb + 5:
            return []

        atr = _atr(bars)
        signals = []

        for i in range(lb + 1, len(bars)):
            if atr[i] == 0:
                continue

            window = bars[i - lb:i]

            # Parabolic bull: each bar's range is larger than previous, all bull
            ranges = [_range(b) for b in window]
            bull_count = sum(1 for b in window if _is_bull(b))

            if bull_count >= lb - 1:  # almost all bull
                # Check acceleration: ranges increasing
                increasing = sum(1 for j in range(1, len(ranges)) if ranges[j] > ranges[j - 1])
                if increasing >= lb * 0.6:
                    # Last bar is climactic (very large)
                    if ranges[-1] > atr[i] * 1.5:
                        curr = bars[i]
                        if _is_bear(curr) and _is_strong(curr, 0.4):
                            signals.append(_make_signal(
                                symbol, SignalType.SELL, curr, qty,
                                f"Parabolic wedge top: accelerating bull trend exhausted"
                            ))

            bear_count = sum(1 for b in window if _is_bear(b))
            if bear_count >= lb - 1:
                increasing = sum(1 for j in range(1, len(ranges)) if ranges[j] > ranges[j - 1])
                if increasing >= lb * 0.6:
                    if ranges[-1] > atr[i] * 1.5:
                        curr = bars[i]
                        if _is_bull(curr) and _is_strong(curr, 0.4):
                            signals.append(_make_signal(
                                symbol, SignalType.BUY, curr, qty,
                                f"Parabolic wedge bottom: accelerating bear trend exhausted"
                            ))

        return signals


# ─── 16. Micro Double Top/Bottom ──────────────────────────────────────────

@register_strategy
class MicroDoubleTopBottomStrategy(BaseStrategy):
    name = "brooks_micro_dt_db"
    description = (
        "Micro Double Top/Bottom: Two bars with nearly equal highs (mDT) or lows (mDB). "
        "Quick reversal pattern, often at end of small legs. "
        "More frequent than full double top/bottom."
    )

    def default_params(self) -> dict:
        return {"tolerance_pct": 0.15, "quantity": 1}

    def generate_signals(self, symbol: str, bars: list[dict]) -> list[Signal]:
        tol = self.params.get("tolerance_pct", 0.15) / 100
        qty = self.params.get("quantity", 1)
        if len(bars) < 10:
            return []

        signals = []

        for i in range(3, len(bars)):
            prev2, prev, curr = bars[i - 2], bars[i - 1], bars[i]

            # Micro Double Top: prev2 and prev have similar highs, curr reverses
            if (abs(prev2["high"] - prev["high"]) / prev["high"] < tol and
                prev["high"] > prev2["close"] and prev2["high"] > bars[i - 3]["close"] if i >= 3 else True):
                if _is_bear(curr) and curr["close"] < min(prev["low"], prev2["low"]):
                    signals.append(_make_signal(
                        symbol, SignalType.SELL, curr, qty,
                        f"Micro DT at {prev['high']:.2f}, bear reversal"
                    ))

            # Micro Double Bottom
            if (abs(prev2["low"] - prev["low"]) / prev["low"] < tol and
                prev["low"] < prev2["close"] and prev2["low"] < bars[i - 3]["close"] if i >= 3 else True):
                if _is_bull(curr) and curr["close"] > max(prev["high"], prev2["high"]):
                    signals.append(_make_signal(
                        symbol, SignalType.BUY, curr, qty,
                        f"Micro DB at {prev['low']:.2f}, bull reversal"
                    ))

        return signals


# ─── 17. Major Trend Reversal ──────────────────────────────────────────────

@register_strategy
class MajorTrendReversalStrategy(BaseStrategy):
    name = "brooks_major_reversal"
    description = (
        "Major Trend Reversal: (1) Prior strong trend, (2) Climactic bar(s), "
        "(3) Break of trend structure, (4) Higher low/lower high test."
    )

    def default_params(self) -> dict:
        return {"ema_period": 20, "trend_bars": 10, "quantity": 1}

    def generate_signals(self, symbol: str, bars: list[dict]) -> list[Signal]:
        ema_p = self.params.get("ema_period", 20)
        trend_n = self.params.get("trend_bars", 10)
        qty = self.params.get("quantity", 1)
        if len(bars) < ema_p + trend_n + 5:
            return []

        closes = [b["close"] for b in bars]
        ema = _ema(closes, ema_p)
        signals = []

        for i in range(ema_p + trend_n, len(bars)):
            if ema[i] == 0:
                continue

            window_start_close = bars[i - trend_n]["close"]
            window_low = min(b["low"] for b in bars[i - trend_n:i])
            window_high = max(b["high"] for b in bars[i - trend_n:i])

            prev2, prev, curr = bars[i - 2], bars[i - 1], bars[i]

            # Bullish major reversal
            decline = window_start_close - window_low
            if decline > 0:
                is_climax = _is_bear(prev2) and _is_strong(prev2, 0.5) and prev2["low"] <= window_low * 1.003
                higher_low = prev["low"] > prev2["low"] or curr["low"] > prev2["low"]
                strong_rev = _is_bull(curr) and _is_strong(curr, 0.5)
                cross_ema = prev["close"] < ema[i - 1] and curr["close"] > ema[i]

                if is_climax and higher_low and (strong_rev or cross_ema):
                    signals.append(_make_signal(
                        symbol, SignalType.BUY, curr, qty,
                        f"Major bull reversal: climax at {prev2['low']:.2f}, higher low confirmed"
                    ))

            # Bearish major reversal
            rally = window_high - window_start_close
            if rally > 0:
                is_climax = _is_bull(prev2) and _is_strong(prev2, 0.5) and prev2["high"] >= window_high * 0.997
                lower_high = prev["high"] < prev2["high"] or curr["high"] < prev2["high"]
                strong_rev = _is_bear(curr) and _is_strong(curr, 0.5)
                cross_ema = prev["close"] > ema[i - 1] and curr["close"] < ema[i]

                if is_climax and lower_high and (strong_rev or cross_ema):
                    signals.append(_make_signal(
                        symbol, SignalType.SELL, curr, qty,
                        f"Major bear reversal: climax at {prev2['high']:.2f}, lower high confirmed"
                    ))

        return signals


# ═══════════════════════════════════════════════════════════════════════════════
# TRADING RANGE STRATEGIES
# ═══════════════════════════════════════════════════════════════════════════════

# ─── 18. Failed Breakout ───────────────────────────────────────────────────

@register_strategy
class FailedBreakoutStrategy(BaseStrategy):
    name = "brooks_failed_breakout"
    description = (
        "Failed Breakout: Price breaks above/below a range but immediately reverses. "
        "Fade the breakout direction."
    )

    def default_params(self) -> dict:
        return {"range_lookback": 10, "quantity": 1}

    def generate_signals(self, symbol: str, bars: list[dict]) -> list[Signal]:
        lb = self.params.get("range_lookback", 10)
        qty = self.params.get("quantity", 1)
        if len(bars) < lb + 3:
            return []

        signals = []

        for i in range(lb + 1, len(bars)):
            window = bars[i - lb - 1:i - 1]
            rh = max(b["high"] for b in window)
            rl = min(b["low"] for b in window)
            prev, curr = bars[i - 1], bars[i]

            if prev["high"] > rh and prev["close"] > rh:
                if curr["close"] < rh and _is_bear(curr) and _is_strong(curr, 0.4):
                    signals.append(_make_signal(
                        symbol, SignalType.SELL, curr, qty,
                        f"Failed bull BO: broke {rh:.2f} then reversed"
                    ))

            if prev["low"] < rl and prev["close"] < rl:
                if curr["close"] > rl and _is_bull(curr) and _is_strong(curr, 0.4):
                    signals.append(_make_signal(
                        symbol, SignalType.BUY, curr, qty,
                        f"Failed bear BO: broke {rl:.2f} then reversed"
                    ))

        return signals


# ─── 19. Barb Wire ─────────────────────────────────────────────────────────

@register_strategy
class BarbWireStrategy(BaseStrategy):
    name = "brooks_barb_wire"
    description = (
        "Barb Wire: Series of overlapping doji/small bars (tight trading range). "
        "Do NOT trade inside barb wire. Only trade the breakout when a strong "
        "trend bar finally breaks out of the cluster."
    )

    def default_params(self) -> dict:
        return {"min_doji_bars": 4, "quantity": 1}

    def generate_signals(self, symbol: str, bars: list[dict]) -> list[Signal]:
        min_dojis = self.params.get("min_doji_bars", 4)
        qty = self.params.get("quantity", 1)
        if len(bars) < min_dojis + 3:
            return []

        signals = []

        for i in range(min_dojis + 1, len(bars)):
            # Check for barb wire: consecutive dojis/small overlapping bars
            window = bars[i - min_dojis - 1:i - 1]
            doji_count = sum(1 for b in window if _is_doji(b, 0.4))
            if doji_count < min_dojis:
                continue

            # Check overlapping
            overlapping = all(
                window[j]["high"] >= window[j - 1]["low"] and window[j]["low"] <= window[j - 1]["high"]
                for j in range(1, len(window))
            )
            if not overlapping:
                continue

            bw_high = max(b["high"] for b in window)
            bw_low = min(b["low"] for b in window)
            curr = bars[i]

            # Breakout with strong bar
            if _is_bull(curr) and _is_strong(curr, 0.5) and curr["close"] > bw_high:
                signals.append(_make_signal(
                    symbol, SignalType.BUY, curr, qty,
                    f"Barb Wire breakout up: strong bar above {bw_high:.2f}"
                ))
            elif _is_bear(curr) and _is_strong(curr, 0.5) and curr["close"] < bw_low:
                signals.append(_make_signal(
                    symbol, SignalType.SELL, curr, qty,
                    f"Barb Wire breakout down: strong bar below {bw_low:.2f}"
                ))

        return signals


# ─── 20. Second Entry ──────────────────────────────────────────────────────

@register_strategy
class SecondEntryStrategy(BaseStrategy):
    name = "brooks_second_entry"
    description = (
        "Second Entry: In a trading range, the first reversal often fails. "
        "The second attempt at the same direction is higher probability. "
        "Buy second test of range low, sell second test of range high."
    )

    def default_params(self) -> dict:
        return {"range_lookback": 15, "tolerance_pct": 0.3, "quantity": 1}

    def generate_signals(self, symbol: str, bars: list[dict]) -> list[Signal]:
        lb = self.params.get("range_lookback", 15)
        tol = self.params.get("tolerance_pct", 0.3) / 100
        qty = self.params.get("quantity", 1)
        if len(bars) < lb + 5:
            return []

        signals = []

        for i in range(lb + 3, len(bars)):
            window = bars[i - lb:i - 3]
            if len(window) < lb - 3:
                continue
            rh = max(b["high"] for b in window)
            rl = min(b["low"] for b in window)

            # First test of low then second test
            b1, b2, curr = bars[i - 2], bars[i - 1], bars[i]

            # Second entry buy at range bottom
            first_test_low = b1["low"] <= rl * (1 + tol) and _is_bull(b1)
            second_test_low = b2["low"] <= rl * (1 + tol)
            if first_test_low and second_test_low and _is_bull(curr) and curr["close"] > b2["high"]:
                signals.append(_make_signal(
                    symbol, SignalType.BUY, curr, qty,
                    f"2nd Entry buy: double test of range low {rl:.2f}"
                ))

            # Second entry sell at range top
            first_test_high = b1["high"] >= rh * (1 - tol) and _is_bear(b1)
            second_test_high = b2["high"] >= rh * (1 - tol)
            if first_test_high and second_test_high and _is_bear(curr) and curr["close"] < b2["low"]:
                signals.append(_make_signal(
                    symbol, SignalType.SELL, curr, qty,
                    f"2nd Entry sell: double test of range high {rh:.2f}"
                ))

        return signals


# ─── 21. Trading Range Breakout ────────────────────────────────────────────

@register_strategy
class TradingRangeBreakoutStrategy(BaseStrategy):
    name = "brooks_range_breakout"
    description = (
        "Trading Range Breakout: Enter on strong breakout from a defined range. "
        "Requires the breakout bar to close strongly beyond the range boundary "
        "with above-average size."
    )

    def default_params(self) -> dict:
        return {"range_lookback": 15, "quantity": 1}

    def generate_signals(self, symbol: str, bars: list[dict]) -> list[Signal]:
        lb = self.params.get("range_lookback", 15)
        qty = self.params.get("quantity", 1)
        if len(bars) < lb + 3:
            return []

        atr = _atr(bars)
        signals = []

        for i in range(lb + 1, len(bars)):
            if atr[i] == 0:
                continue
            window = bars[i - lb:i]
            rh = max(b["high"] for b in window)
            rl = min(b["low"] for b in window)
            curr = bars[i]

            # Strong breakout above range
            if (curr["close"] > rh and _is_bull(curr) and
                _is_strong(curr, 0.5) and _range(curr) > atr[i] * 1.0):
                signals.append(_make_signal(
                    symbol, SignalType.BUY, curr, qty,
                    f"Range breakout up: strong bar above {rh:.2f}"
                ))

            # Strong breakout below range
            if (curr["close"] < rl and _is_bear(curr) and
                _is_strong(curr, 0.5) and _range(curr) > atr[i] * 1.0):
                signals.append(_make_signal(
                    symbol, SignalType.SELL, curr, qty,
                    f"Range breakout down: strong bar below {rl:.2f}"
                ))

        return signals


# ═══════════════════════════════════════════════════════════════════════════════
# BAR PATTERN STRATEGIES
# ═══════════════════════════════════════════════════════════════════════════════

# ─── 22. Outside Bar ───────────────────────────────────────────────────────

@register_strategy
class OutsideBarStrategy(BaseStrategy):
    name = "brooks_outside_bar"
    description = (
        "Outside Bar (Engulfing): Current bar's range engulfs the previous bar. "
        "Trade the close direction - bullish outside bar = buy, bearish = sell. "
        "Strongest at swing points and after tight ranges."
    )

    def default_params(self) -> dict:
        return {"ema_period": 20, "quantity": 1}

    def generate_signals(self, symbol: str, bars: list[dict]) -> list[Signal]:
        ema_p = self.params.get("ema_period", 20)
        qty = self.params.get("quantity", 1)
        if len(bars) < ema_p + 3:
            return []

        closes = [b["close"] for b in bars]
        ema = _ema(closes, ema_p)
        signals = []

        for i in range(ema_p + 1, len(bars)):
            if ema[i] == 0:
                continue
            prev, curr = bars[i - 1], bars[i]

            if not _is_outside(curr, prev):
                continue
            if not _is_strong(curr, 0.4):
                continue

            # Bullish outside bar
            if _is_bull(curr):
                # Better at swing low or below EMA
                at_low = curr["low"] <= min(b["low"] for b in bars[max(0, i - 5):i]) * 1.003
                if at_low or curr["close"] > ema[i]:
                    signals.append(_make_signal(
                        symbol, SignalType.BUY, curr, qty,
                        f"Bull outside bar: engulfed {prev['high']:.2f}-{prev['low']:.2f}"
                    ))

            # Bearish outside bar
            elif _is_bear(curr):
                at_high = curr["high"] >= max(b["high"] for b in bars[max(0, i - 5):i]) * 0.997
                if at_high or curr["close"] < ema[i]:
                    signals.append(_make_signal(
                        symbol, SignalType.SELL, curr, qty,
                        f"Bear outside bar: engulfed {prev['high']:.2f}-{prev['low']:.2f}"
                    ))

        return signals


# ─── 23. Gap Bar Setup ────────────────────────────────────────────────────

@register_strategy
class GapBarStrategy(BaseStrategy):
    name = "brooks_gap_bar"
    description = (
        "Gap Bar: When price gaps up/down from previous close, the gap often acts "
        "as support/resistance. Trade continuation if gap holds (buy on gap up pullback), "
        "or fade if gap fills completely."
    )

    def default_params(self) -> dict:
        return {"min_gap_pct": 0.3, "quantity": 1}

    def generate_signals(self, symbol: str, bars: list[dict]) -> list[Signal]:
        min_gap = self.params.get("min_gap_pct", 0.3) / 100
        qty = self.params.get("quantity", 1)
        if len(bars) < 5:
            return []

        signals = []

        for i in range(2, len(bars)):
            prev_close = bars[i - 2]["close"]
            gap_bar = bars[i - 1]
            curr = bars[i]

            gap_pct = (gap_bar["open"] - prev_close) / prev_close

            # Gap up
            if gap_pct > min_gap:
                # Gap holds: pullback but low stays above prev close
                if (gap_bar["low"] > prev_close and
                    _is_bear(gap_bar) and _is_bull(curr) and
                    curr["close"] > gap_bar["high"]):
                    signals.append(_make_signal(
                        symbol, SignalType.BUY, curr, qty,
                        f"Gap up held: gap at {prev_close:.2f}, buy pullback"
                    ))
                # Gap fills: bearish
                elif (curr["close"] < prev_close and _is_bear(curr) and _is_strong(curr, 0.4)):
                    signals.append(_make_signal(
                        symbol, SignalType.SELL, curr, qty,
                        f"Gap up filled: failed above {prev_close:.2f}, bearish"
                    ))

            # Gap down
            elif gap_pct < -min_gap:
                if (gap_bar["high"] < prev_close and
                    _is_bull(gap_bar) and _is_bear(curr) and
                    curr["close"] < gap_bar["low"]):
                    signals.append(_make_signal(
                        symbol, SignalType.SELL, curr, qty,
                        f"Gap down held: gap at {prev_close:.2f}, sell rally"
                    ))
                elif (curr["close"] > prev_close and _is_bull(curr) and _is_strong(curr, 0.4)):
                    signals.append(_make_signal(
                        symbol, SignalType.BUY, curr, qty,
                        f"Gap down filled: failed below {prev_close:.2f}, bullish"
                    ))

        return signals


# ─── 24. Micro Channel ────────────────────────────────────────────────────

@register_strategy
class MicroChannelStrategy(BaseStrategy):
    name = "brooks_micro_channel"
    description = (
        "Micro Channel: 3+ consecutive bars where every bar has a higher low (bull) "
        "or lower high (bear). Very strong trend. First break of the micro channel "
        "is a buy/sell signal (pullback entry)."
    )

    def default_params(self) -> dict:
        return {"min_bars": 4, "quantity": 1}

    def generate_signals(self, symbol: str, bars: list[dict]) -> list[Signal]:
        min_b = self.params.get("min_bars", 4)
        qty = self.params.get("quantity", 1)
        if len(bars) < min_b + 3:
            return []

        signals = []

        for i in range(min_b + 1, len(bars)):
            # Bull micro channel: min_b consecutive higher lows
            bull_mc = True
            for j in range(i - min_b, i):
                if bars[j]["low"] <= bars[j - 1]["low"]:
                    bull_mc = False
                    break

            if bull_mc:
                # First bar to break the channel (lower low)
                curr = bars[i]
                prev = bars[i - 1]
                if curr["low"] < prev["low"]:
                    # This is the pullback - next bull bar is entry
                    if i + 1 < len(bars):
                        entry = bars[i + 1]
                        if _is_bull(entry) and entry["close"] > curr["high"]:
                            signals.append(_make_signal(
                                symbol, SignalType.BUY, entry, qty,
                                f"Micro Channel break: {min_b} higher lows, buy first pullback"
                            ))

            # Bear micro channel: min_b consecutive lower highs
            bear_mc = True
            for j in range(i - min_b, i):
                if bars[j]["high"] >= bars[j - 1]["high"]:
                    bear_mc = False
                    break

            if bear_mc:
                curr = bars[i]
                prev = bars[i - 1]
                if curr["high"] > prev["high"]:
                    if i + 1 < len(bars):
                        entry = bars[i + 1]
                        if _is_bear(entry) and entry["close"] < curr["low"]:
                            signals.append(_make_signal(
                                symbol, SignalType.SELL, entry, qty,
                                f"Micro Channel break: {min_b} lower highs, sell first rally"
                            ))

        return signals


# ═══════════════════════════════════════════════════════════════════════════════
# ADVANCED STRATEGIES
# ═══════════════════════════════════════════════════════════════════════════════

# ─── 25. Measured Move ─────────────────────────────────────────────────────

@register_strategy
class MeasuredMoveStrategy(BaseStrategy):
    name = "brooks_measured_move"
    description = (
        "Measured Move: After leg 1 (impulse) and leg 2 (pullback), "
        "leg 3 is expected to equal leg 1 in size. Take profit at MM target. "
        "Also fade at MM completion (potential reversal zone)."
    )

    def default_params(self) -> dict:
        return {"tolerance_pct": 1.0, "quantity": 1}

    def generate_signals(self, symbol: str, bars: list[dict]) -> list[Signal]:
        tol = self.params.get("tolerance_pct", 1.0) / 100
        qty = self.params.get("quantity", 1)
        if len(bars) < 15:
            return []

        signals = []
        sh = _swing_highs(bars, 2)
        sl = _swing_lows(bars, 2)

        # Bull measured move: low -> high -> higher low -> target
        for hi in range(len(sh)):
            i_h, h = sh[hi]
            # Find preceding swing low
            preceding_lows = [(i_l, l) for i_l, l in sl if i_l < i_h]
            if not preceding_lows:
                continue
            i_l1, l1 = preceding_lows[-1]

            # Find higher low after the high
            following_lows = [(i_l, l) for i_l, l in sl if i_l > i_h and l > l1]
            if not following_lows:
                continue
            i_l2, l2 = following_lows[0]

            # Measured move target
            leg1 = h - l1
            target = l2 + leg1

            # Check if price reaches target zone
            for j in range(i_l2 + 1, min(i_l2 + 20, len(bars))):
                if abs(bars[j]["high"] - target) / target < tol:
                    if _is_bear(bars[j]) or (j + 1 < len(bars) and _is_bear(bars[j + 1])):
                        rev_bar = bars[j + 1] if j + 1 < len(bars) and _is_bear(bars[j + 1]) else bars[j]
                        signals.append(_make_signal(
                            symbol, SignalType.SELL, rev_bar, qty,
                            f"MM target hit: {l1:.0f}->{h:.0f}->{l2:.0f}, target {target:.2f}"
                        ))
                    break

        # Bear measured move
        for li in range(len(sl)):
            i_l, l = sl[li]
            preceding_highs = [(i_h, h) for i_h, h in sh if i_h < i_l]
            if not preceding_highs:
                continue
            i_h1, h1 = preceding_highs[-1]

            following_highs = [(i_h, h) for i_h, h in sh if i_h > i_l and h < h1]
            if not following_highs:
                continue
            i_h2, h2 = following_highs[0]

            leg1 = h1 - l
            target = h2 - leg1

            for j in range(i_h2 + 1, min(i_h2 + 20, len(bars))):
                if target > 0 and abs(bars[j]["low"] - target) / target < tol:
                    if _is_bull(bars[j]) or (j + 1 < len(bars) and _is_bull(bars[j + 1])):
                        rev_bar = bars[j + 1] if j + 1 < len(bars) and _is_bull(bars[j + 1]) else bars[j]
                        signals.append(_make_signal(
                            symbol, SignalType.BUY, rev_bar, qty,
                            f"MM target hit: {h1:.0f}->{l:.0f}->{h2:.0f}, target {target:.2f}"
                        ))
                    break

        signals.sort(key=lambda s: s.timestamp)
        # Deduplicate
        seen = set()
        unique = []
        for s in signals:
            key = s.timestamp.isoformat()
            if key not in seen:
                seen.add(key)
                unique.append(s)
        return unique


# ─── 26. Breakout Pullback ─────────────────────────────────────────────────

@register_strategy
class BreakoutPullbackStrategy(BaseStrategy):
    name = "brooks_breakout_pullback"
    description = (
        "Breakout Pullback: After strong breakout, wait for pullback that holds "
        "above breakout level. High probability when breakout bar is strong."
    )

    def default_params(self) -> dict:
        return {"range_lookback": 15, "ema_period": 20, "quantity": 1}

    def generate_signals(self, symbol: str, bars: list[dict]) -> list[Signal]:
        lb = self.params.get("range_lookback", 15)
        ema_p = self.params.get("ema_period", 20)
        qty = self.params.get("quantity", 1)
        if len(bars) < max(lb, ema_p) + 5:
            return []

        signals = []

        for i in range(lb + 3, len(bars)):
            window = bars[i - lb - 3:i - 3]
            if len(window) < lb:
                continue
            rh = max(b["high"] for b in window)
            rl = min(b["low"] for b in window)

            bo, pb, entry = bars[i - 2], bars[i - 1], bars[i]

            if _is_bull(bo) and _is_strong(bo, 0.5) and bo["close"] > rh:
                if pb["low"] >= rh * 0.995 and _is_bull(entry) and entry["close"] > pb["high"]:
                    signals.append(_make_signal(
                        symbol, SignalType.BUY, entry, qty,
                        f"Bull BO pullback: held above {rh:.2f}"
                    ))

            if _is_bear(bo) and _is_strong(bo, 0.5) and bo["close"] < rl:
                if pb["high"] <= rl * 1.005 and _is_bear(entry) and entry["close"] < pb["low"]:
                    signals.append(_make_signal(
                        symbol, SignalType.SELL, entry, qty,
                        f"Bear BO pullback: held below {rl:.2f}"
                    ))

        return signals


# ─── 27. 20 Gap Bar ───────────────────────────────────────────────────────

@register_strategy
class TwentyGapBarStrategy(BaseStrategy):
    name = "brooks_20_gap_bar"
    description = (
        "20 Gap Bar: When a bar's low is above the 20 EMA (gap bar) in a bull trend "
        "(or high below EMA in bear), it shows strong momentum. "
        "After 20+ bars without touching EMA, first touch is a buy/sell."
    )

    def default_params(self) -> dict:
        return {"ema_period": 20, "gap_count": 15, "quantity": 1}

    def generate_signals(self, symbol: str, bars: list[dict]) -> list[Signal]:
        ema_p = self.params.get("ema_period", 20)
        gap_n = self.params.get("gap_count", 15)
        qty = self.params.get("quantity", 1)
        if len(bars) < ema_p + gap_n + 3:
            return []

        closes = [b["close"] for b in bars]
        ema = _ema(closes, ema_p)
        signals = []

        for i in range(ema_p + gap_n, len(bars)):
            if ema[i] == 0:
                continue

            # Count consecutive bars with low above EMA (bull gap bars)
            bull_gap_count = 0
            for j in range(i - 1, max(ema_p, i - 50), -1):
                if ema[j] > 0 and bars[j]["low"] > ema[j]:
                    bull_gap_count += 1
                else:
                    break

            if bull_gap_count >= gap_n:
                curr = bars[i]
                # First touch of EMA
                if curr["low"] <= ema[i] * 1.002 and _is_bull(curr):
                    signals.append(_make_signal(
                        symbol, SignalType.BUY, curr, qty,
                        f"20 Gap Bar: {bull_gap_count} bars above EMA, first touch = buy"
                    ))

            # Bear version
            bear_gap_count = 0
            for j in range(i - 1, max(ema_p, i - 50), -1):
                if ema[j] > 0 and bars[j]["high"] < ema[j]:
                    bear_gap_count += 1
                else:
                    break

            if bear_gap_count >= gap_n:
                curr = bars[i]
                if curr["high"] >= ema[i] * 0.998 and _is_bear(curr):
                    signals.append(_make_signal(
                        symbol, SignalType.SELL, curr, qty,
                        f"20 Gap Bar: {bear_gap_count} bars below EMA, first touch = sell"
                    ))

        return signals
