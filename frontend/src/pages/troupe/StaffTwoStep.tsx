import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { components } from "../../api/schema";
import { Toggle } from "../../components/Toggle";
import { Card, ErrorText, Loaded } from "../../components/ui";
import { useAction } from "../../hooks";

type StaffMember = components["schemas"]["StaffMember"];

/**
 * Whether the troupe asks its staff to sign in with two steps (#1057): its lead
 * storyteller chooses (or the custodian). Those without it are sent to set it up when
 * they next open Horatio. Someone on the staff of two troupes needs it if either asks.
 * The staff see who has it.
 */
export function StaffTwoStep({ troupeId, staff }: { troupeId: string; staff: StaffMember[] }) {
  const path = { params: { path: { troupe_id: troupeId } } };
  const key = ["staff-two-step", troupeId];
  const state = useQuery({ queryKey: key, queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/staff-two-step", path)) });
  const set = useAction((required: boolean) => unwrap(api.PUT("/api/troupes/{troupe_id}/staff-two-step", { ...path, body: { required } })), [key]);
  return (
    <Card title="Two-step sign-in">
      <Loaded query={state}>
        {(s) => {
          const without = staff.filter((m) => !s.staff.find((h) => h.user_id === m.user_id)?.two_step);
          return (
            <div className="flex flex-col gap-2 text-sm">
              {s.can_change ? (
                <Toggle
                  label="Staff must sign in with two steps"
                  hint="After their password, a passkey or a code from an authenticator app. Staff see players' emails and lines and veils."
                  checked={s.required}
                  disabled={set.isPending}
                  onChange={(on) => set.mutate(on)}
                />
              ) : (
                <p>{s.required ? "This troupe's staff must sign in with two steps." : "This troupe doesn't ask its staff to sign in with two steps."}</p>
              )}
              {without.length > 0 ? (
                <p className="text-mist">
                  Not set up yet: {without.map((m) => m.display_name).join(", ")}.{s.required && " They're asked to set it up when they next open Horatio."}
                </p>
              ) : (
                <p className="text-mist">Everyone on the staff has it set up.</p>
              )}
              <p className="text-mist">
                Your own is in{" "}
                <Link to="/account/sign-in" className="text-gold underline">
                  Account › Sign-in and email
                </Link>
                .
              </p>
              <ErrorText error={set.error} />
            </div>
          );
        }}
      </Loaded>
    </Card>
  );
}
