import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { ApiError, api, unwrap } from "../../api/client";
import type { components } from "../../api/schema";
import { Badge, Button, ErrorText, Loading } from "../../components/ui";
import { useAction } from "../../hooks";

type Emoji = components["schemas"]["EmojiOut"];
type EmojiSymbol = components["schemas"]["EmojiSymbolOut"];
type Style = Emoji["style"];
type Group = EmojiSymbol["group"];

const GROUPS: { group: Group; title: string }[] = [
  { group: "clan", title: "Clans" },
  { group: "disc/sup", title: "Superior disciplines" },
  { group: "disc/inf", title: "Inferior disciplines" },
  { group: "path", title: "Paths" },
];

const STATUS: Record<
  string,
  { label: string; tone: "mist" | "gold" | "blood" }
> = {
  added: { label: "On the server", tone: "gold" },
  own: { label: "Horatio's own", tone: "mist" },
  queued: { label: "Waiting", tone: "mist" },
  removed: { label: "Removed", tone: "mist" },
  no_room: { label: "No room", tone: "blood" },
  name_taken: { label: "Name taken", tone: "blood" },
  failed: { label: "Failed", tone: "blood" },
};

/** The symbols to start with: those already added, in the order shown. */
function startingChoice(emoji: Emoji): string[] {
  return emoji.symbols.filter((s) => s.added).map((s) => s.key);
}

/**
 * The clan and discipline symbols as emoji on the troupe's Discord server (#870):
 * switched on by the troupe, in the cards' white-bordered style or plain; the
 * server's room for them; which to add, most wanted first, with shortcuts for the
 * troupe's own clans and disciplines; and Horatio's own emoji for what doesn't fit.
 */
export function DiscordEmoji({
  troupeId,
  canEdit,
}: {
  troupeId: string;
  canEdit: boolean;
}) {
  const found = useQuery({
    queryKey: ["discord-emoji", troupeId],
    queryFn: () =>
      unwrap(
        api.GET("/api/troupes/{troupe_id}/discord/emoji", {
          params: { path: { troupe_id: troupeId } },
        }),
      ),
    // While Horatio adds them, see it happen.
    refetchInterval: (q) => (q.state.data?.queued ? 5000 : false),
  });
  if (found.isPending) return <Loading />;
  // No server connected after all (it was disconnected meanwhile): nothing to offer.
  if (found.error instanceof ApiError && found.error.status === 409)
    return null;
  if (found.error) return <ErrorText error={found.error} />;
  return (
    <EmojiChoice troupeId={troupeId} emoji={found.data} canEdit={canEdit} />
  );
}

