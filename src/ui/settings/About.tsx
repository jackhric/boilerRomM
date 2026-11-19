import { ConfirmModal, DialogBody, DialogButton, DialogControlsSection, Field, Navigation, showModal } from "@decky/ui";
import { resetEverything, State } from "../../api";
import { SETUP_ROUTE } from "../../domain/routes";
import { SettingsSection } from "../../steam";
import { Wordmark } from "../kit/wordmark";

const DANGER = "#e5484d";

function confirmWipe() {
  showModal(
    <ConfirmModal
      strTitle="Wipe boilerRomM and start over?"
      strDescription="This signs you out of RomM and SteamGridDB, removes every emulator with its settings, and clears the artwork. Setup then runs again. Your downloaded games and saves stay on this device."
      strOKButtonText="Wipe and restart"
      bDestructiveWarning
      onOK={() => {
        void resetEverything()
          .then(() => Navigation.Navigate(SETUP_ROUTE))
          .catch(() => {});
      }}
    />,
  );
}

export function About({ state }: { state: State }) {
  return (
    <DialogBody>
      <DialogControlsSection>
        <div style={{ padding: "8px 0 20px" }}>
          <Wordmark size={40} />
          <div style={{ marginTop: 10, opacity: 0.7 }}>Your RomM library as a store in Steam, with the emulators to play it.</div>
        </div>
        <Field label="Version" bottomSeparator="standard">{state.version}</Field>
        <Field label="License" bottomSeparator="standard">AGPL-3.0</Field>
        <Field label="Source" bottomSeparator="none">github.com/jackhric/boilerRomM</Field>
      </DialogControlsSection>
      <SettingsSection title="Reset">
        <Field
          label="Wipe and restart"
          description="Removes your sign-ins, emulators and settings, then runs setup again. Downloaded games and saves are kept."
          childrenContainerWidth="fixed"
          bottomSeparator="none"
        >
          <DialogButton style={{ color: DANGER }} onClick={confirmWipe}>Wipe and restart</DialogButton>
        </Field>
      </SettingsSection>
    </DialogBody>
  );
}
