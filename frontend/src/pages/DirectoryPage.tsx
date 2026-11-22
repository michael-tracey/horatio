import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";
import { api, unwrap } from "../api/client";
import { Checkbox } from "../components/Checkbox";
import { Pager } from "../components/Pager";
import { PublicTroupeRow } from "../components/PublicTroupeRow";
import { Button, Card, Empty, Field, Input, Loaded, PageTitle, Select } from "../components/ui";
import { useSearchParamsUpdate } from "../useSearchParamsUpdate";
import { ageFrom, apiQuery, DAYS, FREQUENCIES, NO_SEARCH, pageFrom, searchFrom, searching, TROUPES_PAGE_SIZE, withSearch, type Search } from "./directory";

/** The search: name and place to type, then Search; the rest search as they change. */
function SearchForm({ search, onSearch }: { search: Search; onSearch: (search: Search) => void }) {
  const [draft, setDraft] = useState(search);
  const [age, setAge] = useState(search.age === null ? "" : String(search.age));
  // Back, Forward and Clear change the address: the form follows it.
  const asked = JSON.stringify(search);
  useEffect(() => {
    setDraft(search);
    setAge(search.age === null ? "" : String(search.age));
    // Only when what the address asks for changes, not on every drawing.
  }, [asked]);
  const now = (more: Partial<Search>) => {
    const next = { ...draft, age: ageFrom(age), ...more };
    setDraft(next);
    onSearch(next);
  };
  const submit = (e: FormEvent) => {
    e.preventDefault();
    now({});
  };
  return (
    <form role="search" aria-label="Search troupes" onSubmit={submit} className="flex flex-col gap-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Name">
          <Input value={draft.name} maxLength={200} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
        </Field>
        <Field label="Place" hint="A town, city or region, or the venue's name.">
          <Input value={draft.place} maxLength={200} onChange={(e) => setDraft({ ...draft, place: e.target.value })} />
        </Field>
        <Field label="Day">
          <Select value={draft.day ?? ""} onChange={(e) => now({ day: DAYS.find((d) => d.day === e.target.value)?.day ?? null })}>
            <option value="">Any day</option>
            {DAYS.map((d) => (
              <option key={d.day} value={d.day}>
                {d.label}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="How often">
          <Select
            value={draft.frequency ?? ""}
            onChange={(e) => now({ frequency: FREQUENCIES.find((f) => f.frequency === e.target.value)?.frequency ?? null })}
          >
            <option value="">However often</option>
            {FREQUENCIES.map((f) => (
              <option key={f.frequency} value={f.frequency}>
                {f.label}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Your age" hint="Only troupes whose minimum age you meet, or that give none.">
          <Input type="number" inputMode="numeric" min={0} max={99} value={age} onChange={(e) => setAge(e.target.value)} className="w-24" />
        </Field>
        <Checkbox label="Only troupes welcoming new players" checked={draft.welcoming} onChange={(welcoming) => now({ welcoming })} className="self-end" />
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <Button type="submit">Search</Button>
        {searching(search) && (
          <Button type="button" variant="secondary" onClick={() => onSearch(NO_SEARCH)}>
            Clear the search
          </Button>
        )}
      </div>
    </form>
  );
}

/**
 * The troupe directory (#1192), at /find-a-troupe for anyone, signed in or not: every
 * troupe whose profile is public and that is still running, searched by name, place,
 * when it plays, whether it welcomes new players and age. Each opens its public
 * profile, where Request to join begins. The search is in the address.
 */
export function DirectoryPage() {
  const [params, update] = useSearchParamsUpdate();
  const search = searchFrom(params);
  const page = pageFrom(params);
  const query = apiQuery(search, page);
  const found = useQuery({
    queryKey: ["public-troupes", "directory", query],
    queryFn: () => unwrap(api.GET("/api/public/troupes", { params: { query } })),
    placeholderData: keepPreviousData,
  });
  const searched = searching(search);
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <PageTitle title="Find a troupe" subtitle="Mind's Eye Theatre LARP troupes on Horatio that show their profile to anyone.">
        Find a troupe
      </PageTitle>
      <Card>
        <SearchForm search={search} onSearch={(next) => update((now) => withSearch(now, next))} />
      </Card>
      <Card title="Troupes">
        <Loaded query={found}>
          {(found) =>
            found.total === 0 ? (
              <Empty>{searched ? "No troupe matches that search. Try fewer filters." : "No troupe shows its profile to everyone yet."}</Empty>
            ) : (
              <div className="flex flex-col gap-3">
                {found.troupes.length ? (
                  <ul aria-label="Troupes found" className="divide-y divide-ash">
                    {found.troupes.map((t) => (
                      <li key={t.id}>
                        <PublicTroupeRow troupe={t} details />
                      </li>
                    ))}
                  </ul>
                ) : (
                  <Empty>There are no more troupes. Go back a page.</Empty>
                )}
                <Pager
                  label="Pages of troupes"
                  page={found.page}
                  size={TROUPES_PAGE_SIZE}
                  shown={found.troupes.length}
                  total={found.total}
                  onPage={(to) => update((now) => withSearch(now, searchFrom(now), to))}
                />
              </div>
            )
          }
        </Loaded>
      </Card>
    </div>
  );
}
