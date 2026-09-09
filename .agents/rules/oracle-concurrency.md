---
trigger: "glob:**/connectors/oracle.py"
---

# Oracle Concurrency & Connection Pooling Standards

1. **UUID Temp Tables:** Temporary tables in `insert_into_table` MUST append a unique 8-character hexadecimal UUID suffix to prevent cross-process collisions during concurrent runs:
   ```python
   temp_table_name = f"TMP_{table_name[:12]}_{uuid.uuid4().hex[:8]}".upper()
   ```
2. **Engine Lifecycle & Pooling:** Do not dispose SQLAlchemy engines after individual queries. Use a cached engine factory (`@lru_cache(maxsize=8)`) with `pool_size=5`, `max_overflow=10`, and `pool_pre_ping=True`.
3. **Identifier Sanitization:** Validate table and column names against an allowed identifier regex (`^[A-Za-z0-9_]+$`) before formatting into dynamic `MERGE` SQL strings.
4. **Column Sizing:** Default long string fields (like `COMMENTS`, `WEB_LINK`, `ERROR_MSG`) to `VARCHAR2(4000)` to prevent `ORA-12899`.
