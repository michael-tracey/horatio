import { Link, NavLink, Outlet, useMatch, useNavigate } from "react-router";
import { api, unwrap } from "../api/client";
import { useAction, useMe } from "../hooks";
import { NotificationBell } from "./NotificationBell";
import { Splash } from "./Splash";

export function Layout() {
  const me = useMe();
  const navigate = useNavigate();
  const signOut = useAction(async () => {
    await unwrap(api.POST("/api/auth/logout"));
    navigate("/sign-in");
  });

  const link = ({ isActive }: { isActive: boolean }) =>
    isActive ? "text-parchment" : "text-mist hover:text-parchment";
  // A downtime cycle's pages belong to its troupe.
  const inCycle = !!useMatch("/cycles/*");

  // Until we know who is signed in, carry on the loading screen from index.html.
  if (me.isPending) return <Splash />;

  return (
    <div className="min-h-screen">
      <header className="border-b border-ash bg-dusk/80 backdrop-blur">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-3 px-4 py-3">
          <Link to="/" className="flex items-center gap-2 font-display text-xl tracking-wider text-parchment">
            <img src="/mark-64.png" alt="" width={32} height={32} className="h-8 w-8" />
            Horatio
          </Link>
          {me.data && (
            <nav className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
              <NavLink to="/characters" className={link}>
                Characters
              </NavLink>
              <NavLink to="/troupes" className={({ isActive }) => link({ isActive: isActive || inCycle })}>
                Troupes
              </NavLink>
              {/* Named apart from a troupe's own Rules tab under Customise. */}
              <NavLink to="/rules" className={link} aria-label="Rules reference">
                Rules
              </NavLink>
              {me.data.is_custodian && (
                <NavLink to="/custodian" className={link}>
                  Custodian
                </NavLink>
              )}
              <NotificationBell />
              <NavLink to="/account" className={(state) => `inline-flex items-center gap-1.5 ${link(state)}`} title="Your account">
                <svg viewBox="0 0 24 24" className="h-5 w-5 shrink-0" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
                  <circle cx="12" cy="8" r="4" />
                  <path d="M4 21a8 8 0 0 1 16 0" strokeLinecap="round" />
                </svg>
                <span className="sr-only">Your account: </span>
                {me.data.display_name}
                <span className="hidden sm:inline">{me.data.is_custodian && " (custodian)"}</span>
              </NavLink>
              <button className="text-mist hover:text-parchment" onClick={() => signOut.mutate(undefined)}>
                Sign out
              </button>
            </nav>
          )}
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-6 sm:py-8">
        <Outlet />
      </main>
      {/* The Dark Pack Agreement's notices, on every page (in full on About). */}
      <footer className="mx-auto max-w-5xl px-4 pt-2 pb-8 text-center text-xs text-mist">
        Unofficial fan-made material under Paradox Interactive's Dark Pack Agreement. Portions © Paradox Interactive AB, used with permission. ·{" "}
        <Link to="/about" className="underline hover:text-parchment">
          About Horatio
        </Link>
      </footer>
    </div>
  );
}
