import assert from "node:assert/strict";
import { test } from "node:test";
import { DUE_PATTERN, parseISO, pretty, resolveDue } from "./dates.ts";

const MON = parseISO("2026-03-02");
const WED = parseISO("2026-03-04");

test("weekday phrases resolve to this week's day, 'next' to the following week's", () => {
  assert.equal(resolveDue("Thursday", MON), "2026-03-05");
  assert.equal(resolveDue("Monday", MON), "2026-03-09"); // said on a Monday: a week out, not today
  assert.equal(resolveDue("next Wednesday", WED), "2026-03-11");
  assert.equal(resolveDue("next Monday", MON), "2026-03-09");
  assert.equal(resolveDue("Friday", WED), "2026-03-06");
});

test("relative and calendar phrases", () => {
  assert.equal(resolveDue("EOW", MON), "2026-03-06");
  assert.equal(resolveDue("end of month", MON), "2026-03-31");
  assert.equal(resolveDue("tomorrow", MON), "2026-03-03");
  assert.equal(resolveDue("next week's meeting", MON), "2026-03-09");
  assert.equal(resolveDue("3/9", MON), "2026-03-09");
  assert.equal(resolveDue("March 20", WED), "2026-03-20");
  assert.equal(resolveDue("Feb 10", WED), "2027-02-10"); // no year and already past: next year
  assert.equal(resolveDue("2/30", MON), null);
});

test("due pattern ignores event dates and bad ISO strings are rejected", () => {
  assert.equal(DUE_PATTERN.exec("schedule the next QBR for early June"), null);
  assert.equal(DUE_PATTERN.exec("send it to legal by March 20")?.[1], "March 20");
  assert.throws(() => parseISO("2026-02-30"), /invalid/);
  assert.equal(pretty("2026-03-06"), "Fri 06 Mar");
});
