import { useState } from "react";
import { Button, ErrorText, Field, Input } from "../../components/ui";
import { deviceScene, forgetDeviceScene } from "./scene";

/**
 * Before scenes were kept on the server, each browser kept one scene per troupe.
 * If this one still has one with characters in it, offer to save it as a named
 * scene. Saved or dismissed, the browser forgets it.
 */
export function SaveDeviceScene({
  troupeId,
  onSave,
  storage,
}: {
  troupeId: string;
  onSave: (name: string, characters: string[]) => Promise<unknown>;
  storage?: Storage;
}) {
  const [ids, setIds] = useState(() => deviceScene(troupeId, storage));
  const [name, setName] = useState("My scene");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<unknown>(null);
  if (ids.length === 0) return null;

  const forget = () => {
    forgetDeviceScene(troupeId, storage);
    setIds([]);
  };
  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      await onSave(name.trim() || "My scene", ids);
      forget();
    } catch (e) {
      setError(e);
    } finally {
      setSaving(false);
    }
  };
  return (
    <section aria-label="This device's scene" className="flex flex-col gap-3 rounded-lg border border-gold/50 bg-gold/10 p-3">
      <p className="text-sm">
        This device still has a scene of its own, with {ids.length === 1 ? "1 character" : `${ids.length} characters`}, from before scenes were kept for the troupe. Save it to keep it, on every device.
      </p>
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void save();
        }}
      >
        <div className="min-w-48 flex-1">
          <Field label="Name of the scene">
            <Input value={name} maxLength={80} onChange={(e) => setName(e.target.value)} />
          </Field>
        </div>
        <Button type="submit" disabled={saving}>
          Save this device's scene
        </Button>
        <Button type="button" variant="ghost" onClick={forget}>
          Dismiss
        </Button>
      </form>
      <ErrorText error={error} />
    </section>
  );
}
