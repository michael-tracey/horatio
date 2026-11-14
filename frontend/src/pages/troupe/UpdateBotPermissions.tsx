import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import { Button, ErrorText } from "../../components/ui";
import { useAction } from "../../hooks";
import { manualLink } from "../../manualLink";
import { listed } from "./botPermissions";

/**
 * What the Horatio bot lacks on the connected server of all that adding it asks for
 * (#891), and a way to give it them: Discord's add-bot screen again, for that server
 * only, which updates the bot's role. Nothing when it has them all, or when Discord
 * wouldn't say (`lacks` is null).
 */
export function UpdateBotPermissions({ troupeId, lacks, canEdit }: { troupeId: string; lacks: string[] | null | undefined; canEdit: boolean }) {
  const update = useAction(async () => {
    const { url } = await unwrap(api.POST("/api/troupes/{troupe_id}/discord/invite", { params: { path: { troupe_id: troupeId } } }));
    window.location.assign(url);
  });
  if (!lacks?.length) return null;
  return (
    <div className="flex flex-col items-start gap-2 rounded-md border border-gold/40 bg-gold/10 px-3 py-2" role="status">
      <p>
        The Horatio bot lacks {listed(lacks)} on this server, which some of Horatio's features need.{" "}
        {canEdit
          ? "Updating its permissions takes you through Discord's add-bot screen again, for this server only; you can untick any you'd rather not give."
          : "A storyteller who sets up connectors can update them."}{" "}
        <Link to={manualLink("running-a-troupe", "adding-the-horatio-bot")} className="underline hover:text-parchment">
          What each is for
        </Link>
      </p>
      {canEdit && (
        <Button type="button" variant="secondary" className="min-h-8 px-3 text-xs" onClick={() => update.mutate(undefined)} disabled={update.isPending}>
          Update the bot's permissions
        </Button>
      )}
      <ErrorText error={update.error} />
    </div>
  );
}
