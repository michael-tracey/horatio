import { useState } from "react";
import { api, unwrap } from "../api/client";
import type { LinesVeils } from "../api/types";
import { Button, Card, ErrorText, Input, Notice } from "../components/ui";
import { useAction } from "../hooks";

const MAX_ITEMS = 20;

/**
 * The player's own lines and veils, on Your account: what they don't want in their
 * games, in their own words, and whether other players in their troupes see them.
 * Saved on their own, so the profile form never wipes them.
 */
export function LinesVeilsForm({ value }: { value: LinesVeils }) {
  const [lines, setLines] = useState(value.lines);
  const [veils, setVeils] = useState(value.veils);
  const [shared, setShared] = useState(value.shared);
  const [saved, setSaved] = useState(false);
  const save = useAction(async () => {
    const kept = await unwrap(api.PUT("/api/profile/lines-veils", { body: { lines, veils, shared } }));
    setLines(kept.lines);
    setVeils(kept.veils);
    setShared(kept.shared);
    setSaved(true);
  });

  return (
    <form
      className="mt-6"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(undefined);
      }}
      onChange={() => setSaved(false)}
    >
      <Card title="Lines and veils">
        <div className="flex flex-col gap-4 text-sm">
          <div className="flex flex-col gap-2">
            <p>
              <strong>Lines and veils</strong> tell your storytellers, and other players if you choose, what you don’t want in your games.
            </p>
            <ul className="ml-5 list-disc">
              <li>
                A <strong>line</strong> is something that won’t happen in play around you at all.
              </li>
              <li>
                A <strong>veil</strong> can happen in the story, but off-screen: it fades to black, or is summed up rather than played out.
              </li>
            </ul>
            <p className="text-mist">
              Write them in your own words, e.g. “Line: harm to children”, “Veil: torture”. Your troupes’ staff always see them. Other players see
              them only if you turn on sharing below. You can change them at any time, and you never have to explain why. They are never public
              and never printed.
            </p>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <Items label="Lines" one="line" placeholder="e.g. spiders" items={lines} onChange={setLines} />
            <Items label="Veils" one="veil" placeholder="e.g. needles" items={veils} onChange={setVeils} />
          </div>
          <label className="flex items-start gap-2">
            <input type="checkbox" className="mt-1" checked={shared} onChange={(e) => setShared(e.target.checked)} />
            <span>
              Share my lines and veils with other players in my troupes
              <span className="block text-xs text-mist">
                {shared
                  ? "On: the other players in your troupes see them on the Who’s Who, as well as the staff."
                  : "Off: only the staff of the troupes you play in see them."}
              </span>
            </span>
          </label>
          <ErrorText error={save.error} />
          {saved && <Notice>Saved.</Notice>}
          <Button type="submit" disabled={save.isPending} className="self-start">
            Save lines and veils
          </Button>
        </div>
      </Card>
    </form>
  );
}

/** One list: a box for each, and a button to add another. */
function Items({
  label,
  one,
  placeholder,
  items,
  onChange,
}: {
  label: string;
  one: string;
  placeholder: string;
  items: string[];
  onChange: (items: string[]) => void;
}) {
  // An empty list still shows one box to write in.
  const shown = items.length ? items : [""];
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="mb-1 text-mist">{label}</legend>
      {shown.map((item, i) => (
        <div key={i} className="flex gap-2">
          <Input
            aria-label={`${label.slice(0, -1)} ${i + 1}`}
            className="min-w-0 flex-1"
            maxLength={100}
            placeholder={placeholder}
            value={item}
            onChange={(e) => onChange(shown.map((x, j) => (j === i ? e.target.value : x)))}
          />
          {items.length > 0 && (
            <Button type="button" variant="ghost" aria-label={`Remove ${one} ${i + 1}`} onClick={() => onChange(items.filter((_, j) => j !== i))}>
              Remove
            </Button>
          )}
        </div>
      ))}
      {shown.length < MAX_ITEMS && (
        <Button type="button" variant="secondary" className="self-start" onClick={() => onChange([...shown, ""])}>
          Add a {one}
        </Button>
      )}
    </fieldset>
  );
}
