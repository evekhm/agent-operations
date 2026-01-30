"""
Analytics tools for latency distribution and performance metrics.

This module contains tools for analyzing:
- Latency distribution (buckets)
- Detailed latency performance metrics (percentiles, stats)
- Slowest queries (generic)
- Latency breakdown by Group (Agent, Root Agent, Model)
- Metadata discovery (Agents/Models)
- Root Cause Analysis (AI.GENERATE)
"""
import json
import logging
from typing import Optional

import pandas as pd

from ...config import PROJECT_ID, DATASET_ID, LLM_EVENTS_VIEW_ID, DEFAULT_TIME_RANGE, CONNECTION_ID
from ...utils.bq import execute_bigquery
from ...utils.caching import cached_tool
from ...utils.common import AnalysisEncoder, build_standard_where_clause
from ...utils.telemetry import trace_span

logger = logging.getLogger(__name__)


@trace_span()
@cached_tool()
async def analyze_latency_distribution(
    time_range: str = DEFAULT_TIME_RANGE,
    agent_name: Optional[str] = None,
    root_agent_name: Optional[str] = None,
    model_name: Optional[str] = None,
    view_id: Optional[str] = None,
    latency_col: str = "duration_ms"
) -> str:
    """
    Analyze latency distribution categorized into buckets.
    
    Buckets:
    - <1s
    - 1-2s
    - 2-3s
    - 3-5s
    - 5-15s
    - 15-30s
    - 30s-1m
    - 1m-5m
    - 5m+
    
    Args:
        time_range (str): Time range to analyze (e.g., "24h", "7d", "all").
        agent_name (str): Optional. Filter by specific agent name.
        root_agent_name (str): Optional. Filter by root agent name.
        model_name (str): Optional. Filter by specific model.
        view_id (str): Optional. BigQuery table/view ID to query. Defaults to LLM_EVENTS_VIEW_ID.
        latency_col (str): Column name for latency/duration (default: "duration_ms").

    Returns:
        str: JSON string containing distribution data.
    """
    target_table = view_id or LLM_EVENTS_VIEW_ID
    logger.info(f"[TOOL CALL-analyze_latency_distribution] time_range='{time_range}', "
                f"agent_name='{agent_name}', root_agent_name='{root_agent_name}', "
                f"model_name='{model_name}', view_id='{target_table}', latency_col='{latency_col}'")
    
    try:
        where_clause = build_standard_where_clause(
            time_range=time_range,
            filter_config={
                "agent_name": (agent_name, "="),
                "root_agent_name": (root_agent_name, "="),
                "model_name": (model_name, "=")
            }
        )
        
        query = f"""
        WITH latency_data AS (
          SELECT
            {latency_col} as latency_ms
          FROM
            `{PROJECT_ID}.{DATASET_ID}.{target_table}` AS T
          WHERE
            {where_clause}
        )
        SELECT
          CASE
            WHEN latency_ms < 1000 THEN '<1s'
            WHEN latency_ms >= 1000 AND latency_ms < 2000 THEN '1-2s'
            WHEN latency_ms >= 2000 AND latency_ms < 3000 THEN '2-3s'
            WHEN latency_ms >= 3000 AND latency_ms < 5000 THEN '3-5s'
            WHEN latency_ms >= 5000 AND latency_ms < 15000 THEN '5-15s'
            WHEN latency_ms >= 15000 AND latency_ms < 30000 THEN '15-30s'
            WHEN latency_ms >= 30000 AND latency_ms < 60000 THEN '30s-1m'
            WHEN latency_ms >= 60000 AND latency_ms < 300000 THEN '1m-5m'
            ELSE '5m+'
          END AS category,
          COUNT(*) as count,
          AVG(latency_ms) as avg_latency_ms,
          MIN(latency_ms) as min_latency_ms,
          MAX(latency_ms) as max_latency_ms
        FROM latency_data
        GROUP BY category
        ORDER BY 
          CASE category
            WHEN '<1s' THEN 1
            WHEN '1-2s' THEN 2
            WHEN '2-3s' THEN 3
            WHEN '3-5s' THEN 4
            WHEN '5-15s' THEN 5
            WHEN '15-30s' THEN 6
            WHEN '30s-1m' THEN 7
            WHEN '1m-5m' THEN 8
            WHEN '5m+' THEN 9
          END
        """
        
        df = await execute_bigquery(query)
        
        if df.empty:
            return json.dumps({
                "error": "No data found",
                "metadata": {"time_range": time_range, "view_id": target_table}
            })
            
        total_requests = df['count'].sum()
        distribution = []
        
        for _, row in df.iterrows():
            distribution.append({
                "category": row['category'],
                "count": int(row['count']),
                "percentage": float(row['count'] / total_requests * 100) if total_requests > 0 else 0,
                "avg_latency_ms": float(row['avg_latency_ms']),
                "min_latency_ms": float(row['min_latency_ms']),
                "max_latency_ms": float(row['max_latency_ms'])
            })
            
        result = {
            "metadata": {
                "time_range": time_range,
                "view_id": target_table,
                "latency_col": latency_col,
                "total_requests": int(total_requests),
                "agent_name": agent_name,
                "root_agent_name": root_agent_name,
                "model_name": model_name
            },
            "distribution": distribution
        }
        
        return json.dumps(result, cls=AnalysisEncoder)
        
    except Exception as e:
        logger.error(f"Error in analyze_latency_distribution: {str(e)}")
        return json.dumps({"error": str(e)})


