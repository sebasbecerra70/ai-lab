# Bandit Experiments

Epsilon-greedy, UCB1 and Thompson sampling go head to head with a classic A/B test on simulated conversion experiments. The comparison measures **regret**: the conversions you give up while you are still learning which variant wins.

```text
$ npm run demo
== pricing-page CTA: 4 arms, 20,000 visitors, best start-free at 4.6% (four button/copy variants, one clear winner)
   a powered A/B test for a 10% lift needs 39,475/arm - more traffic than the experiment has, so it runs underpowered on half
   policy                   lost conv    p90  to best  picks best   regret at 5k / 10k / 15k / 20k
   A/B test (2500/arm)             80     97      57%         92%   36 / 73 / 77 / 80
   epsilon-greedy (0.1)            66    129      55%         74%   24 / 41 / 54 / 66
   UCB1                           127    135      31%         64%   34 / 66 / 97 / 127
   Thompson sampling               55     89      66%         96%   23 / 37 / 47 / 55

== onboarding checklist: 2 arms, 20,000 visitors, best progress-bar at 12.3% (two variants within 0.3 points: hard to tell apart)
   a powered A/B test for a 10% lift needs 12,004/arm - more traffic than the experiment has, so it runs underpowered on half
   policy                   lost conv    p90  to best  picks best   regret at 5k / 10k / 15k / 20k
   A/B test (5000/arm)             22     45      64%         79%   8 / 15 / 19 / 22
   epsilon-greedy (0.1)            27     57      55%         61%   8 / 14 / 21 / 27
   UCB1                            28     32      53%         61%   7 / 14 / 21 / 28
   Thompson sampling               23     46      62%         72%   6 / 12 / 18 / 23

== upgrade nudge: 6 arms, 20,000 visitors, best discount-20 at 2.9% (six variants, most of them bad)
   a powered A/B test for a 10% lift needs 80,682/arm - more traffic than the experiment has, so it runs underpowered on half
   policy                   lost conv    p90  to best  picks best   regret at 5k / 10k / 15k / 20k
   A/B test (1666/arm)            100    122      45%         76%   46 / 92 / 96 / 100
   epsilon-greedy (0.1)            65    121      50%         69%   27 / 43 / 55 / 65
   UCB1                           164    168      21%         65%   43 / 85 / 125 / 164
   Thompson sampling               58     85      57%         86%   27 / 41 / 51 / 58

pricing-page CTA, one Thompson run: traffic share and posterior P(best) per arm
   visitors          control     start-free      see-plans  talk-to-sales
   2,000           32% / 39%        9% / 7%      40% / 42%      19% / 11%
   5,000           36% / 52%        8% / 4%      46% / 41%       10% / 3%
   10,000          48% / 77%      11% / 17%       34% / 5%        7% / 2%
   20,000          43% / 19%      34% / 78%       18% / 0%        5% / 2%
(200 simulated experiments per policy; lost conv = expected conversions lost vs always showing the best arm)
```

## Why it matters
A pricing page with 20,000 visitors a month cannot run a properly powered four-arm A/B test for a 10% lift: that needs 39,475 visitors *per arm*. So teams run underpowered tests and send three quarters of the traffic to losing variants while they wait. In the CTA scenario, Thompson sampling gives up 55 expected conversions against the oracle, compared with 80 for the A/B test. It also ends on the right variant in 96% of runs, against 92%. At a $600 first-year contract value, those 25 conversions are $15k a month on one page.

The comparison also shows where a bandit is the wrong tool:
- **Close races.** In the onboarding scenario (12.0% vs 12.3%) nothing has the traffic to separate the arms, and the A/B test is as good as anything. If the decision is permanent and you need a clean effect size for the board deck, run the test.
- **UCB1 at low conversion rates.** Its exploration bonus is sized for rewards spread across [0, 1], so at 3–5% rates it keeps exploring almost uniformly and does worse than the A/B test.
- **Stopping early.** In the single Thompson run at the bottom, the posterior gives the wrong arm (control) a 77% chance of being best after 10,000 visitors. Because Thompson never stops exploring, it recovers by 20,000. A PM who stopped at "77% likely" would have shipped the wrong button.

## Architecture
```
data/scenarios.json  arms with true conversion rates, visitors
        │
        ▼
compare(scenario, factories, runs)          same random stream per run for every policy
        │
        ├─ ExploreThenCommit   equal split for n/arm (power analysis, capped at half the traffic), then ship winner
        ├─ EpsilonGreedy(0.1)  explore uniformly 10% of the time
        ├─ UCB1                mean + sqrt(2 ln t / n)
        └─ Thompson            Beta(1+wins, 1+losses) draw per arm, play the max
        │
        ▼
runOnce(): Bernoulli rewards, expected regret at checkpoints, traffic per arm, final allocation
        │
        ▼
summary: mean and p90 lost conversions, share of traffic to the best arm, % of runs that end on the best arm
```
- **The baseline is honest.** The A/B test uses the textbook sample-size formula (a test checks 3,841/arm for 10% → 12%). When the traffic can't support it, it does what teams actually do: split half the traffic and ship the observed winner.
- **Expected regret, not realized regret.** Each step adds `p_best - p_chosen`, which takes out the noise of individual conversions so policies are compared on decisions, not luck. Every policy also sees the same reward stream per run (common random numbers).
- **p90 matters as much as the mean.** Epsilon-greedy has a good mean but a fat tail: some runs lock onto a wrong arm early and pay for it all month. That risk is what a PM should weigh.
- **No dependencies.** It has a seeded PRNG (mulberry32), and the gamma and beta samplers (Marsaglia–Tsang) are written by hand and tested against known means, so every number in this README can be reproduced.
- **Why no LLM?** This is a statistics and decision problem with a known right answer per scenario. Simulation is the right tool. An LLM could write the experiment readout, but it shouldn't pick the winner.

## Run
```bash
npm test            # 11 tests (node:test via tsx)
npm run demo        # 200 simulated experiments per policy per scenario (~10 s)
npx --yes tsx src/cli.ts 50   # quicker
```
Edit `data/scenarios.json` to model your own variants and traffic.

## Next steps
- Add non-stationary scenarios (novelty effects, weekday mix) and a discounted or sliding-window Thompson.
- Add contextual bandits (for example by traffic source) with a per-segment Beta posterior.
- Add guardrail metrics: stop any arm whose refund or churn rate is credibly worse, whatever its conversion rate.
