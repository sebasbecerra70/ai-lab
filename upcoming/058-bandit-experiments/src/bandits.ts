// Four ways to split traffic between variants. All see only Bernoulli rewards (converted or not).
import { Rng } from "./rng.ts";

export interface Policy {
  readonly name: string;
  select(): number;
  update(arm: number, reward: number): void;
}

abstract class Counting {
  readonly pulls: number[];
  readonly wins: number[];
  constructor(readonly arms: number) {
    this.pulls = new Array(arms).fill(0);
    this.wins = new Array(arms).fill(0);
  }
  update(arm: number, reward: number): void {
    this.pulls[arm] += 1;
    this.wins[arm] += reward;
  }
  mean(arm: number): number {
    return this.pulls[arm] ? this.wins[arm] / this.pulls[arm] : 0;
  }
  protected argmax(score: (arm: number) => number): number {
    let best = 0;
    let bestScore = -Infinity;
    for (let a = 0; a < this.arms; a++) {
      const s = score(a);
      if (s > bestScore) {
        best = a;
        bestScore = s;
      }
    }
    return best;
  }
}

/** The classic A/B test: equal split for a fixed sample, then ship the observed winner to everyone. */
export class ExploreThenCommit extends Counting implements Policy {
  readonly name: string;
  private t = 0;
  constructor(arms: number, readonly perArm: number) {
    super(arms);
    this.name = `A/B test (${perArm}/arm)`;
  }
  select(): number {
    const arm = this.t < this.perArm * this.arms ? this.t % this.arms : this.argmax((a) => this.mean(a));
    this.t += 1;
    return arm;
  }
}

/** Explore a random arm with probability epsilon, otherwise exploit the best observed mean. */
export class EpsilonGreedy extends Counting implements Policy {
  readonly name: string;
  constructor(arms: number, readonly epsilon: number, private rng: Rng) {
    super(arms);
    this.name = `epsilon-greedy (${epsilon})`;
  }
  select(): number {
    const untried = this.pulls.indexOf(0);
    if (untried >= 0) return untried;
    if (this.rng.next() < this.epsilon) return this.rng.int(this.arms);
    return this.argmax((a) => this.mean(a));
  }
}

/** UCB1: optimism in the face of uncertainty. Mean plus a bonus that shrinks as an arm is sampled. */
export class UCB1 extends Counting implements Policy {
  readonly name = "UCB1";
  private t = 0;
  select(): number {
    this.t += 1;
    const untried = this.pulls.indexOf(0);
    if (untried >= 0) return untried;
    return this.argmax((a) => this.index(a));
  }
  index(arm: number): number {
    return this.mean(arm) + Math.sqrt((2 * Math.log(this.t)) / this.pulls[arm]);
  }
}

/** Thompson sampling with a Beta(1,1) prior: draw a plausible rate per arm, play the highest draw.
 *  Traffic share tracks the posterior probability that each arm is best. */
export class Thompson extends Counting implements Policy {
  readonly name = "Thompson sampling";
  constructor(arms: number, private rng: Rng) {
    super(arms);
  }
  select(): number {
    return this.argmax((a) => this.rng.beta(1 + this.wins[a], 1 + this.pulls[a] - this.wins[a]));
  }
  /** Monte Carlo estimate of P(arm is best) under the current posterior: what you'd report to stakeholders. */
  probBest(draws = 2000): number[] {
    const counts = new Array(this.arms).fill(0);
    for (let i = 0; i < draws; i++) {
      counts[this.argmax((a) => this.rng.beta(1 + this.wins[a], 1 + this.pulls[a] - this.wins[a]))] += 1;
    }
    return counts.map((c) => c / draws);
  }
}
