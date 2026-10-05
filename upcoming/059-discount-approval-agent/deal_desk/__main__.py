"""CLI: python -m deal_desk [deals.json]"""
import os
import sys
from pathlib import Path

from . import AnthropicLLM, MockLLM, fit, load_deals, load_history, load_policy, log_loss, review

DATA = Path(__file__).resolve().parent.parent / "data"


def main() -> None:
    policy = load_policy(DATA / "policy.json")
    deals = load_deals(Path(sys.argv[1]) if len(sys.argv) > 1 else DATA / "deals.json")
    history = load_history(DATA / "history.csv")
    model = fit(history)
    base = sum(r["won"] for r in history) / len(history)
    print(f"win model: {len(history)} closed deals, log loss {log_loss(model, history):.3f} "
          f"(base rate {base:.0%}); p(win) mid-market, no competitor: "
          + ", ".join(f"{d}% -> {model.p_win(d, False, 'mid-market'):.0%}" for d in (0, 10, 20, 30, 40)))
    # offline, the mock misquotes one margin so the memo check has something to catch
    llm = AnthropicLLM() if os.environ.get("ANTHROPIC_API_KEY") else MockLLM(sloppy={"Q-1044"})
    reviews = [review(d, policy, llm, model, history) for d in deals]
    for r in reviews:
        d, f = r.decision, r.facts
        print(f"\n== {d.deal.id} {d.deal.customer}: {d.deal.discount:.0f}% on ${f['list_arr']:,} list "
              f"-> {d.status.upper()} ({', '.join(d.approvers)})")
        allow = f" after {', '.join(f'{k} -{v}' for k, v in d.allowances.items())}" if d.allowances else ""
        print(f"   effective {d.effective_discount:.0f}%{allow}; margin {d.margin:.0%}; net ARR ${f['net_arr']:,}")
        for x in d.findings:
            print(f"   ! {x.rule}: {x.detail}" + (f" -> {x.route}" if x.route else "") + ("  [BLOCKING]" if x.blocking else ""))
        for g in d.give_gets:
            print(f"   > {g}")
        if f["counter_discount_pct"] != f["discount_pct"]:
            print(f"   win model: {f['win_at_request_pct']}% at {f['discount_pct']}% vs {f['win_at_counter_pct']}% "
                  f"at {f['counter_discount_pct']}%; expected ARR ${f['expected_arr_request']:,} vs "
                  f"${f['expected_arr_counter']:,}")
        if r.memo_issues:
            print(f"   memo REJECTED ({'; '.join(r.memo_issues)}), template memo used")
        else:
            print(f"   memo ok: {r.memo.splitlines()[0][:110]}...")
    by = {s: [r for r in reviews if r.decision.status == s] for s in ("auto-approve", "escalate", "reject")}
    given = sum(r.decision.deal.list_arr - r.decision.deal.net_arr() for r in reviews)
    print("\n" + ", ".join(f"{s}: {len(v)}" for s, v in by.items()) + f"; discount requested ${given:,.0f}/yr")


if __name__ == "__main__":
    main()
