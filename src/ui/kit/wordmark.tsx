// The boilerRomM wordmark: Space Grotesk (SIL Open Font License, LICENSES/OFL-1.1-SpaceGrotesk.txt), "boiler" light
// and grey, "RomM" bold and white. The font is inlined so the name looks the same on every device.
const fonts = import.meta.glob<string>("../../../assets/fonts/SpaceGrotesk-latin.woff2", { eager: true, query: "?inline", import: "default" });
const FACE = "boilerRomM Wordmark";
const CSS = `@font-face { font-family: "${FACE}"; src: url(${Object.values(fonts)[0] ?? ""}) format("woff2"); font-weight: 300 700; font-display: block; }`;

export function Wordmark({ size }: { size: number }) {
  return (
    <span style={{ fontFamily: `"${FACE}", sans-serif`, fontWeight: 400, fontSize: size, lineHeight: 1, letterSpacing: "-0.025em", color: "#9aa1a9", whiteSpace: "nowrap" }}>
      <style>{CSS}</style>
      boiler<b style={{ fontWeight: 700, color: "#f1f2f3" }}>RomM</b>
    </span>
  );
}
