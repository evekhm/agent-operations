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
import asyncio
from typing import Optional

import pandas as pd

from ...config import PROJECT_ID, DATASET_ID, LLM_EVENTS_VIEW_ID, DEFAULT_TIME_RANGE, CONNECTION_ID, DATASET_LOCATION, INVOCATION_EVENTS_VIEW_ID, TOOL_EVENTS_VIEW_ID, AGENT_EVENTS_VIEW_ID
from ...utils.bq import execute_bigquery
from ...utils.caching import cached_tool
from ...utils.common import AnalysisEncoder, build_standard_where_clause

logger = logging.getLogger(__name__)


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


@cached_tool()
async def get_slowest_queries(
    time_range: str = DEFAULT_TIME_RANGE,
    limit: int = 5,
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

        target_table = view_id.strip()

        # Dynamic column selection based on view_id
        if target_table == LLM_EVENTS_VIEW_ID:
            select_col_model = "model_name"
            select_col_tokens = "prompt_token_count, candidates_token_count, total_token_count, thoughts_token_count, time_to_first_token_ms"
            select_col_extra = ", full_request, full_response, llm_config"
        elif target_table == TOOL_EVENTS_VIEW_ID:
            select_col_model = "NULL as model_name"
            select_col_tokens = "NULL as prompt_token_count, NULL as candidates_token_count, NULL as total_token_count, NULL as thoughts_token_count, NULL as time_to_first_token_ms"
            select_col_extra = ", tool_name, tool_args, tool_result"
        elif target_table == INVOCATION_EVENTS_VIEW_ID:
            select_col_model = "NULL as model_name"
            # Invocations don't have standard token counts or instructions in the same way, but have content
            select_col_tokens = "NULL as prompt_token_count, NULL as candidates_token_count, NULL as total_token_count, NULL as thoughts_token_count, NULL as time_to_first_token_ms"
            select_col_extra = ", content_text as instruction" # Using content_text as loose equivalent for instruction/input
        else: # AGENT_EVENTS_VIEW_ID (default fallthrough or explicit)
            select_col_model = "NULL as model_name"
            select_col_tokens = "NULL as prompt_token_count, NULL as candidates_token_count, NULL as total_token_count, NULL as thoughts_token_count, NULL as time_to_first_token_ms"
            select_col_extra = ", instruction"

        if target_table == INVOCATION_EVENTS_VIEW_ID:
             # Invocations have invocation_id, not span_id/parent_span_id
             # We map invocation_id to span_id for consistency in the SELECT, or use NULL
             select_ids = "invocation_id as span_id, trace_id, session_id, NULL as parent_span_id"
        else:
             select_ids = "span_id, trace_id, session_id, parent_span_id"

        # Select key columns + metrics
        query = f"""
        SELECT 
            {select_ids},
            {latency_col},
            agent_name,
            root_agent_name,
            {select_col_model},
            {select_col_tokens},
            status,
            timestamp{select_col_extra}
        FROM `{PROJECT_ID}.{DATASET_ID}.{target_table}` AS T
        WHERE {where_clause}
        ORDER BY {latency_col} DESC
        LIMIT {limit}
        """

        df = await execute_bigquery(query)

        # Truncate massive columns with descriptive pointers so the agent relies on analyze_root_cause for full data inspection
        for col in ['tool_args', 'response_content', 'prompt_content']:
            if col in df.columns:
                df[col] = df[col].astype(str).apply(
                    lambda x: x if len(x) <= 800 else f"[LARGE PAYLOAD: {len(x)} chars. Use batch_analyze_root_cause(span_ids='...') to analyze full content instead of fetching it here.]"
                )

        
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


@cached_tool()
async def analyze_latency_grouped(
    group_by: str = "agent_name",
    time_range: str = DEFAULT_TIME_RANGE,
    model_name: Optional[str] = None,
    exclude_root: bool = False,
    view_id: Optional[str] = None,
    latency_col: str = "duration_ms"
) -> str:
    """
    Break down latency metrics by a specific dimension (Agent, Root Agent, or Model).
    
    Args:
        group_by (str): Dimension to group by. One of: "agent_name", "root_agent_name", "model_name".
        time_range (str): Time range.
        model_name (str): Optional. Filter by specific model (useful when grouping by agent).
        exclude_root (bool): Optional. If True, excludes rows where agent_name matches root_agent_name.
        view_id (str): Optional.
        latency_col (str): Duration column.

    Returns:
        str: JSON string containing grouped latency metrics.
    """
    target_table = view_id or LLM_EVENTS_VIEW_ID
    logger.info(f"[TOOL CALL-analyze_latency_grouped] group_by='{group_by}', time_range='{time_range}', "
                f"model_name='{model_name}', exclude_root={exclude_root}, view_id='{target_table}', latency_col='{latency_col}'")
    
    # Updated allowed_groups to include tool_name
    allowed_groups = ["agent_name", "root_agent_name", "model_name", "tool_name"]
    
    # Handle multi-column grouping
    group_columns = [g.strip() for g in group_by.split(",")]
    for col in group_columns:
        if col not in allowed_groups:
             return json.dumps({"error": f"Invalid group_by column: {col}. Must be one of {allowed_groups}"})

    try:
        where_clause = build_standard_where_clause(
            time_range=time_range,
            filter_config={"model_name": (model_name, "=")}
        )
        
        if exclude_root:
            where_clause += " AND agent_name != root_agent_name"
        
        # Build SELECT and GROUP BY clauses dynamically
        select_group_cols = ", ".join(group_columns)
        group_by_clause = ", ".join([str(i+1) for i in range(len(group_columns))])

        query = f"""
        SELECT
          {select_group_cols},
          COUNT(*) as total_count,
          COUNTIF(status = 'ERROR') as error_count,
          COUNTIF(status != 'ERROR' AND status != 'PENDING') as success_count,
          ROUND(COUNTIF(status = 'ERROR') / NULLIF(COUNTIF(status != 'PENDING'), 0) * 100, 2) as error_rate_pct,
          AVG(IF(status != 'ERROR' AND status != 'PENDING', {latency_col}, NULL)) as avg_ms,
          STDDEV(IF(status != 'ERROR' AND status != 'PENDING', {latency_col}, NULL)) as std_latency_ms,
          ROUND((STDDEV(IF(status != 'ERROR' AND status != 'PENDING', {latency_col}, NULL)) / NULLIF(AVG(IF(status != 'ERROR' AND status != 'PENDING', {latency_col}, NULL)), 0)) * 100, 2) as cv_pct,
          MIN(IF(status != 'ERROR' AND status != 'PENDING', {latency_col}, NULL)) as min_ms,
          APPROX_QUANTILES(IF(status != 'ERROR' AND status != 'PENDING', {latency_col}, NULL), 1000)[OFFSET(500)] as p50_ms,
          APPROX_QUANTILES(IF(status != 'ERROR' AND status != 'PENDING', {latency_col}, NULL), 1000)[OFFSET(750)] as p75_ms,
          APPROX_QUANTILES(IF(status != 'ERROR' AND status != 'PENDING', {latency_col}, NULL), 1000)[OFFSET(900)] as p90_ms,
          APPROX_QUANTILES(IF(status != 'ERROR' AND status != 'PENDING', {latency_col}, NULL), 1000)[OFFSET(950)] as p95_ms,
          APPROX_QUANTILES(IF(status != 'ERROR' AND status != 'PENDING', {latency_col}, NULL), 1000)[OFFSET(990)] as p99_ms,
          APPROX_QUANTILES(IF(status != 'ERROR' AND status != 'PENDING', {latency_col}, NULL), 1000)[OFFSET(999)] as p999_ms,
          MAX(IF(status != 'ERROR' AND status != 'PENDING', {latency_col}, NULL)) as max_ms"""
        
        # Conditionally add token metrics if querying LLM events
        if str(target_table) == str(LLM_EVENTS_VIEW_ID):
             query += """,
          AVG(prompt_token_count) as avg_input_tokens,
          APPROX_QUANTILES(prompt_token_count, 100)[OFFSET(95)] as p95_input_tokens,
          AVG(candidates_token_count) as avg_output_tokens,
          APPROX_QUANTILES(candidates_token_count, 100)[OFFSET(95)] as p95_output_tokens,
          AVG(thoughts_token_count) as avg_thought_tokens,
          APPROX_QUANTILES(thoughts_token_count, 100)[OFFSET(95)] as p95_thought_tokens
             """
             
        query += f"""
        FROM
          `{PROJECT_ID}.{DATASET_ID}.{target_table}` AS T
        WHERE
          {where_clause}
        GROUP BY {group_by_clause}
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
            record = {
                "total_count": int(row['total_count']),
                "success_count": int(row['success_count']),
                "error_count": int(row['error_count']),
                "error_rate_pct": float(row['error_rate_pct']) if pd.notna(row['error_rate_pct']) else 0.0,
                "min_ms": float(row['min_ms']) if pd.notna(row['min_ms']) else None,
                "avg_ms": float(row['avg_ms']) if pd.notna(row['avg_ms']) else None,
                "std_latency_ms": float(row['std_latency_ms']) if pd.notna(row['std_latency_ms']) else None,
                "cv_pct": float(row['cv_pct']) if pd.notna(row['cv_pct']) else None,
                "p50_ms": float(row['p50_ms']) if pd.notna(row['p50_ms']) else None,
                "p75_ms": float(row['p75_ms']) if pd.notna(row['p75_ms']) else None,
                "p90_ms": float(row['p90_ms']) if pd.notna(row['p90_ms']) else None,
                "p95_ms": float(row['p95_ms']) if pd.notna(row['p95_ms']) else None,
                "p99_ms": float(row['p99_ms']) if pd.notna(row['p99_ms']) else None,
                "p999_ms": float(row['p999_ms']) if pd.notna(row['p999_ms']) else None,
                "max_ms": float(row['max_ms']) if pd.notna(row['max_ms']) else None
            }
            
            # Add token metrics if available
            if str(target_table) == str(LLM_EVENTS_VIEW_ID):
                 record.update({
                     "avg_input_tokens": float(row['avg_input_tokens']) if pd.notna(row['avg_input_tokens']) else 0.0,
                     "p95_input_tokens": float(row['p95_input_tokens']) if pd.notna(row['p95_input_tokens']) else 0.0,
                     "avg_output_tokens": float(row['avg_output_tokens']) if pd.notna(row['avg_output_tokens']) else 0.0,
                     "p95_output_tokens": float(row['p95_output_tokens']) if pd.notna(row['p95_output_tokens']) else 0.0,
                     "avg_thought_tokens": float(row['avg_thought_tokens']) if pd.notna(row['avg_thought_tokens']) else 0.0,
                     "p95_thought_tokens": float(row['p95_thought_tokens']) if pd.notna(row['p95_thought_tokens']) else 0.0,
                 })
            # Add grouping columns to the record
            for col in group_columns:
                record[col] = row[col]
            records.append(record)
            
        result = {
            "metadata": {"time_range": time_range, "view_id": target_table, "group_by": group_by},
            "breakdown": records
        }
        return json.dumps(result, cls=AnalysisEncoder)
        
    except Exception as e:
        logger.error(f"Error in analyze_latency_grouped: {str(e)}")
        return json.dumps({"error": str(e)})



@cached_tool()
async def get_active_metadata(
    time_range: str = "7d",
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
        import asyncio
        
        async def fetch_distinct(column_name: str, limit: int = 50) -> list[str]:
            query = f"""
            SELECT DISTINCT {column_name}
            FROM `{PROJECT_ID}.{DATASET_ID}.{target_table}` AS T
            WHERE {where_clause} AND {column_name} IS NOT NULL
            LIMIT {limit}
            """
            
            df = await execute_bigquery(query)
            if df.empty:
                return []
            return df[column_name].tolist()

        agents, root_agents, models = await asyncio.gather(
            fetch_distinct("agent_name"),
            fetch_distinct("root_agent_name"),
            fetch_distinct("model_name")
        )
        
        if not agents and not root_agents and not models:
            return json.dumps({"message": "No metadata found", "metadata": {"view_id": target_table}})

        result = {
            "metadata": {"time_range": time_range, "view_id": target_table},
            "agents": agents,
            "root_agents": root_agents,
            "models": models
        }
        
        return json.dumps(result, cls=AnalysisEncoder)
        
    except Exception as e:
        logger.error(f"Error in get_active_metadata: {str(e)}")
        return json.dumps({"error": str(e)})


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
        connection_id = f"{PROJECT_ID}.{DATASET_LOCATION}.{CONNECTION_ID}"
        model_endpoint = "gemini-2.0-flash"
        
        id_column = "invocation_id" if target_table == INVOCATION_EVENTS_VIEW_ID else "span_id"
        
        query = f"""
        SELECT
            {id_column} AS span_id,
            AI.GENERATE(
                ('Analyze this request log and explain the root cause of the latency or error. Be concise. Focus ONLY on factors visible in the log (e.g. LLM prompt size, external API delays). NEVER use the words "sequential" or "parallel", as the agent architecture is fixed and already concurrent. Describe only what is in the data. Log: ', TO_JSON_STRING(T)),
                connection_id => '{connection_id}',
                endpoint => '{model_endpoint}'
            ).result AS analysis
        FROM `{PROJECT_ID}.{DATASET_ID}.{target_table}` AS T
        WHERE {id_column} = '{span_id}'
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


@cached_tool()
async def batch_analyze_root_cause(
    span_ids: str,
    view_ids: str = None
) -> str:
    """
    Perform AI-powered root cause analysis on multiple requests (spans) in PARALLEL.
    Use this when you have multiple spans to analyze (e.g., top 3 slowest queries) to save time.
    
    Args:
        span_ids (str): Comma-separated list of span_ids to analyze.
        view_ids (str): Comma-separated list of view IDs corresponding to each span, OR a single view ID to apply to all.
                        If provided as a list, it must match the order of span_ids.

    Returns:
        str: JSON string containing a list of analysis results.
    """
    logger.info(f"[TOOL CALL-batch_analyze_root_cause] span_ids='{span_ids}', view_ids='{view_ids}'")
    
    try:
        id_list = [s.strip() for s in span_ids.split(",") if s.strip()]
        
        # Handle view_ids
        if not view_ids:
            view_list = [None] * len(id_list)
        else:
            v_list = [v.strip() for v in view_ids.split(",") if v.strip()]
            if len(v_list) == 1:
                view_list = [v_list[0]] * len(id_list)
            elif len(v_list) == len(id_list):
                view_list = v_list
            else:
                return json.dumps({"error": "Mismatch between count of span_ids and view_ids provided."})

        # Create concurrent tasks
        tasks = []
        for span_id, view_id in zip(id_list, view_list):
            tasks.append(analyze_root_cause(span_id=span_id, view_id=view_id))
            
        # Run in parallel
        results_json = await asyncio.gather(*tasks)
        
        # Parse JSONs back to dicts to return a composite JSON list
        results = [json.loads(r) for r in results_json]
        
        return json.dumps({"batch_analysis": results}, cls=AnalysisEncoder)

    except Exception as e:
        logger.error(f"Error in batch_analyze_root_cause: {str(e)}")
        return json.dumps({"error": str(e)})


@cached_tool()
async def get_fastest_queries(
    time_range: str = "7d",
    limit: int = 10,
    agent_name: Optional[str] = None,
    root_agent_name: Optional[str] = None,
    model_name: Optional[str] = None,
    view_id: Optional[str] = None,
    latency_col: str = "duration_ms"
) -> str:
    """
    Fetch the fastest successful queries.
    
    Args:
        time_range (str): Time range to analyze (e.g., "24h", "7d", "all").
        limit (int): Number of requests to return.
        agent_name (str): Optional. Filter by specific agent name.
        root_agent_name (str): Optional. Filter by root agent name.
        model_name (str): Optional. Filter by model version.
        view_id (str): Optional. BigQuery table/view ID to query. Defaults to LLM_EVENTS_VIEW_ID.
        latency_col (str): Column name for latency/duration (default: "duration_ms").

    Returns:
        str: JSON string containing a list of fastest requests with details.
    """
    target_table = view_id or LLM_EVENTS_VIEW_ID
    logger.info(f"[TOOL CALL-get_fastest_queries] time_range='{time_range}', limit={limit}, "
                f"agent_name='{agent_name}', root_agent_name='{root_agent_name}', "
                f"model_name='{model_name}', view_id='{target_table}', latency_col='{latency_col}'")
    try:
        filter_config = {
            "agent_name": (agent_name, "="),
            "root_agent_name": (root_agent_name, "="),
            "model_name": (model_name, "=")
        }

        where_clause = build_standard_where_clause(
            time_range=time_range,
            filter_config=filter_config
        )
        
        # Filter out 0ms or negative latencies as they might be errors/artifacts
        query = f"""
        SELECT *
        FROM `{PROJECT_ID}.{DATASET_ID}.{target_table}` AS T
        WHERE {where_clause} AND {latency_col} > 0
        ORDER BY {latency_col} ASC
        LIMIT {limit}
        """

        df = await execute_bigquery(query)
        
        if df.empty:
            return json.dumps({
                "message": "No data found for fastest requests.", 
                "metadata": {"view_id": target_table}
            })
            
        requests = df.to_dict(orient="records")
            
        result = {
            "metadata": {"time_range": time_range, "limit": limit,
                         "agent_name": agent_name, "root_agent_name": root_agent_name,
                         "model_name": model_name, "view_id": target_table},
            "requests": requests
        }
        
        return json.dumps(result, cls=AnalysisEncoder)
        
    except Exception as e:
        logger.error(f"Error in get_fastest_queries: {str(e)}")
        return json.dumps({"error": str(e)})


@cached_tool()
async def get_baseline_performance_metrics(
    group_by: str = "agent_name",
    time_range: str = "7d",
    limit_percentile: float = 0.1,
    model_name: Optional[str] = None,
    view_id: Optional[str] = None,
    latency_col: str = "duration_ms"
) -> str:
    """
    Establish a dynamic performance baseline by analyzing the fastest queries (e.g., top 10%).
    
    Args:
        group_by (str): Dimension to group by. One of: "agent_name", "model_name", "tool_name".
        time_range (str): Time range to analyze (e.g., "7d", "all").
        limit_percentile (float): The top percentile of fastest queries to use for the baseline (e.g., 0.1 for top 10%).
        model_name (str): Optional. Filter by specific model.
        view_id (str): Optional. BigQuery table/view ID to query.
        latency_col (str): Column name for latency/duration (default: "duration_ms").

    Returns:
        str: JSON string containing baseline metrics (mean, p95) for the best performing percentage of queries.
    """
    allowed_groups = {
        "agent_name": AGENT_EVENTS_VIEW_ID,
        "root_agent_name": INVOCATION_EVENTS_VIEW_ID,
        "model_name": LLM_EVENTS_VIEW_ID,
        "tool_name": TOOL_EVENTS_VIEW_ID
    }

    if group_by not in allowed_groups:
        return json.dumps({"error": f"Invalid group_by: {group_by}. Must be one of {list(allowed_groups.keys())}"})
        
    target_table = view_id or allowed_groups[group_by]
    logger.info(f"[TOOL CALL-get_baseline_performance_metrics] group_by='{group_by}', time_range='{time_range}', "
                f"limit_percentile={limit_percentile}, model_name='{model_name}', "
                f"view_id='{target_table}', latency_col='{latency_col}'")

    try:
        where_clause = build_standard_where_clause(
            time_range=time_range,
            filter_config={"model_name": (model_name, "=")}
        )
        
        query = f"""
        WITH RankedData AS (
            SELECT
                {group_by} as group_key,
                {latency_col} as latency_ms,
                PERCENT_RANK() OVER (PARTITION BY {group_by} ORDER BY {latency_col} ASC) as percentile_rank
            FROM `{PROJECT_ID}.{DATASET_ID}.{target_table}` AS T
            WHERE {where_clause} AND {latency_col} > 50
        ),
        FilteredBaseline AS (
            SELECT group_key, latency_ms
            FROM RankedData
            WHERE percentile_rank <= {limit_percentile}
        )
        SELECT
            group_key,
            COUNT(*) as baseline_sample_size,
            AVG(latency_ms) as target_mean_ms,
            APPROX_QUANTILES(latency_ms, 100)[OFFSET(95)] as target_p95_ms
        FROM FilteredBaseline
        GROUP BY group_key
        ORDER BY target_mean_ms ASC
        """
        
        df = await execute_bigquery(query)
        
        if df.empty:
            return json.dumps({
                "message": "No data found for baseline creation.",
                "metadata": {"view_id": target_table, "group_by": group_by}
            })
            
        records = []
        for _, row in df.iterrows():
            records.append({
                group_by: row['group_key'],
                "baseline_sample_size": int(row['baseline_sample_size']),
                "target_mean_ms": float(row['target_mean_ms']) if pd.notna(row['target_mean_ms']) else None,
                "target_p95_ms": float(row['target_p95_ms']) if pd.notna(row['target_p95_ms']) else None
            })
            
        result = {
            "metadata": {"time_range": time_range, "view_id": target_table, "group_by": group_by, "limit_percentile": limit_percentile},
            "baseline": records
        }
        return json.dumps(result, cls=AnalysisEncoder)
        
    except Exception as e:
        logger.error(f"Error in get_baseline_performance_metrics: {str(e)}")
        return json.dumps({"error": str(e)})



@cached_tool()
async def get_latest_queries(
    time_range: str = DEFAULT_TIME_RANGE,
    limit: int = 10,
    agent_name: Optional[str] = None,
    root_agent_name: Optional[str] = None,
    model_name: Optional[str] = None,
    view_id: Optional[str] = None,
    latency_col: str = "duration_ms"
) -> str:
    """
    Fetch the most recent queries to check for recent performance improvements.
    
    Args:
        time_range (str): Time range to analyze (default is '24h' to keep it recent).
        limit (int): Number of most recent requests to return.
        agent_name (str): Optional. Filter by specific agent name.
        root_agent_name (str): Optional. Filter by root agent name.
        model_name (str): Optional. Filter by model version.
        view_id (str): Optional. BigQuery table/view ID to query. Defaults to agent_events_view.
        latency_col (str): Column name for latency/duration (default: "duration_ms").

    Returns:
        str: JSON string containing a list of the most recent requests with details.
    """
    target_table = view_id or "agent_events_view"
    logger.info(f"[TOOL CALL-get_latest_queries] time_range='{time_range}', limit={limit}, "
                f"agent_name='{agent_name}', root_agent_name='{root_agent_name}', "
                f"model_name='{model_name}', view_id='{target_table}', latency_col='{latency_col}'")
    try:
        filter_config = {
            "agent_name": (agent_name, "="),
            "root_agent_name": (root_agent_name, "="),
            "model_name": (model_name, "=")
        }

        where_clause = build_standard_where_clause(
            time_range=time_range,
            filter_config=filter_config
        )
        
        query = f"""
        SELECT *
        FROM `{PROJECT_ID}.{DATASET_ID}.{target_table}` AS T
        WHERE {where_clause} AND {latency_col} IS NOT NULL
        ORDER BY timestamp DESC
        LIMIT {limit}
        """

        df = await execute_bigquery(query)
        
        if df.empty:
            return json.dumps({
                "message": "No recent data found for latest requests verification.", 
                "metadata": {"view_id": target_table}
            })
            
        requests = df.to_dict(orient="records")
            
        result = {
            "metadata": {"time_range": time_range, "limit": limit,
                         "agent_name": agent_name, "root_agent_name": root_agent_name,
                         "model_name": model_name, "view_id": target_table},
            "requests": requests
        }
        
        return json.dumps(result, cls=AnalysisEncoder)
        
    except Exception as e:
        logger.error(f"Error in get_latest_queries: {str(e)}")
        return json.dumps({"error": str(e)})

async def get_failed_queries(
    time_range: str = "24h",
    limit: int = 10,
    agent_name: str = None,
    root_agent_name: str = None,
    model_name: str = None,
    view_id: str = None,
    latency_col: str = "duration_ms"
) -> str:
    """
    Retrieves the most recent failed requests (status = 'ERROR') with their details.
    Use this after analyze_latency_grouped shows a high error_rate_pct for a specific component.
    Always specify the problematic component (e.g., model_name="gemini-3.0-pro") to narrow down the search.
    
    Args:
        time_range (str): Time filter (e.g., "1h", "24h", "7d", "all").
        limit (int): Max number of failed requests to return.
        agent_name (str, optional): Filter by agent name.
        root_agent_name (str, optional): Filter by root agent name.
        model_name (str, optional): Filter by model name.
        view_id (str, optional): The target BigQuery view (e.g., "agent_events_view", "llm_events_view"). Defaults to llm_events_view.
        latency_col (str): Column name for latency/duration (default: "duration_ms").
        
    Returns:
        str: JSON string containing a list of failed requests with details.
    """
    target_table = view_id or LLM_EVENTS_VIEW_ID
    logger.info(f"[TOOL CALL-get_failed_queries] time_range='{time_range}', limit={limit}, "
                f"agent_name='{agent_name}', root_agent_name='{root_agent_name}', "
                f"model_name='{model_name}', view_id='{target_table}', latency_col='{latency_col}'")
    try:
        filter_config = {
            "agent_name": (agent_name, "="),
            "root_agent_name": (root_agent_name, "="),
            "model_name": (model_name, "="),
            "status": ("ERROR", "=")
        }
        
        where_clause = build_standard_where_clause(
            time_range=time_range,
            filter_config=filter_config
        )

        query = f"""
        SELECT * 
        FROM `{PROJECT_ID}.{DATASET_ID}.{target_table}` AS T
        WHERE {where_clause}
        ORDER BY timestamp DESC
        LIMIT {limit}
        """

        df = await execute_bigquery(query)
        
        if df.empty:
            return json.dumps({
                "message": "No failed queries found matching criteria.", 
                "metadata": {"view_id": target_table}
            })
            
        requests = df.to_dict(orient="records")
            
        result = {
            "metadata": {"time_range": time_range, "limit": limit,
                         "agent_name": agent_name, "root_agent_name": root_agent_name,
                         "model_name": model_name, "view_id": target_table},
            "requests": requests
        }
        
        return json.dumps(result, cls=AnalysisEncoder)
        
    except Exception as e:
        logger.error(f"Error in get_failed_queries: {str(e)}")
        return json.dumps({"error": str(e)})


@cached_tool()
async def analyze_latency_trend(
    group_by: str,
    view_id: str,
    time_range: str = "30d",
    bucket_size: str = "1d"
) -> str:
    """
    Analyzes the temporal trend of latency and errors by chopping the time array into distinct chronological buckets.
    Used exclusively by Playbook C to determine if slopes are degrading or improving over long periods of time.
    """
    try:
        # Strip invisible characters from LLM injection
        view_id = str(view_id).strip()
        group_by = str(group_by).strip()
        
        # 1. Strict view validation
        if view_id not in ["agent_events_view", "llm_events_view", "tool_events_view"]:
            return json.dumps({"error": f"Invalid view_id: {view_id}"})
            
        # 2. Strict group_by validation so the LLM cannot inject bad column names
        valid_groups = ["agent_name", "model_name", "tool_name"]
        if group_by not in valid_groups:
             return json.dumps({"error": f"Invalid group_by '{group_by}'. MUST be one of {valid_groups}"})
            
        where_clause = build_standard_where_clause(time_range=time_range)
        
        # Translate generic bucket strings to BigQuery intervals
        interval_map = {"1h": "HOUR", "1d": "DAY", "7d": "WEEK"}
        bq_interval = interval_map.get(bucket_size, "DAY")
        
        clean_where_clause = where_clause.replace("T.", "")
        
        query = f"""
        SELECT
            {group_by} AS name,
            TIMESTAMP_TRUNC(timestamp, {bq_interval}) AS time_bucket,
            COUNT(*) AS total_calls,
            APPROX_QUANTILES(duration_ms, 100)[OFFSET(95)] AS p95_ms,
            AVG(duration_ms) AS avg_ms,
            COUNTIF(status = 'ERROR') / NULLIF(COUNT(*), 0) * 100 AS error_rate_pct
        FROM
            `{PROJECT_ID}.{DATASET_ID}.{view_id}`
        WHERE
            {clean_where_clause}
        GROUP BY
            name, time_bucket
        ORDER BY
            name, time_bucket ASC
        """
        
        df = await execute_bigquery(query)
        
        if df.empty:
            return json.dumps({"error": "No data found for trend analysis."})
            
        trend_results = {}
        for name, group in df.groupby('name'):
            buckets = []
            for _, row in group.iterrows():
                buckets.append({
                    "bucket": row['time_bucket'].strftime('%Y-%m-%d %H:%M:%S'),
                    "p95_ms": float(row['p95_ms']) if pd.notna(row['p95_ms']) else None,
                    "error_rate_pct": f"{float(row['error_rate_pct']):.2f}%" if pd.notna(row['error_rate_pct']) else "0.00%"
                })
            trend_results[name] = {"trend": buckets}
            
        return json.dumps({"trend_analysis": trend_results}, cls=AnalysisEncoder)
    except Exception as e:
        logger.error(f"Error in analyze_latency_trend: {e}")
        return json.dumps({"error": str(e)})

@cached_tool()
async def get_llm_impact_analysis(
    time_range: str = "7d",
    limit: int = 15,
    agent_name: Optional[str] = None,
    root_agent_name: Optional[str] = None,
    model_name: Optional[str] = None,
    view_id: Optional[str] = None
) -> str:
    """
    Analyze the impact of LLM calls on End-to-End latency.
    
    Joins LLM events with their parent Agent and Root Invocation to calculate:
    - % Impact (LLM Duration / Total Duration)
    - Token usage (Input/Output/Thought)
    - User Message context
    
    Args:
        time_range (str): Time range to analyze.
        limit (int): Number of top bottlenecks to return.
        agent_name (str): Filter by Agent.
        root_agent_name (str): Filter by Root Agent.
        model_name (str): Filter by Model.
        view_id (str): Optional view override (defaults to LLM view).

    Returns:
        str: JSON string containing the impact analysis.
    """
    target_table = view_id or LLM_EVENTS_VIEW_ID
    logger.info(f"[TOOL CALL-get_llm_impact_analysis] time_range='{time_range}', limit={limit}")

    try:
        # Build filter for the PRIMARY table (LLM_EVENTS_VIEW as 'L')
        # We filter 'L' directly for efficiency.
        where_clause = build_standard_where_clause(
            time_range=time_range,
            filter_config={
                "agent_name": (agent_name, "="),
                "root_agent_name": (root_agent_name, "="), 
                "model_name": (model_name, "=")
            },
            table_alias="L"
        )
        
        query = f"""
        SELECT
            L.duration_ms as llm_duration,
            L.time_to_first_token_ms,
            L.model_name,
            COALESCE(L.status, 'UNKNOWN') as llm_status,
            L.prompt_token_count as input_tokens,
            L.candidates_token_count as output_tokens,
            L.thoughts_token_count as thought_tokens,
            L.total_token_count,
            A.agent_name,
            A.duration_ms as agent_duration,
            COALESCE(A.status, 'UNKNOWN') as agent_status,
            I.root_agent_name,
            I.duration_ms as root_duration,
            COALESCE(I.status, 'UNKNOWN') as root_status,
            ROUND(SAFE_DIVIDE(L.duration_ms, I.duration_ms) * 100, 2) as impact_pct,
            L.trace_id,
            L.session_id,
            L.span_id,
            L.parent_span_id,
            L.timestamp,
            SUBSTR(I.content_text, 1, 100) as user_message_trunk
        FROM `{PROJECT_ID}.{DATASET_ID}.{target_table}` L
        LEFT JOIN `{PROJECT_ID}.{DATASET_ID}.{AGENT_EVENTS_VIEW_ID}` A ON L.parent_span_id = A.span_id
        LEFT JOIN `{PROJECT_ID}.{DATASET_ID}.{INVOCATION_EVENTS_VIEW_ID}` I ON L.session_id = I.session_id
        WHERE
            {where_clause}
        ORDER BY L.duration_ms DESC
        LIMIT {limit}
        """

        df = await execute_bigquery(query)
        
        if df.empty:
             return json.dumps({
                "message": "No impact data found.",
                "metadata": {"view_id": target_table}
            })

        records = []
        for _, row in df.iterrows():
            records.append({
                "llm_duration": float(row['llm_duration']),
                "time_to_first_token_ms": float(row['time_to_first_token_ms']) if pd.notna(row['time_to_first_token_ms']) else None,
                "model_name": row['model_name'],
                "llm_status": row['llm_status'],
                "input_tokens": int(row['input_tokens']) if pd.notna(row['input_tokens']) else 0,
                "output_tokens": int(row['output_tokens']) if pd.notna(row['output_tokens']) else 0,
                "thought_tokens": int(row['thought_tokens']) if pd.notna(row['thought_tokens']) else 0,
                "total_tokens": int(row['total_token_count']) if pd.notna(row['total_token_count']) else 0,
                "agent_name": row['agent_name'],
                "agent_duration": float(row['agent_duration']) if pd.notna(row['agent_duration']) else 0.0,
                "agent_status": row['agent_status'],
                "root_agent_name": row['root_agent_name'],
                "root_duration": float(row['root_duration']) if pd.notna(row['root_duration']) else 0.0,
                "root_status": row['root_status'],
                "impact_pct": float(row['impact_pct']) if pd.notna(row['impact_pct']) else 0.0,
                "trace_id": row['trace_id'],
                "session_id": row['session_id'],
                "span_id": row['span_id'],
                "timestamp": row['timestamp'].isoformat() if hasattr(row['timestamp'], 'isoformat') else str(row['timestamp']),
                "user_message_trunk": row['user_message_trunk']
            })

        result = {
            "metadata": {"time_range": time_range, "view_id": target_table},
            "impact_analysis": records
        }
        
        return json.dumps(result, cls=AnalysisEncoder)

    except Exception as e:
        logger.error(f"Error in get_llm_impact_analysis: {str(e)}")
        return json.dumps({"error": str(e)})
