import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../../api/client";
import type { components } from "../../../api/schema";
import { Badge, Button, Card, Empty, ErrorText, Field, Select } from "../../../components/ui";
import { useAction } from "../../../hooks";
import { manualLink } from "../../../manualLink";

type NpcPicksFit = components["schemas"]["NpcPicksFit"];

const npcs = (n: number) => `${n} NPC${n === 1 ? "" : "s"}`;

/**
 * Fit the creation picks of one troupe's NPCs built without the wizard (#533), as
 * `python -m horatio.npc_picks` does on the server for every troupe: preview it, then
 * fit. Picks staff placed or took off by hand are kept, and fitting again changes nothing.
 */
export function FitNpcPicks() {
  const [troupeId, setTroupeId] = useState("");
  const troupes = useQuery({ queryKey: ["troupes"], queryFn: () => unwrap(api.GET("/api/troupes")) });
  const path = (id: string) => ({ params: { path: { troupe_id: id } } });
  const preview = useMutation({ mutationFn: (id: string) => unwrap(api.GET("/api/tools/npc-picks/{troupe_id}", path(id))) });
  const fit = useAction((id: string) => unwrap(api.POST("/api/tools/npc-picks/{troupe_id}", path(id))));
  const choose = (id: string) => {
    setTroupeId(id);
    preview.reset();
    fit.reset();
  };

  return (
    <Card title="Fit NPC creation picks">
      <p className="mb-3 text-sm text-mist">
        An NPC built without the wizard (built quickly, made sheeted from Stock, or imported from Yorick) has creation picks fitted to its sheet, so its starting
        dots are free as a player character's are. Every change to its sheet fits them again, but NPCs no one has changed since that came in still need fitting
        once. Picks staff placed or took off by hand are kept, and fitting again changes nothing.{" "}
        <Link to={manualLink("custodian", "fitting-npc-creation-picks")} className="text-gold hover:underline">
          How it works
        </Link>
      </p>
      <div className="flex flex-wrap items-end gap-3">
        <Field label="Troupe">
          <Select value={troupeId} onChange={(e) => choose(e.target.value)} className="max-w-md">
            <option value="">Choose a troupe…</option>
            {troupes.data?.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </Select>
        </Field>
        <Button
          type="button"
          variant="ghost"
          disabled={!troupeId || preview.isPending || fit.isPending}
          onClick={() => {
            fit.reset();
            preview.mutate(troupeId);
          }}
        >
          Preview
        </Button>
      </div>
      <ErrorText error={troupes.error ?? preview.error ?? fit.error} />
      {fit.data ? (
        <Outcome found={fit.data} done />
      ) : (
        preview.data && (
          <>
            <Outcome found={preview.data} done={false} />
            <div className="mt-3 flex flex-wrap items-center justify-end gap-3">
              {preview.data.changed === 0 && <p className="text-sm text-mist">Nothing to fit: every NPC's picks fit its sheet already.</p>}
              <Button type="button" disabled={preview.data.changed === 0 || fit.isPending} onClick={() => fit.mutate(preview.data.troupe_id)}>
                Fit {npcs(preview.data.changed)}
              </Button>
            </div>
          </>
        )
      )}
    </Card>
  );
}

/** What fitting would do (the preview) or did, NPC by NPC, and what it left alone. */
function Outcome({ found, done }: { found: NpcPicksFit; done: boolean }) {
  const label = done ? "Fitted" : "Preview";
  return (
    <section aria-label={label} className="mt-4 flex flex-col gap-3 text-sm">
      <p role={done ? "status" : undefined}>
        {done
          ? `Fitted. Of ${found.troupe_name}'s ${npcs(found.fitted.length)} built without the wizard, ${found.changed} changed.`
          : `Of ${found.troupe_name}'s ${npcs(found.fitted.length)} built without the wizard, ${found.changed} would change. Nothing has changed yet.`}
      </p>
      {found.fitted.length ? (
        <table aria-label={done ? "NPCs fitted" : "NPCs to fit"} className="w-full max-w-xl">
          <thead className="text-left text-xs text-mist">
            <tr>
              <th className="py-1 pr-3 font-normal">NPC</th>
              <th className="py-1 pr-3 font-normal">XP worth {done ? "before" : "now"} → after</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-ash/50">
            {found.fitted.map((n) => (
              <tr key={n.id}>
                <td className="py-1.5 pr-3">
                  <Link to={`/characters/${n.id}`} className="hover:text-gold">
                    {n.name}
                  </Link>
                </td>
                <td className="py-1.5 pr-3">
                  {n.xp_now} → {n.xp_after}
                  {!n.changed && (
                    <Badge className="ml-2" tone="mist">
                      Fitted already
                    </Badge>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="border-t border-ash font-semibold">
              <td className="py-1.5 pr-3">Total</td>
              <td className="py-1.5 pr-3">
                {found.xp_now} → {found.xp_after}
              </td>
            </tr>
          </tfoot>
        </table>
      ) : (
        <Empty>The troupe has no NPCs built without the wizard.</Empty>
      )}
      {found.skipped.length > 0 && (
        <div>
          <h3 className="mb-1 text-mist">Left as they are</h3>
          <ul className="divide-y divide-ash/50">
            {found.skipped.map((s) => (
              <li key={s.id} className="py-1.5">
                {s.name} <span className="text-mist">· {s.why}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
