import { describe, expect, it } from "vitest";
import type { ProjectOut } from "../../api/types";
import { projectLine, projectStatus } from "./projectText";

const project = (over: Partial<ProjectOut>): ProjectOut => ({
  id: "p",
  character_id: "c",
  character_name: "Agnes",
  name: "Path change: Night",
  kind: "path_change",
  target: 9,
  monthly_minimum: 1,
  progress: 4,
  status: "active",
  path: "Night",
  with_teacher: true,
  restarts: 0,
  finished_at: null,
  sheet_change_due: false,
  this_cycle: null,
  starts_over: false,
  history: [],
  ...over,
});

describe("a project's line", () => {
  it("says how far it has got and its rules", () => {
    expect(projectLine(project({}))).toBe("4 of 9 actions · with a teacher · at least 1 a month");
    expect(projectLine(project({ restarts: 2, with_teacher: false, target: 18 }))).toBe(
      "4 of 18 actions · without a teacher · at least 1 a month · started over 2 times",
    );
    expect(projectLine(project({ kind: "research", monthly_minimum: null, target: 1, progress: 0, restarts: 1 }))).toBe("0 of 1 action · started over once");
    expect(projectStatus("dropped")).toBe("Stopped");
  });
});
