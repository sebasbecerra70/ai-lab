// Turn a ranked list into quarters: fill each quarter's capacity in RICE order, respecting dependencies.
import type { Scored } from "./rice.ts";

export interface Slot {
  quarter: number; // 1-based
  feature: Scored;
}

export interface Roadmap {
  slots: Slot[];
  unscheduled: { feature: Scored; reason: string }[];
}

export function planRoadmap(ranked: Scored[], capacityPerQuarter: number, quarters: number): Roadmap {
  const left = Array.from({ length: quarters }, () => capacityPerQuarter);
  const placed = new Map<string, number>();
  const slots: Slot[] = [];
  const unscheduled: Roadmap["unscheduled"] = [];
  let pending = [...ranked];
  // Repeat passes so a high-RICE item blocked only by a later-ranked dependency gets placed once it lands.
  for (let pass = 0; pass < ranked.length && pending.length; pass++) {
    const next: Scored[] = [];
    for (const f of pending) {
      const deps = f.dependsOn ?? [];
      if (deps.some((d) => !placed.has(d))) {
        next.push(f);
        continue;
      }
      // A dependent can start in the same quarter as its dependency ends at the earliest.
      const earliest = Math.max(0, ...deps.map((d) => placed.get(d)! - 1));
      const q = left.findIndex((cap, i) => i >= earliest && cap >= f.effort);
      if (q === -1) {
        unscheduled.push({ feature: f, reason: f.effort > capacityPerQuarter ? "larger than one quarter's capacity" : "no capacity left" });
        continue;
      }
      left[q] -= f.effort;
      placed.set(f.id, q + 1);
      slots.push({ quarter: q + 1, feature: f });
    }
    if (next.length === pending.length) {
      for (const f of next) unscheduled.push({ feature: f, reason: `waiting on ${(f.dependsOn ?? []).filter((d) => !placed.has(d)).join(", ")}` });
      pending = [];
    } else {
      pending = next;
    }
  }
  slots.sort((a, b) => a.quarter - b.quarter || a.feature.rank - b.feature.rank);
  return { slots, unscheduled };
}
