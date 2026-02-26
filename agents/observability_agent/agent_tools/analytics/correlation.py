"""
Correlation Analysis Tool.

This module provides tools to fetch raw data for correlation analysis between
latency and token usage.
"""
import logging
from typing import Optional

import pandas as pd
from ...utils.caching import cached_tool
from google.adk.tools.tool_context import ToolContext

from ...utils.bq import execute_bigquery
from ...utils.common import build_standard_where_clause

logger = logging.getLogger(__name__)

@cached_tool(session_scope=True)
async def fetch_correlation_data(
    time_range: str = "24h",
    limit: int = 2000,
    tool_context: ToolContext = None
) -> str:
    """
    Fetches raw data points for correlation analysis (Latency vs Tokens).
    
    Args:
        time_range (str): Time range filter (e.g., "24h", "7d", "all").
        limit (int): Maximum number of rows to fetch.
        
    Returns:
        str: JSON string of the fetched data.
    """
    where_clause = build_standard_where_clause(time_range=time_range)
    
    query = f"""
    SELECT
        root_agent_name,
        agent_name,
        model_name,
        total_token_count,
        prompt_token_count as input_token_count,
        candidates_token_count as output_token_count,
        thoughts_token_count,
        duration_ms
    FROM `{{PROJECT_ID}}.{{DATASET_ID}}.llm_events_view` AS T
    WHERE {where_clause}
      AND total_token_count > 0
      AND duration_ms > 0
    ORDER BY timestamp DESC
    LIMIT {limit}
    """
    
    from ...config import PROJECT_ID, DATASET_ID
    query = query.format(PROJECT_ID=PROJECT_ID, DATASET_ID=DATASET_ID)
    
    try:
        df = await execute_bigquery(query)
        if df.empty:
             return "{}"
        return df.to_json(orient="records", date_format="iso")
    except Exception as e:
        logger.error(f"Error fetching correlation data: {e}")
        return "{}"
