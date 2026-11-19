import { describe, expect, it } from "vitest";
import { applyFilters, forYouRow, NO_FILTERS, rotate, sortGames, storeModel, tagsOf } from "../../src/domain/catalog";
import { formatAgo, formatDate, formatHours, formatSize, percent, scoreWord } from "../../src/domain/format";
import { ACTION_LABELS, actionKind, canRemove, statusText } from "../../src/domain/status";
import { describeProblem } from "../../src/domain/problem";
import { game, rated } from "./fixtures";

describe("status", () => {
  it("gives every state one action and says whether there is something to remove", () => {
    const of = (status: any) => game({ status });
    const table = ["available", "queued", "downloading", "paused", "incomplete", "failed", "installed"].map((s) => [s, ACTION_LABELS[actionKind(of(s))], canRemove(of(s))]);
    expect(table).toEqual([
      ["available", "Download", false],
      ["queued", "Stop download", false],
      ["downloading", "Stop download", false],
      ["paused", "Resume", true],
      ["incomplete", "Resume", true],
      ["failed", "Resume", true],
      ["installed", "Play", true],
    ]);
  });

  it("words a state the same wherever it is shown", () => {
    expect(statusText(game({ status: "installed" }))).toBe("On this Device");
    expect(statusText(game({ status: "paused" }))).toBe("Paused");
    expect(statusText(game({ status: "failed" }))).toBe("Download failed");
    expect(statusText(game({ status: "available", size_bytes: 3 * 2 ** 30 }))).toBe("3.0 GB");
    const p = { rom_id: 1, appid: 0, done_bytes: 2 ** 30, total_bytes: 4 * 2 ** 30, bps: 12 * 2 ** 20, status: "downloading" as const, error: "" };
    expect(statusText(game({ status: "downloading" }), p)).toBe("25% · 1.0 GB of 4.0 GB · 12 MB/s");
  });
});

describe("format", () => {
  it("sizes, dates, hours, scores and progress", () => {
    expect([formatSize(500), formatSize(5 << 20), formatSize(1.5 * (1 << 30))]).toEqual(["1 KB", "5 MB", "1.5 GB"]);
    expect([0, 990, 700, 7300, 2 * 86400].map((t) => formatAgo(t, 1000))).toEqual(["never", "just now", "5 minutes ago", "just now", "just now"]);
    expect([formatAgo(1000, 1060), formatAgo(1000, 4600), formatAgo(1000, 1000 + 2 * 86400)]).toEqual(["1 minute ago", "1 hour ago", "2 days ago"]);
    expect([formatDate("1998-06-29"), formatDate("")]).toEqual(["Jun 29, 1998", ""]);
    expect([formatHours(36000), formatHours(7.25), formatHours(0)]).toEqual(["10 hours", "7.3 hours", ""]);
    expect([scoreWord(96), scoreWord(80), scoreWord(10)]).toEqual(["Overwhelmingly Positive", "Very Positive", "Mostly Negative"]);
    expect([percent(), percent({ done_bytes: 1, total_bytes: 0 } as any), percent({ done_bytes: 1, total_bytes: 4 } as any)]).toEqual([0, 0, 25]);
  });
});

