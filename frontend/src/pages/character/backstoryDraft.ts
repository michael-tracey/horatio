import type { BackstoryDraftOut, BackstoryOut } from "../../api/types";

/**
 * The backstory as its writer has it in the editor (issue #426). Edits are numbered
 * as they are made, as in the downtime form (downtimeForm.ts), so what the player
 * typed since the server last took it is never replaced by what a refetch brings.
 */
export type Writing = {
  text: string;
  /** The version the draft was started from: submitting names it. */
  basedOn: number;
  /** The number of the latest edit, and of the latest the server has taken. */
  edit: number;
  saved: number;
  /** The latest version, and when the draft was last saved, as the server last said. */
  version: number;
  savedAt: string | null;
  /** Goes up when the text is replaced from outside the editor, which then starts afresh. */
  loads: number;
  /** Save at once rather than once typing stops: the player chose to keep their draft. */
  urgent: boolean;
};

export type WritingChange =
  | { type: "loaded"; backstory: BackstoryOut }
  | { type: "reset"; backstory: BackstoryOut }
  | { type: "edit"; text: string }
  | { type: "keep mine"; version: number }
  | { type: "saved"; edit: number; version: number; draft: BackstoryDraftOut | null };

/** Whether there are edits the server doesn't have yet. */
export const unsaved = (w: Writing) => w.edit > w.saved;

/** A newer version was submitted since the draft was started. */
export const behind = (w: Writing) => w.basedOn < w.version;

const time = (at: string | null | undefined) => (at ? Date.parse(at) : 0);

/** The writing as the server has it: the draft if there is one, else the latest version. */
export function opened(b: BackstoryOut, loads = 0): Writing {
  return {
    text: b.draft?.text ?? b.text,
    basedOn: b.draft?.based_on ?? b.version,
    edit: 0,
    saved: 0,
    version: b.version,
    savedAt: b.draft?.saved_at ?? null,
    loads,
    urgent: false,
  };
}

export function writingReducer(w: Writing, change: WritingChange): Writing {
  switch (change.type) {
    case "loaded": {
      // Something newer than this editor last heard of: a version submitted, or the
      // draft saved elsewhere. Taken only while nothing here is unsaved.
      const b = change.backstory;
      const newer = b.version > w.version || time(b.draft?.saved_at) > time(w.savedAt);
      if (!newer) return w;
      if (unsaved(w)) return { ...w, version: Math.max(w.version, b.version) };
      return { ...opened(b, w.loads + 1), edit: w.edit, saved: w.saved };
    }
    case "reset":
      return { ...opened(change.backstory, w.loads + 1), edit: w.edit, saved: w.edit };
    case "edit":
      return change.text === w.text ? w : { ...w, text: change.text, edit: w.edit + 1, urgent: false };
    case "keep mine":
      return { ...w, basedOn: change.version, version: Math.max(w.version, change.version), edit: w.edit + 1, urgent: true };
    case "saved":
      return {
        ...w,
        saved: Math.max(w.saved, change.edit),
        version: Math.max(w.version, change.version),
        savedAt: change.draft?.saved_at ?? w.savedAt,
        urgent: false,
      };
  }
}
