import { useEffect, useId, useMemo, useState } from "react";
import { deviceZone } from "../dates";
import { Input } from "./ui";

/** A zone as people read it: "America/New York". */
export function zoneWords(zone: string): string {
  return zone.replaceAll("_", " ");
}

/** Every IANA zone this browser knows, such as "America/New_York". */
export function allZones(): string[] {
  const zones = typeof Intl.supportedValuesOf === "function" ? Intl.supportedValuesOf("timeZone") : [];
  return [...new Set([...zones, "UTC", deviceZone()])].sort();
}

/**
 * A time zone from the IANA list, as the account's Time zone and a troupe's have it (#102,
 * #1211): type to search the list, and a zone from it is chosen at once. Left empty, it
 * chooses none (`placeholder` says what that means); left half-typed, it stays as it was.
 */
export function ZonePicker({
  saved,
  onChoose,
  label = "Time zone",
  placeholder,
  clearText,
  disabled,
  className = "sm:items-end",
}: {
  /** The zone chosen now, or null for none. */
  saved: string | null;
  onChoose: (zone: string | null) => void;
  label?: string;
  placeholder: string;
  /** The button that chooses none, shown while one is chosen. */
  clearText: string;
  disabled?: boolean;
  /** Its alignment: on the right from `sm` up, as on a setting's row, by default. */
  className?: string;
}) {
  const zones = useMemo(allZones, []);
  const list = useId();
  const [text, setText] = useState(saved ?? "");
  useEffect(() => setText(saved ?? ""), [saved]);
  const choose = (zone: string | null) => {
    if (zone !== saved) onChoose(zone);
  };
  return (
    <span className={`flex flex-col items-start gap-1 ${className}`}>
      <Input
        type="search"
        aria-label={label}
        list={list}
        placeholder={placeholder}
        value={text}
        disabled={disabled}
        onChange={(e) => {
          setText(e.target.value);
          if (zones.includes(e.target.value)) choose(e.target.value);
        }}
        onBlur={() => (text.trim() ? setText(saved ?? "") : choose(null))}
        className="w-64 max-w-full text-sm"
      />
      <datalist id={list}>
        {zones.map((z) => (
          <option key={z} value={z} />
        ))}
      </datalist>
      {saved && (
        <button type="button" className="text-xs text-mist underline hover:text-parchment" disabled={disabled} onClick={() => choose(null)}>
          {clearText}
        </button>
      )}
    </span>
  );
}
