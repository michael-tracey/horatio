import { useQuery } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../../api/client";
import type { components } from "../../../api/schema";
import { Button, Card, ErrorText, Loading } from "../../../components/ui";
import { useDates } from "../../../dates";
import { useAction } from "../../../hooks";
import { manualLink } from "../../../manualLink";
import { FetchFailed, FetchForm, FetchProgress, LicenceBox, NotSetUp, POLL, RemoveDialog, useRefreshWhenDone } from "./fetchParts";

type DarkPackTool = components["schemas"]["DarkPackTool"];

const HOW: Record<string, string> = { fetched: "Fetched", uploaded: "Uploaded", command: "Imported with the command" };

/**
 * Paradox's Dark Pack resources (#534): the server fetches the kit from Paradox's
 * download and imports it, or the custodian uploads what an import elsewhere wrote.
 * Deploys no longer copy them to the server.
 */
export function DarkPackResources() {
  const state = useQuery({
    queryKey: ["tools", "dark-pack"],
    queryFn: () => unwrap(api.GET("/api/tools/dark-pack")),
    refetchInterval: (q) => (q.state.data?.job ? POLL : false),
  });
  const fetch = useAction((address: string) => unwrap(api.POST("/api/tools/dark-pack/fetch", { body: { address, accept_licence: true } })));
  const remove = useAction(() => unwrap(api.DELETE("/api/tools/dark-pack")));
  const [removing, setRemoving] = useState(false);
  const s = state.data;
  useRefreshWhenDone(!!s?.job);

  return (
    <Card
      title="Dark Pack resources"
      actions={
        s?.imported && (
          <Button type="button" variant="danger" disabled={!!s.job || !s.writable} onClick={() => setRemoving(true)}>
            Remove
          </Button>
        )
      }
    >
      <p className="mb-3 text-sm text-mist">
        Paradox's{" "}
        <a href={s?.agreement} target="_blank" rel="noreferrer" className="text-gold hover:underline">
          Dark Pack Agreement
        </a>{" "}
        lets Horatio show the Dark Pack logo on the About page and the clans' symbols on badges. Its licence belongs to whoever runs the server, so Horatio never
        ships them: the server fetches Paradox's free download here and keeps only what Horatio uses, about a megabyte.{" "}
        <Link to={manualLink("custodian", "the-dark-pack-resources")} className="text-gold hover:underline">
          How it works
        </Link>
      </p>
      {state.isPending ? (
        <Loading />
      ) : state.error ? (
        <ErrorText error={state.error} />
      ) : (
        <>
          <NotSetUp configured={s!.configured} writable={s!.writable} />
          <Status state={s!} />
          {s!.job && <FetchProgress job={s!.job} unit="bytes" />}
          {s!.error && (
            <FetchFailed error={s!.error} at={s!.error_at}>
              <p className="mt-1">If it keeps failing, import the kit on your own computer and upload the result below.</p>
            </FetchFailed>
          )}
          {s!.configured && s!.writable && (
            <>
              <FetchForm
                defaultAddress={s!.default_address}
                agreement={s!.agreement}
                disabled={!!s!.job}
                pending={fetch.isPending}
                label={s!.imported ? "Fetch and import again" : "Fetch and import"}
                onFetch={(address) => fetch.mutate(address)}
              />
              <p className="mt-2 text-xs text-mist">
                The download is about 450 MB, so it takes a few minutes. What's here now stays until the new import is whole.
              </p>
              <ErrorText error={fetch.error} />
              <UploadResult state={s!} />
            </>
          )}
          <ErrorText error={remove.error} />
        </>
      )}
      <RemoveDialog
        title="Remove the Dark Pack resources?"
        open={removing}
        pending={remove.isPending}
        onClose={() => setRemoving(false)}
        onRemove={() => remove.mutate(undefined, { onSuccess: () => setRemoving(false) })}
      >
        The Dark Pack logo and the clans' symbols come off the server now. Badges show only the clan logos uploaded in Clan logos until they're fetched again.
      </RemoveDialog>
    </Card>
  );
}

/** What is on the server now. */
function Status({ state }: { state: DarkPackTool }) {
  const dates = useDates();
  if (!state.configured) return null;
  if (!state.imported) return <p className="text-sm">Not on this server yet.</p>;
  return (
    <section aria-label="On the server" className="flex flex-col gap-1 text-sm">
      <p>
        {HOW[state.how ?? "command"] ?? "Imported"}
        {state.imported_at ? ` ${dates.dateTime(state.imported_at)}` : ""}
        {state.address ? (
          <>
            {" "}
            from <span className="break-all text-mist">{state.address}</span>
          </>
        ) : null}
        {state.sources.length ? `, from ${state.sources.join(" and ")}` : ""}.
      </p>
      <p>{state.logo ? "The Dark Pack logo is here." : "The Dark Pack logo isn't here: the About page needs it."}</p>
      <p>
        Clan symbols ({state.clans.length}): {state.clans.join(", ") || "none"}.
      </p>
      {state.missing.length > 0 && <p className="text-mist">Not in the kit: {state.missing.join(", ")}.</p>}
    </section>
  );
}

/**
 * The fallback: the custodian imports the kit on their own computer with the
 * command, zips the dark-pack folder it wrote, and uploads that.
 */
function UploadResult({ state }: { state: DarkPackTool }) {
  const input = useRef<HTMLInputElement>(null);
  const [accepted, setAccepted] = useState(false);
  const upload = useAction((file: File) => {
    const form = new FormData();
    form.append("file", file);
    form.append("accept_licence", "true");
    return unwrap(api.POST("/api/tools/dark-pack/upload", { body: form as never, bodySerializer: (body: unknown) => body as FormData }));
  });
  return (
    <details className="mt-4 text-sm">
      <summary className="cursor-pointer text-mist hover:text-parchment">Or upload an import made on your own computer</summary>
      <div className="mt-2 flex flex-col gap-3">
        <p className="text-mist">
          Download the kit from the agreement's page, import it with <code>python -m horatio.dark_pack</code> as <code>dark-pack/README.md</code> says, zip the{" "}
          <code>dark-pack</code> folder it wrote, and upload the zip (about a megabyte, not Paradox's zips).
        </p>
        <LicenceBox agreement={state.agreement} accepted={accepted} onChange={setAccepted} />
        <input
          ref={input}
          type="file"
          accept=".zip,application/zip"
          aria-label="The zipped dark-pack folder"
          className="sr-only"
          onChange={(e) => {
            const file = e.target.files?.[0];
            e.target.value = "";
            if (file) upload.mutate(file);
          }}
        />
        <div>
          <Button type="button" variant="secondary" disabled={!accepted || !!state.job || upload.isPending} onClick={() => input.current?.click()}>
            {upload.isPending ? "Uploading…" : "Upload the zip"}
          </Button>
        </div>
        <ErrorText error={upload.error} />
      </div>
    </details>
  );
}
