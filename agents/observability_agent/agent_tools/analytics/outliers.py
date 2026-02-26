from collections import Counter
import json
import logging
import pandas as pd
from ...utils.bq import execute_bigquery
from ...utils.common import build_standard_where_clause, AnalysisEncoder
from ...utils.caching import cached_tool
from ...config import PROJECT_ID, DATASET_ID, AGENT_EVENTS_VIEW_ID, TOOL_EVENTS_VIEW_ID, LLM_EVENTS_VIEW_ID

logger = logging.getLogger(__name__)

@cached_tool()
async def analyze_outlier_patterns(
    time_range: str = "7d",
    metric: str = "duration_ms",
    threshold_percentile: float = 0.95,
    limit: int = 20
) -> str:
    """
    Identifies common characteristics of outlier requests (e.g., slowest 5%).
    
    analyzes:
    - Agent distribution in outliers
    - Tool usage in outliers
    - Model usage in outliers
    - Input token count visualization (buckets)
    
    Args:
        time_range: Time range to analyze.
        metric: Metric to analyze (default: duration_ms).
        threshold_percentile: Percentile to define outliers (default: 0.95).
        limit: Max records to return in sample.
        
    Returns:
        JSON string with outlier analysis.
    """
    logger.info(f"[TOOL CALL-analyze_outlier_patterns] time_range={time_range}, metric={metric}")
    
    try:
        # 1. Calculate Threshold
        # We need a quick query to get P95 of the metric for All Root Agents (End-to-End)
        # OR we can just order by DESC and take top X%?
        # Let's use quantile approximation if possible, or just standard WHERE metric > X
        
        # Step 1: Get P95 value
        threshold_query = f"""
        SELECT PERCENTILE_CONT({metric}, {threshold_percentile}) OVER() as p_val
        FROM `{PROJECT_ID}.{DATASET_ID}.{AGENT_EVENTS_VIEW_ID}`
        WHERE 
            timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {time_range.replace('d', ' DAY').replace('h', ' HOUR')})
            AND parent_span_id IS NULL -- Root Agents only for E2E outliers
        LIMIT 1
        """
        # Parsing time_range strictly might be safer using utils, but simple replace works for standard "7d", "24h"
        # However, build_standard_where_clause is better if we want consistency.
        
        where_clause = build_standard_where_clause(time_range, table_alias="T")
        
        threshold_query = f"""
        SELECT percentile_cont(x, {threshold_percentile}) over() as threshold
        FROM (
            SELECT {metric} as x 
            FROM `{PROJECT_ID}.{DATASET_ID}.{AGENT_EVENTS_VIEW_ID}` T
            WHERE {where_clause} AND T.parent_span_id IS NULL
        )
        LIMIT 1
        """
        
        # Actually standard SQL PERCENTILE_CONT logic might be tricky in subselects without grouping.
        # Simpler: Get APPROX_QUANTILES
        threshold_query = f"""
        SELECT APPROX_QUANTILES({metric}, 100)[OFFSET({int(threshold_percentile*100)})] as threshold
        FROM `{PROJECT_ID}.{DATASET_ID}.{AGENT_EVENTS_VIEW_ID}` T
        WHERE {where_clause} AND T.parent_span_id IS NULL
        """
        
        df_thresh = await execute_bigquery(threshold_query)
        if df_thresh.empty:
            return json.dumps({"message": "Not enough data for outliers"})
            
        threshold_val = df_thresh.iloc[0]['threshold']
        
        # 2. Fetch Outliers
        outlier_query = f"""
        SELECT 
            T.agent_name,
            T.model_name,
            -- We might want joined tool usage? That's complex.
            -- Let's stick to Agent-level attributes first.
            T.input_token_count,
            T.output_token_count,
            T.total_token_count,
            T.duration_ms,
            T.status,
            T.trace_id
        FROM `{PROJECT_ID}.{DATASET_ID}.{AGENT_EVENTS_VIEW_ID}` T
        WHERE {where_clause} 
        AND T.parent_span_id IS NULL
        AND T.{metric} >= {threshold_val}
        ORDER BY T.{metric} DESC
        LIMIT 1000
        """
        
        df_outliers = await execute_bigquery(outlier_query)
        
        if df_outliers.empty:
             return json.dumps({"message": "No outliers found > threshold", "threshold": float(threshold_val)})

        # 3. Analyze Patterns
        # - Agent Distribution
        agent_counts = df_outliers['agent_name'].value_counts(normalize=True).to_dict()
        
        # - Token Impact (Correlation in outliers?)
        #   Let's just return bucketed stats
        
        result = {
            "metadata": {
                "metric": metric,
                "threshold_percentile": threshold_percentile,
                "threshold_value": float(threshold_val),
                "outlier_count": len(df_outliers)
            },
            "distributions": {
                "agent_name": {k: f"{v*100:.1f}%" for k, v in agent_counts.items()},
                "status": df_outliers['status'].value_counts(normalize=True).to_dict()
            },
            "averages": {
                "input_tokens": float(df_outliers['input_token_count'].mean()),
                "output_tokens": float(df_outliers['output_token_count'].mean()),
                "duration_ms": float(df_outliers['duration_ms'].mean())
            },
            "samples": df_outliers.head(limit).to_dict(orient="records")
        }
        
        return json.dumps(result, cls=AnalysisEncoder)
        
    except Exception as e:
        logger.error(f"Error in analyze_outlier_patterns: {e}")
        return json.dumps({"error": str(e)})
