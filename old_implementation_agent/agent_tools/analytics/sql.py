"""
Tool for executing arbitrary SQL queries against BigQuery.
"""
import json
import logging
from typing import Optional

from ...utils.bq import execute_bigquery
from ...utils.common import AnalysisEncoder
from ...utils.caching import cached_tool
from ...config import PROJECT_ID, DATASET_ID

logger = logging.getLogger(__name__)

@cached_tool()
async def run_sql_query(query: str) -> str:
    """
    Execute an arbitrary SQL query against BigQuery.
    
    Use this tool when standard analytical tools (like analyze_latency_grouped) are insufficient 
    and you need to run a custom JOIN, aggregations, or specific data extraction.
    
    Args:
        query (str): The standard SQL query to execute.
        
    Returns:
        str: JSON string containing the query results.
    """
    logger.info(f"[TOOL CALL-run_sql_query] query='{query}'")
    
    try:
        # Basic safety check - strictly read-only
        forbidden_keywords = ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "GRANT", "REVOKE", "CREATE", "TRUNCATE", "MERGE"]
        upper_query = query.upper()
        for keyword in forbidden_keywords:
            if keyword in upper_query.split(): # Simple word boundary check
                 return json.dumps({"error": f"Operation '{keyword}' is not allowed. Read-only access only."})

        # Auto-qualify common view names if they are not qualified
        # This handles cases where the LLM forgets the dataset prefix
        common_tables = [
            "agent_events_view", 
            "llm_events_view", 
            "tool_events_view", 
            "invocation_events_view",
            "agent_events"
        ]
        
        for table in common_tables:
            # Simple check: if table is in query but not precoded by dataset in any obvious way
            # We use a simple replace which might be risky if table name is a substring of another, 
            # but these names are fairly unique. 
            # Better regex: \b{table}\b -> `{PROJECT_ID}.{DATASET_ID}.{table}`
            import re
            pattern = r'(?<![\.\w])' + re.escape(table) + r'(?![\.\w])'
            replacement = f"`{PROJECT_ID}.{DATASET_ID}.{table}`"
            query = re.sub(pattern, replacement, query, flags=re.IGNORECASE)

        df = await execute_bigquery(query)
        
        if df.empty:
            return json.dumps({"message": "Query returned no results.", "query": query})

        # Convert to records
        results = df.to_dict(orient="records")
        
        return json.dumps({
            "metadata": {"query_length": len(query), "row_count": len(results)},
            "results": results
        }, cls=AnalysisEncoder)
        
    except Exception as e:
        logger.error(f"Error in run_sql_query: {str(e)}")
        return json.dumps({"error": str(e)})
