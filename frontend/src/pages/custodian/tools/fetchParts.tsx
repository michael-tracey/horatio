import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type ReactNode } from "react";
import type { components } from "../../../api/schema";
import { Dialog } from "../../../components/Dialog";
import { Button, Field, Input, Notice } from "../../../components/ui";
import { useDates } from "../../../dates";

type FetchJob = components["schemas"]["FetchJob"];

/** How often a fetch under way is asked after. */
export const POLL = 2000;

/** Bytes as people read them. */
export function size(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toLocaleString(undefined, { maximumFractionDigits: 0 })} MB`;
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${bytes} bytes`;
}

/** When a fetch finishes, everything that shows what it fetched is asked again. */
export function useRefreshWhenDone(running: boolean) {
  const client = useQueryClient();
  const was = useRef(running);
  useEffect(() => {
    if (was.current && !running) void client.invalidateQueries();
    was.current = running;
  }, [running, client]);
}

/** Where the server can't keep or write the files, why, and nothing else. */
export function NotSetUp({ configured, writable }: { configured: boolean; writable: boolean }) {
  if (!configured) {
    return <Notice>This server has no Dark Pack folder, so there is nowhere to keep them. On the server, the setting HORATIO_DARK_PACK_DIR names it.</Notice>;
  }
  if (!writable) {
    return <Notice>The server can't write to its Dark Pack folder. A server deployed before Horatio could fetch these mounts it read-only: deploy again to fix it.</Notice>;
  }
  return null;
}

/**
 * The address to fetch from, filled with the usual one, and the licence to accept
 * first: the Dark Pack Agreement is the operator's to accept, not Horatio's.
 */
export function FetchForm({
  defaultAddress,
  agreement,
  disabled,
  pending,
  label,
  onFetch,
  children,
}: {
  defaultAddress: string;
  agreement: string;
  disabled: boolean;
  pending: boolean;
  label: string;
  onFetch: (address: string) => void;
  children?: ReactNode;
}) {
  const [address, setAddress] = useState(defaultAddress);
  const [accepted, setAccepted] = useState(false);
  return (
    <form
      className="mt-4 flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        onFetch(address);
      }}
    >
      <Field label="Address" hint="Only https addresses. Change it if the files move.">
        <Input type="url" value={address} onChange={(e) => setAddress(e.target.value)} required />
      </Field>
      <LicenceBox agreement={agreement} accepted={accepted} onChange={setAccepted} />
      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" disabled={disabled || pending || !accepted || !address.trim()}>
          {label}
        </Button>
        {address !== defaultAddress && (
          <Button type="button" variant="ghost" onClick={() => setAddress(defaultAddress)}>
            Use the usual address
          </Button>
        )}
        {children}
      </div>
    </form>
  );
}

export function LicenceBox({ agreement, accepted, onChange }: { agreement: string; accepted: boolean; onChange: (accepted: boolean) => void }) {
  return (
    <label className="flex items-start gap-2 text-sm">
      <input type="checkbox" className="mt-1" checked={accepted} onChange={(e) => onChange(e.target.checked)} />
      <span>
        I accept Paradox's{" "}
        <a href={agreement} target="_blank" rel="noreferrer" className="text-gold hover:underline">
          Dark Pack Agreement
        </a>{" "}
        for this server
      </span>
    </label>
  );
}

/** A fetch under way: what it is doing, and how far it has got. */
export function FetchProgress({ job, unit }: { job: FetchJob; unit: "bytes" | "files" }) {
  const dates = useDates();
  const count = (n: number) => (unit === "bytes" ? size(n) : n.toLocaleString());
  const far = job.total ? `${count(job.done)} of ${count(job.total)}` : job.done ? count(job.done) : "";
  return (
    <div className="mt-4">
      <p role="status" className="mb-2 text-sm">
        {job.stage}
        {far ? `: ${far}` : ""}… Started {dates.dateTime(job.started_at)} by @{job.by}. You can leave this page and come back.
      </p>
      <progress className="h-2 w-full accent-gold" max={job.total || 1} value={job.total ? job.done : 0} aria-label={`${job.stage} progress`} />
    </div>
  );
}

/** Why the last fetch failed: what was there before is still there. */
export function FetchFailed({ error, at, children }: { error: string; at: string | null | undefined; children?: ReactNode }) {
  const dates = useDates();
  return (
    <div role="alert" className="mt-4 rounded-md border border-blood/60 bg-blood/15 px-3 py-2 text-sm text-parchment">
      <p>
        The last fetch{at ? `, ${dates.dateTime(at)},` : ""} failed: {error}
      </p>
      <p className="mt-1">What was here before it is still here.</p>
      {children}
    </div>
  );
}

/** Ask before taking them off the server. */
export function RemoveDialog({
  title,
  open,
  pending,
  onClose,
  onRemove,
  children,
}: {
  title: string;
  open: boolean;
  pending: boolean;
  onClose: () => void;
  onRemove: () => void;
  children: ReactNode;
}) {
  return (
    <Dialog title={title} open={open} onClose={onClose}>
      <p className="mb-4 text-sm">{children}</p>
      <div className="flex justify-end gap-2">
        <Button type="button" variant="secondary" onClick={onClose}>
          Keep them
        </Button>
        <Button type="button" variant="danger" disabled={pending} onClick={onRemove}>
          Remove them
        </Button>
      </div>
    </Dialog>
  );
}
