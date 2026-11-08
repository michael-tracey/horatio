import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../../api/client";
import type { components } from "../../../api/schema";
import { Button, Card, ErrorText, Loading } from "../../../components/ui";
import { useDates } from "../../../dates";
import { useAction } from "../../../hooks";
import { manualLink } from "../../../manualLink";
import { FetchFailed, FetchForm, FetchProgress, NotSetUp, POLL, RemoveDialog, size, useRefreshWhenDone } from "./fetchParts";

type VtesSymbolsTool = components["schemas"]["VtesSymbolsTool"];
type Matched = components["schemas"]["Matched"];

const KINDS: Record<string, string> = { svg: "SVG", webp: "WebP", png: "PNG" };

/**
 * The symbols of Vampire: The Eternal Struggle from KRCG (#534), fetched for later:
 * nothing shows them yet. Wherever something does, it credits KRCG and gives
 * Paradox's notice, as the Dark Pack Agreement asks.
 */
export function VtesSymbols() {
  const state = useQuery({
    queryKey: ["tools", "vtes-symbols"],
    queryFn: () => unwrap(api.GET("/api/tools/vtes-symbols")),
    refetchInterval: (q) => (q.state.data?.job ? POLL : false),
  });
  const fetch = useAction((address: string) => unwrap(api.POST("/api/tools/vtes-symbols/fetch", { body: { address, accept_licence: true } })));
  const remove = useAction(() => unwrap(api.DELETE("/api/tools/vtes-symbols")));
  const [removing, setRemoving] = useState(false);
  const s = state.data;
  useRefreshWhenDone(!!s?.job);

  return (
    <Card
      title="VTES symbols"
      actions={
        s?.fetched && (
          <Button type="button" variant="danger" disabled={!!s.job || !s.writable} onClick={() => setRemoving(true)}>
            Remove
          </Button>
        )
      }
    >
      <p className="mb-3 text-sm text-mist">
        The clan and discipline symbols and game icons of <em>Vampire: The Eternal Struggle</em>, with its two fonts, from{" "}
        <a href="https://static.krcg.org/" target="_blank" rel="noreferrer" className="text-gold hover:underline">
          KRCG
        </a>
        , free to use under the Dark Pack Agreement. They're for later (cards of characters in the style of VTES, symbols beside clans and disciplines, Discord
        emoji): nothing shows them yet.{" "}
        <Link to={manualLink("custodian", "vtes-symbols")} className="text-gold hover:underline">
          How it works
        </Link>
      </p>
      {state.isPending ? (
        <Loading />
      ) : state.error ? (
        <ErrorText error={state.error} />
      ) : (
        <>
          <NotSetUp configured={s!.configured} writable={s!.writable} />
          <Status state={s!} />
          {s!.job && <FetchProgress job={s!.job} unit="files" />}
          {s!.error && <FetchFailed error={s!.error} at={s!.error_at} />}
          {s!.configured && s!.writable && (
            <>
              <FetchForm
                defaultAddress={s!.default_address}
                agreement={s!.agreement}
                disabled={!!s!.job}
                pending={fetch.isPending}
                label={s!.fetched ? "Fetch again" : "Fetch"}
                onFetch={(address) => fetch.mutate(address)}
              />
              <p className="mt-2 text-xs text-mist">
                A few hundred small files, fetched one at a time to be polite: a few minutes. What's here now stays until the new fetch is whole.
              </p>
              <ErrorText error={fetch.error} />
            </>
          )}
          <ErrorText error={remove.error} />
        </>
      )}
      <RemoveDialog
        title="Remove the VTES symbols?"
        open={removing}
        pending={remove.isPending}
        onClose={() => setRemoving(false)}
        onRemove={() => remove.mutate(undefined, { onSuccess: () => setRemoving(false) })}
      >
        The symbols and fonts come off the server now. Nothing shows them yet, so nothing else changes.
      </RemoveDialog>
    </Card>
  );
}

/** What is on the server now. */
function Status({ state }: { state: VtesSymbolsTool }) {
  const dates = useDates();
  if (!state.configured) return null;
  if (!state.fetched) return <p className="text-sm">Not on this server yet.</p>;
  return (
    <section aria-label="On the server" className="flex flex-col gap-3 text-sm">
      <p>
        Fetched {state.fetched_at ? dates.dateTime(state.fetched_at) : ""} from <span className="break-all text-mist">{state.address}</span>.
      </p>
      <table aria-label="Symbols" className="w-full max-w-xl">
        <thead className="text-left text-xs text-mist">
          <tr>
            <th className="py-1 pr-3 font-normal">Kind</th>
            <th className="py-1 pr-3 font-normal">Clans</th>
            <th className="py-1 pr-3 font-normal">Disciplines</th>
            <th className="py-1 pr-3 font-normal">Superior</th>
            <th className="py-1 pr-3 font-normal">Icons</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-ash/50">
          {state.counts.map((c) => (
            <tr key={c.kind}>
              <td className="py-1.5 pr-3">{KINDS[c.kind] ?? c.kind}</td>
              <td className="py-1.5 pr-3">{c.clans}</td>
              <td className="py-1.5 pr-3">{c.inferior}</td>
              <td className="py-1.5 pr-3">{c.superior}</td>
              <td className="py-1.5 pr-3">{c.icons}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p>Fonts: {state.fonts.join(", ") || "none"}.</p>
      <Matches label="Horatio's clans and bloodlines" found={state.clans} />
      <Matches label="Horatio's disciplines" found={state.disciplines} />
      {state.large_png.length > 0 && (
        <p className="text-mist">
          Over Discord's 256 KB for an emoji: {state.large_png.map((l) => `${l.path} (${size(l.size)})`).join(", ")}.
        </p>
      )}
    </section>
  );
}

/** Which of Horatio's names have a symbol, and which don't. */
function Matches({ label, found }: { label: string; found: Matched[] }) {
  const without = found.filter((m) => !m.symbol);
  return (
    <p>
      {label} with a symbol: {found.length - without.length} of {found.length}.
      {without.length > 0 && <span className="text-mist"> Without one: {without.map((m) => m.name).join(", ")}.</span>}
    </p>
  );
}
