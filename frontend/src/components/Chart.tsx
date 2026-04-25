import { useEffect, useRef, useCallback } from "react";
import {
  createChart,
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  createSeriesMarkers,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
  type CandlestickData,
  type HistogramData,
  type LineData,
  type Time,
  type ISeriesMarkersPluginApi,
  ColorType,
  CrosshairMode,
  LineStyle,
  TickMarkType,
} from "lightweight-charts";
import type { Bar, PaperStrategyStatus, Signal } from "../types";
import { formatBeijingDateTime } from "../utils/time";

interface ChartProps {
  bars: Bar[];
  signals: Signal[];
  paperRunnerStatuses?: PaperStrategyStatus[];
  viewKey?: string;
  height?: number;
}

type ChartMarker = Parameters<ISeriesMarkersPluginApi<Time>["setMarkers"]>[0][number];
const EMA20_PERIOD = 20;

function toChartTime(iso: string): Time {
  return (new Date(iso).getTime() / 1000) as Time;
}

function calculateEmaData(bars: Bar[], period: number): LineData[] {
  if (bars.length === 0) {
    return [];
  }

  const multiplier = 2 / (period + 1);
  let ema: number | null = null;
  return bars.map((bar) => {
    ema = ema == null ? bar.close : bar.close * multiplier + ema * (1 - multiplier);
    return {
      time: toChartTime(bar.time),
      value: ema,
    };
  });
}

function exitReasonLabel(reason: string): string {
  switch (reason) {
    case "phase1_confirmed_swing_low_break_after_1r":
      return "1R small PB swing/EMA exit";
    case "phase1_pullback_count_confirmed_swing_low_break_after_1r":
      return "1R swing/EMA exit";
    case "phase1_breakout_confirmed_swing_low_break_after_1r":
      return "1R breakout swing/EMA exit";
    case "stop_loss":
      return "stop loss";
    case "take_profit":
      return "take profit";
    case "session_close":
      return "session close";
    case "manual_stop":
      return "manual stop";
    default:
      return reason.replaceAll("_", " ");
  }
}

function markerTimeOrNull(iso: string | null | undefined): Time | null {
  if (!iso) {
    return null;
  }
  const time = toChartTime(iso);
  return Number.isNaN(time as number) ? null : time;
}

function isDynamicExitReason(reason: string | null | undefined): boolean {
  return reason === "phase1_confirmed_swing_low_break_after_1r"
    || reason === "phase1_pullback_count_confirmed_swing_low_break_after_1r"
    || reason === "phase1_breakout_confirmed_swing_low_break_after_1r";
}

function makeExitMarker(
  time: Time,
  text: string,
  dynamic = false,
): ChartMarker {
  return {
    time,
    position: "aboveBar" as const,
    color: dynamic ? "#f97316" : "#ef4444",
    shape: "arrowDown" as const,
    text,
  };
}

function latestDynamicExitTriggerTime(runnerStatus: PaperStrategyStatus): Time | null {
  const dynamicExit = runnerStatus.dynamic_exit;
  if (dynamicExit?.triggered) {
    return markerTimeOrNull(dynamicExit.bar_time);
  }
  return null;
}

function paperExitMarker(runnerStatus: PaperStrategyStatus): ChartMarker[] {
  const label = strategyLabel(runnerStatus.strategy);
  const lastExit = runnerStatus.last_exit;
  if (lastExit != null) {
    const exitTime = markerTimeOrNull(lastExit.exit_time);
    if (exitTime == null) {
      return [];
    }
    return [makeExitMarker(
      exitTime,
      `${label} EXIT ${lastExit.quantity} @ $${lastExit.exit_price.toFixed(2)} · ${exitReasonLabel(lastExit.reason)}`,
      isDynamicExitReason(lastExit.reason),
    )];
  }

  const pendingExit = runnerStatus.pending_order;
  if (pendingExit?.side === "sell") {
    const pendingTime = markerTimeOrNull(pendingExit.signal_time);
    if (pendingTime == null) {
      return [];
    }
    return [makeExitMarker(
      pendingTime,
      `${label} EXIT PENDING ${pendingExit.quantity} · ${exitReasonLabel(pendingExit.reason)}`,
      isDynamicExitReason(pendingExit.reason),
    )];
  }

  const triggerTime = latestDynamicExitTriggerTime(runnerStatus);
  if (triggerTime == null || runnerStatus.dynamic_exit?.trigger_price == null) {
    return [];
  }

  return [makeExitMarker(
    triggerTime,
    `${label} DYNAMIC EXIT $${runnerStatus.dynamic_exit.trigger_price.toFixed(2)} · ${exitReasonLabel(runnerStatus.dynamic_exit.trigger_reason ?? "")}`,
    true,
  )];
}

