"""
Analytics tools for detailed diagnostics and debugging of Google model performance.

We investigate LLM model performance by looking into llm requests/responses (model-level).

This module contains tools for "deep dive" analysis:
- Identifying slow queries and outliers
- Analyzing concurrent request impact
- Cluster analysis for slow queries
- Single query inspection
"""
import json
import logging
from typing import Optional

import pandas as pd
from google.cloud import bigquery

from ...config import (PROJECT_ID, DATASET_ID, LLM_EVENTS_VIEW_ID, INVOCATION_EVENTS_VIEW_ID, AGENT_EVENTS_VIEW_ID,
                       DEFAULT_TIME_RANGE)
from ...utils.bq import execute_bigquery, run_query_async
from ...utils.caching import cached_tool
from ...utils.common import AnalysisEncoder, build_standard_where_clause
from ...utils.telemetry import trace_span

logger = logging.getLogger(__name__)


@trace_span()
@cached_tool()
async def analyze_latency_groups(
    time_range: str = DEFAULT_TIME_RANGE,
    threshold_ms: int = 0,
    model_name: Optional[str] = None,
    agent_name: Optional[str] = None,
    root_agent_name: Optional[str] = None,
    limit: int = 20
) -> str:
    """
    Analyze latency groups (clustering by agent/model) with optional threshold.
    
    Unifies outlier analysis (threshold > 0) and general clustering (threshold = 0).

    Args:
        time_range (str): Time range to analyze (e.g., "24h", "7d", "all").
        threshold_ms (int): Latency threshold in milliseconds. 
                           If > 0, analyzes only requests exceeding this threshold (Outliers).
                           If 0, analyzes all requests (Clustering).
        model_name (str): Optional. Filter by specific model.
        agent_name (str): Optional. Filter by specific agent name.
        root_agent_name (str): Optional. Filter by root agent name.
        limit (int): Maximum number of groups to return. Defaults to 20.

    Returns:
        str: JSON string containing a list of groups with count and latency stats.
    """
    tool_mode = "Outlier Analysis" if threshold_ms > 0 else "Cluster Analysis"
    logger.info(f"[TOOL CALL-analyze_latency_groups] mode='{tool_mode}', time_range='{time_range}', "
                f"threshold_ms={threshold_ms}, model_name='{model_name}', agent_name='{agent_name}',"
                f" root_agent_name='{root_agent_name}', limit={limit}")
    try:
        filter_config = {
            "model_name": (model_name, "="),
            "agent_name": (agent_name, "="),
            "root_agent_name": (root_agent_name, "="),
        }
        if threshold_ms > 0:
            filter_config["duration_ms"] = (threshold_ms, ">")

        where_clause = build_standard_where_clause(
            time_range=time_range,
            filter_config=filter_config
        )
        
        query = f"""
        SELECT
          T.agent_name,
          T.root_agent_name,
          T.model_name,
          COUNT(*) as count,
          AVG(duration_ms) as avg_latency_ms,
          MIN(duration_ms) as min_latency_ms,
          MAX(duration_ms) as max_latency_ms,
          STDDEV(duration_ms) as std_latency_ms
        FROM `{PROJECT_ID}.{DATASET_ID}.{LLM_EVENTS_VIEW_ID}` AS T
        WHERE {where_clause}
        GROUP BY root_agent_name, agent_name, model_name
        ORDER BY count DESC
        LIMIT {limit}
        """

        df = await execute_bigquery(query)
        
        if df.empty:
            return json.dumps({"message": f"No data found for {tool_mode} > {threshold_ms}ms"})
            
        groups = []
        for _, row in df.iterrows():
            groups.append({
                "root_agent_name": row['root_agent_name'],
                "agent_name": row['agent_name'],
                "model_name": row['model_name'],
                "count": int(row['count']),
                "avg_latency_ms": float(row['avg_latency_ms']),
                "min_latency_ms": float(row['min_latency_ms']),
                "max_latency_ms": float(row['max_latency_ms']),
                "std_latency_ms": float(row['std_latency_ms']) if pd.notna(row['std_latency_ms']) else 0.0
            })
            
        result = {
            "metadata": {"time_range": time_range, "threshold_ms": threshold_ms, "mode": tool_mode,
                         "root_agent_name": root_agent_name,
                         "agent_name": agent_name, "model_name": model_name, "limit": limit},
            "groups": groups
        }
        
        return json.dumps(result, cls=AnalysisEncoder)
        
    except Exception as e:
        logger.error(f"Error in analyze_latency_groups: {str(e)}")
        return json.dumps({"error": str(e)})


