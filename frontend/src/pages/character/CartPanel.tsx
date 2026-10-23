import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";
import { api, unwrap } from "../../api/client";
import type { components } from "../../api/schema";
import type { CharacterOut } from "../../api/types";
import { Badge, Button, Card, ErrorText, Notice } from "../../components/ui";
import { useAction } from "../../hooks";
import { AskStaff } from "./AskStaff";
import { askException, costText, describe, toChange, type Cart, type CartLine } from "./cart";

type CartOut = components["schemas"]["CartOut"];

function post(characterId: string, lines: CartLine[], dryRun: boolean) {
  return unwrap(
    api.POST("/api/characters/{character_id}/cart", {
      params: { path: { character_id: characterId } },
      body: { changes: lines.map(toChange), dry_run: dryRun },
    }),
  );
}

const pricesKey = (characterId: string, lines: CartLine[]) => ["cart", characterId, lines];

/** What each line in the cart costs, or why it is refused, as the server would
 * make them now: asked again whenever the cart or the saved sheet changes. */
export function useCartPrices(characterId: string, lines: CartLine[]) {
  const prices = useQuery({
    queryKey: pricesKey(characterId, lines),
    queryFn: () => post(characterId, lines, true),
    enabled: lines.length > 0,
  });
  // Only an answer for these very lines.
  const data = prices.data && prices.data.lines.length === lines.length ? prices.data : undefined;
  return { ...prices, data, totals: data ? totals(data) : null };
}

export function totals(prices: CartOut) {
  const costs = prices.lines.map((l) => l.cost ?? 0);
  const spends = costs.filter((c) => c > 0).reduce((n, c) => n + c, 0);
  const refunds = -costs.filter((c) => c < 0).reduce((n, c) => n + c, 0);
  return {
    spends,
    refunds,
    net: spends - refunds,
    left: prices.balance - spends + refunds,
    refused: prices.lines.some((l) => l.refused !== null),
  };
}

