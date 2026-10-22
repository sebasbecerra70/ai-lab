// Completeness checker: lints a Markdown PRD for missing sections, unmeasurable goals and vague requirements.

export interface Gap {
  severity: "blocker" | "major" | "minor";
  section: string;
  message: string;
}

export interface CheckResult {
  score: number; // 0-100
  gaps: Gap[];
}

export const REQUIRED_SECTIONS = [
  "Problem",
  "Users",
  "Goals and success metrics",
  "Non-goals",
  "Requirements",
  "Acceptance criteria",
  "Risks and open questions",
  "Launch plan",
];

const PENALTY = { blocker: 20, major: 10, minor: 4 } as const;
const VAGUE = /\b(fast|faster|quick(ly)?|easy|easier|intuitive|seamless(ly)?|user-friendly|robust|scalable|better|improved?)\b/i;
const PLACEHOLDER = /\b(TBD|TODO|TBC|lorem ipsum)\b|\?\?\?/i;

export function parseSections(md: string): Map<string, string> {
  const out = new Map<string, string>();
  let current: string | null = null;
  for (const line of md.split("\n")) {
    const h = line.match(/^##\s+(.+?)\s*$/);
    if (h) {
      current = h[1];
      out.set(current, "");
    } else if (current) out.set(current, `${out.get(current)}${line}\n`);
  }
  for (const [k, v] of out) out.set(k, v.trim());
  return out;
}

const bullets = (body: string) => body.split("\n").filter((l) => /^\s*[-*]\s+/.test(l)).map((l) => l.replace(/^\s*[-*]\s+(\[[ x]\]\s*)?/, "").trim());

export function checkPrd(md: string): CheckResult {
  const sections = parseSections(md);
  const gaps: Gap[] = [];
  const add = (severity: Gap["severity"], section: string, message: string) => gaps.push({ severity, section, message });

  if (!/^#\s+\S/m.test(md)) add("minor", "Title", "missing a '# ' title line");
  for (const s of REQUIRED_SECTIONS) {
    if (!sections.has(s)) add("blocker", s, "section is missing");
    else if (!sections.get(s)) add("blocker", s, "section is empty");
  }
  for (const [name, body] of sections) {
    if (PLACEHOLDER.test(body)) add("major", name, `contains a placeholder (${body.match(PLACEHOLDER)![0]})`);
  }

  const problem = sections.get("Problem") ?? "";
  if (problem && problem.split(/\s+/).length < 25) add("major", "Problem", "under 25 words; who has the problem and what it costs is unclear");
  if (problem && !/\d/.test(problem)) add("major", "Problem", "no evidence: add a number (tickets, churn, hours, revenue)");

  const goals = bullets(sections.get("Goals and success metrics") ?? "");
  for (const g of goals.filter((g) => !/\d/.test(g))) add("major", "Goals and success metrics", `not measurable: "${g}"`);

  const reqs = bullets(sections.get("Requirements") ?? "");
  const p0 = reqs.filter((r) => /^P0\b/.test(r));
  if (reqs.length && !p0.length) add("major", "Requirements", "no P0 requirement; launch scope is undefined");
  for (const r of reqs.filter((r) => !/^P[0-2]\b/.test(r))) add("minor", "Requirements", `unprioritised: "${r}"`);
  for (const r of reqs) {
    const text = r.replace(/^P[0-2]:?\s*/, ""); // the "0" in "P0" is not a number for this purpose
    const m = text.match(VAGUE);
    if (m && !/\d/.test(text)) add("minor", "Requirements", `vague word "${m[0]}" without a number: "${r}"`);
  }

  const criteria = bullets(sections.get("Acceptance criteria") ?? "").filter((c) => /\bgiven\b.*\bwhen\b.*\bthen\b/i.test(c));
  if (sections.get("Acceptance criteria") && criteria.length < p0.length) {
    add("major", "Acceptance criteria", `${criteria.length} Given/When/Then criteria for ${p0.length} P0 requirements`);
  }

  const score = Math.max(0, 100 - gaps.reduce((s, g) => s + PENALTY[g.severity], 0));
  return { score, gaps };
}
