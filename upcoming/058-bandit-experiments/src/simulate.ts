// Monte Carlo comparison of traffic-allocation policies on Bernoulli conversion scenarios.
import { EpsilonGreedy, ExploreThenCommit, type Policy, Thompson, UCB1 } from "./bandits.ts";
import { Rng } from "./rng.ts";

export interface Arm {
  id: string;
  rate: number;
}

export interface Scenario {
  name: string;
  note?: string;
  visitors: number;
  arms: Arm[];
}

export interface RunResult {
  regret: number[]; // cumulative expected regret at each checkpoint
  pulls: number[];
  conversions: number;
  finalArm: number; // the arm the policy is sending most traffic to at the end
}

export interface Summary {
  policy: string;
  meanRegret: number;
  p90Regret: number;
  regretCurve: number[];
  bestShare: number; // share of all traffic that went to the best arm
  pickedBest: number; // share of runs whose final allocation favors the best arm
  conversions: number;
}

export type Factory = (arms: number, rng: Rng) => Policy;

const Z = { a05: 1.959964, p80: 0.841621 };

/** Visitors per arm for a two-sided test at alpha 0.05 and 80% power to detect a relative lift `mde`. */
export function sampleSizePerArm(baseline: number, mde: number): number {
  const p1 = baseline;
  const p2 = baseline * (1 + mde);
  const pBar = (p1 + p2) / 2;
  const num = Z.a05 * Math.sqrt(2 * pBar * (1 - pBar)) + Z.p80 * Math.sqrt(p1 * (1 - p1) + p2 * (1 - p2));
  return Math.ceil((num * num) / ((p2 - p1) * (p2 - p1)));
}

export function bestArm(s: Scenario): number {
  return s.arms.reduce((b, a, i) => (a.rate > s.arms[b].rate ? i : b), 0);
}

/** One simulated experiment. Regret is the expected conversions lost against always showing the best arm,
 *  which is less noisy than counting realized conversions. */
export function runOnce(s: Scenario, policy: Policy, rng: Rng, checkpoints: number[]): RunResult {
  const best = s.arms[bestArm(s)].rate;
  const pulls = new Array(s.arms.length).fill(0);
  const tail = new Array(s.arms.length).fill(0);
  const tailStart = Math.floor(s.visitors * 0.9);
  const regret: number[] = [];
  let cum = 0;
  let conversions = 0;
  let next = 0;
  for (let t = 1; t <= s.visitors; t++) {
    const arm = policy.select();
    const reward = rng.next() < s.arms[arm].rate ? 1 : 0;
    policy.update(arm, reward);
    pulls[arm] += 1;
    if (t > tailStart) tail[arm] += 1;
    conversions += reward;
    cum += best - s.arms[arm].rate;
    if (t === checkpoints[next]) {
      regret.push(cum);
      next += 1;
    }
  }
  const finalArm = tail.indexOf(Math.max(...tail));
  return { regret, pulls, conversions, finalArm };
}

function quantile(xs: number[], q: number): number {
  const s = [...xs].sort((a, b) => a - b);
  return s[Math.min(s.length - 1, Math.floor(q * s.length))];
}

export function compare(s: Scenario, factories: Factory[], runs: number, seed = 1, points = 4): Summary[] {
  const checkpoints = Array.from({ length: points }, (_, i) => Math.round((s.visitors * (i + 1)) / points));
  const best = bestArm(s);
  return factories.map((make) => {
    const results: RunResult[] = [];
    let name = "";
    for (let r = 0; r < runs; r++) {
      // the same seed per run for every policy: each policy faces the same stream of luck
      const rng = new Rng(seed * 100_003 + r);
      const policy = make(s.arms.length, new Rng(seed * 7919 + r));
      name = policy.name;
      results.push(runOnce(s, policy, rng, checkpoints));
    }
    const finals = results.map((x) => x.regret[x.regret.length - 1]);
    return {
      policy: name,
      meanRegret: finals.reduce((a, b) => a + b, 0) / runs,
      p90Regret: quantile(finals, 0.9),
      regretCurve: checkpoints.map((_, i) => results.reduce((a, x) => a + x.regret[i], 0) / runs),
      bestShare: results.reduce((a, x) => a + x.pulls[best], 0) / (runs * s.visitors),
      pickedBest: results.filter((x) => x.finalArm === best).length / runs,
      conversions: results.reduce((a, x) => a + x.conversions, 0) / runs,
    };
  });
}

/** The default line-up: an A/B test and three bandits. The A/B test uses the powered sample size when the
 *  traffic allows it; otherwise it does what teams do in practice: split half the traffic, then ship the
 *  observed winner. */
export function defaultFactories(s: Scenario, mde = 0.1): Factory[] {
  const perArm = Math.min(sampleSizePerArm(s.arms[0].rate, mde), Math.floor(s.visitors / 2 / s.arms.length));
  return [
    (k) => new ExploreThenCommit(k, perArm),
    (k, rng) => new EpsilonGreedy(k, 0.1, rng),
    (k) => new UCB1(k),
    (k, rng) => new Thompson(k, rng),
  ];
}
