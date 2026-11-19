// Connects the backend to Steam for as long as the plugin is loaded.
import { downloadControl, getState, launchTarget, onProgress, onState, State } from "../api";
import { ensureArt, ensureShortcut, installSteam, launchIfRequested, publishDownloads, steamDiagnostics, steamProgress, syncSteam, toastOutcome } from "../steam";
import { download, removeFromDevice } from "./games";
import { shortcutRepair } from "./shortcuts";

/** `onState` sees each new state together with the one before it. Returns what undoes everything. */
export function start(onStateChange: (next: State, previous: State | undefined) => void): () => void {
  let latest: State | undefined;
  const stopSteam = installSteam({
    control: (action, appid, value) => downloadControl(action, appid, value),
    uninstall: (rom_id) => removeFromDevice(rom_id),
  });
  const repair = shortcutRepair(() => latest?.installs ?? []);
  const follow = (s: State) => {
    latest = s;
    syncSteam({ downloads: s.downloads.items, installs: s.installs ?? [], installed: s.installed ?? [] });
    repair.check();
  };
  const offState = onState((s) => {
    onStateChange(s, latest);
    follow(s);
  });
  const offProgress = onProgress((p) => {
    steamProgress(p);
    toastOutcome(p, latest?.library.games.find((g) => g.rom_id === p.rom_id)?.name ?? "ChickenTender");
    // A multi-file game's launch file is only known once it is on disk.
    if (p.status === "done" && p.appid) {
      void launchTarget(p.rom_id)
        .then(ensureShortcut)
        .finally(() => launchIfRequested(p.appid));
    }
  });
  getState()
    .then((s) => {
      follow(s);
      // The Downloads rows show the wide art, which the previous instance's undo cleared.
      for (const d of s.downloads.items) if (d.appid) ensureArt(d.appid, d.name);
    })
    .catch(() => {});
  // Test hook for the Decky Toolkit (cef_evaluate): the same calls the UI makes.
  // publish feeds the Downloads page a made-up list (e.g. a download held at 40%) until the next backend event.
  (window as any).__chickenTender = { download, remove: removeFromDevice, getState, publish: publishDownloads, steam: steamDiagnostics };
  return () => {
    delete (window as any).__chickenTender;
    repair.stop();
    stopSteam();
    offState();
    offProgress();
  };
}
