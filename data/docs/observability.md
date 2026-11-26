# Observability

## Logs
Services log structured JSON to stdout. Logs are shipped to Datadog and retained for 15 days. Never log PII such as emails, card numbers or access tokens.

## Metrics and alerts
Each service exposes Prometheus metrics on `/metrics`. Every service must have alerts for error rate, p95 latency and saturation. Alert definitions live in the `monitoring/` folder of the monorepo and are reviewed like code.

## Tracing
Distributed tracing uses OpenTelemetry with Datadog APM. Propagate the `traceparent` header on all outbound calls.

## SLOs
Tier-1 services target 99.9% monthly availability and p95 latency below 300 ms.
