---
name: onboard-core
description: Onboard a new core banking system's extract files into the risk copilot. Profiles the files, maps them to the canonical model, generates Bronze load SQL, canonical views and data-quality tests, and lists what a person must review. Use when a new core, an acquired bank's system or a new extract arrives.
---

# Onboard a new core

The mapping is produced by a deterministic tool, `coco_skills/onboard_core/onboard.py` (rules, no AI). Do not write or change mappings by guessing: run the tool, show its output, and let a person decide every review item.

## Steps

1. Put the new core's extract files (`.csv` or `.csv.gz`) in one folder, for example `data/out/demo/core_c/`, and upload them to `@BRONZE.RAW_STAGE/<core>/` (the loader in `scripts/` does this).
2. Run the tool:
   `python -m coco_skills.onboard_core.onboard --core <core> --files <folder> --out build/onboard/<core>`
3. Show the person `build/onboard/<core>/mapping.yaml`: the `review` list, every field with `level: low` or `medium`, and the `links` notes. Stop and ask them to resolve each review item (for example unknown status codes). Record their decisions in the mapping file.
4. Load and build, in Snowflake:
   `snow sql -c default -f build/onboard/<core>/10_bronze.sql`
   `snow sql -c default -f build/onboard/<core>/20_canonical.sql`
5. Run the data-quality tests and show the result:
   `snow sql -c default -f build/onboard/<core>/30_dq_tests.sql`
   Rows marked `must be 0` must be 0 before the core feeds Gold. Rows marked `report` are data problems to raise with the source system's owner; do not hide them.
6. Record the run in `docs/coco_usage_log.md`.

## How good is it

`python -m coco_skills.onboard_core.evaluate --data data/out/demo` scores the tool on real data. See `coco_skills/onboard_core/README.md` for the results on Core A, Core B (compared with the hand-written mappings) and Core C (never mapped before).
