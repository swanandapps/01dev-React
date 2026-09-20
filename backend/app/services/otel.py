"""
OpenTelemetry tracing for the /chat request path → OTLP (local SigNoz).

Opt-in and non-fatal, mirroring tracing.py:
  - OTEL_EXPORTER_OTLP_ENDPOINT  → export spans over OTLP gRPC (e.g. SigNoz at
    http://localhost:4317). If unset, tracing is a NO-OP — spans still "created"
    but go nowhere, so prod without a collector is unaffected and never crashes.
  - OTEL_CONSOLE=true            → also print spans to stdout (local verification).

Additive: this is the first step of moving observability onto OTel as one open
standard. LangSmith and /quiz are untouched.
"""
import os

from opentelemetry import trace

_SERVICE = "the01dev-chat"
_initialized = False


def init_tracing() -> None:
    """Configure the global TracerProvider once (on app startup). No-op if unconfigured."""
    global _initialized
    if _initialized:
        return

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    console = os.getenv("OTEL_CONSOLE", "").lower() in ("1", "true", "yes")
    if not endpoint and not console:
        return  # opt-in: nothing configured → leave the default no-op provider

    try:
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter, SimpleSpanProcessor

        provider = TracerProvider(resource=Resource.create({"service.name": _SERVICE}))
        if endpoint:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True)))
        if console:
            provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
        trace.set_tracer_provider(provider)
        _initialized = True
        print(f"OTel: tracing enabled → {endpoint or 'console'} (service={_SERVICE})")
    except Exception as e:  # noqa: BLE001 — observability must never break the app
        print(f"OTel: init failed ({e}); tracing disabled")


def get_tracer():
    """Return the tracer. Emits real spans only if init_tracing configured a provider,
    otherwise the default no-op tracer (start_as_current_span becomes a cheap no-op)."""
    return trace.get_tracer("the01dev.chat")
