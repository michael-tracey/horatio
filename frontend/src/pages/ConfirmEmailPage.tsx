import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router";
import { api, unwrap } from "../api/client";
import { Button, Card, ErrorText, Loading, Notice } from "../components/ui";
import { useAction, useMe } from "../hooks";

/**
 * Where the link sent to a new address lands: confirm it, and the account's
 * email changes. No sign-in needed, since the player may have lost the old
 * address. It asks first, so a mail program that opens links to check them
 * changes nothing.
 */
export function ConfirmEmailPage() {
  const { token = "" } = useParams();
  const me = useMe();
  const change = useQuery({
    queryKey: ["email-change", token],
    queryFn: () => unwrap(api.GET("/api/auth/email-change/{token}", { params: { path: { token } } })),
    retry: false,
  });
  const confirm = useAction(() => unwrap(api.POST("/api/auth/email-change/{token}", { params: { path: { token } } })));
  const onward = me.data ? (
    <Link to="/account" className="text-center text-gold underline">
      Back to your account
    </Link>
  ) : (
    <Link to="/sign-in" className="text-center text-gold underline">
      Sign in
    </Link>
  );

  return (
    <div className="mx-auto mt-2 max-w-sm sm:mt-8">
      <Card title="Confirm your new email">
        <div className="flex flex-col gap-4 text-sm">
          {confirm.data ? (
            <>
              <Notice>Done: your email is now {confirm.data.email}. Sign in with it from now on.</Notice>
              {onward}
            </>
          ) : change.isPending ? (
            <Loading />
          ) : change.error ? (
            <>
              <ErrorText error={change.error} />
              {onward}
            </>
          ) : (
            <>
              <p>
                Change the email of {change.data.display_name}'s Horatio account (@{change.data.handle}) to {change.data.new_email}?
              </p>
              <ErrorText error={confirm.error} />
              <Button onClick={() => confirm.mutate(undefined)} disabled={confirm.isPending}>
                Confirm new email
              </Button>
            </>
          )}
        </div>
      </Card>
    </div>
  );
}