@trace_span()
@cached_tool()
async def analyze_latency_performance(
    time_range: str = DEFAULT_TIME_RANGE,
    agent_name: Optional[str] = None,
    root_agent_name: Optional[str] = None,
    model_name: Optional[str] = None,
    view_id: Optional[str] = None,
    latency_col: str = "duration_ms"
) -> str:
    """
    Calculate detailed latency performance metrics.
    
    Metrics:
    - Count
    - Avg (ms)
    - P50, P90, P95, P99, P99.9 (ms)
    - Min, Max (ms)
    - Nan (PENDING state count)
    - Std Dev, Median, Mean
    
    Args:
        time_range (str): Time range to analyze.
        agent_name (str): Optional system filter.
        root_agent_name (str): Optional system filter.
        model_name (str): Optional model filter.
        view_id (str): Optional. BigQuery table/view ID to query. Defaults to LLM_EVENTS_VIEW_ID.
        latency_col (str): Column name for latency/duration (default: "duration_ms").

    Returns:
        str: JSON string containing performance metrics.
    """
    target_table = view_id or LLM_EVENTS_VIEW_ID
    logger.info(f"[TOOL CALL-analyze_latency_performance] time_range='{time_range}', "
                f"agent_name='{agent_name}', root_agent_name='{root_agent_name}', "
                f"model_name='{model_name}', view_id='{target_table}', latency_col='{latency_col}'")

    try:
        where_clause = build_standard_where_clause(
            time_range=time_range,
            filter_config={
                "agent_name": (agent_name, "="),
                "root_agent_name": (root_agent_name, "="),
                "model_name": (model_name, "=")
            }
        )
        
        query = f"""
        SELECT
          COUNT(*) as total_count,
          COUNTIF({latency_col} IS NULL) as pending_count,
          AVG({latency_col}) as mean_ms,
          APPROX_QUANTILES({latency_col}, 100)[OFFSET(50)] as p50_ms,
          APPROX_QUANTILES({latency_col}, 100)[OFFSET(50)] as median_ms, -- Same as P50
          APPROX_QUANTILES({latency_col}, 100)[OFFSET(90)] as p90_ms,
          APPROX_QUANTILES({latency_col}, 100)[OFFSET(95)] as p95_ms,
          APPROX_QUANTILES({latency_col}, 100)[OFFSET(99)] as p99_ms,
          APPROX_QUANTILES({latency_col}, 1000)[OFFSET(999)] as p999_ms,
          MIN({latency_col}) as min_ms,
          MAX({latency_col}) as max_ms,
          STDDEV({latency_col}) as std_ms
        FROM
          `{PROJECT_ID}.{DATASET_ID}.{target_table}` AS T
        WHERE
          {where_clause}
        """

        df = await execute_bigquery(query)
        
        if df.empty:
            return json.dumps({
                "error": "No data found",
                "metadata": {"time_range": time_range, "view_id": target_table}
            })

        row = df.iloc[0]
        
        result = {
            "metadata": {
                "time_range": time_range,
                "view_id": target_table,
                "latency_col": latency_col,
                "agent_name": agent_name,
                "root_agent_name": root_agent_name,
                "model_name": model_name
            },
            "performance": {
                "count": int(row['total_count']),
                "pending_nan": int(row['pending_count']),
                "avg_ms": float(row['mean_ms']) if pd.notna(row['mean_ms']) else None,
                "mean_ms": float(row['mean_ms']) if pd.notna(row['mean_ms']) else None,
                "median_ms": float(row['median_ms']) if pd.notna(row['median_ms']) else None,
                "p50_ms": float(row['p50_ms']) if pd.notna(row['p50_ms']) else None,
                "p90_ms": float(row['p90_ms']) if pd.notna(row['p90_ms']) else None,
                "p95_ms": float(row['p95_ms']) if pd.notna(row['p95_ms']) else None,
                "p99_ms": float(row['p99_ms']) if pd.notna(row['p99_ms']) else None,
                "p99_9_ms": float(row['p999_ms']) if pd.notna(row['p999_ms']) else None,
                "min_ms": float(row['min_ms']) if pd.notna(row['min_ms']) else None,
                "max_ms": float(row['max_ms']) if pd.notna(row['max_ms']) else None,
                "std_ms": float(row['std_ms']) if pd.notna(row['std_ms']) else None
            }
        }
        
        return json.dumps(result, cls=AnalysisEncoder)

    except Exception as e:
        logger.error(f"Error in analyze_latency_performance: {str(e)}")
        return json.dumps({"error": str(e)})


