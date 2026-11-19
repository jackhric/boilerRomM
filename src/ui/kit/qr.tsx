import { useMemo } from "react";
import { encode } from "uqr";

export function QrCode({ value, size }: { value: string; size: number }) {
  const { path, modules } = useMemo(() => {
    const qr = encode(value, { ecc: "M", border: 0 });
    const path = qr.data.flatMap((row, y) => row.map((on, x) => (on ? `M${x} ${y}h1v1h-1z` : ""))).join("");
    return { path, modules: qr.size };
  }, [value]);
  // Light modules on whatever is behind: the surrounding dark panel serves as the quiet zone.
  return (
    <svg width={size} height={size} viewBox={`0 0 ${modules} ${modules}`} shapeRendering="crispEdges" style={{ display: "block", margin: "0 auto" }}>
      <path d={path} fill="#fff" />
    </svg>
  );
}
