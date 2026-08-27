# Cloudflare Edge Gateway

This package is a dedicated, non-deployed Worker for the Digital Twin API. It forwards authenticated API traffic to the configured origin, adds request IDs, limits request bodies, handles CORS, disables caching, and avoids logging personal payloads. Configure the real web/API origins and deploy only after reviewing the account resources and approving a dedicated Worker name.

The R2 binding is intentionally commented out. Use a dedicated private bucket for model artifacts and exports; do not reuse the existing `omnis-assets` bucket without explicit ownership confirmation.
