-- Score Silver entity resolution and data-quality checks against ground truth, in Snowflake.
-- Needs the EVAL schema (load with -WithEval). Compare with tests/results/er_eval_demo.json
-- (DuckDB pre-flight on the same data: 3,948 auto links, 0 false merges, 93 in review,
--  52 true links in review, 0 look-alikes merged, 440 of 440 DQ issues).
USE ROLE RISK_ADMIN;
USE WAREHOUSE RISK_WH;
USE DATABASE RISK_COPILOT;

WITH truth AS (SELECT 'core_a:' || "core_a_cif" AS a_id, 'core_b:' || "core_b_party_uuid" AS b_id, "tier" AS tier
                 FROM EVAL.GT_DUPLICATE_LINKS),
     look  AS (SELECT 'core_a:' || "core_a_cif" AS a_id, 'core_b:' || "core_b_party_uuid" AS b_id
                 FROM EVAL.GT_LOOKALIKE_PAIRS),
     auto  AS (SELECT a_id, b_id FROM SILVER.AUTO_LINKS),
     rev   AS (SELECT a_id, b_id FROM SILVER.MATCH_REVIEW_QUEUE),
     dq_sys AS (SELECT rule_id, record_key FROM SILVER.DQ_EXCEPTIONS),
     dq_gt  AS (SELECT "issue_type" AS rule_id, "record_key" AS record_key FROM EVAL.GT_DQ_ISSUES)
SELECT
    (SELECT COUNT(*) FROM truth)                                               AS true_links,
    (SELECT COUNT(*) FROM auto)                                                AS auto_links,
    (SELECT COUNT(*) FROM auto a JOIN truth t ON t.a_id = a.a_id AND t.b_id = a.b_id) AS auto_correct,
    (SELECT COUNT(*) FROM auto a LEFT JOIN truth t ON t.a_id = a.a_id AND t.b_id = a.b_id
      WHERE t.a_id IS NULL)                                                    AS false_merges,
    (SELECT COUNT(*) FROM rev)                                                 AS review_queue,
    (SELECT COUNT(*) FROM rev r JOIN truth t ON t.a_id = r.a_id AND t.b_id = r.b_id) AS true_links_in_review,
    (SELECT COUNT(*) FROM auto a JOIN look l ON l.a_id = a.a_id AND l.b_id = a.b_id) AS lookalikes_merged,
    (SELECT COUNT(*) FROM dq_sys)                                              AS dq_found,
    (SELECT COUNT(*) FROM dq_gt)                                               AS dq_injected,
    (SELECT COUNT(*) FROM dq_sys s JOIN dq_gt g ON g.rule_id = s.rule_id AND g.record_key = s.record_key) AS dq_injected_found,
    ROUND(100 * auto_correct / true_links, 2)                                  AS recall_auto_pct,
    ROUND(100 * (auto_correct + true_links_in_review) / true_links, 2)         AS recall_after_review_pct;
