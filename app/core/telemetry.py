import logging
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from app.config import settings

logger = logging.getLogger(__name__)


def setup_telemetry() -> None:
    """
    Initializes OpenTelemetry Tracer Provider and registers exporters and processors.
    Includes instrumentations for FastAPI, Redis, Celery, and SQLAlchemy.
    """
    if not settings.OTEL_EXPORTER_OTLP_ENDPOINT:
        logger.info("OTEL_EXPORTER_OTLP_ENDPOINT not set. Skipping OpenTelemetry configuration.")
        return

    try:
        # Create resource configuration identifying our microservice
        resource = Resource.create(
            attributes={
                "service.name": settings.OTEL_SERVICE_NAME,
                "environment": "development"
            }
        )

        provider = TracerProvider(resource=resource)
        
        # Setup OTLP gRPC exporter forwarding to Jaeger
        exporter = OTLPSpanExporter(
            endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT,
            insecure=True
        )
        
        processor = BatchSpanProcessor(exporter)
        provider.add_span_processor(processor)
        
        # Make provider globally accessible
        trace.set_tracer_provider(provider)
        
        logger.info("OpenTelemetry trace provider configured successfully.")
        
    except Exception as e:
        logger.error(f"Failed to initialize OpenTelemetry: {e}", exc_info=True)


def instrument_app_telemetry(app) -> None:
    """
    Wires up automated request/response tracing for FastAPI.
    """
    if not settings.OTEL_EXPORTER_OTLP_ENDPOINT:
        return
        
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor.instrument_app(app)
        logger.info("FastAPI OpenTelemetry instrumentation active.")
    except Exception as e:
        logger.warning(f"FastAPI OpenTelemetry instrumentation failed: {e}")


def instrument_workers_telemetry() -> None:
    """
    Wires up automated tracing for Celery worker processes.
    """
    if not settings.OTEL_EXPORTER_OTLP_ENDPOINT:
        return
        
    try:
        from opentelemetry.instrumentation.celery import CeleryInstrumentor
        CeleryInstrumentor().instrument()
        logger.info("Celery OpenTelemetry instrumentation active.")
    except Exception as e:
        logger.warning(f"Celery OpenTelemetry instrumentation failed: {e}")


def instrument_db_telemetry(engine) -> None:
    """
    Wires up tracing for SQLAlchemy DB queries.
    """
    if not settings.OTEL_EXPORTER_OTLP_ENDPOINT:
        return
        
    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        SQLAlchemyInstrumentor().instrument(engine=engine)
        logger.info("SQLAlchemy OpenTelemetry instrumentation active.")
    except Exception as e:
        logger.warning(f"SQLAlchemy OpenTelemetry instrumentation failed: {e}")
