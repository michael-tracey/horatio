import { useEffect, useId, useRef, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useMatch } from "react-router";
import { useMe } from "../hooks";
import { useAppearance } from "../loaders/useMotif";
import { NeedsConnection } from "../offline/NeedsConnection";
import { OfflineStrip, useSendWaiting, useSignOut } from "../offline/Offline";
import { NotificationBell } from "./NotificationBell";
import { Splash } from "./Splash";
import { ErrorText } from "./ui";

export function Layout() {
  const me = useMe();
  // Asked at once, beside who is signed in, for the loading animation (#568).
  useAppearance();
  // Signing out clears what is kept on this device for the person (#502).
  const signOut = useSignOut();
  useSendWaiting();

  const link = ({ isActive }: { isActive: boolean }) =>
    isActive ? "text-parchment" : "text-mist hover:text-parchment";
  // A downtime cycle's pages belong to its troupe.
  const inCycle = !!useMatch("/cycles/*");

  // Until we know who is signed in, carry on the loading screen from index.html;
  // offline, with nothing kept here, there is no knowing.
  if (me.isPending && me.fetchStatus === "paused")
    return (
      <main className="mx-auto max-w-5xl px-4 py-6">
        <NeedsConnection />
      </main>
    );
  if (me.isPending) return <Splash />;

  return (
    <div className="min-h-screen">
      <header className="relative z-20 border-b border-ash bg-dusk/80 backdrop-blur">
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-3 px-4 py-3">
          <Link to="/" className="flex items-center gap-2 font-display text-xl tracking-wider text-parchment">
            <img src="/mark-64.png" alt="" width={32} height={32} className="h-8 w-8" />
            Horatio
          </Link>
          {/* Signed out, the manual is the one place to go: it's for anyone. */}
          {!me.data && (
            <nav className="flex items-center gap-4 text-sm">
              <NavLink to="/help" className={link}>
                Help
              </NavLink>
            </nav>
          )}
          {me.data && (
            <>
              {/* The whole bar from lg up; below it, the bell and a menu, so the bar stays one line (#746). */}
              <nav aria-label="Main" className="hidden items-center gap-x-4 text-sm whitespace-nowrap lg:flex">
                <SiteLinks inCycle={inCycle} isCustodian={me.data.is_custodian} link={link} />
                <NotificationBell />
                <AccountLink name={me.data.display_name} isCustodian={me.data.is_custodian} className={(state) => `inline-flex min-w-0 items-center gap-1.5 ${link(state)}`} short />
                <button className="text-mist hover:text-parchment" onClick={signOut.signOut}>
                  Sign out
                </button>
              </nav>
              <div className="flex items-center gap-1 lg:hidden">
                <NotificationBell />
                <SiteMenu name={me.data.display_name} isCustodian={me.data.is_custodian} inCycle={inCycle} onSignOut={signOut.signOut} />
              </div>
            </>
          )}
        </div>
        {signOut.error !== null && (
          <div className="mx-auto max-w-5xl px-4 pb-3">
            <ErrorText error={signOut.error} />
          </div>
        )}
      </header>
      <OfflineStrip />
      {signOut.dialog}
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

type LinkClass = (state: { isActive: boolean }) => string;

/** The places every signed-in person can go, then Custodian for the custodian. */
function SiteLinks({ inCycle, isCustodian, link, onPick }: { inCycle: boolean; isCustodian: boolean; link: LinkClass; onPick?: () => void }) {
  return (
    <>
      <NavLink to="/characters" className={link} onClick={onPick}>
        Characters
      </NavLink>
      <NavLink to="/troupes" className={({ isActive }) => link({ isActive: isActive || inCycle })} onClick={onPick}>
        Troupes
      </NavLink>
      {/* The book's rules: named apart from a troupe's own Rules and House rules (#778). */}
      <NavLink to="/rules" className={link} onClick={onPick}>
        Rulebook
      </NavLink>
      <NavLink to="/help" className={link} onClick={onPick}>
        Help
      </NavLink>
      {isCustodian && (
        <NavLink to="/custodian" className={link} onClick={onPick}>
          Custodian
        </NavLink>
      )}
    </>
  );
}

/** The person's own name, which opens their account; "(custodian)" after it for the custodian. `short` cuts a long name short, to keep the bar to one line. */
function AccountLink({ name, isCustodian, className, short = false, onPick }: { name: string; isCustodian: boolean; className: LinkClass; short?: boolean; onPick?: () => void }) {
  return (
    <NavLink to="/account" className={className} title="Your account" onClick={onPick}>
      <svg viewBox="0 0 24 24" className="h-5 w-5 shrink-0" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
        <circle cx="12" cy="8" r="4" />
        <path d="M4 21a8 8 0 0 1 16 0" strokeLinecap="round" />
      </svg>
      <span className="sr-only">Your account: </span>
      <span className={short ? "max-w-48 truncate" : "min-w-0 break-words"}>{name}</span>
      {isCustodian && <span className="shrink-0"> (custodian)</span>}
    </NavLink>
  );
}

/**
 * Below lg, the bar's links behind a menu button (#746): it opens over the page under
 * the bar, one link to a line. Choosing a link, Escape, a press outside it or moving
 * to another page closes it; it takes focus as it opens and gives it back to the
 * button when Escape closes it.
 */
export function SiteMenu({ name, isCustodian, inCycle, onSignOut }: { name: string; isCustodian: boolean; inCycle: boolean; onSignOut: () => void }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const button = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const { pathname } = useLocation();

  // Moving to another page closes it, however the move came about.
  useEffect(() => setOpen(false), [pathname]);

  useEffect(() => {
    if (!open) return;
    panel.current?.querySelector<HTMLElement>("a, button")?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      setOpen(false);
      button.current?.focus();
    };
    const onDown = (e: MouseEvent | TouchEvent) => {
      const target = e.target as Node;
      if (!panel.current?.contains(target) && !button.current?.contains(target)) setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("touchstart", onDown);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("touchstart", onDown);
    };
  }, [open]);

  const item = ({ isActive }: { isActive: boolean }) =>
    `px-4 py-3 text-base ${isActive ? "bg-ash/40 text-parchment" : "text-mist hover:bg-ash/40 hover:text-parchment"}`;
  const close = () => setOpen(false);

  return (
    <>
      <button
        ref={button}
        aria-label="Menu"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen(!open)}
        className="grid h-9 w-9 place-items-center rounded-full text-mist hover:bg-ash/60 hover:text-parchment print:hidden"
      >
        <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true">
          {open ? <path d="M6 6l12 12M18 6L6 18" /> : <path d="M4 7h16M4 12h16M4 17h16" />}
        </svg>
      </button>
      {open && (
        <div ref={panel} id={id} className="absolute inset-x-0 top-full z-30 border-b border-ash bg-dusk shadow-xl print:hidden">
          <nav aria-label="Main" className="mx-auto flex max-w-5xl flex-col divide-y divide-ash/60 py-1">
            <SiteLinks inCycle={inCycle} isCustodian={isCustodian} link={(state) => `block ${item(state)}`} onPick={close} />
            <AccountLink name={name} isCustodian={isCustodian} className={(state) => `flex items-center gap-2 ${item(state)}`} onPick={close} />
            <button
              className="block px-4 py-3 text-left text-base text-mist hover:bg-ash/40 hover:text-parchment"
              onClick={() => {
                close();
                onSignOut();
              }}
            >
              Sign out
            </button>
          </nav>
        </div>
      )}
    </>
  );
}
