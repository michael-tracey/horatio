import { SplashScreen } from "../loaders/splash";
import { useMotif } from "../loaders/useMotif";

/** The loading screen: the logo, with the chosen loading animation under it. The
 * same as index.html shows before the app starts (loaders/splash.tsx), so one
 * hands over to the other. */
export function Splash() {
  return <SplashScreen motif={useMotif()} />;
}