@trace_span()
@cached_tool()
async def get_slowest_queries(
    time_range: str = DEFAULT_TIME_RANGE,
    limit: int = 10,
    min_latency_ms: float = 0,
    agent_name: Optional[str] = None,
    root_agent_name: Optional[str] = None,
    model_name: Optional[str] = None,
    view_id: Optional[str] = None,
    latency_col: str = "duration_ms"
) -> str:
    """
    Fetch the slowest successful queries.
    
    Args:
        time_range (str): Time range to analyze (e.g., "24h", "7d", "all").
        limit (int): Number of requests to return.
        min_latency_ms (float): Optional minimum latency filter.
        agent_name (str): Optional. Filter by specific agent name.
        root_agent_name (str): Optional. Filter by root agent name.
        model_name (str): Optional. Filter by model version.
        view_id (str): Optional. BigQuery table/view ID to query. Defaults to LLM_EVENTS_VIEW_ID.
        latency_col (str): Column name for latency/duration (default: "duration_ms").

    Returns:
        str: JSON string containing a list of slowest requests with details.
    """
    target_table = view_id or LLM_EVENTS_VIEW_ID
    logger.info(f"[TOOL CALL-get_slowest_queries] time_range='{time_range}', limit={limit}, "
                f"min_latency_ms={min_latency_ms}, agent_name='{agent_name}', "
                f"root_agent_name='{root_agent_name}', model_name='{model_name}', "
                f"view_id='{target_table}', latency_col='{latency_col}'")
    try:
        filter_config = {
            "agent_name": (agent_name, "="),
            "root_agent_name": (root_agent_name, "="),
            "model_name": (model_name, "=")
        }
        if min_latency_ms > 0:
            filter_config[latency_col] = (min_latency_ms, ">")

        where_clause = build_standard_where_clause(
            time_range=time_range,
            filter_config=filter_config
        )
        
        query = f"""
        SELECT *
        FROM `{PROJECT_ID}.{DATASET_ID}.{target_table}` AS T
        WHERE {where_clause}
        ORDER BY {latency_col} DESC
        LIMIT {limit}
        """

        df = await execute_bigquery(query)
        
        if df.empty:
            return json.dumps({
                "message": "No data found for slowest requests.", 
                "metadata": {"view_id": target_table}
            })
            
        requests = df.to_dict(orient="records")
            
        result = {
            "metadata": {"time_range": time_range, "limit": limit, "min_latency_ms": min_latency_ms,
                         "agent_name": agent_name, "root_agent_name": root_agent_name,
                         "model_name": model_name, "view_id": target_table},
            "requests": requests
        }
        
        return json.dumps(result, cls=AnalysisEncoder)
        
    except Exception as e:
        logger.error(f"Error in get_slowest_queries: {str(e)}")
        return json.dumps({"error": str(e)})


