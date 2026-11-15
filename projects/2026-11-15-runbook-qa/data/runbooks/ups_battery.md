# UPS Battery Alarms

## UPS on battery alarm
1. Check the BMS for a utility power loss or a transfer to generator.
2. If utility is present, inspect the UPS input breaker and the static switch status on the UPS front panel.
3. Note the estimated battery runtime shown on the UPS display and announce it on the ops bridge.
4. If runtime is under 10 minutes and generator has not started, start the critical load shedding plan.
5. Page the electrical on-call engineer and open a P1 incident.

## UPS battery string high temperature
1. Confirm the reading on two independent sensors before acting.
2. Verify the battery room CRAC unit is running and the room temperature is below 25 C.
3. If a single string exceeds 40 C, isolate that string using its DC disconnect, per the vendor procedure.
4. Do not open battery cabinets while a string is in thermal runaway; evacuate and call the fire department.
5. Open a P2 incident and request a battery vendor inspection.
