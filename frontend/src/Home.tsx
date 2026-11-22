import { lazy } from "react";
import { Navigate } from "react-router";
import { Loading, SessionCheckFailed } from "./components/ui";
import { useMe } from "./hooks";
import { NeedsConnection } from "./offline/NeedsConnection";
import { LazyPages } from "./staleBuild";

// Loaded only for people signed out, so someone signed in never downloads it.
const LandingPage = lazy(() => import("./pages/LandingPage").then((m) => ({ default: m.LandingPage })));

/**
 * The site's front door, `/`. Signed in, on to Characters as ever (RequireSignIn there
 * sends someone who must set up two-step sign-in to do that first). Signed out, the
 * landing page (#1164). A session check that fails says so, as RequireSignIn does.
 */
export function Home() {
  const me = useMe();
  if (me.data) return <Navigate to="/characters" replace />;
  if (me.isPending) return me.fetchStatus === "paused" ? <NeedsConnection /> : <Loading />;
  if (me.isError)
    return me.fetchStatus === "paused" ? (
      <NeedsConnection />
    ) : (
      <div className="mx-auto max-w-md px-4 py-8">
        <SessionCheckFailed />
      </div>
    );
  return (
    <LazyPages>
      <LandingPage />
    </LazyPages>
  );
}
