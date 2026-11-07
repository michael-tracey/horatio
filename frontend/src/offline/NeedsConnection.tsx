import { useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router";
import type { CharacterListOut } from "../api/types";
import { characterOf, screenName } from "./screens";

/**
 * A screen that can't work offline says so, rather than loading for ever, and offers
 * the way to what does: the character's own Play View and sheet, or the characters.
 */
export function NeedsConnection({ pathname }: { pathname?: string }) {
  const client = useQueryClient();
  const here = pathname ?? window.location.pathname;
  const characterId = characterOf(here);
  // From another of the character's screens, the way to its Play View and sheet.
  const mine = !!characterId && !here.startsWith("/play/") && !!client.getQueryData<CharacterListOut[]>(["characters"])?.some((c) => c.id === characterId);
  const link = "text-gold underline hover:text-parchment";
  return (
    <div role="status" className="py-8 text-center">
      <p className="text-parchment">{screenName(here)} needs a connection.</p>
      <p className="mt-2 text-sm text-mist">
        {mine ? (
          <>
            <Link to={`/play/characters/${characterId}`} className={link}>
              Open its Play View
            </Link>{" "}
            or{" "}
            <Link to={`/characters/${characterId}`} className={link}>
              its sheet
            </Link>
            , which work offline if they're kept on this device.
          </>
        ) : (
          <>
            <Link to="/characters" className={link}>
              Your characters
            </Link>{" "}
            work offline if they're kept on this device.
          </>
        )}
      </p>
    </div>
  );
}

