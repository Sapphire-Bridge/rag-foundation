from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.responses import Response

http_requests_total = Counter("http_requests_total", "HTTP requests", ["method", "endpoint", "status"])
http_request_duration = Histogram("http_request_duration_seconds", "HTTP request duration", ["method", "endpoint"])
gemini_calls_total = Counter("gemini_api_calls_total", "Gemini API calls", ["operation", "status"])
gemini_latency = Histogram("gemini_api_latency_seconds", "Gemini API latency", ["operation"])
token_usage_total = Counter("llm_tokens_total", "LLM token usage", ["model", "type"])


async def metrics_endpoint():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
