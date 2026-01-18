"""Production-grade moderation subsystem.

Self-contained modules:
- config (draft/published + validation)
- rule engine (deterministic)
- action engine (safe execution + retries + idempotency)
- audit logging (correlation IDs)

Designed to coexist with existing/legacy commands.
"""
