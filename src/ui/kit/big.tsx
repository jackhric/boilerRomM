// Couch-sized pieces for full-page screens (setup, error states). Sizes are the ones chosen in the setup design.
import { DialogButton, Spinner } from "@decky/ui";
import { CSSProperties, ReactNode } from "react";

export const T = {
  title: { fontSize: 40, fontWeight: 700, color: "#f1f2f3", lineHeight: 1.15, letterSpacing: "-0.01em" } as CSSProperties,
  page: { fontSize: 30, fontWeight: 700, color: "#f1f2f3" } as CSSProperties,
  sub: { fontSize: 28, color: "#d6d9dc" } as CSSProperties,
  body: { fontSize: 20, color: "#acb2b8", lineHeight: 1.4 } as CSSProperties,
  desc: { fontSize: 18, color: "#9a9fa5", lineHeight: 1.4 } as CSSProperties,
  eyebrow: { fontSize: 14, fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", color: "#9a9fa5" } as CSSProperties,
  white: { color: "#f1f2f3" } as CSSProperties,
};

export const column: CSSProperties = { display: "flex", flexDirection: "column" };
export const centred: CSSProperties = { ...column, alignItems: "center", textAlign: "center", justifyContent: "center", height: "100%" };

/** The class of the control that takes the focus when its screen appears. */
export const PRIMARY = "brm-primary";

type ButtonProps = { children: ReactNode; onClick(): void; large?: boolean; small?: boolean; primary?: boolean; quiet?: boolean; disabled?: boolean };

export function SetupButton({ children, onClick, large, small, primary, quiet, disabled }: ButtonProps) {
  const style: CSSProperties = {
    width: "auto", flex: "0 0 auto", minWidth: quiet || small ? 0 : large ? 300 : 220, height: small ? 44 : large ? 60 : 52,
    padding: quiet ? "0 18px" : small ? "0 22px" : "0 32px", fontSize: small ? 18 : large ? 22 : 20, whiteSpace: "nowrap",
    ...(quiet ? { background: "transparent" } : {}),
  };
  return <DialogButton className={primary ? PRIMARY : undefined} style={style} disabled={disabled} onClick={onClick}>{children}</DialogButton>;
}

export function Check({ size = 26 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth={3.6} strokeLinecap="round" strokeLinejoin="round" style={{ flex: "0 0 auto" }}>
      <path d="M4 12.5l5.5 5.5L20 7" />
    </svg>
  );
}

export function BigCheck() {
  return (
    <svg width={190} height={150} viewBox="0 0 190 150" fill="none">
      <path d="M22 80l48 48 98-106" stroke="#fff" strokeWidth={24} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function Busy({ size = 24 }: { size?: number }) {
  return <Spinner style={{ width: size, height: size, flex: "0 0 auto" }} />;
}

/** An icon or spinner beside one line of text. */
export function Line({ icon, children, style }: { icon?: ReactNode; children: ReactNode; style?: CSSProperties }) {
  return <div style={{ display: "flex", alignItems: "center", gap: 14, ...style }}>{icon}<span>{children}</span></div>;
}

export function Steps({ items, small }: { items: { text: ReactNode; lead?: ReactNode; color?: string }[]; small?: boolean }) {
  const size = small ? 21 : 26;
  return (
    <ol style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 22 }}>
      {items.map((item, i) => (
        <li key={i} style={{ display: "flex", gap: small ? 16 : 20, alignItems: "center", fontSize: size, color: item.color ?? "#f1f2f3" }}>
          <span style={{ flex: `0 0 ${small ? 24 : 34}px`, fontSize: size, fontWeight: 700, color: "#636b74", fontVariantNumeric: "tabular-nums", display: "flex", alignItems: "center" }}>
            {item.lead ?? i + 1}
          </span>
          {item.text}
        </li>
      ))}
    </ol>
  );
}

/** A row like the ones on Steam's settings pages: what it is on the left, its state on the right. */
/** `active`: the row being worked on, a shade lighter than the rest. */
export function StatusRow({ left, right, minHeight = 84, padding = "16px 20px", active }: { left: ReactNode; right?: ReactNode; minHeight?: number; padding?: string; active?: boolean }) {
  return (
    <div data-active={active || undefined} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 28, background: active ? "rgba(84,98,116,.6)" : "rgba(35,42,51,.55)", padding, minHeight, transition: "background .3s ease-out" }}>
      <div style={{ minWidth: 0 }}>{left}</div>
      <div style={{ flex: "0 0 auto", display: "flex", alignItems: "center" }}>{right}</div>
    </div>
  );
}
