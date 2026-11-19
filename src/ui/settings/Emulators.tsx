import { ConfirmModal, Dropdown, Menu, MenuItem, MenuSeparator, showContextMenu, showModal } from "@decky/ui";
import { useEffect, useState } from "react";
import { FaDownload } from "react-icons/fa";
import { EmulatorInfo, EmulatorVersion, emulatorVersions, installEmulator, resetEmulator, State, uninstallEmulator } from "../../api";
import { emulatorLogo } from "../emulatorLogos";
import { RowButton, RowControls, RowFill, RowMoreButton, SettingsList, SettingsRow } from "../kit/settings";

const BUSY_TEXT: Record<Exclude<EmulatorInfo["busy"], "">, string> = { queued: "Waiting to install…", installing: "Installing…", uninstalling: "Uninstalling…", resetting: "Resetting…", fetching: "Getting BIOS…" };

/** The line under the name: what it emulates, then where it stands. */
function subtitle(e: EmulatorInfo): string {
  const state = e.busy ? BUSY_TEXT[e.busy] : !e.installed ? "Not installed" : e.firmware ? e.version_name : `${e.version_name}  ·  needs ${e.requires}`;
  return [e.system, state].filter(Boolean).join("  ·  ");
}

const run = (call: () => Promise<unknown>) => () => void call().catch(() => {});

function confirmReset(e: EmulatorInfo) {
  showModal(
    <ConfirmModal
      strTitle={`Reset ${e.name}?`}
      strDescription={`${e.name}'s settings go back to boilerRomM's defaults. Saves, save states and BIOS files are kept.`}
      strOKButtonText="Reset"
      onOK={run(() => resetEmulator(e.id))}
    />,
  );
}

const versionLabel = (v: EmulatorVersion) => `${v.name || v.tag}${v.tested ? "  ·  recommended" : v.prerelease ? "  ·  pre-release" : ""}`;

/** The builds on offer; until the project answers (or if it does not), the installed build only. */
function useVersions(e: EmulatorInfo): EmulatorVersion[] {
  const [listed, setListed] = useState<EmulatorVersion[]>([]);
  useEffect(() => {
    let live = true;
    emulatorVersions(e.id).then((v) => live && setListed(v)).catch(() => {});
    return () => {
      live = false;
    };
  }, [e.id]);
  if (!e.version || listed.some((v) => v.tag === e.version)) return listed;
  return [{ tag: e.version, name: e.version_name, prerelease: false, published: "", tested: false }, ...listed];
}

/** Everything but choosing and installing a build; new per-emulator settings go here. */
function showMore(e: EmulatorInfo, target: HTMLElement) {
  showContextMenu(
    <Menu label={e.name}>
      <MenuItem disabled={!e.configured} onSelected={() => confirmReset(e)}>Reset</MenuItem>
      <MenuItem onSelected={run(() => installEmulator(e.id, e.version))}>Reinstall</MenuItem>
      <MenuSeparator />
      <MenuItem tone="destructive" onSelected={run(() => uninstallEmulator(e.id))}>Uninstall</MenuItem>
    </Menu>,
    target,
  );
}

/** Asks which build to install, the recommended one first. Without a list (offline, or GitHub said no) it installs that one. */
function chooseInstall(e: EmulatorInfo, versions: EmulatorVersion[], target: HTMLElement) {
  if (!versions.length) return run(() => installEmulator(e.id))();
  showContextMenu(
    <Menu label={`Install ${e.name}`}>
      {versions.map((v) => <MenuItem key={v.tag} onSelected={run(() => installEmulator(e.id, v.tag))}>{versionLabel(v)}</MenuItem>)}
    </Menu>,
    target,
  );
}

function Actions({ e }: { e: EmulatorInfo }) {
  const versions = useVersions(e);
  const busy = !!e.busy;
  if (!e.installed) {
    return (
      <RowControls swapKey={e.installed}>
        <RowButton icon={<FaDownload />} disabled={busy} onClick={(target) => chooseInstall(e, versions, target)}>Install</RowButton>
      </RowControls>
    );
  }
  return (
    <RowControls swapKey={e.installed}>
      <RowFill>
        <Dropdown
          menuLabel={`${e.name} version`}
          disabled={busy}
          rgOptions={versions.map((v) => ({ data: v.tag, label: versionLabel(v) }))}
          selectedOption={e.version}
          // The closed control shows the bare version; what kind of build it is only matters while choosing.
          renderButtonValue={() => e.version_name}
          onChange={(o) => o.data !== e.version && run(() => installEmulator(e.id, o.data))()}
        />
      </RowFill>
      <RowMoreButton label={`More for ${e.name}`} disabled={busy} onClick={(target) => showMore(e, target)} />
    </RowControls>
  );
}

export function Emulators({ state }: { state: State }) {
  return (
    <SettingsList>
      {state.emulators.map((e) => (
        <SettingsRow key={e.id} logo={emulatorLogo(e.id)} dimmed={!e.installed} title={e.name} subtitle={subtitle(e)} error={e.error}>
          <Actions e={e} />
        </SettingsRow>
      ))}
    </SettingsList>
  );
}
