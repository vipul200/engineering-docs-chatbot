# API Standards

## Style
Public APIs are REST over HTTPS with JSON bodies and are versioned in the path (`/v1/...`). Internal service-to-service calls use gRPC.

## Authentication
External clients authenticate with OAuth 2.0 client-credentials; tokens expire after 1 hour. Internal services use mTLS issued by the service mesh (Istio).

## Rate limits
The default public rate limit is 100 requests per second per API key, with bursts up to 200. Exceeding it returns HTTP 429 with a `Retry-After` header.

## Errors
Error responses use the shape `{"error": {"code": "...", "message": "...", "request_id": "..."}}`. Always include the `request_id` when reporting a bug.

## Pagination
List endpoints use cursor pagination with `limit` (max 100) and `cursor` parameters.