export function EmojiChoice({
  troupeId,
  emoji,
  canEdit,
}: {
  troupeId: string;
  emoji: Emoji;
  canEdit: boolean;
}) {
  // The switch moves at once, and back if saving fails.
  const [on, setOn] = useState(emoji.on);
  useEffect(() => setOn(emoji.on), [emoji.on]);
  const [chosen, setChosen] = useState<string[]>(() => startingChoice(emoji));
  const [removeOthers, setRemoveOthers] = useState(false);
  const change = useAction(
    (body: { on: boolean; style: Style; own: boolean }) =>
      unwrap(
        api.PUT("/api/troupes/{troupe_id}/discord/emoji", {
          params: { path: { troupe_id: troupeId } },
          body,
        }),
      ),
  );
  const push = useAction(() =>
    unwrap(
      api.POST("/api/troupes/{troupe_id}/discord/emoji/push", {
        params: { path: { troupe_id: troupeId } },
        body: { symbols: chosen, remove_others: removeOthers },
      }),
    ),
  );
  const settings = { on: emoji.on, style: emoji.style, own: emoji.own };
  const free = emoji.room
    ? Math.max(emoji.room.room - emoji.room.used, 0)
    : null;
  const toAdd = chosen.filter((k) => {
    const s = emoji.symbols.find((x) => x.key === k);
    return !s?.added || s.other_style;
  });
  const freed = removeOthers
    ? emoji.symbols.filter(
        (s) => s.added === "server" && !chosen.includes(s.key),
      ).length
    : 0;
  const over = free === null ? 0 : Math.max(toAdd.length - free - freed, 0);
  const toggle = (key: string) =>
    setChosen(
      chosen.includes(key) ? chosen.filter((k) => k !== key) : [...chosen, key],
    );
  const choose = (keys: string[]) =>
    setChosen([...chosen, ...keys.filter((k) => !chosen.includes(k))]);

  return (
    <section
      aria-label="Clan and discipline emoji"
      className="flex flex-col gap-2 rounded-md border border-ash p-3"
    >
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={on}
          disabled={!canEdit || change.isPending}
          onChange={(e) => {
            setOn(e.target.checked);
            change.mutate(
              { ...settings, on: e.target.checked },
              { onError: () => setOn(emoji.on) },
            );
          }}
        />
        Let Horatio add the clan and discipline symbols to the server as emoji
      </label>
      <p className="text-xs text-mist">
        Players can then write :brujah: or :aus_sup: in their own messages.
        Horatio only ever removes emoji it added itself.
      </p>
      {!emoji.fetched && (
        <p className="text-xs text-blood-bright">
          The custodian hasn't fetched the VTES symbols in this style yet
          (Custodian › Tools). There's nothing to add until they do.
        </p>
      )}
      {emoji.on && emoji.lacks && emoji.lacks.length > 0 && (
        <p className="text-xs text-blood-bright" role="status">
          To add emoji, the Horatio bot needs {emoji.lacks.join(" and ")} on the
          server. Give it to its role in Discord's Server Settings › Roles.
        </p>
      )}
      {emoji.on && (
        <>
          <fieldset
            disabled={!canEdit}
            className="flex flex-wrap gap-x-4 gap-y-1 text-sm"
          >
            <legend className="mb-1 font-sans text-xs tracking-wide text-mist uppercase">
              Style
            </legend>
            {(
              [
                ["png_wb", "White-bordered, as on the cards"],
                ["png", "Plain"],
              ] as [Style, string][]
            ).map(([style, words]) => (
              <label key={style} className="flex items-center gap-1.5">
                <input
                  type="radio"
                  name="emoji-style"
                  checked={emoji.style === style}
                  onChange={() => change.mutate({ ...settings, style })}
                />
                {words}
              </label>
            ))}
          </fieldset>
          {emoji.room ? (
            <p className="text-xs text-mist" role="status">
              The server has {free} of {emoji.room.room} emoji slots free
              (Server Boost level {emoji.room.boost}).
            </p>
          ) : (
            <p className="text-xs text-mist">
              Discord didn't say how much room the server has.
            </p>
          )}
          <label className="flex items-center gap-2 text-xs">
            <input
              type="checkbox"
              checked={emoji.own}
              disabled={!canEdit}
              onChange={(e) =>
                change.mutate({ ...settings, own: e.target.checked })
              }
            />
            For what doesn't fit, use Horatio's own emoji. Only Horatio's own
            posts can show them; players can't use them.
          </label>
          {canEdit && (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs text-mist">Choose:</span>
              <Button
                type="button"
                variant="ghost"
                className="min-h-8 px-2 text-xs"
                onClick={() => choose(emoji.clans)}
                disabled={!emoji.clans.length}
              >
                This troupe's clans
              </Button>
              <Button
                type="button"
                variant="ghost"
                className="min-h-8 px-2 text-xs"
                onClick={() => choose(emoji.disciplines)}
                disabled={!emoji.disciplines.length}
              >
                Disciplines in use
              </Button>
              <Button
                type="button"
                variant="ghost"
                className="min-h-8 px-2 text-xs"
                onClick={() => choose(emoji.symbols.map((s) => s.key))}
              >
                Everything
              </Button>
              <Button
                type="button"
                variant="ghost"
                className="min-h-8 px-2 text-xs"
                onClick={() => setChosen([])}
              >
                None
              </Button>
            </div>
          )}
          {GROUPS.map(({ group, title }) => {
            const listed = emoji.symbols.filter((s) => s.group === group);
            if (!listed.length) return null;
            const picked = listed.filter((s) => chosen.includes(s.key)).length;
            return (
              <details
                key={group}
                className="rounded border border-ash/60 px-2 py-1"
              >
                <summary className="cursor-pointer text-sm text-parchment">
                  {title}{" "}
                  <span className="text-xs text-mist">
                    ({picked} of {listed.length} chosen)
                  </span>
                </summary>
                <ul className="mt-1 grid gap-1 sm:grid-cols-2">
                  {listed.map((s) => (
                    <li
                      key={s.key}
                      className="flex flex-wrap items-center gap-2"
                    >
                      <label className="flex items-center gap-1.5">
                        <input
                          type="checkbox"
                          checked={chosen.includes(s.key)}
                          disabled={!canEdit}
                          onChange={() => toggle(s.key)}
                          aria-label={`${s.label} (:${s.name}:)`}
                        />
                        <img
                          src={`/api/vtes-symbols/${emoji.style}/${s.group}/${s.key.split("/").pop()}.png`}
                          alt=""
                          className="h-5 w-5"
                        />
                        {s.label}
                        <span className="font-mono text-xs text-mist">
                          :{s.name}:
                        </span>
                      </label>
                      {s.status && STATUS[s.status] && (
                        <span title={s.note ?? undefined}>
                          <Badge tone={STATUS[s.status]!.tone}>
                            {STATUS[s.status]!.label}
                          </Badge>
                        </span>
                      )}
                      {s.other_style && <Badge>Other style</Badge>}
                    </li>
                  ))}
                </ul>
              </details>
            );
          })}
          {canEdit && (
            <div className="flex flex-col gap-2">
              <label className="flex items-center gap-2 text-xs">
                <input
                  type="checkbox"
                  checked={removeOthers}
                  onChange={(e) => setRemoveOthers(e.target.checked)}
                />
                Remove the emoji Horatio added that aren't chosen now, to make
                room
              </label>
              {over > 0 && (
                <p className="text-xs text-blood-bright" role="status">
                  {over} of the {toAdd.length} to add won't fit: Horatio adds
                  them in the order chosen until the server is full
                  {emoji.own
                    ? ", then uses its own emoji for the rest"
                    : ", and lists the rest"}
                  .
                </p>
              )}
              <div>
                <Button
                  type="button"
                  variant="secondary"
                  className="min-h-8 px-3 text-xs"
                  onClick={() => push.mutate(undefined)}
                  disabled={push.isPending || !emoji.fetched}
                >
                  Add the chosen emoji
                </Button>
              </div>
            </div>
          )}
          {emoji.queued > 0 && (
            <p className="text-xs text-mist" role="status">
              Working through {emoji.queued}{" "}
              {emoji.queued === 1 ? "change" : "changes"}: Horatio adds a few at
              a time, as Discord allows.
            </p>
          )}
        </>
      )}
      <ErrorText error={change.error ?? push.error} />
    </section>
  );
}
