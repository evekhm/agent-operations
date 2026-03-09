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
from .queries import FETCH_CORRELATION_DATA_QUERY

logger = logging.getLogger(__name__)

from ...config import MAX_RAW_RECORDS_LIMIT

@cached_tool(session_scope=True)
async def fetch_correlation_data(
    time_range: str = "24h",
    limit: int = MAX_RAW_RECORDS_LIMIT,
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
    
    from ...config import LLM_EVENTS_VIEW_ID
    
    query = FETCH_CORRELATION_DATA_QUERY.format(
        limit=limit,
        where_clause=where_clause
    )
    
    try:
        df = await execute_bigquery(query)
        if df.empty:
             return "{}"
        return df.to_json(orient="records", date_format="iso")
    except Exception as e:
        logger.error(f"Error fetching correlation data: {e}")
        return "{}"
