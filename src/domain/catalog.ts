// What the store shows and in what order, worked out from the library alone.
import type { Game, GameDetails, Platform, Recommendation } from "../api";

export interface Row {
  key: string;
  title: string;
  subtitle: string;
  games: Game[];
  /** A short line under a card in place of its status, by rom id. */
  notes?: Record<number, string>;
}

const ROW_LIMIT = 24;

export function recentRow(games: Game[]): Row | undefined {
  const recent = [...games].sort((a, b) => b.added_at.localeCompare(a.added_at)).slice(0, ROW_LIMIT);
  return recent.length ? { key: "recent", title: "Recently added", subtitle: "New on your RomM server", games: recent } : undefined;
}

/** "Top rated" and "On this Device", the rows below the personal ones. */
export function laterRows(games: Game[]): Row[] {
  const rows: Row[] = [];
  const rated = topRated(games).slice(0, ROW_LIMIT);
  if (rated.length) rows.push({ key: "rated", title: "Top rated", subtitle: "Best reviewed in the library", games: rated });
  const installed = games.filter((g) => g.status === "installed");
  if (installed.length) rows.push({ key: "installed", title: "On this Device", subtitle: `${installed.length} ready to play`, games: installed });
  return rows;
}

/** Recommendations resolved against the library (RomM may recommend a game the snapshot no longer has). */
function resolve(games: Game[], recs: Recommendation[]): [Game, Recommendation][] {
  const byId = new Map(games.map((g) => [g.rom_id, g]));
  const seen = new Set<number>();
  const out: [Game, Recommendation][] = [];
  for (const r of recs) {
    const g = byId.get(r.rom_id);
    if (g && !seen.has(g.rom_id)) {
      seen.add(g.rom_id);
      out.push([g, r]);
    }
  }
  return out.slice(0, ROW_LIMIT);
}

/** "genre: Platform" -> "Genre: Platform". */
export function reasonText(reason: string): string {
  const [kind, ...rest] = reason.split(":");
  const value = rest.join(":").trim();
  if (!value) return reason;
  const label = kind.trim().replace(/_/g, " ");
  return `${label.charAt(0).toUpperCase()}${label.slice(1)}: ${value}`;
}

export function forYouRow(games: Game[], recs: Recommendation[]): Row | undefined {
  const picks = resolve(games, recs);
  if (!picks.length) return undefined;
  const seeds = new Set(picks.map(([, r]) => r.seed_rom_name || ""));
  const oneSeed = seeds.size === 1 ? [...seeds][0] : "";
  const notes: Record<number, string> = {};
  for (const [g, r] of picks) {
    notes[g.rom_id] = !oneSeed && r.seed_rom_name ? `Like ${r.seed_rom_name}` : r.reasons[0] ? reasonText(r.reasons[0]) : "";
  }
  return { key: "foryou", title: "For you", subtitle: oneSeed ? `Because you played ${oneSeed}` : "Picked from the games you play", games: picks.map(([g]) => g), notes };
}

export function similarRow(games: Game[], recs: Recommendation[], self: number): Row | undefined {
  const picks = resolve(games, recs.filter((r) => r.rom_id !== self));
  if (!picks.length) return undefined;
  const notes: Record<number, string> = {};
  for (const [g, r] of picks) if (r.reasons[0]) notes[g.rom_id] = reasonText(r.reasons[0]);
  return { key: "similar", title: "More like this", subtitle: "From your library", games: picks.map(([g]) => g), notes };
}

/** The portrait art of a game: SteamGridDB's capsule, then RomM's cover. */
export const coverOf = (game: Game) => game.art.grid || game.cover_large || game.cover;

/** The hero backdrop: SteamGridDB's hero, then (once details are known) the first screenshot or the cover. */
export const backdropOf = (game: Game, details?: GameDetails) => game.art.hero || (details ? details.screenshots[0] || game.cover_large || game.cover : undefined);

export function topRated(games: Game[]): Game[] {
  return games.filter((g) => g.rating !== null).sort((a, b) => (b.rating ?? 0) - (a.rating ?? 0));
}

