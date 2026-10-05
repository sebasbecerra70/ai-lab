# Release Notes Generator

Turn a release's conventional commits into customer-facing release notes. Commits are grouped by user impact, internal work is hidden, duplicates are dropped, the semver bump is inferred, and breaking changes come with the migration action. An LLM then polishes the wording, and a guard rejects any rewrite that drops a number or invents a fact.

```text
$ npm run demo

16 commits: 1 duplicate, 5 internal (hidden), 1 non-conventional
  needs a human: b7a6c5d "updated stuff"
semver: 3.7.2 -> 4.0.0 (major: 2 breaking change(s))

## 4.0.0

### Breaking changes
- **Dashboards:** V2 layout engine replaces legacy widgets API (#401)
  - Action needed: custom widgets built on /api/v1/widgets must migrate to /api/v2/layouts.
- **Notifications:** Email digests now respect the workspace timezone (#411)
  - Action needed: digest send time moves from 09:00 UTC to 09:00 in each workspace's timezone.

### New
- **Billing:** Usage-based invoices with per-seat line items (#412)
- **Integrations:** Slack notifications for SLA breaches (#409)

### Fixed
- **Exports:** CSV export no longer drops rows with unicode customer names (#418)
- **Sign-in:** Single sign-on login loop after the identity provider session expired (#420, #398)
- **Billing:** Rounding error on prorated seat refunds (#422)

### Faster
- **Search:** cache tokenized index per workspace, p95 from 840ms to 210ms (#415)

polish: 7/8 rewrites accepted
  kept original for N4: dropped number(s) 95, 840, 210 ("Search is now much faster for large workspaces")
```

## Why it matters
Release notes are where product, support and customer success learn what shipped, and they're usually written at 6 p.m. on release day by whoever drew the short straw. Two failure modes cost real money. The first is a breaking change buried in a list of fixes: the digest timezone change above would generate a wave of "why did my email arrive at 3 a.m." tickets if customers weren't told. The second is marketing-style polish that loses the facts ("search is much faster" instead of "840 ms → 210 ms"). This pipeline makes the structure deterministic (sections, migration actions, issue links, version number) and uses the LLM only for wording. The guard caught the vague performance rewrite and kept the precise original. For a team shipping every two weeks, that's about 26 releases a year that go out consistent and on time instead of becoming a recurring chore.

## Architecture
```
git log ──► parseLog(): type(scope)!: subject (#ref) | BREAKING CHANGE: footer | Refs: #n
              ▼
           dedupe(): same (type, scope, subject) twice → drop (cherry-picks, re-merges)
              ▼
           group(): breaking | feat | fix | perf → user sections, scope → product area (glossary)
                    chore/ci/test/docs/refactor → counted, hidden;  non-conventional → "needs a human"
              ▼                                  ▼
           semverBump() → 3.7.2 → 4.0.0       polish(): LLM gets "N3 | fix | subject" + jargon glossary
                                                 ▼  returns {id: text}
                                              checkRewrite() per item: no lost/new numbers, no #refs,
                                              ≤160 chars, no unknown ids → else keep the original
              └────────────────► render(): markdown with Action needed: lines and refs
```
- **The model never controls structure.** Sections, ordering, issue links and the version number come from code. The model returns `{id: text}` only, so it can't reorder, merge or drop items.
- **Per-item fallback instead of all-or-nothing.** One bad rewrite keeps its original subject, and the other seven polished lines still ship.
- **Numbers are facts.** Any number missing from the rewrite, or added by it, rejects that rewrite. It's a cheap check that catches the most common way LLM polish misleads.
- **Commit hygiene shows up in the output.** "updated stuff" is surfaced for a human rather than silently dropped, which is a gentle nudge toward better commit messages.

## Run
```bash
npm test                                   # 10 tests (node:test via tsx)
npm run demo                               # sample release, mock LLM
git log v3.7.2..HEAD --format='commit %h%n%B' > /tmp/log.txt && npx tsx src/cli.ts /tmp/log.txt 3.7.2
ANTHROPIC_API_KEY=... npm run demo
```

## Next steps
- Pull PR titles and labels from the GitHub API, since PR descriptions are often better source text than commits.
- Produce audience variants from the same items: a customer changelog, an internal support brief, and an API changelog limited to breaking changes.
- Fail CI when a breaking change has no `BREAKING CHANGE:` migration note.
