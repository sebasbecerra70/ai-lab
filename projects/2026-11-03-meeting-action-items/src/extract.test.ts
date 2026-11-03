import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { matchAttendee, parseNotes, regexExtract } from "./extract.ts";

const notes = (f: string) => parseNotes(readFileSync(new URL(`../data/notes/${f}`, import.meta.url), "utf8"));

test("notes header gives title, date and attendees without role tags", () => {
  const m = notes("vendor-qbr.md");
  assert.equal(m.date, "2026-03-04");
  assert.deepEqual(m.attendees, ["Alex Romero", "Dana Kim", "Luis Ortega", "Beth Nguyen"]);
  assert.throws(() => parseNotes("# x\nno date here"), /Date/);
});

test("attendee matching accepts first names and handles, rejects strangers", () => {
  const people = ["Priya Shah", "Sam Lee"];
  assert.equal(matchAttendee("@sam", people), "Sam Lee");
  assert.equal(matchAttendee("priya", people), "Priya Shah");
  assert.equal(matchAttendee("Legal", people), null);
});

test("regex finds every owned action in the ops notes with resolved dates", () => {
  const x = regexExtract(notes("ops-weekly.md"));
  const byOwner = Object.fromEntries(x.actions.map((a) => [a.owner ?? "none", a]));
  assert.equal(byOwner["Priya Shah"].due, "2026-03-05");
  assert.equal(byOwner["Priya Shah"].task, "Confirm the overtime budget with finance");
  assert.equal(byOwner["Jen Okafor"].due, "2026-03-06");
  assert.equal(byOwner["Sam Lee"].due, "2026-03-09");
  assert.equal(byOwner["Marco Diaz"].due, "2026-03-09");
  assert.match(byOwner.none.task, /label printer jams/);
  assert.equal(x.actions.length, 5); // "Marco thinks..." and "Jen said..." are discussion, not actions
});

test("decisions are captured but undecided discussion is not", () => {
  const x = regexExtract(notes("ops-weekly.md"));
  assert.equal(x.decisions.length, 2);
  assert.ok(x.decisions.every((d) => !/WMS/.test(d.text)));
  const q = regexExtract(notes("vendor-qbr.md"));
  assert.deepEqual(q.decisions.map((d) => d.text.slice(0, 10)), ["We will mo", "Price stay"]);
  assert.equal(q.actions.find((a) => a.owner === "Alex Romero")?.due, null);
});
