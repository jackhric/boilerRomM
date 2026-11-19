import { Navigation } from "@decky/ui";
import { useState } from "react";
import { cancelSgdbSignin, checkConnection, ConnectionCheck, disconnect, refreshLibrary, SGDB_SIGN_IN, startSgdbSignin, State } from "../../api";
import { formatAgo } from "../../domain/format";
import { SettingsSection } from "../../steam";
import { RowButton, RowControls, SettingsBody, SettingsRow } from "../kit/settings";
import { confirm, run } from "./common";

const host = (url: string) => url.replace(/^https?:\/\//, "");

function Check({ result }: { result: ConnectionCheck }) {
  const server = result.reachable ? `Answered in ${result.ms} ms` : result.error;
  const version = !result.reachable ? "" : result.supported ? `RomM ${result.version}` : result.error;
  const signin = !result.reachable ? "" : result.signed_in ? `Signed in as ${result.username || "this device"}` : result.error || "Not signed in";
  return (
    <>
      <SettingsRow title="Server" subtitle={server} />
      {result.reachable && <SettingsRow title="Version" subtitle={version} />}
      {result.reachable && <SettingsRow title="Sign-in" subtitle={signin} />}
    </>
  );
}

function Connection({ state }: { state: State }) {
  const { server, account, library } = state;
  const [checking, setChecking] = useState(false);
  const [result, setResult] = useState<ConnectionCheck>();
  const check = () => {
    setChecking(true);
    checkConnection().then(setResult).catch(() => setResult(undefined)).finally(() => setChecking(false));
  };
  const who = account.paired ? `Signed in as ${account.username || "this device"}` : "Not signed in";
  return (
    <SettingsSection title="RomM">
      <SettingsRow title={host(server.url) || "No server"} subtitle={[server.version && `RomM ${server.version}`, who].filter(Boolean).join("  ·  ")} error={server.error}>
        <RowControls>
          <RowButton disabled={checking || !server.url} onClick={check}>{checking ? "Checking…" : "Check connection"}</RowButton>
        </RowControls>
      </SettingsRow>
      {result && <Check result={result} />}
      <SettingsRow title="This device" subtitle={account.device_name} />
      <SettingsRow
        title="Library"
        subtitle={library.loading ? "Loading…" : `${library.games.length.toLocaleString()} games on ${library.platforms.length} platforms  ·  loaded ${formatAgo(library.loaded_at, Date.now() / 1000)}`}
        error={library.error}
      >
        <RowControls>
          <RowButton disabled={library.loading || !account.paired} onClick={run(refreshLibrary)}>Refresh library</RowButton>
        </RowControls>
      </SettingsRow>
    </SettingsSection>
  );
}

function Artwork({ state }: { state: State }) {
  const { sgdb } = state;
  const signingIn = sgdb.signin.active;
  const signIn = () => {
    Navigation.NavigateToExternalWeb(SGDB_SIGN_IN);
    startSgdbSignin().catch(() => {});
  };
  const subtitle = signingIn
    ? "Signing in…"
    : !sgdb.configured ? "Not connected" : sgdb.art_total ? `Connected  ·  artwork for ${sgdb.art_ready} of ${sgdb.art_total} games` : "Connected";
  const error = sgdb.signin.stage === "failed" ? sgdb.signin.error : sgdb.error;
  return (
    <SettingsSection title="SteamGridDB">
      <SettingsRow title="Artwork" subtitle={subtitle} error={error}>
        <RowControls>
          {signingIn
            ? <RowButton onClick={run(cancelSgdbSignin)}>Cancel</RowButton>
            : <RowButton onClick={signIn}>{sgdb.configured ? "Sign in again" : "Sign in"}</RowButton>}
        </RowControls>
      </SettingsRow>
    </SettingsSection>
  );
}

function Account({ state }: { state: State }) {
  const ask = () => confirm("Disconnect from RomM?", "This device signs out of RomM. Games on the device and your settings are kept.", "Disconnect", run(disconnect));
  return (
    <SettingsSection title="Account">
      <SettingsRow title="Disconnect" subtitle={`Sign out of ${host(state.server.url) || "RomM"}`}>
        <RowControls>
          <RowButton disabled={!state.server.url} onClick={ask}>Disconnect</RowButton>
        </RowControls>
      </SettingsRow>
    </SettingsSection>
  );
}

export function Server({ state }: { state: State }) {
  return (
    <SettingsBody>
      <Connection state={state} />
      <Artwork state={state} />
      <Account state={state} />
    </SettingsBody>
  );
}
