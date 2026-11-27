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

/* B185 Task 10 (D-G92 (10), rulings P16, P30): the choices of the domain
   select, read from the served schema. The page keeps no list of domains.
   The eight areas stand under the heading the schema's x-annex-iii-areas
   gives their point (the number in x-annex-iii-area-values); the value
   none_of_these_areas has no heading in the Act and is shown as the label
   below (P16). Unknown is not a value of the schema: the page offers it as
   the empty choice. */
export type DomainChoice = { value: string; label: string; area: number | null };

const NONE_OF_THESE_AREAS = "none_of_these_areas";
const NONE_OF_THESE_AREAS_LABEL = "none of the eight areas of Annex III";

function domainNode(payload: unknown): Record<string, unknown> | null {
  const schema = asRecord(asRecord(payload)?.schema);
  return asRecord(asRecord(schema?.properties)?.domain);
}

/* The schema's enum in order, null (the schema is unavailable) when the
   domain property, an area's number or an area's heading cannot be read. */
export function readDomainChoices(payload: unknown): DomainChoice[] | null {
  const node = domainNode(payload);
  const schema = asRecord(asRecord(payload)?.schema);
  const flagsNode = asRecord(asRecord(schema?.properties)?.flags);
  const values = node?.enum;
  if (!node || !flagsNode || !Array.isArray(values)) return null;
  const numbers = asRecord(node["x-annex-iii-area-values"]) ?? {};
  const headings = asRecord(flagsNode["x-annex-iii-areas"]) ?? {};
  const choices: DomainChoice[] = [];
  for (const value of values) {
    if (value === null) continue;
    if (typeof value !== "string") return null;
    if (value === NONE_OF_THESE_AREAS) {
      choices.push({ value, label: NONE_OF_THESE_AREAS_LABEL, area: null });
      continue;
    }
    const area = numbers[value];
    if (typeof area !== "number") return null;
    const heading = headings[String(area)];
    if (typeof heading !== "string") return null;
    choices.push({ value, label: heading, area });
  }
  return choices.length > 0 ? choices : null;
}

/* B185, the final fix wave (item 5): how a refusal shows a given domain, the
   rule the classifier follows (removed_facts.domain_value_shown): a string as
   it is, its control characters (U+0000 to U+001F) escaped as JSON text
   escapes them; any other value as its JSON text; then, when the text is
   longer than the schema's x-refusal-value-limit characters (code points,
   not UTF-16 units), its first that many characters and the schema's
   x-refusal-value-cut with {count}, the characters left out. */
export function domainValueShown(value: unknown, node: Record<string, unknown> | null): string {
  let text =
    typeof value === "string"
      ? value.replace(/[\u0000-\u001f]/g, (c) => JSON.stringify(c).slice(1, -1))
      : String(JSON.stringify(value));
  const limit = node?.["x-refusal-value-limit"];
  const cut = node?.["x-refusal-value-cut"];
  if (typeof limit === "number" && typeof cut === "string") {
    const chars = Array.from(text);
    if (chars.length > limit) {
      text = chars.slice(0, limit).join("") + cut.replace("{count}", String(chars.length - limit));
    }
  }
  return text;
}

/* A value of the list is kept. Any other value is not kept and carries the
   schema's refusal: x-refusal with {value} filled in as domainValueShown
   shows it and, for a word of x-removed-values, ": " and its message. An
   empty value is unknown. */
export function domainOfSchema(
  value: unknown,
  payload: unknown
): { value: string | null; refused: string | null } {
  if (value === null || value === undefined || value === "") {
    return { value: null, refused: null };
  }
  const node = domainNode(payload);
  const values = Array.isArray(node?.enum) ? (node.enum as unknown[]) : [];
  if (typeof value === "string" && values.includes(value)) {
    return { value, refused: null };
  }
  const template = typeof node?.["x-refusal"] === "string" ? (node["x-refusal"] as string) : null;
  if (template === null) return { value: null, refused: null };
  // A replacement function, so a "$&" or "$'" in the value is never read as
  // a replacement pattern.
  const shown = domainValueShown(value, node);
  let refused = template.replace("{value}", () => shown);
  const removed = asRecord(node?.["x-removed-values"]);
  const message = typeof value === "string" ? removed?.[value] : undefined;
  if (typeof message === "string") refused = `${refused}: ${message}`;
  return { value: null, refused };
}
