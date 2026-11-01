import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router";
import { api, unwrap } from "../../api/client";
import type { GameNight } from "../../api/types";
import { Dialog } from "../../components/Dialog";
import { EmptyState } from "../../components/EmptyState";
import { QrCode } from "../../components/QrCode";
import { useToast } from "../../components/Toast";
import { Badge, Button, Card, ErrorText, Field, Input, Loading, Select } from "../../components/ui";
import { useDates } from "../../dates";
import { useAction } from "../../hooks";
import { checkInUrl, names, pastMonthly, spacedCode, toAward } from "./checkin";
import { Stepper } from "./XpAwardsTab";

/**
 * One game's night, for the troupe's running staff (issue #421): check-in at the
 * door with its code and QR code, who came (checked in or out by hand), and the
 * game's XP for everyone there in one go.
 */
export function GameNightPage({ troupeId }: { troupeId: string }) {
  const { gameId = "" } = useParams();
  const dates = useDates();
  const night = useQuery({
    queryKey: ["game-night", gameId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/games/{game_id}/night", { params: { path: { troupe_id: troupeId, game_id: gameId } } })),
  });
  if (night.isPending) return <Loading />;
  if (night.error) return <ErrorText error={night.error} />;
  const n = night.data;
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <Link to={`/troupes/${troupeId}`} className="self-start text-sm text-mist underline hover:text-parchment">
          Back to About
        </Link>
        <h2 className="font-display text-xl text-gold">Game night</h2>
        <time dateTime={n.starts_at} className="text-sm text-parchment">
          {dates.game(n.starts_at, n.ends_at)}
        </time>
      </div>
      <div className="grid gap-6 md:grid-cols-2">
        <DoorCard night={n} />
        <AttendanceCard night={n} />
        {n.can_award && <AwardCard night={n} />}
      </div>
    </div>
  );
}

function usePath(night: GameNight) {
  return { params: { path: { troupe_id: night.troupe_id, game_id: night.id } } };
}

/** Check-in at the door: open it, show its code and QR code, make a new code, close it. */
function DoorCard({ night }: { night: GameNight }) {
  const dates = useDates();
  const toast = useToast();
  const path = usePath(night);
  const [showing, setShowing] = useState(false);
  const open = useAction(
    async (fresh: boolean) => {
      await unwrap(api.PUT("/api/troupes/{troupe_id}/games/{game_id}/checkin", path));
      toast({ message: fresh ? "New code made. The old one no longer works." : "Check-in is open." });
    },
    [["game-night", night.id]],
  );
  const close = useAction(
    async () => {
      await unwrap(api.DELETE("/api/troupes/{troupe_id}/games/{game_id}/checkin", path));
      toast({ message: "Check-in closed. You can still check people in by hand." });
    },
    [["game-night", night.id]],
  );
  const over = new Date(night.ends_at) <= new Date();
  const { code } = night.checkin;
  const url = code ? checkInUrl(window.location.origin, code) : "";
  const typeAt = `${window.location.host}/check-in`;

  return (
    <Card title="Check-in at the door" className="md:col-span-2">
      {code ? (
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start">
          <QrCode text={url} label={`QR code for check-in, code ${spacedCode(code)}`} className="w-48 self-center sm:self-start" />
          <div className="flex flex-col gap-3 text-sm">
            <p>
              <span className="text-mist">Code</span>
              <br />
              <span className="font-mono text-3xl tracking-widest text-parchment" aria-label={`Code ${code.split("").join(" ")}`}>
                {spacedCode(code)}
              </span>
            </p>
            <p className="text-mist">
              Players scan it with their phone's camera, or type the code at <span className="text-parchment">{typeAt}</span>, then pick who they're playing. Their
              night starts on the Play View. They can also tap Check in on the troupe's About tab.
            </p>
            <div className="flex flex-wrap gap-2">
              <Button type="button" onClick={() => setShowing(true)}>
                Show at the door
              </Button>
              <Button type="button" variant="secondary" disabled={open.isPending} onClick={() => open.mutate(true)}>
                New code
              </Button>
              <Button type="button" variant="ghost" disabled={close.isPending} onClick={() => close.mutate(undefined)}>
                Close check-in
              </Button>
            </div>
          </div>
          <Dialog title="Check in" open={showing} onClose={() => setShowing(false)} phoneFull>
            <div className="flex flex-col items-center gap-4 text-center">
              <QrCode text={url} label={`QR code for check-in, code ${spacedCode(code)}`} className="w-full max-w-80" />
              <p className="font-mono text-4xl tracking-widest text-parchment">{spacedCode(code)}</p>
              <p className="text-sm text-mist">
                Scan with your phone's camera, or go to <span className="text-parchment">{typeAt}</span> and type the code.
              </p>
            </div>
          </Dialog>
        </div>
      ) : night.xp.amount !== null ? (
        <p className="text-sm text-mist">Check-in closed when the game's XP was awarded.</p>
      ) : over ? (
        <p className="text-sm text-mist">This game is over. You can still check characters in by hand, for the record.</p>
      ) : night.checkin.can_open ? (
        <div className="flex flex-col gap-3 text-sm">
          <p className="text-mist">
            Opening check-in gives the door a code and a QR code. Players scan it, or tap Check in on the troupe's About tab, and pick who they're playing. Their night starts
            on the Play View: Willpower full after a day's rest, and Blood as the troupe's settings say.
          </p>
          <Button type="button" className="self-start" disabled={open.isPending} onClick={() => open.mutate(false)}>
            Open check-in
          </Button>
        </div>
      ) : (
        <p className="text-sm text-mist">Check-in opens {dates.deadline(night.checkin.opens_at)}, 12 hours before the game starts.</p>
      )}
      <ErrorText error={open.error ?? close.error} />
    </Card>
  );
}

