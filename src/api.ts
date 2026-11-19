// The only file that knows the backend's method and event names.
import { addEventListener, callable, removeEventListener } from "@decky/api";

/** The install ledger's state for a game (py_modules/boilerromm/ledger.py); "available" has no record. */
export type GameStatus = "available" | "queued" | "downloading" | "paused" | "incomplete" | "failed" | "installed";

export interface Game {
  rom_id: number;
  name: string;
  platform_id: number;
  platform: string;
  slug: string;
  size_bytes: number;
  cover: string;
  cover_large: string;
  regions: string[];
  /** ISO time the game was added to RomM. */
  added_at: string;
  release_year: number | null;
  genres: string[];
  /** 0-100, from RomM's metadata, or null. */
  rating: number | null;
  multi: boolean;
  status: GameStatus;
  sgdb_id: number | null;
  /** SteamGridDB CDN URLs, "" while unknown or when SteamGridDB has none; filled in by later state events. */
  art: GameArtUrls;
}

export type ArtKind = "grid" | "wide" | "hero" | "logo" | "icon";
export type GameArtUrls = Record<ArtKind, string>;
export interface GameArt extends GameArtUrls { rom_id: number; sgdb_id: number | null; ready: boolean }
/** One artwork file read by the backend (the webview cannot fetch the CDN cross-origin); base64 "" when there is none. */
export interface ArtBytes { base64: string; format: "png" | "jpg" | "webp" | "" }

/** The long fields of one game, fetched on demand. */
export interface GameDetails {
  rom_id: number;
  summary: string;
  screenshots: string[];
  youtube_video_id: string;
  developers: string[];
  publishers: string[];
  game_modes: string[];
  player_count: string;
  franchises: string[];
  fs_name: string;
  /** A video file RomM hosts for the game, or "". */
  video: string;
  /** ISO date (YYYY-MM-DD) or "". */
  released: string;
  genres: string[];
  themes: string[];
  perspectives: string[];
  /** IGDB's 0-100 scores, null when RomM has none. */
  user_score: number | null;
  user_score_count: number;
  critic_score: number | null;
  age_ratings: { rating: string; category: string; cover: string }[];
  hltb: { main_story?: number; main_plus_extra?: number; completionist?: number };
  /** Number of RetroAchievements. */
  achievements: number;
  last_played: string;
}

export interface Platform { id: number; name: string; slug: string; rom_count: number; /** IGDB platform logo URL, or "" */ logo: string }

/** One entry of RomM's personalised feed (or of "similar games"), for a game that is in the library. */
export interface Recommendation {
  rom_id: number;
  score: number;
  /** Human-readable reasons such as "genre: Platform" or "franchise: Zelda". */
  reasons: string[];
  seed_rom_id?: number | null;
  /** The played game this recommendation stems from, when RomM says so. */
  seed_rom_name?: string;
}

export interface Progress {
  rom_id: number;
  appid: number;
  done_bytes: number;
  total_bytes: number;
  bps: number;
  status: "queued" | "downloading" | "done" | "failed" | "cancelled";
  error: string;
}

/** One download as Steam's Downloads page sees it (src/steam/inject.ts OurDownload plus the game). */
export interface DownloadItem {
  appid: number;
  rom_id: number;
  name: string;
  bytes_total: number;
  bytes_done: number;
  rate: number;
  eta: number;
  state: "downloading" | "paused" | "queued" | "done";
  queue_index: number;
  completed_at: number;
  started_at: number;
}

export type SgdbSigninStage = "" | "opening" | "login" | "consent" | "reading" | "verifying" | "done" | "failed";
/** "Sign in with Steam": the backend follows Steam's browser to SteamGridDB; `error` is set on "failed". */
export interface SgdbSignin { active: boolean; stage: SgdbSigninStage; error: string }

/** A finished game that has a Steam shortcut, as Steam's storage pages need it. */
export interface InstalledGame { rom_id: number; appid: number; name: string; path: string; folder: string; bytes: number; device: number }

/** One record of the install ledger, held against the disk. */
export interface Install {
  rom_id: number;
  name: string;
  state: Exclude<GameStatus, "available">;
  /** The Steam shortcut the backend has on record, 0 for none. */
  appid: number;
  bytes_done: number;
  bytes_total: number;
  /** Listed files that are absent or short. */
  missing: string[];
  error: string;
  queued_at: number;
  updated_at: number;
  completed_at: number;
}

