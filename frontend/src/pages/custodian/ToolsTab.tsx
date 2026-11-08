import { FitNpcPicks } from "./tools/FitNpcPicks";

/**
 * Maintenance that would otherwise need a command on the server, one card a tool.
 * Each says what it does and shows what it would change before it changes it.
 */
export function ToolsTab() {
  return (
    <div className="flex flex-col gap-4">
      <FitNpcPicks />
    </div>
  );
}
