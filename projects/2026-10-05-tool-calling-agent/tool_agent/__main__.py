"""CLI: python -m tool_agent "What is hall_b.it_load_kw in BTU per hour?" """
import os
import sys
from pathlib import Path

from . import Agent, AnthropicChatLLM, KeywordPlannerLLM, default_registry, format_trace

DEMO_QUESTIONS = [
    "What is hall_b.it_load_kw in BTU per hour?",
    "How much headroom is left: hall_a.it_load_kw vs hall_a.design_capacity_kw?",
    "Generator runtime in hours = site.diesel_tank_liters / site.generator_burn_lph",
]


def main() -> None:
    registry = default_registry(Path(__file__).resolve().parent.parent / "data" / "ops_facts.json")
    llm = AnthropicChatLLM() if os.environ.get("ANTHROPIC_API_KEY") else KeywordPlannerLLM()
    questions = [" ".join(sys.argv[1:])] if sys.argv[1:] else DEMO_QUESTIONS
    for q in questions:
        print(f"Q: {q}")
        print(format_trace(Agent(llm, registry).run(q)))


if __name__ == "__main__":
    main()
