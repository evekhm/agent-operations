import functools
import logging
import os
from typing import Optional

import google.auth
from opentelemetry import trace
from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
from opentelemetry.instrumentation.google_genai import GoogleGenAiSdkInstrumentor

def get_tracer():
    return trace.get_tracer(__name__)

def init_tracer(project_id: Optional[str] = None):
    """Initialize Cloud Trace exporter."""
    if project_id is None:
        project_id = os.getenv('PROJECT_ID')
        if not project_id:
            _, project_id = google.auth.default()

    try:
        from opentelemetry.propagate import set_global_textmap
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        
        # Setup Global Tracer Provider
        tracer_provider = TracerProvider()
        trace.set_tracer_provider(tracer_provider)
        
        # Cloud Trace Exporter
        cloud_exporter = CloudTraceSpanExporter(project_id=project_id)
        span_processor = BatchSpanProcessor(cloud_exporter)
        tracer_provider.add_span_processor(span_processor)

        # Instrument Google Gen AI SDK
        try:
            GoogleGenAiSdkInstrumentor().instrument()
        except Exception as e:
            logging.warning(f"Failed to instrument Google Gen AI SDK: {e}")

        # Instrument SQLite if used
        # SQLite3Instrumentor().instrument()
        
        logging.info(f"✓ OpenTelemetry tracing enabled for project: {project_id}")
        return trace.get_tracer(__name__)
        
    except Exception as e:
        logging.error(f"Failed to initialize OpenTelemetry: {e}")
        # Return a no-op tracer so execution can continue
        return trace.get_tracer(__name__)

def setup_telemetry(project_id: Optional[str] = None):
    """Wrapper for init_tracer to maintain backward compatibility."""
    return init_tracer(project_id)

# Tool stats registry
# Format: {tool_name: {"calls": 0, "errors": 0, "durations": [], "last_args": None}}
_TOOL_STATS = {}

def get_tool_stats():
    """Get the current tool usage statistics."""
    return _TOOL_STATS

def trace_span(name_override=None):
    """
    Decorator to manually wrap functions in a trace span and track usage stats.
    Supports both sync and async functions.
    
    Args:
        name_override: Optional name for the span. If None, uses module.function_name.
    """
    def decorator(func):
        import inspect
        
        # Common setup for span name and stats registration
        module_name = func.__module__
        qual_name = func.__name__
        span_name = name_override or f"{module_name}.{qual_name}"
        report_name = qual_name
        
        # Initialize stats if needed
        if report_name not in _TOOL_STATS:
            _TOOL_STATS[report_name] = {
                "calls": 0, 
                "errors": 0, 
                "durations": [],
                "description": func.__doc__.strip().split('\n')[0] if func.__doc__ else "No description"
            }

        if inspect.iscoroutinefunction(func):
            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                tracer = get_tracer()
                import time
                start_time = time.time()
                error_occurred = False
                
                with tracer.start_as_current_span(span_name) as span:
                    try:
                        return await func(*args, **kwargs)
                    except Exception as e:
                        error_occurred = True
                        span.record_exception(e)
                        span.set_status(trace.Status(trace.StatusCode.ERROR))
                        raise e
                    finally:
                        duration = time.time() - start_time
                        _TOOL_STATS[report_name]['calls'] += 1
                        _TOOL_STATS[report_name]['durations'].append(duration)
                        if error_occurred:
                            _TOOL_STATS[report_name]['errors'] += 1
            return wrapper
        else:
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                tracer = get_tracer()
                import time
                start_time = time.time()
                error_occurred = False
                
                with tracer.start_as_current_span(span_name) as span:
                    try:
                        return func(*args, **kwargs)
                    except Exception as e:
                        error_occurred = True
                        span.record_exception(e)
                        span.set_status(trace.Status(trace.StatusCode.ERROR))
                        raise e
                    finally:
                        duration = time.time() - start_time
                        _TOOL_STATS[report_name]['calls'] += 1
                        _TOOL_STATS[report_name]['durations'].append(duration)
                        if error_occurred:
                            _TOOL_STATS[report_name]['errors'] += 1
            return wrapper
            
    return decorator
