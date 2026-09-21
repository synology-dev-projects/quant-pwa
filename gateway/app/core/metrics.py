"""
gateway/app/core/metrics.py - Prometheus Metrics Collectors for Quant AI Gateway
Exposes standard Prometheus metrics tracking:
- HTTP requests total (method, endpoint, status_code)
- HTTP request duration seconds histogram (method, endpoint)
- In-memory cache hits / misses total (cache_name)
- Active SSE stream connections gauge
- Active level alerts gauge
- Pipeline scrape duration seconds histogram (pipeline)
Zero external network calls, ultra-low latency (<0.1ms).
"""

from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

# 1. HTTP Request Metrics
REQUEST_COUNT = Counter(
    "quant_http_requests_total",
    "Total HTTP requests received by the gateway",
    ["method", "endpoint", "status_code"],
)

REQUEST_LATENCY = Histogram(
    "quant_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

# 2. In-Memory Cache Efficiency Metrics
CACHE_HITS = Counter(
    "quant_cache_hits_total",
    "Total in-memory cache hits",
    ["cache_name"],
)

CACHE_MISSES = Counter(
    "quant_cache_misses_total",
    "Total in-memory cache misses",
    ["cache_name"],
)

# 3. Active Real-Time Gauges
ACTIVE_SSE_CONNECTIONS = Gauge(
    "quant_active_sse_connections",
    "Active SSE stream connections",
)

ACTIVE_ALERTS_COUNT = Gauge(
    "quant_active_alerts_total",
    "Active proximity level alerts tracked today",
)

# 4. Pipeline Execution Metrics
SCRAPE_DURATION = Histogram(
    "quant_pipeline_scrape_duration_seconds",
    "Pipeline scrape or execution duration in seconds",
    ["pipeline"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
)


def get_metrics_payload() -> bytes:
    """Returns the latest Prometheus formatted metrics payload."""
    return generate_latest()
