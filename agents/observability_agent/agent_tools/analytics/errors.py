from collections import Counter, defaultdict
import json
import logging
from google.cloud import bigquery
from ...utils.common import AnalysisEncoder
from ...utils.bq import execute_bigquery
from ...utils.time import parse_time_range
from ...config import PROJECT_ID, DATASET_ID, LOGS_VIEW_ID, get_table_list
from ...utils.telemetry import trace_span
from ...utils.caching import cached_tool

logger = logging.getLogger(__name__)

@trace_span()
@cached_tool()
async def classify_errors_by_type(
    time_range: str = "24h"
) -> str:
    """
    Classify errors into categories: QUOTA, TIMEOUT, PERMISSION, MODEL, TOOL.
    
    Provides structured error breakdown for H13 hypothesis analysis.
    
    Args:
        time_range: Time range to analyze
        
    Returns:
        JSON with error classification and counts
    """
    logger.info(f"[TOOL CALL-classify_errors_by_type] time_range={time_range}")
    
    try:
        time_range_dict = json.loads(parse_time_range(time_range))
        start_time, end_time = time_range_dict['start_date'], time_range_dict['end_date']
        
        # Query logs with error severity
        query = f"""
        SELECT
            status,
            CASE
                WHEN LOWER(error_message) LIKE '%quota%' OR LOWER(error_message) LIKE '%rate limit%' THEN 'QUOTA_EXCEEDED'
                WHEN LOWER(error_message) LIKE '%timeout%' OR LOWER(error_message) LIKE '%deadline%' THEN 'TIMEOUT'
                WHEN LOWER(error_message) LIKE '%permission%' OR LOWER(error_message) LIKE '%unauthorized%' OR LOWER(error_message) LIKE '%403%' THEN 'PERMISSION_DENIED'
                WHEN LOWER(error_message) LIKE '%model%' OR LOWER(error_message) LIKE '%generation%' OR LOWER(error_message) LIKE '%500%' THEN 'MODEL_ERROR'
                WHEN LOWER(error_message) LIKE '%tool%' OR LOWER(error_message) LIKE '%function%' THEN 'TOOL_ERROR'
                ELSE 'OTHER'
            END as error_type,
            COUNT(*) as count,
            ARRAY_AGG(SUBSTR(error_message, 0, 200) ORDER BY timestamp DESC LIMIT 3) as sample_messages
        FROM `{PROJECT_ID}.{DATASET_ID}.{LOGS_VIEW_ID}`
        WHERE status = 'ERROR'
        AND timestamp BETWEEN '{start_time}' AND '{end_time}'
        GROUP BY status, error_type
        ORDER BY count DESC
        """
        
        df = await execute_bigquery(query)
        
        if df.empty:
            return json.dumps({
                "status": "healthy",
                "message": "No errors found in the specified time range",
                "time_range": time_range
            })
        
        # Aggregate by error type
        by_type = {}
        by_severity = {}
        
        for _, row in df.iterrows():
            error_type = row['error_type']
            severity = 'ERROR' 
            count = int(row['count'])
            
            if error_type not in by_type:
                by_type[error_type] = {"count": 0, "samples": []}
            by_type[error_type]["count"] += count
            if row['sample_messages']:
                by_type[error_type]["samples"].extend(row['sample_messages'][:2])
            
            if severity not in by_severity:
                by_severity[severity] = 0
            by_severity[severity] += count
        
        total_errors = sum(by_severity.values())
        
        result = {
            "time_range": time_range,
            "total_errors": total_errors,
            "by_type": {k: {"count": v["count"], "percentage": round(v["count"]/total_errors*100, 1), "samples": v["samples"][:2]} 
                       for k, v in sorted(by_type.items(), key=lambda x: x[1]["count"], reverse=True)},
            "by_severity": by_severity,
            "recommendations": []
        }
        
        # Add recommendations based on error types
        if by_type.get('QUOTA_EXCEEDED', {}).get('count', 0) > 10:
            result['recommendations'].append("High quota errors - consider rate limiting or quota increase")
        if by_type.get('TIMEOUT', {}).get('count', 0) > 5:
            result['recommendations'].append("Timeout errors detected - check slow operations or increase timeouts")
        if by_type.get('TOOL_ERROR', {}).get('count', 0) > 5:
            result['recommendations'].append("Tool errors detected - review tool definitions")
        
        return json.dumps(result, cls=AnalysisEncoder)
        
    except Exception as e:
        logger.error(f"Error in classify_errors_by_type: {e}")
        return json.dumps({"error": str(e)})


