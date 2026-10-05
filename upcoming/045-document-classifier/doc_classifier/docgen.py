"""Seeded generator for synthetic, OCR-noisy shipping documents (so the sample data is reproducible)."""
from __future__ import annotations

import json
import random
from pathlib import Path

PORTS = ["Shanghai", "Ningbo", "Busan", "Rotterdam", "Hamburg", "Los Angeles", "Long Beach", "Savannah", "Houston", "Veracruz"]
COMPANIES = ["Acme Housewares Ltd", "Pacific Rim Textiles", "Northstar Tools Inc", "Delta Components GmbH",
             "Sunrise Furniture Co", "Blue Harbor Imports LLC", "Granite Supply Corp", "Lotus Electronics"]
GOODS = [("ceramic mugs", "6912.00"), ("cotton t-shirts", "6109.10"), ("cordless drills", "8467.21"),
         ("LED panels", "9405.42"), ("oak dining chairs", "9401.61"), ("USB-C cables", "8544.42"),
         ("stainless cookware", "7323.93"), ("yoga mats", "3926.90")]
CARRIERS = ["Maersk", "MSC", "CMA CGM", "Hapag-Lloyd", "ONE", "Evergreen"]
INCOTERMS = ["FOB", "CIF", "EXW", "DDP", "FCA"]


def _noise(text: str, rng: random.Random, rate: float) -> str:
    """Simulate OCR: drop, double or confuse characters (0/O, 1/l, 5/S)."""
    swaps = {"0": "O", "O": "0", "1": "l", "l": "1", "5": "S", "S": "5", "e": "c", "m": "rn"}
    out = []
    for ch in text:
        r = rng.random()
        if r < rate / 3:
            continue
        if r < 2 * rate / 3:
            out.append(swaps.get(ch, ch))
        elif r < rate:
            out.append(ch + ch)
        else:
            out.append(ch)
    return "".join(out)


def _items(rng: random.Random, k: int) -> list[tuple[str, str, int, float]]:
    return [(g, hs, rng.randint(50, 5000), round(rng.uniform(0.8, 60), 2)) for g, hs in rng.sample(GOODS, k)]


def bill_of_lading(rng: random.Random) -> str:
    shipper, consignee = rng.sample(COMPANIES, 2)
    pol, pod = rng.sample(PORTS, 2)
    items = _items(rng, rng.randint(1, 3))
    lines = [rng.choice(["BILL OF LADING", "OCEAN BILL OF LADING", "B/L"]) + f" No. {rng.choice(CARRIERS)[:3].upper()}{rng.randint(10**7, 10**8)}",
             f"Shipper: {shipper}", f"Consignee: {consignee}", rng.choice(["Notify party: same as consignee", f"Notify party: {rng.choice(COMPANIES)}"]),
             f"Vessel / voyage: {rng.choice(CARRIERS)} {rng.choice(['Aurora', 'Pioneer', 'Horizon'])} {rng.randint(100, 999)}E",
             f"Port of loading: {pol}", f"Port of discharge: {pod}",
             f"Container: {rng.choice(['MSKU', 'TGHU', 'CMAU'])}{rng.randint(10**6, 10**7)} seal {rng.randint(10**5, 10**6)}",
             f"{len(items) * rng.randint(10, 40)} packages said to contain:"]
    lines += [f"  {g}" for g, *_ in items]
    lines += [f"Gross weight {rng.randint(2000, 24000)} kg", rng.choice(["Freight prepaid", "Freight collect"]),
              rng.choice(["Shipped on board", "Received for shipment"]) + " in apparent good order and condition",
              f"Number of original B/Ls: {rng.choice(['THREE (3)', '3/3', 'ONE (1)'])}", "Signed for the carrier as agent"]
    return "\n".join(lines)


def commercial_invoice(rng: random.Random) -> str:
    seller, buyer = rng.sample(COMPANIES, 2)
    items = _items(rng, rng.randint(1, 4))
    total = sum(q * p for _, _, q, p in items)
    lines = [rng.choice(["COMMERCIAL INVOICE", "INVOICE", "Commercial Invoice"]) + f" #{rng.randint(1000, 99999)}",
             f"Seller: {seller}", f"Bill to: {buyer}", f"Terms of sale: {rng.choice(INCOTERMS)} {rng.choice(PORTS)}",
             f"Payment terms: {rng.choice(['Net 30', 'Net 60', 'T/T 30% deposit', 'L/C at sight'])}",
             f"Port of loading: {rng.choice(PORTS)}  Vessel: {rng.choice(CARRIERS)}",
             "Description            Qty     Unit price    Amount"]
    lines += [f"{g:<22} {q:>6}   USD {p:>8.2f}   USD {q * p:,.2f}" for g, _, q, p in items]
    lines += [f"Subtotal USD {total:,.2f}", f"Freight USD {rng.randint(800, 4000):,}", f"Total amount due USD {total * 1.04:,.2f}",
              f"Bank: {rng.choice(['HSBC', 'Citibank', 'Bank of China'])} SWIFT {rng.choice(['HSBCHKHH', 'CITIUS33', 'BKCHCNBJ'])}",
              "We certify this invoice is true and correct"]
    return "\n".join(lines)


