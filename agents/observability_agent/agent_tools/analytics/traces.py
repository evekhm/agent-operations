from typing import List, Dict
import logging
from agents.observability_agent.utils.bq import execute_bigquery
from agents.observability_agent.config import PROJECT_ID, DATASET_ID, AGENT_EVENTS_VIEW_ID

logger = logging.getLogger(__name__)

async def fetch_trace_spans(trace_id: str) -> List[Dict]:
    """
    Fetches all spans for a given trace_id to reconstruct the execution tree.
    Returns a list of dictionaries representing the spans, sorted by timestamp.
    """
    query = f"""
    SELECT
        span_id,
        parent_span_id,
        agent_name,
        root_agent_name,
        tool_name,
        model_name,
        CAST(timestamp as STRING) as timestamp,
        duration_ms,
        status,
        error_message
    FROM `{PROJECT_ID}.{DATASET_ID}.{AGENT_EVENTS_VIEW_ID}`
    WHERE trace_id = '{trace_id}'
    ORDER BY timestamp ASC
    """
    try:
        df = await execute_bigquery(query)
        if df.empty:
            return []
        return df.to_dict('records')
    except Exception as e:
        logger.error(f"Error fetching trace spans for {trace_id}: {e}")
        return []
