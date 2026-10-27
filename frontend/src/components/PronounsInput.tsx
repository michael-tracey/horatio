import { useId, type InputHTMLAttributes } from "react";
import { Input } from "./ui";

/** The usual pronouns, offered as someone types; any other text is fine too. */
const PRONOUNS = ["he/him", "she/her", "they/them", "she/they", "he/they", "any/all", "ask me"];

/** Pronouns as free text, with the usual ones suggested (issue #265). */
export function PronounsInput(props: InputHTMLAttributes<HTMLInputElement>) {
  const list = useId();
  return (
    <>
      <Input maxLength={40} autoComplete="off" placeholder="she/her" list={list} {...props} />
      <datalist id={list}>
        {PRONOUNS.map((p) => (
          <option key={p} value={p} />
        ))}
      </datalist>
    </>
  );
}

/** " (she/her)" after a name, or nothing for none. */
export function Pronouns({ pronouns, className = "text-xs text-mist" }: { pronouns: string | null | undefined; className?: string }) {
  if (!pronouns) return null;
  return <span className={className}> ({pronouns})</span>;
}
