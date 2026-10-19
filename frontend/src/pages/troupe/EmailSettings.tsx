import { Field, Input } from "../../components/ui";

type Settings = Record<string, unknown>;

/**
 * Email comes from Horatio's own address to each player's account address;
 * replies go to the troupe's storytellers.
 */
export function EmailSettings({ settings, onChange }: { troupeId: string; settings: Settings; onChange: (settings: Settings) => void; canEdit: boolean }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <Field label="Replies go to" hint="The storytellers' address; players' replies reach it.">
        <Input type="email" value={(settings.reply_to as string) ?? ""} onChange={(e) => onChange({ ...settings, reply_to: e.target.value })} />
      </Field>
      <Field label="Test address" hint="Test mode sends every email here instead of to players.">
        <Input
          type="email"
          value={(settings.test_address as string) ?? ""}
          onChange={(e) => onChange({ ...settings, test_address: e.target.value })}
        />
      </Field>
    </div>
  );
}
