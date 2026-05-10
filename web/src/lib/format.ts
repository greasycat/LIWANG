export function formatBytes(v: number | null | undefined): string {
  if (v == null || v <= 0) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  let f = v;
  while (f >= 1024 && i < units.length - 1) {
    f /= 1024;
    i += 1;
  }
  return f >= 10 || i === 0 ? `${f.toFixed(0)} ${units[i]}` : `${f.toFixed(1)} ${units[i]}`;
}

export function formatMoney(v: number): string {
  return `¥${v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function formatInt(v: number): string {
  return v.toLocaleString();
}

const DATE_FMT = new Intl.DateTimeFormat("zh-CN", {
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
});

export function formatDateTime(iso: string): string {
  return DATE_FMT.format(new Date(iso));
}

export function dateBucket(iso: string): string {
  const dt = new Date(iso);
  const today = new Date();
  const days = Math.floor(
    (Date.UTC(today.getFullYear(), today.getMonth(), today.getDate()) -
      Date.UTC(dt.getFullYear(), dt.getMonth(), dt.getDate())) /
      86400000,
  );
  if (days <= 0) return "今天";
  if (days === 1) return "昨天";
  if (days < 7) return "本周";
  if (days < 30) return "本月";
  return "更早";
}
