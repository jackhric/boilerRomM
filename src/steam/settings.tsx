// The pieces that make a page of ours look like Steam's own settings. Taken from Decky Toolkit's settings page.
import { DialogControlsSection, DialogControlsSectionHeader, SidebarNavigation } from "@decky/ui";
import { ComponentProps, ReactNode, useEffect } from "react";
import { tweak } from "./core/tweak";

type MainWindow = {
  m_BrowserWindow?: { document?: Document };
  m_HeaderStore?: { m_nNumTabbedPagesActingAsHeaderBackground: number };
};

const mainWindow = (): MainWindow | undefined => (window as any).SteamUIStore?.WindowStore?.GamepadUIMainWindowInstance;

/**
 * Makes the top bar transparent like Steam's own settings: Steam counts pages "acting as the header background" and
 * drops the bar's dark backdrop while any is shown. Without the store the bar stays dark.
 */
export function useTransparentHeader() {
  useEffect(() => tweak("transparent-header", () => {
    const store = mainWindow()?.m_HeaderStore;
    if (typeof store?.m_nNumTabbedPagesActingAsHeaderBackground !== "number") return;
    store.m_nNumTabbedPagesActingAsHeaderBackground++;
    return () => {
      store.m_nNumTabbedPagesActingAsHeaderBackground = Math.max(0, store.m_nNumTabbedPagesActingAsHeaderBackground - 1);
    };
  }), []);
}

const classCache = new Map<string, boolean>();

/** Whether Steam's stylesheets in the main window define `.name`. */
function hasGlobalClass(name: string): boolean {
  const cached = classCache.get(name);
  if (cached !== undefined) return cached;
  const doc = mainWindow()?.m_BrowserWindow?.document;
  if (!doc) return false;
  const needle = `.${name}`;
  const found = Array.from(doc.styleSheets).some((sheet) => {
    let rules: CSSRuleList;
    try {
      rules = sheet.cssRules;
    } catch {
      return false;
    }
    return Array.from(rules).some((rule) => {
      const sel = (rule as CSSStyleRule).selectorText;
      return !!sel && sel.split(/[\s,>+~:]+/).some((part) => part === needle || part.startsWith(`${needle}.`));
    });
  });
  classCache.set(name, found);
  return found;
}

/** A group of rows with a heading styled like Steam's settings ("Updates"); the plain header if Steam lacks the classes. */
export function SettingsSection({ title, children }: { title: string; children: ReactNode }) {
  if (!hasGlobalClass("SettingsDialogSubHeader")) {
    return (
      <DialogControlsSection>
        <DialogControlsSectionHeader>{title}</DialogControlsSectionHeader>
        {children}
      </DialogControlsSection>
    );
  }
  return (
    <DialogControlsSection className="DialogLabelledControlsSection DialogSettingsSection">
      <div role="heading" aria-level={3} className="SettingsDialogSubHeader">{title}</div>
      {children}
    </DialogControlsSection>
  );
}

type Pages = ComponentProps<typeof SidebarNavigation>["pages"];
type Page = Exclude<Pages[number], "separator">;

/** Sidebar pages in groups with a line between them. Steam drops a separator unless a later page is `visible`. */
export function settingsPages(...groups: Page[][]): Pages {
  return groups.flatMap((group, i) => [...(i ? (["separator"] as const) : []), ...group.map((p) => ({ visible: true, ...p }))]);
}
