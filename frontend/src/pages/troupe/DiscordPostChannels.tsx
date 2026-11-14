import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { AgencyOut, ChannelsOut } from "../../api/types";
import { useToast } from "../../components/Toast";
import { Badge, ErrorText, Field, Loading, Notice, Select } from "../../components/ui";
import { useAction } from "../../hooks";
import type { Kind } from "../news/posts";
import { useAgencies } from "../news/queries";
import { Masthead } from "../news/Story";
import { BotLacks, FOR_NEWS, FOR_POSTS } from "./botPermissions";

type Channel = ChannelsOut["channels"][number];

/** What each kind's channel says. */
const CHANNEL_WORDS = {
  news: {
    label: "The troupe's news channel",
    hint: "Stories from agencies without a channel of their own go here, as embeds. With none, news is in the app only.",
    what: "News",
  },
  announcement: {
    label: "The troupe's announcements channel",
    hint: "Announcements go here, as embeds, never in the news channel. With none, they're in the app only.",
    what: "Announcements",
  },
} as const;

function optionLabel(c: Channel): string {
  return `#${c.name}${c.category ? ` (${c.category})` : ""}${c.private ? ", private" : ""}`;
}

/**
 * The troupe's own channels on Discord (#882): its news channel and its
 * announcements channel (#511), chosen apart so the two never mix, and each news
 * agency's own channel (#510). Each is saved as it's chosen, apart from the
 * connector's Save, and the switches for downtime results don't apply to them.
 * Only storytellers choose, as they do the rest of the connectors.
 */
