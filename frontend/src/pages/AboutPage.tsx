import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { api, unwrap } from "../api/client";
import { Card, PageTitle } from "../components/ui";
import { useMe } from "../hooks";

const SOURCE = "https://github.com/michael-tracey/horatio";
const DARK_PACK = "https://www.paradoxinteractive.com/games/world-of-darkness/community/dark-pack-agreement";

/** Paradox's notice, word for word, as the Dark Pack Agreement asks. */
export const PARADOX_NOTICE =
  "Portions of the materials are the copyrights and trademarks of Paradox Interactive AB, and are used with permission. All rights reserved. For more information please visit worldofdarkness.com.";

function A({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a href={href} target="_blank" rel="noreferrer" className="text-gold underline hover:text-parchment">
      {children}
    </a>
  );
}

/**
 * What Horatio is, and what the Dark Pack Agreement asks of it: the Dark Pack
 * logo, Paradox's notice, and that it is unofficial. Public, like the sign-in page.
 */
export function AboutPage() {
  const me = useMe();
  const darkPack = useQuery({ queryKey: ["dark-pack"], queryFn: () => unwrap(api.GET("/api/dark-pack")), staleTime: 5 * 60_000 });
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <PageTitle subtitle="Character sheets, downtimes and game nights for Mind's Eye Theatre LARP troupes.">About Horatio</PageTitle>

      <Card title="What Horatio is">
        <div className="flex flex-col gap-3 text-sm leading-relaxed">
          <p>
            Horatio keeps a LARP troupe's characters, experience, downtimes and game nights in one place: players build and play their characters, and storytellers
            run the troupe around them.
          </p>
          <p>
            It is free, and always will be: no fees, no subscriptions, nothing to buy inside it. Its code is open source under the GNU Affero General Public
            License; you can read it, run your own copy, and improve it at <A href={SOURCE}>{SOURCE.replace("https://", "")}</A>.
          </p>
          <p>
            The rules Horatio follows come from <em>Mind's Eye Theatre: Vampire The Masquerade</em>, published by By Night Studios. Horatio describes traits and
            powers in its own words, briefly; you still need the books to play.
          </p>
        </div>
      </Card>

      <Card title="The Dark Pack">
        <div className="flex flex-col items-start gap-4 text-sm leading-relaxed sm:flex-row">
          {darkPack.data?.logo && <img src="/api/dark-pack/logo.webp" alt="Dark Pack" width={160} height={160} className="h-40 w-40 shrink-0 object-contain" />}
          <div className="flex flex-col gap-3">
            <p>
              Horatio is unofficial fan-made material, made under Paradox Interactive's <A href={DARK_PACK}>Dark Pack Agreement</A>. It is not official World of
              Darkness material, and it is not endorsed by Paradox Interactive or By Night Studios.
            </p>
            <p className="border-l-2 border-gold/60 pl-3 text-parchment">{PARADOX_NOTICE}</p>
            <p>
              World of Darkness, Vampire: The Masquerade and their clans, disciplines and symbols are Paradox's. Visit <A href="https://www.worldofdarkness.com">worldofdarkness.com</A>{" "}
              to learn more.
            </p>
            {darkPack.data?.clans.length ? (
              <p className="text-mist">The clan symbols on this server's badges come from the Dark Pack's community assets.</p>
            ) : null}
          </div>
        </div>
        {me.data?.is_custodian && darkPack.data && !darkPack.data.logo && (
          <p className="mt-4 rounded-md border border-gold/40 bg-gold/10 px-3 py-2 text-sm">
            For the custodian: the Dark Pack logo isn't on this server yet. The agreement asks for it. Import the Dark Pack resources as{" "}
            <code>dark-pack/README.md</code> describes, and it appears here, with the clan symbols for badges.
          </p>
        )}
      </Card>
    </div>
  );
}
