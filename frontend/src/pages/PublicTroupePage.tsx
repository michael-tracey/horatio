import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router";
import { api, ApiError, unwrap } from "../api/client";
import { LinkButton } from "../components/LinkButton";
import { Loading, PageTitle, SessionCheckFailed } from "../components/ui";
import { useMe } from "../hooks";
import { withNext } from "../next";
import { DIRECTORY, requestToJoin } from "./directory";
import { TroupeProfileView } from "./troupe/TroupeProfile";

/**
 * For someone signed out: Request to join makes an account, the main way on, or they
 * sign in. Either goes on into asking the troupe to take a character (#1192).
 */
function JoinOrSignIn({ troupeId }: { troupeId: string }) {
  const next = requestToJoin(troupeId);
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
      <LinkButton to={withNext("/sign-up", next)}>Request to join</LinkButton>
      <Link to={withNext("/sign-in", next)} className="text-sm text-gold underline">
        Sign in
      </Link>
    </div>
  );
}

/**
 * For someone signed in: Request to join, into the ask-to-join flow with this troupe
 * chosen, unless they're on its staff or have a character at home in it already; and
 * the troupe's own page.
 */
function JoinOrOpen({ troupeId }: { troupeId: string }) {
  const troupe = useQuery({
    queryKey: ["troupe", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}", { params: { path: { troupe_id: troupeId } } })),
  });
  const characters = useQuery({ queryKey: ["characters"], queryFn: () => unwrap(api.GET("/api/characters")) });
  const inIt =
    !!troupe.data?.my_role ||
    !!troupe.data?.archived ||
    !!characters.data?.some((c) => c.status === "active" && c.home_troupe_id === troupeId);
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
      {!inIt && <LinkButton to={requestToJoin(troupeId)}>Request to join</LinkButton>}
      <Link to={`/troupes/${troupeId}`} className="text-sm text-gold underline">
        Open the troupe
      </Link>
    </div>
  );
}

/**
 * A troupe's profile at its shareable address, /t/<troupe>: for anyone at all
 * when the troupe has made it public, and for anyone signed in either way.
 */
export function PublicTroupePage() {
  const { troupeId = "" } = useParams();
  const me = useMe();
  const signedIn = !!me.data;
  // Couldn't tell (the server failed): neither the troupe's own page nor signing in (#621).
  const unknown = !signedIn && me.isError;
  const profile = useQuery({
    queryKey: ["troupe-profile", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/profile", { params: { path: { troupe_id: troupeId } } })),
    retry: false,
  });

  if (profile.isPending) return <Loading />;
  if (profile.error) {
    const missing = profile.error instanceof ApiError && profile.error.status === 404;
    return (
      <div className="flex flex-col items-start gap-3">
        <p className="text-mist">
          {missing ? (signedIn ? "There is no such troupe." : "This troupe's profile is only for people signed in, or there is no such troupe.") : profile.error.message}
        </p>
        {unknown ? <SessionCheckFailed /> : !signedIn && <JoinOrSignIn troupeId={troupeId} />}
      </div>
    );
  }
  const p = profile.data;

  return (
    <>
      {p.banner && (
        <img
          src={`${p.banner}/1500.webp`}
          srcSet={`${p.banner}/750.webp 750w, ${p.banner}/1500.webp 1500w`}
          sizes="(min-width: 64rem) 64rem, 100vw"
          alt=""
          className="mb-4 aspect-[3/1] w-full rounded-lg border border-ash object-cover"
        />
      )}
      <PageTitle
        actions={
          signedIn ? (
            <JoinOrOpen troupeId={p.id} />
          ) : unknown ? (
            <SessionCheckFailed />
          ) : (
            <JoinOrSignIn troupeId={p.id} />
          )
        }
      >
        {p.name}
      </PageTitle>
      <TroupeProfileView profile={p} signedIn={signedIn} />
      {p.public && (
        <p className="mt-6 text-sm">
          <Link to={DIRECTORY} className="text-gold underline hover:text-parchment">
            Find another troupe
          </Link>
        </p>
      )}
    </>
  );
}
