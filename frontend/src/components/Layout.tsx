import { Link, NavLink, Outlet, useNavigate } from "react-router";
import { api, unwrap } from "../api/client";
import { useAction, useMe } from "../hooks";
import { NotificationBell } from "./NotificationBell";

export function Layout() {
  const me = useMe();
  const navigate = useNavigate();
  const signOut = useAction(async () => {
    await unwrap(api.POST("/api/auth/logout"));
    navigate("/sign-in");
  });

  const link = ({ isActive }: { isActive: boolean }) =>
    isActive ? "text-parchment" : "text-mist hover:text-parchment";

  return (
    <div className="min-h-screen">
      <header className="border-b border-ash bg-dusk/80 backdrop-blur">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-3 px-4 py-3">
          <Link to="/" className="font-display text-xl tracking-wider text-parchment">
            Horatio
          </Link>
          {me.data && (
            <nav className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
              <NavLink to="/characters" className={link}>
                Characters
              </NavLink>
              <NavLink to="/troupes" className={link}>
                Troupes
              </NavLink>
              {me.data.is_custodian && (
                <NavLink to="/custodian" className={link}>
                  Custodian
                </NavLink>
              )}
              <NotificationBell />
              <span className="hidden text-mist sm:inline">·</span>
              <NavLink to="/account" className={link} title="Your account">
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
    </div>
  );
}
