import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap } from "../../api/client";
import type { components } from "../../api/schema";
import { Button, Card, Empty, ErrorText, Loaded } from "../../components/ui";
import { useToast } from "../../components/Toast";
import { useDates } from "../../dates";
import { useAction } from "../../hooks";

type Throttled = components["schemas"]["ThrottledOut"];

const THROTTLED = ["throttled"];
// How often the card asks again while on screen (#1095), as limits clear by themselves.
const REFRESH = 30_000;

/**
 * Who the limits on sign-ins and sign-ups hold back now (#1074): each address (and
 * login, for the limit at one login), the limit it is over and when that clears, with
 * Unblock to let it try again at once. An address shows in full only while sign-in
 * events keep IP addresses; otherwise only its start, and Unblock still works.
 * Wrong second-step codes and password changes are limited at an account, from
 * anywhere: those name the account.
 *
 * It asks again every half minute and when the window comes back into focus, but not
 * while an Unblock is on its way: that refreshes it when done.
 */
export function ThrottledCard() {
  const toast = useToast();
  const client = useQueryClient();
  const unblock = useAction(
    async (id: string) => {
      // A refresh already on its way would change the list under it.
      await client.cancelQueries({ queryKey: THROTTLED });
      return unwrap(api.POST("/api/throttled/unblock", { body: { id } }));
    },
    [THROTTLED, ["audit"]],
  );
  const held = useQuery({
    queryKey: THROTTLED,
    queryFn: () => unwrap(api.GET("/api/throttled")),
    refetchInterval: unblock.isPending ? false : REFRESH,
    refetchOnWindowFocus: !unblock.isPending,
  });

  return (
    <Card title="Throttled now">
      <Loaded query={held}>
        {(found) =>
          found.length ? (
            <div className="flex flex-col gap-2 text-sm">
              <p className="text-mist">
                Held back for too many tries from one place, or too many wrong
                second-step codes or password changes at one account. Each may
                try again once its limit clears, or at once if you unblock it.
              </p>
              <ul className="divide-y divide-ash/50" aria-label="Throttled now">
                {found.map((throttled) => (
                  <Row
                    key={throttled.id}
                    throttled={throttled}
                    busy={unblock.isPending}
                    onUnblock={() =>
                      unblock.mutate(throttled.id, {
                        onSuccess: () =>
                          toast({
                            message: "Unblocked. It may try again now.",
                          }),
                      })
                    }
                  />
                ))}
              </ul>
              {found.some((t) => t.masked) && (
                <p className="text-mist">
                  Addresses show in full only while Record IP addresses with
                  sign-in events is ticked, on the Audit log card.
                </p>
              )}
            </div>
          ) : (
            <Empty>No one is held back now.</Empty>
          )
        }
      </Loaded>
      <ErrorText error={unblock.error} />
    </Card>
  );
}

function Row({
  throttled,
  busy,
  onUnblock,
}: {
  throttled: Throttled;
  busy: boolean;
  onUnblock: () => void;
}) {
  const dates = useDates();
  // Wrong second-step codes are also limited at the account, from anywhere (#1057);
  // password changes only there, so they show the account alone (#1095).
  const account = throttled.held === "second_step" || throttled.held === "password_change";
  const login = throttled.login ?? (account ? "an account no longer here" : "a login no account uses");
  const alone = throttled.held === "password_change";
  const address = alone ? login : throttled.anywhere ? "Anywhere" : (throttled.address ?? "No address");
  const atLogin = throttled.per_login && !alone;
  const what = {
    sign_up: "Sign-ups",
    sign_in: "Sign-ins",
    second_step: "Second-step codes",
    password_change: "Password changes",
  }[throttled.held];
  return (
    <li className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 py-2">
      <div className="min-w-0">
        <p className="break-words text-parchment">
          <span className={throttled.anywhere ? undefined : "font-mono"}>{address}</span>
          {atLogin && <> at {login}</>}
        </p>
        <p className="text-xs text-mist">
          {what} over the limit of {throttled.limit}. Clears {dates.dateTime(throttled.clears)}.
        </p>
      </div>
      <Button type="button" variant="secondary" disabled={busy} aria-label={`Unblock ${address}${atLogin ? ` at ${login}` : ""}`} onClick={onUnblock}>
        Unblock
      </Button>
    </li>
  );
}
