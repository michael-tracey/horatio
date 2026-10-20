import { useState } from "react";
import { clanColour, initials } from "./avatar";

/** How big it shows, and which of the picture's files fit that size (and twice it, for sharp screens). */
const SIZES = {
  xs: { px: 24, file: "48", sharp: "48" },
  sm: { px: 36, file: "48", sharp: "128" },
  md: { px: 64, file: "128", sharp: "128" },
  lg: { px: 112, file: "128", sharp: "512" },
  xl: { px: 192, file: "512", sharp: "512" },
} as const;

export type AvatarSize = keyof typeof SIZES;

/**
 * A character's picture, round, or without one its initials on its clan's
 * colour. `picture` is the API's address for it (CharacterOut.picture and the
 * like); a picture that will not load falls back to the initials too.
 */
export function Avatar({ name, picture, clan, size = "sm", className = "" }: { name: string; picture?: string | null; clan?: string | null; size?: AvatarSize; className?: string }) {
  const { px, file, sharp } = SIZES[size];
  const [failed, setFailed] = useState<string | null>(null);
  const shown = picture && failed !== picture;
  const box = `inline-grid shrink-0 place-items-center overflow-hidden rounded-full border border-ash ${className}`;
  if (shown) {
    return (
      <img
        src={`${picture}/${file}.webp`}
        srcSet={file === sharp ? undefined : `${picture}/${file}.webp 1x, ${picture}/${sharp}.webp 2x`}
        alt=""
        width={px}
        height={px}
        loading="lazy"
        onError={() => setFailed(picture)}
        className={`${box} bg-ash object-cover`}
        style={{ width: px, height: px }}
      />
    );
  }
  return (
    <span
      aria-hidden="true"
      className={`${box} font-display text-parchment/90 select-none`}
      style={{ width: px, height: px, background: clanColour(clan), fontSize: Math.max(10, px * 0.38) }}
    >
      {initials(name)}
    </span>
  );
}
