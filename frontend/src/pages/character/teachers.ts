/**
 * The teacher a player chooses for a trait a troupe's teacher rule is about
 * (horatio.teaching): a character of the troupe, by id, or an NPC named in words.
 */

/** The picker's value for "an NPC, named in words". */
export const NPC_TEACHER = "npc";

export type TeacherChoice = { teacher: string; teacher_id: string | null; npc: boolean };

export const NO_TEACHER: TeacherChoice = { teacher: "", teacher_id: null, npc: false };

/** The picker's value for a choice. */
export function teacherValue(choice: TeacherChoice): string {
  return choice.teacher_id ?? (choice.npc ? NPC_TEACHER : "");
}

/** Whether a teacher has been chosen: a character, or an NPC with a name. */
export function hasTeacher(choice: TeacherChoice): boolean {
  return !!choice.teacher_id || (choice.npc && !!choice.teacher.trim());
}

/** What the API is sent for the choice. */
export function teacherFields(choice: TeacherChoice): { teacher: string; teacher_id?: string } {
  if (choice.teacher_id) return { teacher: "", teacher_id: choice.teacher_id };
  return { teacher: choice.npc ? choice.teacher.trim() : "" };
}
