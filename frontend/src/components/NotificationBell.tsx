import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router";
import { api, unwrap } from "../api/client";
import type { NotificationOut } from "../api/types";
import { useDates } from "../dates";
import { useAction, useNotifications } from "../hooks";
import { Avatar } from "./Avatar";
import { EmptyState } from "./EmptyState";
import { PlayerInLine } from "./PlayerInLine";
import { PostThumb } from "./PostThumb";
import { CountBubble } from "./ui";

const RELATIVE = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });

/** "5 minutes ago", "yesterday", and so on. */
export function timeAgo(at: string, now = Date.now()): string {
  const seconds = Math.round((new Date(at).getTime() - now) / 1000);
  const steps: [Intl.RelativeTimeFormatUnit, number][] = [
    ["second", 60],
    ["minute", 60],
    ["hour", 24],
    ["day", 7],
    ["week", 4.35],
    ["month", 12],
    ["year", Infinity],
  ];
  let value = seconds;
  for (const [unit, size] of steps) {
    if (Math.abs(value) < size) return RELATIVE.format(Math.round(value), unit);
    value /= size;
  }
  return RELATIVE.format(Math.round(value), "year");
}

/** The bell in the menu bar: work waiting on you, then messages. Each opens where to deal with it. */
export function NotificationBell() {
  const bell = useNotifications(true);
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const read = useAction((ids?: string[]) => unwrap(api.POST("/api/notifications/read", { body: { ids: ids ?? null } })));

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !box.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);

  const items = bell.data?.items ?? [];
  const tasks = items.filter((i) => i.task);
  const messages = items.filter((i) => !i.task);
  const unread = messages.filter((i) => !i.read);

  const go = (item: NotificationOut) => {
    setOpen(false);
    if (!item.task && !item.read) read.mutate([item.id]);
    // A link elsewhere, such as a Discord channel or invite (#855), opens in a tab of its own.
    if (/^https?:\/\//i.test(item.link)) window.open(item.link, "_blank", "noopener,noreferrer");
    else navigate(item.link);
  };

  return (
    <div ref={box} className="relative">
      <button
        aria-label={bell.data?.count ? `Notifications, ${bell.data.count} waiting` : "Notifications"}
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        className="relative grid h-9 w-9 place-items-center rounded-full text-mist hover:bg-ash/60 hover:text-parchment"
      >
        <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
          <path d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9" strokeLinejoin="round" />
          <path d="M10.3 21a1.94 1.94 0 0 0 3.4 0" strokeLinecap="round" />
        </svg>
        <span className="absolute -top-0.5 -right-0.5">
          <CountBubble count={bell.data?.count ?? 0} label="waiting" />
        </span>
      </button>
      {open && (
        <div
          role="dialog"
          aria-label="Notifications"
          className="fixed inset-x-4 top-16 z-20 max-h-[70vh] overflow-y-auto rounded-lg border border-ash bg-dusk shadow-xl sm:absolute sm:inset-x-auto sm:top-full sm:right-0 sm:mt-2 sm:w-96"
        >
          {items.length === 0 && (
            <div className="px-4 py-2">
              <EmptyState title="Nothing waiting.">Tasks waiting on you, and messages for you, show here as they come.</EmptyState>
            </div>
          )}
          {tasks.length > 0 && <Group title="Waiting on you" items={tasks} onOpen={go} onFollow={() => setOpen(false)} />}
          {messages.length > 0 && (
            <Group
              title="Messages"
              items={messages}
              onOpen={go}
              onFollow={() => setOpen(false)}
              action={
                unread.length > 0 && (
                  <button className="text-xs text-mist hover:text-parchment" onClick={() => read.mutate(undefined)}>
                    Mark all read
                  </button>
                )
              }
            />
          )}
          <div className="px-4 py-2.5 text-right">
            <Link to="/account/notifications" onClick={() => setOpen(false)} className="text-xs text-mist underline hover:text-parchment">
              Notification settings
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}

function Group({
  title,
  items,
  onOpen,
  onFollow,
  action,
}: {
  title: string;
  items: NotificationOut[];
  onOpen: (i: NotificationOut) => void;
  /** A link in a line, such as a player's name, was followed (#1131). */
  onFollow: () => void;
  action?: React.ReactNode;
}) {
  const dates = useDates();
  return (
    <section className="border-b border-ash last:border-b-0">
      <h2 className="flex items-center justify-between px-4 pt-3 pb-1 font-sans text-xs tracking-wide text-mist uppercase">
        {title}
        {action}
      </h2>
      <ul>
        {items.map((item) => {
          // A line naming a player links their name to their profile (#1131). A link can't sit
          // in a button, so its row's button lies over the row, named by the line, and the link over that.
          const named = Boolean(item.player_id && item.player_name);
          const line = `notice-${item.id}`;
          const inside = (
            <>
              <span aria-hidden="true" className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${item.task ? "bg-blood-bright" : item.read ? "" : "bg-gold"}`} />
              {item.picture &&
                (item.kind === "announcement.published" ? (
                  <PostThumb picture={item.picture} className="h-9 w-9" />
                ) : (
                  <Avatar name="" picture={item.picture} size="sm" />
                ))}
              <span className="min-w-0">
                <span id={named ? line : undefined} className={`block text-sm ${item.read ? "text-mist" : "text-parchment"}`}>
                  {named ? (
                    <PlayerInLine text={item.summary} playerId={item.player_id} playerName={item.player_name} onFollow={onFollow} className="relative z-20" />
                  ) : (
                    item.summary
                  )}
                </span>
                <span className="block text-xs text-mist">
                  {item.troupe_name && `${item.troupe_name} · `}
                  <time dateTime={item.at} title={dates.dateTime(item.at)}>
                    {timeAgo(item.at)}
                  </time>
                </span>
              </span>
            </>
          );
          return (
            <li key={item.id}>
              {named ? (
                <div className="relative flex w-full gap-3 px-4 py-2.5 text-left hover:bg-ash/40">
                  <button onClick={() => onOpen(item)} aria-labelledby={line} className="absolute inset-0 z-10" />
                  {inside}
                </div>
              ) : (
                <button onClick={() => onOpen(item)} className="flex w-full gap-3 px-4 py-2.5 text-left hover:bg-ash/40">
                  {inside}
                </button>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
