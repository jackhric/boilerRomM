// What the UI and Steam's own buttons do to a game: the backend call together with its Steam side.
import { toaster } from "@decky/api";
import { cancelDownload, playTarget, queueDownload, removeGame, State } from "../api";
import { publishDownloads, removeShortcut, runShortcut } from "../steam";
import { prepareShortcut } from "./shortcuts";

/** Queues a download; the Steam shortcut is made first when Steam allows it, and the download goes ahead without. */
export async function download(rom_id: number): Promise<State> {
  const appid = await prepareShortcut(rom_id).catch(() => 0);
  return queueDownload(rom_id, appid).catch((e) => {
    toaster.toast({ title: "Download did not start", body: e instanceof Error ? e.message : String(e) });
    throw e;
  });
}

/** Stops a download; what it fetched stays for Resume. */
export const stopDownload = (rom_id: number) => cancelDownload(rom_id);

/** Deletes the files and the Steam shortcut of a game, in whatever state it is. */
export async function removeFromDevice(rom_id: number): Promise<State> {
  const s = await removeGame(rom_id);
  // The Downloads page reads each item's app overview, so the item must be gone before the shortcut is.
  publishDownloads(s.downloads.items);
  removeShortcut(s.removed);
  return s;
}

export async function play(rom_id: number, name: string) {
  const t = await playTarget(rom_id);
  if (t.blocked) toaster.toast({ title: name, body: t.blocked });
  else if (t.appid) runShortcut(t.appid);
  else toaster.toast({ title: name, body: "No Steam shortcut yet: remove the game and download it again." });
}