@trace_span()
@cached_tool()
async def correlate_errors_with_latency(
    time_range: str = "24h"
) -> str:
    """
    Find correlation between errors and high-latency requests.

    This tool fetches error logs and attempts to correlate them with
    BigQuery latency data using trace_id.

    Args:
        time_range: Time range to analyze (e.g., "24h", "7d", "all")

    Returns:
        JSON string with correlation analysis showing:
        - Error patterns associated with high latency
        - Latency impact of specific errors
        - Confidence scores
    """
    # Get error logs
    # Note: We need a way to get the logging client. 
    # Since we don't have get_logging_client imported, we'll use google.cloud.logging
    from google.cloud import logging as cloud_logging
    client = cloud_logging.Client(project=PROJECT_ID)
    bq_client = bigquery.Client(project=PROJECT_ID)

    # Build filter for errors (simplified time filter logic here, ideally use parse_time_range_to_filter)
    # But parse_time_range returns "24" (hours) or date string?
    # parse_time_range returns a JSON window.
    # We need a filter string for Cloud Logging.
    
    # Let's adapt parse_time_range_to_filter logic here or import it if we had it.
    # We will compute it from time_range string manually or use the one from log_analysis_tools if we moved it.
    # I'll implement a simple version here.
    
    from datetime import datetime, timedelta
    
    if time_range.lower() == "all":
        hours_back = 24 * 30
    elif time_range.endswith('h'):
        hours_back = int(time_range[:-1])
    elif time_range.endswith('d'):
        hours_back = int(time_range[:-1]) * 24
    else:
        hours_back = 24
        
    start_time_dt = datetime.utcnow() - timedelta(hours=hours_back)
    time_filter = f'timestamp>="{start_time_dt.isoformat()}Z"'

    filters = [
        time_filter,
        'severity="ERROR"'
    ]
    filter_str = " AND ".join(filters)

    # Fetch error logs
    error_logs = []
    trace_to_errors = defaultdict(list)

    try:
        iterator = client.list_entries(filter_=filter_str, max_results=500)
        for entry in iterator:
            # Extract message
            if isinstance(entry.payload, dict):
                message = entry.payload.get('message', str(entry.payload))
            else:
                message = str(entry.payload)

            # Extract trace_id
            trace_id = None
            if hasattr(entry, 'trace') and entry.trace:
                trace_id = entry.trace.split('/')[-1] if '/' in entry.trace else entry.trace

            if trace_id:
                trace_to_errors[trace_id].append({
                    'message': message,
                    'timestamp': entry.timestamp.isoformat() if hasattr(entry, 'timestamp') else None
                })
                error_logs.append({
                    'trace_id': trace_id,
                    'message': message
                })
    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": f"Failed to fetch error logs: {str(e)}"
        })

    if not error_logs:
        return json.dumps({
            "status": "no_errors",
            "message": f"No errors found in time_range={time_range}",
            "time_range": time_range
        })

    # Query BigQuery for latency data of these traces
    tables = get_table_list()
    # parse_time_range returns JSON logic, we already calculated hours_back effectively
    
    bq_time_filter = f"start_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {hours_back} HOUR)"

    # Build query to get latency for traces with errors
    trace_ids_str = "', '".join(list(trace_to_errors.keys())[:100])  # Limit to avoid query size issues

    table_queries = []
    # Assuming DATASET_ID is defined (it is imported)
    for table in tables:
        table_queries.append(f"""
        SELECT
            trace_id,
            agent_name,
            TIMESTAMP_DIFF(end_time, start_time, MILLISECOND) as duration_ms
        FROM `{PROJECT_ID}.{DATASET_ID}.{table}`
        WHERE {bq_time_filter}
        AND trace_id IN ('{trace_ids_str}')
        """)

    try:
        query = " UNION ALL ".join(table_queries)
        df = bq_client.query(query).to_dataframe()
    except Exception as e:
        # If BigQuery query fails, return error log summary only
        return json.dumps({
            "status": "partial",
            "message": "Could not correlate with BigQuery latency data",
            "error": str(e),
            "error_summary": {
                "total_errors": len(error_logs),
                "affected_traces": len(trace_to_errors),
                "error_patterns": Counter([e['message'][:100] for e in error_logs]).most_common(5)
            }
        })

    if df.empty:
        return json.dumps({
            "status": "no_correlation",
            "message": "No matching traces found in BigQuery",
            "error_count": len(error_logs)
        })

    # Calculate correlation
    avg_latency_with_errors = df['duration_ms'].mean()

    correlation = {
        "total_errors": len(error_logs),
        "affected_traces": len(trace_to_errors),
        "time_range": time_range,

        # Latency analysis
        "traces_with_errors": {
            "count": len(df),
            "avg_latency_ms": float(avg_latency_with_errors),
            "median_latency_ms": float(df['duration_ms'].median()),
            "p95_latency_ms": float(df['duration_ms'].quantile(0.95))
        },

        # Error patterns
        "error_patterns": [
            {
                "message_prefix": msg[:100],
                "count": count,
                "affected_traces": len([t for t, errs in trace_to_errors.items() 
                                       if any(msg[:100] in e['message'] for e in errs)])
            }
            for msg, count in Counter([e['message'] for e in error_logs]).most_common(5)
        ],

        # Per-agent impact
        "by_agent": df.groupby('agent_name').agg({
            'duration_ms': ['mean', 'count']
        }).to_dict(),

        "interpretation": {
            "note": "This shows latency for traces that had errors. Compare with overall latency to assess impact.",
            "recommendation": "Use get_overall_statistics() to compare with baseline latency"
        }
    }

    return json.dumps(correlation, indent=2, default=str)
