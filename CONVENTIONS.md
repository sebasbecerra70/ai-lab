# Conventions

- Each project lives in `projects/<YYYY-MM-DD>-<kebab-slug>/`.
- **Python projects:** a package folder, `tests/` (pytest), an empty `conftest.py` at the project root, and `requirements.txt` only if needed (keep dependencies minimal; tests must not need network or API keys). Test command: `python -m pytest -q` from the project folder.
- **TypeScript projects:** `src/`, `*.test.ts` using `node:test`, and a `package.json` with a `test` script (`npx --yes tsx --test src/*.test.ts` or similar). Dependencies are allowed but keep them few. CI runs `npm install --no-audit --no-fund && npm test` when `package.json` exists.
- **LLM access:** always behind an interface with a deterministic mock used in tests, plus a real implementation (prefer the Anthropic Messages API, model `claude-sonnet-5-5`) that turns on when `ANTHROPIC_API_KEY` is set.
- **README.md sections:** one-line pitch, a sample run, Why it matters (a business angle tied to supply chain, logistics or operations), Architecture (with an ASCII diagram), Run, and Next steps.
- Add a row to the root README index between the `INDEX` markers, with the newest entry at the bottom.
