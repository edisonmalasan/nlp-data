"""
src/clean/ — the Stage 2 cleaning pipeline.

Implements DATA_CONTRACT.md sections 6, 7, 8 and 11:

    normalize.py   L0 -> L1 text rules, context assembly, dedup key
    dedup.py       exact and near duplicate removal
    spam.py        F1-F8 spam and low-value filters
    pii.py         anonymization
    pipeline.py    runs the chain and writes the exclusion ledger

Run it with:

    python src/clean/pipeline.py \\
        --pool       data/interim/comments_captured.csv \\
        --out        data/processed/candidate_pool.csv \\
        --ledger-out data/interim/exclusion_ledger.csv \\
        --report     data/interim/cleaning_report.json

Order matters and must not change:

    filter -> normalize -> dedup -> scrub

Deduplication runs before the train/dev/test split, always. If a duplicate
pair straddles the split, the model is evaluated on text it has already seen.
"""
