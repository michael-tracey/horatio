import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "../../api/client";
import { Badge, Button, ErrorText, Field, Loading, Notice, Select } from "../../components/ui";
import { useAction } from "../../hooks";

type Settings = Record<string, unknown>;

/**
 * The troupe's Discord server and channels: add the Horatio bot to the server,
 * then pick a private channel for each character and a test channel.
 */
export function DiscordSettings({
  troupeId,
  settings,
  onChange,
  canEdit,
}: {
  troupeId: string;
  settings: Settings;
  onChange: (settings: Settings) => void;
  canEdit: boolean;
}) {
  const setup = useQuery({
    queryKey: ["discord", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/discord", { params: { path: { troupe_id: troupeId } } })),
  });
  const invite = useAction(async () => {
    const { url } = await unwrap(api.POST("/api/troupes/{troupe_id}/discord/invite", { params: { path: { troupe_id: troupeId } } }));
    window.location.assign(url);
  });
  const disconnect = useAction(() => unwrap(api.DELETE("/api/troupes/{troupe_id}/discord", { params: { path: { troupe_id: troupeId } } })));
  if (setup.isPending) return <Loading />;
  if (setup.error) return <ErrorText error={setup.error} />;
  const { guild_name, guild_id, channels, characters } = setup.data;
  const chosen = (settings.channels ?? {}) as Record<string, string>;
  const testChannel = (settings.test_channel as string | null) ?? "";
  const missing = characters.filter((c) => !chosen[c.id]);
  const channelLabel = (id: string) => {
    const c = channels.find((ch) => ch.id === id);
    return c ? `#${c.name}${c.category ? ` (${c.category})` : ""}${c.private ? "" : " – anyone in the server can see it"}` : id;
  };

  if (!guild_id) {
    return (
      <div className="flex flex-col gap-2 text-sm">
        <p>No Discord server is connected. Add the Horatio bot to the troupe's server; it only needs to see channels and send messages.</p>
        {canEdit && (
          <div>
            <Button type="button" variant="secondary" onClick={() => invite.mutate(undefined)} disabled={invite.isPending}>
              Add Horatio to your Discord
            </Button>
          </div>
        )}
        <ErrorText error={invite.error} />
      </div>
    );
  }

  const choose = (characterId: string, channel: string) => onChange({ ...settings, channels: { ...chosen, [characterId]: channel } });

  return (
    <div className="flex flex-col gap-4 text-sm">
      <div className="flex flex-wrap items-center gap-3">
        <span>
          Connected to <span className="text-parchment">{guild_name ?? guild_id}</span>.
        </span>
        {canEdit && (
          <Button type="button" variant="ghost" className="min-h-8 px-2" onClick={() => disconnect.mutate(undefined)}>
            Disconnect
          </Button>
        )}
      </div>
      <Notice>
        Each character's channel should be private: visible only to that player and the storytellers. Horatio warns where
        everyone in the server can see a channel, but cannot check every role's permissions.
      </Notice>
      <Field label="Test channel" hint="Test mode sends every result here instead of to players.">
        <Select value={testChannel} onChange={(e) => onChange({ ...settings, test_channel: e.target.value || null })}>
          <option value="">None</option>
          {channels.map((c) => (
            <option key={c.id} value={c.id}>
              {channelLabel(c.id)}
            </option>
          ))}
        </Select>
      </Field>
      <div>
        <h3 className="mb-1 font-sans text-xs tracking-wide text-mist uppercase">Each character's channel</h3>
        {missing.length > 0 && (
          <p className="mb-2 text-xs text-blood-bright">
            {missing.length} {missing.length === 1 ? "character has" : "characters have"} no channel: {missing.map((c) => c.name).join(", ")}. Their
            results will fail on Discord until one is chosen.
          </p>
        )}
        <ul className="divide-y divide-ash">
          {characters.map((c) => (
            <li key={c.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2">
              <span className="min-w-32 flex-1 text-parchment">{c.name}</span>
              {chosen[c.id] && !channels.find((ch) => ch.id === chosen[c.id])?.private && <Badge tone="blood">Not private</Badge>}
              <Select
                aria-label={`Discord channel for ${c.name}`}
                value={chosen[c.id] ?? ""}
                onChange={(e) => choose(c.id, e.target.value)}
                className="w-auto min-w-48"
              >
                <option value="">No channel</option>
                {channels.map((ch) => (
                  <option key={ch.id} value={ch.id}>
                    {channelLabel(ch.id)}
                  </option>
                ))}
              </Select>
            </li>
          ))}
        </ul>
      </div>
      <ErrorText error={disconnect.error} />
    </div>
  );
}
