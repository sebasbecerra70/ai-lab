# Power Distribution

## PDU breaker trip
1. Identify the tripped breaker and affected racks from the DCIM power view.
2. Confirm affected servers failed over to their B-side power supplies.
3. Check the rack's power draw history for overload before the trip.
4. Do not reset a breaker more than once; a second trip indicates a fault that needs an electrician.
5. Reset the breaker once, then watch the branch current for 15 minutes.
6. If the circuit was overloaded, move load to another circuit and update the rack power budget.

## Lockout tagout for electrical work
1. Only qualified electricians may perform lockout tagout.
2. Notify affected customers and the ops bridge before isolating any circuit.
3. Isolate the circuit, apply a personal lock and tag, and verify zero energy with a rated tester.
4. Never bypass or remove another person's lock.
5. Remove locks only after work is complete and the area is clear, then restore power and verify.
