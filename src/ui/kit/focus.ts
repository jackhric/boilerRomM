import { RefObject, useCallback, useEffect } from "react";

const focusMemory = new Map<string, string>();

const QUICK_MS = 220;
let lastMove = 0;

// A single move glides; holding or tapping a direction quickly jumps, so the page never lags behind the focus.
function pace(): ScrollBehavior {
  const now = performance.now();
  const quick = now - lastMove < QUICK_MS;
  lastMove = now;
  return quick ? "instant" : "smooth";
}

/** Brings a newly focused element into view. */
export function reveal(el: HTMLElement | null, block: ScrollLogicalPosition = "nearest") {
  el?.scrollIntoView({ block, inline: "center", behavior: pace() });
}

/** Scrolls the page an element is on back to its top (the hero), at the same pace as reveal. */
export function revealPageTop(el: HTMLElement | null) {
  el?.closest(".ctk-page")?.scrollTo({ top: 0, behavior: pace() });
}

/**
 * Returns the page to its top while focus is inside `el` (the head of a page). Steam scrolls a focused element only
 * just into view about 80 ms after focus, so the top is asked for again once that has started.
 */
export function holdPageTop(el: HTMLElement | null) {
  const page = el?.closest<HTMLElement>(".ctk-page");
  const win = el?.ownerDocument.defaultView;
  if (!el || !page || !win) return;
  page.scrollTo({ top: 0, behavior: pace() });
  const again = () => {
    if (page.scrollTop > 0 && el.querySelector(".gpfocus")) page.scrollTo({ top: 0, behavior: "smooth" });
  };
  // The page window's timers: this script's own are throttled to about one a second.
  win.setTimeout(again, 160);
  win.setTimeout(again, 450);
}

/**
 * A freshly mounted route page has no gamepad focus and ignores preferredFocus; a DOM focus() on a Focusable hands
 * it over. Gives focus to the element left from (remember its selector), else to `fallback`.
 */
export function useReturnFocus(key: string, root: RefObject<HTMLElement | null>, ready: boolean, fallback = "[data-autofocus]") {
  useEffect(() => {
    if (!ready) return;
    const saved = focusMemory.get(key);
    const back = saved ? root.current?.querySelector<HTMLElement>(saved) : null;
    const el = back || root.current?.querySelector<HTMLElement>(fallback);
    if (!el) return;
    el.focus();
    if (back) reveal(back);
  }, [ready]);
  return useCallback((selector: string | undefined) => {
    if (selector) focusMemory.set(key, selector);
    else focusMemory.delete(key);
  }, [key]);
}

/** The selector of a game card inside its section, for useReturnFocus. */
export function cardSelector(el: HTMLElement | null, romId: number): string {
  const section = el?.closest<HTMLElement>("[data-section]")?.dataset.section;
  return section ? `[data-section="${section}"] [data-rom="${romId}"]` : `[data-rom="${romId}"]`;
}