@trace_span()
@cached_tool()
async def get_concurrent_request_impact(
    time_range: str = DEFAULT_TIME_RANGE,
    agent_name: Optional[str] = None,
    root_agent_name: Optional[str] = None,
    model_name: Optional[str] = None
) -> str:
    """
    Analyze the impact of concurrent requests on latency.
    
    Args:
        time_range (str): Time range to analyze.
        agent_name (str): Optional. Filter by agent name.
        root_agent_name (str): Optional. Filter by root agent name.
        model_name (str): Optional. Filter by model version.

    Returns:
        str: JSON string containing concurrency impact analysis.
    """
    logger.info(f"[TOOL CALL-get_concurrent_request_impact] time_range='{time_range}', "
                f"agent_name='{agent_name}', root_agent_name='{root_agent_name}', model_name='{model_name}'")
    try:
        where_clause = build_standard_where_clause(
            time_range=time_range,
            filter_config={
                "agent_name": (agent_name, "="),
                "root_agent_name": (root_agent_name, "="),
                "model_name": (model_name, "=")
            }
        )
        
        # Using TIMESTAMP_TRUNC to minute.
        query = f"""
        WITH ConcurrencyCounts AS (
            SELECT
                TIMESTAMP_TRUNC(timestamp, MINUTE) as time_bucket,
                COUNT(*) as concurrent_requests,
                AVG(duration_ms) as avg_latency_in_bucket
            FROM `{PROJECT_ID}.{DATASET_ID}.{LLM_EVENTS_VIEW_ID}` AS T
            WHERE {where_clause}
            GROUP BY time_bucket
        )
        SELECT
            concurrent_requests,
            AVG(avg_latency_in_bucket) as avg_latency_for_level,
            COUNT(*) as occurrences
        FROM ConcurrencyCounts
        GROUP BY concurrent_requests
        ORDER BY concurrent_requests ASC
        """
        
        df = await execute_bigquery(query)
        
        if df.empty:
            return json.dumps({"message": "No concurrent request data found."})
            
        impact_data = []
        for _, row in df.iterrows():
            impact_data.append({
                "concurrent_requests": int(row['concurrent_requests']),
                "avg_latency_ms": float(row['avg_latency_for_level']),
                "occurrences": int(row['occurrences'])
            })
            
        result = {
            "metadata": {"time_range": time_range, "agent_name": agent_name,
                         "root_agent_name": root_agent_name, "model_name": model_name},
            "data": impact_data,
            "correlation": "Positive correlation implies queuing/resource contention."
        }
        
        return json.dumps(result, cls=AnalysisEncoder)

    except Exception as e:
        logger.error(f"Error in get_concurrent_request_impact: {str(e)}")
        return json.dumps({"error": str(e)})


