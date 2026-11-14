import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import {
  Badge,
  Button,
  ErrorText,
  Field,
  Loading,
  Notice,
  Select,
} from "../../components/ui";
import { useAction } from "../../hooks";
import { manualLink } from "../../manualLink";
import { BotLacks, FOR_RESULTS, lacking } from "./botPermissions";
import { DiscordEmoji } from "./DiscordEmoji";
import { ManagedCharacterRow, ManagedChannels } from "./ManagedChannels";
import { UpdateBotPermissions } from "./UpdateBotPermissions";

type Settings = Record<string, unknown>;

/**
 * The troupe's Discord server and channels: add the Horatio bot to the server,
 * then pick a private channel for each character and a test channel. A channel
 * named for a character is suggested, for storytellers to use or not; one already
 * chosen for someone else, or as the test channel, is not.
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
    queryFn: () =>
      unwrap(
        api.GET("/api/troupes/{troupe_id}/discord", {
          params: { path: { troupe_id: troupeId } },
        }),
      ),
    // While Horatio makes queued channels (#855), brings them into step or checks
    // them (#856), see it happen.
    refetchInterval: (q) => {
      const managed = q.state.data?.managed;
      return managed && (managed.queued || managed.syncing || managed.checking)
        ? 5000
        : false;
    },
  });
  const invite = useAction(async () => {
    const { url } = await unwrap(
      api.POST("/api/troupes/{troupe_id}/discord/invite", {
        params: { path: { troupe_id: troupeId } },
      }),
    );
    window.location.assign(url);
  });
  const disconnect = useAction(() =>
    unwrap(
      api.DELETE("/api/troupes/{troupe_id}/discord", {
        params: { path: { troupe_id: troupeId } },
      }),
    ),
  );
  // A channel Horatio made is saved already; it joins the choices here once, so a
  // later Save keeps it (and choosing "No channel" afterwards sticks).
  const joined = useRef(new Set<string>());
  const made = Object.entries(setup.data?.managed?.characters ?? {}).filter(
    ([, c]) => c.made && c.channel,
  );
  useEffect(() => {
    const current = (settings.channels ?? {}) as Record<string, string>;
    const fresh = made.filter(
      ([id, c]) =>
        !joined.current.has(`${id}:${c.channel}`) && current[id] !== c.channel,
    );
    made.forEach(([id, c]) => joined.current.add(`${id}:${c.channel}`));
    if (fresh.length)
      onChange({
        ...settings,
        channels: {
          ...current,
          ...Object.fromEntries(fresh.map(([id, c]) => [id, c.channel!])),
        },
      });
  });
  if (setup.isPending) return <Loading />;
  if (setup.error) return <ErrorText error={setup.error} />;
  const { guild_name, guild_id, channels, characters, suggestions, managed } =
    setup.data;
  const chosen = (settings.channels ?? {}) as Record<string, string>;
  const testChannel = (settings.test_channel as string | null) ?? "";
  const missing = characters.filter((c) => !chosen[c.id]);
  const taken = new Set(
    [...Object.values(chosen), testChannel].filter(Boolean),
  );
  const suggested = (characterId: string) => {
    const channel = suggestions[characterId];
    return channel && !chosen[characterId] && !taken.has(channel)
      ? channel
      : null;
  };
  const toSuggest = characters.filter((c) => suggested(c.id));
  const channelLabel = (id: string) => {
    const c = channels.find((ch) => ch.id === id);
    return c
      ? `#${c.name}${c.category ? ` (${c.category})` : ""}${c.private ? "" : " – anyone in the server can see it"}`
      : id;
  };

  if (!guild_id) {
    return (
      <div className="flex flex-col gap-2 text-sm">
        <p>
          No Discord server is connected. Add the Horatio bot to the troupe's
          server. It asks for every permission Horatio's features use; you can
          untick any you'd rather not give.
        </p>
        {canEdit && (
          <div>
            <Button
              type="button"
              variant="secondary"
              onClick={() => invite.mutate(undefined)}
              disabled={invite.isPending}
            >
              Add Horatio to your Discord
            </Button>
          </div>
        )}
        <ErrorText error={invite.error} />
      </div>
    );
  }

  const choose = (characterId: string, channel: string) =>
    onChange({ ...settings, channels: { ...chosen, [characterId]: channel } });
  const useAll = () =>
    onChange({
      ...settings,
      channels: {
        ...chosen,
        ...Object.fromEntries(toSuggest.map((c) => [c.id, suggestions[c.id]!])),
      },
    });

  return (
    <div className="flex flex-col gap-4 text-sm">
      <div className="flex flex-wrap items-center gap-3">
        <span>
          Connected to{" "}
          <span className="text-parchment">{guild_name ?? guild_id}</span>.
        </span>
        {canEdit && (
          <Button
            type="button"
            variant="ghost"
            className="min-h-8 px-2"
            onClick={() => disconnect.mutate(undefined)}
          >
            Disconnect
          </Button>
        )}
      </div>
      <UpdateBotPermissions
        troupeId={troupeId}
        lacks={setup.data.lacks}
        canEdit={canEdit}
      />
      <Notice>
        Each character's channel should be private: visible only to that player,
        the storytellers and the Horatio bot. Horatio warns where everyone in
        the server can see a channel, but cannot check every role's permissions.{" "}
        <Link
          to={manualLink("running-a-troupe", "connectors-discord-and-email")}
          className="underline hover:text-parchment"
        >
          How to set up the channels
        </Link>
      </Notice>
      <Field
        label="Test channel"
        hint="Test mode sends every result here instead of to players."
      >
        <Select
          value={testChannel}
          onChange={(e) =>
            onChange({ ...settings, test_channel: e.target.value || null })
          }
        >
          <option value="">None</option>
          {channels.map((c) => (
            <option key={c.id} value={c.id}>
              {channelLabel(c.id)}
            </option>
          ))}
        </Select>
      </Field>
      <BotLacks
        channel={channels.find((c) => c.id === testChannel)}
        needs={FOR_RESULTS}
        what="test results"
      />
      {managed && (
        <ManagedChannels
          troupeId={troupeId}
          managed={managed}
          canEdit={canEdit}
          without={missing.length}
        />
      )}
      <DiscordEmoji troupeId={troupeId} canEdit={canEdit} />
      <div>
        <h3 className="mb-1 font-sans text-xs tracking-wide text-mist uppercase">
          Each character's channel
        </h3>
        {missing.length > 0 && (
          <p className="mb-2 text-xs text-blood-bright">
            {missing.length}{" "}
            {missing.length === 1 ? "character has" : "characters have"} no
            channel: {missing.map((c) => c.name).join(", ")}. Until one is
            chosen, they get their results in Horatio (and by email, if it's
            on), but nothing on Discord.
          </p>
        )}
        {canEdit && toSuggest.length > 0 && (
          <div className="mb-2 flex flex-wrap items-center gap-3">
            <span className="text-xs text-mist">
              {toSuggest.length}{" "}
              {toSuggest.length === 1
                ? "channel matches a character's name"
                : "channels match characters' names"}
              .
            </span>
            <Button
              type="button"
              variant="secondary"
              className="min-h-8 px-3 text-xs"
              onClick={useAll}
            >
              Use the suggestions
            </Button>
          </div>
        )}
        <ul className="divide-y divide-ash">
          {characters.map((c) => (
            <li
              key={c.id}
              className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2"
            >
              <span className="min-w-32 flex-1 text-parchment">{c.name}</span>
              {chosen[c.id] &&
                !channels.find((ch) => ch.id === chosen[c.id])?.private && (
                  <Badge tone="blood">Not private</Badge>
                )}
              {lacking(
                channels.find((ch) => ch.id === chosen[c.id])?.missing,
                FOR_RESULTS,
              ).map((name) => (
                <Badge key={name} tone="blood">
                  Bot lacks {name}
                </Badge>
              ))}
              {canEdit && (
                <Suggestion
                  channel={channels.find((ch) => ch.id === suggested(c.id))}
                  who={c.name}
                  onUse={(id) => choose(c.id, id)}
                />
              )}
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
              {managed?.on && (
                <ManagedCharacterRow
                  troupeId={troupeId}
                  characterId={c.id}
                  name={c.name}
                  state={managed.characters[c.id]}
                  hasChannel={!!chosen[c.id]}
                  canEdit={canEdit}
                  onMade={(channel) => choose(c.id, channel)}
                />
              )}
            </li>
          ))}
        </ul>
      </div>
      <ErrorText error={disconnect.error} />
    </div>
  );
}

/** The channel a character's name suggests, to use with one tap. */
function Suggestion({
  channel,
  who,
  onUse,
}: {
  channel: { id: string; name: string } | undefined;
  who: string;
  onUse: (id: string) => void;
}) {
  if (!channel) return null;
  return (
    <span className="flex items-center gap-1.5 text-xs text-mist">
      Suggested: #{channel.name}
      <Button
        type="button"
        variant="ghost"
        className="min-h-8 px-2 text-xs"
        aria-label={`Use #${channel.name} for ${who}`}
        onClick={() => onUse(channel.id)}
      >
        Use
      </Button>
    </span>
  );
}