export function DiscordPostChannels({ troupeId }: { troupeId: string }) {
  const channels = useQuery({
    queryKey: ["post-channels", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/post-channels", { params: { path: { troupe_id: troupeId } } })),
  });
  const agencies = useAgencies(troupeId);
  return (
    <section aria-label="Channels for the whole troupe" className="flex flex-col gap-3 rounded-md border border-ash p-3">
      <div>
        <h3 className="font-sans text-xs tracking-wide text-mist uppercase">Channels for the whole troupe</h3>
        <p className="mt-1 text-xs text-mist">Where Horatio posts for everyone in the troupe. Each is saved as you choose it; the switches for downtime results don't apply here.</p>
      </div>
      {channels.error ? (
        <ErrorText error={channels.error} />
      ) : !channels.data ? (
        <Loading />
      ) : channels.data.unavailable ? (
        <Notice>{channels.data.unavailable} Until Horatio can see the server's channels, news and announcements are in the app only.</Notice>
      ) : (
        <>
          <PostChannel kind="news" troupeId={troupeId} channels={channels.data} />
          <PostChannel kind="announcement" troupeId={troupeId} channels={channels.data} />
          <div>
            <h4 className="mb-1 font-sans text-xs tracking-wide text-mist uppercase">Each news agency's channel</h4>
            {agencies.error ? (
              <ErrorText error={agencies.error} />
            ) : !agencies.data ? (
              <Loading />
            ) : agencies.data.length === 0 ? (
              <p className="text-xs text-mist">
                The troupe has no news agencies yet. They're added under{" "}
                <Link to={`/troupes/${troupeId}/news-agencies`} className="underline hover:text-parchment">
                  News agencies
                </Link>
                .
              </p>
            ) : (
              <ul aria-label="Each news agency's channel" className="divide-y divide-ash">
                {agencies.data.map((a) => (
                  <AgencyChannel key={a.id} agency={a} channels={channels.data} />
                ))}
              </ul>
            )}
          </div>
          {!channels.data.can_change && <p className="text-xs text-mist">Only storytellers choose channels.</p>}
        </>
      )}
    </section>
  );
}

/**
 * One channel picked from the server's text channels, with what the bot lacks in it.
 * `none` is what choosing no channel means.
 */
function ChannelChoice({
  label,
  hint,
  none,
  value,
  channels,
  disabled,
  onChoose,
  what,
  needs = FOR_POSTS,
}: {
  label: string;
  hint: string;
  none: string;
  value: string | null;
  channels: Channel[];
  disabled: boolean;
  onChoose: (channel: string | null) => void;
  what: string;
  /** The permissions to warn about; news also needs Manage Webhooks, to post as its agency (#883). */
  needs?: readonly string[];
}) {
  return (
    <div className="flex flex-col gap-1">
      <Field label={label} hint={hint}>
        <Select value={value ?? ""} disabled={disabled} onChange={(e) => onChoose(e.target.value || null)}>
          <option value="">{none}</option>
          {channels.map((c) => (
            <option key={c.id} value={c.id}>
              {optionLabel(c)}
            </option>
          ))}
          {value && !channels.some((c) => c.id === value) && <option value={value}>A channel no longer on the server</option>}
        </Select>
      </Field>
      <BotLacks channel={channels.find((c) => c.id === value)} needs={needs} what={what} />
    </div>
  );
}

/** The troupe's channel for a kind of post: for news, where every agency without its own posts; for announcements (#511), where they all go. */
function PostChannel({ kind, troupeId, channels }: { kind: Kind; troupeId: string; channels: ChannelsOut }) {
  const toast = useToast();
  const words = CHANNEL_WORDS[kind];
  const choose = useAction((channel: string | null) =>
    unwrap(api.PUT("/api/troupes/{troupe_id}/post-channels", { params: { path: { troupe_id: troupeId } }, body: { kind, channel } })),
  );
  return (
    <div className="flex flex-col gap-1">
      <ChannelChoice
        label={`${words.label}, on ${channels.server ?? "its server"}`}
        hint={words.hint}
        none="None: in the app only"
        value={kind === "news" ? channels.news : channels.announcements}
        channels={channels.channels}
        disabled={!channels.can_change || choose.isPending}
        onChoose={(channel) =>
          choose.mutate(channel, { onSuccess: () => toast({ message: channel ? "Channel chosen." : `${words.what} ${kind === "news" ? "is" : "are"} in the app only.` }) })
        }
        what={words.what.toLowerCase()}
        needs={kind === "news" ? FOR_NEWS : FOR_POSTS}
      />
      <ErrorText error={choose.error} />
    </div>
  );
}

/** A news agency's own channel, or none for the troupe's news channel. */
function AgencyChannel({ agency, channels }: { agency: AgencyOut; channels: ChannelsOut }) {
  const toast = useToast();
  // The agency's name, description and colour go back as they are: only its channel changes.
  const choose = useAction((channel: string | null) =>
    unwrap(
      api.PUT("/api/agencies/{agency_id}", {
        params: { path: { agency_id: agency.id } },
        body: { name: agency.name, description: agency.description, colour: agency.colour, discord_channel: channel },
      }),
    ),
  );
  const value = agency.discord_channel;
  return (
    <li className="flex flex-col gap-1 py-2">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="flex min-w-32 flex-1 flex-wrap items-center gap-2">
          <Masthead agency={agency} small />
          {agency.retired && <Badge>Retired</Badge>}
        </span>
        <Select
          aria-label={`${agency.name}'s channel`}
          className="w-auto min-w-48"
          value={value ?? ""}
          disabled={!channels.can_change || choose.isPending}
          onChange={(e) => {
            const channel = e.target.value || null;
            choose.mutate(channel, {
              onSuccess: () => toast({ message: channel ? `${agency.name}'s channel is chosen.` : `${agency.name}'s stories go to the troupe's news channel.` }),
            });
          }}
        >
          <option value="">The troupe's news channel</option>
          {channels.channels.map((c) => (
            <option key={c.id} value={c.id}>
              {optionLabel(c)}
            </option>
          ))}
          {value && !channels.channels.some((c) => c.id === value) && <option value={value}>A channel no longer on the server</option>}
        </Select>
      </div>
      <BotLacks channel={channels.channels.find((c) => c.id === value)} needs={FOR_NEWS} what="its stories" />
      <ErrorText error={choose.error} />
    </li>
  );
}
