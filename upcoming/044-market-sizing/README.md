# Market Sizing Model

Size a market two independent ways, top-down from analyst spend and bottom-up from facility counts × fit × price. The model reconciles the two, takes SOM as the tighter of sales capacity and achievable share, and runs sensitivity tables that show which assumptions are worth arguing about.

```text
$ python -m market_sizing
AI capacity-planning software for data centers (priced per rack per year)
serving Europe, North America / colocation, enterprise

              top-down   bottom-up    gap
TAM            $217.0M     $183.3M   16%
SAM            $103.3M     $116.3M   11%
SOM              $3.4M       $3.6M       bottom-up capped by sales capacity
(SOM = ARR after 3 years)

Tornado: bottom-up SOM $3.6M, each assumption at low / high
  reps                        $2.4M .. $4.8M     swing $2.4M
  deals_per_rep_per_year      $2.4M .. $4.8M     swing $2.4M
  price_per_rack              $2.7M .. $4.8M     swing $2.1M

SOM by price per rack (rows) x deals per rep per year (cols)
                 6         9        12
     $45     $1.8M     $2.7M     $3.6M
     $62     $2.5M     $3.8M     $5.0M
     $80     $3.2M     $4.8M     $6.4M
```

## Why it matters
Most pitch-deck TAMs come from multiplying one analyst number by a hopeful percentage, and investors and partner committees know it. A BD lead who walks in with two sizings that agree within 11-16% has a defensible number: one built from spend, one built from 11 region × tier segments of facility counts, rack density and fit. The more useful result is the SOM. Year-3 revenue in this sample is $3.6M, and it is capped by **sales capacity** (6 AEs × 9 deals/yr), not by the $116M SAM. The tornado makes the same point. Reps and win rate each swing SOM by $2.4M, and the market-size inputs barely move it. So the business case should be argued about hiring and sales productivity, not about whether TAM is $180M or $220M.

This is spreadsheet math on purpose. An LLM adds nothing to multiplication, and every number here needs to trace back to a named assumption with a source.

## Architecture
```
assumptions.json (base/low/high + source)      segments.csv (region, tier, facilities, racks, fit)
          │                                               │
          ▼                                               ▼
   top_down(): spend × module share              bottom_up(): Σ facilities × fit × racks × price
          × served regions × served tiers                 filter to served regions/tiers = SAM
          │                                               │
          └──────────► SOM = min(reps × deals × years × avg deal,  SAM × max share) ◄┘
                                    │
                    reconcile(): TAM/SAM gap ≤ 30%? else flag
                                    │
              tornado(): each assumption to low/high ── two_way(): price × productivity grid
```
- **Two methods, one SOM rule.** The methods share no inputs except price, so agreement between them is real evidence. A gap over 30% gets flagged instead of averaged away.
- **SOM is a min of two constraints, and the model reports which one binds.** That tells the reader whether the plan is limited by go-to-market or by the market itself.
- **Every assumption carries low/base/high and a source.** Loading fails if the base falls outside its own range, which catches the most common spreadsheet error: someone edits the base and forgets the bounds.
- **Tornado drops zero-swing inputs.** Showing that top-down inputs don't move bottom-up SOM is itself the finding.

## Run
```bash
pip install pytest
python -m pytest -q                 # 9 tests
python -m market_sizing             # sample: data center capacity-planning software
python -m market_sizing path/to/dir # your own assumptions.json + segments.csv
```

## Next steps
- Monte Carlo over the low/high ranges (triangular distributions) to report a P10/P50/P90 SOM.
- Add a year-by-year ramp with rep hiring dates, ramp time and churn instead of a single horizon.
- Export the tornado and two-way tables to CSV for the board deck.
