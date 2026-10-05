"""CLI: python -m invoice_extract [invoice.txt ...] [--json]"""
import json
import os
import sys
from pathlib import Path

from . import AnthropicLLM, InvoiceExtractor, RecordedLLM


def main() -> None:
    data = Path(__file__).resolve().parent.parent / "data"
    args = [a for a in sys.argv[1:] if a != "--json"]
    files = [Path(a) for a in args] or sorted((data / "invoices").glob("*.txt"))
    llm = AnthropicLLM() if os.environ.get("ANTHROPIC_API_KEY") else RecordedLLM.from_file(data / "mock_responses.json")
    extractor = InvoiceExtractor(llm)
    for f in files:
        result = extractor.extract(f.read_text())
        d = result.data
        fixed = sorted(k for k, s in result.sources.items() if s == "regex")
        print(f"{f.name}: {d.get('invoice_number')} {d.get('vendor')}  {d.get('currency')} {d.get('total')}  "
              f"lines={len(d.get('line_items', []))}  [{result.status}]")
        if result.llm_errors:
            print(f"    llm issues: {result.llm_errors}")
            print(f"    regex filled: {', '.join(fixed)}")
        if result.errors:
            print(f"    still failing: {result.errors}")
        if "--json" in sys.argv:
            print(json.dumps(d, indent=2))


if __name__ == "__main__":
    main()
