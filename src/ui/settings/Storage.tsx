import { ButtonItem, Menu, MenuItem, showContextMenu, TextField } from "@decky/ui";
import { useEffect, useState } from "react";
import { Game, Install, Progress, setRomsDir, State } from "../../api";
import { download, removeFromDevice, stopDownload } from "../../app/games";
import { formatSize, percent } from "../../domain/format";
import { SettingsSection } from "../../steam";
import { useProgress } from "../../state";
import { RowButton, RowControls, RowMoreButton, SettingsBody, SettingsRow } from "../kit/settings";
import { confirm, run } from "./common";

const byName = (a: Install, b: Install) => a.name.localeCompare(b.name);

function detail(i: Install, game: Game | undefined, p: Progress | undefined): string {
  const total = i.bytes_total || game?.size_bytes || 0;
  const size = total ? formatSize(total) : "";
  let what = size;
  if (i.state === "downloading" && p) {
    what = `${Math.round(percent(p))}%  ·  ${formatSize(p.done_bytes)} of ${formatSize(p.total_bytes)}${p.bps ? `  ·  ${formatSize(p.bps)}/s` : ""}`;
  } else if (i.state === "downloading") what = "Starting…";
  else if (i.state === "queued") what = "Waiting";
  else if (i.state === "paused") what = `Paused  ·  ${formatSize(i.bytes_done)} of ${size}`;
  else if (i.state === "incomplete") what = `${i.bytes_done ? `${formatSize(i.bytes_done)} of ${size}` : "Files missing"}`;
  return [game?.platform, what].filter(Boolean).join("  ·  ");
}

function askRemove(i: Install) {
  confirm(`Remove ${i.name}?`, "Its files and its Steam shortcut are deleted. The game stays on your RomM server.", "Remove", run(() => removeFromDevice(i.rom_id)));
}

function GameRow({ i, game, progress }: { i: Install; game: Game | undefined; progress: Progress | undefined }) {
  const running = i.state === "queued" || i.state === "downloading";
  const done = i.state === "installed";
  const more = (target: HTMLElement) =>
    showContextMenu(<Menu label={i.name}><MenuItem tone="destructive" onSelected={() => askRemove(i)}>Remove from this device</MenuItem></Menu>, target);
  return (
    <SettingsRow logo={game?.cover} title={i.name} subtitle={detail(i, game, progress)} error={i.state === "failed" ? i.error || "Download failed" : ""}>
      <RowControls>
        {done ? (
          <RowButton onClick={() => askRemove(i)}>Remove</RowButton>
        ) : (
          <>
            {running
              ? <RowButton onClick={run(() => stopDownload(i.rom_id))}>Cancel</RowButton>
              : <RowButton disabled={!game} onClick={run(() => download(i.rom_id))}>Resume</RowButton>}
            <RowMoreButton label={`More for ${i.name}`} onClick={more} />
          </>
        )}
      </RowControls>
    </SettingsRow>
  );
}

function Group({ title, installs, state }: { title: string; installs: Install[]; state: State }) {
  const progress = useProgress();
  if (!installs.length) return null;
  return (
    <SettingsSection title={title}>
      {[...installs].sort(byName).map((i) => (
        <GameRow key={i.rom_id} i={i} game={state.library.games.find((g) => g.rom_id === i.rom_id)} progress={progress[i.rom_id]} />
      ))}
    </SettingsSection>
  );
}

function Folder({ state }: { state: State }) {
  const current = state.downloads.roms_dir;
  const [dir, setDir] = useState(current);
  useEffect(() => setDir(current), [current]);
  const { used_bytes, free_bytes, total_bytes } = state.storage;
  return (
    <SettingsSection title="This device">
      <TextField
        label="ROM folder"
        value={dir}
        spellCheck={false}
        onChange={(e) => setDir(e.target.value)}
        description={state.roms_dir_exists ? "One subfolder per system." : "This folder is made when the first game downloads."}
      />
      {dir.trim() !== current && <ButtonItem layout="below" onClick={run(() => setRomsDir(dir))}>Save folder</ButtonItem>}
      <SettingsRow title="Games on this device" subtitle={used_bytes ? formatSize(used_bytes) : "Nothing yet"} />
      <SettingsRow title="Free space" subtitle={total_bytes ? `${formatSize(free_bytes)} free of ${formatSize(total_bytes)}` : "Unknown"} />
    </SettingsSection>
  );
}

export function Storage({ state }: { state: State }) {
  const of = (...states: Install["state"][]) => state.installs.filter((i) => states.includes(i.state));
  return (
    <SettingsBody>
      <Folder state={state} />
      <Group title="Downloading" installs={of("queued", "downloading", "paused")} state={state} />
      <Group title="Incomplete" installs={of("incomplete", "failed")} state={state} />
      <Group title="Installed" installs={of("installed")} state={state} />
      {!state.installs.length && (
        <SettingsSection title="Games">
          <SettingsRow title="No games on this device" />
        </SettingsSection>
      )}
    </SettingsBody>
  );
}
