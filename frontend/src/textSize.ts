import { useEffect } from "react";
import { useLocation } from "react-router";
import type { Preferences } from "./api/types";
import { usePreferences } from "./hooks";

/**
 * The page's base font size for a text size setting (#107), or null to leave
 * the browser's own. Large is about 15% bigger, and Tailwind's spacing, being
 * in rem, grows with it. Printed sheets and badges (everything under /print/)
 * keep their own fixed sizes.
 */
export function rootFontSize(textSize: Preferences["text_size"], pathname: string): string | null {
  if (pathname.startsWith("/print/")) return null;
  return textSize === "large" ? "115%" : null;
}

/** Sets the base font size on <html> from the signed-in person's text size. */
export function useTextSize() {
  const { text_size } = usePreferences();
  const { pathname } = useLocation();
  const size = rootFontSize(text_size, pathname);
  useEffect(() => {
    const root = document.documentElement;
    if (size) root.style.fontSize = size;
    else root.style.removeProperty("font-size");
  }, [size]);
}
