import { Link } from "react-router";
import { Card } from "../../components/ui";
import { SettingDocumentFor } from "./SettingDocument";

/**
 * The Setting tab: the troupe's Setting Style Document for every member to read before
 * they build (MET: VTM p. 331), and to print for the Storyteller table. Its running
 * staff write their parts under Troupe settings; the rest follows the troupe's own
 * settings, each part linking to where it is changed.
 */
export function SettingTab({ troupeId, staff }: { troupeId: string; staff: boolean }) {
  const base = `/troupes/${troupeId}`;
  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-mist">
        The chronicle as its storytellers set it out, for building characters that fit it.{" "}
        {staff && (
          <>
            Write the title, teaser, scope, themes, moods and notes under{" "}
            <Link to={`${base}/settings`} className="underline hover:text-parchment">
              Troupe settings
            </Link>
            ; the rest follows the troupe's settings. Keep what players mustn't read in the{" "}
            <Link to={`${base}/story-bible`} className="underline hover:text-parchment">
              story bible
            </Link>
            .{" "}
          </>
        )}
        <Link to={`/print/setting/${troupeId}`} target="_blank" className="underline hover:text-parchment">
          Print it
        </Link>
      </p>
      <Card>
        <SettingDocumentFor troupeId={troupeId} editBase={staff ? base : undefined} />
      </Card>
    </div>
  );
}
