import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "../../api/client";
import { Field, Select } from "../../components/ui";

const GENERIC = "";

/**
 * Which troupe a character is built for: its rules (house rules, specialisation
 * lists) apply until a home troupe accepts the character. Or the plain rule set,
 * to keep it in the vault and bring it to a troupe later.
 */
export function BuildFor({
  value,
  onChange,
  disabled,
  newCharacter = false,
  splat,
}: {
  value: string | null;
  onChange: (troupeId: string | null) => void;
  disabled?: boolean;
  /** Say what XP a new character starts with: the troupe's XP floor, or the rule set's. */
  newCharacter?: boolean;
  /** Offer only the troupes that take characters of this splat (a ghoul's). */
  splat?: string;
}) {
  const troupes = useQuery({ queryKey: ["troupes"], queryFn: () => unwrap(api.GET("/api/troupes")) });
  const troupe = troupes.data?.find((t) => t.id === value);
  const offered = troupes.data?.filter((t) => !splat || t.id === value || t.allowed_splats.includes(splat));
  const start = !newCharacter ? "" : troupe ? ` It starts with ${troupe.xp_floor} XP, ${troupe.name}'s XP floor.` : " It starts with 30 XP.";
  // Left on the book's rules while there are troupes: say why choosing one matters.
  const why =
    value === null && !disabled && offered?.length
      ? "Building for a game? Choose its troupe so its house rules apply."
      : "A troupe's own rules apply while you build; you can still change this until a troupe accepts the character.";
  return (
    <Field label="Which troupe will you play in?" hint={`${why}${start}`}>
      <Select value={value ?? GENERIC} disabled={disabled} onChange={(e) => onChange(e.target.value || null)}>
        {offered?.map((t) => (
          <option key={t.id} value={t.id}>
            {t.name}
          </option>
        ))}
        <option value={GENERIC}>No troupe yet (book rules)</option>
      </Select>
    </Field>
  );
}
