import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "../../api/client";
import { Input, Select } from "../../components/ui";
import { willpowerText } from "../troupe/teacherRules";
import { NPC_TEACHER, teacherValue, type TeacherChoice } from "./teachers";

/** The trait being bought, from `current` to `rating`. */
export type Bought = { category: string; name: string; detail: string; rating: number; current: number };

/** Who teaches a trait, where the troupe's teacher rules ask for one (horatio.teaching). */
export function useTeacherOptions(characterId: string, bought: Bought | null) {
  return useQuery({
    queryKey: ["teachers", characterId, bought],
    queryFn: () =>
      unwrap(
        api.GET("/api/characters/{character_id}/teachers", {
          params: { path: { character_id: characterId }, query: { ...bought! } },
        }),
      ),
    enabled: bought !== null,
  });
}

/**
 * Choosing the teacher for a trait a troupe's teacher rule is about: one of the
 * troupe's characters who hold it at the rating the rule asks, or an NPC named in
 * words, whom staff approve. Shows nothing when the trait needs no teacher.
 */
export function TeacherPicker({
  characterId,
  bought,
  label,
  value,
  onChange,
}: {
  characterId: string;
  bought: Bought;
  /** The trait, for the controls' names: "Lore 3". */
  label: string;
  value: TeacherChoice;
  onChange: (choice: TeacherChoice) => void;
}) {
  const options = useTeacherOptions(characterId, bought);
  const need = options.data;
  if (!need) return null;
  const picked = teacherValue(value);
  return (
    <div className="flex flex-col gap-1.5 rounded border border-gold/40 bg-gold/5 p-2 text-xs">
      <span className="text-gold">Needs a teacher who holds it at {need.rating} or more.</span>
      <Select
        aria-label={`Teacher for ${label}`}
        value={picked}
        onChange={(e) => {
          const id = e.target.value;
          if (id === NPC_TEACHER) onChange({ teacher: value.teacher_id ? "" : value.teacher, teacher_id: null, npc: true });
          else if (!id) onChange({ teacher: "", teacher_id: null, npc: false });
          else onChange({ teacher: need.candidates.find((c) => c.id === id)?.name ?? "", teacher_id: id, npc: false });
        }}
        className="min-h-8 py-1 text-xs"
      >
        <option value="">Choose a teacher…</option>
        {need.candidates.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
            {c.kind === "npc" ? " (NPC)" : ""}
          </option>
        ))}
        <option value={NPC_TEACHER}>An NPC: name them</option>
      </Select>
      {need.candidates.length === 0 && <span className="text-mist">No one in the troupe holds it at {need.rating} yet.</span>}
      {picked === NPC_TEACHER && (
        <Input
          aria-label={`NPC teaching ${label}`}
          value={value.teacher}
          maxLength={200}
          placeholder="Who teaches it"
          onChange={(e) => onChange({ teacher: e.target.value, teacher_id: null, npc: true })}
          className="min-h-8 py-1 text-xs"
        />
      )}
      {picked === NPC_TEACHER && <span className="text-mist">The storytellers approve an NPC teacher.</span>}
      {need.willpower > 0 && picked !== NPC_TEACHER && (
        <span className="text-mist">Their player confirms spending {willpowerText(need.willpower, need.games)}.</span>
      )}
    </div>
  );
}