function paperEntryMarker(runnerStatus: PaperStrategyStatus): ChartMarker[] {
  const position = runnerStatus.position;
  if (position == null) {
    return [];
  }
  const label = strategyLabel(runnerStatus.strategy);
  const targetText =
    position.target_price == null
      ? "no fixed TP"
      : `TP $${position.target_price.toFixed(2)}`;
  return [{
    time: toChartTime(position.signal_time ?? position.entry_time),
    position: "belowBar" as const,
    color: strategyColor(runnerStatus.strategy),
    shape: "arrowUp" as const,
    text: `${label} ENTRY ${position.quantity} @ $${position.entry_price.toFixed(2)} · SL $${position.stop_price.toFixed(2)} · ${targetText}`,
  }];
}

function paperRunnerMarkers(runnerStatus: PaperStrategyStatus): ChartMarker[] {
  return [
    ...paperEntryMarker(runnerStatus),
    ...paperExitMarker(runnerStatus),
  ];
}

const BEIJING_TIME_ZONE = "Asia/Shanghai";

const beijingAxisFormatters = {
  year: new Intl.DateTimeFormat("zh-CN", {
    timeZone: BEIJING_TIME_ZONE,
    year: "numeric",
  }),
  month: new Intl.DateTimeFormat("zh-CN", {
    timeZone: BEIJING_TIME_ZONE,
    year: "numeric",
    month: "2-digit",
  }),
  day: new Intl.DateTimeFormat("zh-CN", {
    timeZone: BEIJING_TIME_ZONE,
    month: "2-digit",
    day: "2-digit",
  }),
  minute: new Intl.DateTimeFormat("zh-CN", {
    timeZone: BEIJING_TIME_ZONE,
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }),
  second: new Intl.DateTimeFormat("zh-CN", {
    timeZone: BEIJING_TIME_ZONE,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }),
};

function chartTimeToDate(time: Time): Date | null {
  if (typeof time === "number") {
    return new Date(time * 1000);
  }
  if (typeof time === "string") {
    return new Date(`${time}T00:00:00Z`);
  }
  if ("year" in time && "month" in time && "day" in time) {
    return new Date(Date.UTC(time.year, time.month - 1, time.day));
  }
  return null;
}

function formatBeijingAxisTick(time: Time, tickMarkType: TickMarkType): string {
  const date = chartTimeToDate(time);
  if (date == null || Number.isNaN(date.getTime())) {
    return String(time);
  }

  switch (tickMarkType) {
    case TickMarkType.Year:
      return beijingAxisFormatters.year.format(date);
    case TickMarkType.Month:
      return beijingAxisFormatters.month.format(date);
    case TickMarkType.DayOfMonth:
      return beijingAxisFormatters.day.format(date);
    case TickMarkType.TimeWithSeconds:
      return beijingAxisFormatters.second.format(date);
    case TickMarkType.Time:
    default:
      return beijingAxisFormatters.minute.format(date);
  }
}

function strategyLabel(strategy: string): string {
  switch (strategy) {
    case "brooks_small_pb_trend":
      return "Small PB Trend";
    case "brooks_breakout_pullback":
      return "Breakout Pullback";
    case "brooks_pullback_count":
      return "Pullback Count";
    default:
      return strategy;
  }
}

