import { DialogButton, Navigation } from "@decky/ui";
import { State } from "../../api";
import { SETUP_ROUTE } from "../../domain/routes";
import { C, Page } from "../kit";

/** The store pages rely on a paired RomM server and SteamGridDB art; first-run setup provides both. */
export const needsSetup = (state: State) => !state.setup_done || !state.account.paired || !state.sgdb?.configured;

export function SetupPage() {
  return (
    <Page>
      <div style={{ height: "100%", display: "flex", flexDirection: "column", gap: 24, alignItems: "center", justifyContent: "center", textAlign: "center", padding: "0 40px", fontSize: 20, color: C.subtitle }}>
        boilerRomM is not set up yet.
        <DialogButton style={{ width: "auto", padding: "0 32px", height: 52, fontSize: 20 }} onClick={() => Navigation.Navigate(SETUP_ROUTE)}>
          Set up boilerRomM
        </DialogButton>
      </div>
    </Page>
  );
}
