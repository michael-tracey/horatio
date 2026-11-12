import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "../../api/client";
import type { ThrowSetOut } from "../../api/types";
import { HORATIO_IMAGES, pictureImages, type ThrowImages } from "./throwImages";
import { THROWS, type Throw } from "./throws";

/**
 * The Throws tab's pictures, as the person chose them in Settings (#671): Horatio's,
 * or the whole set of a troupe they play in. The chosen set's three pictures come
 * with the answer, as the pictures themselves, so the offline store keeps them
 * (offline/keep.ts) and throws show them with no signal. A choice whose troupe the
 * person left, or whose set the troupe removed, comes back as none: Horatio's.
 */

export const THROW_IMAGES = ["throw-images"] as const;

export type ChosenSet = ThrowSetOut & {
  /** Each picture as a data: address, at 512 px, to keep on the device. */
  pictures: Record<Throw, string>;
};

export type ChosenThrows = {
  /** The set the Throws tab uses; null for Horatio's. */
  chosen: ChosenSet | null;
  /** Every set the person may choose. */
  offered: ThrowSetOut[];
};

/** How a set is named in Settings and on the tab: its own name, and its troupe's. */
export function setName(set: Pick<ThrowSetOut, "name" | "troupe_name">): string {
  return set.name ? `${set.name} (${set.troupe_name})` : set.troupe_name;
}

/** A picture, read into a data: address so it can be kept. */
export async function asData(address: string, get: typeof fetch = fetch): Promise<string> {
  const response = await get(address, { credentials: "same-origin" });
  if (!response.ok) throw new Error(`The picture didn't come (${response.status}).`);
  const blob = await response.blob();
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error ?? new Error("The picture couldn't be read."));
    reader.readAsDataURL(blob);
  });
}

/** The person's choice, with the chosen set's pictures read in to keep. */
export async function fetchThrowImages(get: typeof fetch = fetch): Promise<ChosenThrows> {
  const mine = await unwrap(api.GET("/api/throw-images"));
  const set = mine.chosen;
  if (!set) return { chosen: null, offered: mine.offered };
  const [rock, paper, scissors] = await Promise.all(THROWS.map((which) => asData(`${set[which]}/512.webp`, get)));
  return { chosen: { ...set, pictures: { rock: rock!, paper: paper!, scissors: scissors! } }, offered: mine.offered };
}

/** The pictures the tab shows: the chosen set, or Horatio's while there is none (or none kept yet). */
export function imagesOf(kept: ChosenThrows | undefined): ThrowImages {
  const set = kept?.chosen;
  return set ? pictureImages(setName(set), set.pictures) : HORATIO_IMAGES;
}

export function useThrowImages() {
  return useQuery({ queryKey: THROW_IMAGES, queryFn: () => fetchThrowImages(), staleTime: 10 * 60_000 });
}

/** The Throws tab's pictures, as chosen. */
export function useChosenThrowImages(): ThrowImages {
  return imagesOf(useThrowImages().data);
}