export interface BiosFolder {
  platform: string;
  folder: string;
  /** Names of the recognised files in the folder. */
  found: string[];
  ready: boolean;
  /** The files to put on the RomM server for it, as they are usually named. */
  expects: string;
}

/** The outcome of asking the RomM server now. */
export interface ConnectionCheck {
  reachable: boolean;
  version: string;
  supported: boolean;
  signed_in: boolean;
  username: string;
  /** Round trip of the version request. */
  ms: number;
  error: string;
}

/** An emulator boilerRomM installs and runs itself (py_modules/boilerromm/emulators). */
export interface EmulatorInfo {
  id: string;
  name: string;
  /** What it emulates, e.g. "PlayStation 2". */
  system: string;
  platforms: string[];
  installed: boolean;
  /** The installed build's release tag; "" when not installed. */
  version: string;
  /** What to call that build: the tag, or the release's own name where the tag is only a commit. */
  version_name: string;
  /** Whether what it needs from the user is in place. */
  firmware: boolean;
  /** What that is, as it reads after "needs": "a BIOS", "firmware", "keys". */
  requires: string;
  ready: boolean;
  /** Whether it has settings on the device that Reset would replace. */
  configured: boolean;
  /** One entry per platform whose folder the user fills with firmware or keys; empty when it needs none. */
  bios: BiosFolder[];
  /** "queued" is waiting its turn behind another install. */
  /** The firmware is where the emulator uses it (RPCS3 unpacks its own; for the rest, the files being there). */
  firmware_installed: boolean;
  /** What is installed, e.g. "ps2-0230a-20080220.bin"; "" when nothing is. */
  firmware_label: string;
  /** The kind of firmware file it takes, e.g. ".bin". */
  accepts: string;
  /** It takes a set of files, not one. */
  firmware_set: boolean;
  year: number;
  busy: "" | "queued" | "installing" | "firmware" | "uninstalling" | "resetting" | "fetching" | "removing";
  error: string;
  /** Bytes of the download in flight and its size (0 when the host does not say); null when nothing is downloading. */
  progress: [done: number, total: number] | null;
}

export interface State {
  server: { url: string; version: string; error: string };
  pairing: { status: "idle" | "waiting" | "approved" | "expired" | "denied" | "error"; user_code?: string; verification_url?: string; expires_at?: number; error?: string };
  account: { paired: boolean; username: string; device_id: string; device_name: string };
  library: { platforms: Platform[]; games: Game[]; recommended: Recommendation[]; loaded_at: number; loading: boolean; error: string };
  downloads: { active: Progress | null; queue: number[]; items: DownloadItem[]; roms_dir: string };
  installs: Install[];
  installed: InstalledGame[];
  roms_dir_exists: boolean;
  /** Bytes the installed games take, and the free and total bytes of the drive the ROM folder is on. */
  storage: { used_bytes: number; free_bytes: number; total_bytes: number };
  emulators: EmulatorInfo[];
  /** Whether first-run setup has been finished on this device. */
  setup_done: boolean;
  sgdb: { configured: boolean; error: string; art_ready: number; art_total: number; signin: SgdbSignin };
  version: string;
}

export const getState = callable<[], State>("get_state");
export const setServer = callable<[url: string], State>("set_server");
export const checkConnection = callable<[], ConnectionCheck>("check_connection");
export const startPairing = callable<[], State>("start_pairing");
export const disconnect = callable<[], State>("disconnect");
export const resetEverything = callable<[], State>("reset");
export const refreshLibrary = callable<[], State>("refresh_library");
export const gameDetails = callable<[rom_id: number], GameDetails>("game_details");
export const similarGames = callable<[rom_id: number], Recommendation[]>("similar_games");
export const cancelDownload = callable<[rom_id: number], State>("cancel_download");
export const downloadControl = callable<[action: string, appid: number, value: number], State>("download_control");
export const launchTarget = callable<[rom_id: number], LaunchTarget>("launch_target");
/** `launchTarget` for a game about to be started: missing firmware is fetched from RomM first. */
export const playTarget = callable<[rom_id: number], LaunchTarget>("play_target");
export const coverBase64 = callable<[rom_id: number], { base64: string; format: string }>("cover_base64");
/** Writes a shortcut icon (base64 PNG) to the plugin's runtime dir and returns its path. */
export const saveIcon = callable<[rom_id: number, base64: string], string>("save_icon");
/** An invalid key leaves `sgdb.configured` false with `sgdb.error` set; it does not throw. */
export const setSgdbKey = callable<[key: string], State>("set_sgdb_key");
/** Follows the page opened in Steam's browser (SGDB_SIGN_IN) until the key is saved or it fails. */
export const startSgdbSignin = callable<[], State>("start_sgdb_signin");
export const cancelSgdbSignin = callable<[], State>("cancel_sgdb_signin");
/** Steam's own sign-in page for SteamGridDB, which returns to SteamGridDB signed in. Same as OPENID_URL in signin.py. */
export const SGDB_SIGN_IN =
  "https://steamcommunity.com/openid/login?openid.ns=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0" +
  "&openid.mode=checkid_setup" +
  "&openid.identity=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select" +
  "&openid.claimed_id=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select" +
  "&openid.realm=https%3A%2F%2Fwww.steamgriddb.com" +
  "&openid.return_to=https%3A%2F%2Fwww.steamgriddb.com%2Flogin%2Fsteam";
