import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import { Card, Empty, ErrorText, Input, Loading } from "../../components/ui";
import { memberSince } from "../players";

/** Every account, for the custodian: find someone by name or email. Open someone to
 * see their profile or reset their password. */
export function PeopleTab() {
  const [q, setQ] = useState("");
  const people = useQuery({
    queryKey: ["players", q],
    queryFn: () => unwrap(api.GET("/api/players", { params: { query: { q } } })),
    placeholderData: (previous) => previous,
  });

  return (
    <Card>
      <Input type="search" aria-label="Search people" placeholder="Name or email…" value={q} onChange={(e) => setQ(e.target.value)} className="mb-3" />
      {people.isPending ? (
        <Loading />
      ) : people.data?.length ? (
        <ul className="divide-y divide-ash text-sm">
          {people.data.map((p) => (
            <li key={p.id}>
              <Link to={`/players/${p.id}`} className="flex flex-col gap-0.5 py-2 hover:text-gold sm:flex-row sm:items-center sm:justify-between">
                <span>{p.display_name}</span>
                <span className="text-xs break-all text-mist">
                  {p.email} · since {memberSince(p.member_since)}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        <Empty>No one matches.</Empty>
      )}
      <ErrorText error={people.error} />
    </Card>
  );
}