/** Ask before leaving the page while the cart holds changes. */
export function useLeaveWarning(active: boolean) {
  useEffect(() => {
    if (!active) return;
    const warn = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [active]);
}

const plural = (n: number, one: string) => `${n} ${one}${n === 1 ? "" : "s"}`;

/**
 * The cart in the sheet's side panel: each change with what it costs, the
 * totals, and Spend XP (Apply picks during creation), which makes them all or
 * none.
 */
export function CartPanel({ character, cart, balance, creating }: { character: CharacterOut; cart: Cart; balance: number; creating: boolean }) {
  const prices = useCartPrices(character.id, cart.lines);
  const client = useQueryClient();
  const [message, setMessage] = useState<ReactNode>(null);
  // A refused line being asked of staff as an exception.
  const [asking, setAsking] = useState<CartLine | null>(null);
  const spend = useAction(async () => {
    const lines = cart.lines;
    const result = await post(character.id, lines, false);
    if (result.applied) {
      cart.clear();
      const net = totals(result).net;
      const waits = result.lines.some((l) => l.needs_approval);
      setMessage(
        <Notice>
          {creating ? "Picks applied." : net > 0 ? `Spent ${net} XP.` : net < 0 ? `Gained ${-net} XP.` : "Done."}
          {waits && " Some of it waits for the home troupe's approval."}
        </Notice>,
      );
    } else {
      client.setQueryData(pricesKey(character.id, lines), result);
      setMessage(<ErrorText error="Nothing was spent: a change was refused. It is marked below." />);
    }
    return result;
  });
  const t = prices.totals;
  const lines = cart.lines;
  const reason = !lines.length
    ? null
    : !t
      ? null
      : t.left < 0
        ? `That is ${-t.left} XP more than ${character.name} has.`
        : t.refused
          ? "A change can't be made; see the line marked."
          : null;

  return (
    <Card dense title="Cart" className="scroll-mt-4" actions={lines.length > 0 && <span className="text-xs text-mist">{plural(lines.length, "change")}</span>}>
      <div id="cart" className="flex flex-col gap-3">
        {lines.length === 0 ? (
          <>
            {message}
            <p className="text-sm text-mist">
              {creating
                ? "Picks you place or take back here wait in the cart until you apply them."
                : "Raise, lower, add or change traits and they wait here; nothing is spent until you press Spend XP."}
            </p>
          </>
        ) : (
          <>
            <ul aria-label="Changes in the cart" className="flex flex-col gap-2 text-sm">
              {lines.map((line, i) => {
                const priced = prices.data?.lines[i];
                const cost = costText(priced?.cost);
                const exception = line.kind === "set" ? line.exception : undefined;
                // Only a home troupe's staff can make an exception, and only to add or raise a trait.
                const askable = !!priced?.refused && !exception && line.kind === "set" && line.to > line.from && !!character.home_troupe_id;
                return (
                  <li key={`${describe(line)}/${i}`} className="flex flex-col gap-0.5">
                    <span className="flex items-start justify-between gap-2">
                      <span className={priced?.refused ? "text-blood-bright" : undefined}>
                        {describe(line)}
                        {cost && <span className="text-mist"> · {cost}</span>}
                      </span>
                      <span className="flex shrink-0 items-center gap-2">
                        {exception && <Badge tone="gold">exception</Badge>}
                        {priced?.needs_approval && <Badge tone="gold">needs approval</Badge>}
                        <button
                          aria-label={`Take ${describe(line)} out of the cart`}
                          className="h-6 w-6 rounded border border-ash text-xs leading-none text-mist hover:border-mist hover:text-parchment"
                          onClick={() => {
                            setMessage(null);
                            cart.remove(line);
                          }}
                        >
                          ×
                        </button>
                      </span>
                    </span>
                    {priced?.refused && <span className="text-xs text-blood-bright">{priced.refused}</span>}
                    {exception && (
                      <span className="text-xs text-mist">
                        Asked of staff{exception.free ? ", free" : ""}: {exception.reason}
                        {priced?.breaks.length ? <span className="block">Against the rules: {priced.breaks.join(" ")}</span> : null}
                      </span>
                    )}
                    {askable && asking !== line && (
                      <button type="button" className="self-start text-xs text-gold underline" onClick={() => setAsking(line)}>
                        Ask staff
                      </button>
                    )}
                    {askable && asking === line && (
                      <AskStaff
                        name={describe(line)}
                        refusal={priced?.refused ?? ""}
                        onCancel={() => setAsking(null)}
                        onAsk={(asked) => {
                          setAsking(null);
                          setMessage(null);
                          cart.update((ls) => askException(ls, line, asked));
                        }}
                      />
                    )}
                  </li>
                );
              })}
            </ul>
            {!creating && (
              <dl className="grid grid-cols-3 gap-2 border-t border-ash pt-2 text-center text-xs">
                <div>
                  <dt className="text-mist">Spends</dt>
                  <dd className="text-base">{t ? `${t.spends} XP` : "…"}</dd>
                </div>
                <div>
                  <dt className="text-mist">Refunds</dt>
                  <dd className="text-base">{t ? `${t.refunds} XP` : "…"}</dd>
                </div>
                <div>
                  <dt className="text-mist">Left</dt>
                  <dd className={t && t.left < 0 ? "text-base text-blood-bright" : "text-base text-gold"}>{t ? `${t.left} XP` : `${balance} XP`}</dd>
                </div>
              </dl>
            )}
            {message}
            {reason && <p className="text-xs text-blood-bright">{reason}</p>}
            <ErrorText error={prices.error ?? spend.error} />
            <div className="flex flex-wrap gap-2">
              <Button disabled={!t || !!reason || spend.isPending} onClick={() => spend.mutate(undefined)}>
                {creating ? "Apply picks" : "Spend XP"}
              </Button>
              <Button
                variant="ghost"
                onClick={() => {
                  setMessage(null);
                  cart.clear();
                }}
              >
                Clear
              </Button>
            </div>
          </>
        )}
      </div>
    </Card>
  );
}

/** On a phone the cart sits below the sheet: a bar at the foot of the screen says what is in it, and goes there. */
export function CartBar({ characterId, cart }: { characterId: string; cart: Cart }) {
  const prices = useCartPrices(characterId, cart.lines);
  if (!cart.lines.length) return null;
  const net = prices.totals?.net;
  const summary = `${plural(cart.lines.length, "change")}${net != null && net !== 0 ? ` · ${costText(net)}` : ""}`;
  return (
    <div className="fixed inset-x-0 bottom-0 z-20 border-t border-ash bg-night/95 px-4 py-2 backdrop-blur lg:hidden">
      <button
        aria-label={`${summary} · Review`}
        className="flex min-h-10 w-full items-center justify-between gap-2 text-sm"
        onClick={() => document.getElementById("cart")?.scrollIntoView({ behavior: "smooth", block: "center" })}
      >
        <span>{summary}</span>
        <span className="text-gold">Review</span>
      </button>
    </div>
  );
}

/**
 * Finish character creation. With changes still in the cart, it asks first
 * whether to apply them or drop them.
 */
export function FinishCreation({
  character,
  cart,
  disabled,
  children,
  className,
  onFinished,
}: {
  character: CharacterOut;
  cart: Cart;
  disabled?: boolean;
  children: ReactNode;
  className?: string;
  onFinished?: () => void;
}) {
  const [asking, setAsking] = useState(false);
  const finish = useAction(async (withCart: "apply" | "drop" | null) => {
    if (withCart === "apply") {
      const result = await post(character.id, cart.lines, false);
      const refused = result.lines.find((l) => l.refused)?.refused;
      if (!result.applied) throw new Error(`Nothing was applied: ${refused ?? "a change was refused"}`);
      cart.clear();
    }
    await unwrap(api.POST("/api/characters/{character_id}/creation/complete", { params: { path: { character_id: character.id } } }));
    if (withCart === "drop") cart.clear();
    setAsking(false);
    onFinished?.();
  });
  const pending = cart.lines.length > 0;
  return (
    <div className={className}>
      {asking && pending ? (
        <div className="flex flex-col gap-2">
          <Notice>
            {plural(cart.lines.length, "change")} in the cart {cart.lines.length === 1 ? "is" : "are"} not applied yet. Apply them, or drop them, before finishing?
          </Notice>
          <div className="flex flex-wrap gap-2">
            <Button disabled={finish.isPending} onClick={() => finish.mutate("apply")}>
              Apply them and finish
            </Button>
            <Button variant="secondary" disabled={finish.isPending} onClick={() => finish.mutate("drop")}>
              Drop them and finish
            </Button>
            <Button variant="ghost" onClick={() => setAsking(false)}>
              Cancel
            </Button>
          </div>
        </div>
      ) : (
        <Button disabled={disabled || finish.isPending} onClick={() => (pending ? setAsking(true) : finish.mutate(null))}>
          {children}
        </Button>
      )}
      <ErrorText error={finish.error} />
    </div>
  );
}
