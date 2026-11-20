import { Navigate, Outlet, useLocation } from "react-router";
import { Loading, SessionCheckFailed } from "./components/ui";
import { useMe } from "./hooks";
import { withNext } from "./next";
import { NeedsConnection } from "./offline/NeedsConnection";
import { LazyPages } from "./staleBuild";

/**
 * The pages for someone signed in. Only the server saying there is no session (a
 * 401, which `useMe` makes null) sends the person to sign in; any other failure
 * says so on the page they asked for, with Try again (#621). Someone who must set up
 * two-step sign-in is sent to do that first, wherever they were going (#1057).
 */
export function RequireSignIn() {
  const me = useMe();
  const location = useLocation();
  // Offline with nothing kept here, it can't know who is signed in.
  if (me.isPending && me.fetchStatus === "paused") return <NeedsConnection />;
  if (me.isPending) return <Loading />;
  // Someone who must have two-step sign-in sets it up first (#1057).
  if (me.data?.two_step_needed && location.pathname !== TWO_STEP) return <Navigate to={withNext(TWO_STEP, here(location))} replace />;
  if (me.data)
    return (
      <LazyPages>
        <Outlet />
      </LazyPages>
    );
  if (me.isError)
    return me.fetchStatus === "paused" ? (
      <NeedsConnection />
    ) : (
      <div className="mx-auto max-w-md px-4 py-8">
        <SessionCheckFailed />
      </div>
    );
  // Sign in, then on to where they were going.
  return <Navigate to={withNext("/sign-in", here(location))} replace />;
}

const TWO_STEP = "/two-step";

/** Where they were going, to go on to afterwards. */
function here(location: { pathname: string; search: string; hash: string }): string | null {
  return location.pathname === "/" ? null : location.pathname + location.search + location.hash;
}
