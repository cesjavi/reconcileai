Schema is owned by Alembic (`apps/api/alembic`): 0001 (prototype, superseded) -> 0002 deterministic engine -> 0003 Evolus.

    cd apps/api && alembic upgrade head      # needs DATABASE_URL

Tables: reconciliation_batches, bank_transactions, system_deposits, match_candidates (partial unique indexes
guarantee one effective link per bank transaction / deposit), reconciliation_decisions, audit_events (hash-chained),
inference_logs, evolus_executions, agent_recommendations. Verified on SQLite only; PostgreSQL is untested.
