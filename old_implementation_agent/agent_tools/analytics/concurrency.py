"""
Analytics tools for tracing execution concurrency and identifying architectural bottlenecks.
"""
import json
import logging
from typing import Optional

import pandas as pd

from ...config import PROJECT_ID, DATASET_ID, DEFAULT_TIME_RANGE
from ...utils.bq import execute_bigquery
from ...utils.caching import cached_tool
from ...utils.common import AnalysisEncoder

logger = logging.getLogger(__name__)

@cached_tool()
async def analyze_trace_concurrency(
    session_id: str,
) -> str:
    """
    Analyzes the execution timeline of a specific session to determine if tasks ran 
    sequentially or concurrently. This provides mathematical evidence for architectural suggestions.
    
    Args:
        session_id (str): The session_id of the trace to analyze.

    Returns:
        str: JSON string containing overlapping span analysis and sequential bottlenecks.
    """
    logger.info(f"[TOOL CALL-analyze_trace_concurrency] session_id='{session_id}'")
    
    try:
        query = f"""
        WITH all_events AS (
            SELECT span_id, parent_span_id as parent_id, timestamp as start_time, duration_ms, session_id, agent_name as name, 'Agent' as type 
            FROM `{PROJECT_ID}.{DATASET_ID}.agent_events_view` 
            WHERE session_id = '{session_id}'
            UNION ALL
            SELECT span_id, parent_span_id as parent_id, timestamp as start_time, duration_ms, session_id, model_name as name, 'LLM' as type 
            FROM `{PROJECT_ID}.{DATASET_ID}.llm_events_view` 
            WHERE session_id = '{session_id}'
            UNION ALL
            SELECT span_id, parent_span_id as parent_id, timestamp as start_time, duration_ms, session_id, tool_name as name, 'Tool' as type 
            FROM `{PROJECT_ID}.{DATASET_ID}.tool_events_view` 
            WHERE session_id = '{session_id}'
        ),
        events_with_end AS (
            SELECT 
                *,
                TIMESTAMP_ADD(start_time, INTERVAL CAST(duration_ms AS INT64) MILLISECOND) as end_time
            FROM all_events
        ),
        parent_stats AS (
            SELECT 
                p.span_id as parent_span_id,
                p.name as parent_name,
                p.type as parent_type,
                p.duration_ms as parent_duration,
                COUNT(c.span_id) as num_children,
                SUM(c.duration_ms) as sum_child_durations,
                MIN(c.start_time) as first_child_start,
                MAX(c.end_time) as last_child_end
            FROM events_with_end p
            JOIN events_with_end c ON c.parent_id = p.span_id
            GROUP BY 1, 2, 3, 4
        )
        SELECT 
            parent_span_id,
            parent_name,
            parent_type,
            parent_duration,
            num_children,
            sum_child_durations,
            TIMESTAMP_DIFF(last_child_end, first_child_start, MILLISECOND) as absolute_wall_clock_time,
            (sum_child_durations / NULLIF(TIMESTAMP_DIFF(last_child_end, first_child_start, MILLISECOND), 0)) as overlap_ratio
        FROM parent_stats
        WHERE num_children > 1
        ORDER BY overlap_ratio DESC
        """
        
        df = await execute_bigquery(query)
        
        if df.empty:
            return json.dumps({
                "message": f"No concurrent relationships found for session {session_id}.", 
                "metadata": {"session_id": session_id}
            })
            
        records = df.to_dict(orient="records")
        bottlenecks = []
        for r in records:
            ratio = float(r.get('overlap_ratio') or 0.0)
            if ratio >= 0.9 and ratio <= 1.1:
                bottleneck_note = "Strictly Sequential (No Overlap). Architectural Parallelization RECOMMENDED if mathematically possible."
            elif ratio > 1.1:
                bottleneck_note = "Concurrent Execution Detected. Parallelization ALREADY present."
            else:
                bottleneck_note = "Gaps in execution or mixed concurrency."
            
            bottlenecks.append({
                "parent_span_id": r['parent_span_id'],
                "parent_name": r['parent_name'],
                "parent_duration_ms": r['parent_duration'],
                "num_children": r['num_children'],
                "sum_child_durations_ms": r['sum_child_durations'],
                "absolute_wall_clock_time_ms": r['absolute_wall_clock_time'],
                "overlap_ratio": ratio,
                "analysis": bottleneck_note
            })
            
        result = {
            "metadata": {"session_id": session_id},
            "concurrency_analysis": bottlenecks
        }
        
        return json.dumps(result, cls=AnalysisEncoder)
        
    except Exception as e:
        logger.error(f"Error in analyze_trace_concurrency: {str(e)}")
        return json.dumps({"error": str(e)})


