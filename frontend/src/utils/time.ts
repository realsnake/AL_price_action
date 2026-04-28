const BEIJING_TIME_ZONE = "Asia/Shanghai";

function parseTimestamp(value: string): Date {
  // Backend timestamps are often emitted as naive UTC strings.
  // Add an explicit UTC suffix so the browser doesn't treat them as local time.
  const normalized = /(?:Z|[+-]\d{2}:\d{2})$/.test(value) ? value : `${value}Z`;
  return new Date(normalized);
}

const beijingDateFormatter = new Intl.DateTimeFormat("en-CA", {
  timeZone: BEIJING_TIME_ZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

const beijingDateTimeFormatter = new Intl.DateTimeFormat("zh-CN", {
  timeZone: BEIJING_TIME_ZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
});

const beijingTimeFormatter = new Intl.DateTimeFormat("zh-CN", {
  timeZone: BEIJING_TIME_ZONE,
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
});

export function formatBeijingDate(value: string): string {
  return beijingDateFormatter.format(parseTimestamp(value));
}

export function formatBeijingDateTime(value: string | null | undefined): string {
  return value ? `${beijingDateTimeFormatter.format(parseTimestamp(value))} BJT` : "n/a";
}

export function formatBeijingTime(value: string | null | undefined): string {
  return value ? `${beijingTimeFormatter.format(parseTimestamp(value))} BJT` : "n/a";
}
