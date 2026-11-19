import { Focusable } from "@decky/ui";
import { CSSProperties, ReactNode, useEffect, useLayoutEffect, useRef, useState } from "react";
import { FaExclamationTriangle } from "react-icons/fa";
import { Busy, PRIMARY, SetupButton, T } from "./big";
import { C, FOOTER } from "./tokens";

export interface ErrorStateProps {
  title: string;
  /** The raw error: what went wrong, for someone who wants to know. */
  detail?: string;
  icon?: ReactNode;
  retry?: { label?: string; run(): unknown };
  secondary?: { label: string; run(): void };
}

const PAGE: CSSProperties = {
  position: "absolute", top: 0, left: 0, right: 0, bottom: FOOTER, boxSizing: "border-box", padding: "48px 72px 0", background: C.page,
  display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", textAlign: "center", gap: 18,
};

/** A page that could not show what it was asked to: what happened in plain words, and a way to try again. */
export function ErrorState({ title, detail, icon, retry, secondary }: ErrorStateProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [busy, setBusy] = useState(false);
  const live = useRef(true);
  useEffect(() => () => void (live.current = false), []);
  useLayoutEffect(() => {
    ref.current?.querySelector<HTMLElement>(`.${PRIMARY}`)?.focus();
  }, []);
  const run = () => {
    if (busy || !retry) return;
    setBusy(true);
    Promise.resolve()
      .then(retry.run)
      .catch(() => {})
      .finally(() => live.current && setBusy(false));
  };
  return (
    <Focusable ref={ref} style={PAGE}>
      <div style={{ fontSize: 110, lineHeight: 0, color: C.body, opacity: 0.85, marginBottom: 14 }}>{icon ?? <FaExclamationTriangle />}</div>
      <div style={{ ...T.title, fontSize: 36 }}>{title}</div>
      {detail && <div style={{ ...T.desc, fontSize: 16, color: C.note, maxWidth: 760, wordBreak: "break-word" }}>{detail}</div>}
      {(retry || secondary) && (
        <div style={{ display: "flex", gap: 12, alignItems: "center", marginTop: 26 }}>
          {retry && (
            // Stays enabled while busy: a disabled button would drop the controller focus.
            <SetupButton large primary onClick={run}>
              {busy ? <><Busy size={22} /><span style={{ marginLeft: 12 }}>Trying…</span></> : retry.label ?? "Try again"}
            </SetupButton>
          )}
          {secondary && <SetupButton large primary={!retry} onClick={secondary.run}>{secondary.label}</SetupButton>}
        </div>
      )}
    </Focusable>
  );
}
