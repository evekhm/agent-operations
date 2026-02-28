import json
import json
import logging

from ...config import PROJECT_ID, DATASET_ID, TOOL_EVENTS_VIEW_ID, \
    AGENT_EVENTS_VIEW_ID, INVOCATION_EVENTS_VIEW_ID
from ...utils.bq import execute_bigquery
from ...utils.caching import cached_tool
from ...utils.common import AnalysisEncoder
from ...utils.common import build_standard_where_clause
from ...utils.telemetry import trace_span

logger = logging.getLogger(__name__)

@trace_span()
@cached_tool()
async def get_tool_errors(
    time_range: str = "24h",
    limit: int = 5
) -> str:
    """
    Fetches detailed tool errors with context (Agent, Root Agent, User Message).
    
    Args:
        time_range: Time range to analyze (e.g., "24h").
        limit: Max number of errors to return.
        
    Returns:
        JSON string containing list of tool errors.
    """
    logger.info(f"[TOOL CALL-get_tool_errors] time_range='{time_range}', limit={limit}")
    try:
        where_clause = build_standard_where_clause(time_range=time_range)
        
        query = f"""
        SELECT
            T.timestamp,
            T.tool_name,
            ANY_VALUE(T.tool_args) AS tool_args,
            ANY_VALUE(T.error_message) AS error_message,
            ANY_VALUE(A.agent_name) AS agent_name,
            ANY_VALUE(A.status) AS agent_status,
            ANY_VALUE(I.root_agent_name) AS root_agent_name,
            ANY_VALUE(I.status) AS root_status,
            ANY_VALUE(I.content_text_summary) AS user_message,
            T.trace_id,
            T.span_id
        FROM `{PROJECT_ID}.{DATASET_ID}.{TOOL_EVENTS_VIEW_ID}` AS T
        LEFT JOIN `{PROJECT_ID}.{DATASET_ID}.{AGENT_EVENTS_VIEW_ID}` AS A ON T.parent_span_id = A.span_id
        LEFT JOIN `{PROJECT_ID}.{DATASET_ID}.{INVOCATION_EVENTS_VIEW_ID}` AS I ON REPLACE(T.trace_id, '-', '') = REPLACE(I.trace_id, '-', '')
        WHERE {where_clause}
        AND T.status = 'ERROR'
        GROUP BY T.timestamp, T.tool_name, T.trace_id, T.span_id
        ORDER BY T.timestamp DESC
        LIMIT {limit}
        """
        
        df = await execute_bigquery(query)
        
        if df.empty:
            return json.dumps([])
            
        return json.dumps(df.to_dict(orient="records"), cls=AnalysisEncoder)
        
    except Exception as e:
        logger.error(f"Error in get_tool_errors: {e}")
        return json.dumps({"error": str(e)})
