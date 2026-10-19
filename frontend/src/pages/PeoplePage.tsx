import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, Navigate } from "react-router";
import { api, unwrap } from "../api/client";
import { Card, Empty, ErrorText, Input, Loading, PageTitle } from "../components/ui";
import { useMe } from "../hooks";
import { memberSince } from "./players";

/** Every account, for the custodian: find someone by name or email. */
export function PeoplePage() {
  const me = useMe();
  const [q, setQ] = useState("");
  const people = useQuery({
    queryKey: ["players", q],
    queryFn: () => unwrap(api.GET("/api/players", { params: { query: { q } } })),
    enabled: !!me.data?.is_custodian,
    placeholderData: (previous) => previous,
  });
  if (me.data && !me.data.is_custodian) return <Navigate to="/characters" replace />;

  return (
    <>
      <PageTitle subtitle="Everyone with an account. Open someone to see their profile or reset their password.">People</PageTitle>
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
    </>
  );
}
