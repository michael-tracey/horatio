import { useQuery } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";
import { api, unwrap } from "../../api/client";
import type { components } from "../../api/schema";
import { Badge, Button, Card, ErrorText, Field, Loaded, Select } from "../../components/ui";
import { useToast } from "../../components/Toast";
import { useDates } from "../../dates";
import { useAction } from "../../hooks";
import { dayChoices, keptFor } from "./audit";
import { SiteFold } from "./SiteFold";

type Settings = components["schemas"]["AuditSettingsOut"];

const SETTINGS = ["audit", "settings"];

// How long each level can be kept, in days; Forever too.
const DEBUG_DAYS = [7, 14, 30, 90, 180, 365];
const INFO_DAYS = [90, 180, 365, 730, 1825];

/**
 * The audit log (#1062): whether debug events are recorded, how long debug and info
 * events are kept, and what the daily purge last deleted. Notice events are always
 * kept.
 */
export function AuditLogCard() {
  const settings = useQuery({ queryKey: SETTINGS, queryFn: () => unwrap(api.GET("/api/audit/settings")) });
  return <Loaded query={settings}>{(found) => <AuditLogForm settings={found} />}</Loaded>;
}

function AuditLogForm({ settings }: { settings: Settings }) {
  const toast = useToast();
  const dates = useDates();
  const [debug, setDebug] = useState(settings.record === "debug");
  const [keepDebug, setKeepDebug] = useState(settings.keep_debug);
  const [keepInfo, setKeepInfo] = useState(settings.keep_info);
  useEffect(() => {
    setDebug(settings.record === "debug");
    setKeepDebug(settings.keep_debug);
    setKeepInfo(settings.keep_info);
  }, [settings.record, settings.keep_debug, settings.keep_info]);
  const save = useAction(
    () => unwrap(api.PUT("/api/audit/settings", { body: { record: debug ? "debug" : "info", keep_debug: keepDebug, keep_info: keepInfo } })),
    [SETTINGS],
  );
  const submit = (event: FormEvent) => {
    event.preventDefault();
    save.mutate(undefined, { onSuccess: () => toast({ message: "Saved. The audit log works this way from now on." }) });
  };
  const last = settings.last_purge;
  const recording = settings.record === "debug";
  const kept = (days: number | null) => (days === null ? "forever" : `for ${keptFor(days)}`);

  return (
    <Card title="Audit log" actions={<Badge tone={recording ? "gold" : "mist"}>{recording ? "Recording debug events" : "Debug events off"}</Badge>}>
      {/* What it keeps and the last purge stay in sight; the levels and the settings fold away (#944). */}
      <div className="flex flex-col gap-4 text-sm">
        <p className="text-parchment">
          Keeps debug events {kept(settings.keep_debug)}, info events {kept(settings.keep_info)}, and notice events forever.
        </p>
        <p className="text-xs text-mist">
          {last
            ? `Last cleared ${dates.dateTime(last.at)}: ${last.debug.toLocaleString()} debug and ${last.info.toLocaleString()} info events deleted${last.finished ? "" : ", with more still to delete"}.`
            : "Not cleared yet."}
        </p>
        <SiteFold summary="Levels, and what it records and keeps">
          <form onSubmit={submit} className="flex flex-col gap-4">
            <p className="text-mist">
              Each change in the log has a level. <strong className="text-parchment">Notice</strong> ones, such as suspensions, merges, deletions and what Horatio
              reads back as history, are kept forever. <strong className="text-parchment">Info</strong> ones are most changes, as troupes see them in their logs.{" "}
              <strong className="text-parchment">Debug</strong> ones are routine: signing in and out, failed sign-ins, signing up, and a character starting to visit
              a troupe. They show only in Custodian › Audit. Once a day Horatio deletes the debug and info events older than you keep them.
            </p>
            <label className="flex items-start gap-2">
              <input type="checkbox" className="mt-1" checked={debug} onChange={(e) => setDebug(e.target.checked)} />
              <span>Record debug events</span>
            </label>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Keep debug events for">
                <DaysSelect usual={DEBUG_DAYS} value={keepDebug} onChange={setKeepDebug} />
              </Field>
              <Field label="Keep info events for">
                <DaysSelect usual={INFO_DAYS} value={keepInfo} onChange={setKeepInfo} />
              </Field>
            </div>
            <div>
              <Button type="submit" variant="secondary" disabled={save.isPending}>
                Save audit log settings
              </Button>
            </div>
            <ErrorText error={save.error} />
          </form>
        </SiteFold>
      </div>
    </Card>
  );
}

function DaysSelect({
  usual,
  value,
  onChange,
  id,
  "aria-describedby": describedBy,
}: {
  usual: number[];
  value: number | null;
  onChange: (days: number | null) => void;
  id?: string;
  "aria-describedby"?: string;
}) {
  return (
    <Select id={id} aria-describedby={describedBy} value={value ?? ""} onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}>
      {dayChoices(usual, value).map((days) => (
        <option key={days} value={days}>
          {keptFor(days)}
        </option>
      ))}
      <option value="">Forever</option>
    </Select>
  );
}
