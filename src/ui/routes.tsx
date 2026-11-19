// The three route pages: each guards, loads and gates, then hands over to the page itself.
import { Navigation, SteamSpinner, useParams } from "@decky/ui";
import { ReactNode, useMemo } from "react";
import { FaGamepad } from "react-icons/fa";
import { refreshLibrary, State } from "../api";
import { describeProblem } from "../domain/problem";
import { SETTINGS_ROUTE, STORE_ROUTE } from "../domain/routes";
import { useBackendState, useProgress } from "../state";
import { useGameData } from "./game/data";
import { Page } from "./kit";
import { ErrorState } from "./kit/ErrorState";
import { Guard } from "./kit/guard";
import { needsSetup, SetupPage } from "./store/Setup";
import { Console } from "./store/ConsolePage";
import { StoreGame } from "./game/GamePage";
import { Store } from "./store/Discover";

const reload = () => refreshLibrary();
const toStore = { label: "Back to the store", run: () => Navigation.Navigate(STORE_ROUTE) };

function LibraryError({ error }: { error: string }) {
  const problem = describeProblem(error);
  return <ErrorState title={problem.title} detail={problem.detail} retry={{ run: reload }} secondary={{ label: "Server settings", run: () => Navigation.Navigate(SETTINGS_ROUTE) }} />;
}

function NoGames() {
  return <ErrorState icon={<FaGamepad />} title="No games yet" detail="Add games to your RomM server, then check again." retry={{ label: "Check again", run: reload }} />;
}

/** What to show instead of a page while the state is missing, unpaired or still loading; undefined when ready. */
function gate(state: State | undefined): ReactNode | undefined {
  if (!state) return <Page><SteamSpinner /></Page>;
  if (needsSetup(state)) return <SetupPage />;
  if (!state.library.games.length) {
    if (state.library.loading) return <Page><SteamSpinner /></Page>;
    if (state.library.error) return <LibraryError error={state.library.error} />;
  }
  return undefined;
}

export function StorePage() {
  return <Guard what="the store"><StoreRoute /></Guard>;
}

function StoreRoute() {
  const state = useBackendState();
  const progress = useProgress();
  const waiting = gate(state);
  if (waiting || !state) return <>{waiting}</>;
  if (!state.library.games.length) return <NoGames />;
  return <Store state={state} progress={progress} />;
}

export function GamePage() {
  const { rom_id } = useParams<{ rom_id: string }>();
  // Keyed so following "More like this" starts a fresh page at the top.
  return <Guard what="this game"><GameRoute key={rom_id} romId={Number(rom_id)} /></Guard>;
}

function GameRoute({ romId }: { romId: number }) {
  const { state, data } = useGameData(romId);
  const waiting = gate(state);
  if (waiting || !state) return <>{waiting}</>;
  if (!data) return <ErrorState icon={<FaGamepad />} title="This game isn't in your library any more" retry={{ label: "Check again", run: reload }} secondary={toStore} />;
  return <StoreGame state={state} data={data} />;
}

export function ConsolePage() {
  const { platform_id } = useParams<{ platform_id: string }>();
  return <Guard what="this console"><ConsoleRoute key={platform_id} platformId={Number(platform_id)} /></Guard>;
}

function ConsoleRoute({ platformId }: { platformId: number }) {
  const state = useBackendState();
  const progress = useProgress();
  const all = state?.library.games;
  const games = useMemo(() => (all ? all.filter((g) => g.platform_id === platformId) : []), [all, platformId]);
  const waiting = gate(state);
  if (waiting || !state) return <>{waiting}</>;
  const platform = state.library.platforms.find((p) => p.id === platformId);
  if (!platform || !games.length) {
    const title = platform ? `No ${platform.name} games` : "This console isn't in your library any more";
    return <ErrorState icon={<FaGamepad />} title={title} detail={platform ? "Your RomM server has none for this console." : undefined} retry={{ label: "Check again", run: reload }} secondary={toStore} />;
  }
  return <Console state={state} platform={platform} games={games} progress={progress} />;
}
