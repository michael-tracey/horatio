import type { LeavingWarningsOut } from "../../api/types";

/** "Agnes", "Agnes and Cora", "Agnes, Cora and Elise". */
const andList = (names: string[]) => new Intl.ListFormat("en-GB", { type: "conjunction" }).format(names);

const capital = (text: string) => text.charAt(0).toUpperCase() + text.slice(1);

/**
 * What retiring a character, or changing why it left, would tell other players
 * before they should know (#748), as the person may know of it: a regnant's thralls,
 * whose bonds fade unfelt at its Final Death (MET: VTM p. 296), learn it died from its
 * Who's Who listing or remembrances; the other sharers of a shared background learn it
 * left when its dots are withdrawn. A warning only: the choice stays theirs.
 */
export function leavingWarnings(
  found: LeavingWarningsOut,
  { name, reason, listed, remembering }: { name: string; reason: string | null; listed: boolean; remembering: boolean },
): string[] {
  const said: string[] = [];
  if (reason === "final_death" && found.thralls.length > 0 && (listed || remembering)) {
    const thralls = found.thralls.map((t) => t.name);
    const one = thralls.length === 1;
    const telling = [listed && `listing ${name} under “No longer with us”`, remembering && "opening remembrances"].filter((t): t is string => !!t);
    said.push(
      `${name} is the regnant of ${andList(thralls)}. At Final Death ${one ? "the bond fades" : "those bonds fade"} over a month, and ${one ? "the thrall feels it" : "the thralls feel them"} all the while (MET: VTM p. 296). ` +
        `${capital(andList(telling))} tells ${one ? "the thrall's player" : "their players"} that ${name} died now. Leave ${telling.length > 1 ? "them" : "it"} until the ${one ? "bond has" : "bonds have"} faded if they shouldn't know yet.`,
    );
  }
  if (reason !== null) {
    for (const shared of found.shared) {
      const others = andList(shared.others);
      said.push(
        found.staff
          ? `${name} has dots in ${shared.name} with ${others}. Logging their withdrawal shows those sharers' players that ${name} left: hold off if they shouldn't know yet.`
          : `${name} has dots in ${shared.name} with ${others}. When the storytellers log their withdrawal, those sharers' players see that ${name} left.`,
      );
    }
  }
  return said;
}
