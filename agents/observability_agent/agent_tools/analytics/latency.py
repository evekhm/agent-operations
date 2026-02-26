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
import asyncio
import json
import logging
import time
from typing import Optional

import pandas as pd

from ...config import (PROJECT_ID, DATASET_ID, LLM_EVENTS_VIEW_ID, DEFAULT_TIME_RANGE, CONNECTION_ID, DATASET_LOCATION,
                       INVOCATION_EVENTS_VIEW_ID, TOOL_EVENTS_VIEW_ID, AGENT_EVENTS_VIEW_ID)

from ...utils.bq import execute_bigquery
from ...utils.caching import cached_tool
from ...utils.common import AnalysisEncoder, build_standard_where_clause, sanitize_for_markdown

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
    latency_col: str = "duration_ms",
    group_by: Optional[str] = None
) -> str:
    """
    Calculate detailed latency performance metrics, optionally grouped by a column.
    
    Metrics:
    - Count, Avg, Median, P95, P99 (ms)
    - Min, Max, Outliers (>2std, >3std)
    - Token Statistics (Mean, Correlation)
    - Latency Buckets
    
    Args:
        time_range (str): Time range to analyze.
        agent_name (str): Optional system filter.
        root_agent_name (str): Optional system filter.
        model_name (str): Optional model filter.
        view_id (str): Optional. BigQuery table/view ID to query.
        latency_col (str): Column name for latency (default: "duration_ms").
        group_by (str): Optional column to group by (e.g. "model_name").

    Returns:
        str: JSON string containing performance metrics (list of dicts if grouped).
    """
    target_table = view_id or LLM_EVENTS_VIEW_ID
    logger.info(f"[TOOL CALL-analyze_latency_performance] time_range='{time_range}', "
                f"group_by='{group_by}', filters=(agent='{agent_name}', root='{root_agent_name}', model='{model_name}')")

    try:
        where_clause = build_standard_where_clause(
            time_range=time_range,
            filter_config={
                "agent_name": (agent_name, "="),
                "root_agent_name": (root_agent_name, "="),
                "model_name": (model_name, "=")
            }
        )
        
        # Determine grouping
        group_select = f"{group_by}," if group_by else ""
        group_clause = f"GROUP BY {group_by}" if group_by else ""
        
        # specific for final query which joins two tables with same column
        group_select_final = f"R.{group_by}," if group_by else ""
        group_clause_final = f"GROUP BY R.{group_by}" if group_by else ""
        join_clause = f"ON R.{group_by} = S.{group_by}" if group_by else "ON 1=1"
        
        query = f"""
        WITH RawData AS (
          SELECT
            {group_select}
            {latency_col} as latency_ms,
            candidates_token_count as output_tokens,
            thoughts_token_count as thinking_tokens,
            (IFNULL(candidates_token_count, 0) + IFNULL(thoughts_token_count, 0)) as total_output_tokens
          FROM `{PROJECT_ID}.{DATASET_ID}.{target_table}` AS T
          WHERE {where_clause}
        ),
        Stats AS (
          SELECT
            {group_select}
            AVG(latency_ms) as mean_ms,
            STDDEV(latency_ms) as std_ms
          FROM RawData
          {group_clause}
        )
        SELECT
          {group_select_final}
          COUNT(*) as total_count,
          COUNTIF(R.latency_ms IS NULL) as pending_count,
          ANY_VALUE(S.mean_ms) as mean_ms,
          APPROX_QUANTILES(R.latency_ms, 100)[OFFSET(50)] as p50_ms,
          APPROX_QUANTILES(R.latency_ms, 100)[OFFSET(50)] as median_ms,
          APPROX_QUANTILES(R.latency_ms, 100)[OFFSET(90)] as p90_ms,
          APPROX_QUANTILES(R.latency_ms, 100)[OFFSET(95)] as p95_ms,
          APPROX_QUANTILES(R.latency_ms, 100)[OFFSET(99)] as p99_ms,
          APPROX_QUANTILES(R.latency_ms, 1000)[OFFSET(999)] as p999_ms,
          MIN(R.latency_ms) as min_ms,
          MAX(R.latency_ms) as max_ms,
          ANY_VALUE(S.std_ms) as std_ms,
          COUNTIF(R.latency_ms > (S.mean_ms + 2 * S.std_ms)) as count_2std,
          COUNTIF(R.latency_ms > (S.mean_ms + 3 * S.std_ms)) as count_3std,
          -- Token Stats
          AVG(R.output_tokens) as mean_tokens,
          APPROX_QUANTILES(R.output_tokens, 100)[OFFSET(50)] as median_tokens,
          MIN(R.output_tokens) as min_tokens,
          MAX(R.output_tokens) as max_tokens,
          CORR(R.latency_ms, R.output_tokens) as corr_latency_output,
          CORR(R.latency_ms, R.total_output_tokens) as corr_latency_output_thinking,
          -- Latency Buckets
          COUNTIF(R.latency_ms < 1000) as bucket_under_1s,
          COUNTIF(R.latency_ms >= 1000 AND R.latency_ms < 2000) as bucket_1_2s,
          COUNTIF(R.latency_ms >= 2000 AND R.latency_ms < 3000) as bucket_2_3s,
          COUNTIF(R.latency_ms >= 3000 AND R.latency_ms < 5000) as bucket_3_5s,
          COUNTIF(R.latency_ms >= 5000 AND R.latency_ms < 8000) as bucket_5_8s,
          COUNTIF(R.latency_ms >= 8000) as bucket_over_8s
        FROM
          RawData R
        JOIN Stats S {join_clause}
        {group_clause_final}
        """

        df = await execute_bigquery(query)
        
        if df.empty:
            return json.dumps({
                "error": "No data found",
                "metadata": {"time_range": time_range, "view_id": target_table}
            })

        results = []
        for _, row in df.iterrows():
            total_count = int(row['total_count'])
            
            def calc_pct(count):
                return (count / total_count * 100) if total_count > 0 else 0.0
                
            # Helper for safer float conversion
            def safe_float(val, default=None):
                return float(val) if pd.notna(val) else default

            result_item = {
                "metadata": {
                    "time_range": time_range,
                    "view_id": target_table,
                    "latency_col": latency_col,
                    "agent_name": agent_name,
                    "root_agent_name": root_agent_name,
                    "model_name": model_name
                },
                "performance": {
                    "count": total_count,
                    "pending_nan": int(row['pending_count']),
                    "avg_ms": safe_float(row['mean_ms']),
                    "mean_ms": safe_float(row['mean_ms']),
                    "median_ms": safe_float(row['median_ms']),
                    "p50_ms": safe_float(row['p50_ms']),
                    "p90_ms": safe_float(row['p90_ms']),
                    "p95_ms": safe_float(row['p95_ms']),
                    "p99_ms": safe_float(row['p99_ms']),
                    "p99_9_ms": safe_float(row['p999_ms']),
                    "min_ms": safe_float(row['min_ms']),
                    "max_ms": safe_float(row['max_ms']),
                    "std_ms": safe_float(row['std_ms']),
                    "outliers": {
                        "count_2std": int(row['count_2std']) if pd.notna(row['count_2std']) else 0,
                        "pct_2std": float(f"{calc_pct(int(row['count_2std']) if pd.notna(row['count_2std']) else 0):.1f}"),
                        "count_3std": int(row['count_3std']) if pd.notna(row['count_3std']) else 0,
                        "pct_3std": float(f"{calc_pct(int(row['count_3std']) if pd.notna(row['count_3std']) else 0):.1f}")
                    },
                    "token_stats": {
                        "mean_tokens": safe_float(row['mean_tokens']),
                        "median_tokens": safe_float(row['median_tokens']),
                        "min_tokens": safe_float(row['min_tokens']),
                        "max_tokens": safe_float(row['max_tokens']),
                        "corr_latency_output": safe_float(row['corr_latency_output']),
                        "corr_latency_output_thinking": safe_float(row['corr_latency_output_thinking'])
                    },
                    "distribution": {
                        "bucket_under_1s": {"count": int(row['bucket_under_1s']), "pct": float(f"{calc_pct(row['bucket_under_1s']):.1f}")},
                        "bucket_1_2s": {"count": int(row['bucket_1_2s']), "pct": float(f"{calc_pct(row['bucket_1_2s']):.1f}")},
                        "bucket_2_3s": {"count": int(row['bucket_2_3s']), "pct": float(f"{calc_pct(row['bucket_2_3s']):.1f}")},
                        "bucket_3_5s": {"count": int(row['bucket_3_5s']), "pct": float(f"{calc_pct(row['bucket_3_5s']):.1f}")},
                        "bucket_5_8s": {"count": int(row['bucket_5_8s']), "pct": float(f"{calc_pct(row['bucket_5_8s']):.1f}")},
                        "bucket_over_8s": {"count": int(row['bucket_over_8s']), "pct": float(f"{calc_pct(row['bucket_over_8s']):.1f}")}
                    }
                }
            }
            if group_by:
                result_item["metadata"][group_by] = row[group_by]
            results.append(result_item)

        if group_by:
            return json.dumps(results, cls=AnalysisEncoder)
        else:
            return json.dumps(results[0], cls=AnalysisEncoder)
            
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

        if target_table == TOOL_EVENTS_VIEW_ID:
            where_clause += " AND tool_name != 'transfer_to_agent'"

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
        for col in ['tool_args', 'response_content', 'prompt_content', 'full_request', 'full_response', 'instruction', 'content_text', 'user_message', 'error_message']:
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
    latency_col: str = "duration_ms",
    percentile: float = 95.0
) -> str:
    """
    Break down latency metrics by a specific dimension (Agent, Root Agent, or Model).
    
    Args:
        group_by (str): Dimension to group by. One of: "agent_name", "root_agent_name", "model_name", "tool_name".
                        Can also be comma-separated like "agent_name,model_name".
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
                f"model_name='{model_name}', exclude_root={exclude_root}, view_id='{target_table}', "
                f"latency_col='{latency_col}', percentile={percentile}")
    
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
            # Explicitly exclude root agents which typically have no parent span in the trace structure
            where_clause += " AND parent_span_id IS NOT NULL"
            
        if target_table == TOOL_EVENTS_VIEW_ID:
            where_clause += " AND tool_name != 'transfer_to_agent'"
        
        # Build SELECT and GROUP BY clauses dynamically
        select_group_cols = ", ".join(group_columns)
        group_by_clause = ", ".join([str(i+1) for i in range(len(group_columns))])

        # SPECIAL CASE: Grouping by Agent AND Model requires a JOIN between Agent View and LLM View
        # This is because 'model_name' is not in Agent View, and 'agent_name' in LLM View might be the sub-agent name (which is fine)
        # So we MUST join if target_table is AGENT_EVENTS_VIEW_ID and 'model_name' is in group_by.

        if str(target_table) == str(AGENT_EVENTS_VIEW_ID) and "model_name" in group_columns:
             # Construct the JOIN query
             # We need to map group columns to A or L aliases
             # agent_name -> A.agent_name
             # model_name -> L.model_name
             
             select_clauses = []
             group_indices = []
             
             for idx, col in enumerate(group_columns):
                 if col == "agent_name":
                     select_clauses.append("A.agent_name")
                 elif col == "model_name":
                     select_clauses.append("L.model_name")
                 elif col == "root_agent_name":
                     select_clauses.append("A.root_agent_name")
                 else:
                     select_clauses.append(f"A.{col}") # Default to Agent table
                 group_indices.append(str(idx + 1))
                 
             select_group_sql = ", ".join(select_clauses)
             group_by_sql = ", ".join(group_indices)
             
             # Re-build where clause with Alias 'A'
             where_clause_joined = build_standard_where_clause(
                time_range=time_range,
                filter_config={"model_name": (model_name, "=")},
                table_alias="A"
             )
             
             if exclude_root:
                where_clause_joined += " AND A.agent_name != A.root_agent_name"

             query = f"""
                WITH LLM_Aggregated AS (
                    SELECT 
                        parent_span_id, 
                        model_name,
                        SUM(candidates_token_count) as candidates_token_count,
                        SUM(thoughts_token_count) as thoughts_token_count,
                        SUM(total_token_count) as total_token_count
                    FROM `{PROJECT_ID}.{DATASET_ID}.{LLM_EVENTS_VIEW_ID}`
                    GROUP BY 1, 2
                )
                SELECT
                  {select_group_sql},
                  COUNT(DISTINCT A.span_id) as total_count,
                  COUNT(DISTINCT CASE WHEN A.status = 'ERROR' THEN A.span_id END) as error_count,
                  COUNT(DISTINCT CASE WHEN A.status != 'ERROR' AND A.status != 'PENDING' THEN A.span_id END) as success_count,
                  ROUND(COUNT(DISTINCT CASE WHEN A.status = 'ERROR' THEN A.span_id END) / NULLIF(COUNT(DISTINCT A.span_id), 0) * 100, 2) as error_rate_pct,
                  AVG(A.{latency_col}) as avg_ms,
                  STDDEV(A.{latency_col}) as std_latency_ms,
                  0.0 as cv_pct, -- approximation
                  MIN(A.{latency_col}) as min_ms,
                  APPROX_QUANTILES(A.{latency_col}, 1000)[OFFSET(500)] as p50_ms,
                  APPROX_QUANTILES(A.{latency_col}, 1000)[OFFSET(750)] as p75_ms,
                  APPROX_QUANTILES(A.{latency_col}, 1000)[OFFSET(900)] as p90_ms,
                  APPROX_QUANTILES(A.{latency_col}, 1000)[OFFSET(950)] as p95_ms,
                  APPROX_QUANTILES(A.{latency_col}, 1000)[OFFSET(990)] as p99_ms,
                  APPROX_QUANTILES(A.{latency_col}, 1000)[OFFSET(999)] as p999_ms,
                  APPROX_QUANTILES(A.{latency_col}, 1000)[OFFSET(CAST({percentile} * 10 AS INT64))] as p_custom_ms,
                  MAX(A.{latency_col}) as max_ms,
                  -- Token Metrics
                  AVG(L.candidates_token_count) as avg_output_tokens,
                  APPROX_QUANTILES(L.candidates_token_count, 100)[OFFSET(50)] as median_output_tokens,
                  MIN(L.candidates_token_count) as min_output_tokens,
                  MAX(L.candidates_token_count) as max_output_tokens,
                  -- Correlation Metrics
                  CORR(A.{latency_col}, L.candidates_token_count - IFNULL(L.thoughts_token_count, 0)) as corr_latency_pure_output,
                  CORR(A.{latency_col}, L.candidates_token_count) as corr_latency_output_plus_thoughts,
                  CORR(A.{latency_col}, L.total_token_count) as corr_latency_total
                FROM `{PROJECT_ID}.{DATASET_ID}.{AGENT_EVENTS_VIEW_ID}` AS A
                JOIN LLM_Aggregated AS L
                ON A.span_id = L.parent_span_id
                WHERE {where_clause_joined}
                GROUP BY {group_by_sql}
                ORDER BY avg_ms DESC
             """
        
        else:
            # ORIGINAL LOGIC for single table
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
              APPROX_QUANTILES(IF(status != 'ERROR' AND status != 'PENDING', {latency_col}, NULL), 1000)[OFFSET(CAST({percentile} * 10 AS INT64))] as p_custom_ms,
              MAX(IF(status != 'ERROR' AND status != 'PENDING', {latency_col}, NULL)) as max_ms"""
            
            # Conditionally add token metrics if querying LLM events
            if str(target_table) == str(LLM_EVENTS_VIEW_ID):
                 query += f""",
              AVG(prompt_token_count) as avg_input_tokens,
              APPROX_QUANTILES(prompt_token_count, 100)[OFFSET(95)] as p95_input_tokens,
              AVG(candidates_token_count) as avg_output_tokens,
              APPROX_QUANTILES(candidates_token_count, 100)[OFFSET(95)] as p95_output_tokens,
              APPROX_QUANTILES(candidates_token_count, 100)[OFFSET(50)] as median_output_tokens,
              MIN(candidates_token_count) as min_output_tokens,
              MAX(candidates_token_count) as max_output_tokens,
              AVG(thoughts_token_count) as avg_thought_tokens,
              APPROX_QUANTILES(thoughts_token_count, 100)[OFFSET(95)] as p95_thought_tokens,
              AVG(total_token_count) as avg_total_tokens,
              APPROX_QUANTILES(total_token_count, 100)[OFFSET(95)] as p95_total_tokens,
              CORR({latency_col}, prompt_token_count) as corr_latency_input,
              CORR({latency_col}, candidates_token_count) as corr_latency_output,
              CORR({latency_col}, total_token_count) as corr_latency_total
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
        
        token_df = pd.DataFrame()
        if str(target_table) != str(LLM_EVENTS_VIEW_ID) and any(g in ["agent_name", "root_agent_name"] for g in group_columns):
            token_query = f"""
            SELECT
              {select_group_cols},
              AVG(prompt_token_count) as avg_input_tokens,
              APPROX_QUANTILES(prompt_token_count, 100)[OFFSET(95)] as p95_input_tokens,
              AVG(candidates_token_count) as avg_output_tokens,
              APPROX_QUANTILES(candidates_token_count, 100)[OFFSET(95)] as p95_output_tokens,
              APPROX_QUANTILES(candidates_token_count, 100)[OFFSET(50)] as median_output_tokens,
              MIN(candidates_token_count) as min_output_tokens,
              MAX(candidates_token_count) as max_output_tokens,
              AVG(thoughts_token_count) as avg_thought_tokens,
              APPROX_QUANTILES(thoughts_token_count, 100)[OFFSET(95)] as p95_thought_tokens,
              AVG(total_token_count) as avg_total_tokens,
              APPROX_QUANTILES(total_token_count, 100)[OFFSET(95)] as p95_total_tokens
            FROM `{PROJECT_ID}.{DATASET_ID}.{LLM_EVENTS_VIEW_ID}` AS T
            WHERE {where_clause}
            GROUP BY {group_by_clause}
            """
            token_df = await execute_bigquery(token_query)
        
        if df.empty:
            return json.dumps({
                "message": "No data found.",
                "metadata": {"view_id": target_table, "group_by": group_by}
            })
            
        if not token_df.empty:
            # Merge token metrics if available
            try:
                df = df.merge(token_df, on=group_columns, how='left')
            except Exception as e:
                logger.warning(f"Failed to merge token metrics: {e}")

        # Helper for safer float conversion
        def safe_float(val):
            return float(val) if pd.notna(val) else None

        # Sanitize for JSON serialization
        records = df.to_dict(orient="records")
        
        # Post-processing for dynamic keys and type safety
        final_records = []
        for rec in records:
            # Handle dynamic percentile key
            if 'p_custom_ms' in rec:
                rec[f"p{percentile}_ms"] = rec.pop('p_custom_ms')
            
            # Ensure safe types (AnalysisEncoder handles most, but being explicit helps)
            clean_rec = {}
            for k, v in rec.items():
                if pd.isna(v):
                    clean_rec[k] = None
                else:
                    clean_rec[k] = v

            # Add correlation metrics if present
            if 'corr_latency_pure_output' in rec:
                clean_rec['corr_latency_pure_output'] = safe_float(rec.get('corr_latency_pure_output'))
                clean_rec['corr_latency_output_plus_thoughts'] = safe_float(rec.get('corr_latency_output_plus_thoughts'))
                clean_rec['corr_latency_total'] = safe_float(rec.get('corr_latency_total'))

            final_records.append(clean_rec)
        
        records = final_records
            
        return json.dumps({
            "metadata": {"view_id": target_table, "group_by": group_by, "time_range": time_range},
            "data": records
        }, cls=AnalysisEncoder)

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

        async def fetch_distinct(column_name: str, limit: int = 50) -> list[str]:
            """Fetch distinct values for a given column from the events view."""
            query = f"""
            SELECT DISTINCT {column_name}
            FROM `{PROJECT_ID}.{DATASET_ID}.{target_table}` AS T
            WHERE {where_clause} AND {column_name} IS NOT NULL
            LIMIT {limit}
            """
            
            try:
                df = await execute_bigquery(query)
                if df.empty:
                    return []
                return df[column_name].tolist()
            except Exception as e:
                # If column doesn't exist (e.g. model_name in agent_events_view), return empty list
                # This is safer than hardcoding view names
                if "Unrecognized name" in str(e):
                    return []
                raise e

        # Parallel execution for all potential columns
        # We try to fetch model_name even for agent_events_view, but catch the error if it doesn't exist
        # This makes the tool robust to view schema changes
        agents, root_agents, models = await asyncio.gather(
            fetch_distinct("agent_name"),
            fetch_distinct("root_agent_name"),
            fetch_distinct("model_name"),
            return_exceptions=True
        )

        # Handle exceptions from gather if any (though fetch_distinct catches most)
        def _process_result(res):
            if isinstance(res, Exception):
                logger.warning(f"Metadata fetch failed: {res}")
                return []
            return res

        agents = _process_result(agents)
        root_agents = _process_result(root_agents)
        models = _process_result(models)
        
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
        
        # print(f"DEBUG: Executing AI.GENERATE for span {span_id}...", flush=True)
        try:
            df = await execute_bigquery(query)
        except Exception as query_err:
            print(f"DEBUG: BigQuery AI.GENERATE failed for {span_id}: {query_err}", flush=True)
            raise query_err
        
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
            
        # Custom logging for user visibility
        start_time = time.time()
        logger.info(f"Starting AI Root Cause Analysis on {len(id_list)} traces (View IDs: {view_list})...")
        # logger.info(f"Starting batch_analyze_root_cause for {len(id_list)} spans.")

        # Run in parallel
        # print(f"DEBUG: Awaiting {len(tasks)} analysis tasks...", flush=True)
        results_json = await asyncio.gather(*tasks)
        
        duration = time.time() - start_time
        logger.info(f"Finished AI Root Cause Analysis in {duration:.2f}s.")
        logger.info(f"Finished batch_analyze_root_cause in {duration:.2f}s")
        
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
        
        # Truncate massive columns with descriptive pointers so the agent relies on analyze_root_cause for full data inspection
        for col in ['tool_args', 'response_content', 'prompt_content', 'full_request', 'full_response', 'instruction', 'content_text', 'user_message', 'error_message']:
            if col in df.columns:
                df[col] = df[col].astype(str).apply(
                    lambda x: x if len(x) <= 800 else f"[LARGE PAYLOAD: {len(x)} chars. Use batch_analyze_root_cause(span_ids='...') to analyze full content instead of fetching it here.]"
                )
        
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
            SUBSTR(I.content_text, 1, 250) as user_message_trunk
        FROM `{PROJECT_ID}.{DATASET_ID}.{target_table}` L
        LEFT JOIN `{PROJECT_ID}.{DATASET_ID}.{AGENT_EVENTS_VIEW_ID}` A ON L.parent_span_id = A.span_id
        LEFT JOIN `{PROJECT_ID}.{DATASET_ID}.{INVOCATION_EVENTS_VIEW_ID}` I ON L.trace_id = I.trace_id
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
        error_str = str(e)
        if "429" in error_str or "Resource exhausted" in error_str:
            logger.warning(f"get_llm_impact_analysis hit quota: {error_str}")
            return json.dumps({
                "message": "LLM Impact Analysis skipped due to quota limits (429).",
                "metadata": {"view_id": target_table},
                "impact_analysis": []
            })
        logger.error(f"Error in get_llm_impact_analysis: {error_str}")
        return json.dumps({"error": error_str})

async def get_tool_impact_analysis(limit: int = 15, time_range: str = "24h") -> str:
    """
    Fetches the top slowest Tool executions with joined context (Agent & Root Invocation).
    Used to populate the 'Top Tool Bottlenecks & Impact' table.
    """
    try:
        where_clause = build_standard_where_clause(
            time_range=time_range,
            table_alias="T"
        )

        query = f"""
        SELECT
            T.duration_ms as tool_duration,
            T.tool_name,
            TO_JSON_STRING(T.tool_args) as tool_args,
            COALESCE(TO_JSON_STRING(T.tool_result), '') as tool_result_str,
            COALESCE(T.status, 'UNKNOWN') as tool_status,
            T.agent_name,
            A.duration_ms as agent_duration,
            COALESCE(A.status, 'UNKNOWN') as agent_status,
            I.root_agent_name,
            I.duration_ms as root_duration,
            COALESCE(I.status, 'UNKNOWN') as root_status,
            SAFE_DIVIDE(T.duration_ms, I.duration_ms) * 100 as impact_pct,
            T.trace_id,
            T.session_id,
            T.span_id,
            T.parent_span_id,
            T.timestamp,
            SUBSTR(I.content_text, 1, 250) as user_message_trunk
        FROM `{PROJECT_ID}.{DATASET_ID}.{TOOL_EVENTS_VIEW_ID}` T
        LEFT JOIN `{PROJECT_ID}.{DATASET_ID}.{AGENT_EVENTS_VIEW_ID}` A ON T.parent_span_id = A.span_id
        LEFT JOIN `{PROJECT_ID}.{DATASET_ID}.{INVOCATION_EVENTS_VIEW_ID}` I ON T.trace_id = I.trace_id
        WHERE
            {where_clause}
        ORDER BY T.duration_ms DESC
        LIMIT {limit}
        """

        df = await execute_bigquery(query)
        
        if df.empty:
             return json.dumps({
                "message": "No tool impact data found.",
                "metadata": {"view_id": TOOL_EVENTS_VIEW_ID}
            })

        for col in ['tool_args', 'response_content', 'tool_result']:
            if col in df.columns:
                df[col] = df[col].astype(str).apply(
                    lambda x: x if len(x) <= 800 else f"[TRUNCATED: {len(x)} chars. Use batch_analyze_root_cause(span_ids='...') to see full content.]"
                )

        records = []
        for _, row in df.iterrows():
            records.append({
                "tool_duration": float(row['tool_duration']),
                "tool_name": row['tool_name'],
                "tool_args": row['tool_args'],
                "tool_status": row['tool_status'],
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
            "metadata": {"time_range": time_range, "view_id": TOOL_EVENTS_VIEW_ID},
            "impact_analysis": records
        }
        
        return json.dumps(result, cls=AnalysisEncoder)

    except Exception as e:
        logger.error(f"Error in get_tool_impact_analysis: {str(e)}")
        return json.dumps({"error": str(e)})

@cached_tool()
async def get_error_impact_analysis(
    time_range: str = "7d",
    limit: int = 10,
    view_ids: str = None # Legacy/Generic param
) -> str:
    """
    Aggregates error data from ALL four views with JOINED context to show true propagation.
    
    Args:
        time_range (str): Time range to analyze.
        limit (int): Max number of failed requests to return per category.
        view_ids (str): Optional. unused.

    Returns:
        str: JSON string containing lists of errors for each component type with parent status.
    """
    logger.info(f"[TOOL CALL-get_error_impact_analysis] time_range='{time_range}', limit={limit}")
    
    try:
        common_where = build_standard_where_clause(
            time_range=time_range,
            filter_config={"status": ("ERROR", "=")},
            table_alias="T"
        )
        
        # 1. Tool Errors (Joined with Agent and Root)
        query_tools = f"""
        SELECT 
            T.tool_name, 
            T.error_message, 
            T.timestamp, 
            T.tool_args,
            T.agent_name,
            COALESCE(A.status, 'UNKNOWN') as agent_status,
            I.root_agent_name,
            COALESCE(I.status, 'UNKNOWN') as root_status,
            I.content_text as user_message,
            T.trace_id, 
            T.span_id
        FROM `{PROJECT_ID}.{DATASET_ID}.{TOOL_EVENTS_VIEW_ID}` T
        LEFT JOIN `{PROJECT_ID}.{DATASET_ID}.{AGENT_EVENTS_VIEW_ID}` A ON T.parent_span_id = A.span_id
        LEFT JOIN `{PROJECT_ID}.{DATASET_ID}.{INVOCATION_EVENTS_VIEW_ID}` I ON T.trace_id = I.trace_id
        WHERE {common_where}
        ORDER BY T.timestamp DESC
        LIMIT {limit}
        """

        # 2. LLM Errors (Joined with Agent and Root)
        query_llm = f"""
        SELECT 
            T.model_name, 
            T.error_message, 
            T.timestamp, 
            T.llm_config,
            T.agent_name,
            COALESCE(A.status, 'UNKNOWN') as agent_status,
            I.root_agent_name,
            COALESCE(I.status, 'UNKNOWN') as root_status,
            I.content_text as user_message,
            T.trace_id, 
            T.span_id
        FROM `{PROJECT_ID}.{DATASET_ID}.{LLM_EVENTS_VIEW_ID}` T
        LEFT JOIN `{PROJECT_ID}.{DATASET_ID}.{AGENT_EVENTS_VIEW_ID}` A ON T.parent_span_id = A.span_id
        LEFT JOIN `{PROJECT_ID}.{DATASET_ID}.{INVOCATION_EVENTS_VIEW_ID}` I ON T.trace_id = I.trace_id
        WHERE {common_where}
        ORDER BY T.timestamp DESC
        LIMIT {limit}
        """

        # 3. Agent Errors (Joined with Root)
        query_agents = f"""
        SELECT 
            T.agent_name, 
            T.error_message, 
            T.timestamp, 
            T.root_agent_name,
            COALESCE(I.status, 'UNKNOWN') as root_status,
            I.content_text as user_message,
            T.trace_id, 
            T.span_id
        FROM `{PROJECT_ID}.{DATASET_ID}.{AGENT_EVENTS_VIEW_ID}` T
        LEFT JOIN `{PROJECT_ID}.{DATASET_ID}.{INVOCATION_EVENTS_VIEW_ID}` I ON T.trace_id = I.trace_id
        WHERE {common_where}
        ORDER BY T.timestamp DESC
        LIMIT {limit}
        """

        # 4. Root Invocation Errors
        query_root = f"""
        SELECT 
            T.root_agent_name, 
            T.error_message, 
            T.timestamp, 
            T.content_text as user_message,
            T.trace_id, 
            T.invocation_id
        FROM `{PROJECT_ID}.{DATASET_ID}.{INVOCATION_EVENTS_VIEW_ID}` T
        WHERE {common_where}
        ORDER BY T.timestamp DESC
        LIMIT {limit}
        """

        # Run all 4 queries in parallel
        results = await asyncio.gather(
            execute_bigquery(query_tools),
            execute_bigquery(query_llm),
            execute_bigquery(query_agents),
            execute_bigquery(query_root)
        )
        
        tool_df, llm_df, agent_df, root_df = results

        def to_records(df):
            if df.empty:
                return []
            if 'timestamp' in df.columns:
                df['timestamp'] = df['timestamp'].astype(str)
            
            # Sanitize all string columns to prevent markdown table breakage and truncate massive payloads
            for col in df.columns:
                if df[col].dtype == object or df[col].dtype == str:
                     df[col] = df[col].astype(str).apply(
                         lambda x: x if len(x) <= 800 else f"[TRUNCATED: {len(x)} chars. Use batch_analyze_root_cause(span_ids='...') to see full content.]"
                     ).apply(sanitize_for_markdown)
            
            return df.to_dict(orient="records")

        final_result = {
            "metadata": {"time_range": time_range, "limit": limit},
            "tool_errors": to_records(tool_df),
            "llm_errors": to_records(llm_df),
            "agent_errors": to_records(agent_df),
            "root_errors": to_records(root_df)
        }
        
        return json.dumps(final_result, cls=AnalysisEncoder)

    except Exception as e:
        logger.error(f"Error in get_error_impact_analysis: {str(e)}")
        return json.dumps({"error": str(e)})

