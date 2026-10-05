# Pricing Simulator

Fits **price elasticity** from price/volume history, runs what-if price changes, breaks each deal into a **pocket-price waterfall**, and shows how much extra volume a discount has to win just to break even.

```text
$ npm run demo
SW-18-80 Stretch wrap 18in 80ga (case)
  list $52.00, cost $31.50 (margin 39%), 4,200 units/mo
  elasticity -1.71 (R² 0.83, 10 price points) -> elastic
    change    price   units    revenue  gross profit  vs today
    -10.0%   $46.80   5,030   $235,397       $76,957    -10.6%
     -5.0%   $49.40   4,585   $226,515       $82,077     -4.7%
     +0.0%   $52.00   4,200   $218,400       $86,100     +0.0%
     +5.0%   $54.60   3,864   $210,951       $89,248     +3.7%
    +10.0%   $57.20   3,568   $204,084       $91,695     +6.5%
  profit-maximizing price: $58.22 (capped at the observed price range: the model is not trusted beyond it)

TP-48-2 Carton tape 48mm (case of 36)
  list $64.00, cost $38.00 (margin 41%), 2,600 units/mo
  elasticity -2.65 (R² 0.95, 10 price points) -> elastic
    change    price   units    revenue  gross profit  vs today
    -10.0%   $57.60   3,438   $198,055       $67,394     -0.3%
     -5.0%   $60.80   2,979   $181,123       $67,921     +0.5%
     +0.0%   $64.00   2,600   $166,400       $67,600     +0.0%
     +5.0%   $67.20   2,284   $153,508       $66,703     -1.3%
    +10.0%   $70.40   2,019   $142,147       $65,420     -3.2%
  profit-maximizing price: $60.99

CB-HD-24 Heavy-duty corner board 24in (bundle)
  list $39.00, cost $17.50 (margin 55%), 1,500 units/mo
  elasticity -0.31 (R² 0.20, 10 price points) -> inelastic
    change    price   units    revenue  gross profit  vs today
    -10.0%   $35.10   1,550    $54,421       $27,288    -15.4%
     -5.0%   $37.05   1,524    $56,478       $29,801     -7.6%
     +0.0%   $39.00   1,500    $58,500       $32,250     +0.0%
     +5.0%   $40.95   1,477    $60,491       $34,640     +7.4%
    +10.0%   $42.90   1,456    $62,452       $36,976    +14.7%
  profit-maximizing price: $42.89 (capped at the observed price range: the model is not trusted beyond it)

pocket-price waterfalls:

  Delta Freight - 900 x SW-18-80
    list price                 $52.00    $52.00
    volume discount            -$3.12    $48.88
    promo discount             -$1.96    $46.92
    = invoice price                      $46.92
    rebate                     -$0.94    $45.99
    payment terms (60d)        -$0.34    $45.65
    freight                    -$2.40    $43.25
    = pocket price                       $43.25
    unit cost                 -$31.50    $11.75
    = pocket margin                      $11.75
    pocket margin 22.6% of list vs 39.4% list margin; $10,572 per order

  Harbor Retail DC - 400 x SW-18-80
    list price                 $52.00    $52.00
    volume discount            -$1.56    $50.44
    = invoice price                      $50.44
    freight                    -$1.10    $49.34
    = pocket price                       $49.34
    unit cost                 -$31.50    $17.84
    = pocket margin                      $17.84
    pocket margin 34.3% of list vs 39.4% list margin; $7,136 per order

  Quanta Auto - 650 x TP-48-2
    list price                 $64.00    $64.00
    volume discount            -$5.12    $58.88
    promo discount             -$2.94    $55.94
    = invoice price                      $55.94
    rebate                     -$1.68    $54.26
    payment terms (90d)        -$0.80    $53.46
    freight                    -$2.90    $50.56
    = pocket price                       $50.56
    unit cost                 -$38.00    $12.56
    = pocket margin                      $12.56
    pocket margin 19.6% of list vs 40.6% list margin; $8,161 per order

discount break-even (extra volume needed to keep gross profit flat):
  discount    margin 20%  margin 30%  margin 40%  margin 55%
  5%                +33%        +20%        +14%        +10%
  10%              +100%        +50%        +33%        +22%
  15%              +300%       +100%        +60%        +37%
  20%              never       +200%       +100%        +57%
```

## Why it matters
Most B2B price leakage is invisible on the invoice. In the sample, Delta Freight's order looks like a routine 6% + 4% discount, but after the rebate, 60-day terms and freight the business keeps **22.6% of list instead of 39.4%**. That is $10.6k of margin on a single order where list margin suggests about $18.4k. The break-even table tells the sales manager what that discount must buy: at a 40% margin, a 10% discount needs **33% more volume** to keep gross profit flat, and at 20% margin a 20% discount can never pay back.

The elasticity side answers the opposite question for a BD or pricing lead. Carton tape is elastic (-2.65), so a 5% increase loses profit. Corner board is inelastic (-0.31), so a 5% increase adds about 7% to gross profit with little volume lost. The low R² (0.20) there is a flag to run a controlled price test before rolling it out.

## Architecture
```
data/products.json ─► fitElasticity: OLS on ln(units) ~ ln(price)  ─► elasticity, R²
        │                       │
        │                       ▼
        │             whatIf: Q1 = Q0·(P1/P0)^e  ─► units, revenue, gross profit vs today
        │             optimalPrice: P* = c·e/(1+e), capped to the observed price range
        ▼
data/deals.json ───► waterfall: list ─ volume ─ promo = invoice
                                 ─ rebate ─ terms (cost of capital) ─ freight = pocket
                                 ─ unit cost = pocket margin   (zero-value rows dropped)
                     breakEvenVolumeIncrease: d / (m − d)
```
- **Constant-elasticity (log-log) demand.** One parameter is easy to explain to a sales team and fits typical price tests well locally. The trade-off is that it is only trustworthy near observed prices, so the optimizer is capped at the observed price range and the output says when that cap applies.
- **Anchored what-ifs.** Scenarios scale from today's actual volume, not from the regression intercept, so a 0% change reproduces today's numbers exactly and fit noise doesn't shift the baseline.
- **Off-invoice leakage is priced explicitly.** Rebates come off the invoice price, and extended payment terms are charged at a 9% annual cost of capital for the days beyond net-30. These are the items an invoice-price report misses.
- **Discounts compound** (the promo applies to the already volume-discounted price), which matches how most ERPs apply them.
- **Why not an LLM?** Every number here is arithmetic or a two-parameter regression, so an LLM would add cost and risk without adding insight. The output is already a table a deal desk can read.
- No dependencies: Node's built-in test runner and `tsx`.

## Run
```bash
npm test          # 10 tests (node:test via tsx)
npm run demo
```
Edit `data/products.json` (list price, cost, volume, price history) and `data/deals.json` to model your own line.

## Next steps
- Add cross-price elasticity between substitute SKUs, so that a price rise on one SKU shows the volume moving to the other.
- Bootstrap the elasticity fit to give a confidence band on each what-if row.
- Add a deal-desk check that flags any quote whose pocket margin falls below a floor before it is approved.
