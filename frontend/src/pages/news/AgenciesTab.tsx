import { useQuery } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { AgencyOut, ChannelsOut } from "../../api/types";
import { ActionMenu, MenuGroup, MenuItem } from "../../components/ActionMenu";
import { Dialog } from "../../components/Dialog";
import { useToast } from "../../components/Toast";
import { Badge, Button, Card, Empty, ErrorText, Field, Input, Loading } from "../../components/ui";
import { useAction } from "../../hooks";
import { manualLink } from "../../manualLink";
import { ACCEPT, MAX_BYTES } from "./PostForm";
import { useAgencies } from "./queries";
import { Masthead } from "./Story";

/**
 * Customise › News agencies (#510, #782): the troupe's news agencies, each with its
 * masthead. Storytellers and assistant storytellers keep them. Their Discord
 * channels, and the troupe's news and announcements channels, are chosen under
 * Connectors › Discord (#882); here an agency shows the channel it has of its own.
 */
export function AgenciesTab({ troupeId, archived }: { troupeId: string; archived: boolean }) {
  const agencies = useAgencies(troupeId);
  const channels = useQuery({
    queryKey: ["post-channels", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/post-channels", { params: { path: { troupe_id: troupeId } } })),
  });
  const [adding, setAdding] = useState(false);
  return (
    <div className="flex flex-col gap-6">
      <Card
        title="News agencies"
        actions={
          !archived && (
            <Button variant="secondary" onClick={() => setAdding(true)}>
              Add an agency
            </Button>
          )
        }
      >
        <p className="mb-3 text-sm text-mist">
          The troupe's in-world news: a newspaper, a TV station, a Kindred rumour sheet. Storytellers write as them on the News tab.{" "}
          <Link to={manualLink("running-a-troupe", "news-agencies")} className="underline hover:text-parchment">
            More about news
          </Link>
        </p>
        <p className="mb-3 text-sm text-mist">
          Their Discord channels, and the troupe's news and announcements channels, are chosen under{" "}
          <Link to={`/troupes/${troupeId}/connectors`} className="underline hover:text-parchment">
            Connectors › Discord
          </Link>
          .
        </p>
        {agencies.isPending ? (
          <Loading />
        ) : agencies.error ? (
          <ErrorText error={agencies.error} />
        ) : agencies.data.length === 0 ? (
          <Empty>No agencies yet. Add one to start writing news.</Empty>
        ) : (
          <table aria-label="News agencies" className="w-full text-sm">
            <thead className="max-lg:sr-only">
              <tr className="border-b border-ash text-left text-xs text-mist">
                <th className="py-2 pr-3 font-normal">Masthead</th>
                <th className={`${WIDE} py-2 pr-3 font-normal`}>About</th>
                <th className={`${WIDE} py-2 pr-3 font-normal`}>Discord channel</th>
                <th className="py-2 font-normal">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ash">
              {agencies.data.map((a) => (
                <AgencyRow key={a.id} troupeId={troupeId} agency={a} channels={channels.data} archived={archived} />
              ))}
            </tbody>
          </table>
        )}
      </Card>
      <Dialog title="Add an agency" open={adding} onClose={() => setAdding(false)}>
        <AgencyForm troupeId={troupeId} onDone={() => setAdding(false)} />
      </Dialog>
    </div>
  );
}

const WIDE = "hidden lg:table-cell";

function channelName(channels: ChannelsOut | undefined, id: string | null): string {
  if (!id) return "The troupe's news channel";
  const found = channels?.channels.find((c) => c.id === id);
  return found ? `#${found.name}` : "A channel no longer on the server";
}

/** Where an agency's stories go on Discord: the troupe's news channel, or its own, with a link to change it in Connectors. */
function AgencyChannel({ troupeId, agency, channels }: { troupeId: string; agency: AgencyOut; channels: ChannelsOut | undefined }) {
  if (!agency.discord_channel) return <>{channelName(channels, null)}</>;
  return (
    <>
      {channelName(channels, agency.discord_channel)}{" "}
      <Link to={`/troupes/${troupeId}/connectors`} className="underline hover:text-parchment">
        Change in Connectors
      </Link>
    </>
  );
}

type Opened = "edit" | "masthead";

function AgencyRow({ troupeId, agency, channels, archived }: { troupeId: string; agency: AgencyOut; channels: ChannelsOut | undefined; archived: boolean }) {
  const [open, setOpen] = useState<Opened | null>(null);
  const toast = useToast();
  const path = { params: { path: { agency_id: agency.id } } };
  const retire = useAction(() => unwrap(agency.retired ? api.POST("/api/agencies/{agency_id}/restore", path) : api.POST("/api/agencies/{agency_id}/retire", path)));
  const about = agency.description || <span className="text-mist">No description.</span>;
  return (
    <tr>
      <td className="py-2.5 pr-3 align-top">
        <span className="flex flex-wrap items-center gap-2">
          <Masthead agency={agency} small />
          {agency.retired && <Badge>Retired</Badge>}
        </span>
        <span className="mt-1 block text-xs text-mist lg:hidden">
          {agency.description && `${agency.description} · `}
          <AgencyChannel troupeId={troupeId} agency={agency} channels={channels} />
        </span>
      </td>
      <td className={`${WIDE} py-2.5 pr-3 align-top`}>{about}</td>
      <td className={`${WIDE} py-2.5 pr-3 align-top text-mist`}>
        <AgencyChannel troupeId={troupeId} agency={agency} channels={channels} />
      </td>
      <td className="w-px py-1 text-right align-top">
        {!archived && (
          <ActionMenu label={`Actions for ${agency.name}`} variant="ghost">
            <MenuGroup label="Change">
              <MenuItem onSelect={() => setOpen("edit")}>Edit…</MenuItem>
              <MenuItem onSelect={() => setOpen("masthead")}>Masthead picture…</MenuItem>
            </MenuGroup>
            <MenuGroup label="Retire">
              <MenuItem onSelect={() => retire.mutate(undefined, { onSuccess: () => toast({ message: agency.retired ? `${agency.name} is back.` : `${agency.name} is retired; its stories stay.` }) })}>
                {agency.retired ? "Bring back" : "Retire"}
              </MenuItem>
            </MenuGroup>
          </ActionMenu>
        )}
        <Dialog title={`Edit ${agency.name}`} open={open === "edit"} onClose={() => setOpen(null)}>
          <AgencyForm troupeId="" agency={agency} onDone={() => setOpen(null)} />
        </Dialog>
        <Dialog title={`${agency.name}'s masthead`} open={open === "masthead"} onClose={() => setOpen(null)}>
          <MastheadPicture agency={agency} />
        </Dialog>
        <ErrorText error={retire.error} />
      </td>
    </tr>
  );
}

/**
 * An agency's name, description and colour: new, or changed. Its Discord channel is
 * left out, and so kept: it is chosen under Connectors › Discord.
 */
function AgencyForm({ troupeId, agency, onDone }: { troupeId: string; agency?: AgencyOut; onDone: () => void }) {
  const [name, setName] = useState(agency?.name ?? "");
  const [description, setDescription] = useState(agency?.description ?? "");
  const [colour, setColour] = useState(agency?.colour ?? "#8b1e1e");
  const save = useAction(() => {
    const body = { name, description, colour: colour.toLowerCase() };
    return unwrap(
      agency
        ? api.PUT("/api/agencies/{agency_id}", { params: { path: { agency_id: agency.id } }, body })
        : api.POST("/api/troupes/{troupe_id}/agencies", { params: { path: { troupe_id: troupeId } }, body }),
    );
  });
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(undefined, { onSuccess: onDone });
      }}
    >
      <Field label="Name">
        <Input required maxLength={100} value={name} onChange={(e) => setName(e.target.value)} />
      </Field>
      <Field label="Description (optional)" hint="A line about it, for staff: “The Kindred rumour sheet slipped under Elysium's door.”">
        <Input maxLength={500} value={description} onChange={(e) => setDescription(e.target.value)} />
      </Field>
      <Field label="Masthead colour" hint="Behind its name, beside its stories, and down the side of its Discord posts.">
        <Input type="color" className="h-10 w-20 p-1" value={colour} onChange={(e) => setColour(e.target.value)} />
      </Field>
      <div className="flex items-center gap-3 text-sm">
        <span className="text-mist">Masthead:</span>
        <Masthead agency={{ ...(agency ?? { id: "", picture: null, discord_channel: null, retired: false }), name: name || "Name", description, colour }} small />
      </div>
      <ErrorText error={save.error} />
      <Button type="submit" className="self-start" disabled={save.isPending || !name.trim()}>
        {agency ? "Save" : "Add the agency"}
      </Button>
    </form>
  );
}

