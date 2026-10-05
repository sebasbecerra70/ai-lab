"""Seeded generator for a few hours of data center syslog with one injected incident."""
from __future__ import annotations

import random
from pathlib import Path

HOSTS = [f"r{r:02d}-bmc" for r in range(10, 16)] + ["core-sw1", "core-sw2", "pdu-a3", "pdu-b3"]


def _ts(sec: int) -> str:
    return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


def _ip(rng):
    return f"10.20.{rng.randint(0, 9)}.{rng.randint(2, 250)}"


ROUTINE = [  # (weight, host pool, message factory)
    (30, "bmc", lambda r: f"sensor CPU{r.randint(0, 1)}_Temp reading {r.randint(48, 66)} C ok"),
    (20, "bmc", lambda r: f"fan FAN{r.randint(1, 6)} speed {r.randint(7800, 9200)} RPM ok"),
    (12, "sw", lambda r: f"Interface Ethernet1/{r.randint(1, 48)} link up, speed 25G"),
    (10, "sw", lambda r: f"BGP neighbor {_ip(r)} keepalive received"),
    (8, "bmc", lambda r: f"session opened for user svc_monitor from {_ip(r)}"),
    (8, "bmc", lambda r: f"session closed for user svc_monitor from {_ip(r)}"),
    (6, "pdu", lambda r: f"outlet {r.randint(1, 24)} current {r.uniform(0.4, 4.8):.1f} A within limit"),
    (3, "sw", lambda r: f"Interface Ethernet1/{r.randint(1, 48)} link down"),
    (2, "bmc", lambda r: f"SEL log {r.randint(10, 90)}% full"),
]


def generate(hours: int = 6, seed: int = 52, incident_at: int = 4 * 3600 + 20 * 60) -> list[str]:
    rng = random.Random(seed)
    pools = {"bmc": [h for h in HOSTS if "bmc" in h], "sw": ["core-sw1", "core-sw2"], "pdu": ["pdu-a3", "pdu-b3"]}
    weights = [w for w, _, _ in ROUTINE]
    lines: list[tuple[int, str]] = []
    for sec in range(0, hours * 3600, 60):
        for host in pools["bmc"]:
            # heartbeat every 5 minutes, except r13's BMC which hangs at the incident
            if sec % 300 == 0 and not (host == "r13-bmc" and sec >= incident_at):
                lines.append((sec, f"{host} heartbeat seq={sec // 300} ok"))
        for _ in range(rng.choice([4, 5, 5, 6])):
            _, pool, fn = rng.choices(ROUTINE, weights)[0]
            host = rng.choice(pools[pool])
            if host == "r13-bmc" and sec >= incident_at:
                continue
            lines.append((sec + rng.randint(0, 59), f"{host} {fn(rng)}"))
        if incident_at <= sec < incident_at + 25 * 60:
            # PSU fault on rack 13: brand-new error template, plus fans spinning up on the neighbours
            for _ in range(rng.randint(2, 4)):
                lines.append((sec + rng.randint(0, 59), f"r13-bmc PSU2 input voltage {rng.randint(150, 175)} V out of range, failing over to PSU1"))
            for _ in range(rng.randint(3, 6)):
                h = rng.choice(["r12-bmc", "r14-bmc"])
                lines.append((sec + rng.randint(0, 59), f"{h} fan FAN{rng.randint(1, 6)} speed {rng.randint(12500, 14000)} RPM ok"))
            if rng.random() < 0.5:
                lines.append((sec + rng.randint(0, 59), f"pdu-a3 outlet {rng.randint(13, 16)} current {rng.uniform(9.5, 11.5):.1f} A above warning threshold"))
    lines.sort()
    return [f"{_ts(s)} {m}" for s, m in lines]


if __name__ == "__main__":
    out = Path(__file__).resolve().parent.parent / "data" / "syslog.txt"
    out.write_text("\n".join(generate()) + "\n")
