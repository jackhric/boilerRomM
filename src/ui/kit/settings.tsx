// Rows for a page that looks like Steam's own settings: a logo, a title over a subtitle, and the controls in Steam's
// fixed column at the right. Everything but the logo is Steam's own layout and sizing.
import { DialogBody, DialogButton, DialogControlsSection, Field, Focusable, gamepadDialogClasses } from "@decky/ui";
import { CSSProperties, ReactNode, useEffect, useRef } from "react";
import { FaEllipsisH } from "react-icons/fa";

const LOGO = 56;
const ERROR = "#e5484d";
// As tall as the logo, so the controls sit level with the middle of the row instead of its top.
const controls: CSSProperties = { display: "flex", alignItems: "center", gap: 8, minHeight: LOGO };
const square: CSSProperties = { flex: "0 0 auto", width: 40, height: 40, minWidth: 0, padding: 0, display: "flex", alignItems: "center", justifyContent: "center" };
const wide: CSSProperties = { flex: "1 1 0", minWidth: 0, display: "flex", alignItems: "center", justifyContent: "center", gap: 10 };

/** The body of a settings page: a list of rows. */
export function SettingsList({ children }: { children: ReactNode }) {
  return (
    <DialogBody>
      <DialogControlsSection>{children}</DialogControlsSection>
    </DialogBody>
  );
}

/** The body of a page made of SettingsSections, which bring their own controls section. */
export function SettingsBody({ children }: { children: ReactNode }) {
  return <DialogBody>{children}</DialogBody>;
}

export interface SettingsRowProps {
  /** An image address; the row has no logo without one. */
  logo?: string;
  /** Draws the logo faded, for something that is not there yet. */
  dimmed?: boolean;
  title: ReactNode;
  subtitle?: ReactNode;
  /** Shown in place of the subtitle. */
  error?: string;
  /** The controls, usually inside a RowControls. */
  children?: ReactNode;
}

export function SettingsRow({ logo, dimmed, title, subtitle, error, children }: SettingsRowProps) {
  // Steam's own icon slot sits beside the label only, so the description would wrap under the logo. The logo goes
  // in the label instead, beside both lines, and the description keeps Steam's class.
  const label = (
    <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
      {logo && <img src={logo} alt="" style={{ width: LOGO, height: LOGO, flex: "0 0 auto", objectFit: "contain", opacity: dimmed ? 0.45 : 1 }} />}
      <div style={{ minWidth: 0 }}>
        <div>{title}</div>
        {(error || subtitle) && (
          <div className={gamepadDialogClasses.FieldDescription} style={{ marginTop: 2 }}>
            {error ? <span style={{ color: ERROR }}>{error}</span> : subtitle}
          </div>
        )}
      </div>
    </div>
  );
  return (
    <Field label={label} childrenContainerWidth="fixed" bottomSeparator="standard">
      {children}
    </Field>
  );
}

/**
 * The controls of a row, side by side. When `swapKey` changes the row is showing different controls, and the focus
 * that was on a removed one moves to the first new one instead of being lost.
 */
export function RowControls({ swapKey, children }: { swapKey?: unknown; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const first = useRef(true);
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    ref.current?.querySelector("button")?.focus();
  }, [swapKey]);
  return <Focusable ref={ref} style={controls}>{children}</Focusable>;
}

type ButtonProps = { disabled?: boolean; onClick(target: HTMLElement): void };

/** A button that fills the control column, or shares it with what is beside it. */
export function RowButton({ icon, children, disabled, onClick }: ButtonProps & { icon?: ReactNode; children: ReactNode }) {
  return (
    <DialogButton style={wide} disabled={disabled} onClick={(ev: MouseEvent) => onClick(ev.currentTarget as HTMLElement)}>
      {icon}{children}
    </DialogButton>
  );
}

/** The square "…" button that opens a row's menu; `label` is what a screen reader says. */
export function RowMoreButton({ label, disabled, onClick }: ButtonProps & { label: string }) {
  return (
    <DialogButton style={square} disabled={disabled} aria-label={label} onClick={(ev: MouseEvent) => onClick(ev.currentTarget as HTMLElement)}>
      <FaEllipsisH />
    </DialogButton>
  );
}

/** Something that takes the rest of the control column beside a square button, e.g. a dropdown. */
export function RowFill({ children }: { children: ReactNode }) {
  return <div style={{ flex: "1 1 0", minWidth: 0 }}>{children}</div>;
}
