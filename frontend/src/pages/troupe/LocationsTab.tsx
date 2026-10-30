import { useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { Link, Route, Routes, useLocation, useNavigate, useParams } from "react-router";
import { api, unwrap } from "../../api/client";
import type { LocationCatalogueOut, LocationDetailOut, LocationOut } from "../../api/types";
import { LogList } from "../../components/LogList";
import { Badge, Button, Card, Empty, ErrorText, Input, Loading, Select } from "../../components/ui";
import { useAction } from "../../hooks";
import { LocationForm, Warnings } from "./LocationForm";
import { controlText, controllerKey, countText, distinct, filtered, influenceText, NO_FILTERS, qualitiesText, qualityText, typeText, type Filters } from "./locations";

/**
 * The troupe's locations, for its storytellers and assistants: the Stock
 * Locations that matter in its chronicle and its characters' Havens, with who
 * controls each. Players never see the record.
 */
export function LocationsTab({ troupeId }: { troupeId: string }) {
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
      <Route index element={<List troupeId={troupeId} locations={list.data} catalogue={catalogue.data} />} />
      <Route path="new" element={<New troupeId={troupeId} locations={list.data} catalogue={catalogue.data} />} />
      <Route path=":locationId" element={<One troupeId={troupeId} locations={list.data} catalogue={catalogue.data} />} />
    </Routes>
  );
}

type Props = { troupeId: string; locations: LocationOut[]; catalogue: LocationCatalogueOut };

function List({ troupeId, locations, catalogue }: Props) {
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
        actions={
          <Button variant="secondary" onClick={() => navigate(`/troupes/${troupeId}/locations/new`)}>
            Add a location
          </Button>
        }
      >
        <p className="mb-3 text-sm text-mist">
          The places that matter here, with their qualities and who controls them ({catalogue.book}, pp. 117–133). Only storytellers and assistant storytellers see this
          list. A character controls up to five locations, and one more for each dot of Retainers; Havens don't count.
        </p>
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
      </Card>
      {locations.length === 0 ? (
        <Empty>No locations yet.</Empty>
      ) : shown.length === 0 ? (
        <Empty>No locations match.</Empty>
      ) : (
        <ul className="flex flex-col gap-2" aria-label="Locations">
          {shown.map((l) => (
            <li key={l.id} className="rounded-md border border-ash bg-dusk p-3 text-sm">
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <Link to={l.id} className="text-gold hover:text-parchment">
                  {l.name}
                </Link>
                <span className="text-mist">· {typeText(l)}</span>
                <span className="text-mist">· {controlText(l)}</span>
                {l.locked && <Badge tone="blood">Locked</Badge>}
                {l.haven_of && <Badge tone="gold">Haven</Badge>}
                {l.elysium_since != null && <Badge tone="gold">Elysium</Badge>}
                {l.negatives.length > 0 && <Badge tone="blood">{l.negatives.map((n) => `${n.name} ×${n.level}`).join(", ")}</Badge>}
              </div>
              {l.qualities.length > 0 && <p className="mt-1">{qualitiesText(l.qualities)}</p>}
              {(l.address || influenceText(l) || l.feeding_block || l.parent) && (
                <p className="mt-1 text-xs text-mist">
                  {[l.parent && `Part of ${l.parent.name}`, influenceText(l), l.feeding_block && `Feeding block: ${l.feeding_block}`, l.address].filter(Boolean).join(" · ")}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
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

function One({ troupeId, locations, catalogue }: Props) {
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
            <Record location={location.data} catalogue={catalogue} onEdit={() => setEditing(true)} />
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
function Record({ location: l, catalogue, onEdit }: { location: LocationDetailOut; catalogue: LocationCatalogueOut; onEdit: () => void }) {
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
    ...(l.web_address ? [["Web", <a key="w" href={l.web_address} target="_blank" rel="noreferrer" className="text-gold hover:text-parchment break-all">{l.web_address}</a>] as [string, ReactNode]] : []),
    ...(l.map_link ? [["Map", <a key="m" href={l.map_link} target="_blank" rel="noreferrer" className="text-gold hover:text-parchment">Open the map</a>] as [string, ReactNode]] : []),
    ...(l.haven_of ? [["Haven of", l.haven_of.name] as [string, string]] : []),
    ...(l.elysium_since != null ? [["Elysium", `Unviolated since ${l.elysium_since}: ${l.elysium_qualities} Elysium ${l.elysium_qualities === 1 ? "quality" : "qualities"}`] as [string, string]] : []),
  ];
  return (
    <Card
      title={l.name}
      actions={
        <span className="flex items-center gap-2">
          {l.locked && <Badge tone="blood">Locked</Badge>}
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
