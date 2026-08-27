# Cloudflare Integration Plan

Cloudflare is a suitable edge layer for Digital Twin, but the current account contains existing resources that appear to belong to other systems. No destructive or mutating Cloudflare operation was performed.

## Account inventory

| Resource | Current finding | Decision |
|---|---|---|
| Zones | No zones returned for the account | DNS/custom-domain work requires a domain or zone to be added first |
| R2 | Existing bucket `omnis-assets` | Do not reuse without explicit confirmation; create a dedicated private bucket for model artifacts and exports |
| Workers | Existing scripts `edge-cortex`, `midas-engine`, `omnis-ingest-cortex`, `omnis-oracle-brain`, `omnis-sentinel-guard`, and `omnis-singularity-core` | Do not modify; create a dedicated Digital Twin Worker only after a name and deployment approval are confirmed |
| Queues | Worker inventory indicates queue handlers, but no queue resource was modified or assumed | Use a dedicated queue for training and connector ingestion after resource discovery and approval |

## Recommended role in the architecture

Cloudflare should sit in front of the web and API origins for TLS, caching of non-sensitive static assets, rate limiting, and edge request controls. R2 is appropriate for private model artifacts, export packages, and encrypted connector snapshots when accessed through short-lived signed URLs or an authenticated Worker. Workers Queues can decouple connector ingestion and training-job dispatch from the FastAPI request path. Lifecycle rules should automatically expire temporary exports and raw payloads.

Cloudflare should not receive raw personal data by default. The Worker should validate an authenticated request, attach a request ID, enforce size and content-type limits, and forward only the minimum required payload to the API or queue. Logs must be redacted. Existing account resources must remain untouched until their ownership and purpose are confirmed.

## Safe next step

The repository is ready for a Cloudflare-specific Worker package containing private R2 upload/download handlers, queue message schemas, and origin-routing configuration. Deploying or creating those resources requires explicit approval of the resource names and may require a domain, queue, or bucket creation decision. The existing `omnis-assets` bucket and `omnis-*` Workers should not be used as Digital Twin infrastructure without confirmation.

## Reference

Cloudflare documents server-side generation of short-lived R2 presigned URLs for browser uploads and private object access: <https://developers.cloudflare.com/r2/objects/upload-objects/>. The current implementation should use this pattern rather than public buckets for sensitive artifacts.
