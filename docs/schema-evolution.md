# Schema evolution

Input rules carry a `schema_version`, and the entire canonical rules document contributes to the run identity. Changing mappings, required fields, thresholds, or time semantics therefore creates a separate run rather than reusing an incompatible checkpoint.

Safe additive evolution:

1. Add an optional field to ingestion and the typed model.
2. Add a new PostgreSQL migration; never edit an applied migration.
3. Increment `schema_version` and add fixtures for old and new exports.
4. Deploy code and migration before producers require the field.
5. Observe quarantine and dimension scores before making the field required.

Breaking changes should use a parallel schema version and an explicit backfill. Migration checksums stop changed historical SQL from running unnoticed. This project supports a fixed ticket shape; a production implementation may add version-specific adapters and a schema registry.
