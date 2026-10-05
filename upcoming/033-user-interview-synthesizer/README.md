# User Interview Synthesizer

Turn raw customer interview transcripts into a ranked affinity map and a short, citation-checked insight summary, so a PM can go from six interviews to a prioritized problem list in seconds.

```text
$ npm run demo
6 interviews, 30 participant quotes, 1 untagged

AFFINITY MAP (ranked by reach, pain first)
[-] Pricing & packaging  (5 participants: P1, P2, P3, P4, P6; net -4)
      P2-1: "Pricing is confusing, I could not tell which tier included the forecasting module."
      P3-5: "The price jumped at renewal and nobody explained why."
[-] Onboarding & setup  (5 participants: P1, P2, P3, P5, P6; net -1)
      P1-1: "Setup took us almost two weeks because nobody could find the import template."
      P2-3: "The onboarding checklist was too long and my team skipped half of it."
[-] Reporting & export  (5 participants: P1, P2, P3, P5, P6; net -1)
      P1-3: "The weekly report export breaks when we have more than a few thousand rows."
      P6-5: "Exporting a report to PDF cuts off the last column."
[-] Collaboration  (4 participants: P3, P4, P5, P6; net -1)
      P3-2: "I share screenshots in Slack because there's no way to comment on a chart."
      P6-4: "I wish I could leave notes for the night shift inside the app."
[~] Integrations  (4 participants: P1, P2, P4, P5; net 0)
      P5-4: "We still copy data from our ERP by hand because there's no SAP connector."
      P1-4: "Honestly I would pay more if it connected to our WMS directly."
[-] Performance  (3 participants: P3, P4, P5; net -3)
      P3-1: "The app is slow when I open the SKU view, sometimes it takes ten seconds to load."
      P4-4: "Dashboards load slowly on Monday mornings when everyone logs in."
[~] Support  (2 participants: P1, P4; net 0)
      P4-3: "Support was slow during the holidays, we waited three days for a reply."
      P1-5: "Support answered fast, usually within an hour, which saved us during peak."
[+] Alerts & monitoring  (2 participants: P2, P6; net 2)
      P2-4: "I love the alerting, it caught a stockout two days early."
      P6-3: "The temperature alerts are the best feature, they saved a shipment last month."

INSIGHTS
1. Pricing & packaging is a pain point for 5 of 6 participants. [P1-4] [P2-1]
2. Onboarding & setup is a pain point for 5 of 6 participants. [P1-1] [P2-3]
3. Reporting & export is a pain point for 5 of 6 participants. [P1-3] [P2-2]

citation check: 6 cited, 0 unknown, 0 uncited insight lines
```

## Why it matters
A PM running a discovery sprint usually ends up with 6-12 hour-long interviews and spends a day or two on sticky notes before anyone sees a synthesis. This tool does the mechanical part (tagging, counting, grouping quotes) in a transparent, repeatable way. The LLM only writes the narrative, and every claim has to cite a real quote ID. In the sample, it shows within seconds that pricing confusion came up with 5 of 6 customers. That's the kind of finding that changes a roadmap: a packaging fix can ship in a sprint, while the integration everyone assumed was #1 has more mixed sentiment.

## Architecture
```
interviews.txt ──► parseTranscripts()  → quotes with stable IDs (P2-3)
                         │
                         ▼
             tagThemes() codebook + sentiment() lexicon
                         │
                         ▼
             buildAffinityMap()  group by theme, rank by #participants, pain first
                         │
          ┌──────────────┴──────────────┐
          ▼                             ▼
 renderAffinityMap()            buildPrompt() → LLMClient (Mock | Claude)
                                        │
                                        ▼
                               checkCitations(): unknown IDs, uncited insights
```
- **Deterministic first, LLM last.** Counting how many participants raised a theme is a job for code, not a model. The model gets pre-counted clusters, so it can't inflate "most users said..." claims.
- **Codebook over clustering.** A reviewable keyword codebook is what research teams already use. It's explainable and easy to edit, and the `untagged` bucket shows what the codebook misses (here, P1-2's praise for the dashboard). The trade-off is recall on phrasing you didn't anticipate.
- **Reach before volume.** Ranking by distinct participants avoids one talkative interviewee dominating the map.
- **Citation guard.** `checkCitations` rejects quote IDs that don't exist and insight lines with no citation, which are the two most common ways an LLM summary drifts from the evidence.

## Run
```bash
npm test          # 10 node:test tests, offline
npm run demo      # uses MockLLM; set ANTHROPIC_API_KEY to use Claude
npx tsx src/cli.ts path/to/your-interviews.txt
```

## Next steps
- Let the LLM propose new codebook themes from the untagged bucket, and have a human approve them.
- Weight participants by segment (ARR, persona), so reach reflects business impact.
- Export the affinity map as a FigJam/Miro board for workshop use.
