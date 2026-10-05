# Dock Door Scheduler

Assigns a day of inbound truck appointments to dock doors so trucks wait less in the yard. It respects reefer-only doors and door speeds, and it charges for dwell past the free window and for crew overtime. A greedy earliest-finish rule builds the plan, and iterated local search improves it.

```text
$ python -m dock_scheduler
42 trucks, 6 doors (2 reefer)

plan           avg wait max wait  reefer >60 min detention overtime    cost
rotation           75m     173m    121m      21    $1,346     110m   15935
greedy             25m      83m     29m       2        $0       0m    1414
local search       24m      83m     24m       5        $3       0m    1323

local search cost path: 1414 -> 1365 -> 1334 -> 1323

Door plan after local search (* reefer, +N = minutes waited)
D1 reefer 1.2m/plt  T03*@06:10 T08*@07:04(+44) T09*@07:43(+83) T26*@08:45 T29*@10:05 T27*@10:44(+39) T35*@11:31(+21) T41@12:35
D2 reefer 1.2m/plt  T05*@06:15 T11*@06:54(+19) T04*@07:34(+79) T20@08:28(+38) T23@09:14(+54) T28*@10:05 T33*@11:10 T38@11:49(+4)
D3 dry    1.0m/plt  T01@06:05 T07@06:54(+34) T15@07:41(+21) T16@08:24(+54) T22@09:13(+58) T30@10:25 T36@11:20 T39@12:15 T42@12:50
D4 dry    1.0m/plt  T02@06:10 T12@07:01(+11) T10@07:44(+74) T17@08:35(+55) T24@09:22(+62) T31@10:50 T37@11:41(+21)
D5 dry    1.6m/plt  T06@06:15 T14@07:09(+9) T19@07:50(+5) T18@08:31(+46) T25@09:25(+60) T34@11:10 T40@12:15
D6 dry    1.6m/plt  T13@08:00(+65) T21@09:00(+55) T32@11:10

detention saved vs rotation: $1,343 today, ~$335,750 over 250 shifts
```

## Why it matters
A DC that receives 40 or more trucks before noon usually assigns doors at the guard shack, in rotation. When the morning bank arrives together, rotation sends a 26-pallet load to the slow door while a fast door sits idle. Trucks pile up in the yard, and carriers bill detention once a driver has been on site for more than two hours (here $75/h). In the sample day, rotation leaves 21 of 42 trucks waiting more than an hour, runs $1,346 of detention and keeps two doors open 110 minutes past close. Earliest-finish assignment cuts the average wait from 75 to 25 minutes with no detention. Local search then reorders the reefer queue (reefer wait 29 → 24 min), which is where the product risk is. Across 250 receiving days the detention difference alone is about a third of a million dollars. Carriers also rate shippers on dwell time, and a "shipper of choice" gets capacity in a tight market.

## Architecture
```
data/doors.csv ─────────┐   reefer?, minutes per pallet, open/close
data/appointments.csv ──┤   arrival, pallets, reefer?
                        ▼
   rotation()  greedy(): earliest finish over compatible doors (ties keep reefer doors free)
       │             │
       │             ▼
       │      local_search(): descend() over relocate + swap moves
       │             │        kick 3 random trucks, descend again, keep if better (30 kicks, seeded)
       ▼             ▼
   door_slots(): per door, start = max(arrival, previous end + changeover)
       │
       ▼
   door_cost(): reefer-weighted wait + 10x minutes past free dwell + 5x overtime  ─► kpis() ─► report
```
- **The cost is separable by door.** Each door's timeline depends only on its own queue, so a relocate or swap move is priced by re-simulating just two doors. With six doors that is 3x cheaper than re-costing the whole day, and the saving grows with the number of doors.
- **The objective is convex in a single truck's wait.** With a linear wait objective, the search happily made one truck wait 157 minutes to save several others a few minutes each, which is what actually triggers detention and carrier complaints. The dwell-past-free-window penalty stops that.
- **Reefer wait counts double**, because a waiting reefer burns fuel and puts the cold chain at risk. Reefer doors can take dry trucks but not the other way round. Greedy breaks ties toward dry doors so it doesn't use up reefer capacity.
- **Why a heuristic rather than a MIP?** Door assignment with sequencing is NP-hard, and the stack here is standard library only. Greedy plus iterated local search gets within a few percent in seconds, and on a 5-truck instance a test checks that it matches the brute-force optimum. The yard also changes every 15 minutes, so a fast re-plan matters more than a proof of optimality.
- **Honest result.** Most of the gain comes from replacing rotation with a queue-aware rule. Local search adds about 6% on cost, mostly by protecting reefer loads. Both numbers are shown, so nobody oversells the clever part.

## Run
```bash
pip install pytest
python -m pytest -q                                   # 10 tests
python -m dock_scheduler                              # sample day
python -m dock_scheduler my_appointments.csv          # your own day, same columns
```

## Next steps
- Re-plan online as trucks check in early or late, freezing doors that are already in progress.
- Add labor: unload crews as a shared resource across doors, so two fast doors can't run at once with one crew.
- Learn unload minutes per pallet by carrier and SKU mix from WMS timestamps instead of using a per-door constant.
