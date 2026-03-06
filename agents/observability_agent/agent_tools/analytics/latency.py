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

from .llm_diagnostics import logger
from .queries import (
    GET_LATENCY_DISTRIBUTION_QUERY,
    GET_LATENCY_PERFORMANCE_QUERY,
    GET_PAGINATED_EVENTS_QUERY,
    GET_ACTIVE_METADATA_QUERY,
    ANALYZE_ROOT_CAUSE_QUERY,
    GET_BASELINE_PERFORMANCE_QUERY,
    ANALYZE_LATENCY_TREND_QUERY,
    GET_LATENCY_GROUPED_JOINED_QUERY,
    GET_LATENCY_GROUPED_BASE_QUERY,
    GET_LATENCY_GROUPED_TOKEN_QUERY,
    GET_RAW_INVOCATIONS_QUERY,
    GET_RAW_AGENTS_QUERY
)
from ...config import (PROJECT_ID, DATASET_ID, LLM_EVENTS_VIEW_ID, DEFAULT_TIME_RANGE, CONNECTION_ID, DATASET_LOCATION,
                       INVOCATION_EVENTS_VIEW_ID, TOOL_EVENTS_VIEW_ID, AGENT_EVENTS_VIEW_ID, TOOLS_TO_EXCLUDE_STR,
                       LLM_SPECIFIC_COLUMNS, TOOL_SPECIFIC_COLUMNS, AGENT_SPECIFIC_COLUMNS, INVOCATION_SPECIFIC_COLUMNS,
                       COMMON_COLUMNS)
from ...utils.bq import execute_bigquery, format_dataframe_to_requests
from ...utils.caching import cached_tool
from ...utils.common import AnalysisEncoder, build_standard_where_clause, get_sort_clause

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
        
        query = GET_LATENCY_DISTRIBUTION_QUERY.format(
            latency_col=latency_col,
            target_table=target_table,
            where_clause=where_clause
        )
        
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
                f"group_by='{group_by}', filters=(agent='{agent_name}', root='{root_agent_name}', model='{model_name}'), "
                f"view_id='{target_table}', latency_col='{latency_col}'")

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
        
        query = GET_LATENCY_PERFORMANCE_QUERY.format(
            group_select=group_select,
            latency_col=latency_col,            target_table=target_table,
            where_clause=where_clause,
            group_clause=group_clause,
            group_select_final=group_select_final,
            join_clause=join_clause,
            group_clause_final=group_clause_final
        )

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
async def get_llm_requests(
    time_range: str = "24h",
    limit: int = 10,
    min_latency_ms: float = 0,
    model_name: Optional[str] = None,
    sort_by: str = "latest",
    failed_only: bool = False,
    exclude_zero_duration: bool = False,
    truncate: bool = False,
) -> str:
    """
    Fetch LLM requests with filtering and sorting options.

    Args:
        time_range (str): Time range to analyze (e.g. "24h", "7d", "all").
        limit (int): Maximum number of requests to return.
        min_latency_ms (float): Filter for requests slower than this threshold.
        model_name (str): Optional. Filter by specific model name.
        sort_by (str): Sorting criteria: "slowest", "fastest", "latest".
        failed_only (bool): If True, only return requests with status='ERROR'.
        exclude_zero_duration (bool): If True, exclude requests with 0ms duration.
        truncate (bool): Whether to truncate large payloads in the response.

    Returns:
        str: JSON string containing metadata and specific LLM request details.
    """
    logger.info(f"[TOOL CALL-get_llm_requests] "
                f"time_range='{time_range}', limit={limit}, sort_by='{sort_by}', "
                f"model_name='{model_name}', min_latency_ms={min_latency_ms}, "
                f"failed_only={failed_only}, exclude_zero_duration={exclude_zero_duration}, "
                f"truncate={truncate}")
    try:
        filter_config = {
            "model_name": (model_name, "=")
        }
        if failed_only:
            filter_config["status"] = ("ERROR", "=")

        if min_latency_ms > 0:
            filter_config["duration_ms"] = (str(min_latency_ms), ">")
        elif exclude_zero_duration:
            filter_config["duration_ms"] = (str(0), ">")

        where_clause = build_standard_where_clause(
            time_range=time_range,
            filter_config=filter_config
        )

        # Sorting Logic
        order_clause = get_sort_clause(sort_by, table_alias="T")

        llm_specific_columns_str = ",\n    ".join(f"T.{col}" for col in LLM_SPECIFIC_COLUMNS)
        common_columns_str = ",\n    ".join(f"T.{col}" for col in COMMON_COLUMNS)
        extra_selects = (
            "A.status AS agent_status,\n    "
            "A.duration_ms as agent_duration_ms,\n    "    
            "I.status AS root_status,\n    "
            "I.duration_ms as root_duration_ms,\n    "
            "I.content_text_summary"
        )
        joins = (
            f"LEFT JOIN `{PROJECT_ID}.{DATASET_ID}.{INVOCATION_EVENTS_VIEW_ID}` AS I ON T.trace_id = I.trace_id\n        "
            f"LEFT JOIN `{PROJECT_ID}.{DATASET_ID}.{AGENT_EVENTS_VIEW_ID}` AS A ON T.parent_span_id = A.span_id"
        )
        query = GET_PAGINATED_EVENTS_QUERY.format(
            specific_columns=f"{llm_specific_columns_str},\n    {extra_selects}",
            common_columns=common_columns_str,            view_id=LLM_EVENTS_VIEW_ID,
            joins=joins,
            where_clause=where_clause,
            order_clause=order_clause,
            limit=limit
        )

        df = await execute_bigquery(query)
        requests = format_dataframe_to_requests(df, truncate=truncate)

            
        result = {
            "metadata": {"time_range": time_range,
                         "limit": limit,
                         "min_latency_ms": min_latency_ms,
                         "failed_only": failed_only
                         },
            "requests": requests
        }
        
        return json.dumps(result, cls=AnalysisEncoder)
        
    except Exception as e:
        logger.error(f"Error in get_llm_requests: {str(e)}")
        return json.dumps({"error": str(e)})


