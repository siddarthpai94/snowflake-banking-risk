# coco_skills/onboard_core: onboard a new core (F9, Saturday)

A packaged CoCo skill that:

1. reads a new core's Bronze schema;
2. proposes a mapping to the canonical model;
3. generates the load SQL and data-quality tests;
4. runs them.

**Target output format:** `config/mappings/core_a.yaml` and `core_b.yaml` are hand-written examples of the mapping the skill must produce.

**Test fixture:** `data/out/demo/core_c/` is a third core the skill has never seen. It uses different column names (camelCase), date formats (`YYYY/MM/DD`, epoch seconds), ID formats (`C-` + 7 digits) and a dashed tax token. 300 of its 3,000 customers are also Core A customers (see `ground_truth/person_map.csv.gz`, core `core_c`), so the onboarding result can be scored.

Acceptance from the build plan: the skill onboards Core B from scratch in the demo, and the same skill runs on Core C.
