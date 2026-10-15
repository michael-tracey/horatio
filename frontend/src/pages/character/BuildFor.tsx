import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "../../api/client";
import { Field, Select } from "../../components/ui";

const GENERIC = "";

/**
 * Which troupe a character is built for: its rules (house rules, specialisation
 * lists) apply until a home troupe accepts the character. Or the plain rule set,
 * to keep it in the vault and bring it to a troupe later.
 */
export function BuildFor({ value, onChange, disabled }: { value: string | null; onChange: (troupeId: string | null) => void; disabled?: boolean }) {
  const troupes = useQuery({ queryKey: ["troupes"], queryFn: () => unwrap(api.GET("/api/troupes")) });
  return (
    <Field label="Build for" hint="A troupe's own rules apply while you build; you can still change this until a troupe accepts the character.">
      <Select value={value ?? GENERIC} disabled={disabled} onChange={(e) => onChange(e.target.value || null)}>
        <option value={GENERIC}>Generic rules (in my vault)</option>
        {troupes.data?.map((t) => (
          <option key={t.id} value={t.id}>
            {t.name}
          </option>
        ))}
      </Select>
    </Field>
  );
}
