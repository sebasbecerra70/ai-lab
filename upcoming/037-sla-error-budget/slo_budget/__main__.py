"""CLI: python -m slo_budget"""
from pathlib import Path

from . import (BudgetStatus, Timeline, incident_cost, load_config, load_incidents, match_incidents, nines_table,
               replay, sla_credit_pct)

DATA = Path(__file__).resolve().parent.parent / "data"


def fmt_min(m: int) -> str:
    return f"d{m // 1440 + 1:02d} {m % 1440 // 60:02d}:{m % 60:02d}"


def main() -> None:
    cfg, incidents = load_config(DATA / "slo.json"), load_incidents(DATA / "incidents.csv")
    slo = cfg["slo_target"]
    print("allowed downtime   30d      quarter   year")
    for t, d30, dq, dy in nines_table():
        print(f"  {t:<8.4%}  {d30:7.1f}m {dq:8.1f}m {dy / 60:6.1f}h")

    tl = Timeline.synthesize(cfg, incidents)
    bad, total = tl.window(len(tl), len(tl))
    status = BudgetStatus(slo, total - bad, total)
    print(f"\n{cfg['service']} SLO {slo:.1%} over {cfg['window_days']}d: {total / 1e6:.1f}M requests, "
          f"SLI {status.sli:.4%}, budget used {status.consumed:.0%} (remaining {status.remaining:.0%})")

    events = replay(tl, slo, step=1)
    print("\nincident   dur   budget   first alert        delay")
    for det in match_incidents(incidents, events):
        inc = det.incident
        share = incident_cost(tl, inc, cfg["baseline_error_rate"]) / status.budget_events
        alert = f"{det.first_alert.rule.name:<12} {det.delay_min:>4}m" if det.first_alert else "none         -"
        print(f"{inc.incident_id}  {inc.duration:>4}m  {share:6.1%}   {alert}   {inc.description}")
    matched = {id(d.first_alert) for d in match_incidents(incidents, events) if d.first_alert}
    print(f"\n{len(events)} alert events ({sum(e.rule.severity == 'page' for e in events)} pages)")
    for e in events:
        print(f"  {fmt_min(e.fired_at)} -> {fmt_min(e.resolved_at)}  {e.rule.severity:<6} {e.rule.name}"
              f"{'' if id(e) in matched else '  (follow-on)'}")

    credit = sla_credit_pct(status.sli, cfg["sla_tiers"])
    print(f"\nSLA: availability {status.sli:.3%} -> credit {credit}% "
          f"(${cfg['monthly_contract_value_usd'] * credit / 100:,.0f} on ${cfg['monthly_contract_value_usd']:,}/month)")


if __name__ == "__main__":
    main()
