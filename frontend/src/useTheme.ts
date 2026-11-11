import { useEffect } from "react";
import { useMe } from "./hooks";
import { applyTheme, isTheme, rememberTheme } from "./theme";

/**
 * Shows the signed-in person's theme, and keeps it on this device for index.html
 * next time. Until the account is known (or with no signal and nothing kept), and
 * once signed out, the page keeps the one index.html set: the theme last shown here.
 */
export function useTheme() {
  const me = useMe();
  const theme = me.data?.preferences.theme;
  useEffect(() => {
    if (!isTheme(theme)) return;
    applyTheme(theme);
    rememberTheme(theme);
  }, [theme]);
}
