import { useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { Link, Route, Routes, useLocation, useNavigate, useParams } from "react-router";
import { api, unwrap } from "../../api/client";
import type { LocationCatalogueOut, LocationDetailOut, LocationOut } from "../../api/types";
import { ActionMenu, MenuGroup, MenuItem, MenuLink } from "../../components/ActionMenu";
import { Dialog } from "../../components/Dialog";
import { EmptyState, FilterBar } from "../../components/EmptyState";
import { InfoButton } from "../../components/InfoButton";
import { LogList } from "../../components/LogList";
import { useToast } from "../../components/Toast";
import { Badge, Button, Card, Empty, ErrorText, Input, Loading, Select } from "../../components/ui";
import { WebLink } from "../../components/WebLink";
import { useAction } from "../../hooks";
import { LocationForm, Warnings } from "./LocationForm";
import { RemoveNegative } from "./RemoveNegative";
import { controlText, controllerKey, countText, distinct, filtered, influenceText, NO_FILTERS, qualitiesText, qualityText, typeText, type Filters } from "./locations";

/**
 * The troupe's locations, for its storytellers and assistants: the Stock
 * Locations that matter in its chronicle and its characters' Havens, with who
 * controls each. Players never see the record.
 */
export function LocationsTab({ troupeId, questsOn = false }: { troupeId: string; questsOn?: boolean }) {
  const path = { params: { path: { troupe_id: troupeId } } };
  const list = useQuery({
    queryKey: ["locations", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/locations", path)),
  });
  const catalogue = useQuery({
    queryKey: ["location-catalogue", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/locations/catalogue", path)),
  });
  if (list.isPending || catalogue.isPending) return <Loading />;
  if (list.error || catalogue.error) return <ErrorText error={list.error ?? catalogue.error} />;
  return (
    <Routes>
      <Route index element={<List troupeId={troupeId} locations={list.data} catalogue={catalogue.data} questsOn={questsOn} />} />
      <Route path="new" element={<New troupeId={troupeId} locations={list.data} catalogue={catalogue.data} />} />
      <Route path=":locationId" element={<One troupeId={troupeId} locations={list.data} catalogue={catalogue.data} questsOn={questsOn} />} />
    </Routes>
  );
}

type Props = { troupeId: string; locations: LocationOut[]; catalogue: LocationCatalogueOut };

function List({ troupeId, locations, catalogue, questsOn }: Props & { questsOn: boolean }) {
  const navigate = useNavigate();
  const [f, setF] = useState<Filters>(NO_FILTERS);
  const set = (change: Partial<Filters>) => setF({ ...f, ...change });
  const shown = filtered(locations, f);
  const controllers = new Map<string, string>();
  for (const l of locations) {
    if (l.controller) controllers.set(controllerKey(l), l.controller.name);
    if (l.joint?.id) controllers.set(`c:${l.joint.id}`, l.joint.name);
  }
  const filtering = JSON.stringify(f) !== JSON.stringify(NO_FILTERS);

  return (
    <div className="flex flex-col gap-4">
      <Card
        title="Locations"
        info={
          <InfoButton label="About locations">
            Each with its qualities and who controls it ({catalogue.book}, pp. 117–133). Only storytellers and assistant storytellers see this list. A character
            controls up to five locations, and one more for each dot of Retainers; Havens don't count.
          </InfoButton>
        }
        actions={
          <Button variant="secondary" onClick={() => navigate(`/troupes/${troupeId}/locations/new`)}>
            Add a location
          </Button>
        }
      >
        {locations.length === 0 ? (
          <EmptyState title="No locations yet.">The places that matter in the chronicle go here, with who controls each. Start with Add a location, above.</EmptyState>
        ) : (
          <p className="mb-3 text-sm text-mist">The places that matter here, and who controls them.</p>
        )}
        <FilterBar count={locations.length} filtering={filtering}>
          <div className="flex flex-col gap-3">
            <Input aria-label="Search locations" placeholder={`Search ${locations.length} locations by name or address…`} value={f.query} onChange={(e) => set({ query: e.target.value })} />
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <Select aria-label="Controller" value={f.controller} onChange={(e) => set({ controller: e.target.value })}>
                <option value="">Any controller</option>
                <option value="none">Uncontrolled</option>
                <option value="uncontrollable">Uncontrollable</option>
                {[...controllers].sort((a, b) => a[1].localeCompare(b[1])).map(([key, name]) => (
                  <option key={key} value={key}>
                    {name}
                  </option>
                ))}
              </Select>
              <Select aria-label="Type" value={f.kind} onChange={(e) => set({ kind: e.target.value })}>
                <option value="">Any type</option>
                {catalogue.types.map((t) => (
                  <option key={t.key} value={t.key}>
                    {t.name}
                  </option>
                ))}
              </Select>
              <Select aria-label="Quality" value={f.quality} onChange={(e) => set({ quality: e.target.value })}>
                <option value="">Any quality</option>
                {distinct([...catalogue.qualities.map((q) => q.name), ...locations.flatMap((l) => l.qualities.map((q) => q.name))]).map((q) => (
                  <option key={q} value={q}>
                    {q}
                  </option>
                ))}
              </Select>
              <Select aria-label="Influence area" value={f.influence} onChange={(e) => set({ influence: e.target.value })}>
                <option value="">Any influence</option>
                {distinct(locations.map(influenceText)).map((a) => (
                  <option key={a} value={a}>
                    {a}
                  </option>
                ))}
              </Select>
              <Select aria-label="Feeding block" value={f.block} onChange={(e) => set({ block: e.target.value })}>
                <option value="">Any feeding block</option>
                {distinct(locations.map((l) => l.feeding_block)).map((b) => (
                  <option key={b} value={b}>
                    {b}
                  </option>
                ))}
              </Select>
              <Select aria-label="Locked" value={f.locked} onChange={(e) => set({ locked: e.target.value as Filters["locked"] })}>
                <option value="">Locked or not</option>
                <option value="locked">Locked</option>
                <option value="open">Not locked</option>
              </Select>
              <Select aria-label="Negative qualities" value={f.negatives} onChange={(e) => set({ negatives: e.target.value as Filters["negatives"] })}>
                <option value="">Any negatives</option>
                <option value="any">With negatives</option>
                <option value="secret">With secret negatives</option>
                <option value="none">Without negatives</option>
              </Select>
              {filtering && (
                <Button variant="ghost" onClick={() => setF(NO_FILTERS)}>
                  Clear filters
                </Button>
              )}
            </div>
          </div>
        </FilterBar>
      </Card>
      {locations.length === 0 ? null : shown.length === 0 ? (
        <Empty>No locations match.</Empty>
      ) : (
        <Card>
          <table aria-label="Locations" className="w-full text-sm">
            {/* On a phone or a narrow window each row folds into a card, under the one heading. */}
            <thead className="max-lg:sr-only">
              <tr className="border-b border-ash text-left text-xs text-mist">
                <th className="py-2 pr-3 font-normal">Name</th>
                <th className={`${WIDE} py-2 pr-3 font-normal`}>Type</th>
                <th className={`${WIDE} py-2 pr-3 font-normal`}>Controller</th>
                <th className={`${WIDE} py-2 pr-3 font-normal`}>Qualities</th>
                <th className={`${WIDE} py-2 pr-3 font-normal`}>Influence area</th>
                <th className={`${WIDE} py-2 pr-3 font-normal`}>Locked</th>
                <th className="py-2 font-normal">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ash">
              {shown.map((l) => (
                <Row key={l.id} location={l} troupeId={troupeId} locations={locations} catalogue={catalogue} questsOn={questsOn} />
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}

/** A column shown only on a wide screen; on a narrow one it folds in under the name. */
const WIDE = "hidden lg:table-cell";

type Opened = "edit" | "remove";

/** One location on the list: what it is and who controls it, and what staff can do with it behind ⋯. */
function Row({ location: l, troupeId, locations, catalogue, questsOn }: Props & { location: LocationOut; questsOn: boolean }) {
  const [open, setOpen] = useState<Opened | null>(null);
  const close = () => setOpen(null);
  const toast = useToast();
  // Said and closed before the list is asked again, which takes the row away.
  const remove = useAction(async () => {
    await unwrap(api.DELETE("/api/locations/{location_id}", { params: { path: { location_id: l.id } } }));
    toast({ message: `${l.name} removed.` });
    close();
  });
  const qualities = qualitiesText(l.qualities);
  const negatives = l.negatives.length > 0 && (
    <span className="text-blood-bright">
      {l.negatives.map((n) => `${n.name} ×${n.level}${n.secret ? " (secret)" : ""}`).join(", ")}
    </span>
  );
  const badges = (
    <>
      {l.haven_of && <Badge tone="gold">Haven</Badge>}
      {l.elysium_since != null && <Badge tone="gold">Elysium</Badge>}
    </>
  );
  const where = [l.parent && `Part of ${l.parent.name}`, l.feeding_block && `Feeding block: ${l.feeding_block}`, l.address].filter(Boolean).join(" · ");
  return (
    <tr>
      <td className="py-2.5 pr-3 align-top">
        <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <Link to={l.id} className="text-gold hover:text-parchment">
            {l.name}
          </Link>
          {badges}
          {l.locked && (
            <Badge tone="blood" className="lg:hidden">
              Locked
            </Badge>
          )}
        </span>
        <span className="mt-0.5 block text-xs text-mist wrap-anywhere lg:hidden">
          {[typeText(l), controlText(l), influenceText(l)].filter(Boolean).join(" · ")}
        </span>
        {(qualities || negatives) && (
          <span className="mt-0.5 block text-xs lg:hidden">
            {qualities}
            {qualities && negatives && "; "}
            {negatives}
          </span>
        )}
        {where && <span className="mt-0.5 block text-xs text-mist wrap-anywhere">{where}</span>}
      </td>
      <td className={`${WIDE} py-2.5 pr-3 align-top whitespace-nowrap text-mist`}>{typeText(l)}</td>
      <td className={`${WIDE} py-2.5 pr-3 align-top`}>{controlText(l)}</td>
      <td className={`${WIDE} py-2.5 pr-3 align-top text-xs`}>
        {qualities}
        {qualities && negatives && <br />}
        {negatives}
      </td>
      <td className={`${WIDE} py-2.5 pr-3 align-top text-mist`}>{influenceText(l)}</td>
      <td className={`${WIDE} py-2.5 pr-3 align-top`}>{l.locked && <Badge tone="blood">Locked</Badge>}</td>
      <td className="w-px py-1 text-right align-top">
        <ActionMenu label={`Actions for ${l.name}`} variant="ghost">
          <MenuGroup label="The record">
            <MenuLink to={l.id}>Open</MenuLink>
            <MenuItem onSelect={() => setOpen("edit")}>Edit…</MenuItem>
            {questsOn && <MenuLink to={`/troupes/${troupeId}/quests/new?location=${l.id}`}>Build a quest for it</MenuLink>}
          </MenuGroup>
          <MenuGroup label="Remove">
            <MenuItem onSelect={() => setOpen("remove")}>Remove…</MenuItem>
          </MenuGroup>
        </ActionMenu>
        {/* The dialogs sit here, as nothing but cells may sit in a row (Dialog sets its own text-left). */}
        <Dialog title={`Change ${l.name}`} open={open === "edit"} onClose={close} wide>
          <LocationForm
            troupeId={troupeId}
            catalogue={catalogue}
            others={locations.filter((o) => o.id !== l.id)}
            location={l}
            onSaved={(saved, warnings) => {
              toast({ message: warnings.length ? `Saved, but: ${warnings.join(" ")}` : `${saved.name} saved.`, duration: warnings.length ? 10_000 : undefined });
              close();
            }}
            onCancel={close}
          />
        </Dialog>
        <Dialog title={`Remove ${l.name}`} open={open === "remove"} onClose={close}>
          <p className="text-sm">Remove {l.name} from the troupe's locations? Its log stays in the troupe's log.</p>
          <div className="mt-4 flex flex-wrap gap-2">
            <Button
              variant="danger"
              disabled={remove.isPending}
              onClick={() => remove.mutate(undefined)}
            >
              Remove location
            </Button>
            <Button variant="ghost" onClick={close}>
              Cancel
            </Button>
          </div>
          <ErrorText error={remove.error} />
        </Dialog>
      </td>
    </tr>
  );
}

function New({ troupeId, locations, catalogue }: Props) {
  const navigate = useNavigate();
  const back = `/troupes/${troupeId}/locations`;
  return (
    <div className="flex flex-col gap-4">
      <Link to={back} className="text-sm text-mist hover:text-gold">
        ← All locations
      </Link>
      <Card title="Add a location">
        <LocationForm
          troupeId={troupeId}
          catalogue={catalogue}
          others={locations}
          location={null}
          onSaved={(saved, warnings) => navigate(`${back}/${saved.id}`, { state: { warnings } })}
          onCancel={() => navigate(back)}
        />
      </Card>
    </div>
  );
}

function One({ troupeId, locations, catalogue, questsOn }: Props & { questsOn: boolean }) {
  const { locationId = "" } = useParams();
  const navigate = useNavigate();
  const back = `/troupes/${troupeId}/locations`;
  const [editing, setEditing] = useState(false);
  // A new location's warnings come with it from the Add page.
  const state = useLocation().state as { warnings?: string[] } | null;
  const [warnings, setWarnings] = useState<string[]>(state?.warnings ?? []);
  const location = useQuery({
    queryKey: ["location", locationId],
    queryFn: () => unwrap(api.GET("/api/locations/{location_id}", { params: { path: { location_id: locationId } } })),
  });
  const remove = useAction(async () => {
    await unwrap(api.DELETE("/api/locations/{location_id}", { params: { path: { location_id: locationId } } }));
    navigate(back);
  });
  const forfeit = useAction(() => unwrap(api.POST("/api/locations/{location_id}/forfeit", { params: { path: { location_id: locationId } } })));
  return (
    <div className="flex flex-col gap-4">
      <Link to={back} className="text-sm text-mist hover:text-gold">
        ← All locations
      </Link>
      {location.isPending ? (
        <Loading />
      ) : location.error ? (
        <ErrorText error={location.error} />
      ) : (
        <>
          <Warnings warnings={warnings} />
          {editing ? (
            <Card title={`Change ${location.data.name}`}>
              <LocationForm
                troupeId={troupeId}
                catalogue={catalogue}
                others={locations.filter((l) => l.id !== locationId)}
                location={location.data}
                onSaved={(_, w) => {
                  setWarnings(w);
                  setEditing(false);
                }}
                onCancel={() => setEditing(false)}
              />
            </Card>
          ) : (
            <Record
              location={location.data}
              catalogue={catalogue}
              onEdit={() => setEditing(true)}
              onQuest={questsOn ? () => navigate(`/troupes/${troupeId}/quests/new?location=${locationId}`) : undefined}
            />
          )}
          {location.data.forfeit && (
            <Card title="Forfeit">
              <p className="text-sm text-blood-bright">{location.data.forfeit}</p>
              <Button className="mt-2" variant="danger" disabled={forfeit.isPending} onClick={() => forfeit.mutate(undefined)}>
                Confirm: nobody controls it now
              </Button>
              <ErrorText error={forfeit.error} />
            </Card>
          )}
          {location.data.negatives.length > 0 && !editing && (
            <Card title="Remove a negative">
              <RemoveNegative troupeId={troupeId} location={location.data} />
            </Card>
          )}
          {location.data.subsidiaries.length > 0 && (
            <Card title="Subsidiaries">
              <ul className="flex flex-col gap-1 text-sm">
                {location.data.subsidiaries.map((s) => (
                  <li key={s.id}>
                    <Link to={`${back}/${s.id}`} className="text-gold hover:text-parchment">
                      {s.name}
                    </Link>{" "}
                    <span className="text-mist">
                      · {s.controller ? `controlled by ${s.controller.name}` : s.control === "uncontrollable" ? "uncontrollable" : "uncontrolled"}
                      {s.with_parent ? ", with the conglomerate" : ""}
                    </span>
                  </li>
                ))}
              </ul>
              {location.data.not_counted && <p className="mt-2 text-xs text-mist">Its controller has it free: {location.data.not_counted}, outside the control limit.</p>}
            </Card>
          )}
          <Card title="Log">
            {location.data.log.length ? <LogList entries={location.data.log} /> : <Empty>Nothing yet.</Empty>}
          </Card>
          <div>
            <Button
              variant="danger"
              disabled={remove.isPending}
              onClick={() => {
                if (confirm(`Remove ${location.data.name} from the troupe's locations? Its log stays in the troupe's log.`)) remove.mutate(undefined);
              }}
            >
              Remove location
            </Button>
            <ErrorText error={remove.error} />
          </div>
        </>
      )}
    </div>
  );
}

/** The location as staff keep it. */
function Record({ location: l, catalogue, onEdit, onQuest }: { location: LocationDetailOut; catalogue: LocationCatalogueOut; onEdit: () => void; onQuest?: () => void }) {
  const quality = (name: string) => catalogue.qualities.find((q) => q.name === name);
  const advantage = (name: string) => catalogue.haven_advantages.find((a) => a.name === name);
  const rows: [string, ReactNode][] = [
    ["Type", `${typeText(l)}${countText(l) ? ` · ${countText(l)}` : ""}`],
    ["Control", controlText(l) + (l.not_counted ? ` (not counted toward the control limit: ${l.not_counted})` : "")],
    ...(l.heir ? [["Heir", l.heir.name] as [string, string]] : []),
    ...(l.parent ? [["Conglomerate", <Link key="p" to={`/troupes/${l.troupe_id}/locations/${l.parent.id}`} className="text-gold hover:text-parchment">{l.parent.name}</Link>] as [string, ReactNode]] : []),
    ...(influenceText(l) ? [["Influence", influenceText(l)] as [string, string]] : []),
    ...(l.feeding_block ? [["Feeding block", l.feeding_block] as [string, string]] : []),
    ...(l.address ? [["Address", l.address] as [string, string]] : []),
    ...(l.web_address ? [["Web", <WebLink key="w" url={l.web_address} className="text-gold hover:text-parchment break-all" />] as [string, ReactNode]] : []),
    ...(l.map_link ? [["Map", <WebLink key="m" url={l.map_link} className="text-gold hover:text-parchment">Open the map</WebLink>] as [string, ReactNode]] : []),
    ...(l.haven_of ? [["Haven of", l.haven_of.name] as [string, string]] : []),
    ...(l.elysium_since != null ? [["Elysium", `Unviolated since ${l.elysium_since}: ${l.elysium_qualities} Elysium ${l.elysium_qualities === 1 ? "quality" : "qualities"}`] as [string, string]] : []),
  ];
  return (
    <Card
      title={l.name}
      actions={
        <span className="flex items-center gap-2">
          {l.locked && <Badge tone="blood">Locked</Badge>}
          {onQuest && (
            <Button variant="ghost" onClick={onQuest}>
              Build a quest
            </Button>
          )}
          <Button variant="secondary" onClick={onEdit}>
            Edit
          </Button>
        </span>
      }
    >
      <dl className="grid gap-x-4 gap-y-1 text-sm sm:grid-cols-[10rem_1fr]">
        {rows.map(([label, value]) => (
          <div key={label} className="contents">
            <dt className="text-mist">{label}</dt>
            <dd className="mb-1 sm:mb-0">{value}</dd>
          </div>
        ))}
      </dl>
      {l.qualities.length > 0 && (
        <section className="mt-4">
          <h3 className="mb-1 font-sans text-xs tracking-wide text-mist uppercase">Qualities</h3>
          <ul className="flex flex-col gap-1 text-sm">
            {l.qualities.map((q, i) => (
              <li key={i}>
                <span className="text-parchment">{qualityText(q)}</span>
                {q.kind !== "standard" && <span className="ml-1 text-xs text-gold">{q.kind}</span>}
                {!q.known && <span className="ml-1 text-xs text-mist">(no longer offered here)</span>}
                {quality(q.name) && <span className="text-mist"> — {quality(q.name)!.text}</span>}
                {q.free_here && <span className="block text-xs text-gold">{q.free_here}</span>}
              </li>
            ))}
          </ul>
        </section>
      )}
      {l.negatives.length > 0 && (
        <section className="mt-4">
          <h3 className="mb-1 font-sans text-xs tracking-wide text-mist uppercase">Negative qualities</h3>
          <ul className="flex flex-col gap-1 text-sm">
            {l.negatives.map((n) => (
              <li key={n.name}>
                <span className="text-parchment">
                  {n.name} ×{n.level}
                </span>
                {n.secret && (
                  <span className="ml-2">
                    <Badge tone="blood">Secret</Badge>
                  </span>
                )}
                {n.by && <span className="text-mist"> · by {n.by}</span>}
                <span className="block text-xs text-mist">{n.effect}</span>
                {n.name === "Out of Code" && n.games > 0 && (
                  <span className="block text-xs text-blood-bright">
                    {n.games} {n.games === 1 ? "game has" : "games have"} passed at this level; it gets worse after two.
                  </span>
                )}
                {n.name === "Damaged" && l.damaged_off.length > 0 && <span className="block text-xs text-mist">Switched off: {l.damaged_off.join(", ")}.</span>}
              </li>
            ))}
          </ul>
        </section>
      )}
      {l.haven_advantages.length > 0 && (
        <section className="mt-4">
          <h3 className="mb-1 font-sans text-xs tracking-wide text-mist uppercase">Haven advantages</h3>
          <ul className="flex flex-col gap-1 text-sm">
            {l.haven_advantages.map((a) => (
              <li key={a}>
                <span className="text-parchment">{a}</span>
                {advantage(a) && <span className="text-mist"> — {advantage(a)!.text}</span>}
              </li>
            ))}
          </ul>
        </section>
      )}
      {l.notes && (
        <section className="mt-4">
          <h3 className="mb-1 font-sans text-xs tracking-wide text-mist uppercase">Notes for staff</h3>
          <p className="text-sm whitespace-pre-wrap">{l.notes}</p>
        </section>
      )}
    </Card>
  );
}