/** A picture to show in place of an agency's name: its nameplate or logo. */
function MastheadPicture({ agency }: { agency: AgencyOut }) {
  const path = { params: { path: { agency_id: agency.id } } };
  const fileInput = useRef<HTMLInputElement>(null);
  const [tooBig, setTooBig] = useState(false);
  const upload = useAction(async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    await unwrap(api.POST("/api/agencies/{agency_id}/picture", { ...path, body: form as never, bodySerializer: (b: unknown) => b as FormData }));
  });
  const remove = useAction(() => unwrap(api.DELETE("/api/agencies/{agency_id}/picture", path)));
  return (
    <div className="flex flex-col gap-3 text-sm">
      <Masthead agency={agency} />
      <p className="text-mist">Optional: a nameplate or logo, shown in place of the name on its stories, and beside them on Discord. Without one, the name shows on its colour.</p>
      <input
        ref={fileInput}
        type="file"
        accept={ACCEPT}
        aria-label="Choose a masthead picture"
        className="sr-only"
        onChange={(e) => {
          const file = e.target.files?.[0];
          e.target.value = "";
          if (!file) return;
          setTooBig(file.size > MAX_BYTES);
          if (file.size <= MAX_BYTES) upload.mutate(file);
        }}
      />
      <span className="flex flex-wrap gap-2">
        <Button type="button" variant="secondary" disabled={upload.isPending} onClick={() => fileInput.current?.click()}>
          {upload.isPending ? "Uploading…" : agency.picture ? "Upload another" : "Add a picture"}
        </Button>
        {agency.picture && (
          <Button type="button" variant="ghost" disabled={remove.isPending} onClick={() => remove.mutate(undefined)}>
            Remove the picture
          </Button>
        )}
      </span>
      {tooBig && <ErrorText error="That picture is over 10 MB. Try a smaller one." />}
      <ErrorText error={upload.error ?? remove.error} />
    </div>
  );
}
