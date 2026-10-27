import { api, unwrap } from "../../api/client";
import type { TroupeOut } from "../../api/types";
import { Card, ErrorText } from "../../components/ui";
import { useAction } from "../../hooks";

type PrintStatus = "all" | "negative" | "none";

const STATUS: { value: PrintStatus; label: string; meaning: string; text: string }[] = [
  { value: "all", label: "All", meaning: "The status each character carries into a game here, negative status marked out.", text: "all status" },
  {
    value: "negative",
    label: "Negative only",
    meaning: "Negative status must be shown with a sticker, badge or other obvious sign (p. 312).",
    text: "negative status only",
  },
  { value: "none", label: "None", meaning: "The space is left for stickers.", text: "no status" },
];

/** What the troupe's game badges print: the titles held here, and how much status. */
export function BadgeSetting({ troupe, canEdit }: { troupe: TroupeOut; canEdit: boolean }) {
  const save = useAction((body: { badge_titles?: boolean; badge_status?: PrintStatus }) =>
    unwrap(api.PATCH("/api/troupes/{troupe_id}", { params: { path: { troupe_id: troupe.id } }, body })),
  );
  const status = STATUS.find((o) => o.value === troupe.badge_status) ?? STATUS[0]!;
  return (
    <Card title="Badges">
      {!canEdit ? (
        <p className="text-sm">
          Badges print {troupe.badge_titles ? "titles" : "no titles"} and {status.text}.
        </p>
      ) : (
        <div className="flex flex-col gap-3 text-sm">
          <p className="text-mist">What the troupe's game badges print. There is always room for stickers.</p>
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={troupe.badge_titles} disabled={save.isPending} onChange={(e) => save.mutate({ badge_titles: e.target.checked })} />
            Print titles
          </label>
          <fieldset className="flex flex-col gap-2">
            <legend className="mb-1">Print status</legend>
            {STATUS.map((o) => (
              <label key={o.value} className="flex items-start gap-2">
                <input
                  type="radio"
                  name="badge-status"
                  className="mt-1"
                  checked={troupe.badge_status === o.value}
                  disabled={save.isPending}
                  onChange={() => save.mutate({ badge_status: o.value })}
                />
                <span>
                  {o.label}
                  <span className="block text-xs text-mist">{o.meaning}</span>
                </span>
              </label>
            ))}
          </fieldset>
          <ErrorText error={save.error} />
        </div>
      )}
    </Card>
  );
}