@trace_span()
@cached_tool()
async def analyze_latency_grouped(
    group_by: str = "agent_name",
    time_range: str = DEFAULT_TIME_RANGE,
    model_name: Optional[str] = None,
    view_id: Optional[str] = None,
    latency_col: str = "duration_ms"
) -> str:
    """
    Break down latency metrics by a specific dimension (Agent, Root Agent, or Model).
    
    Args:
        group_by (str): Dimension to group by. One of: "agent_name", "root_agent_name", "model_name".
        time_range (str): Time range.
        model_name (str): Optional. Filter by specific model (useful when grouping by agent).
        view_id (str): Optional.
        latency_col (str): Duration column.

    Returns:
        str: JSON string containing grouped latency metrics.
    """
    target_table = view_id or LLM_EVENTS_VIEW_ID
    logger.info(f"[TOOL CALL-analyze_latency_grouped] group_by='{group_by}', time_range='{time_range}', "
                f"model_name='{model_name}', view_id='{target_table}', latency_col='{latency_col}'")
    
    # Updated allowed_groups to include tool_name
    allowed_groups = ["agent_name", "root_agent_name", "model_name", "tool_name"]
    if group_by not in allowed_groups:
        return json.dumps({"error": f"Invalid group_by: {group_by}. Must be one of {allowed_groups}"})

    try:
        where_clause = build_standard_where_clause(
            time_range=time_range,
            filter_config={"model_name": (model_name, "=")}
        )
        
        query = f"""
        SELECT
          {group_by} as group_key,
          COUNT(*) as total_count,
          AVG({latency_col}) as avg_ms,
          APPROX_QUANTILES({latency_col}, 100)[OFFSET(50)] as p50_ms,
          APPROX_QUANTILES({latency_col}, 100)[OFFSET(95)] as p95_ms,
          APPROX_QUANTILES({latency_col}, 100)[OFFSET(99)] as p99_ms,
          MAX({latency_col}) as max_ms
        FROM
          `{PROJECT_ID}.{DATASET_ID}.{target_table}` AS T
        WHERE
          {where_clause}
        GROUP BY group_key
        ORDER BY avg_ms DESC
        """
        
        df = await execute_bigquery(query)
        
        if df.empty:
            return json.dumps({
                "message": "No data found.",
                "metadata": {"view_id": target_table, "group_by": group_by}
            })
            
        records = []
        for _, row in df.iterrows():
            records.append({
                group_by: row['group_key'],
                "total_count": int(row['total_count']),
                "avg_ms": float(row['avg_ms']) if pd.notna(row['avg_ms']) else None,
                "p50_ms": float(row['p50_ms']) if pd.notna(row['p50_ms']) else None,
                "p95_ms": float(row['p95_ms']) if pd.notna(row['p95_ms']) else None,
                "p99_ms": float(row['p99_ms']) if pd.notna(row['p99_ms']) else None,
                "max_ms": float(row['max_ms']) if pd.notna(row['max_ms']) else None
            })
            
        result = {
            "metadata": {"time_range": time_range, "view_id": target_table, "group_by": group_by},
            "breakdown": records
        }
        return json.dumps(result, cls=AnalysisEncoder)
        
    except Exception as e:
        logger.error(f"Error in analyze_latency_grouped: {str(e)}")
        return json.dumps({"error": str(e)})


