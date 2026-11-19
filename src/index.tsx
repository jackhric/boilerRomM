import { ButtonItem, DialogButton, Navigation, PanelSection, PanelSectionRow, Spinner, staticClasses } from "@decky/ui";
import { definePlugin, routerHook } from "@decky/api";
import { FaCog, FaDrumstickBite } from "react-icons/fa";
import { start } from "./app/start";
import { CONSOLE_ROUTE, GAME_ROUTE, SETTINGS_ROUTE, SETUP_ROUTE, STORE_ROUTE } from "./domain/routes";
import { useBackendState } from "./state";
import { ConsolePage, GamePage, StorePage } from "./ui/routes";
import { SettingsPage } from "./ui/settings/SettingsPage";
import { SetupPage } from "./ui/setup/SetupPage";
import { Wordmark } from "./ui/kit/wordmark";

function Content() {
  const state = useBackendState();
  if (!state) {
    return (
      <PanelSection>
        <PanelSectionRow><Spinner style={{ width: 24, height: 24 }} /></PanelSectionRow>
      </PanelSection>
    );
  }
  if (!state.setup_done) {
    return (
      <PanelSection>
        <PanelSectionRow>
          <ButtonItem
            layout="below"
            description="Connect to your RomM server, add artwork and install the emulators."
            onClick={() => {
              Navigation.CloseSideMenus();
              Navigation.Navigate(SETUP_ROUTE);
            }}
          >
            Set up boilerRomM
          </ButtonItem>
        </PanelSectionRow>
      </PanelSection>
    );
  }
  return (
    <PanelSection>
      <PanelSectionRow>
        <ButtonItem
          layout="below"
          onClick={() => {
            Navigation.CloseSideMenus();
            Navigation.Navigate(STORE_ROUTE);
          }}
        >
          Open store
        </ButtonItem>
      </PanelSectionRow>
    </PanelSection>
  );
}

export default definePlugin(() => {
  routerHook.addRoute(STORE_ROUTE, StorePage, { exact: true });
  routerHook.addRoute(GAME_ROUTE, GamePage, { exact: true });
  routerHook.addRoute(CONSOLE_ROUTE, ConsolePage, { exact: true });
  routerHook.addRoute(SETTINGS_ROUTE, SettingsPage, { exact: true });
  routerHook.addRoute(SETUP_ROUTE, SetupPage, { exact: true });
  const stop = start((next, previous) => {
    // Signed in through Steam's browser: leave the SteamGridDB page for where the sign-in was started from.
    if (previous?.sgdb.signin?.active && !previous.sgdb.configured && next.sgdb.configured) {
      Navigation.Navigate(next.setup_done ? STORE_ROUTE : SETUP_ROUTE);
      Navigation.CloseSideMenus();
    }
  });
  return {
    name: "boilerRomM",
    titleView: (
      <div className={staticClasses.Title} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flex: 1, padding: 0 }}>
        <Wordmark size={20} />
        <DialogButton
          style={{ height: 28, width: 40, minWidth: 0, padding: "10px 12px", display: "flex", alignItems: "center", justifyContent: "center" }}
          onClick={() => {
            Navigation.CloseSideMenus();
            Navigation.Navigate(SETTINGS_ROUTE);
          }}
        >
          <FaCog style={{ display: "block" }} />
        </DialogButton>
      </div>
    ),
    content: <Content />,
    icon: <FaDrumstickBite />,
    onDismount() {
      stop();
      routerHook.removeRoute(STORE_ROUTE);
      routerHook.removeRoute(GAME_ROUTE);
      routerHook.removeRoute(CONSOLE_ROUTE);
      routerHook.removeRoute(SETTINGS_ROUTE);
      routerHook.removeRoute(SETUP_ROUTE);
    },
  };
});
