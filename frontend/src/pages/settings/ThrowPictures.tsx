import { useQueryClient } from "@tanstack/react-query";
import type { ReactNode } from "react";
import type { ThrowSetOut } from "../../api/types";
import { useToast } from "../../components/Toast";
import { useSetPreferences } from "../../hooks";
import { setName, THROW_IMAGES, useThrowImages } from "../play/chosenThrows";
import { HORATIO_IMAGES } from "../play/throwImages";
import { THROW_NAMES, THROWS } from "../play/throws";

/** Three small pictures side by side, to tell the sets apart. */
function Previews({ picture }: { picture: (which: (typeof THROWS)[number]) => ReactNode }) {
  return (
    <span aria-hidden="true" className="flex shrink-0 gap-1">
      {THROWS.map((which) => (
        <span key={which} title={THROW_NAMES[which]} className="block size-9 text-parchment">
          {picture(which)}
        </span>
      ))}
    </span>
  );
}

/**
 * "Throw pictures" (#671): Horatio's, or the whole set of a troupe the person plays
 * in. Kept on the account. A set they can no longer choose shows as Horatio's.
 */
export function ThrowPictures() {
  const mine = useThrowImages();
  const set = useSetPreferences();
  const client = useQueryClient();
  const toast = useToast();
  const chosen = mine.data?.chosen?.troupe_id ?? null;
  const offered = mine.data?.offered ?? [];
  const choose = (troupeId: string | null, name: string) =>
    set.mutate(
      { throw_images: troupeId },
      {
        onSuccess: () => {
          void client.invalidateQueries({ queryKey: THROW_IMAGES });
          toast({ message: `Throw pictures: ${name}. Saved.` });
        },
      },
    );
  const option = (troupeId: string | null, name: string, previews: ReactNode) => (
    <button
      key={troupeId ?? "horatio"}
      type="button"
      role="radio"
      aria-checked={chosen === troupeId}
      disabled={set.isPending}
      onClick={() => choose(troupeId, name)}
      className={`flex min-h-12 w-full items-center justify-between gap-3 px-3 py-2 text-left text-sm ${chosen === troupeId ? "bg-gold/20 text-gold" : "text-mist hover:text-parchment"} [&+&]:border-t [&+&]:border-ash`}
    >
      <span className="min-w-0">{name}</span>
      {previews}
    </button>
  );
  const troupeSet = (s: ThrowSetOut) =>
    option(
      s.troupe_id,
      setName(s),
      <Previews picture={(which) => <img src={`${s[which]}/128.webp`} alt="" className="h-full w-full object-contain" />} />,
    );
  return (
    <div className="w-full sm:w-80">
      <div role="radiogroup" aria-label="Throw pictures" className="overflow-hidden rounded-md border border-ash">
        {option(null, "Horatio's", <Previews picture={HORATIO_IMAGES.picture} />)}
        {offered.map(troupeSet)}
      </div>
    </div>
  );
}
