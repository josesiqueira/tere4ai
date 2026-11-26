/* The facts of the assess page, read from the facade's served features
   schema (B184, rulings P1, P4, P14, P18). Pure functions only, no imports,
   so the page and a test can both run them. */

/* The page keeps no list of facts and no words of its own about any fact.
   Each fact is shown by its schema name with the schema's description under
   it as text. The facts that carry x-annex-iii-area stand under the heading
   that the schema's x-annex-iii-areas gives their area, opened at the first
   fact of the area in schema order. */
export type SchemaFlag = { name: string; description: string; area: number | null };

export type FlagGroup = { area: number | null; heading: string | null; flags: SchemaFlag[] };

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

/* Reads the served schema's flags in the file's order. Returns null (the
   schema is unavailable) when the flags cannot be read or an area has no
   heading, so a partly read schema is never shown as the whole one. */
export function readFlagGroups(payload: unknown): FlagGroup[] | null {
  const schema = asRecord(asRecord(payload)?.schema);
  const flagsNode = asRecord(asRecord(schema?.properties)?.flags);
  const properties = asRecord(flagsNode?.properties);
  if (!flagsNode || !properties) return null;
  const areaHeadings = asRecord(flagsNode["x-annex-iii-areas"]) ?? {};
  const groups: FlagGroup[] = [];
  for (const [name, definition] of Object.entries(properties)) {
    const def = asRecord(definition) ?? {};
    const description = typeof def.description === "string" ? def.description : "";
    const areaValue = def["x-annex-iii-area"];
    const area = typeof areaValue === "number" ? areaValue : null;
    const flag: SchemaFlag = { name, description, area };
    const last = groups[groups.length - 1];
    if (last && last.area === area) {
      last.flags.push(flag);
      continue;
    }
    let heading: string | null = null;
    if (area !== null) {
      const text = areaHeadings[String(area)];
      if (typeof text !== "string") return null;
      heading = text;
    }
    groups.push({ area, heading, flags: [flag] });
  }
  return groups.length > 0 ? groups : null;
}

/* Every fact name of the read schema, in schema order. */
export function factNamesOf(groups: FlagGroup[]): string[] {
  return groups.flatMap((group) => group.flags.map((flag) => flag.name));
}

/* B184 Task 8, fix round 1 (I2): a permalink or a stored form made before a
   fact left the schema still carries it. Keeps the values whose key is a fact
   of the schema and names, sorted, every other key, which the page neither
   sends nor writes back into the link. */
export function splitFlagsBySchema(
  flags: Record<string, string>,
  schemaFacts: readonly string[]
): { kept: Record<string, string>; dropped: string[] } {
  const known = new Set(schemaFacts);
  const kept: Record<string, string> = {};
  const dropped: string[] = [];
  for (const [key, value] of Object.entries(flags)) {
    if (known.has(key)) kept[key] = value;
    else dropped.push(key);
  }
  dropped.sort();
  return { kept, dropped };
}
