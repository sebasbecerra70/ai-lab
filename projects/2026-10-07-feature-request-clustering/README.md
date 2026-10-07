# Feature Request Clustering

Groups a backlog of raw feature requests into themes with TF-IDF and k-means, has an LLM name each theme, and **ranks the themes by ARR at stake**, not by how many tickets they have.

```text
$ python -m request_clusters
40 feature requests -> 6 themes, ranked by ARR at stake
silhouette by k: k=4:0.24  k=5:0.27  k=6:0.31  k=7:0.27  -> k=6
1. API / Webhook / Order requests  [9 requests, 7 accounts, $686k ARR]
   terms: api, webhook, order, table, erp
   e.g. "Public REST API endpoint to create orders programmatically"
2. Chatop / Slack / Notification requests  [7 requests, 7 accounts, $589k ARR]
   terms: chatop, slack, notification, msteam, channel
   e.g. "Send a Slack message when a task is assigned to me"
3. SSO / SAML / Login requests  [7 requests, 7 accounts, $579k ARR]
   terms: sso, saml, login, okta, user
   e.g. "Single sign-on with Ping Identity using SAML 2.0"
4. Mobile / APP / Offline requests  [6 requests, 6 accounts, $507k ARR]
   terms: mobile, app, offline, barcode, support
   e.g. "Mobile app should queue scans offline and sync later"
5. Export / CSV / Excel requests  [7 requests, 7 accounts, $358k ARR]
   terms: export, csv, excel, data, report
   e.g. "Download raw data export in CSV for our BI tool"
6. DARK / MODE / Theme requests  [4 requests, 4 accounts, $131k ARR]
   terms: dark, mode, theme, warehouse, mobile
   e.g. "Let users pick a dark mode or high contrast theme"
```

## Why it matters
A PM with 400 open requests across Zendesk, Gong notes and a Salesforce field can't read them all before planning, and request counts are misleading: the loudest small customer files ten tickets. Here, the 7 chat-notification asks come from 7 accounts worth $589k ARR, and dark mode is 4 asks worth $131k. That turns a roadmap argument into a revenue conversation with sales. Counting each account once per theme stops one vocal customer from inflating a theme.

## Architecture
```
requests.csv ─► tokenize (synonyms, stopwords, light stemming)
                     │
                     ▼
              TF-IDF (min_df=2) ─► unit vectors
                     │
                     ▼
     k-means++ (cosine, 8 restarts) for k in 4..7 ─► silhouette picks k
                     │
                     ▼
   per cluster: top centroid terms + 4 most central requests
                     │
                     ▼
         LLMClient.complete ─► theme name (MockLLM | Claude)
                     │
                     ▼
     rank themes by de-duplicated ARR ─► report
```
- **Classic ML does the grouping and the LLM only names the groups.** Clustering 40 or 40,000 requests with TF-IDF + k-means is free, deterministic and reproducible. The LLM gets one short prompt per cluster, so a full run costs a few cents and stays auditable.
- **Synonyms beat a bigger model here.** Five hand-written rules ("single sign-on" → sso, Slack/Teams → chatops) raised silhouette from 0.27 to 0.31 and fixed the obvious mis-splits. A product team can maintain that list.
- **Silhouette chooses k** within a sensible range, so the number of themes isn't tuned by hand. The scores are printed so the reviewer can overrule them.
- **The labeling prompt uses the most central examples**, not random ones, so the name describes a typical request in the cluster.
- **Trade-off:** bag-of-words misses paraphrases with no shared words (e.g. "can't log in with corporate account" vs "SSO"). Hashed or neural embeddings are the next step if that matters.

## Run
```bash
pip install pytest
python -m pytest -q                 # 10 tests, offline
python -m request_clusters          # choose k by silhouette
python -m request_clusters 5        # force k=5
ANTHROPIC_API_KEY=... python -m request_clusters   # Claude writes the theme names
```

## Next steps
- Swap TF-IDF for embeddings and compare silhouette and a hand-labeled purity score.
- Track themes week over week (match new centroids to old ones) to spot rising asks.
- Weight by renewal date: ARR renewing in the next 90 days matters more.
