/* The classifier's levels (B118): stored value to shown name. Mirrors
   LEVEL_NAMES in src/tere4ai/mcp_server/levels.py, which is the source. A
   screen that shows a project's level as a level uses levelName(); a screen
   that prints an envelope field under its field name prints the stored value. */

export const LEVEL_NAMES: Record<string, string> = {
  unacceptable_risk: "Unacceptable risk",
  high_risk: "High risk",
  limited_risk: "Limited risk",
  minimal_risk: "Minimal risk",
  undetermined: "Undetermined: facts missing",
};

export function levelName(value: string | null | undefined): string {
  if (value == null) return "";
  return Object.hasOwn(LEVEL_NAMES, value) ? LEVEL_NAMES[value] : value;
}
