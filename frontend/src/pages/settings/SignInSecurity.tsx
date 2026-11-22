import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "../../api/client";
import type { components } from "../../api/schema";
import { useToast } from "../../components/Toast";
import { Badge, Button, Card, ErrorText, Loaded } from "../../components/ui";
import { useDates, type Dates } from "../../dates";
import { useAction } from "../../hooks";

type SignedInAt = components["schemas"]["SignedInAt"];
type RecentSignIn = components["schemas"]["RecentSignIn"];

const SESSIONS = ["account-sessions"];
const SIGN_INS = ["account-sign-ins"];

// The server writes a sign-in's last use at most every 5 minutes (horatio.auth.sessions).
const RECENTLY = 6 * 60_000;

/** When a sign-in was last used, in words: "Active in the last few minutes", as the
 * server notes it only every few minutes, or "Last active 3 Nov 2026, 14:05". */
export function lastActive(at: string | null, dates: Pick<Dates, "dateTime">, now = Date.now()): string | null {
  if (!at) return null;
  return now - Date.parse(at) < RECENTLY ? "Active in the last few minutes" : `Last active ${dates.dateTime(at)}`;
}

/** The second line of a sign-in: when it started, when it was last used, and where. */
export function sessionDetails(s: SignedInAt, dates: Pick<Dates, "dateTime">, now = Date.now()): string {
  const parts = [`Signed in ${dates.dateTime(s.signed_in_at)}`];
  const active = lastActive(s.last_active_at, dates, now);
  if (active) parts.push(active.charAt(0).toLowerCase() + active.slice(1));
  if (s.place) parts.push(`from ${s.place}`);
  return parts.join(", ");
}

/**
 * Where you're signed in (#1193): each sign-in still going, with the browser and system
 * it was started from, when, when it was last used and, while the custodian keeps
 * addresses with sign-ins, roughly where. **Sign out** ends one; **Sign out everywhere
 * else** ends all but this one. Neither asks for the password: they only take access
 * away, and someone who fears another has their sign-in must be able to act at once.
 */
export function SessionsCard() {
  const dates = useDates();
  const toast = useToast();
  const sessions = useQuery({ queryKey: SESSIONS, queryFn: () => unwrap(api.GET("/api/account/sessions")) });
  const signOut = useAction(
    async (s: SignedInAt) => {
      await unwrap(api.POST("/api/account/sessions/{session_id}/sign-out", { params: { path: { session_id: s.id } } }));
      toast({ message: `Signed out on ${s.device}.` });
    },
    [SESSIONS, SIGN_INS],
  );
  const everywhereElse = useAction(async () => {
    const { ended } = await unwrap(api.POST("/api/account/sessions/sign-out-others"));
    toast({ message: ended === 1 ? "Signed out on 1 other device." : `Signed out on ${ended} other devices.` });
  }, [SESSIONS, SIGN_INS]);

  return (
    <Card title="Where you're signed in">
      <Loaded query={sessions}>
        {(all) => {
          const others = all.filter((s) => !s.this_device);
          return (
            <div className="flex flex-col gap-3 text-sm">
              <ul className="divide-y divide-ash/50">
                {all.map((s) => (
                  <li key={s.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                    <div className="min-w-0">
                      <span className="text-parchment">{s.device}</span> {s.this_device && <Badge tone="gold">This device</Badge>}
                      <span className="block text-mist">{sessionDetails(s, dates)}</span>
                    </div>
                    {!s.this_device && (
                      <Button
                        type="button"
                        variant="ghost"
                        className="min-h-8 px-2"
                        aria-label={`Sign out on ${s.device}, signed in ${dates.dateTime(s.signed_in_at)}`}
                        disabled={signOut.isPending}
                        onClick={() => signOut.mutate(s)}
                      >
                        Sign out
                      </Button>
                    )}
                  </li>
                ))}
              </ul>
              {others.length > 0 ? (
                <Button type="button" variant="secondary" className="self-start" disabled={everywhereElse.isPending} onClick={() => everywhereElse.mutate(undefined)}>
                  Sign out everywhere else
                </Button>
              ) : (
                <p className="text-mist">You're signed in only here.</p>
              )}
              <ErrorText error={signOut.error ?? everywhereElse.error} />
            </div>
          );
        }}
      </Loaded>
    </Card>
  );
}

const OUTCOME: Record<RecentSignIn["outcome"], { label: string; tone: "mist" | "gold" | "blood" }> = {
  signed_in: { label: "Signed in", tone: "mist" },
  failed: { label: "Failed", tone: "blood" },
  turned_away: { label: "Turned away", tone: "blood" },
};

/**
 * Recent sign-ins (#1193): the last ten sign-ins at your account, and the tries that
 * failed or were turned away, from the audit log, with roughly where while the
 * custodian keeps addresses. Signing in is a routine event, kept only while the
 * custodian records those; the card says so when they don't.
 */
export function RecentSignInsCard() {
  const dates = useDates();
  const recent = useQuery({ queryKey: SIGN_INS, queryFn: () => unwrap(api.GET("/api/account/sign-ins")) });
  return (
    <Card title="Recent sign-ins">
      <Loaded query={recent}>
        {({ sign_ins, all_kept }) => (
          <div className="flex flex-col gap-2 text-sm">
            {sign_ins.length > 0 ? (
              <ul className="divide-y divide-ash/50">
                {sign_ins.map((s, i) => (
                  <li key={`${s.at}-${i}`} className="flex flex-wrap items-center justify-between gap-2 py-2">
                    <div className="min-w-0">
                      <span className="text-parchment">{s.how}</span>
                      <span className="block text-mist">
                        {dates.dateTime(s.at)}
                        {s.place && `, from ${s.place}`}
                      </span>
                    </div>
                    <Badge tone={OUTCOME[s.outcome].tone}>{OUTCOME[s.outcome].label}</Badge>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-mist">None that Horatio's log keeps.</p>
            )}
            {!all_kept && (
              <p className="text-mist">
                Horatio's log keeps every sign-in only while the custodian asks it to, so this shows wrong second steps and tries turned away, but not each time you signed in.
              </p>
            )}
            <p className="text-mist">Something here that wasn't you? Change your password, then sign out everywhere else.</p>
          </div>
        )}
      </Loaded>
    </Card>
  );
}
