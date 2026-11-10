import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router";
import { api, unwrap } from "../api/client";
import { Avatar } from "../components/Avatar";
import { useToast } from "../components/Toast";
import { Button, Card, ErrorText, Loading, SessionCheckFailed } from "../components/ui";
import { useDates } from "../dates";
import { useAction, useMe } from "../hooks";
import { withNext } from "../next";

/**
 * Where a claim link lands (#481): the character a troupe is giving its player, with
 * its portrait. Signed in, claim it; signed out, sign up (or in) first and come back
 * here. It asks first, so a mail program that opens links to check them claims nothing.
 */
export function ClaimPage() {
  const { token = "" } = useParams();
  const me = useMe();
  const dates = useDates();
  const toast = useToast();
  const navigate = useNavigate();
  const here = `/claim/${token}`;
  const claim = useQuery({
    queryKey: ["claim", token, !!me.data],
    queryFn: () => unwrap(api.GET("/api/claims/{token}", { params: { path: { token } } })),
    retry: false,
    enabled: !me.isPending,
  });
  const take = useAction(async () => {
    const character = await unwrap(api.POST("/api/claims/{token}", { params: { path: { token } } }));
    toast({ message: `${character.name} is yours now.` });
    navigate(`/characters/${character.id}`);
  });

  return (
    <div className="mx-auto mt-2 max-w-sm sm:mt-8">
      <Card title="Claim your character">
        <div className="flex flex-col gap-4 text-sm">
          {claim.isPending ? (
            <Loading />
          ) : claim.error ? (
            <ErrorText error={claim.error} />
          ) : (
            <>
              <div className="flex items-center gap-4">
                <Avatar name={claim.data.character_name} picture={claim.data.picture} clan={claim.data.clan} size="md" />
                <div>
                  <p className="font-display text-lg text-gold">{claim.data.character_name}</p>
                  <p className="text-mist">{claim.data.clan ? `${claim.data.clan}, of ${claim.data.troupe_name}` : claim.data.troupe_name}</p>
                </div>
              </div>
              <p>
                {claim.data.troupe_name} is giving you {claim.data.character_name}: once you claim it, it is your character, at home in the troupe and already accepted.
                {claim.data.carried_xp > 0 && <> It comes with {claim.data.carried_xp} unspent XP carried over.</>}
              </p>
              <p className="text-xs text-mist">This link works once, until {dates.dateTime(claim.data.expires_at)}.</p>
              {me.data ? (
                <>
                  <ErrorText error={take.error} />
                  <Button onClick={() => take.mutate(undefined)} disabled={take.isPending}>
                    Claim {claim.data.character_name}
                  </Button>
                  <p className="text-xs text-mist">Signed in as @{me.data.handle}. Not you? Sign out first.</p>
                </>
              ) : me.isError ? (
                // Not known to be signed out: don't offer an account (#621).
                <SessionCheckFailed />
              ) : (
                <>
                  <Link
                    to={withNext("/sign-up", here)}
                    className="inline-flex min-h-10 items-center justify-center rounded-md bg-blood px-5 text-sm font-medium text-parchment hover:bg-blood-bright"
                  >
                    Sign up to claim it
                  </Link>
                  <p className="text-center">
                    Already have an account?{" "}
                    <Link to={withNext("/sign-in", here)} className="text-gold underline">
                      Sign in
                    </Link>
                  </p>
                </>
              )}
            </>
          )}
        </div>
      </Card>
    </div>
  );
}
