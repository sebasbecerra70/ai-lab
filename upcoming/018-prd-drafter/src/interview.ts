// Structured PM interview: fixed questions, per-answer validation, and follow-ups when an answer is too vague.

export interface Question {
  id: string;
  section: string;
  prompt: string;
  /** Returns a follow-up question if the answer is not good enough yet, or null when it passes. */
  check: (answer: string) => string | null;
  list?: boolean; // answer is a list, one item per line
}

const words = (s: string) => s.trim().split(/\s+/).filter(Boolean).length;
const items = (s: string) => s.split("\n").map((x) => x.replace(/^[-*]\s*/, "").trim()).filter(Boolean);
const hasNumber = (s: string) => /\d/.test(s);

export const QUESTIONS: Question[] = [
  {
    id: "title",
    section: "Overview",
    prompt: "What is the feature called?",
    check: (a) => (words(a) >= 2 ? null : "Give it a descriptive name of at least two words."),
  },
  {
    id: "problem",
    section: "Problem",
    prompt: "What problem does this solve, for whom, and what evidence do you have?",
    check: (a) =>
      words(a) < 25
        ? "Say more: who has the problem, how often, and what it costs them (aim for 25+ words)."
        : hasNumber(a)
          ? null
          : "What evidence backs this up? Add a number: tickets, churn, time lost, deals blocked.",
  },
  {
    id: "users",
    section: "Users",
    prompt: "Who are the target users or personas?",
    list: true,
    check: (a) => (items(a).length >= 1 ? null : "Name at least one persona."),
  },
  {
    id: "goals",
    section: "Goals and success metrics",
    prompt: "How will we know it worked? List metrics with a baseline and a target.",
    list: true,
    check: (a) => {
      const vague = items(a).filter((m) => !hasNumber(m));
      return vague.length ? `These metrics have no number; give a baseline and target: ${vague.join("; ")}` : items(a).length ? null : "Add at least one metric.";
    },
  },
  {
    id: "non_goals",
    section: "Non-goals",
    prompt: "What is explicitly out of scope?",
    list: true,
    check: (a) => (items(a).length >= 1 ? null : "Name at least one non-goal; it prevents scope creep later."),
  },
  {
    id: "requirements",
    section: "Requirements",
    prompt: "What must the feature do? One requirement per line, prefix with P0/P1/P2.",
    list: true,
    check: (a) => {
      const reqs = items(a);
      const untagged = reqs.filter((r) => !/^P[0-2]\b/.test(r));
      if (!reqs.length) return "List at least one requirement.";
      if (untagged.length) return `Tag each requirement with P0, P1 or P2: ${untagged.join("; ")}`;
      return reqs.some((r) => r.startsWith("P0")) ? null : "Which requirement is the P0 (must have for launch)?";
    },
  },
  {
    id: "risks",
    section: "Risks and open questions",
    prompt: "What could go wrong, and what don't we know yet?",
    list: true,
    check: (a) => (items(a).length >= 1 ? null : "Name at least one risk or open question."),
  },
  {
    id: "launch",
    section: "Launch plan",
    prompt: "How will this roll out (beta, flag, % rollout, GA)?",
    check: (a) => (words(a) >= 6 ? null : "Describe the rollout steps: who gets it first and what gates GA."),
  },
];

export type Answers = Record<string, string>;

export interface Turn {
  questionId: string;
  asked: string;
  answer: string;
  followUp: string | null;
}

/** Runs the interview against a scripted responder (a person in a REPL, or canned answers in tests). */
export class Interview {
  readonly transcript: Turn[] = [];
  readonly answers: Answers = {};

  constructor(private maxFollowUps = 2) {}

  async run(respond: (questionId: string, prompt: string, attempt: number) => Promise<string> | string): Promise<Answers> {
    for (const q of QUESTIONS) {
      let prompt = q.prompt;
      for (let attempt = 0; attempt <= this.maxFollowUps; attempt++) {
        const answer = (await respond(q.id, prompt, attempt)).trim();
        const followUp = q.check(answer);
        this.transcript.push({ questionId: q.id, asked: prompt, answer, followUp });
        if (!followUp || attempt === this.maxFollowUps) {
          // Keep the best we got; the completeness checker will still flag what's weak.
          this.answers[q.id] = answer;
          break;
        }
        prompt = followUp;
      }
    }
    return this.answers;
  }
}

export function splitList(answer: string): string[] {
  return items(answer);
}
