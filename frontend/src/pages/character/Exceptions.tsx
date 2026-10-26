import { useState } from "react";
import type { ExceptionOut } from "../../api/types";
import { Card } from "../../components/ui";
import { useDates } from "../../dates";

/** "Given by exception: approved by Clara, 12 Oct 2026, free". */
export function exceptionText(exception: ExceptionOut, date: (at: string) => string): string {
  const free = exception.free ? ", free" : "";
  if (exception.status === "waiting") return `Asked as an exception${free}: waiting on the storytellers`;
  const who = `${exception.status === "approved" ? "approved" : "given"} by ${exception.by ?? "staff"}`;
  return `Given by exception: ${who}${exception.at ? `, ${date(exception.at)}` : ""}${free}`;
}

/** Beside a trait held by exception: the mark, with why on hover, or on a tap. */
export function ExceptionMark({ exception }: { exception: ExceptionOut }) {
  const dates = useDates();
  const [open, setOpen] = useState(false);
  const text = exceptionText(exception, dates.date);
  return (
    <>
      <button
        type="button"
        aria-expanded={open}
        title={`${text}. ${exception.reason}`}
        className="ml-2 rounded border border-gold/50 px-1 text-xs text-gold"
        onClick={() => setOpen(!open)}
      >
        {exception.status === "waiting" ? "exception asked" : "by exception"}
      </button>
      {open && (
        <span className="block text-xs text-mist">
          {text}. {exception.reason}
        </span>
      )}
    </>
  );
}

const named = (e: ExceptionOut) => `${e.name}${e.detail ? `: ${e.detail}` : ""}${e.rating ? ` ${e.rating}` : ""}`;

/** Every trait the character holds by exception, with who approved or gave it, and why. */
export function ExceptionsCard({ exceptions }: { exceptions: ExceptionOut[] }) {
  const dates = useDates();
  if (!exceptions.length) return null;
  return (
    <Card dense title="Exceptions">
      <ul aria-label="Traits held by exception" className="flex flex-col gap-2 text-sm">
        {exceptions.map((e) => (
          <li key={`${e.trait_id}/${e.rating}`}>
            <span className="text-parchment">{named(e)}</span>
            <span className="block text-xs text-gold">{exceptionText(e, dates.date)}</span>
            <span className="block text-xs text-mist">Why: {e.reason}</span>
            {e.breaks.length > 0 && <span className="block text-xs text-mist">Against the rules: {e.breaks.join(" ")}</span>}
          </li>
        ))}
      </ul>
    </Card>
  );
}
