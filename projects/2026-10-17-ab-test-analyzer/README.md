# A/B Test Analyzer

Turns raw experiment counts into a decision a PM can defend: **ship, don't ship, keep running, or investigate**. It checks sample-ratio mismatch first, then significance, confidence intervals, power and guardrail metrics. All the statistics are written from scratch.

```text
$ python -m ab_test
checkout-express-pay: SHIP
  control 32.00% (n=48,210)  treatment 34.00% (n=48,377)  lift +6.2%  diff 95% CI [+1.40, +2.59] pp
  - significant lift +6.2% (p=0.0000)
  - CI lower bound +1.40pp is below the +1.60pp MDE: real, but maybe smaller than planned
  - guardrail refund_rate ok (+2.5%, p=0.72)

onboarding-checklist: KEEP RUNNING
  - not significant (p=0.30) and only 38% power for a 8% lift

pricing-annual-default: INVESTIGATE SRM
  control 3.00% (n=20,412)  treatment 3.43% (n=19,107)  lift +14.3%  diff 95% CI [+0.08, +0.78] pp
  - sample ratio mismatch: treatment got 19,107 visitors vs 19,760 expected (p=5.2e-11)
  - assignment or logging is broken; the lift below cannot be trusted

search-autocomplete-v2: DON'T SHIP
  - well powered (99%) and no significant effect; CI upper bound +0.38pp rules out the +0.66pp MDE

free-shipping-banner: DON'T SHIP
  - significant lift +16.8% (p=0.0053)
  - guardrail return_rate worsened +66.4% (p=0.0019), over the 15% limit

$ python -m ab_test plan 0.032 0.10
baseline 3.20%, MDE +10% relative, alpha 0.05 two-sided
  power 80%: 49,777 per arm -> 5 days at 20,000 visitors/day
  power 90%: 66,636 per arm -> 7 days at 20,000 visitors/day
```

## Why it matters
Most bad experiment calls aren't math errors. They're process errors:
- **"+14% conversion, ship it!"** The pricing test above shows a +14% lift, but treatment got 650 fewer visitors than a 50/50 split allows (p = 5e-11). That pattern usually means a redirect or bot filter dropped users from one arm, and it would have shipped a broken measurement as a win.
- **"Not significant, so it doesn't work."** The onboarding test only has 38% power. It can't tell "no effect" from "too early", so the right call is to keep running, not to kill a feature that may be +5%.
- **"Conversion is up, done."** The free-shipping banner lifts orders 17% but raises returns 66%. Return shipping on a $60 average order can erase that gain, so the guardrail blocks it.

A planning step (`plan`) puts a number on test duration up front. "We need 50k users per arm, about 5 days" is a better roadmap input than "let's run it for a while".

## Architecture
```
data/experiments.json ──► analyze(exp)
                             │ 1. SRM chi-square on visitor split (alpha 0.001) ──fail──► INVESTIGATE SRM
                             │ 2. two-proportion z-test (pooled SE) + Wald CI (unpooled SE)
                             │ 3. achieved power at the pre-registered MDE
                             │ 4. decision table:
                             │      sig & up ──► SHIP (flag if CI low < MDE) ──► guardrail z-test
                             │      sig & down ──► DON'T SHIP
                             │      not sig & power < 80% ──► KEEP RUNNING
                             │      not sig & power ≥ 80% ──► DON'T SHIP
                             ▼
                          Verdict(decision, reasons, test, power)
stats.py: norm_cdf (erf), norm_ppf (Acklam), chi2_sf (incomplete gamma series), sample size, power
```
- **SRM gate first.** If the split is broken, nothing downstream can be trusted, so the verdict short-circuits. The gate uses alpha = 0.001 because it runs on every experiment and false alarms erode trust in the tool.
- **Pooled SE for the test, unpooled for the CI.** That's the standard choice: the test assumes H0 (equal rates), and the interval shouldn't.
- **The MDE is an input.** Each experiment declares the smallest lift worth shipping before launch. Power and "CI below MDE" warnings are measured against it, which makes it harder to move the goalposts afterwards.
- **No dependencies.** The normal quantile and chi-square tail are about 40 lines and are tested against textbook values (z = 1.96 at 0.975, chi-square 3.84 at p = 0.05, the 3,841-per-arm sample size from standard calculators).
- **Trade-off:** fixed-horizon frequentist tests assume you look once. Teams that check daily need sequential tests (mSPRT or alpha spending). That's listed below, not hidden.

## Run
```bash
python -m pytest -q                  # 14 tests
python -m ab_test                    # analyze the sample portfolio
python -m ab_test plan 0.04 0.05     # sample size for 4% baseline, +5% relative MDE
```

## Next steps
- Add CUPED variance reduction with pre-period data, which typically cuts required sample size by 20–40%.
- Add sequential testing (always-valid p-values) so daily peeking is safe.
- Support continuous metrics (revenue per visitor) with Welch's t-test and a bootstrap CI.
- Apply a Benjamini-Hochberg correction when an experiment reports many secondary metrics.
