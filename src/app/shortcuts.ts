// A game's Steam shortcut: made (with its art) before a download starts, and put right when Steam and the install
// ledger disagree.
import { ArtBytes, artBase64, coverBase64, GameArt, gameArt, Install, launchTarget, saveIcon, setShortcut } from "../api";
import { addToCollection, clearDerivedArt, ensureArt, ensureShortcut, hasShortcut, iconPng, setCapsule, setSgdbArt, SGDB_KINDS, SgdbKind, waitForOverview } from "../steam";

const NO_ART: ArtBytes = { base64: "", format: "" };
const HERO = 1;
const WIDE = 3;
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
/** SteamGridDB can be slow; the download must not wait on it for long. */
const within = <T,>(p: Promise<T>, ms: number) => Promise.race([p, sleep(ms).then(() => undefined)]).catch(() => undefined);

/** The SteamGridDB images of a game the backend has; every kind is asked for when its art is not known. */
async function sgdbImages(rom_id: number, art: GameArt | undefined): Promise<Partial<Record<SgdbKind, ArtBytes>>> {
  const kinds = SGDB_KINDS.filter((k) => !art || art[k]);
  const got = await Promise.all(kinds.map((k) => artBase64(rom_id, k).catch(() => NO_ART)));
  return Object.fromEntries(kinds.map((k, i) => [k, got[i]]));
}

/** A Steam shortcut (with art, in the RomM collection) for a game about to download; 0 when Steam says no. */
export async function prepareShortcut(rom_id: number): Promise<number> {
  const t = await launchTarget(rom_id);
  const art = await within(gameArt(rom_id), 5000);
  const cover = await coverBase64(rom_id).catch(() => NO_ART);
  const sgdbIcon = art?.icon ? (await within(artBase64(rom_id, "icon"), 5000)) ?? NO_ART : NO_ART;
  // The icon file must exist before the shortcut does: Steam reads it only into the shortcut's first app overview.
  const png = sgdbIcon.format === "png" && sgdbIcon.base64 ? Promise.resolve(sgdbIcon.base64) : iconPng(t.name, cover);
  const icon = await png.then((b64) => saveIcon(rom_id, b64)).catch(() => "");
  const appid = await ensureShortcut({ ...t, icon });
  if (!appid) return 0;
  if (appid !== t.appid) await setShortcut(rom_id, appid);
  void (async () => {
    if (!(await waitForOverview(appid))) return;
    addToCollection(appid);
    const sgdb = await setSgdbArt(appid, await sgdbImages(rom_id, art));
    const ok = sgdb.has("grid") || (await setCapsule(appid, cover));
    if (ok || sgdb.size) {
      // A gradient from an earlier run must not shadow the real art.
      clearDerivedArt(appid, [...(sgdb.has("hero") ? [] : [HERO]), ...(sgdb.has("wide") ? [] : [WIDE])]);
      await sleep(1500); // Steam writes the grid files after the call returns
    }
    await ensureArt(appid, t.name);
  })();
  return appid;
}

// A game in the queue or installed needs its shortcut (the Downloads page and the library show it through one).
const NEEDS_SHORTCUT = new Set(["queued", "downloading", "paused", "installed"]);
// A new shortcut's overview arrives a moment after it is recorded; only one still missing after this is gone.
const SHORTCUT_SETTLE_MS = 5000;
const MAX_REPAIRS = 2;

export type RepairSteam = {
  /** Undefined until Steam's app list has loaded. */
  hasShortcut(appid: number): boolean | undefined;
  prepare(rom_id: number): Promise<unknown>;
  forget(rom_id: number): Promise<unknown>;
};

/** Brings Steam's shortcuts back in line with the install ledger: recreates a missing one, forgets a stale appid. */
export function shortcutRepair(installs: () => Install[], steam: RepairSteam = { hasShortcut, prepare: prepareShortcut, forget: (rom_id) => setShortcut(rom_id, 0) }) {
  const tries = new Map<number, number>();
  let timer: ReturnType<typeof setTimeout> | undefined;
  let running = false;
  const run = async () => {
    timer = undefined;
    if (running) return;
    running = true;
    try {
      for (const i of installs()) {
        const present = i.appid ? steam.hasShortcut(i.appid) : false;
        if (present !== false || (tries.get(i.rom_id) ?? 0) >= MAX_REPAIRS) continue;
        tries.set(i.rom_id, (tries.get(i.rom_id) ?? 0) + 1);
        if (NEEDS_SHORTCUT.has(i.state)) await steam.prepare(i.rom_id).catch(() => 0);
        else if (i.appid) await steam.forget(i.rom_id).catch(() => undefined);
      }
    } finally {
      running = false;
    }
  };
  return {
    check() {
      if (timer === undefined) timer = setTimeout(() => void run(), SHORTCUT_SETTLE_MS);
    },
    stop() {
      if (timer !== undefined) clearTimeout(timer);
    },
  };
}
