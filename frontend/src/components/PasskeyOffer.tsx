import { useQuery } from "@tanstack/react-query";
import { browserSupportsWebAuthn, platformAuthenticatorIsAvailable } from "@simplewebauthn/browser";
import { useState } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../api/client";
import { useMe } from "../hooks";
import { offerAnswered, offerDue } from "../passkeyOffer";
import { Button, buttonClasses } from "./ui";

/**
 * After a password sign-in, on a device that can keep a passkey of its own (its face,
 * finger or PIN), the offer to add one (#1193): once on each device (horatio's
 * passkeyOffer), with **Not now**. **Add a passkey** goes to the usual form in Account ›
 * Sign-in, which asks for the password as ever. Never while two-step sign-in is still
 * to be set up, nor where this site can't make passkeys.
 */
export function PasskeyOffer() {
  const me = useMe();
  const [, answered] = useState(0);
  const due = offerDue() && !!me.data && !me.data.two_step_needed;
  const device = useQuery({
    queryKey: ["platform-passkeys"],
    queryFn: async () => browserSupportsWebAuthn() && (await platformAuthenticatorIsAvailable()),
    enabled: due,
    staleTime: Infinity,
  });
  const site = useQuery({ queryKey: ["two-step"], queryFn: () => unwrap(api.GET("/api/two-step")), enabled: due && device.data === true });
  if (!due || device.data !== true || !site.data?.passkeys_available) return null;
  const answer = () => {
    offerAnswered();
    answered((n) => n + 1);
  };
  return (
    <section aria-label="Add a passkey" className="mb-4 flex flex-wrap items-center gap-3 rounded-lg border border-gold/60 bg-dusk p-3 text-sm sm:mb-6">
      <p className="min-w-0 flex-1 basis-60">This device can keep a passkey. Add one, and next time it signs you in alone, with no password.</p>
      <div className="flex flex-wrap gap-2">
        <Link to="/account/sign-in#passkeys" className={buttonClasses("primary")} onClick={answer}>
          Add a passkey
        </Link>
        <Button type="button" variant="ghost" onClick={answer}>
          Not now
        </Button>
      </div>
    </section>
  );
}
