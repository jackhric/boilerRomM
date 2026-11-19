// Numbers and dates as the store words them.
import type { Progress } from "../api";

export function formatSize(bytes: number): string {
  if (bytes >= 1 << 30) return `${(bytes / (1 << 30)).toFixed(1)} GB`;
  if (bytes >= 1 << 20) return `${Math.round(bytes / (1 << 20))} MB`;
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

export function percent(p?: Progress): number {
  return p && p.total_bytes ? (100 * p.done_bytes) / p.total_bytes : 0;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
/** "1998-06-29" -> "Jun 29, 1998", like the store's release dates. */
export function formatDate(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  return m ? `${MONTHS[Number(m[2]) - 1]} ${Number(m[3])}, ${m[1]}` : "";
}

// RomM passes HowLongToBeat's numbers through; they are seconds there, but a small value can only be hours.
export function formatHours(value?: number): string {
  if (!value) return "";
  const hours = value >= 1000 ? value / 3600 : value;
  return hours >= 10 ? `${Math.round(hours)} hours` : `${Math.round(hours * 10) / 10} hours`;
}

/** Steam's review wording for a 0-100 score. */
export function scoreWord(score: number): string {
  if (score >= 95) return "Overwhelmingly Positive";
  if (score >= 80) return "Very Positive";
  if (score >= 70) return "Mostly Positive";
  if (score >= 40) return "Mixed";
  return "Mostly Negative";
}

/** "just now", "5 minutes ago", "2 hours ago"; "never" for 0. Both times are in seconds. */
export function formatAgo(then: number, now: number): string {
  if (!then) return "never";
  const s = Math.max(0, now - then);
  if (s < 60) return "just now";
  const unit = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"} ago`;
  if (s < 3600) return unit(Math.floor(s / 60), "minute");
  if (s < 86400) return unit(Math.floor(s / 3600), "hour");
  return unit(Math.floor(s / 86400), "day");
}