@trace_span()
@cached_tool()
async def analyze_request_queuing(
    time_range: str = DEFAULT_TIME_RANGE,
    agent_name: Optional[str] = None,
    root_agent_name: Optional[str] = None,
    model_name: Optional[str] = None
) -> str:
    """
    Analyze request queuing behaviors.
    
    Args:
        time_range (str): Time range to analyze.
        agent_name (str): Optional. Filter by agent name.
        root_agent_name (str): Optional. Filter by root agent name.
        model_name (str): Optional. Filter by model version.

    Returns:
        str: JSON string containing burst analysis.
    """
    logger.info(f"[TOOL CALL-analyze_request_queuing] time_range='{time_range}', "
                f"agent_name='{agent_name}', root_agent_name='{root_agent_name}', model_name='{model_name}'")
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
        WITH Bursts AS (
             SELECT
                TIMESTAMP_TRUNC(timestamp, SECOND) as second_bucket,
                COUNT(*) as requests_per_second
             FROM `{PROJECT_ID}.{DATASET_ID}.{LLM_EVENTS_VIEW_ID}` AS T
             WHERE {where_clause}
             GROUP BY second_bucket
             HAVING requests_per_second > 1
        )
        SELECT
            requests_per_second,
            COUNT(*) as burst_count
        FROM Bursts
        GROUP BY requests_per_second
        ORDER BY requests_per_second DESC
        """
        
        df = await execute_bigquery(query)
        bursts = []
        if not df.empty:
            for _, row in df.iterrows():
                bursts.append({
                    "requests_per_second": int(row['requests_per_second']),
                    "burst_count": int(row['burst_count'])
                })
                
        result = {
            "metadata": {"time_range": time_range, "agent_name": agent_name,
                         "root_agent_name": root_agent_name, "model_name": model_name},
            "bursts": bursts,
            "summary": "High burst counts indicate likely queuing."
        }
        return json.dumps(result, cls=AnalysisEncoder)
    except Exception as e:
        logger.error(f"Error in analyze_request_queuing: {e}")
        return json.dumps({"error": str(e)})


@trace_span()
@cached_tool()
async def get_config_outliers(
    time_range: str = DEFAULT_TIME_RANGE,
    agent_name: Optional[str] = None,
    root_agent_name: Optional[str] = None,
    model_name: Optional[str] = None,
    config_keys: Optional[list[str]] = None,
    limit: int = 20,
) -> str:
    """
    Identify outlier configurations (e.g., high temperature) that correlate with high latency.
    
    Args:
        time_range (str): Time range to analyze.
        agent_name (str): Optional. Filter by agent name.
        root_agent_name (str): Optional. Filter by root agent name.
        model_name (str): Optional. Filter by model version.
        config_keys (list[str]): Optional. List of config keys to analyze. 
                                Defaults to ['temperature', 'max_output_tokens', 'top_p', 'top_k'].

    Returns:
        str: JSON string containing config outlier stats.
    """
    if config_keys is None:
        config_keys = ['temperature', 'max_output_tokens', 'top_p', 'top_k']
        
    logger.info(f"[TOOL CALL-get_config_outliers] time_range='{time_range}', "
                f"agent_name='{agent_name}', root_agent_name='{root_agent_name}', "
                f"model_name='{model_name}', config_keys={config_keys}")
    try:
        where_clause = build_standard_where_clause(
            time_range=time_range,
            filter_config={
                "agent_name": (agent_name, "="),
                "root_agent_name": (root_agent_name, "="),
                "model_name": (model_name, "=")
            }
        )
        
        # Build dynamic columns for config keys
        config_selects = []
        group_by_cols = ["agent_name", "model_name"]
        
        for key in config_keys:
            # Extract value from JSON, default to 'default' if missing (assume system default)
            # We try to cast to STRING for uniformity in grouping
            col_alias = f"config_{key}"
            config_selects.append(f"COALESCE(JSON_VALUE(llm_config, '$.{key}'), 'default') AS {col_alias}")
            group_by_cols.append(col_alias)
            
        config_select_str = ",\n            ".join(config_selects)
        group_by_str = ", ".join(group_by_cols)
        
        query = f"""
        SELECT
            agent_name,
            model_name,
            {config_select_str},
            AVG(duration_ms) as avg_latency,
            STDDEV(duration_ms) as stddev_latency,
            COUNT(*) as request_count
        FROM `{PROJECT_ID}.{DATASET_ID}.{LLM_EVENTS_VIEW_ID}` AS T
        WHERE {where_clause}
        GROUP BY {group_by_str}
        HAVING request_count > 5
        ORDER BY avg_latency DESC
        LIMIT {limit}
        """
        
        df = await execute_bigquery(query)
        outliers = []
        if not df.empty:
            for _, row in df.iterrows():
                # Reconstruct config dict
                config_settings = {}
                for key in config_keys:
                    col_alias = f"config_{key}"
                    val = row[col_alias]
                    # Try to convert numeric strings back to numbers for cleaner JSON
                    try:
                        if val != 'default':
                            if '.' in val:
                                val = float(val)
                            else:
                                val = int(val)
                    except (ValueError, TypeError):
                        pass
                    config_settings[key] = val

                outliers.append({
                    "agent_name": row['agent_name'],
                    "model_name": row['model_name'],
                    "config": config_settings,
                    "avg_latency_ms": float(row['avg_latency']),
                    "stddev_latency_ms": 0.0 if pd.isna(row['stddev_latency']) else float(row['stddev_latency']),
                    "request_count": int(row['request_count'])
                })
                
        result = {
            "metadata": {"time_range": time_range, "agent_name": agent_name,
                         "root_agent_name": root_agent_name, "model_name": model_name,
                         "analyzed_keys": config_keys},
            "outliers": outliers
        }
        return json.dumps(result, cls=AnalysisEncoder)
    except Exception as e:
        logger.error(f"Error in get_config_outliers: {e}")
        return json.dumps({"error": str(e)})



@trace_span()
@cached_tool()
async def fetch_single_query(span_id: str) -> str:
    """
    Fetches a single query's full details by span_id.
    """
    logger.info(f"[TOOL CALL-fetch_single_query] fetch_single_query(span_id='{span_id}')")
    try:
        # Query the view directly
        query = f"""
        SELECT
          T.timestamp,
          T.span_id,
          T.full_request,
          T.full_response,
          T.model_name,
          T.agent_name,
          T.duration_ms,
          T.thoughts_token_count,
          T.candidates_token_count AS output_token_count,
          T.prompt_token_count,
          T.total_token_count
        FROM `{PROJECT_ID}.{DATASET_ID}.{LLM_EVENTS_VIEW_ID}` AS T
        WHERE CAST(T.span_id AS STRING) = @span_id
        LIMIT 1
        """

        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("span_id", "STRING", str(span_id))
            ]
        )

        # Use helper for async execution
        df = await run_query_async(query, job_config=job_config)

        if df.empty:
            return json.dumps({"error": f"No record found for span_id: {span_id}"})

        row = df.iloc[0]
        # Handle cases where full_request/response are already dicts or strings
        full_req = row['full_request']
        if isinstance(full_req, str):
            try:
                full_req = json.loads(full_req)
            except:
                pass
            
        full_resp = row['full_response']
        if isinstance(full_resp, str):
            try:
                full_resp = json.loads(full_resp)
            except:
                pass

        record = {
            "timestamp": row['timestamp'].isoformat() if hasattr(row['timestamp'], 'isoformat') else str(row['timestamp']),
            "span_id": row['span_id'],
            "full_request": full_req,
            "full_response": full_resp,
            "model_name": row['model_name'],
            "agent_name": row['agent_name'],
            "duration_ms": float(row['duration_ms']) if pd.notna(row['duration_ms']) else None,
            "thoughts_token_count": int(row['thoughts_token_count']) if pd.notna(row['thoughts_token_count']) else None,
            "output_token_count": int(row['output_token_count']) if pd.notna(row['output_token_count']) else None,
            "prompt_token_count": int(row['prompt_token_count']) if pd.notna(row['prompt_token_count']) else None,
            "total_token_count": int(row['total_token_count']) if pd.notna(row['total_token_count']) else None
        }

        return json.dumps(record, cls=AnalysisEncoder, default=str)

    except Exception as e:
        error_msg = f"Error fetching query {span_id}: {str(e)}"
        logger.error(f"[PROGRESS] Failed to fetch query {span_id}: {str(e)}")
        return json.dumps({"error": error_msg})



@trace_span()
@cached_tool()
async def analyze_empty_llm_responses(
    time_range: str = DEFAULT_TIME_RANGE,
    agent_name: Optional[str] = None,
    root_agent_name: Optional[str] = None,
    model_name: Optional[str] = None,
    limit: int = 20
) -> str:
    """
    Identify cases where the LLM returned 0 output tokens.
    
    Args:
        time_range (str): Time range to analyze.
        agent_name (str): Optional. Filter by agent name.
        root_agent_name (str): Optional. Filter by root agent name.
        model_name (str): Optional. Filter by model version.
        limit (int): Max number of detailed records to return.

    Returns:
        str: JSON string containing summary stats and individual trace records.
    """
    logger.info(f"[TOOL CALL-analyze_empty_llm_responses] time_range='{time_range}', limit={limit}, "
                f"agent_name='{agent_name}', root_agent_name='{root_agent_name}', model_name='{model_name}'")
    try:
        where_clause = build_standard_where_clause(
            time_range=time_range,
            filter_config={
                "agent_name": (agent_name, "="),
                "root_agent_name": (root_agent_name, "="),
                "model_name": (model_name, "=")
            }
        )
        
        # We only care about explicit empty responses that are not just pending
        # IFNULL handles cases where it might be explicitly null but completed.
        where_clause += " AND (T.candidates_token_count = 0 OR IFNULL(T.candidates_token_count, 0) = 0)"

        # 1. Get summary stats
        summary_query = f"""
        SELECT
            model_name,
            agent_name,
            COUNT(*) as empty_response_count
        FROM `{PROJECT_ID}.{DATASET_ID}.{LLM_EVENTS_VIEW_ID}` AS T
        WHERE {where_clause}
        GROUP BY model_name, agent_name
        ORDER BY empty_response_count DESC
        """
        
        summary_df = await execute_bigquery(summary_query)
        stats = []
        if not summary_df.empty:
            for _, row in summary_df.iterrows():
                stats.append({
                    "model_name": row['model_name'],
                    "agent_name": row['agent_name'],
                    "empty_response_count": int(row['empty_response_count'])
                })

        # 2. Get detailed records
        records_query = f"""
        SELECT
            T.span_id,
            T.trace_id,
            T.timestamp,
            T.model_name,
            T.agent_name,
            T.prompt_token_count,
            T.duration_ms as duration_ms,
            SUBSTR(CAST(I.content_text AS STRING), 1, 250) as user_message_trunk
        FROM `{PROJECT_ID}.{DATASET_ID}.{LLM_EVENTS_VIEW_ID}` AS T
        LEFT JOIN `{PROJECT_ID}.{DATASET_ID}.{INVOCATION_EVENTS_VIEW_ID}` I ON T.trace_id = I.trace_id
        WHERE {where_clause}
        ORDER BY timestamp DESC
        LIMIT {limit}
        """
        
        records_df = await execute_bigquery(records_query)
        records = []
        if not records_df.empty:
            for _, row in records_df.iterrows():
                records.append({
                    "span_id": str(row['span_id']),
                    "trace_id": str(row['trace_id']) if pd.notna(row['trace_id']) else None,
                    "timestamp": row['timestamp'].isoformat() if hasattr(row['timestamp'], 'isoformat') else str(row['timestamp']),
                    "model_name": row['model_name'],
                    "agent_name": row['agent_name'],
                    "prompt_tokens": int(row['prompt_token_count']) if pd.notna(row['prompt_token_count']) else 0,
                    "duration_ms": float(row['duration_ms']) if pd.notna(row['duration_ms']) else 0.0,
                    "user_message": row['user_message_trunk'] if pd.notna(row['user_message_trunk']) else None
                })

        result = {
            "metadata": {"time_range": time_range, "limit": limit, "agent_name": agent_name, 
                         "root_agent_name": root_agent_name, "model_name": model_name},
            "stats": stats,
            "records": records
        }
        
        return json.dumps(result, cls=AnalysisEncoder)

    except Exception as e:
        logger.error(f"Error in analyze_empty_llm_responses: {str(e)}")
        return json.dumps({"error": str(e)})
