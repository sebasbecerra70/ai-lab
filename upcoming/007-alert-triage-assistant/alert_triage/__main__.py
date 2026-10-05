"""CLI: python -m alert_triage"""
import os
from pathlib import Path

from . import AnthropicLLM, TemplateLLM, Topology, dedupe, draft_summary, fmt_time, load_alerts, triage


def main() -> None:
    data = Path(__file__).resolve().parent.parent / "data"
    alerts = load_alerts(data / "alerts.json")
    topo = Topology.load(data / "topology.json")
    incidents = triage(alerts, topo)
    print(f"{len(alerts)} alerts -> {len(dedupe(alerts))} deduped groups -> {len(incidents)} incidents\n")
    for inc in incidents:
        print(f"{inc.severity} (score {inc.points}) root cause: {inc.root_cause}  start {fmt_time(inc.first)}  "
              f"alerts {inc.alert_count}")
        for g in inc.groups:
            print(f"    {g.host:<9}{g.check:<16}x{len(g.alerts):<3}{g.severity}")
    llm = AnthropicLLM() if os.environ.get("ANTHROPIC_API_KEY") else TemplateLLM()
    print("\nOn-call summary:")
    print(draft_summary(incidents, llm))


if __name__ == "__main__":
    main()
