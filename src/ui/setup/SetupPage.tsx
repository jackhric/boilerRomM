// First-run setup: eight screens, one thing on each. The screen shown follows from what is already done, so leaving
// halfway and coming back resumes at the first step still to do.
import { Focusable, Navigation, SteamSpinner, TextField } from "@decky/ui";
import { CSSProperties, ReactNode, useEffect, useLayoutEffect, useRef, useState } from "react";
import { FaDownload } from "react-icons/fa";
import {
  cancelSgdbSignin, EmulatorInfo, finishSetup, installAllEmulators, refreshLibrary, setServer, setSgdbKey, SGDB_SIGN_IN, startPairing,
  startSgdbSignin, State,
} from "../../api";
import { STORE_ROUTE } from "../../domain/routes";
import { useTransparentHeader } from "../../steam";
import { useBackendState } from "../../state";
import { emulatorLogo } from "../emulatorLogos";
import { FOOTER } from "../kit";
import { Guard } from "../kit/guard";
import { QrCode } from "../kit/qr";
import { Wordmark } from "../kit/wordmark";
import { BigCheck, Busy, centred, Check, column, Line, PRIMARY, SetupButton, StatusRow, Steps, T } from "./parts";

type Step = "welcome" | "server" | "pair" | "verify" | "artwork" | "emulators" | "installing" | "ready";
const ORDER: Step[] = ["welcome", "server", "pair", "verify", "artwork", "emulators", "installing", "ready"];

