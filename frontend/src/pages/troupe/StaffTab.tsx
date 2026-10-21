import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { Role, TroupeOut } from "../../api/types";
import { AtHandle, PersonPicker } from "../../components/PersonPicker";
import { Button, Card, ErrorText, Field, Loading, Select } from "../../components/ui";
import { useAction } from "../../hooks";
import { roleLabel } from "./roles";

const ASSIGNABLE: Role[] = ["storyteller", "assistant_storyteller", "narrator"];

export function StaffTab({ troupe, canManage }: { troupe: TroupeOut; canManage: boolean }) {
  const path = { params: { path: { troupe_id: troupe.id } } };
  const staff = useQuery({ queryKey: ["staff", troupe.id], queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/staff", path)) });
  const [handle, setHandle] = useState("");
  const [role, setRole] = useState<Role>("narrator");
  const assign = useAction(async () => {
    await unwrap(api.PUT("/api/troupes/{troupe_id}/staff", { ...path, body: { handle, role } }));
    setHandle("");
  });
  const change = useAction((body: { handle: string; role: Role }) => unwrap(api.PUT("/api/troupes/{troupe_id}/staff", { ...path, body })));
  const remove = useAction((user_id: string) =>
    unwrap(api.DELETE("/api/troupes/{troupe_id}/staff/{user_id}", { params: { path: { troupe_id: troupe.id, user_id } } })),
  );

  return (
    <div className="grid gap-6 md:grid-cols-2">
      <Card title="Staff">
        {staff.isPending ? (
          <Loading />
        ) : (
          <ul className="divide-y divide-ash">
            {staff.data?.map((m) => (
              <li key={m.user_id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                <span>
                  <Link to={`/players/${m.user_id}`} className="hover:text-gold">
                    {m.display_name}
                  </Link>{" "}
                  <span className="text-sm text-mist">
                    <AtHandle handle={m.handle} /> · {roleLabel(m.role)}
                  </span>
                </span>
                {canManage && m.role !== "lead_storyteller" && (
                  <span className="flex shrink-0 items-center gap-1">
                    <Select
                      aria-label={`Role for ${m.display_name}`}
                      className="w-auto"
                      value={m.role}
                      disabled={change.isPending}
                      onChange={(e) => change.mutate({ handle: m.handle, role: e.target.value as Role })}
                    >
                      {ASSIGNABLE.map((r) => (
                        <option key={r} value={r}>
                          {roleLabel(r)}
                        </option>
                      ))}
                    </Select>
                    <Button variant="ghost" onClick={() => remove.mutate(m.user_id)}>
                      Remove
                    </Button>
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
        <ErrorText error={staff.error ?? change.error ?? remove.error} />
      </Card>
      {canManage && (
        <Card title="Add staff">
          <form
            className="flex flex-col gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              assign.mutate(undefined);
            }}
          >
            <Field label="Person" hint="Pick them from the list, or type a name or handle to find them. They need an account already.">
              <PersonPicker required troupeId={troupe.id} value={handle} onChange={setHandle} />
            </Field>
            <Field label="Role">
              <Select value={role} onChange={(e) => setRole(e.target.value as Role)}>
                {ASSIGNABLE.map((r) => (
                  <option key={r} value={r}>
                    {roleLabel(r)}
                  </option>
                ))}
              </Select>
            </Field>
            <ErrorText error={assign.error} />
            <Button type="submit" disabled={assign.isPending}>
              Save
            </Button>
          </form>
        </Card>
      )}
    </div>
  );
}
