# Observability Guide

## Metrics

- The backend exposes Prometheus metrics at `/metrics`; by default this endpoint is restricted to localhost in `backend/app/main.py`. In production, expose it only to your Prometheus/monitoring network (e.g., via internal load balancer or service mesh), never directly to the public internet.
- Key series:
  - `http_requests_total` / `http_request_duration_seconds`: request volume + latency.
  - `gemini_calls_total` / `gemini_latency_seconds`: upstream Gemini usage.
  - `rate_limit_hits_total`: implicit from 429 responses; add alerting around spikes.
- To enable scraping:
  - Kubernetes: add a `ServiceMonitor` pointing to the backend service/port.
  - Docker/VM: expose `/metrics` internally and let Prometheus scrape via static config.

## Logs

- Structured JSON logs (via `app/telemetry.py`) include:
  - `timestamp`, `level`, `message`
  - `correlation_id` (from `CorrelationIdMiddleware`)
  - `request metadata` (method, path, latency)
- Recommended pipeline:
  - Ship logs to Loki or Elasticsearch.
  - Index by `correlation_id` to stitch backend + frontend events.

## Dashboards (starter ideas)

| Panel | Description |
|-------|-------------|
| Request rate & latency | Plot `http_requests_total`/`http_request_duration_seconds` by endpoint. |
| Gemini call health | Success/error rate from `gemini_calls_total`. |
| Upload pipeline | Custom logs filtered on `upload_*` events show ingestion delays. |
| Redis availability | Alert on Redis connection failures logged by `rate_limit_middleware`. |

## Alerting

Set alerts for:

- HTTP 5xx rate exceeds 2% over 5 minutes.
- Redis unreachable or falling back to in-memory limiter.
- Gemeni error rate > 5% for 10 minutes.
- Database migrations failing at startup (`Security gate` errors).
- Custom business metrics (budget exhaustion events, stuck uploads).

## Keepalives & Streaming

- `STREAM_KEEPALIVE_SECS` controls the cadence of SSE comment frames to keep connections alive.
- Monitor `app/routes/chat.py` logs for `metadataFilter ignored` warnings as a signal of clients attempting unsupported filters.

## References

- Prometheus default dashboards: https://github.com/prometheus-community/awesome-prometheus-alerts
- Grafana Loki: https://grafana.com/oss/loki/
- Sample alert rules: store them in your infra repo and reference this document from README.