@cached_tool()
async def get_tool_requests(
    time_range: str = "24h",
    limit: int = 10,
    min_latency_ms: float = 0,
    agent_name: Optional[str] = None,
    sort_by: str = "slowest",
    failed_only: bool = False,
    truncate: bool = False,
) -> str:
    """
    Fetch Tool executions with filtering and sorting options.

    Args:
        time_range (str): Time range to analyze (e.g. "24h", "7d", "all").
        limit (int): Maximum number of requests to return.
        min_latency_ms (float): Filter for requests slower than this threshold.
        agent_name (str): Optional. Filter by specific agent name.
        sort_by (str): Sorting criteria: "slowest", "fastest", "latest".
        failed_only (bool): If True, only return requests with status='ERROR'.
        truncate (bool): Whether to truncate large payloads in the response.

    Returns:
        str: JSON string containing metadata and specific Tool execution details.
    """
    logger.info(f"[TOOL CALL-get_tool_requests] time_range='{time_range}', limit={limit}, "
                f"min_latency_ms={min_latency_ms}, agent_name='{agent_name}', sort_by='{sort_by}', "
                f"failed_only={failed_only}, truncate={truncate}")
    try:
        filter_config = {
            "agent_name": (agent_name, "=")
        }
        if min_latency_ms > 0:
            filter_config["duration_ms"] = (str(min_latency_ms), ">")

        if failed_only:
            filter_config["status"] = ("ERROR", "=")

        where_clause = build_standard_where_clause(
            time_range=time_range,
            filter_config=filter_config
        )
        if TOOLS_TO_EXCLUDE_STR:
            where_clause += f" AND tool_name NOT IN ({TOOLS_TO_EXCLUDE_STR})"

        # Sorting Logic
        order_clause = get_sort_clause(sort_by, table_alias="T")

        tool_specific_columns_str = ",\n    ".join(f"T.{col}" for col in TOOL_SPECIFIC_COLUMNS)
        common_columns_str = ",\n    ".join(f"T.{col}" for col in COMMON_COLUMNS)

        extra_selects = (
            "A.status AS agent_status,\n    "
            "A.duration_ms as agent_duration_ms,\n    "
            "I.status AS root_status,\n    "
            "I.duration_ms as root_duration_ms,\n    "
            "I.content_text_summary"
        )
        joins = (
            f"LEFT JOIN `{PROJECT_ID}.{DATASET_ID}.{INVOCATION_EVENTS_VIEW_ID}` AS I ON T.trace_id = I.trace_id\n        "
            f"LEFT JOIN `{PROJECT_ID}.{DATASET_ID}.{AGENT_EVENTS_VIEW_ID}` AS A ON T.parent_span_id = A.span_id"
        )
        query = GET_PAGINATED_EVENTS_QUERY.format(
            specific_columns=f"{tool_specific_columns_str},\n    {extra_selects}",
            common_columns=common_columns_str,            view_id=TOOL_EVENTS_VIEW_ID,
            joins=joins,
            where_clause=where_clause,
            order_clause=order_clause,
            limit=limit
        )

        df = await execute_bigquery(query)
        requests = format_dataframe_to_requests(df, truncate=truncate)
            
        result = {
            "metadata": {"time_range": time_range,
                         "limit": limit,
                         "agent_name": agent_name,
                         "min_latency_ms": min_latency_ms
                         },
            "requests": requests
        }
        
        return json.dumps(result, cls=AnalysisEncoder)
        
    except Exception as e:
        logger.error(f"Error in get_tool_requests: {str(e)}")
        return json.dumps({"error": str(e)})


