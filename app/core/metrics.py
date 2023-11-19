from prometheus_client import Counter, Gauge, Histogram
from prometheus_fastapi_instrumentator import Instrumentator
from fastapi import FastAPI

# Custom Prometheus Metrics
ACTIVE_WS_CONNECTIONS = Gauge(
    "collabstream_active_websocket_connections",
    "Number of active WebSocket connections currently established in room servers",
    ["room_id"]
)

DOCUMENT_DELTAS_TOTAL = Counter(
    "collabstream_document_deltas_total",
    "Total number of operational transform deltas processed by the engine",
    ["room_id", "op_type"]
)

AI_ANALYSIS_TRIGGERS_TOTAL = Counter(
    "collabstream_ai_analysis_triggers_total",
    "Total number of debounced AI analysis streaming triggers",
    ["room_id"]
)

SNAPSHOTS_CREATED_TOTAL = Counter(
    "collabstream_snapshots_created_total",
    "Total number of document snapshots backed up to S3/MinIO",
    ["document_id"]
)

OT_CONCURRENT_CONFLICTS_TOTAL = Counter(
    "collabstream_ot_concurrent_conflicts_total",
    "Total number of concurrent edits that required operational transform revision adjustments",
    ["room_id"]
)


def instrument_app(app: FastAPI) -> None:
    """
    Auto-instruments FastAPI with Prometheus metrics,
    exposing the metrics under the `/metrics` endpoint.
    """
    # Create instrumentator with customized buckets
    instrumentator = Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        should_respect_env_var=False,
        metric_name="collabstream_http_requests",
        label_unhandled_exception_class=True
    )
    
    # Register instrumentation on FastAPI app
    instrumentator.instrument(app).expose(app, endpoint="/metrics")