@cached_tool()
async def detect_sequential_bottlenecks(
    time_range: str = DEFAULT_TIME_RANGE
) -> str:
    """
    Proactively scans the last 24 hours to find parents that executed 
    multiple children sequentially rather than concurrently, wasting time.
    
    Args:
        time_range (str): Time range to analyze (default is '24h').

    Returns:
        str: JSON string containing a list of the most severe sequential bottlenecks.
    """
    logger.info(f"[TOOL CALL-detect_sequential_bottlenecks] time_range='{time_range}'")
    try:
        query = f"""
        WITH all_events AS (
            SELECT span_id, parent_span_id as parent_id, timestamp as start_time, duration_ms, session_id, agent_name as name, 'Agent' as type 
            FROM `{PROJECT_ID}.{DATASET_ID}.agent_events_view` 
            WHERE timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
            UNION ALL
            SELECT span_id, parent_span_id as parent_id, timestamp as start_time, duration_ms, session_id, model_name as name, 'LLM' as type 
            FROM `{PROJECT_ID}.{DATASET_ID}.llm_events_view` 
            WHERE timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
            UNION ALL
            SELECT span_id, parent_span_id as parent_id, timestamp as start_time, duration_ms, session_id, tool_name as name, 'Tool' as type 
            FROM `{PROJECT_ID}.{DATASET_ID}.tool_events_view` 
            WHERE timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
        ),
        events_with_end AS (
            SELECT 
                span_id, parent_id, start_time, duration_ms, session_id, name, type,
                TIMESTAMP_ADD(start_time, INTERVAL CAST(duration_ms AS INT64) MILLISECOND) as end_time
            FROM all_events
        ),
        -- PRE-FILTER: Only get parents that actually have children
        child_counts AS (
            SELECT parent_id, COUNT(*) as child_count
            FROM events_with_end
            WHERE parent_id IS NOT NULL
            GROUP BY parent_id
            HAVING child_count > 1
        ),
        parent_stats AS (
            SELECT 
                p.session_id,
                p.span_id as parent_span_id,
                p.name as parent_name,
                p.type as parent_type,
                p.duration_ms as parent_duration,
                COUNT(c.span_id) as num_children,
                SUM(c.duration_ms) as sum_child_durations,
                MIN(c.start_time) as first_child_start,
                MAX(c.end_time) as last_child_end
            FROM events_with_end p
            JOIN child_counts cc ON cc.parent_id = p.span_id
            JOIN events_with_end c ON c.parent_id = p.span_id AND c.session_id = p.session_id
            GROUP BY 1, 2, 3, 4, 5
        )
        SELECT 
            session_id,
            parent_span_id,
            parent_name,
            parent_duration,
            num_children,
            sum_child_durations,
            TIMESTAMP_DIFF(last_child_end, first_child_start, MILLISECOND) as absolute_wall_clock_time,
            (sum_child_durations / NULLIF(TIMESTAMP_DIFF(last_child_end, first_child_start, MILLISECOND), 0)) as overlap_ratio
        FROM parent_stats
        WHERE num_children > 1 AND parent_duration > 5000
        ORDER BY overlap_ratio DESC
        """

        df = await execute_bigquery(query)
        
        if df.empty:
            return json.dumps({
                "message": "No sequential bottlenecks detected in the timeframe.", 
                "metadata": {"time_range": time_range}
            })
            
        # Filter for ratios ~ 1.0 (sequential)
        sequential_only = df[(df['overlap_ratio'] >= 0.9) & (df['overlap_ratio'] <= 1.1)].head(10)
        
        requests = sequential_only.to_dict(orient="records")
            
        result = {
            "metadata": {"time_range": time_range, "bottlenecks_found": len(requests)},
            "bottlenecks": requests
        }
        
        return json.dumps(result, cls=AnalysisEncoder)
        
    except Exception as e:
        logger.error(f"Error in detect_sequential_bottlenecks: {str(e)}")
        return json.dumps({"error": str(e)})