@cached_tool()
async def get_agent_requests(
    time_range: str = "24h",
    limit: int = 10,
    min_latency_ms: float = 0,
    agent_name: Optional[str] = None,
    order_type: Optional[str] = "DESC",
    sort_by: str = "slowest",
    failed_only: bool = False,
    exclude_zero_duration: bool = False,
    exclude_root_agent: bool = False,
    truncate: bool = False,
) -> str:
    """
    Fetch Agent executions with filtering and sorting options.

    Args:
        time_range (str): Time range to analyze.
        limit (int): Max number of requests.
        min_latency_ms (float): Min latency filter.
        agent_name (str): Filter by agent name.
        order_type (str): DEPRECATED. Sort order for duration.
        sort_by (str): Sorting criteria: "slowest", "fastest", "latest".
        failed_only (bool): If True, only return requests with status='ERROR'.
        exclude_zero_duration (bool): If True, exclude requests with 0ms duration.
        exclude_root_agent (bool): If True, excludes requests where agent_name matches root_agent_name.
        truncate (bool): Truncate large fields.
        
    Returns:
        str: JSON string containing metadata and specific Agent execution details.
    """
    logger.info(f"[TOOL CALL-get_agent_requests] "
                f"time_range='{time_range}', limit={limit}, sort_by='{sort_by}', "
                f"agent_name='{agent_name}', order_type='{order_type}', exclude_root_agent={exclude_root_agent}"
                f"min_latency_ms={min_latency_ms}, failed_only={failed_only}, "
                f"exclude_zero_duration={exclude_zero_duration}, truncate={truncate}")
    try:
        filter_config = {
            "agent_name": (agent_name, "=")
        }
        if failed_only:
            filter_config["status"] = ("ERROR", "=")

        if min_latency_ms > 0:
            filter_config["duration_ms"] = (str(min_latency_ms), ">")
        if exclude_zero_duration:
            filter_config["duration_ms"] = (str(0), ">")

        extra_filters = []
        if exclude_root_agent:
            extra_filters.append("T.agent_name != T.root_agent_name")

        where_clause = build_standard_where_clause(
            time_range=time_range,
            filter_config=filter_config,
            extra_filters=extra_filters
        )

        # Sorting Logic
        order_clause = get_sort_clause(sort_by, order_type, table_alias="T")

        agent_specific_columns_str = ",\n    ".join(f"T.{col}" for col in AGENT_SPECIFIC_COLUMNS)
        common_columns_str = ",\n    ".join(f"T.{col}" for col in COMMON_COLUMNS)

        extra_selects = (
            "I.status AS root_status,\n    "
            "I.duration_ms as root_duration_ms,\n    "
            "I.content_text_summary"
        )
        joins = f"LEFT JOIN `{PROJECT_ID}.{DATASET_ID}.{INVOCATION_EVENTS_VIEW_ID}` AS I ON T.trace_id = I.trace_id"
        
        query = GET_PAGINATED_EVENTS_QUERY.format(
            specific_columns=f"{agent_specific_columns_str},\n    {extra_selects}",
            common_columns=common_columns_str,            view_id=AGENT_EVENTS_VIEW_ID,
            joins=joins,
            where_clause=where_clause,
            order_clause=order_clause,
            limit=limit
        )

        df = await execute_bigquery(query)

        # Added safety check for empty dataframes
        if df.empty:
            return json.dumps({
                "message": "No data found for Agents."
            })

        requests = format_dataframe_to_requests(df, truncate=truncate)

        result = {
            "metadata": {"time_range": time_range, "limit": limit, "min_latency_ms": min_latency_ms,
                         "agent_name": agent_name, "failed_only": failed_only},
            "requests": requests
        }

        return json.dumps(result, cls=AnalysisEncoder)

    except Exception as e:
        logger.error(f"Error in get_agent_requests: {str(e)}")
        return json.dumps({"error": str(e)})