export type SortKey = "name" | "added" | "rating" | "size" | "year";
export const SORTS: [SortKey, string][] = [["name", "Name"], ["added", "Recently added"], ["rating", "Rating"], ["year", "Release year"], ["size", "Size"]];
const compare: Record<SortKey, (a: Game, b: Game) => number> = {
  name: (a, b) => a.name.localeCompare(b.name),
  added: (a, b) => b.added_at.localeCompare(a.added_at) || a.name.localeCompare(b.name),
  rating: (a, b) => (b.rating ?? -1) - (a.rating ?? -1) || a.name.localeCompare(b.name),
  year: (a, b) => (b.release_year ?? 0) - (a.release_year ?? 0) || a.name.localeCompare(b.name),
  size: (a, b) => b.size_bytes - a.size_bytes || a.name.localeCompare(b.name),
};
export const sortGames = (games: Game[], key: SortKey) => [...games].sort(compare[key]);

export interface ConsoleEntry { platform: Platform; count: number; /** Hero art of the console's best-rated game, or "". */ art: string }

export interface StoreModel {
  games: Game[];
  platforms: Platform[];
  byId: Map<number, Game>;
  recent?: Row;
  forYou?: Row;
  rated?: Row;
  installed?: Row;
  /** A changing pick of the better-rated games that have hero art, for spotlights and carousels. */
  featured: Game[];
  consoles: ConsoleEntry[];
}

const FEATURED = 12;
// Featured is drawn from this many of the best-rated games (a third of the library, within these bounds).
const POOL_MIN = 24;
const POOL_MAX = 60;

/** The top of a best-first list, shuffled by `seed`: the same seed gives the same picks. */
export function rotate(best: Game[], seed: number): Game[] {
  const pool = best.slice(0, Math.min(POOL_MAX, Math.max(POOL_MIN, Math.ceil(best.length / 3))));
  let a = seed >>> 0;
  const random = () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = Math.imul(a ^ (a >>> 15), a | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 2 ** 32;
  };
  for (let i = pool.length - 1; i > 0; i--) {
    const j = Math.floor(random() * (i + 1));
    [pool[i], pool[j]] = [pool[j], pool[i]];
  }
  return pool;
}

/**
 * `seed` picks which of the better-rated games are featured. `keep` is the featured ids of the model before this
 * one: those stay, in order, so that art arriving for other games does not reshuffle what is on screen.
 */
export function storeModel(games: Game[], platforms: Platform[], recommended: Recommendation[], seed: number, keep: number[] = []): StoreModel {
  const later = laterRows(games);
  const counts = new Map<number, number>();
  for (const g of games) counts.set(g.platform_id, (counts.get(g.platform_id) ?? 0) + 1);
  const rated = topRated(games);
  const withArt = rated.filter((g) => g.art.hero);
  const byId = new Map(games.map((g) => [g.rom_id, g]));
  const kept = keep.map((id) => byId.get(id)).filter((g): g is Game => !!g);
  const drawn = rotate(withArt.length >= 4 ? withArt : rated.length ? rated : games, seed).filter((g) => !keep.includes(g.rom_id));
  return {
    games,
    platforms,
    byId,
    recent: recentRow(games),
    forYou: forYouRow(games, recommended),
    rated: later.find((r) => r.key === "rated"),
    installed: later.find((r) => r.key === "installed"),
    featured: [...kept, ...drawn].slice(0, FEATURED),
    consoles: platforms.filter((p) => counts.get(p.id)).map((p) => ({
      platform: p,
      count: counts.get(p.id) ?? 0,
      art: withArt.find((g) => g.platform_id === p.id)?.art.hero ?? "",
    })),
  };
}

/** Tags for a game the way the store lists them: genres, themes, perspectives, series. */
export function tagsOf(game: Game, details?: GameDetails): string[] {
  const all = details ? [...details.genres, ...details.themes, ...details.perspectives, ...details.franchises] : game.genres;
  return [...new Set(all.filter(Boolean))];
}

export interface Filters { platformId: number; genre: string; installed: boolean }
export const NO_FILTERS: Filters = { platformId: 0, genre: "", installed: false };

export const filtersActive = (f: Filters) => f.platformId !== 0 || f.genre !== "" || f.installed;

const words = (s: string) => s.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, " ").trim().split(" ").filter(Boolean);

export function applyFilters(games: Game[], f: Filters, query: string): Game[] {
  const terms = words(query);
  if (!terms.length && !filtersActive(f)) return games;
  return games.filter((g) => {
    if (f.platformId && g.platform_id !== f.platformId) return false;
    if (f.genre && !g.genres.includes(f.genre)) return false;
    if (f.installed && g.status !== "installed") return false;
    if (!terms.length) return true;
    const name = ` ${words(g.name).join(" ")}`;
    return terms.every((t) => name.includes(t));
  });
}