/** Who came, each checked out by hand if need be, and anyone else checked in by hand. */
function AttendanceCard({ night }: { night: GameNight }) {
  const toast = useToast();
  const path = usePath(night);
  const [chosen, setChosen] = useState("");
  const [rested, setRested] = useState(true);
  const awarded = night.xp.amount !== null;
  const notYet = new Date(night.checkin.opens_at) > new Date();
  const checkIn = useAction(
    async () => {
      const done = await unwrap(api.POST("/api/troupes/{troupe_id}/games/{game_id}/attendance", { ...path, body: { character_id: chosen, rested } }));
      toast({ message: `Checked in: ${done.character_name}` });
      setChosen("");
      setRested(true);
    },
    [["game-night", night.id]],
  );
  const checkOut = useAction(
    async ({ id, name }: { id: string; name: string }) => {
      await unwrap(
        api.DELETE("/api/troupes/{troupe_id}/games/{game_id}/attendance/{character_id}", {
          params: { path: { ...path.params.path, character_id: id } },
        }),
      );
      toast({ message: `Checked out: ${name}` });
    },
    [["game-night", night.id]],
  );

  return (
    <Card title={`Who came (${night.attendees.length})`} className="md:col-span-2">
      <div className="flex flex-col gap-4">
        {night.attendees.length === 0 ? (
          <EmptyState title="Nobody has checked in yet.">Characters show here as their players check in, or as you check them in below.</EmptyState>
        ) : (
          <ul aria-label="Checked in" className="divide-y divide-ash border-y border-ash">
            {night.attendees.map((a) => (
              <li key={a.character_id} className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 py-2 text-sm">
                <span className="min-w-0">
                  <Link to={`/characters/${a.character_id}`} className="text-parchment hover:text-gold">
                    {a.character_name}
                  </Link>
                  <span className="ml-2 text-xs text-mist">{a.player.display_name}</span>
                  <span className="ml-2 inline-flex flex-wrap gap-1 align-middle">
                    {!a.home && <Badge>Visiting</Badge>}
                    {a.by_staff && <Badge>By hand</Badge>}
                    {a.rested === false && <Badge>No day's rest</Badge>}
                  </span>
                </span>
                <Button
                  type="button"
                  variant="ghost"
                  className="px-2"
                  disabled={awarded || checkOut.isPending}
                  aria-label={`Check out ${a.character_name}`}
                  onClick={() => checkOut.mutate({ id: a.character_id, name: a.character_name })}
                >
                  Check out
                </Button>
              </li>
            ))}
          </ul>
        )}
        {awarded ? (
          <p className="text-xs text-mist">The game's XP has been awarded, so who came is settled. Correct a character's award from its Experience tab.</p>
        ) : notYet ? null : night.others.length === 0 ? (
          night.attendees.length > 0 && <p className="text-xs text-mist">Everyone in the troupe is checked in.</p>
        ) : (
          <form
            className="flex flex-col gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              if (chosen) checkIn.mutate(undefined);
            }}
          >
            <div className="flex flex-wrap items-end gap-3">
              <div className="min-w-60 flex-1">
                <Field label="Check someone in by hand">
                  <Select value={chosen} onChange={(e) => setChosen(e.target.value)}>
                    <option value="">Choose a character…</option>
                    {night.others.map((o) => (
                      <option key={o.character_id} value={o.character_id}>
                        {o.character_name} ({o.player_name})
                      </option>
                    ))}
                  </Select>
                </Field>
              </div>
              <Button type="submit" variant="secondary" disabled={!chosen || checkIn.isPending}>
                Check in
              </Button>
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={rested} onChange={(e) => setRested(e.target.checked)} />
              Had a full day's rest
              <span className="text-xs text-mist">(Willpower starts full)</span>
            </label>
          </form>
        )}
        <ErrorText error={checkIn.error ?? checkOut.error} />
      </div>
    </Card>
  );
}