const serverFound = (s: State) => !!s.server.version && !s.server.error;
const working = (e: EmulatorInfo) => e.busy === "queued" || e.busy === "installing";
const host = (url: string) => url.replace(/^https?:\/\//, "").replace(/[/?].*$/, "");

/** Where setup stands: the first step not yet done. */
function resume(s: State): Step {
  if (!serverFound(s)) return s.server.url ? "server" : "welcome";
  if (!s.account.paired) return "pair";
  if (!s.sgdb.configured) return "artwork";
  if (s.emulators.some(working)) return "installing";
  return s.emulators.some((e) => !e.installed && !e.error) ? "emulators" : "ready";
}

const PAGE: CSSProperties = {
  position: "absolute", top: 0, left: 0, right: 0, bottom: FOOTER, overflow: "hidden", padding: "48px 72px 0",
  background: "radial-gradient(1400px 520px at 50% -12%, rgba(94,174,255,.07), rgba(94,174,255,0) 70%), #171d25",
  color: "#d6d9dc", fontSize: 20, lineHeight: 1.4, boxSizing: "border-box",
};

function Welcome({ next }: { next(): void }) {
  return (
    <div style={{ ...centred, gap: 28, paddingBottom: 12 }}>
      <Wordmark size={116} />
      <div style={{ ...T.sub, marginTop: 6 }}>Your RomM library, in Steam.</div>
      <div style={{ ...T.desc, maxWidth: 600, fontSize: 20 }}>
        Connect to your RomM server, add game artwork and install the emulators. It takes about five minutes.
      </div>
      <div style={{ marginTop: 26 }}><SetupButton large primary onClick={next}>Next</SetupButton></div>
    </div>
  );
}

function Server({ state, next }: { state: State; next(): void }) {
  const [address, setAddress] = useState(host(state.server.url) || "");
  const [checking, setChecking] = useState("");
  const typed = address.trim();
  const found = serverFound(state) && host(state.server.url) === host(typed) && !checking;
  const failed = !checking && !!state.server.error && host(state.server.url) === host(typed);
  const connect = () => {
    setChecking(typed);
    setServer(typed).catch(() => {}).finally(() => setChecking(""));
  };
  return (
    <div style={{ ...column, alignItems: "center", textAlign: "center", paddingTop: 52, gap: 16, maxWidth: 760, margin: "0 auto" }}>
      <div style={T.title}>Where is your RomM server?</div>
      <div style={T.desc}>Type the address you use to open RomM in a browser.</div>
      <div style={{ width: "100%", marginTop: 18, textAlign: "left" }}>
        <TextField value={address} spellCheck={false} focusOnMount={!found} disabled={!!checking} onChange={(e) => setAddress(e.target.value)} />
      </div>
      <div style={{ minHeight: 66, marginTop: 6 }}>
        {checking && (
          <>
            <Line icon={<Busy />} style={{ ...T.white, justifyContent: "center" }}>Checking {host(checking)}…</Line>
            <div style={{ ...T.desc, fontSize: 16, marginTop: 6 }}>Trying https://, then http://</div>
          </>
        )}
        {found && <Line icon={<Check />} style={{ ...T.white, justifyContent: "center" }}>Found RomM {state.server.version} at {state.server.url}</Line>}
        {failed && (
          <>
            <div style={T.white}>{state.server.version ? state.server.error : `Nothing answered at ${host(typed)}.`}</div>
            {!state.server.version && (
              <div style={{ ...T.desc, fontSize: 17, marginTop: 4 }}>Check the address, and that the server is on and reachable from this device.</div>
            )}
          </>
        )}
      </div>
      <div>
        {found
          ? <SetupButton primary onClick={next}>Next</SetupButton>
          : <SetupButton primary={failed} disabled={!typed || !!checking} onClick={connect}>Connect</SetupButton>}
      </div>
    </div>
  );
}

function Pair({ state }: { state: State }) {
  const { pairing, account } = state;
  const paired = account.paired;
  const waiting = pairing.status === "waiting";
  const start = () => void startPairing().catch(() => {});
  useEffect(() => {
    if (!paired && pairing.status === "idle") start();
  }, []);
  const url = pairing.verification_url ?? "";
  const problem = !paired && !waiting && pairing.status !== "idle" && pairing.status !== "approved";
  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", height: "100%", alignItems: "center", gap: 64 }}>
      <div style={{ ...column, gap: 34 }}>
        <div style={T.title}>Pair this device</div>
        <Steps items={[{ text: "Scan the code with your phone." }, { text: "Sign in to RomM." }, { text: "Approve this device." }]} />
        <div style={{ marginTop: 8 }}>
          {paired
            ? <Line icon={<Check />} style={T.white}>Approved. Signed in as {account.username}.</Line>
            : problem
              ? <div style={T.white}>{pairing.status === "expired" ? "That code ran out." : pairing.error || "RomM did not approve this device."}</div>
              : <Line icon={<Busy />} style={T.body}>Waiting for approval…</Line>}
        </div>
        {!paired && <div><SetupButton small primary onClick={start}>Get a new code</SetupButton></div>}
      </div>
      <div style={{ ...column, alignItems: "center", textAlign: "center", gap: 22, opacity: paired ? 0.25 : 1 }}>
        <div style={{ lineHeight: 0, width: 300, height: 300 }}>
          {url && <QrCode value={url} size={300} />}
        </div>
        <div style={{ ...T.desc, fontSize: 17, maxWidth: 420 }}>
          No camera? Open <span style={T.white}>{url.replace(/^https?:\/\//, "").replace(/\?.*$/, "") || `${host(state.server.url)}/pair`}</span> on any device and enter
        </div>
        <div style={{ fontSize: 36, fontWeight: 700, letterSpacing: "0.14em", color: "#f1f2f3", fontVariantNumeric: "tabular-nums", minHeight: 50 }}>
          {pairing.user_code?.replace(/^(.{4})(.+)$/, "$1 $2")}
        </div>
      </div>
    </div>
  );
}

function Verify({ state, next }: { state: State; next(): void }) {
  const library = state.library;
  const read = library.loaded_at > 0 && !library.loading;
  useEffect(() => {
    if (!read && !library.loading) void refreshLibrary().catch(() => {});
  }, []);
  const done = read && !library.error;
  const rows: [title: string, detail: string, state: "done" | "busy" | "wait" | "failed"][] = [
    ["Server version", `RomM ${state.server.version} is supported`, "done"],
    ["Sign-in", `Signed in as ${state.account.username}`, "done"],
    ["Library", library.error ? library.error : read ? `${library.games.length.toLocaleString()} games on ${library.platforms.length} platforms` : "Reading the library…",
      library.error ? "failed" : read ? "done" : "busy"],
  ];
  return (
    <div style={{ display: "grid", gridTemplateColumns: "400px 1fr", gap: 64, alignItems: "center", height: "100%" }}>
      <div style={{ ...column, alignItems: "center", textAlign: "center", gap: 26 }}>
        {done ? <BigCheck /> : <Busy size={190} />}
        <div style={{ ...T.title, fontSize: 36 }}>{done ? "Connected to RomM" : library.error ? "Could not read the library" : "Checking…"}</div>
        {done && <SetupButton primary onClick={next}>Next</SetupButton>}
        {library.error && !library.loading && <SetupButton primary onClick={() => void refreshLibrary().catch(() => {})}>Try again</SetupButton>}
      </div>
      <div style={{ ...column, gap: 2 }}>
        {rows.map(([title, detail, status]) => (
          <StatusRow
            key={title}
            left={<><div style={{ fontSize: 20, color: status === "wait" ? "#636b74" : "#f1f2f3" }}>{title}</div><div style={{ fontSize: 16, color: "#9a9fa5", marginTop: 2 }}>{detail}</div></>}
            right={status === "done" ? <Check /> : status === "busy" ? <Busy size={22} /> : null}
          />
        ))}
      </div>
    </div>
  );
}

function Artwork({ state }: { state: State }) {
  const signin = state.sgdb.signin;
  const [typing, setTyping] = useState(false);
  const [key, setKey] = useState("");
  const [saving, setSaving] = useState(false);
  const signIn = () => {
    Navigation.NavigateToExternalWeb(SGDB_SIGN_IN);
    startSgdbSignin().catch(() => {});
  };
  const save = () => {
    setSaving(true);
    setSgdbKey(key.trim()).catch(() => {}).finally(() => setSaving(false));
  };
  const at = signin.active ? (signin.stage === "opening" ? 0 : signin.stage === "reading" || signin.stage === "verifying" ? 2 : 1) : -1;
  const items = ["Steam's sign-in page opens.", "Press Sign In there.", "You come back here. Your key is saved for you."].map((text, i) => ({
    text,
    lead: at < 0 ? undefined : i < at ? <Check size={20} /> : i === at ? <Busy size={20} /> : undefined,
    color: at < 0 || i === at ? undefined : i < at ? "#9a9fa5" : "#636b74",
  }));
  const error = signin.stage === "failed" ? signin.error : state.sgdb.error;
  return (
    <div style={{ display: "grid", gridTemplateColumns: "1.1fr 1fr", gap: 72, alignItems: "center", height: "100%" }}>
      <div style={{ ...column, gap: 20 }}>
        <div style={T.title}>Your games need artwork</div>
        <div style={T.body}>boilerRomM gets box art and banners from SteamGridDB, which needs a free account.</div>
        {typing ? (
          <div style={{ ...column, gap: 14, marginTop: 14 }}>
            <TextField label="SteamGridDB API key" bIsPassword value={key} onChange={(e) => setKey(e.target.value)} description="steamgriddb.com → your profile → Preferences → API" />
            <div style={{ display: "flex", gap: 12 }}>
              <SetupButton primary disabled={saving || !key.trim()} onClick={save}>Save key</SetupButton>
              <SetupButton quiet onClick={() => setTyping(false)}>Sign in with Steam instead</SetupButton>
            </div>
          </div>
        ) : (
          <div style={{ marginTop: 28, display: "flex", gap: 12, alignItems: "center" }}>
            {signin.active
              ? <SetupButton large primary onClick={() => void cancelSgdbSignin().catch(() => {})}>Cancel</SetupButton>
              : <SetupButton large primary onClick={signIn}>Sign in with Steam</SetupButton>}
            {!signin.active && <SetupButton quiet onClick={() => setTyping(true)}>Type a key instead</SetupButton>}
          </div>
        )}
        {error && <div style={{ ...T.desc, color: "#f1f2f3" }}>{error}</div>}
      </div>
      <div style={{ ...column, gap: 24, borderLeft: "1px solid rgba(255,255,255,.1)", paddingLeft: 52 }}>
        <div style={T.eyebrow}>{signin.active ? "Signing in" : "What happens"}</div>
        <Steps small items={items} />
      </div>
    </div>
  );
}

function Emulators({ state }: { state: State }) {
  const count = state.emulators.length;
  return (
    <div style={{ ...centred, gap: 22 }}>
      <div style={T.title}>Install emulators</div>
      <div style={{ ...T.body, maxWidth: 700 }}>boilerRomM installs {count} emulators, so every system in your library has one. About 800 MB.</div>
      <div style={{ display: "grid", gridTemplateColumns: `repeat(${count}, 124px)`, marginTop: 30 }}>
        {state.emulators.map((e) => (
          <div key={e.id} style={{ ...column, alignItems: "center", gap: 10 }}>
            <img src={emulatorLogo(e.id)} alt="" style={{ width: 64, height: 64, objectFit: "contain" }} />
            <span style={{ fontSize: 15, color: "#9a9fa5", lineHeight: 1.2 }}>{e.name}</span>
          </div>
        ))}
      </div>
      <div style={{ marginTop: 34 }}>
        <SetupButton large primary onClick={() => void installAllEmulators().catch(() => {})}><FaDownload style={{ marginRight: 12 }} />Install all</SetupButton>
      </div>
    </div>
  );
}

const megabytes = (bytes: number) => Math.round(bytes / (1 << 20));

function installText(e: EmulatorInfo): { text: string; color: string } {
  if (e.installed && !working(e)) return { text: "Installed", color: "#9a9fa5" };
  if (e.busy === "installing") {
    const [done, total] = e.progress ?? [0, 0];
    return { text: !done ? "Installing…" : total ? `Downloading · ${megabytes(done)} of ${megabytes(total)} MB` : `Downloading · ${megabytes(done)} MB`, color: "#f1f2f3" };
  }
  if (e.busy === "queued") return { text: "Waiting", color: "#636b74" };
  if (e.error) return { text: "Didn't install. You can try again in Settings.", color: "#d6d9dc" };
  return { text: "Waiting", color: "#636b74" };
}

function Installing({ state, next }: { state: State; next(): void }) {
  const all = state.emulators;
  const finished = !all.some(working);
  const installed = all.filter((e) => e.installed && !working(e)).length;
  const settled = all.filter((e) => !working(e) && (e.installed || e.error)).length;
  const current = all.find((e) => e.busy === "installing");
  const [done, total] = current?.progress ?? [0, 0];
  const fraction = Math.min(1, (settled + (total ? done / total : 0)) / Math.max(1, all.length));
  const eyebrow = finished
    ? installed === all.length ? `All ${all.length} emulators installed` : `${installed} of ${all.length} emulators installed`
    : current ? `${done ? "Downloading" : "Installing"} ${current.name}${total ? ` · ${megabytes(done)} MB of ${megabytes(total)} MB` : ""}` : "Starting";
  return (
    <div style={{ ...column, height: "100%", paddingTop: 26, paddingBottom: 32, boxSizing: "border-box" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", minHeight: 52 }}>
        <div style={T.page}>{finished ? "Emulators installed" : "Installing emulators"}</div>
        {finished && <SetupButton primary onClick={next}>Next</SetupButton>}
      </div>
      <div style={{ display: "grid", gap: 2, marginTop: 16 }}>
        {all.map((e) => {
          const status = installText(e);
          return (
            <StatusRow
              key={e.id}
              minHeight={0}
              padding="7px 18px"
              left={
                <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
                  <img src={emulatorLogo(e.id)} alt="" style={{ width: 40, height: 40, objectFit: "contain", opacity: e.installed && !working(e) ? 1 : 0.45 }} />
                  <div>
                    <div style={{ fontSize: 18, lineHeight: 1.25, color: "#f1f2f3" }}>{e.name}</div>
                    <div style={{ fontSize: 14, color: "#9a9fa5" }}>{e.system}</div>
                  </div>
                </div>
              }
              right={<span style={{ fontSize: 16, color: status.color, textAlign: "right" }}>{status.text}</span>}
            />
          );
        })}
      </div>
      <div style={{ marginTop: "auto" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 20, marginBottom: 12 }}>
          <span style={{ ...T.eyebrow, color: "#d6d9dc" }}>{eyebrow}</span>
          <span style={T.eyebrow}>{installed} of {all.length} installed</span>
        </div>
        <div style={{ height: 8, background: "rgba(255,255,255,.1)", borderRadius: 1, overflow: "hidden" }}>
          <div style={{ height: "100%", width: `${fraction * 100}%`, background: "#1a9fff", transition: "width .3s linear" }} />
        </div>
      </div>
    </div>
  );
}

function Ready({ state }: { state: State }) {
  const open = () => {
    void finishSetup().catch(() => {}).finally(() => Navigation.Navigate(STORE_ROUTE));
  };
  return (
    <div style={{ ...centred, gap: 22 }}>
      <div style={{ ...T.title, fontSize: 46 }}>boilerRomM is ready</div>
      <div style={T.body}>{state.library.games.length.toLocaleString()} games from {host(state.server.url)} are in your store.</div>
      <div style={{ marginTop: 30 }}><SetupButton large primary onClick={open}>Open the store</SetupButton></div>
    </div>
  );
}

function Setup({ state }: { state: State }) {
  const [step, setStep] = useState<Step>(() => resume(state));
  const ref = useRef<HTMLDivElement>(null);
  const go = (to: Step) => setStep(to);

  // What the backend reports moves setup on by itself: approval on the phone, the key arriving, installs starting.
  useEffect(() => {
    if (step === "pair" && state.account.paired) {
      const t = setTimeout(() => go("verify"), 1200);
      return () => clearTimeout(t);
    }
    if (step === "artwork" && state.sgdb.configured) go(state.emulators.every((e) => e.installed) ? "ready" : "emulators");
    if (step === "emulators" && state.emulators.some(working)) go("installing");
    return undefined;
  }, [step, state.account.paired, state.sgdb.configured, state.emulators]);

  useLayoutEffect(() => {
    (ref.current?.querySelector<HTMLElement>(`.${PRIMARY}`) ?? ref.current?.querySelector<HTMLElement>("input"))?.focus();
  }, [step]);

  const back = (e: CustomEvent) => {
    const earlier = { server: "welcome", pair: "server", artwork: "verify", emulators: "artwork", ready: "emulators" }[step as string] as Step | undefined;
    if (!earlier) return;
    e.stopPropagation();
    go(earlier);
  };

  let screen: ReactNode;
  if (step === "welcome") screen = <Welcome next={() => go("server")} />;
  else if (step === "server") screen = <Server state={state} next={() => go("pair")} />;
  else if (step === "pair") screen = <Pair state={state} />;
  else if (step === "verify") screen = <Verify state={state} next={() => go(state.sgdb.configured ? "emulators" : "artwork")} />;
  else if (step === "artwork") screen = <Artwork state={state} />;
  else if (step === "emulators") screen = <Emulators state={state} />;
  else if (step === "installing") screen = <Installing state={state} next={() => go("ready")} />;
  else screen = <Ready state={state} />;

  return (
    <Focusable ref={ref} style={PAGE} onCancel={back} data-step={ORDER.indexOf(step) + 1}>
      {screen}
    </Focusable>
  );
}

function Route() {
  useTransparentHeader();
  const state = useBackendState();
  if (!state) return <div style={PAGE}><SteamSpinner /></div>;
  return <Setup state={state} />;
}

export function SetupPage() {
  return <Guard what="setup"><Route /></Guard>;
}
