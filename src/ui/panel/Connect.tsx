import { ButtonItem, Field, PanelSection, PanelSectionRow, TextField } from "@decky/ui";
import { useEffect, useState } from "react";
import { cancelPairing, setServer, startPairing, State } from "../../api";
import { QrCode } from "../kit/qr";

export function Connect({ state }: { state: State }) {
  const [url, setUrl] = useState(state.server.url);
  const [busy, setBusy] = useState(false);
  // The saved address arrives with the first snapshot, after this component mounted.
  useEffect(() => setUrl(state.server.url), [state.server.url]);
  const pairing = state.pairing;
  const serverOk = !!state.server.url && !state.server.error;

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    try {
      await fn();
    } finally {
      setBusy(false);
    }
  };

  if (pairing.status === "waiting") {
    return (
      <PanelSection title="Pair with RomM">
        {pairing.verification_url && (
          <PanelSectionRow>
            <div style={{ padding: "16px 0" }}>
              <QrCode value={pairing.verification_url} size={200} />
            </div>
          </PanelSectionRow>
        )}
        <PanelSectionRow>
          <Field description="Scan with your phone, sign in to RomM and approve this device." />
        </PanelSectionRow>
        <PanelSectionRow>
          <div style={{ textAlign: "center", fontSize: "1.6em", letterSpacing: "0.15em", fontWeight: 700, padding: "4px 0" }}>
            {pairing.user_code?.replace(/^(.{4})(.+)$/, "$1 $2")}
          </div>
        </PanelSectionRow>
        <PanelSectionRow>
          <Field description={<>No camera? Open <b>{pairing.verification_url?.replace(/^https?:\/\//, "").replace(/\?.*$/, "")}</b> in any browser and enter this code.</>} />
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem layout="below" disabled={busy} onClick={() => run(cancelPairing)}>Cancel</ButtonItem>
        </PanelSectionRow>
      </PanelSection>
    );
  }

  const pairingNote =
    pairing.status === "denied" ? "The request was denied in RomM."
    : pairing.status === "expired" ? "The code expired. Start again."
    : pairing.status === "error" ? `Pairing failed: ${pairing.error}`
    : "";

  return (
    <PanelSection title="RomM server">
      <PanelSectionRow>
        <TextField label="Address" value={url} onChange={(e) => setUrl(e.target.value)} description="e.g. https://romm.example.com" />
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem layout="below" disabled={busy || !url.trim()} onClick={() => run(() => setServer(url))}>
          {serverOk && url.trim() === state.server.url ? `Connected: RomM ${state.server.version}` : "Connect"}
        </ButtonItem>
      </PanelSectionRow>
      {state.server.error && (
        <PanelSectionRow>
          <Field description={state.server.error} />
        </PanelSectionRow>
      )}
      {serverOk && (
        <PanelSectionRow>
          <ButtonItem layout="below" disabled={busy} onClick={() => run(startPairing)} description={pairingNote || "Shows a QR code to scan and approve in RomM's web UI; no password is typed on the device."}>
            Pair this device
          </ButtonItem>
        </PanelSectionRow>
      )}
    </PanelSection>
  );
}
