# Shipping Document Classifier

Sort scanned shipping paperwork (bills of lading, commercial invoices, packing lists, customs entries) into the right queue with a naive Bayes classifier written from scratch. Short or ambiguous scans go to a human instead of being misfiled.

```text
$ python -m doc_classifier
train 120 docs (6% OCR noise), test 60 docs (10%), stress 100 docs (20%)

features          5-fold CV    test  stress
words + bigrams      100.0%   98.3%   99.0%
+ char 4-grams       100.0%   98.3%  100.0%

confusion (rows = true, cols = predicted)
         BOL   INV   CUS    PL  precision recall
BOL       14     0     0     1       1.00   0.93
INV        0    15     0     0       1.00   1.00
CUS        0     0    15     0       1.00   1.00
PL         0     0     0    15       0.94   1.00

routing (confidence >= 0.9 and >= 8 known words): 97% auto-filed at 100.0% accuracy, 2 to review
  review pac-99-9   guess PL   conf 1.00, 6 known words  (actually PL)
  review bil-99-3   guess PL   conf 1.00, 5 known words  (actually BOL)

most telling features
  BOL  for, order, voyage, consignee, notify, said
  INV  amount, bank, is, unit, due, we
  CUS  entry, fee, fee_usd, duty, value, customs
  PL   w, w_kg, kg_total, cartons, g, no_0
```

## Why it matters
A mid-size importer or 3PL receives every container as a packet of four to six documents, emailed as one PDF or scanned at the dock. Someone has to split and file each page: the BOL to transport, the invoice to AP, the packing list to receiving, and the customs entry to the broker team. At 300 containers a week and 30 seconds a page, that's about 12 hours of clerical work a week. A misfiled customs entry can also hold a container in port and run up demurrage at $150-300 per day. In the sample, the classifier auto-files 97% of noisy scans with no errors, and the two pages it can't be sure of go to review. One of those two would have been misfiled, even though the model gave it 1.00 confidence.

Why naive Bayes and not an LLM: these documents are formulaic, labels are cheap to collect from existing filing, and the classifier trains in milliseconds, runs on a dock PC, costs nothing per page and explains itself (the "most telling features" list). An LLM fits better as a second stage that extracts fields once the type is known.

## Architecture
```
scan text ──► normalize(): lowercase, numbers → "0" (keep layout, drop values)
                  ▼
           featurize(): words + word bigrams + char 4-grams (OCR-robust)
                  ▼
           NaiveBayes: log P(class) + Σ count × log P(feature | class), Laplace α=0.5
                  ▼                     unseen features ignored, softmax with temperature
           Prediction(label, confidence, evidence = known words)
                  ▼
           confidence ≥ 0.90 AND evidence ≥ 8 ──► auto-file
                  └── otherwise ───────────────► review queue
```
- **Numbers become a placeholder token.** Weights, HS codes and invoice amounts are pure noise as values, but "0 kg" and "USD 0" patterns are strong signals of document type.
- **Char n-grams buy OCR robustness.** "Componennts" loses its word feature but keeps most of its 4-grams. On the 20%-noise stress set this closes the last 1% gap. On clean text it makes no difference, which is the expected behavior.
- **Confidence alone is not a safe gate.** Naive Bayes treats a word, its bigrams and its n-grams as independent evidence, so posteriors pile up at 0.99+. The misfiled page in the sample was a five-word fragment scored at 1.00. Routing therefore also requires a minimum amount of evidence (known words), which is an operational rule anyone on the dock can understand.
- **Reproducible synthetic data.** `docgen.py` builds seeded documents with realistic layouts, shared fields across types (ports, vessels and invoice numbers appear on several), scan fragments and OCR errors (0/O, 1/l, dropped and doubled letters).

## Run
```bash
pip install pytest
python -m pytest -q                       # 13 tests
python -m doc_classifier                  # train, evaluate, show routing and features
python -m doc_classifier scan1.txt scan2.txt
python -m doc_classifier.docgen           # regenerate data/train.jsonl and data/test.jsonl
```

## Next steps
- Split multi-document PDFs page by page and classify each page together with its neighbors, since a packing list's page 2 looks like page 1.
- Add an LLM extraction step per document type (BOL number, container, HS codes) and validate it against the classifier's label.
- Retrain weekly from reviewer corrections and track per-class recall drift.
