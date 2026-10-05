// Demo: npx tsx src/cli.ts [path/to/roadmap.json]
import { readFileSync } from "node:fs";
import { criticalPath } from "./cpm.ts";
import type { Roadmap } from "./graph.ts";
import { gantt, hiringWhatIf, priorityList, schedule, scheduleWithOrder } from "./schedule.ts";

const path = process.argv[2] ?? new URL("../data/roadmap.json", import.meta.url).pathname;
const roadmap = JSON.parse(readFileSync(path, "utf8")) as Roadmap;

const cpm = criticalPath(roadmap.epics);
const greedy = scheduleWithOrder(roadmap, priorityList(roadmap));
const s = schedule(roadmap);
console.log(`${roadmap.epics.length} epics, teams ${Object.entries(roadmap.teams).map(([t, n]) => `${t}=${n}`).join(" ")}\n`);
console.log(`critical path (${cpm.length}w with unlimited people): ${cpm.criticalPath.join(" -> ")}`);
console.log(`greedy priority list:      ${greedy.makespan}w, ${greedy.late.length} epic(s) late`);
console.log(`after local search:        ${s.makespan}w, ${s.late.length} epic(s) late (${s.makespan - cpm.length}w lost to team capacity)\n`);
console.log(gantt(s, roadmap.targetWeek));
console.log(`\nutilization: ${Object.entries(s.utilization).map(([t, u]) => `${t} ${(u * 100).toFixed(0)}%`).join(", ")}`);
if (s.late.length) console.log(`misses target week ${roadmap.targetWeek}: ${s.late.map((l) => `${l.epic.id} (w${l.end})`).join(", ")}`);
console.log("\nwhat if we add one person to...");
for (const w of hiringWhatIf(roadmap)) console.log(`  ${w.team.padEnd(9)} -> ${w.makespan}w (${w.saved > 0 ? `saves ${w.saved}w` : "no change"})`);