@trace_span()
@cached_tool()
async def get_active_metadata(
    time_range: str = DEFAULT_TIME_RANGE,
    view_id: Optional[str] = None
) -> str:
    """
    Get unique metadata values (agents, models) from logs to facilitate drill-down analysis.
    
    Args:
        time_range (str): Time range to scan.
        view_id (str): Optional view ID.

    Returns:
        str: JSON string with lists of active agents, root_agents, and models.
    """
    target_table = view_id or LLM_EVENTS_VIEW_ID
    logger.info(f"[TOOL CALL-get_active_metadata] time_range='{time_range}', view_id='{target_table}'")
    
    try:
        where_clause = build_standard_where_clause(time_range=time_range)
        
        query = f"""
        SELECT
          APPROX_TOP_COUNT(agent_name, 100) as agents,
          APPROX_TOP_COUNT(root_agent_name, 100) as root_agents,
          APPROX_TOP_COUNT(model_name, 100) as models
        FROM
          `{PROJECT_ID}.{DATASET_ID}.{target_table}` AS T
        WHERE
          {where_clause}
        """
        
        df = await execute_bigquery(query)
        
        if df.empty:
            return json.dumps({"message": "No metadata found", "metadata": {"view_id": target_table}})
            
        row = df.iloc[0]
        
        def extract_values(data):
            if data is None: return []
            return [item['value'] for item in data if item['value'] is not None]

        result = {
            "metadata": {"time_range": time_range, "view_id": target_table},
            "agents": extract_values(row['agents']),
            "root_agents": extract_values(row['root_agents']),
            "models": extract_values(row['models'])
        }
        
        return json.dumps(result, cls=AnalysisEncoder)
        
    except Exception as e:
        logger.error(f"Error in get_active_metadata: {str(e)}")
        return json.dumps({"error": str(e)})


@trace_span()
@cached_tool()
async def analyze_root_cause(
    span_id: str,
    view_id: Optional[str] = None
) -> str:
    """
    Perform AI-powered root cause analysis on a specific request (span) using BigQuery AI.GENERATE.
    
    Args:
        span_id (str): The span_id of the request to analyze.
        view_id (str): Optional view ID.

    Returns:
        str: JSON string containing the AI generation result.
    """
    target_table = view_id or LLM_EVENTS_VIEW_ID
    logger.info(f"[TOOL CALL-analyze_root_cause] span_id='{span_id}', view_id='{target_table}'")
    
    try:
        # Generate connection ID
        connection_id = f"{PROJECT_ID}.us.{CONNECTION_ID}"
        model_endpoint = "gemini-1.5-pro"
        
        query = f"""
        SELECT
            span_id,
            AI.GENERATE(
                ('Analyze this request log and explain the root cause of the latency or error. Be concise. Log: ', TO_JSON_STRING(T)),
                connection_id => '{connection_id}',
                endpoint => '{model_endpoint}'
            ).result AS analysis
        FROM `{PROJECT_ID}.{DATASET_ID}.{target_table}` AS T
        WHERE span_id = '{span_id}'
        """
        
        df = await execute_bigquery(query)
        
        if df.empty:
            return json.dumps({"message": f"Span {span_id} not found", "metadata": {"view_id": target_table}})
            
        analysis = df.iloc[0]['analysis']
        
        result = {
            "metadata": {"span_id": span_id, "model": model_endpoint, "view_id": target_table},
            "root_cause_analysis": analysis
        }
        
        return json.dumps(result, cls=AnalysisEncoder)
        
    except Exception as e:
        logger.error(f"Error in analyze_root_cause: {str(e)}")
        return json.dumps({"error": str(e)})
