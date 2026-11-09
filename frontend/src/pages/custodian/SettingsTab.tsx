import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api, unwrap } from "../../api/client";
import { Button, Card, ErrorText, Loaded } from "../../components/ui";
import { useToast } from "../../components/Toast";
import { LoaderMark, loaders } from "../../loaders/art";
import { MOTIFS, motifFor, rememberMotif, type Motif, type MotifsBySplat } from "../../loaders/motifs";
import { SplashScreen } from "../../loaders/splash";
import { useAppearance } from "../../loaders/useMotif";

/** Settings for all of Horatio, which only the custodian chooses. */
export function SettingsTab() {
  const appearance = useAppearance();
  return (
    <Loaded query={appearance}>{(found) => <LoadingAnimationCard bySplat={found.loading_animation} />}</Loaded>
  );
}

/**
 * The loading animation everyone sees (#568), each shown moving as it would: full
 * screen as Horatio opens, and small in a page while it waits for an answer. It is
 * kept by splat, so a splat can later have its own; this chooses the default and
 * leaves any splat's own as it is.
 */
function LoadingAnimationCard({ bySplat }: { bySplat: MotifsBySplat }) {
  const client = useQueryClient();
  const toast = useToast();
  const chosen = motifFor(bySplat);
  const [full, setFull] = useState<Motif | null>(null);
  const save = useMutation({
    mutationFn: (motif: Motif) => unwrap(api.PUT("/api/appearance/loading-animation", { body: { loading_animation: { ...bySplat, default: motif } } })),
    onSuccess: (saved, motif) => {
      client.setQueryData(["appearance"], saved);
      rememberMotif(motifFor(saved.loading_animation));
      toast({ message: `Horatio now shows the ${loaders[motif].label.toLowerCase()} while it loads.` });
    },
  });
  const shown = save.isPending ? save.variables : chosen;

  return (
    <Card title="Loading animation">
      <p className="mb-4 text-sm text-mist">
        What everyone sees while Horatio waits: full screen under the logo as it opens, signed in or not, and small in a page while it waits for an answer. Where a
        device asks for less motion, each stands still and fades gently instead.
      </p>
      <div role="radiogroup" aria-label="Loading animation" className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {MOTIFS.map((motif) => {
          const { label, about } = loaders[motif];
          const on = shown === motif;
          return (
            <div key={motif} className={`flex flex-col gap-3 rounded-md border p-3 ${on ? "border-gold bg-gold/10" : "border-ash"}`}>
              <button
                type="button"
                role="radio"
                aria-checked={on}
                aria-describedby={`loader-about-${motif}`}
                disabled={save.isPending}
                onClick={() => !on && save.mutate(motif)}
                className="flex flex-col items-center gap-3 rounded-md py-2 text-center"
              >
                <span className="grid h-20 place-items-center">
                  <LoaderMark motif={motif} size="block" />
                </span>
                <span className={on ? "font-medium text-gold" : "font-medium text-parchment"}>
                  {label}
                  {on && <span className="sr-only"> (chosen)</span>}
                </span>
              </button>
              <p id={`loader-about-${motif}`} className="text-center text-xs text-mist">
                {about}
              </p>
              <div className="flex flex-wrap items-center justify-center gap-x-3 border-t border-ash pt-2 text-xs text-mist">
                <span className="inline-flex items-center gap-1.5" aria-hidden="true">
                  <LoaderMark motif={motif} size="compact" />
                  Searching…
                </span>
                <Button variant="ghost" className="min-h-8 px-2 text-xs whitespace-nowrap" onClick={() => setFull(motif)} aria-label={`Preview ${label.toLowerCase()} full screen`}>
                  Full screen
                </Button>
              </div>
            </div>
          );
        })}
      </div>
      <ErrorText error={save.error} />
      {full && <FullScreenPreview motif={full} onClose={() => setFull(null)} />}
    </Card>
  );
}

/** The loading screen as it shows when Horatio opens, over everything until closed. */
function FullScreenPreview({ motif, onClose }: { motif: Motif; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (dialog && !dialog.open) dialog.showModal();
  }, []);
  return (
    <dialog
      ref={ref}
      aria-label={`${loaders[motif].label}, full screen`}
      onClose={onClose}
      onClick={() => ref.current?.close()}
      className="m-0 h-dvh max-h-none w-screen max-w-none overflow-hidden bg-night p-0 backdrop:bg-night"
    >
      <SplashScreen motif={motif} />
      <Button variant="secondary" autoFocus className="absolute top-4 right-4" onClick={() => ref.current?.close()}>
        Close
      </Button>
    </dialog>
  );
}
