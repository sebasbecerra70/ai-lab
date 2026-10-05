"""CLI: python -m kpi_narrator"""
import os
from pathlib import Path

from . import AnthropicLLM, MockLLM, build_facts, bridge, fmt, load_kpis, load_segments, narrate, variance

DATA = Path(__file__).resolve().parent.parent / "data"
MARK = {"green": " ", "amber": "~", "red": "!"}


def main() -> None:
    vs = [variance(k) for k in load_kpis(DATA / "kpis.csv")]
    br = bridge(load_segments(DATA / "revenue_drivers.csv"))
    print(f"{'':2}{'KPI':<22}{'actual':>10}{'plan':>10}{'vs plan':>10}{'%':>7}{'vs prior':>10}  status")
    for v in vs:
        k = v.kpi
        print(f"{MARK[v.status]:2}{k.metric:<22}{fmt(k.actual, k.unit):>10}{fmt(k.plan, k.unit):>10}"
              f"{fmt(v.vs_plan, k.unit, True):>10}{v.vs_plan_pct:>+6.1f}%{fmt(v.vs_prior, k.unit, True):>10}  "
              f"{v.status}{'' if v.favorable else ' (unfavorable)'}")
    print(f"\nRevenue bridge: plan {fmt(br.plan, 'usd')} | volume {fmt(br.volume, 'usd', True)} | "
          f"mix {fmt(br.mix, 'usd', True)} | price {fmt(br.price, 'usd', True)} | actual {fmt(br.actual, 'usd')}")
    for name, e in br.by_segment.items():
        print(f"   {name:<11}" + "  ".join(f"{key} {fmt(x, 'usd', True):>8}" for key, x in e.items()))

    facts = build_facts(vs, br)
    llm = AnthropicLLM() if os.environ.get("ANTHROPIC_API_KEY") else MockLLM(sloppy=True)
    n = narrate(llm, facts)
    for i, issues in enumerate(n.issues_by_attempt, 1):
        print(f"\ndraft {i}: " + ("passes the number and direction check" if not issues else
                                  f"{len(issues)} issue(s)\n   - " + "\n   - ".join(issues)))
    print(f"\nExecutive summary ({n.source}, {n.attempts} attempt(s))\n" + "-" * 60)
    print(n.text)


if __name__ == "__main__":
    main()
