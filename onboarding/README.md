# onboarding: onboard a new core (F9), without AI

A rule-based tool (no AI) with a runbook for the person who reviews its output (`RUNBOOK.md`). Given a new core's extract files, it:

1. **profiles** every column from a reproducible random sample (dates in four formats, epoch seconds, ISO timestamps, money, cents, IDs, UUIDs, tax tokens with any prefix or separators, phones, ZIPs, states, emails, "LAST, FIRST" names, "City, ST 12345" fields, code sets);
2. **classifies** each file as customers, accounts or transactions (best score first, never first come);
3. **maps** each canonical field by name (abbreviations such as `NM`, `DT`, `TKN`, camelCase and synonyms such as family/given/postal/mobile) **and** by content: a column whose content does not fit a field is never chosen;
4. **links** files by value overlap (100% of `accounts.custId` values are `customers.custId` values), not by name;
5. **translates** code values with a reviewed vocabulary (CHK, SVG, EFTIN, ...); anything unknown goes on a review list for a person;
6. **writes** `mapping.yaml` (the format of `config/mappings/core_*.yaml`, plus confidence and review items), `10_bronze.sql`, `20_canonical.sql` and `30_dq_tests.sql`.

```
python -m onboarding.onboard --core core_c --files data/out/demo/core_c --out build/onboard/core_c
python -m onboarding.evaluate --data data/out/demo
```

## Results (`evaluate.py`, demo data; the holdout seed gives the same)

| Test | Result |
| --- | --- |
| **Core C, never mapped before**: customers linked to Core A by the generated tax token and date of birth | **297 of 300** true links, **0 false links** (holdout: 296 of 300, 0 false). The misses are Core A records with no date of birth (injected data-quality issue); their tax tokens match exactly |
| **Core B from scratch**, generated vs hand-written mapping, value by value over 18,000 customers | 100% on first name, last name, birth date, tax token, city, state, phone, email; ZIP 99.33% |
| **Core A from scratch**, same comparison over 32,000 customers | 100% on every field except birth date 99.94% |
| Generated data-quality tests vs the injected issues | Found all five kinds with exact counts: 10 duplicate keys, 20 future birth dates, 250 missing birth dates, 120 invalid ZIPs, 40 orphan accounts |
| Items left for a person on Core C | Status codes `1, 2, 9` and channel `card` (unknowable without the source system's documentation), and no email or customer-type column |

The only disagreements with the hand-written mappings are the injected bad values: the hand-written Silver rules blank future birth dates and invalid ZIPs, while the generated mapping keeps the source value and its data-quality tests report it.

## Found and fixed while building it

- Sampling only the first rows missed `SVG` (all early Core C accounts are checking). The profile now samples across the whole file and keeps every distinct code.
- Files were assigned in alphabetical order, so `branches.csv` took the customer slot before `customers.csv` (score 1 vs 15). Assignment is now best score first.
- Organisations' names went into the person's surname on Core B (500 records). When a customer-type column exists, person names are left empty for organisations.

## Limits

- Customers, accounts and transactions are mapped; loans and alerts are recognised but mapped by hand.
- Code values outside the vocabulary need a person. That is deliberate: a guessed status code would silently misclassify accounts.
- Fields such as middle initial, suffix, organisation name and risk rating are not generated yet.
