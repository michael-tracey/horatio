import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router";
import { api, unwrap } from "../../api/client";
import type { DiscordAccount } from "../../api/types";
import { Button, Card, ErrorText } from "../../components/ui";
import { useAction } from "../../hooks";

/** What Discord's callback said (`?discord=` on /account), in plain words. */
export function outcome(said: string | null): { ok: boolean; text: string } | null {
  if (!said) return null;
  if (said === "linked") return { ok: true, text: "Your Discord account is linked." };
  if (said === "cancelled") return { ok: false, text: "Nothing was linked: you cancelled on Discord." };
  if (said === "taken") return { ok: false, text: "That Discord account is already linked to another Horatio account." };
  return { ok: false, text: said };
}

/**
 * Linking the player's own Discord account (#857): Discord confirms who they are,
 * so staff and the troupe's Discord know it's really them, not just a username
 * they typed. It changes nothing about how they sign in.
 */
export function DiscordLinkCard() {
  const [params, setParams] = useSearchParams();
  const account = useQuery({
    queryKey: ["account-discord"],
    queryFn: () => unwrap(api.GET("/api/account/discord")),
  });
  const link = useAction(async () => {
    const { url } = await unwrap(api.POST("/api/account/discord/link"));
    window.location.assign(url);
  });
  const unlink = useAction(() => unwrap(api.DELETE("/api/account/discord")), [["account-discord"], ["player"]]);
  const said = outcome(params.get("discord"));
  const dismiss = () => {
    const next = new URLSearchParams(params);
    next.delete("discord");
    setParams(next, { replace: true });
  };

  if (!account.data) return account.error ? <ErrorText error={account.error} /> : null;
  const data: DiscordAccount = account.data;
  if (!data.available && !data.linked) return null;

  return (
    <Card title="Discord account">
      <div className="flex flex-col gap-3">
        {said && (
          <p role="status" className={`flex flex-wrap items-center gap-2 text-sm ${said.ok ? "text-parchment" : "text-blood-bright"}`}>
            {said.text}
            <Button type="button" variant="ghost" className="min-h-8 px-2" onClick={dismiss}>
              Dismiss
            </Button>
          </p>
        )}
        {data.linked ? (
          <>
            <p className="text-sm text-mist">
              Linked to <span className="text-parchment">@{data.handle}</span>, as Discord confirmed it. Your profile shows that username, and staff can see it's really you.
            </p>
            {data.can_unlink ? (
              <Button type="button" variant="secondary" className="self-start" disabled={unlink.isPending} onClick={() => unlink.mutate(undefined)}>
                Unlink Discord
              </Button>
            ) : (
              <p className="text-sm text-mist">Discord is your only way to sign in, so it stays linked.</p>
            )}
          </>
        ) : (
          <>
            <p className="text-sm text-mist">
              Link your Discord account so staff and your troupe's Discord know it's really you. Discord tells Horatio your username and nothing else, and it doesn't change how you
              sign in.
            </p>
            <Button type="button" variant="secondary" className="self-start" disabled={link.isPending} onClick={() => link.mutate(undefined)}>
              Link my Discord
            </Button>
          </>
        )}
        <ErrorText error={link.error ?? unlink.error} />
      </div>
    </Card>
  );
}