@cached_tool()
async def get_invocation_requests(
    time_range: str = "24h",
    limit: int = 10,
    min_latency_ms: float = 0,
    root_agent_name: Optional[str] = None,
    order_type: Optional[str] = "DESC",
    sort_by: str = "slowest",
    failed_only: bool = False,
    exclude_zero_duration: bool = False,
    truncate: bool = False,
) -> str:
    """
    Fetch Invocation (Root Agent) requests with filtering and sorting options.
    
    Args:
        time_range (str): Time range to analyze.
        limit (int): Max number of requests.
        min_latency_ms (float): Min latency filter.
        root_agent_name (str): Filter by root agent name.
        order_type (str): DEPRECATED. Sort order for duration.
        sort_by (str): Sorting criteria: "slowest", "fastest", "latest".
        failed_only (bool): If True, only return requests with status='ERROR'.
        exclude_zero_duration (bool): If True, exclude requests with 0ms duration.
        truncate (bool): Truncate large fields.
        
    Returns:
        str: JSON string containing metadata and specific Invocation details.
    """
    logger.info(f"[TOOL CALL-get_invocation_requests] "
                f"time_range='{time_range}', limit={limit}, sort_by='{sort_by}', "
                f"root_agent_name='{root_agent_name}', order_type='{order_type}', "
                f"min_latency_ms={min_latency_ms}, failed_only={failed_only}, "
                f"exclude_zero_duration={exclude_zero_duration}, truncate={truncate}")
    try:
        filter_config = {
            "root_agent_name": (root_agent_name, "=")
        }
        if min_latency_ms > 0:
            filter_config["duration_ms"] = (str(min_latency_ms), ">")
        elif exclude_zero_duration:
            filter_config["duration_ms"] = (str(0), ">")

        if failed_only:
            filter_config["status"] = ("ERROR", "=")

        where_clause = build_standard_where_clause(
            time_range=time_range,
            filter_config=filter_config
        )

        # Sorting Logic
        order_clause = get_sort_clause(sort_by, order_type, table_alias="T")

        invocation_specific_columns_str = ",\n    ".join(f"T.{col}" for col in INVOCATION_SPECIFIC_COLUMNS)
        
        # INVOCATION view does not have parent_span_id (it is a root event)
        invocation_common_cols = [col for col in COMMON_COLUMNS if col != 'parent_span_id']
        common_columns_str = ",\n    ".join(f"T.{col}" for col in invocation_common_cols)

        query = GET_PAGINATED_EVENTS_QUERY.format(
            specific_columns=invocation_specific_columns_str,
            common_columns=common_columns_str,            view_id=INVOCATION_EVENTS_VIEW_ID,
            joins="",
            where_clause=where_clause,
            order_clause=order_clause,
            limit=limit
        )

        df = await execute_bigquery(query)
        requests = format_dataframe_to_requests(df, truncate=truncate)
            
        result = {
            "metadata": {"time_range": time_range, "limit": limit, "min_latency_ms": min_latency_ms,
                         "root_agent_name": root_agent_name},
            "requests": requests
        }
        
        return json.dumps(result, cls=AnalysisEncoder)
        
    except Exception as e:
        logger.error(f"Error in get_invocation_requests: {str(e)}")
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
        percentile (float): The percentile value to calculate (e.g., 95.0 for p95).

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

            query = GET_LATENCY_GROUPED_JOINED_QUERY.format(
                select_group_sql=select_group_sql,
                latency_col=latency_col,
                percentile=percentile,
                where_clause_joined=where_clause_joined,
                group_by_sql=group_by_sql
            )
        
        else:
            # ORIGINAL LOGIC for single table
            token_metrics_sql = ""
            if str(target_table) == str(LLM_EVENTS_VIEW_ID):
                 token_metrics_sql = f""",
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

            query = GET_LATENCY_GROUPED_BASE_QUERY.format(
                select_group_cols=select_group_cols,
                latency_col=latency_col,
                percentile=percentile,
                optional_token_metrics=token_metrics_sql,
                target_table=target_table,
                where_clause=where_clause,
                group_by_clause=group_by_clause
            )
        
        df = await execute_bigquery(query)
        
        token_df = pd.DataFrame()
        if str(target_table) != str(LLM_EVENTS_VIEW_ID) and any(g in ["agent_name", "root_agent_name"] for g in group_columns):
            token_query = GET_LATENCY_GROUPED_TOKEN_QUERY.format(
                select_group_cols=select_group_cols,
                where_clause=where_clause,
                group_by_clause=group_by_clause
            )
            token_df = await execute_bigquery(token_query)
        
        if df.empty:
            return json.dumps({
                "message": "No data found for metrics.",
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
            query = GET_ACTIVE_METADATA_QUERY.format(
                column_name=column_name,                target_table=target_table,
                where_clause=where_clause,
                limit=limit
            )
            
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
        
        query = ANALYZE_ROOT_CAUSE_QUERY.format(
            id_column=id_column,
            connection_id=connection_id,
            model_endpoint=model_endpoint,            target_table=target_table,
            span_id=span_id
        )
        
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
        
        query = GET_BASELINE_PERFORMANCE_QUERY.format(
            group_by=group_by,
            latency_col=latency_col,            target_table=target_table,
            where_clause=where_clause,
            limit_percentile=limit_percentile
        )
        
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
async def analyze_latency_trend(
    group_by: str,
    view_id: str,
    time_range: str = "30d",
    bucket_size: str = "1d"
) -> str:
    """
    Analyzes the temporal trend of latency and errors by chopping the time array into distinct chronological buckets.
    Used exclusively by Playbook C to determine if slopes are degrading or improving over long periods of time.

    Args:
        group_by (str): Dimension to group by. One of: "agent_name", "model_name", "tool_name".
        view_id (str): BigQuery table/view ID to query. Must be one of: "agent_events_view", "llm_events_view", "tool_events_view".
        time_range (str): Time range to analyze (e.g. "30d", "24h"). Default is "30d".
        bucket_size (str): Size of each time bucket (e.g. "1d", "1h", "7d"). Default is "1d".

    Returns:
        str: JSON string containing trend analysis data grouped by the specified dimension.
    """
    logger.info(f"[TOOL CALL-analyze_latency_trend] group_by='{group_by}', view_id='{view_id}', "
                f"time_range='{time_range}', bucket_size='{bucket_size}'")
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
        
        query = ANALYZE_LATENCY_TREND_QUERY.format(
            group_by=group_by,
            bq_interval=bq_interval,
            view_id=view_id,
            clean_where_clause=clean_where_clause
        )
        
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


from ...config import MAX_RAW_RECORDS_LIMIT

@cached_tool()
async def get_raw_invocation_events(time_range: str = "24h", limit: int = MAX_RAW_RECORDS_LIMIT) -> str:
    """Fetches raw E2E invocation event data from BigQuery."""
    logger.info(f"[TOOL CALL-get_raw_invocation_events] time_range='{time_range}', limit={limit}")
    where_clause = build_standard_where_clause(time_range=time_range)
    query = GET_RAW_INVOCATIONS_QUERY.format(where_clause=where_clause, limit=limit)
    try:
        df = await execute_bigquery(query)
        if df.empty: return "[]"
        return df.to_json(orient="records", default_handler=str)
    except Exception as e:
        logger.error(f"Failed to fetch raw invocation data: {e}")
        return json.dumps({"error": str(e)})

@cached_tool()
async def get_raw_agent_events(time_range: str = "24h", limit: int = MAX_RAW_RECORDS_LIMIT) -> str:
    """Fetches raw Agent execution event data from BigQuery."""
    logger.info(f"[TOOL CALL-get_raw_agent_events] time_range='{time_range}', limit={limit}")
    where_clause = build_standard_where_clause(time_range=time_range)
    query = GET_RAW_AGENTS_QUERY.format(where_clause=where_clause, limit=limit)
    try:
        df = await execute_bigquery(query)
        if df.empty: return "[]"
        return df.to_json(orient="records", default_handler=str)
    except Exception as e:
        logger.error(f"Failed to fetch raw agent data: {e}")
        return json.dumps({"error": str(e)})