def packing_list(rng: random.Random) -> str:
    shipper, consignee = rng.sample(COMPANIES, 2)
    items = _items(rng, rng.randint(1, 4))
    lines = [rng.choice(["PACKING LIST", "Packing List", "PACKING / WEIGHT LIST"]) + f" ref PL-{rng.randint(1000, 9999)}",
             f"Shipper: {shipper}", f"Ship to: {consignee}", f"Invoice no. {rng.randint(1000, 99999)}  Terms: {rng.choice(INCOTERMS)}", "Carton  Description            Pcs/ctn  Cartons  N.W. kg  G.W. kg  Dimensions cm"]
    c = 1
    for g, _, q, _ in items:
        cartons = max(1, q // rng.choice([12, 24, 48]))
        lines.append(f"{c}-{c + cartons - 1}  {g:<22} {rng.choice([12, 24, 48]):>4} {cartons:>8} {cartons * 9.5:>8.1f} {cartons * 10.8:>8.1f}  "
                     f"{rng.randint(30, 60)}x{rng.randint(30, 60)}x{rng.randint(20, 50)}")
        c += cartons
    lines += [f"Total cartons: {c - 1}", f"Total net weight {rng.randint(500, 9000)} kg", f"Total gross weight {rng.randint(600, 10000)} kg",
              f"Total volume {rng.uniform(5, 60):.2f} CBM", rng.choice(["Shipping marks: as per carton", "Marks: MADE IN CHINA", "Pallets: 0, floor loaded"])]
    return "\n".join(lines)


def customs_declaration(rng: random.Random) -> str:
    importer = rng.choice(COMPANIES)
    items = _items(rng, rng.randint(1, 3))
    lines = [rng.choice(["ENTRY SUMMARY CBP FORM 7501", "CUSTOMS DECLARATION", "Import Declaration / Entry Summary"]),
             f"Entry number: {rng.randint(100, 999)}-{rng.randint(10**6, 10**7)}-{rng.randint(0, 9)}",
             f"Importer of record: {importer}", f"Country of origin: {rng.choice(['CN', 'VN', 'KR', 'DE', 'MX'])}",
             f"Port of entry: {rng.choice(PORTS)}", f"Entry type: {rng.choice(['01 Consumption', '03 AD/CVD', '11 Informal'])}",
             f"Commercial invoice value USD {rng.randint(5000, 90000):,}  B/L {rng.choice(CARRIERS)[:3].upper()}{rng.randint(10**7, 10**8)}",
             "HTS number      Description            Entered value   Duty rate   Duty"]
    for g, hs, q, p in items:
        val = q * p
        rate = rng.choice([0.0, 2.5, 3.4, 6.5, 25.0])
        lines.append(f"{hs}.{rng.randint(10, 99)}   {g:<22} USD {val:>10,.0f}   {rate:>4}%   USD {val * rate / 100:,.2f}")
    lines += [f"Merchandise processing fee USD {rng.uniform(30, 600):.2f}", f"Harbor maintenance fee USD {rng.uniform(10, 300):.2f}",
              "Declarant certifies the statements herein are correct", f"Customs broker: {rng.choice(['Livingston', 'Expeditors', 'C.H. Robinson'])} filer code {rng.randint(100, 999)}"]
    return "\n".join(lines)


GENERATORS = {"bill_of_lading": bill_of_lading, "commercial_invoice": commercial_invoice,
              "packing_list": packing_list, "customs_declaration": customs_declaration}


def generate(n_per_class: int, seed: int, noise: float = 0.03) -> list[dict]:
    rng = random.Random(seed)
    docs = []
    for label, gen in GENERATORS.items():
        for i in range(n_per_class):
            text = gen(rng)
            lines = text.splitlines()
            r = rng.random()
            if r < 0.35:
                # a single scanned page of a multi-page packet: a short run of lines, often no title
                k = rng.randint(3, 5)
                start = rng.randint(1, max(1, len(lines) - k))
                lines = lines[start:start + k]
            elif r < 0.55:
                lines = lines[1:]  # title block cut off
            text = "\n".join(lines)
            docs.append({"id": f"{label[:3]}-{seed}-{i}", "label": label, "text": _noise(text, rng, noise)})
    rng.shuffle(docs)
    return docs


if __name__ == "__main__":
    out = Path(__file__).resolve().parent.parent / "data"
    for name, n, seed, noise in (("train", 30, 7, 0.06), ("test", 15, 99, 0.10)):
        with open(out / f"{name}.jsonl", "w") as f:
            for d in generate(n, seed, noise):
                f.write(json.dumps(d) + "\n")
