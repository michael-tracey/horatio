import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router";
import type { ReactNode } from "react";
import { api, unwrap } from "../../api/client";
import type { ConnectorOut } from "../../api/types";
import { Badge, Button, Card, Empty, ErrorText, Field, Loading, Notice, Select } from "../../components/ui";
import { useToast } from "../../components/Toast";
import { useAction } from "../../hooks";
import { DiscordSettings } from "./DiscordSettings";
import { EmailSettings } from "./EmailSettings";

type Settings = Record<string, unknown>;

/** Each connector's own settings (a server, channels, a test target), by kind. */
export const SETTINGS_EDITORS: Record<
  string,
  (props: { troupeId: string; settings: Settings; onChange: (settings: Settings) => void; canEdit: boolean }) => ReactNode
> = {
  discord: DiscordSettings,
  email: EmailSettings,
};

/**
 * How downtime results reach players. They always appear in Horatio; each
 * connector the troupe switches on carries a copy, the whole result or an alert
 * with a link back.
 */
export function ConnectorsTab({ troupeId, canEdit }: { troupeId: string; canEdit: boolean }) {
  const [params] = useSearchParams();
  const discordOutcome = params.get("discord");
  const connectors = useQuery({
    queryKey: ["connectors", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/connectors", { params: { path: { troupe_id: troupeId } } })),
  });
  if (connectors.isPending) return <Loading />;
  if (connectors.error) return <ErrorText error={connectors.error} />;
  return (
    <div className="flex flex-col gap-4">
      {discordOutcome && (
        <Notice>
          {discordOutcome === "connected"
            ? "The Discord server is connected. Now choose each character's channel and switch Discord on."
            : discordOutcome === "cancelled"
              ? "Adding Horatio to Discord was cancelled."
              : `Discord could not be connected: ${discordOutcome}`}
        </Notice>
      )}
      <Card title="In Horatio" actions={<Badge tone="gold">always on</Badge>}>
        <p className="text-sm">
          Delivered results always appear on the character's Results tab, and the player's bell says they are ready.
        </p>
      </Card>
      {connectors.data.length === 0 && (
        <Card>
          <Empty>This server has no other connectors set up yet.</Empty>
        </Card>
      )}
      {connectors.data.map((c) => (
        <ConnectorCard key={c.kind} troupeId={troupeId} connector={c} canEdit={canEdit} />
      ))}
    </div>
  );
}

/** Where test mode sends everything, by kind. */
const TEST_TARGET: Record<string, string> = { discord: "the test channel", email: "the test address" };

/**
 * One connector, in a clear state: not set up on this server (nothing to fill in,
 * and who can set it up), off, or on. Its choices save together, with Save.
 */
function ConnectorCard({ troupeId, connector, canEdit }: { troupeId: string; connector: ConnectorOut; canEdit: boolean }) {
  const toast = useToast();
  const [enabled, setEnabled] = useState(connector.enabled);
  const [mode, setMode] = useState(connector.mode);
  const [testMode, setTestMode] = useState(connector.test_mode);
  const [settings, setSettings] = useState<Settings>(connector.settings);
  const save = useAction(() =>
    unwrap(
      api.PUT("/api/troupes/{troupe_id}/connectors/{kind}", {
        params: { path: { troupe_id: troupeId, kind: connector.kind } },
        body: { enabled, mode, test_mode: testMode, settings },
      }),
    ),
  );
  const Editor = SETTINGS_EDITORS[connector.kind];
  const state = connector.enabled ? (connector.test_mode ? "on, test mode" : "on") : connector.unavailable ? "not set up" : "off";

  // Not set up on this server: nothing here would work, so there is nothing to fill in;
  // unless it was switched on before, when it can still be switched off.
  if (connector.unavailable && !connector.enabled) {
    return (
      <Card title={connector.name} actions={<Badge>{state}</Badge>}>
        <p className="text-sm">
          {connector.unavailable}{" "}
          {connector.needs.length > 0
            ? "As the custodian, you set it up on the server with these settings:"
            : "Ask the custodian if you would like to use it."}
        </p>
        {connector.needs.length > 0 && (
          <ul className="mt-2 flex flex-wrap gap-2 text-xs">
            {connector.needs.map((name) => (
              <li key={name}>
                <code className="rounded border border-ash bg-night px-1.5 py-0.5">{name}</code>
              </li>
            ))}
          </ul>
        )}
      </Card>
    );
  }

  return (
    <Card title={connector.name} actions={<Badge tone={connector.enabled ? "gold" : "mist"}>{state}</Badge>}>
      {connector.unavailable && (
        <Notice>
          {connector.unavailable} Nothing reaches players through {connector.name} until it is. Switch it off, or ask the custodian.
        </Notice>
      )}
      {!connector.enabled && !connector.unavailable && <p className="text-sm text-mist">Off: results reach players only in Horatio.</p>}
      <form
        className="mt-3 flex flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate(undefined, { onSuccess: () => toast({ message: `Saved ${connector.name}` }) });
        }}
      >
        <fieldset disabled={!canEdit} className="flex flex-col gap-4">
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} disabled={!!connector.unavailable && !enabled} />
            Send downtime results through {connector.name}
          </label>
          {/* What to send and test mode matter only once it is on. */}
          {enabled && (
            <>
              <Field
                label="What to send"
                hint={
                  mode === "alert"
                    ? "Only that results are ready, with a link to the character's Results tab. The results stay in Horatio, where storytellers can still correct them."
                    : "The whole result, as players see it in Horatio."
                }
              >
                <Select value={mode} onChange={(e) => setMode(e.target.value as ConnectorOut["mode"])}>
                  <option value="alert">An alert with a link</option>
                  <option value="full">The full results</option>
                </Select>
              </Field>
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={testMode} onChange={(e) => setTestMode(e.target.checked)} />
                Test mode: send everything to {TEST_TARGET[connector.kind] ?? "the test target"}, not to players
              </label>
            </>
          )}
          {Editor && <Editor troupeId={troupeId} settings={settings} onChange={setSettings} canEdit={canEdit} />}
        </fieldset>
        <ErrorText error={save.error} />
        {canEdit && (
          <div>
            <Button type="submit" disabled={save.isPending}>
              Save
            </Button>
          </div>
        )}
      </form>
    </Card>
  );
}
