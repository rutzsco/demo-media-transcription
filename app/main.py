from fastapi import FastAPI
from .routes.workflow import router as workflow_router
from .routes.status import router as status_router
import logging
from azure.monitor.opentelemetry.exporter import (
    AzureMonitorLogExporter,
    AzureMonitorMetricExporter,
    AzureMonitorTraceExporter,
)
from azure.monitor.opentelemetry import configure_azure_monitor
from opentelemetry._logs import set_logger_provider
from opentelemetry.metrics import set_meter_provider
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor, ConsoleLogExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import ConsoleMetricExporter, PeriodicExportingMetricReader
from opentelemetry.sdk.metrics.view import DropAggregation, View
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.semconv.resource import ResourceAttributes
from opentelemetry.trace import set_tracer_provider
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor

from dotenv import load_dotenv
import os

load_dotenv()
ai_connection_string = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
resource = Resource.create({ResourceAttributes.SERVICE_NAME: "demo-ai-flows-python"})

# Setup logging functions
# configure_azure_monitor()

# Instrumenting the requests library for OpenTelemetry tracing
RequestsInstrumentor().instrument()
def configure_tracer(exporter):
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(exporter))
    set_tracer_provider(tracer_provider)

def configure_logger(exporter):
    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(exporter))
    set_logger_provider(logger_provider)

    handler = LoggingHandler()
    #handler.addFilter(logging.Filter("semantic_kernel"))
    logger = logging.getLogger()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

def configure_metric(exporter):
    meter_provider = MeterProvider(
        metric_readers=[PeriodicExportingMetricReader(exporter, export_interval_millis=5000)],
        resource=resource,
        views=[
            View(instrument_name="*", aggregation=DropAggregation()),
            View(instrument_name="semantic_kernel*"),
        ],
    )
    set_meter_provider(meter_provider)

# Initialization logging based on connection string
if ai_connection_string:
    configure_tracer(AzureMonitorTraceExporter(connection_string=ai_connection_string))
    configure_logger(AzureMonitorLogExporter(connection_string=ai_connection_string))
    configure_metric(AzureMonitorMetricExporter(connection_string=ai_connection_string))
else:
    configure_tracer(ConsoleSpanExporter())
    #configure_logger(ConsoleLogExporter())
    #configure_metric(ConsoleMetricExporter())

# FastAPI app setup
app = FastAPI()
app.include_router(workflow_router)
app.include_router(status_router)
FastAPIInstrumentor.instrument_app(app)

