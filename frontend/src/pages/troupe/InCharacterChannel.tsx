import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import { useToast } from "../../components/Toast";
import { ErrorText, Field, Loading, Select } from "../../components/ui";
import { useAction } from "../../hooks";
import { manualLink } from "../../manualLink";
import { FOR_RESULTS, lacking } from "./botPermissions";

/** What the bot needs in the In-Character channel: to post as an NPC through its webhook. */
export const FOR_IN_CHARACTER = [...FOR_RESULTS, "Manage Webhooks"];

/**
 * The troupe's In-Character channel on Discord (#884): a public channel for in-world
 * talk, where storytellers and assistants post as the troupe's NPCs from each NPC's
 * page. Only the choice of channel is here; it saves as soon as it is made, apart from
 * the connector's Save. Storytellers choose it, as they do the connectors.
 */
export function InCharacterChannel({ troupeId, canEdit }: { troupeId: string; canEdit: boolean }) {
  const toast = useToast();
  const found = useQuery({
    queryKey: ["in-character-channel", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/in-character-channel", { params: { path: { troupe_id: troupeId } } })),
  });
  const choose = useAction((channel: string | null) =>
    unwrap(api.PUT("/api/troupes/{troupe_id}/in-character-channel", { params: { path: { troupe_id: troupeId } }, body: { channel } })),
  );
  if (found.isPending) return <Loading />;
  if (found.error) return <ErrorText error={found.error} />;
  const { channels, channel, unavailable } = found.data;
  // No server to choose from: the rest of the Discord settings say why.
  if (unavailable) return null;
  return (
    <div className="flex flex-col gap-2">
      <Field
        label="In-Character channel"
        hint={
          <>
            A public channel for in-world talk. Storytellers and assistants post there as an NPC, under its name and picture, from the NPC's{" "}
            <strong>⋯</strong> menu.{" "}
            <Link to={manualLink("running-a-troupe", "posting-in-ic-chat-as-an-npc")} className="underline hover:text-parchment">
              More about IC chat
            </Link>
          </>
        }
      >
        <Select
          value={channel ?? ""}
          disabled={!canEdit || !found.data.can_change || choose.isPending}
          onChange={(e) =>
            choose.mutate(e.target.value || null, {
              onSuccess: () => toast({ message: e.target.value ? "In-Character channel chosen." : "No In-Character channel now." }),
            })
          }
        >
          <option value="">None</option>
          {channels.map((c) => (
            <option key={c.id} value={c.id}>
              #{c.name}
              {c.category ? ` (${c.category})` : ""}
              {c.private ? ", private" : ""}
            </option>
          ))}
        </Select>
      </Field>
      <Lacks channel={channels.find((c) => c.id === channel)} />
      <ErrorText error={choose.error} />
    </div>
  );
}

/** What the bot lacks in the chosen channel, if anything: without any of it, NPCs can't post there at all. */
function Lacks({ channel }: { channel: { name: string; missing?: string[] | null } | undefined }) {
  const names = lacking(channel?.missing, FOR_IN_CHARACTER);
  if (!channel || !names.length) return null;
  const list = names.length === 1 ? names[0] : `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
  return (
    <p className="text-xs text-blood-bright" role="status">
      The Horatio bot lacks {list} in #{channel.name}, so NPCs can't post there. Give it {names.length === 1 ? "that permission" : "those permissions"} in the
      channel's settings on Discord.
    </p>
  );
}
