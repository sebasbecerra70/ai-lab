# Prompt Caching Cost Model

Estimate what prompt caching will actually save on *your* traffic before you ship it. The tool replays realistic arrival patterns against Claude's cache rules (write premiums, TTL refresh on read, minimum cacheable prefix) and recommends no cache, a 5-minute TTL or a 1-hour TTL.

```text
$ npm run demo
claude-sonnet-5-5: $2/$10 per MTok, cache read $0.2, min cacheable 512 tokens
workload: 12000 prefix + 400 dynamic input, 350 output tokens
break-even: 5m TTL needs 1 read per write, 1h TTL needs 2

pattern         req/day  no cache       5m       1h  hit% 5m/1h   best
steady             2867    $81.14   $19.24   $19.25  100/100     5m (-76%)
business-hours     1646    $46.58   $12.46   $11.07  97/100      1h (-76%)
bursty             1183    $33.48    $8.26    $8.47  99/99       5m (-75%)
sparse               83     $2.35    $2.38    $0.69  20/96       1h (-71%)
  steady         support bot, 120 req/h around the clock
  business-hours internal copilot, 200 req/h 9-17, 4 req/h otherwise
  bursty         batch-ish jobs: 10-minute bursts of 600 req/h, every 2 hours
  sparse         niche tool, 3 req/h
```

## Why it matters
"Turn on caching, save 90%" is the pitch, but the real savings depend on traffic shape. A support bot with a 12k-token system prompt and 3k requests a day spends about $81/day on Sonnet 5.5 without caching and about $19 with it. That's roughly $22k a year on one endpoint. A niche internal tool at 3 requests an hour gets *nothing* from the default 5-minute TTL (it pays 1.25x write premiums and almost never reads), but saves 71% with the 1-hour TTL. And a 3k-token prefix on Haiku 4.5 never caches at all, because it's under the 4,096-token minimum, which is exactly the kind of silent miss that makes caching projects disappointing. This model lets a platform team answer "which endpoints are worth it, and with which TTL?" in a planning meeting instead of after a month of invoices.

## Architecture
```
standardPatterns()  steady | business-hours | bursty | sparse
   (seeded Poisson arrivals with time-varying rate, thinning)
            │ arrival times (s)
            ▼
simulate(arrivals, workload, model, ttl)
   prefix < model minimum? → price as uncached
   t < expiresAt ? read (cacheRead $) : write (input × 1.25 | 2)
   expiresAt = t + TTL            ← every read refreshes the entry
            │
            ▼
recommend(): cost for none / 5m / 1h → cheapest + savings
breakEvenReads(): reads per write needed to beat no-cache
```
- **Simulation instead of a formula.** Hit rate depends on the gaps between requests, not on the average rate. A business-hours copilot misses at 9am every day, and a bursty batch job misses at the start of every burst. A replay captures that, while a closed-form "requests × 0.9" overstates savings.
- **Pricing lives in one table** (`pricing.ts`), using list prices for Opus 5.5, Sonnet 5.5 and Haiku 4.5, with the cache-read price set per model rather than as a fixed 0.1x (Opus 5.5 reads are 0.05x).
- **A known optimistic assumption:** concurrent cold-start requests are assumed to share one write. In reality, parallel requests that arrive before the first write finishes each pay a write. That cost is noticeable only at burst onset.
- **No LLM calls.** This is a cost and capacity planning tool. Every number is reproducible from the seed, which is what a finance partner needs.

## Run
```bash
npm test                                   # 9 node:test tests
npm run demo                               # Sonnet 5.5, 12k-token prefix
npx tsx src/cli.ts claude-haiku-4-5 3000   # see the minimum-prefix trap
npx tsx src/cli.ts claude-opus-5-5 40000
```

## Next steps
- Load real arrival timestamps from request logs (CSV), and group them by prefix hash to model several cache entries.
- Add a keep-alive strategy (a `max_tokens: 0` refresh just before expiry) and compare it with the 1-hour TTL for sparse traffic.
- Model multi-turn conversations, where the cached prefix grows each turn.
