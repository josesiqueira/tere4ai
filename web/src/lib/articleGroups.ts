/* The Article or Annex a norm id belongs to, and the Act's order of those
   groups (B132): a letter-suffixed Article the Digital Omnibus inserted
   (article-4a) is its own group, between article-4 and article-5, as
   labels.sort_key orders it in src/tere4ai/parse_legal_structure/labels.py
   (number times 100 plus the letter's place: 4 -> 400, 4a -> 401). */

const GROUP = /eu-ai-act:(article-[1-9][0-9]*[a-z]?|annex-[ivxlc]+)(?=:|$)/;

export function articleGroupOf(normId: string): string | null {
  const match = normId.match(GROUP);
  return match ? `eu-ai-act:${match[1]}` : null;
}

export function articleGroupSortKey(group: string): number {
  const match = group.match(/article-([1-9][0-9]*)([a-z]?)$/);
  if (!match) return Number.MAX_SAFE_INTEGER;
  const letter = match[2] ? match[2].charCodeAt(0) - "a".charCodeAt(0) + 1 : 0;
  return Number(match[1]) * 100 + letter;
}

export function compareArticleGroups(a: string, b: string): number {
  return articleGroupSortKey(a) - articleGroupSortKey(b) || a.localeCompare(b);
}