/** The game's XP for everyone there whose home this troupe is, once, with the book's guidance and the monthly warning. */
function AwardCard({ night }: { night: GameNight }) {
  const dates = useDates();
  const toast = useToast();
  const path = usePath(night);
  const [amount, setAmount] = useState(night.session_xp);
  const [reason, setReason] = useState(`Game, ${dates.dueDay(night.starts_at)}`);
  const [toRange, setToRange] = useState(true);
  const [confirming, setConfirming] = useState(false);
  const getting = toAward(night.attendees);
  const visitors = night.attendees.filter((a) => !a.home).map((a) => a.character_name);
  const past = pastMonthly(night.attendees, amount, night.monthly_xp);
  const started = new Date(night.starts_at) <= new Date();
  const award = useAction(
    async () => {
      const done = await unwrap(api.POST("/api/troupes/{troupe_id}/games/{game_id}/xp", { ...path, body: { amount, reason, to_range: toRange } }));
      setConfirming(false);
      toast({
        message:
          `Awarded ${amount} XP to ${done.characters} character${done.characters === 1 ? "" : "s"}.` +
          (done.past_monthly.length ? ` ${names(done.past_monthly)} now ${done.past_monthly.length === 1 ? "has" : "have"} more than ${night.monthly_xp} this month.` : ""),
      });
    },
    [["game-night", night.id]],
  );
  const guidance = (
    <p className="text-xs text-mist">
      The book suggests {night.game_xp_low} to {night.game_xp_high} XP a game, and no more than 8 to {night.monthly_xp} a month (MET: VtM core, p. 108).
    </p>
  );

  if (night.xp.amount !== null)
    return (
      <Card title="The game's XP" className="md:col-span-2">
        <p className="text-sm">
          {night.xp.amount} XP awarded to everyone here who calls this troupe home
          {night.xp.awarded_at && <> on {dates.dateTime(night.xp.awarded_at)}</>}
          {night.xp.awarded_by && <> by {night.xp.awarded_by.display_name}</>}.
        </p>
      </Card>
    );

  return (
    <Card title="Award the game's XP" className="md:col-span-2">
      <form
        className="flex flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          if (confirming) award.mutate(undefined);
          else setConfirming(true);
        }}
      >
        {guidance}
        {!started ? (
          <p className="text-sm text-mist">Award it once the game has started.</p>
        ) : getting.length === 0 ? (
          <EmptyState title="Nobody to award yet.">
            {visitors.length ? "Only visitors have checked in, and their home troupes award their XP." : "Everyone checked in whose home is this troupe gets the game's XP."}
          </EmptyState>
        ) : (
          <>
            <div className="flex flex-wrap items-end gap-4">
              <Field label="Everyone here gets">
                <Stepper
                  label="XP for the game"
                  value={amount}
                  onChange={(n) => {
                    setAmount(Math.max(1, n));
                    setConfirming(false);
                  }}
                />
              </Field>
              <div className="min-w-60 flex-1">
                <Field label="Note everyone gets" hint="The reason on each character's XP history.">
                  <Input
                    required
                    maxLength={500}
                    value={reason}
                    onChange={(e) => {
                      setReason(e.target.value);
                      setConfirming(false);
                    }}
                  />
                </Field>
              </div>
            </div>
            <p className="text-sm">
              {getting.length === 1 ? "1 character" : `${getting.length} characters`}: {names(getting.map((a) => a.character_name))}.
              {visitors.length > 0 && <span className="text-mist"> {names(visitors)} visiting: their home troupes award their XP.</span>}
            </p>
            {past.length > 0 && (
              <p role="alert" className="rounded-md border border-gold/50 px-3 py-2 text-sm text-gold">
                This takes {names(past)} past {night.monthly_xp} XP this month, more than the book suggests. You can still award it.
              </p>
            )}
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={toRange}
                onChange={(e) => {
                  setToRange(e.target.checked);
                  setConfirming(false);
                }}
              />
              Also add to floor and ceiling
            </label>
            <div className="flex flex-wrap items-center gap-3">
              {confirming ? (
                <>
                  <Button type="submit" disabled={award.isPending}>
                    Yes, award {amount} XP to {getting.length === 1 ? "1 character" : `${getting.length} characters`}
                  </Button>
                  <Button type="button" variant="ghost" onClick={() => setConfirming(false)}>
                    Back
                  </Button>
                </>
              ) : (
                <Button type="submit" disabled={!reason.trim()}>
                  Award…
                </Button>
              )}
            </div>
            {confirming && (
              <p role="status" className="text-sm text-gold">
                Each gets an award entry of {amount} XP for “{reason.trim()}”, once for this game, and check-in closes. A mistake can be corrected from the character's
                Experience tab.
                {toRange && ` The troupe's XP floor and ceiling go up by ${amount}.`}
              </p>
            )}
          </>
        )}
        <ErrorText error={award.error} />
      </form>
    </Card>
  );
}
