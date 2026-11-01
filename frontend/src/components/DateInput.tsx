import type { InputHTMLAttributes } from "react";
import { useDates } from "../dates";
import { Input } from "./ui";

/**
 * A date input, or with `type="datetime-local"` a date and time, with what it
 * holds written under it the way Horatio writes dates: "Sat 31 Oct 2026",
 * "Sat 31 Oct 2026, 9:30 pm EDT". The browser draws the input itself in its own
 * locale's order (often mm/dd/yyyy and 12:55 PM), which a page can't change.
 * A datetime-local value is read on the person's own clock (`useDates().fromInput`).
 */
export function DateInput({ type = "date", ...props }: Omit<InputHTMLAttributes<HTMLInputElement>, "type"> & { type?: "date" | "datetime-local" }) {
  const dates = useDates();
  const shown = typeof props.value === "string" ? dates.inputText(props.value) : "";
  return (
    <span className="flex flex-col gap-0.5">
      <Input type={type} {...props} />
      {shown && <span className="text-xs text-parchment/80">{shown}</span>}
    </span>
  );
}
