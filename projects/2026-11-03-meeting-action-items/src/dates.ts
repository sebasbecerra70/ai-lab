// Resolve the due-date phrases people actually write in notes ("by Thursday", "EOW", "3/9", "March 20")
// against the meeting date. All dates are UTC calendar days, so time zones never shift a deadline.

const WEEKDAYS = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"];
const MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"];

export const parseISO = (s: string): Date => {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
  if (!m) throw new Error(`not an ISO date: ${s}`);
  const d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]));
  if (d.getUTCMonth() !== +m[2] - 1) throw new Error(`invalid date: ${s}`);
  return d;
};
export const toISO = (d: Date): string => d.toISOString().slice(0, 10);
export const addDays = (d: Date, n: number): Date => new Date(d.getTime() + n * 86_400_000);
export const pretty = (iso: string): string =>
  parseISO(iso).toLocaleDateString("en-GB", { weekday: "short", day: "2-digit", month: "short", timeZone: "UTC" }).replace(",", "");

/** Phrases that introduce a deadline. "for early June" is an event date, not a due date, so "for" is not here. */
export const DUE_PATTERN =
  /\b(?:by|before|due(?: on)?|no later than)\s+((?:next\s+)?(?:mon|tues|wednes|thurs|fri|satur|sun)day|today|tomorrow|end of (?:the )?(?:week|month)|eow|eom|next week(?:'s meeting)?|\d{1,2}\/\d{1,2}(?:\/\d{2,4})?|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2})\b/i;

export function resolveDue(phrase: string, meeting: Date): string | null {
  const p = phrase.toLowerCase().trim();
  const dow = meeting.getUTCDay();
  if (p === "today") return toISO(meeting);
  if (p === "tomorrow") return toISO(addDays(meeting, 1));
  if (p === "eow" || /^end of (the )?week$/.test(p)) return toISO(addDays(meeting, (5 - dow + 7) % 7));
  if (p === "eom" || /^end of (the )?month$/.test(p))
    return toISO(new Date(Date.UTC(meeting.getUTCFullYear(), meeting.getUTCMonth() + 1, 0)));
  if (p.startsWith("next week")) return toISO(addDays(meeting, 7)); // the next weekly occurrence
  const wd = /^(next\s+)?(\w+day)$/.exec(p);
  if (wd) {
    const target = WEEKDAYS.indexOf(wd[2]);
    if (target < 0) return null;
    let delta = (target - dow + 7) % 7 || 7; // "by Monday" said on a Monday means a week out
    if (wd[1]) {
      // "next Wednesday" = the Wednesday of next week (Monday-based weeks)
      const mondayNext = addDays(meeting, ((1 - dow + 7) % 7) || 7);
      delta = Math.round((addDays(mondayNext, (target + 6) % 7).getTime() - meeting.getTime()) / 86_400_000);
    }
    return toISO(addDays(meeting, delta));
  }
  const num = /^(\d{1,2})\/(\d{1,2})(?:\/(\d{2,4}))?$/.exec(p);
  if (num) return rollForward(meeting, +num[1] - 1, +num[2], num[3] ? +num[3] : undefined);
  const named = /^([a-z]{3})[a-z]*\.?\s+(\d{1,2})$/.exec(p);
  if (named && MONTHS.includes(named[1])) return rollForward(meeting, MONTHS.indexOf(named[1]), +named[2]);
  return null;
}

/** A month/day with no year means the next such day on or after the meeting. */
function rollForward(meeting: Date, month: number, day: number, year?: number): string | null {
  let y = year === undefined ? meeting.getUTCFullYear() : year < 100 ? 2000 + year : year;
  let d = new Date(Date.UTC(y, month, day));
  if (d.getUTCMonth() !== month) return null;
  if (year === undefined && d < meeting) d = new Date(Date.UTC(++y, month, day));
  return toISO(d);
}
