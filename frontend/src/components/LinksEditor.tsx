import type { ProfileLink } from "../api/types";
import { Button, Field, Input } from "./ui";

/** The most links a profile shows: a player's, or a blog author's. */
export const MAX_LINKS = 6;

/**
 * Links someone gives about themself, each a label (such as Bluesky) and an address,
 * up to `MAX_LINKS`: a player's social media, or a blog author's links.
 */
export function LinksEditor({ links, onChange, full = "That's the most links a profile shows." }: { links: ProfileLink[]; onChange: (links: ProfileLink[]) => void; full?: string }) {
  const setLink = (i: number, change: Partial<ProfileLink>) => onChange(links.map((l, j) => (j === i ? { ...l, ...change } : l)));
  return (
    <>
      {links.map((link, i) => (
        <fieldset key={i} className="flex flex-col gap-2 rounded-md border border-ash p-3 sm:flex-row sm:items-end">
          <legend className="sr-only">Link {i + 1}</legend>
          <div className="sm:w-32">
            <Field label="Label">
              <Input placeholder="Bluesky" maxLength={40} value={link.label} onChange={(e) => setLink(i, { label: e.target.value })} />
            </Field>
          </div>
          <div className="min-w-0 flex-1">
            <Field label="Address">
              <Input type="url" required placeholder="https://" value={link.url} onChange={(e) => setLink(i, { url: e.target.value })} />
            </Field>
          </div>
          <Button type="button" variant="ghost" aria-label={`Remove link ${i + 1}`} onClick={() => onChange(links.filter((_, j) => j !== i))}>
            Remove
          </Button>
        </fieldset>
      ))}
      {links.length < MAX_LINKS ? (
        <Button type="button" variant="secondary" className="self-start" onClick={() => onChange([...links, { label: "", url: "" }])}>
          Add a link
        </Button>
      ) : (
        <p className="text-sm text-mist">{full}</p>
      )}
    </>
  );
}
