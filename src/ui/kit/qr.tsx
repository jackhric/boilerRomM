import { useMemo } from "react";
import { encode } from "uqr";

/** A QR code. By default light modules on whatever is behind; give a `color` to draw it dark on a light tile. */
export function QrCode({ value, size, color = "#fff" }: { value: string; size: number; color?: string }) {
  const { path, modules } = useMemo(() => {
    const qr = encode(value, { ecc: "M", border: 0 });
    const path = qr.data.flatMap((row, y) => row.map((on, x) => (on ? `M${x} ${y}h1v1h-1z` : ""))).join("");
    return { path, modules: qr.size };
  }, [value]);
  return (
    <svg width={size} height={size} viewBox={`0 0 ${modules} ${modules}`} shapeRendering="crispEdges" style={{ display: "block", margin: "0 auto" }}>
      <path d={path} fill={color} />
    </svg>
  );
}
