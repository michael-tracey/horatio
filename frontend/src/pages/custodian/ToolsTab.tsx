import { DarkPackResources } from "./tools/DarkPackResources";
import { FitNpcPicks } from "./tools/FitNpcPicks";
import { VtesSymbols } from "./tools/VtesSymbols";

/**
 * Maintenance that would otherwise need a command on the server, one card a tool.
 * Each says what it does and shows what it would change before it changes it, or,
 * for what the server fetches from elsewhere, what it has now.
 */
export function ToolsTab() {
  return (
    <div className="flex flex-col gap-4">
      <FitNpcPicks />
      <DarkPackResources />
      <VtesSymbols />
    </div>
  );
}
