import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router";
import { api, ApiError, unwrap } from "../api/client";
import { Loading, PageTitle } from "../components/ui";
import { useMe } from "../hooks";
import { TroupeProfileView } from "./troupe/TroupeProfile";

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
        {!signedIn && (
          <Link to="/sign-in" className="text-gold underline">
            Sign in
          </Link>
        )}
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
            <Link to="/sign-in" className="text-sm text-gold underline">
              Sign in
            </Link>
          )
        }
      >
        {p.name}
      </PageTitle>
      <TroupeProfileView profile={p} signedIn={signedIn} />
    </>
  );
}
