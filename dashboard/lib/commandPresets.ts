// Command_Presets (Req 28.13). The JSON is the single source: the backend test
// (backend/tests/test_command_presets.py) loads the same file and checks it with Python re.
import presets from "./commandPresets.json";

export interface CommandPreset {
  id: string;
  label: string;
  pattern: string;
  example: string;
  safeExample: string;
}

export const COMMAND_PRESETS: readonly CommandPreset[] = presets as CommandPreset[];