/** Fetches the game's SteamGridDB art now when it is not cached yet. */
export const gameArt = callable<[rom_id: number], GameArt>("game_art");
export const artBase64 = callable<[rom_id: number, kind: ArtKind], ArtBytes>("art_base64");
export const setShortcut = callable<[rom_id: number, appid: number], State>("set_shortcut");
export const removeGame = callable<[rom_id: number], State & { removed: number }>("remove");
/** Queues a download for a game whose Steam shortcut is `appid` (0 for none). */
export const queueDownload = callable<[rom_id: number, appid: number], State>("download");

export interface LaunchTarget { rom_id: number; name: string; appid: number; exe: string; start_dir: string; launch_options: string; cover: string; installed: boolean; /** Why the game cannot start; "" when it can. */ blocked: string }

/** Direct stream addresses for the game's trailer at about 360p and 720p (both silent) and its sound; "" when not resolved. */
export const gameVideo = callable<[rom_id: number], { rom_id: number; small: string; large: string; audio: string }>("game_video");
/** A build of an emulator that can be installed. */
export interface EmulatorVersion { tag: string; /** What to call it, when that is not the tag. */ name?: string; prerelease: boolean; published: string; /** The build boilerRomM is tested with. */ tested: boolean }
export const emulatorVersions = callable<[id: string], EmulatorVersion[]>("emulator_versions");
/** Installs a build, replacing the one installed; without a tag, the tested build. */
export const installEmulator = callable<[id: string, tag?: string], State>("emulator_install");
/** Installs every emulator that is not installed, in the background; each row reports its own outcome. */
export const installAllEmulators = callable<[], State>("emulators_install_all");
export const finishSetup = callable<[], State>("finish_setup");
/** Removes the build and keeps the settings. */
export const uninstallEmulator = callable<[id: string], State>("emulator_uninstall");
/** Replaces the emulator's settings with boilerRomM's defaults. Saves, states and firmware stay. */
export const resetEmulator = callable<[id: string], State>("emulator_reset");
/** Downloads the firmware RomM holds for the emulator's platforms; only files the emulator recognises are kept. */
/** Looks at the BIOS folders again and sends the state. */
/** A firmware file on the RomM server that an emulator could install. */
export interface BiosFile { id: number; name: string; size: number; platform: string; recommended: boolean }
/** By emulator id; an emulator with no compatible file on the server has an empty list. */
export const biosAvailable = callable<[], Record<string, BiosFile[]>>("bios_available");
/** No ids: the recommended file, or the whole set for an emulator that takes one. */
export const installBios = callable<[id: string, firmware_ids: number[]], State>("emulator_bios_install");
export const uninstallBios = callable<[id: string], State>("emulator_bios_uninstall");
export const setRomsDir = callable<[path: string], State>("set_roms_dir");

const STATE_EVENT = "boilerromm_state";
const PROGRESS_EVENT = "boilerromm_progress";

export function onState(listener: (state: State) => void): () => void {
  addEventListener<[State]>(STATE_EVENT, listener);
  return () => removeEventListener(STATE_EVENT, listener);
}

export function onProgress(listener: (p: Progress) => void): () => void {
  addEventListener<[Progress]>(PROGRESS_EVENT, listener);
  return () => removeEventListener(PROGRESS_EVENT, listener);
}
