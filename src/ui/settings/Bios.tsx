import { Menu, MenuItem, MenuSeparator, showContextMenu } from "@decky/ui";
import { useEffect, useState } from "react";
import { FaCheck, FaDownload, FaTimes, FaTrash } from "react-icons/fa";
import { biosAvailable, BiosFile, EmulatorInfo, installBios, State, uninstallBios } from "../../api";
import { formatSize } from "../../domain/format";
import { emulatorLogo } from "../emulatorLogos";
import { RowButton, RowControls, SettingsList, SettingsRow } from "../kit/settings";
import { confirm, run } from "./common";

const GOOD = "#59bf40";
const BAD = "#e5484d";
const SYSTEMS: Record<string, string> = { saturn: "Saturn", segacd: "Sega CD", "3do": "3DO" };

function Status({ ok, optional, children }: { ok: boolean; optional?: boolean; children: string }) {
  const Icon = ok ? FaCheck : FaTimes;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      {!optional && <Icon size={12} color={ok ? GOOD : BAD} style={{ flex: "0 0 auto" }} />}
      <span>{children}</span>
    </div>
  );
}

/** One line for an emulator with one system; one a system for RetroArch, where each needs its own. */
function statusLines(e: EmulatorInfo) {
  // Runs without the files: they are for some games only (Cemu and disc images).
  const optional = e.firmware && !e.bios.every((b) => b.ready);
  if (e.bios.length === 1) {
    const installed = e.bios[0].ready && e.firmware_installed;
    return [
      <Status key="one" ok={installed} optional={optional && !installed}>
        {installed ? `Installed: ${e.firmware_label}` : optional ? `Optional: ${e.accepts}` : `Missing BIOS  ·  accepts ${e.accepts}`}
      </Status>,
    ];
  }
  return e.bios.map((b) => (
    <Status key={b.platform} ok={b.ready}>
      {`${SYSTEMS[b.platform] ?? b.platform}: ${b.ready ? `Installed: ${b.found.join(", ")}` : `Missing BIOS  ·  accepts ${e.accepts}`}`}
    </Status>
  ));
}

function openInstallMenu(e: EmulatorInfo, files: BiosFile[], target: HTMLElement) {
  const several = e.bios.length > 1;
  showContextMenu(
    <Menu label={`Install for ${e.name}`}>
      {e.firmware_set && files.length > 1 && <MenuItem onSelected={run(() => installBios(e.id, []))}>Install all {files.length} files</MenuItem>}
      {e.firmware_set && files.length > 1 && <MenuSeparator />}
      {files.map((f) => (
        <MenuItem key={f.id} onSelected={run(() => installBios(e.id, [f.id]))}>
          {several ? `${SYSTEMS[f.platform] ?? f.platform}  ·  ` : ""}{f.name}{f.size ? `  ·  ${formatSize(f.size)}` : ""}{f.recommended ? "  ·  recommended" : ""}
        </MenuItem>
      ))}
    </Menu>,
    target,
  );
}

function Entry({ e, files }: { e: EmulatorInfo; files: BiosFile[] }) {
  const installed = e.bios.every((b) => b.ready) && e.firmware_installed;
  const remove = () => confirm(`Uninstall ${e.name}'s BIOS?`, "The files are removed from this device. They stay on your RomM server.", "Uninstall", run(() => uninstallBios(e.id)));
  const subtitle = (
    <>
      <div>{e.system}</div>
      {statusLines(e)}
    </>
  );
  return (
    <SettingsRow logo={emulatorLogo(e.id)} dimmed={!e.installed} title={e.name} subtitle={subtitle} error={e.busy ? "" : e.error}>
      <RowControls swapKey={installed}>
        {installed
          ? <RowButton icon={<FaTrash />} disabled={!!e.busy} onClick={remove}>{e.busy === "removing" ? "Uninstalling…" : "Uninstall"}</RowButton>
          : <RowButton icon={<FaDownload />} disabled={!files.length || !!e.busy} onClick={(target) => openInstallMenu(e, files, target)}>{e.busy === "fetching" ? "Installing…" : "Install…"}</RowButton>}
      </RowControls>
    </SettingsRow>
  );
}

export function Bios({ state }: { state: State }) {
  const needing = state.emulators.filter((e) => e.bios.length);
  const [files, setFiles] = useState<Record<string, BiosFile[]>>({});
  useEffect(() => {
    let live = true;
    biosAvailable().then((f) => live && setFiles(f)).catch(() => {});
    return () => {
      live = false;
    };
  }, [state.account.paired, state.library.loaded_at]);
  return (
    <SettingsList>
      <div style={{ padding: "0 0 14px", opacity: 0.7, maxWidth: 900 }}>
        Firmwares and BIOS files must be uploaded in their respective console sections within RomM to install them here. If there are no compatible files on the RomM server, the install button will be disabled.
      </div>
      {needing.map((e) => <Entry key={e.id} e={e} files={files[e.id] ?? []} />)}
    </SettingsList>
  );
}
