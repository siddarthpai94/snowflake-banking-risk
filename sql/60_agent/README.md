# sql/60_agent: audit log (F6)

`60_audit.sql` creates `AUDIT.QUESTION_LOG`: every question, the route and rule chosen, the reviewed question or tool used, the headline and citations. Written by `agent/answer.py:log_question`. See `agent/README.md`.
