# Audit Backlog

These findings remain active for the next review pass.

6. Align the real `config/catalog.yaml` schema with the code paths that still expect `price` or `id`.
7. Use Supabase pgvector as the single vector store architecture and remove any remaining duplicate runtime/docs references.
8. Make tool-triggered escalation pause the graph state, not just notify Telegram.
9. Reject Twilio webhook traffic in production if `TWILIO_AUTH_TOKEN` is missing.
10. Keep repairing the test suite and settings isolation until the full suite is reliable.
11. Align `.env.example` with `config.settings.Settings`.
12. Unify `pyproject.toml` and `requirements.txt` around one dependency source of truth.
13. Redact PII from logs and prints.
14. Allow explicit CRM field clearing with `None` vs empty-string semantics.
15. Replace production `create_all` startup behavior with versioned migrations.
