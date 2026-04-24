import { useEffect, useRef, useCallback } from "react";
import {
  createChart,
  CandlestickSeries,
  HistogramSeries,
  createSeriesMarkers,
  type IChartApi,
  type ISeriesApi,
  type CandlestickData,
  type HistogramData,
  type Time,
  type ISeriesMarkersPluginApi,
  ColorType,
  CrosshairMode,
  TickMarkType,
} from "lightweight-charts";
import type { Bar, Signal } from "../types";
import { formatBeijingDateTime } from "../utils/time";

interface ChartProps {
  bars: Bar[];
  signals: Signal[];
  height?: number;
}

function toChartTime(iso: string): Time {
  return (new Date(iso).getTime() / 1000) as Time;
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

export default function Chart({ bars, signals, height = 500 }: ChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);

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
    markersRef.current = seriesMarkers;

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
    if (!candleRef.current || !volumeRef.current || bars.length === 0) return;

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

    if (markersRef.current) {
      const markers = signals.map((s) => ({
        time: toChartTime(s.timestamp),
        position: s.signal_type === "buy" ? ("belowBar" as const) : ("aboveBar" as const),
        color: s.signal_type === "buy" ? "#22c55e" : "#ef4444",
        shape: s.signal_type === "buy" ? ("arrowUp" as const) : ("arrowDown" as const),
        text: `${s.signal_type.toUpperCase()} $${s.price.toFixed(2)}`,
      }));
      markers.sort((a, b) => (a.time as number) - (b.time as number));
      markersRef.current.setMarkers(markers);
    }

    chartRef.current?.timeScale().fitContent();
  }, [bars, signals]);

  return (
    <div
      ref={containerRef}
      className="w-full rounded-lg overflow-hidden border border-gray-800"
    />
  );
}
