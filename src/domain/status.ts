// A game's state in words and the one thing to do next, the same wherever a game is shown.
import type { Game, GameStatus, Progress } from "../api";
import { formatSize, percent } from "./format";

export const isBusy = (g: Game) => g.status === "queued" || g.status === "downloading";
/** Stopped short of installed: Resume continues it, Remove clears it. */
export const isStopped = (status: GameStatus) => status === "paused" || status === "incomplete" || status === "failed";
const STOPPED_TEXT: Record<"paused" | "incomplete" | "failed", string> = { paused: "Paused", incomplete: "Partly downloaded", failed: "Download failed" };

export type ActionKind = "download" | "resume" | "stop" | "play";
export const actionKind = (g: Game): ActionKind => (g.status === "installed" ? "play" : isBusy(g) ? "stop" : isStopped(g.status) ? "resume" : "download");
export const ACTION_LABELS: Record<ActionKind, string> = { download: "Download", resume: "Resume", stop: "Stop download", play: "Play" };
/** Removing is offered once there is something on the device to remove. */
export const canRemove = (g: Game) => g.status === "installed" || isStopped(g.status);

/** "42% · 1.2 GB of 4.1 GB · 12 MB/s", or the game's resting state in a few words. */
export function statusText(game: Game, p?: Progress): string {
  if (p && p.status === "downloading") return `${Math.round(percent(p))}% · ${formatSize(p.done_bytes)} of ${formatSize(p.total_bytes)}${p.bps ? ` · ${formatSize(p.bps)}/s` : ""}`;
  switch (game.status) {
    case "installed": return "On this Device";
    case "queued": return "Queued";
    case "downloading": return "Starting…";
    case "paused":
    case "incomplete":
    case "failed": return STOPPED_TEXT[game.status];
    default: return formatSize(game.size_bytes);
  }
}
