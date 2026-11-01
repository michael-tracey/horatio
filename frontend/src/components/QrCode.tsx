import { useMemo } from "react";
import { encode } from "uqr";
import { qrPath } from "../pages/troupe/checkin";

/**
 * A QR code of `text`, drawn on the device: black on white with its quiet border,
 * whatever the theme, as phone cameras read that best. Medium error correction
 * survives a smudged or creased printout.
 */
export function QrCode({ text, label, className = "" }: { text: string; label: string; className?: string }) {
  const { size, path } = useMemo(() => {
    const qr = encode(text, { ecc: "M", border: 4 });
    return { size: qr.size, path: qrPath(qr.data) };
  }, [text]);
  return (
    <svg role="img" aria-label={label} viewBox={`0 0 ${size} ${size}`} shapeRendering="crispEdges" className={`rounded-md bg-white ${className}`}>
      <rect width={size} height={size} fill="#fff" />
      <path d={path} fill="#000" />
    </svg>
  );
}
