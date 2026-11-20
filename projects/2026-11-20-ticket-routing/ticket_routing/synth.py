"""Seeded generator of realistic IT tickets: templates x slot fillers, with overlap between queues."""
from __future__ import annotations

import csv
import random
from pathlib import Path

SLOTS = {
    "app": ["Outlook", "Teams", "Salesforce", "SAP", "Excel", "Zoom", "Workday", "Jira", "the ERP", "Chrome"],
    "device": ["laptop", "monitor", "docking station", "keyboard", "headset", "printer", "desk phone", "badge reader"],
    "site": ["Building 2", "the Austin office", "warehouse DC3", "the 4th floor", "the Denver branch", "HQ"],
    "person": ["new hire", "contractor", "my manager", "an intern", "the temp in finance"],
    "when": ["since this morning", "after the update", "again", "for 2 days", "intermittently", "since yesterday"],
}

TEMPLATES = {
    "network": [
        "wifi keeps dropping in {site} {when}", "VPN disconnects every few minutes {when}",
        "cannot reach shared drive, network path not found", "internet is very slow in {site}",
        "no network connection on my {device} at {site}", "VPN connects but cannot reach internal sites",
        "ethernet port at my desk is dead", "packet loss on video calls in {site}", "DNS not resolving internal hostnames {when}",
        "{app} times out, everything else online is slow too",
    ],
    "access": [
        "locked out of my account {when}", "need access to the {app} finance module", "password reset for {person}",
        "MFA prompt not arriving on my phone", "please create accounts for a {person} starting monday",
        "permission denied opening the shared drive folder", "remove access for a {person} who left",
        "cannot log in to {app}, says invalid credentials", "need admin rights to install software",
        "SSO loop when signing in to {app} {when}", "VPN says my account is not authorized",
    ],
    "hardware": [
        "{device} will not turn on", "my {device} screen is flickering {when}", "{device} is broken, need a replacement",
        "laptop battery drains in an hour", "printer on {site} is jammed again", "need a second monitor for a {person}",
        "{device} making a clicking noise", "spilled coffee on my laptop keyboard", "docking station not detecting {device}",
        "laptop overheating and shutting down {when}",
    ],
    "software": [
        "{app} crashes when I open attachments", "{app} keeps freezing {when}", "need {app} installed on my laptop",
        "{app} shows an error after the update", "macro in Excel stopped working {when}", "{app} is not syncing {when}",
        "license expired for {app}", "{app} plugin missing after reinstall", "cannot export report from {app}, error 500",
        "{app} very slow to open files",
    ],
    "security": [
        "got a suspicious email asking for my password", "clicked a link in a phishing email",
        "my laptop was stolen at {site}", "unknown login alert for my account from another country",
        "{app} asking me to approve MFA requests I did not make", "found a USB drive in the parking lot",
        "pop-up says my files are encrypted", "someone is sending emails from my account",
        "lost my badge at {site}", "received an invoice email with a strange attachment",
    ],
}

# Phrasings never seen in training: the test set uses these to measure generalization, not memorization.
HOLDOUT = {
    "network": ["Teams calls keep cutting out and pages load slowly at {site}", "can't connect to the corporate wifi network",
                "remote desktop drops connection from home over VPN", "shared drive mapping lost, network unreachable"],
    "access": ["forgot my password and the reset link has expired", "new contractor needs a login for {app}",
               "I don't have permission to edit the finance folder", "account disabled after too many attempts"],
    "hardware": ["the {device} I was issued has a cracked screen", "laptop fan is loud and it gets very hot",
                 "requesting a replacement charger for my laptop", "{device} stopped working after I dropped it"],
    "software": ["{app} won't start after last night's patch", "please install Visio, need it for a project",
                 "{app} gives an error every time I save", "add-in disappeared from {app} toolbar"],
    "security": ["I think I entered my password on a fake login page", "strange text asking me to approve a sign-in",
                 "my phone with company email on it was stolen", "email from the CEO asking me to buy gift cards"],
}
# Tickets that belong to no IT queue; a good router sends them to human triage instead of guessing.
OFF_TOPIC = ["the coffee machine on the 3rd floor is broken", "when is the open enrollment deadline for benefits",
             "can facilities fix the air conditioning in room 204", "who approves my travel expense report",
             "parking garage gate is stuck open", "need a quote for 500 branded water bottles"]

PREFIXES = ["", "", "hi, ", "urgent: ", "hello team - ", "pls help, ", "re: "]
SUFFIXES = ["", "", ". thanks", ". this is blocking me", ". can someone look", " asap", ". ticket from {site}"]


def fill(text: str, rng: random.Random) -> str:
    for k, vals in SLOTS.items():
        while "{" + k + "}" in text:
            text = text.replace("{" + k + "}", rng.choice(vals), 1)
    return text


def generate(n_per_queue: int, seed: int, holdout_share: float = 0.0, off_topic: int = 0) -> list[dict]:
    rng = random.Random(seed)
    rows = []

    def add(queue: str, template: str) -> None:
        text = rng.choice(PREFIXES) + fill(template, rng) + fill(rng.choice(SUFFIXES), rng)
        rows.append({"id": f"T{seed}{len(rows):04d}", "queue": queue, "text": text})

    for queue, temps in TEMPLATES.items():
        for _ in range(n_per_queue):
            add(queue, rng.choice(HOLDOUT[queue] if rng.random() < holdout_share else temps))
    for _ in range(off_topic):
        add("triage", rng.choice(OFF_TOPIC))
    rng.shuffle(rows)
    return rows


def write(path: Path, rows: list[dict]) -> None:
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id", "queue", "text"])
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    out = Path(__file__).resolve().parent.parent / "data"
    write(out / "train.csv", generate(40, 1))
    write(out / "test.csv", generate(16, 2, holdout_share=0.5, off_topic=8))
