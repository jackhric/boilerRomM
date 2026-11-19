import { useEffect, useState } from "react";
import { GameDetails, gameDetails } from "../../api";

const detailsCache = new Map<number, GameDetails>();
const detailsInFlight = new Map<number, Promise<GameDetails>>();

function fetchDetails(romId: number): Promise<GameDetails> {
  let p = detailsInFlight.get(romId);
  if (!p) {
    p = gameDetails(romId).then((d) => {
      detailsCache.set(romId, d);
      return d;
    }).finally(() => detailsInFlight.delete(romId));
    detailsInFlight.set(romId, p);
  }
  return p;
}

/** Starts fetching a game's details so they are cached before a page asks for them. */
export function prefetchDetails(romId: number): void {
  if (!detailsCache.has(romId)) fetchDetails(romId).catch(() => {});
}

export interface DetailsState {
  details?: GameDetails;
  /** True once the details are known or the fetch has failed: what depends on them can be decided. */
  settled: boolean;
}

/**
 * Details of one game. The default waits a short pause after the game is selected so scrolling a row does not
 * fetch every card; `immediate` (a game page) fetches at once. A cached value is returned on the first render.
 */
export function useDetailsState(romId: number | undefined, immediate = false): DetailsState {
  const [, rerender] = useState(0);
  const [failed, setFailed] = useState<number>();
  useEffect(() => {
    if (romId === undefined || detailsCache.has(romId)) return;
    let live = true;
    const start = () =>
      fetchDetails(romId).then(() => live && rerender((n) => n + 1)).catch(() => live && setFailed(romId));
    if (immediate) {
      start();
      return () => {
        live = false;
      };
    }
    const timer = setTimeout(start, 300);
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [romId, immediate]);
  const details = romId === undefined ? undefined : detailsCache.get(romId);
  return { details, settled: !!details || (romId !== undefined && failed === romId) };
}

export function useGameDetails(romId: number | undefined): GameDetails | undefined {
  return useDetailsState(romId).details;
}
