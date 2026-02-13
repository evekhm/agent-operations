"""
BigQuery Utility Module.

This module handles BigQuery interactions, including:
- **Client Management**: Singleton client with lazy initialization of views and connections.
- **Query Execution**: Async execution with timeout protection and dedicated thread pool.
- **Caching**: Local file-based caching for query results to reduce costs and latency during development/testing.
- **View Management**: Automatically ensures required SQL views exist.
"""
import asyncio
import concurrent.futures
import hashlib
import logging
import os
import shutil
from typing import cast, Awaitable

import pandas as pd
from google.cloud import bigquery
from google.cloud.exceptions import NotFound

from ..config import PROJECT_ID

logger = logging.getLogger(__name__)

# ==============================================================================
# CLIENT & CONNECTION
# ==============================================================================

_bq_client = None
_views_ensured = False

def _get_bq_client():
    """
    Get or initialize the BigQuery client.
    
    This function implements a singleton pattern for the BigQuery client.
    On the first call, it also:
    1. Ensures all required BigQuery views exist (LLM, Tool, Agent, Invocation events).
    2. Ensures the BigQuery Connection (`bqml_connection`) exists for AI functions.
    
    Returns:
        bigquery.Client: The initialized BigQuery client.
    """
    global _bq_client, _views_ensured
    if _bq_client is None:
        _bq_client = bigquery.Client(project=PROJECT_ID)
    
    # Ensure views exist (lazy initialization) - run once per process
    if not _views_ensured:
        try:
            from .views import (
                ensure_llm_events_view_exists,
                ensure_tool_events_view_exists,
                ensure_agent_events_view_exists,
                ensure_invocation_events_view_exists,
            )
            from .connections import ensure_bq_connection_exists
            
            ensure_llm_events_view_exists()
            ensure_tool_events_view_exists()
            ensure_agent_events_view_exists()
            ensure_invocation_events_view_exists()
            ensure_bq_connection_exists()
            _views_ensured = True
        except Exception as e:
            logger.warning(f"Failed to ensure view exists: {e}")
            
    return _bq_client

def check_table_exists(client, table_ref) -> bool:
    """Check if a BigQuery table exists."""
    try:
        client.get_table(table_ref)
        return True
    except NotFound:
        return False

# ==============================================================================
# QUERY EXECUTION & CACHING
# ==============================================================================

CACHE_DIR = os.path.join(os.getcwd(), ".cache", "queries")

def clear_query_cache():
    """Clear the persistent query cache."""
    if os.path.exists(CACHE_DIR):
        shutil.rmtree(CACHE_DIR)
        os.makedirs(CACHE_DIR, exist_ok=True)
        logger.info("[CACHE] Cleared persistent query cache")

def _get_cache_path(query: str, timeout: int, query_parameters: list = None) -> str:
    """Generate cache file path based on query hash and parameters."""
    params_str = str(query_parameters) if query_parameters else ""
    content = f"{query}::{timeout}::{PROJECT_ID}::{params_str}"
    query_hash = hashlib.md5(content.encode()).hexdigest()
    return os.path.join(CACHE_DIR, f"{query_hash}.json")


async def run_query_async(query: str, job_config=None, timeout: int = 1200) -> pd.DataFrame:
    """
    Execute BigQuery query asynchronously using run_in_executor.
    Returns DataFrame.
    """
    client = _get_bq_client()
    
    # Use a dedicated thread pool for BigQuery to avoid blocking the main loop
    if not hasattr(run_query_async, "_executor"):
        # 20 workers to handle parallel queries without choking
        run_query_async._executor = concurrent.futures.ThreadPoolExecutor(max_workers=20, thread_name_prefix="bq_worker")
    
    loop = asyncio.get_running_loop()
        
    def _sync_exec():
        job_cfg = job_config or bigquery.QueryJobConfig()
        if timeout:
            job_cfg.job_timeout_ms = timeout * 1000
            
        job = client.query(query, job_config=job_cfg)
        return job.result(timeout=timeout).to_dataframe()
        
    return await cast(Awaitable[pd.DataFrame], loop.run_in_executor(run_query_async._executor, _sync_exec))


async def execute_bigquery(query: str, timeout: int = 1200, job_config=None) -> pd.DataFrame:
    """
    Execute a BigQuery query with persistent caching and timeout protection.
    
    This function wraps `run_query_async` with a file-based caching layer (`.cache/queries`).
    
    Args:
        query (str): The SQL query to execute.
        timeout (int): Timeout in seconds (default: 1200).
        job_config (bigquery.QueryJobConfig, optional): Job configuration.
        
    Returns:
        pd.DataFrame: The query results as a Pandas DataFrame.
    """
    # ensure cache dir exists
    print(f"\n================ SQL QUERY ================\n"
          f"{query}\n"
          f"===========================================")
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR, exist_ok=True)

    # Extract query parameters for cache key if present
    query_parameters = None
    if job_config and hasattr(job_config, 'query_parameters'):
        query_parameters = job_config.query_parameters
        
    cache_path = _get_cache_path(query, timeout, query_parameters)
    
    # Check cache
    if os.path.exists(cache_path):
        try:
            logger.info(f"[CACHE HIT] Loading results from {cache_path}")
            return pd.read_json(cache_path, orient='records')
        except Exception as e:
            logger.warning(f"[CACHE READ ERROR] Failed to read cache, re-executing: {e}")
    
    # Execute query
    logger.info(f"[BQ EXEC] Running query (timeout={timeout}s)")
    
    # Config setup
    if job_config:
        # Update timeout in existing config
        job_config.job_timeout_ms = timeout * 1000
    else:
        # Create new config
        job_config = bigquery.QueryJobConfig(
            job_timeout_ms=timeout * 1000
        )
    
    try:
        df = await run_query_async(query, job_config=job_config, timeout=timeout)
        
        # Save to cache
        try:
            df.to_json(cache_path, orient='records', date_format='iso')
            logger.info(f"[CACHE SAVE] Saved {len(df)} rows to {cache_path}")
        except Exception as e:
            logger.warning(f"[CACHE SAVE ERROR] Could not save to cache: {e}")
            
        return df
        
    except Exception as e:
        if "timeout" in str(e).lower():
            logger.error(f"BigQuery query timed out after {timeout} seconds")
        raise
