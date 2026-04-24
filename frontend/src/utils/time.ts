const BEIJING_TIME_ZONE = "Asia/Shanghai";

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
  return beijingDateFormatter.format(new Date(value));
}

export function formatBeijingDateTime(value: string | null | undefined): string {
  return value ? `${beijingDateTimeFormatter.format(new Date(value))} BJT` : "n/a";
}

export function formatBeijingTime(value: string | null | undefined): string {
  return value ? `${beijingTimeFormatter.format(new Date(value))} BJT` : "n/a";
}
