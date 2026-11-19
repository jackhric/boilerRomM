import { biosFromRomm, BiosFolder, EmulatorInfo, rescanBios, State } from "../../api";
import { emulatorLogo } from "../emulatorLogos";
import { RowButton, RowControls, SettingsList, SettingsRow } from "../kit/settings";
import { run } from "./common";

function line(b: BiosFolder, several: boolean) {
  const what = b.ready ? (b.found.length ? `Found ${b.found.join(", ")}` : "Installed") : "Not found";
  return `${several ? `${b.platform}: ` : ""}${what}  ·  ${b.folder}`;
}

function Entry({ e, canFetch }: { e: EmulatorInfo; canFetch: boolean }) {
  const subtitle = (
    <>
      {/* Ready without its files: they are for some games only (Cemu and disc images). */}
      <div>{e.firmware && !e.bios.every((b) => b.ready) ? "Optional: " : "Needs "}{e.requires}</div>
      {e.bios.map((b) => <div key={b.platform}>{line(b, e.bios.length > 1)}</div>)}
    </>
  );
  return (
    <SettingsRow logo={emulatorLogo(e.id)} dimmed={!e.installed} title={e.name} subtitle={subtitle} error={e.busy ? "" : e.error}>
      <RowControls>
        <RowButton disabled={!canFetch || !!e.busy} onClick={run(() => biosFromRomm(e.id))}>{e.busy === "fetching" ? "Getting…" : "Get from RomM"}</RowButton>
      </RowControls>
    </SettingsRow>
  );
}

export function Bios({ state }: { state: State }) {
  const needing = state.emulators.filter((e) => e.bios.length);
  return (
    <SettingsList>
      <SettingsRow title="BIOS files" subtitle="Copy files into the folders below, or get them from RomM. Files are recognised by what is in them, not by name.">
        <RowControls>
          <RowButton onClick={run(rescanBios)}>Check again</RowButton>
        </RowControls>
      </SettingsRow>
      {needing.map((e) => <Entry key={e.id} e={e} canFetch={state.account.paired} />)}
    </SettingsList>
  );
}
