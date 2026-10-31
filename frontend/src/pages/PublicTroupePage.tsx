import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router";
import { api, ApiError, unwrap } from "../api/client";
import { Loading, PageTitle } from "../components/ui";
import { useMe } from "../hooks";
import { withNext } from "../next";
import { TroupeProfileView } from "./troupe/TroupeProfile";

const primary = "inline-flex min-h-10 items-center justify-center rounded-md bg-blood px-4 text-sm font-medium text-parchment hover:bg-blood-bright";

/**
 * For someone signed out: make an account, the main way on, or sign in. Either
 * goes on to the troupe's own page, which tells them how to play there.
 */
function JoinOrSignIn({ troupeId }: { troupeId: string }) {
  const next = `/troupes/${troupeId}`;
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
      <Link to={withNext("/sign-up", next)} className={primary}>
        Create an account to play here
      </Link>
      <Link to={withNext("/sign-in", next)} className="text-sm text-gold underline">
        Sign in
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
        {!signedIn && <JoinOrSignIn troupeId={troupeId} />}
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
            <Link to={`/troupes/${p.id}`} className="text-sm text-gold underline">
              Open the troupe
            </Link>
          ) : (
            <JoinOrSignIn troupeId={p.id} />
          )
        }
      >
        {p.name}
      </PageTitle>
      <TroupeProfileView profile={p} signedIn={signedIn} />
    </>
  );
}
