import type { Game } from "../../src/api";

export const game = (over: Partial<Game> = {}): Game => ({
  rom_id: 1, name: "Game", platform_id: 1, platform: "SNES", slug: "snes", size_bytes: 1 << 20, cover: "", cover_large: "", regions: [],
  added_at: "2026-01-01", release_year: 1994, genres: [], rating: null, multi: false, status: "available", sgdb_id: null,
  art: { grid: "", wide: "", hero: "", logo: "", icon: "" }, ...over,
});

/** `n` games rated best first, each with hero art. */
export const rated = (n: number): Game[] => Array.from({ length: n }, (_, i) => game({ rom_id: i + 1, name: `G${i + 1}`, rating: 100 - i, art: { grid: "", wide: "", hero: `hero${i + 1}`, logo: "", icon: "" } }));
