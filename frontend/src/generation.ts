/**
 * How a vampire's Generation reads. The Generation background's rating is not
 * the generation: 1 dot is the 11th (MET: VTM p. 101), so "Generation 1" reads
 * as Caine. Name the generation where the server gives it, else the dots.
 */
import { ordinal } from "./pages/character/embrace";

/** A rating as dots: "●●". */
export function dots(rating: number): string {
  return "●".repeat(Math.max(rating, 0));
}

/**
 * "11th generation" where the generation is known; "Generation background ●"
 * where it isn't (one thin-blooded, or a rule about the dots alone). `withDots`
 * adds the dots to the generation: "11th generation (Generation background ●)".
 */
export function generationText(rating: number, generation?: number | null, withDots = false): string {
  const background = rating > 0 ? `Generation background ${dots(rating)}` : "no Generation background";
  if (!generation) return background;
  return withDots && rating > 0 ? `${ordinal(generation)} generation (${background})` : `${ordinal(generation)} generation`;
}