function strategyColor(strategy: string): string {
  switch (strategy) {
    case "brooks_small_pb_trend":
      return "#22d3ee";
    case "brooks_breakout_pullback":
      return "#f59e0b";
    case "brooks_pullback_count":
      return "#a78bfa";
    default:
      return "#38bdf8";
  }
}

export default function Chart({
  bars,
  signals,
  paperRunnerStatuses = [],
  viewKey,
  height = 500,
}: ChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const ema20Ref = useRef<ISeriesApi<"Line"> | null>(null);
  const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const runnerPriceLinesRef = useRef<IPriceLine[]>([]);
  const lastFitViewKeyRef = useRef<string | null>(null);

  const initChart = useCallback(() => {
    if (!containerRef.current) return;

    if (chartRef.current) {
      chartRef.current.remove();
      chartRef.current = null;
    }

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height,
      layout: {
        background: { type: ColorType.Solid, color: "#0f1117" },
        textColor: "#9ca3af",
      },
      grid: {
        vertLines: { color: "#1e2230" },
        horzLines: { color: "#1e2230" },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: "#2d3348" },
      timeScale: {
        borderColor: "#2d3348",
        timeVisible: true,
        secondsVisible: false,
        tickMarkFormatter: (time: Time, tickMarkType: TickMarkType) =>
          formatBeijingAxisTick(time, tickMarkType),
      },
      localization: {
        timeFormatter: (time: Time) =>
          typeof time === "number"
            ? formatBeijingDateTime(new Date(time * 1000).toISOString())
            : String(time),
      },
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#22c55e",
      downColor: "#ef4444",
      borderDownColor: "#ef4444",
      borderUpColor: "#22c55e",
      wickDownColor: "#ef4444",
      wickUpColor: "#22c55e",
    });

    const ema20Series = chart.addSeries(LineSeries, {
      color: "#fbbf24",
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: true,
      title: "EMA20",
    });

    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
    });

    chart.priceScale("volume").applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });

    const seriesMarkers = createSeriesMarkers(candleSeries);

    chartRef.current = chart;
    candleRef.current = candleSeries;
    volumeRef.current = volumeSeries;
    ema20Ref.current = ema20Series;
    markersRef.current = seriesMarkers;
    lastFitViewKeyRef.current = null;

    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        chart.applyOptions({ width: entry.contentRect.width });
      }
    });
    ro.observe(containerRef.current);

    return () => ro.disconnect();
  }, [height]);

  useEffect(() => {
    const cleanup = initChart();
    return () => {
      cleanup?.();
      if (chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
      }
    };
  }, [initChart]);

  useEffect(() => {
    if (!candleRef.current || !volumeRef.current || !ema20Ref.current || bars.length === 0) return;

    const candleData: CandlestickData[] = bars.map((b) => ({
      time: toChartTime(b.time),
      open: b.open,
      high: b.high,
      low: b.low,
      close: b.close,
    }));

    const volumeData: HistogramData[] = bars.map((b) => ({
      time: toChartTime(b.time),
      value: b.volume,
      color: b.close >= b.open ? "rgba(34,197,94,0.3)" : "rgba(239,68,68,0.3)",
    }));

    candleRef.current.setData(candleData);
    volumeRef.current.setData(volumeData);
    ema20Ref.current.setData(calculateEmaData(bars, EMA20_PERIOD));

    if (markersRef.current) {
      const signalMarkers: ChartMarker[] = signals.map((s) => ({
        time: toChartTime(s.timestamp),
        position: s.signal_type === "buy" ? ("belowBar" as const) : ("aboveBar" as const),
        color: s.signal_type === "buy" ? "#22c55e" : "#ef4444",
        shape: s.signal_type === "buy" ? ("arrowUp" as const) : ("arrowDown" as const),
        text: `${s.signal_type.toUpperCase()} $${s.price.toFixed(2)}`,
      }));
      const runnerMarkers = paperRunnerStatuses.flatMap(paperRunnerMarkers);
      const markers = [...signalMarkers, ...runnerMarkers];
      markers.sort((a, b) => (a.time as number) - (b.time as number));
      markersRef.current.setMarkers(markers);
    }

    const firstBar = bars[0];
    const firstBarKey = `${firstBar.time}:${firstBar.open}:${firstBar.high}:${firstBar.low}:${firstBar.close}`;
    const nextViewKey = `${viewKey ?? "default"}:${firstBarKey}`;
    if (lastFitViewKeyRef.current !== nextViewKey) {
      chartRef.current?.timeScale().fitContent();
      lastFitViewKeyRef.current = nextViewKey;
    }
  }, [bars, signals, paperRunnerStatuses, viewKey]);

  useEffect(() => {
    if (!candleRef.current) return;

    for (const line of runnerPriceLinesRef.current) {
      candleRef.current.removePriceLine(line);
    }
    runnerPriceLinesRef.current = [];

    const nextLines: IPriceLine[] = [];
    for (const runnerStatus of paperRunnerStatuses) {
      const label = strategyLabel(runnerStatus.strategy);
      const position = runnerStatus.position;
      if (position != null) {
        const color = strategyColor(runnerStatus.strategy);
        const targetText =
          position.target_price == null
            ? "no fixed TP"
            : `TP $${position.target_price.toFixed(2)}`;

        nextLines.push(candleRef.current.createPriceLine({
          price: position.entry_price,
          color,
          lineWidth: 2,
          lineStyle: LineStyle.Solid,
          axisLabelVisible: true,
          title: `${label} entry ${position.quantity} @ ${position.entry_price.toFixed(2)} · ${targetText}`,
        }));
        nextLines.push(candleRef.current.createPriceLine({
          price: position.stop_price,
          color: "#fb7185",
          lineWidth: 2,
          lineStyle: LineStyle.Dashed,
          axisLabelVisible: true,
          title: `${label} stop ${position.stop_price.toFixed(2)} · ${position.stop_reason}`,
        }));
        if (position.target_price != null) {
          nextLines.push(candleRef.current.createPriceLine({
            price: position.target_price,
            color: "#34d399",
            lineWidth: 2,
            lineStyle: LineStyle.Dashed,
            axisLabelVisible: true,
            title: `${label} target ${position.target_price.toFixed(2)} · ${position.target_reason ?? "take profit"}`,
          }));
        }
      }

      const dynamicExit = runnerStatus.dynamic_exit;
      if (dynamicExit == null) {
        continue;
      }

      nextLines.push(candleRef.current.createPriceLine({
        price: dynamicExit.one_r_price,
        color: dynamicExit.armed ? "#fbbf24" : "#78716c",
        lineWidth: 1,
        lineStyle: LineStyle.Dotted,
        axisLabelVisible: true,
        title: `${label} 1R ${dynamicExit.armed ? "armed" : "waiting"} @ ${dynamicExit.one_r_price.toFixed(2)}`,
      }));

      if (dynamicExit.swing_low != null) {
        nextLines.push(candleRef.current.createPriceLine({
          price: dynamicExit.swing_low,
          color: dynamicExit.triggered ? "#f97316" : dynamicExit.armed ? "#f59e0b" : "#92400e",
          lineWidth: 2,
          lineStyle: LineStyle.Dashed,
          axisLabelVisible: true,
          title: `${label} dynamic exit ${dynamicExit.triggered ? "TRIGGERED" : dynamicExit.armed ? "armed" : "waiting 1R"}: close < swing ${dynamicExit.swing_low.toFixed(2)} + EMA20`,
        }));
      }
    }

    runnerPriceLinesRef.current = nextLines;
    return () => {
      if (!candleRef.current) return;
      for (const line of runnerPriceLinesRef.current) {
        candleRef.current.removePriceLine(line);
      }
      runnerPriceLinesRef.current = [];
    };
  }, [paperRunnerStatuses]);

  return (
    <div className="relative w-full rounded-lg overflow-hidden border border-gray-800">
      <div className="pointer-events-none absolute left-3 top-3 z-10 rounded border border-amber-300/40 bg-slate-950/80 px-2 py-1 text-xs font-medium text-amber-300 shadow-lg shadow-slate-950/40">
        EMA20
      </div>
      <div ref={containerRef} className="w-full" />
    </div>
  );
}
