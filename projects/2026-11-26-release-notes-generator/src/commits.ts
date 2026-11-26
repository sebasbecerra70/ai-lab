// Parse `git log` output into conventional commits, dedupe, and infer the semver bump.

export interface Commit {
  hash: string;
  type: string; // feat | fix | perf | chore | ...  ("other" when not conventional)
  scope?: string;
  subject: string;
  breaking: boolean;
  breakingNote?: string;
  refs: string[]; // "#412"
  body: string;
}

const HEADER = /^(\w+)(?:\(([\w-]+)\))?(!)?: (.+)$/;

export function parseLog(log: string): Commit[] {
  return log
    .split(/^commit /m)
    .map((b) => b.trim())
    .filter(Boolean)
    .map((block) => {
      const [hashLine, ...rest] = block.split("\n");
      const lines = rest.map((l) => l.trim());
      const header = lines.find((l) => l) ?? "";
      const body = lines.slice(lines.indexOf(header) + 1).join("\n").trim();
      const m = header.match(HEADER);
      const refs = [...new Set([...`${header}\n${body}`.matchAll(/#(\d+)/g)].map((x) => `#${x[1]}`))];
      const note = body.match(/^BREAKING CHANGE: (.+)$/m)?.[1];
      if (!m) return { hash: hashLine.trim(), type: "other", subject: header, breaking: false, refs, body };
      const subject = m[4].replace(/\s*\(#\d+\)\s*$/, "");
      return { hash: hashLine.trim(), type: m[1].toLowerCase(), scope: m[2], subject, breaking: Boolean(m[3] || note), breakingNote: note, refs, body };
    });
}

/** Cherry-picks and re-merges produce the same change twice; keep the first by (type, scope, subject). */
export function dedupe(commits: Commit[]): { kept: Commit[]; dropped: Commit[] } {
  const seen = new Set<string>();
  const kept: Commit[] = [];
  const dropped: Commit[] = [];
  for (const c of commits) {
    const key = `${c.type}|${c.scope ?? ""}|${c.subject.toLowerCase()}`;
    (seen.has(key) ? dropped : kept).push(c);
    seen.add(key);
  }
  return { kept, dropped };
}

export type Bump = "major" | "minor" | "patch" | "none";

export function semverBump(commits: Commit[]): Bump {
  if (commits.some((c) => c.breaking)) return "major";
  if (commits.some((c) => c.type === "feat")) return "minor";
  if (commits.some((c) => c.type === "fix" || c.type === "perf")) return "patch";
  return "none";
}

export function nextVersion(current: string, bump: Bump): string {
  const [maj, min, pat] = current.split(".").map(Number);
  if (bump === "major") return `${maj + 1}.0.0`;
  if (bump === "minor") return `${maj}.${min + 1}.0`;
  if (bump === "patch") return `${maj}.${min}.${pat + 1}`;
  return current;
}
