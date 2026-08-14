export function compactNumber(value: number): string {
  return new Intl.NumberFormat("en-US", {
    notation: "compact",
    maximumFractionDigits: value >= 100_000 ? 0 : 1,
  }).format(value);
}

export function relativeTime(value: string, now = new Date()): string {
  const hasTimezone = /(?:Z|[+-]\d{2}:\d{2})$/.test(value);
  const date = new Date(hasTimezone ? value : `${value}Z`);
  const minutes = Math.max(
    1,
    Math.round((now.getTime() - date.getTime()) / 60_000),
  );
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

export function titleCase(value: string): string {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

export function scoreTone(value: number): "strong" | "watch" | "risk" {
  if (value >= 70) return "strong";
  if (value >= 50) return "watch";
  return "risk";
}
