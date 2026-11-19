import { Menu, MenuItem, Navigation, showContextMenu } from "@decky/ui";
import { createElement, useCallback, useMemo, useState } from "react";
import { Game, State } from "../../api";
import { SortKey, SORTS, StoreModel, storeModel } from "../../domain/catalog";
import { consoleRoute, gameRoute } from "../../domain/routes";

export const openGamePage = (g: Game) => Navigation.Navigate(gameRoute(g.rom_id));
export const openConsolePage = (platformId: number) => Navigation.Navigate(consoleRoute(platformId));

// One draw lasts a visit (until the store has gone unused this long): coming back from a game page shows the same
// picks, a later visit shows new ones.
const ROTATION_MS = 20 * 60 * 1000;
let rotation = { seed: 0, at: 0, picks: [] as number[] };

function currentRotation() {
  const now = Date.now();
  const fresh = !rotation.at || now - rotation.at > ROTATION_MS;
  rotation = fresh ? { seed: (Math.random() * 2 ** 32) >>> 0, at: now, picks: [] } : { ...rotation, at: now };
  return rotation;
}

export function useStoreModel(state: State): StoreModel {
  const { games, platforms, recommended } = state.library;
  return useMemo(() => {
    const { seed, picks } = currentRotation();
    const model = storeModel(games, platforms, recommended, seed, picks);
    rotation.picks = model.featured.map((g) => g.rom_id);
    return model;
  }, [games, platforms, recommended]);
}

let rememberedSort: SortKey = "name";

/** A sort that is kept across visits, with Steam's own menu to change it. */
export function useSort() {
  const [sort, set] = useState(rememberedSort);
  const setSort = useCallback((key: SortKey) => {
    rememberedSort = key;
    set(key);
  }, []);
  const openSortMenu = useCallback((target?: any) => {
    showContextMenu(
      createElement(Menu, { label: "Sort by" }, SORTS.map(([key, label]) => createElement(MenuItem, { key, onSelected: () => setSort(key) }, label))),
      target?.currentTarget ?? target ?? window,
    );
  }, [setSort]);
  return { sort, sortLabel: SORTS.find(([k]) => k === sort)?.[1] ?? "", setSort, openSortMenu };
}
