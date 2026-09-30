# Runbook: onboard a new core

For a data engineer. The mapping comes from a deterministic tool (`onboarding/onboard.py`, rules, no AI); a person reviews and decides every open item.

1. Put the new core's extract files (`.csv` or `.csv.gz`) in one folder, for example `data/out/demo/core_c/`, and upload them to `@BRONZE.RAW_STAGE/<core>/` (the loaders in `scripts/` do this).
2. Run the tool:
   `python -m onboarding.onboard --core <core> --files <folder> --out build/onboard/<core>`
3. Read `build/onboard/<core>/mapping.yaml`: the `review` list, every field with `level: medium` or `low`, and the `links` notes. Resolve each review item (for example unknown status codes) with the source system's owner and record the decision in the mapping.
4. Load and build in Snowflake:
   `snow sql -c default -f build/onboard/<core>/10_bronze.sql`
   `snow sql -c default -f build/onboard/<core>/20_canonical.sql`
5. Run the data-quality tests:
   `snow sql -c default -f build/onboard/<core>/30_dq_tests.sql`
   Rows marked `must be 0` must be 0 before the core feeds Gold. Rows marked `report` are data problems to raise with the source system's owner; they are reported, never hidden.

`python -m onboarding.evaluate --data data/out/demo` scores the tool on real data; see `onboarding/README.md`.
