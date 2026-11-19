import { Navigation, PanelSection, PanelSectionRow, Spinner, staticClasses } from "@decky/ui";
import { definePlugin, routerHook } from "@decky/api";
import { FaDrumstickBite } from "react-icons/fa";
import { start } from "./app/start";
import { CONSOLE_ROUTE, GAME_ROUTE, STORE_ROUTE } from "./domain/routes";
import { useBackendState } from "./state";
import { Connect } from "./ui/panel/Connect";
import { Home } from "./ui/panel/Home";
import { SgdbKey } from "./ui/panel/SgdbKey";
import { ConsolePage, GamePage, StorePage } from "./ui/routes";

function Content() {
  const state = useBackendState();
  if (!state) {
    return (
      <PanelSection>
        <PanelSectionRow><Spinner style={{ width: 24, height: 24 }} /></PanelSectionRow>
      </PanelSection>
    );
  }
  if (!state.account.paired) return <Connect state={state} />;
  return state.sgdb?.configured ? <Home state={state} /> : <SgdbKey state={state} />;
}

export default definePlugin(() => {
  routerHook.addRoute(STORE_ROUTE, StorePage, { exact: true });
  routerHook.addRoute(GAME_ROUTE, GamePage, { exact: true });
  routerHook.addRoute(CONSOLE_ROUTE, ConsolePage, { exact: true });
  const stop = start((next, previous) => {
    // Signed in through Steam's browser: leave it for the store rather than the SteamGridDB page.
    if (previous?.sgdb.signin?.active && !previous.sgdb.configured && next.sgdb.configured) {
      Navigation.Navigate(STORE_ROUTE);
      Navigation.CloseSideMenus();
    }
  });
  return {
    name: "boilerRomM",
    titleView: <div className={staticClasses.Title}>boilerRomM</div>,
    content: <Content />,
    icon: <FaDrumstickBite />,
    onDismount() {
      stop();
      routerHook.removeRoute(STORE_ROUTE);
      routerHook.removeRoute(GAME_ROUTE);
      routerHook.removeRoute(CONSOLE_ROUTE);
    },
  };
});