describe("catalog", () => {
  it("filters by console, genre, installed and every word of the search", () => {
    const games = [
      game({ rom_id: 1, name: "Super Mario World", platform_id: 1, genres: ["Platform"], status: "installed" }),
      game({ rom_id: 2, name: "Super Metroid", platform_id: 1, genres: ["Adventure"] }),
      game({ rom_id: 3, name: "Mario Kart 64", platform_id: 2, genres: ["Racing"] }),
    ];
    const ids = (f = NO_FILTERS, q = "") => applyFilters(games, f, q).map((g) => g.rom_id);
    expect(applyFilters(games, NO_FILTERS, "")).toBe(games);
    expect(ids(NO_FILTERS, "mario")).toEqual([1, 3]);
    expect(ids(NO_FILTERS, "MARIO  super!")).toEqual([1]);
    expect(ids({ ...NO_FILTERS, platformId: 1 })).toEqual([1, 2]);
    expect(ids({ ...NO_FILTERS, genre: "Racing" })).toEqual([3]);
    expect(ids({ ...NO_FILTERS, installed: true }, "mario")).toEqual([1]);
  });

  it("sorts without touching the list it was given", () => {
    const games = [game({ rom_id: 1, name: "B", rating: 50 }), game({ rom_id: 2, name: "A", rating: 90 }), game({ rom_id: 3, name: "C" })];
    expect(sortGames(games, "name").map((g) => g.name)).toEqual(["A", "B", "C"]);
    expect(sortGames(games, "rating").map((g) => g.rom_id)).toEqual([2, 1, 3]);
    expect(games.map((g) => g.rom_id)).toEqual([1, 2, 3]);
  });

  it("rotates featured picks within the better-rated games: same seed same picks, another seed others", () => {
    const best = rated(180);
    const a = rotate(best, 1).map((g) => g.rom_id);
    expect(rotate(best, 1).map((g) => g.rom_id)).toEqual(a);
    expect(rotate(best, 2).map((g) => g.rom_id)).not.toEqual(a);
    expect(a).toHaveLength(60);
    expect(Math.max(...a)).toBeLessThanOrEqual(60);
    expect(rotate(rated(10), 1)).toHaveLength(10);
    expect(best.map((g) => g.rom_id).slice(0, 3)).toEqual([1, 2, 3]);
  });

  it("builds the store from the library: featured from the pool, rows only when they have games", () => {
    const games = rated(90);
    const m = storeModel(games, [{ id: 1, name: "SNES", slug: "snes", rom_count: 90, logo: "" }], [], 7);
    expect(m.featured).toHaveLength(12);
    expect(m.featured.every((g) => g.rom_id <= 30)).toBe(true);
    expect([m.forYou, m.installed]).toEqual([undefined, undefined]);
    expect(m.consoles).toEqual([{ platform: expect.objectContaining({ id: 1 }), count: 90, art: "hero1" }]);
    expect(storeModel([], [], [], 7).featured).toEqual([]);
  });

  it("shows one copy of a game on a shelf however many the library holds", () => {
    const copies = rated(40).map((g, i) => (i < 6 ? { ...g, name: "Castlevania" } : g));
    const m = storeModel(copies, [], [], 7);
    for (const shelf of [m.featured, m.rated!.games, m.recent!.games]) {
      const names = shelf.map((g) => g.name);
      expect(new Set(names).size).toBe(names.length);
    }
    expect(m.games).toHaveLength(40);
  });

  it("keeps the featured picks it is given when art arrives for other games", () => {
    const all = rated(90);
    const few = all.map((g, i) => (i < 40 ? g : { ...g, art: { ...g.art, hero: "" } }));
    const before = storeModel(few, [], [], 7).featured.map((g) => g.rom_id);
    expect(storeModel(all, [], [], 7, before).featured.map((g) => g.rom_id)).toEqual(before);
    const gone = storeModel(all.filter((g) => g.rom_id !== before[0]), [], [], 7, before).featured.map((g) => g.rom_id);
    expect(gone.slice(0, 11)).toEqual(before.slice(1));
    expect(new Set(gone).size).toBe(12);
  });

  it("turns RomM's recommendations into a row, skipping games the library no longer has", () => {
    const games = [game({ rom_id: 1, name: "A" }), game({ rom_id: 2, name: "B" })];
    const recs = [
      { rom_id: 9, score: 1, reasons: [] },
      { rom_id: 2, score: 0.5, reasons: ["genre: Platform"], seed_rom_name: "Super Mario World" },
      { rom_id: 1, score: 0.4, reasons: ["franchise: Zelda"], seed_rom_name: "Super Mario World" },
    ];
    const row = forYouRow(games, recs)!;
    expect(row.games.map((g) => g.rom_id)).toEqual([2, 1]);
    expect(row.subtitle).toBe("Because you played Super Mario World");
    expect(row.notes).toEqual({ 1: "Franchise: Zelda", 2: "Genre: Platform" });
    expect(forYouRow(games, [])).toBeUndefined();
  });

  it("lists a game's tags once each", () => {
    const details: any = { genres: ["Platform"], themes: ["Action", ""], perspectives: ["Side view"], franchises: ["Platform"] };
    expect(tagsOf(game({ genres: ["Platform"] }), details)).toEqual(["Platform", "Action", "Side view"]);
    expect(tagsOf(game({ genres: ["Racing"] }))).toEqual(["Racing"]);
  });
});

describe("describeProblem", () => {
  const kind = (raw: string) => describeProblem(raw).kind;

  it("says the server cannot be reached for network failures", () => {
    for (const raw of [
      "Cannot connect to host roms.example.com:443 ssl:default [Temporary failure in name resolution]",
      "Cannot reach https://romm.local: Connection refused",
      "Nothing answered at romm.local",
      "TimeoutError",
      "Timeout on reading data from socket",
    ]) expect(kind(raw)).toBe("unreachable");
    expect(describeProblem("TimeoutError").title).toBe("Can't reach your RomM server");
  });

  it("says the device is signed out for 401 and 403", () => {
    expect(kind("401 Unauthorized")).toBe("signed-out");
    expect(kind("403 Forbidden")).toBe("signed-out");
    expect(kind("RomM no longer accepts this device; disconnect and pair again")).toBe("signed-out");
  });

  it("says the server had a problem for 5xx", () => {
    expect(kind("502 Bad Gateway")).toBe("server");
    expect(kind("HTTP 500")).toBe("server");
  });

  it("falls back to a generic title, and keeps the raw text as the detail", () => {
    const p = describeProblem("  KeyError: 'id'  ");
    expect(p).toEqual({ kind: "other", title: "Something went wrong", detail: "KeyError: 'id'" });
    expect(describeProblem(undefined).detail).toBe("");
  });

  it("does not mistake a number inside a longer one for a status", () => {
    expect(kind("failed after 4031 bytes")).toBe("other");
  });
});
