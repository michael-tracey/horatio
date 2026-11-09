import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { CharacterOut } from "../../api/types";
import { builtTo } from "./builtTo";

/**
 * Says whose rules a character with no home troupe is built to (issue #569), in
 * BuildFor's words: a troupe's house rules until it accepts the character, or the
 * book's. Nothing once the character has a home troupe, or while the troupes load.
 * Every running troupe is listed to everyone, so naming it tells no one anything new.
 */
export function BuiltTo({ character, className }: { character: CharacterOut; className?: string }) {
  const troupes = useQuery({ queryKey: ["troupes"], queryFn: () => unwrap(api.GET("/api/troupes")) });
  if (character.kind !== "pc" || character.home_troupe_id || !troupes.data) return null;
  const to = builtTo(character, troupes.data);
  if (!to) return null;
  return (
    <p className={className}>
      {to.kind === "troupe" ? (
        <>
          Built to{" "}
          <Link to={`/troupes/${to.troupeId}/house-rules`} className="text-gold underline hover:text-parchment">
            {to.name}'s house rules
          </Link>
          . Not accepted there yet.
        </>
      ) : to.kind === "closed" ? (
        "Built to the house rules of a troupe that has since closed. Not accepted there."
      ) : (
        "Built to the book's rules (no troupe chosen yet)."
      )}
    </p>
  );
}
