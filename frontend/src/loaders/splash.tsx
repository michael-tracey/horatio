import { LoaderMark } from "./art";
import type { Motif } from "./motifs";

/**
 * The loading screen: the logo, with the loading animation under it. index.html
 * shows it before the app starts, with every motif in it and the one last seen
 * here shown (loaders.css, by the screen's data-motif); components/Splash.tsx
 * shows it with the chosen one while the app checks who is signed in, so one
 * hands over to the other.
 */
export function SplashScreen({ motif, motifs = motif ? [motif] : [] }: { motif?: Motif; motifs?: readonly Motif[] }) {
  return (
    <div className="splash" role="status" aria-label="Loading" data-motif={motif}>
      <img src="/logo.webp" alt="Horatio" width={224} height={224} />
      {motifs.map((m) => (
        <LoaderMark key={m} motif={m} size="full" />
      ))}
      <p>Loading…</p>
    </div>
  );
}
