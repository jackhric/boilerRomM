import { useEffect, useState } from "react";
import { getState, onProgress, onState, Progress, State } from "./api";

/** The backend's latest snapshot: fetched on mount, then pushed by the backend on every change. */
export function useBackendState(): State | undefined {
  const [state, setState] = useState<State>();
  useEffect(() => {
    let live = true;
    const off = onState((s) => live && setState(s));
    getState().then((s) => live && setState(s)).catch(() => {});
    return () => {
      live = false;
      off();
    };
  }, []);
  return state;
}

/** Progress of the download in flight, keyed by rom id; a finished one is dropped. */
export function useProgress(): Record<number, Progress> {
  const [progress, setProgress] = useState<Record<number, Progress>>({});
  useEffect(() => onProgress((p) => setProgress((prev) => {
    const next = { ...prev };
    if (p.status === "downloading" || p.status === "queued") next[p.rom_id] = p;
    else delete next[p.rom_id];
    return next;
  })), []);
  return progress;
}
