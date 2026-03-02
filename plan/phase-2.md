# Phase 2: Config schema and Claude API prototype (before LLM pipeline)

Define the full config (TOML) and validate LLM extraction in isolation before wiring Claude into the pipeline. Ensures config is specified and the extraction step is viable.

---

## Detailed steps

### 1. Config schema

- Write the full **config spec** in TOML (see [reference.md#config-schema](reference.md#config-schema-define-before-implementing)).
- Include: search (location, price_max, price_min, bedrooms, bathrooms, category), bright_data (dataset_id, options), claude (model, timeout_seconds, extract_fields), paths (db, output, config_file), dedup (normalize_address, optional suffix mappings), run_status (store, optional status_file).
- Commit the schema file to the repo (e.g. `config_schema.toml` in repo root or as documented in reference).
- **Do not** implement config loading or parsing yet; this phase is spec-only for config. (Phases 0–1 use env/minimal config; full config loading can be added in Phase 3 when wiring Claude.)

### 2. Claude API prototype

- Build a **standalone script** (e.g. `scripts/extract_listing_prototype.py` or similar) that:
  - Takes **sample listing text** as input (from a file or hardcoded string; 1–3 example listings).
  - Calls the **Claude API** with a fixed prompt that requests structured extraction for the fields in [features.md](features.md) (washer/dryer, renter-paid fees, availability, pet policy, parking, lease length, deposit, etc.).
  - Parses the API response and validates that the **output shape** matches the expected schema (e.g. required keys present, types reasonable).
  - Measures **latency** (time from request to parsed response) and logs or prints it.
- Use API key from env (e.g. `ANTHROPIC_API_KEY`); do not hardcode.
- Confirm the script runs successfully against the Claude API and that response format is stable enough to rely on in the pipeline.

### 3. Document findings

- Note the Claude model name and any prompt constraints (length, format) for use in Phase 3.
- If latency or rate limits are a concern, document mitigations (e.g. batch size, timeout) for the main pipeline.

---

## Requirements to pass before moving to Phase 3

- [ ] **Config schema** is written in TOML and committed to the repo; all sections (search, bright_data, claude, paths, dedup, run_status) are specified with types/defaults or comments.
- [ ] **Claude prototype script** exists, runs against sample listing text, and calls the Claude API successfully.
- [ ] **Output validation** passes: the script validates that the API response conforms to the extraction schema (required fields present; no crash on parse).
- [ ] **Latency** has been measured and recorded; team accepts that the LLM step is viable for the intended run frequency (schedule: every 6–24 hours per [features.md](features.md)).
- [ ] **No config loading** has been implemented yet in the main pipeline; config is spec-only.

When all checkboxes are satisfied, proceed to [phase-3.md](phase-3.md).
