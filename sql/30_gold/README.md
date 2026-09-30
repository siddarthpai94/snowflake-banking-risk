# sql/30_gold: canonical banking model (F2, Thursday)

Next step. Builds `GOLD.PARTY`, `PARTY_SOURCE_RECORD`, `HOUSEHOLD`, `ACCOUNT`, `LOAN`, `TRANSACTION`, `ALERT` and `BRANCH` as dynamic tables. It applies the expressions in `config/mappings/core_*.yaml` and joins to `SILVER.PARTY_XREF` for `party_id`. Every row keeps `source_file` and `source_row`. See `docs/spec.md` for keys and definitions.

End-of-day proof from the build plan: one query returns a single customer across both cores with their accounts, loans and alerts.
