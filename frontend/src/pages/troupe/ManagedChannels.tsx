import { useEffect, useState } from "react";
import { api, unwrap } from "../../api/client";
import type { components } from "../../api/schema";
import { Badge, Button, ErrorText } from "../../components/ui";
import { useAction } from "../../hooks";

type Managed = components["schemas"]["ManagedOut"];
type ManagedCharacter = components["schemas"]["ManagedCharacter"];
type Outcome = components["schemas"]["OutcomeOut"];

function listed(names: string[]): string {
  return names.length === 1 ? names[0]! : `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}

/**
 * Character channels Horatio makes (#855): switched on by the troupe, with the
 * server's roles let into each (such as @sts), what the bot still needs on the
 * server, and making every character's channel at once.
 */
export function ManagedChannels({
  troupeId,
  managed,
  canEdit,
  without,
}: {
  troupeId: string;
  managed: Managed;
  canEdit: boolean;
  // How many characters have no channel yet.
  without: number;
}) {
  const [roles, setRoles] = useState<string[]>(managed.staff_roles);
  // The switch moves at once, and back if saving fails.
  const [on, setOn] = useState(managed.on);
  useEffect(() => setOn(managed.on), [managed.on]);
  const change = useAction((body: { on: boolean; staff_roles: string[] }) =>
    unwrap(api.PUT("/api/troupes/{troupe_id}/discord/managed", { params: { path: { troupe_id: troupeId } }, body })),
  );
  const every = useAction(() => unwrap(api.POST("/api/troupes/{troupe_id}/discord/channels", { params: { path: { troupe_id: troupeId } } })));
  const rolesChanged = roles.join() !== managed.staff_roles.join();
  const toggle = (id: string) => setRoles(roles.includes(id) ? roles.filter((r) => r !== id) : [...roles, id]);

  return (
    <section aria-label="Channels Horatio makes" className="flex flex-col gap-2 rounded-md border border-ash p-3">
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={on}
          disabled={!canEdit || change.isPending}
          onChange={(e) => {
            setOn(e.target.checked);
            change.mutate({ on: e.target.checked, staff_roles: roles }, { onError: () => setOn(managed.on) });
          }}
        />
        Let Horatio make each character's private channel
      </label>
      <p className="text-xs text-mist">
        Horatio makes a channel in a "Horatio · Characters" category, lets in the character's player, the roles below and the bot, and keeps everyone
        else out. A player known only by the Discord username they typed is let in once a storyteller confirms it's them.
      </p>
      {managed.on && managed.lacks && managed.lacks.length > 0 && (
        <p className="text-xs text-blood-bright" role="status">
          To make channels, the Horatio bot needs {listed(managed.lacks)} on the server. Give them to its role in Discord's Server Settings › Roles.
        </p>
      )}
      {managed.on && managed.can_invite === false && (
        <p className="text-xs text-mist">Without Create Invite, Horatio can't invite players who aren't on the server yet: you invite them.</p>
      )}
      {managed.on && (
        <fieldset disabled={!canEdit} className="flex flex-col gap-1">
          <legend className="mb-1 font-sans text-xs tracking-wide text-mist uppercase">Staff roles let into every channel</legend>
          {managed.roles.length === 0 && <p className="text-xs text-mist">Discord didn't list the server's roles.</p>}
          <div className="flex flex-wrap gap-x-4 gap-y-1">
            {managed.roles.map((r) => (
              <label key={r.id} className="flex items-center gap-1.5">
                <input type="checkbox" checked={roles.includes(r.id)} onChange={() => toggle(r.id)} />@{r.name}
              </label>
            ))}
          </div>
          {canEdit && rolesChanged && (
            <div>
              <Button type="button" variant="secondary" className="min-h-8 px-3 text-xs" onClick={() => change.mutate({ on: managed.on, staff_roles: roles })}>
                Save staff roles
              </Button>
            </div>
          )}
        </fieldset>
      )}
      {managed.on && canEdit && without > 0 && (
        <div className="flex flex-wrap items-center gap-3">
          <Button type="button" variant="secondary" className="min-h-8 px-3 text-xs" onClick={() => every.mutate(undefined)} disabled={every.isPending}>
            Make channels for every character without one
          </Button>
        </div>
      )}
      {managed.queued > 0 && (
        <p className="text-xs text-mist" role="status">
          Making {managed.queued} {managed.queued === 1 ? "channel" : "channels"}: Horatio makes a few at a time, as Discord allows.
        </p>
      )}
      <ErrorText error={change.error ?? every.error} />
    </section>
  );
}

/**
 * One character's channel as Horatio sees to it: make it, confirm the member a
 * typed username found, or what stands in the way.
 */
export function ManagedCharacterRow({
  troupeId,
  characterId,
  name,
  state,
  hasChannel,
  canEdit,
  onMade,
}: {
  troupeId: string;
  characterId: string;
  name: string;
  state: ManagedCharacter | undefined;
  hasChannel: boolean;
  canEdit: boolean;
  onMade: (channel: string) => void;
}) {
  const path = { params: { path: { troupe_id: troupeId, character_id: characterId } } };
  const done = (outcome: Outcome) => {
    if (outcome.status === "made" && outcome.channel) onMade(outcome.channel);
  };
  const make = useAction(() => unwrap(api.POST("/api/troupes/{troupe_id}/discord/characters/{character_id}/channel", path)));
  const answer = useAction((itsThem: boolean) =>
    unwrap(api.POST("/api/troupes/{troupe_id}/discord/characters/{character_id}/match", { ...path, body: { its_them: itsThem } })),
  );
  const match = state?.match;
  const showNote = state?.note && !(hasChannel && state.status === "made") && !match;
  return (
    <div className="flex w-full flex-col gap-1 pl-0 text-xs sm:pl-2">
      {state?.made && <Badge tone="gold">Made by Horatio</Badge>}
      {state?.discord === "typed" && !match && <span className="text-mist">Discord: @{state.username}, typed, not checked</span>}
      {match && (
        <div className="flex flex-wrap items-center gap-2" role="group" aria-label={`Confirm ${name}'s player on Discord`}>
          {match.avatar && <img src={match.avatar} alt="" className="h-6 w-6 rounded-full" />}
          <span>
            Is <span className="text-parchment">@{match.username}</span> ({match.display_name}) {name}'s player?
          </span>
          {canEdit && (
            <>
              <Button type="button" variant="secondary" className="min-h-8 px-2 text-xs" onClick={() => answer.mutate(true, { onSuccess: done })}>
                Yes, let them in
              </Button>
              <Button type="button" variant="ghost" className="min-h-8 px-2 text-xs" onClick={() => answer.mutate(false)}>
                No
              </Button>
            </>
          )}
        </div>
      )}
      {showNote && <span className={state?.status === "made" || state?.status === "ready" ? "text-mist" : "text-blood-bright"}>{state?.note}</span>}
      {canEdit && !hasChannel && !match && (
        <div>
          <Button
            type="button"
            variant="ghost"
            className="min-h-8 px-2 text-xs"
            aria-label={`Make a channel for ${name}`}
            onClick={() => make.mutate(undefined, { onSuccess: done })}
            disabled={make.isPending}
          >
            Make a channel
          </Button>
        </div>
      )}
      <ErrorText error={make.error ?? answer.error} />
    </div>
  );
}
