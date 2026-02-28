import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from typing import Dict, Any, List

import pandas as pd
from dotenv import load_dotenv

# Ensure we can import agent modules
dir_path = os.path.dirname(__file__)
sys.path.append(os.path.join(dir_path, ".."))

from agents.observability_agent.agent_tools.analytics.latency import (
    analyze_latency_grouped,
    get_slowest_queries,
    get_failed_queries,
    get_failed_agent_queries,
    get_failed_tool_queries,
    fetch_tool_bottlenecks
)
from agents.observability_agent.agent_tools.analytics.errors import (
    get_tool_errors
)
from agents.observability_agent.agent_tools.analytics.llm_diagnostics import (
    analyze_empty_llm_responses,
    fetch_slowest_requests,
    get_failed_llm_queries
)
from agents.observability_agent.agent_tools.analytics.correlation import fetch_correlation_data
from agents.observability_agent.config import (
    AGENT_EVENTS_VIEW_ID,
    INVOCATION_EVENTS_VIEW_ID
)

# Load Environment from root
load_dotenv(os.path.join(dir_path, "../.env"), override=True)

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ReportDataManager")

# Resolve FutureWarning
pd.set_option('future.no_silent_downcasting', True)

class ReportDataManager:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.data_config = self.config.get("data_retrieval", {})
        self.time_range_desc = self.data_config.get("time_period", "24h")
        self.percentile = 95.5
        if "kpis" in self.config and "end_to_end" in self.config["kpis"]:
             self.percentile = self.config["kpis"]["end_to_end"].get("percentile_target", 95.5)
        
        # Configurable Limits
        self.num_slowest = self.data_config.get("num_slowest_queries", 20)
        self.num_errors = self.data_config.get("num_error_queries", 20)

    def json_to_df(self, json_input: Any) -> pd.DataFrame:
        try:
            if isinstance(json_input, pd.DataFrame):
                return json_input
            if isinstance(json_input, str):
                data = json.loads(json_input)
            else:
                data = json_input
                
            if isinstance(data, dict):
                # Try common keys for list data
                for key in ["data", "requests", "impact_analysis", "batch_analysis", "records", "tool_errors", "llm_errors", "agent_errors", "root_errors"]:
                    if key in data and isinstance(data[key], list):
                         return pd.DataFrame(data[key])
                pass

            if isinstance(data, list):
                return pd.DataFrame(data)
            return pd.DataFrame()
        except Exception as e:
            logger.error(f"Failed to parse JSON/Data to DataFrame: {e}")
            return pd.DataFrame()

    async def fetch_tool_errors(self, limit: int = 5):
        """Fetches detailed tool errors with context using get_tool_errors tool."""
        try:
            raw_json = await get_tool_errors(
                time_range=self.time_range_desc, 
                limit=limit
            )
            df = self.json_to_df(raw_json)
            return df
        except Exception as e:
            logger.error(f"Failed to fetch tool errors: {e}")
            return pd.DataFrame()

    async def fetch_llm_errors(self, limit: int = 5):
        """Fetches detailed LLM errors using get_failed_queries tool."""
        try:
            raw_json = await get_failed_llm_queries(
                time_range=self.time_range_desc, 
                limit=limit,
            )
            df = self.json_to_df(raw_json)
            return df
        except Exception as e:
            logger.error(f"Failed to fetch LLM errors: {e}")
            return pd.DataFrame()

    async def fetch_agent_errors(self, limit: int = 5):
        """Fetches detailed Agent errors using get_failed_queries tool."""
        try:
            raw_json = await get_failed_queries(
                time_range=self.time_range_desc, 
                limit=limit * 2, 
                view_id=AGENT_EVENTS_VIEW_ID
            )
            df = self.json_to_df(raw_json)
            # Filter where agent_name != computed_root_agent if columns exist
            if not df.empty and 'agent_name' in df.columns and 'computed_root_agent' in df.columns:
                 df = df[df['agent_name'] != df['computed_root_agent']]
            
            # Map computed_root_agent -> root_agent_name
            if 'computed_root_agent' in df.columns:
                df.rename(columns={'computed_root_agent': 'root_agent_name'}, inplace=True)
                
            return df.head(limit)
        except Exception as e:
            logger.error(f"Failed to fetch agent errors: {e}")
            return pd.DataFrame()

    async def fetch_root_errors(self, limit: int = 5):
        """Fetches detailed Root Agent errors using get_failed_queries tool."""
        try:
            raw_json = await get_failed_queries(
                time_range=self.time_range_desc, 
                limit=limit, 
                view_id=INVOCATION_EVENTS_VIEW_ID
            )
            return self.json_to_df(raw_json)
        except Exception as e:
            logger.error(f"Failed to fetch root errors: {e}")
            return pd.DataFrame()

    async def fetch_raw_llm_data(self, time_range: str = "24h"):
        """Fetches raw LLM event data using fetch_correlation_data tool."""
        try:
            raw_json = await fetch_correlation_data(time_range=time_range, limit=5000)
            df = self.json_to_df(raw_json)
            
            if df.empty:
                return df

            # Rename columns to match expected output for charts
            rename_map = {
                'input_token_count': 'input_tokens',
                'output_token_count': 'output_tokens',
                'timestamp': 'timestamp',
                'thoughts_token_count': 'thought_tokens'
            }
            # Only rename if columns exist
            df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns}, inplace=True)
            
            # Calculate seconds fields
            if 'duration_ms' in df.columns:
                df['latency_seconds'] = pd.to_numeric(df['duration_ms'], errors='coerce') / 1000.0
            
            if 'time_to_first_token_ms' in df.columns:
                df['ttft_seconds'] = pd.to_numeric(df['time_to_first_token_ms'], errors='coerce') / 1000.0
            else:
                df['ttft_seconds'] = 0.0

            # Ensure numeric
            cols_to_numeric = ['input_tokens', 'output_tokens', 'thought_tokens']
            for col in cols_to_numeric:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            
            if 'timestamp' in df.columns:
                 df['timestamp'] = pd.to_datetime(df['timestamp'])

            return df
        except Exception as e:
            logger.error(f"Failed to fetch raw LLM data: {e}")
            return pd.DataFrame()


    async def fetch_llm_bottlenecks_with_details(self, limit: int = 5):
        """Fetches LLM bottlenecks using fetch_slowest_requests tool."""
        try:
            raw_json = await fetch_slowest_requests(time_range=self.time_range_desc, limit=limit)
            df = self.json_to_df(raw_json)
            
            if df.empty:
                return df

            if 'duration_ms' in df.columns:
                df['duration_s'] = pd.to_numeric(df['duration_ms'], errors='coerce') / 1000.0
                
            if 'time_to_first_token_ms' in df.columns:
                df['ttft_s'] = pd.to_numeric(df['time_to_first_token_ms'], errors='coerce') / 1000.0
                
            rename_map = {
                'response_tokens': 'response_token_count',
                'prompt_tokens': 'prompt_token_count',
                'preview': 'input_preview',
                'thought_tokens': 'thought_tokens'
            }
            df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns}, inplace=True)
            
            return df
        except Exception as e:
             logger.error(f"Failed to fetch detailed LLM bottlenecks: {e}")
             return pd.DataFrame()

    async def trace_task(self, name, awaitable):
        logger.info(f"   [START] Task: {name}")
        try:
            res = await awaitable
            logger.info(f"   [DONE] Task: {name}")
            return res
        except Exception as e:
            logger.error(f"   [FAIL] Task: {name} Error: {e}")
            if "RawLLM" in name: return pd.DataFrame()
            raise e

    async def fetch_all_data(self) -> Dict[str, Any]:
        """Fetches all data required for the report."""
        logger.info(f"ReportDataManager: Fetching data in parallel (Time Range: {self.time_range_desc})...")
        
        # Define tasks
        task_agents = self.trace_task("Agents", analyze_latency_grouped(
            group_by="agent_name", 
            time_range=self.time_range_desc, 
            view_id="agent_events_view", 
            percentile=self.percentile,
            exclude_root=True
        ))
        task_roots = self.trace_task("Roots", analyze_latency_grouped(
            time_range=self.time_range_desc,
            group_by="root_agent_name",
            view_id="invocation_events_view",
            percentile=self.percentile
        ))
        task_tools = self.trace_task("Tools", analyze_latency_grouped(group_by="tool_name", view_id="tool_events_view", time_range=self.time_range_desc, percentile=self.percentile))
        
        task_models = self.trace_task("Models", analyze_latency_grouped(group_by="model_name", view_id="llm_events_view", time_range=self.time_range_desc, percentile=self.percentile))
        
        task_agent_models_e2e = self.trace_task("AgentModelsE2E", analyze_latency_grouped(group_by="agent_name,model_name", view_id="agent_events_view", time_range=self.time_range_desc, percentile=self.percentile))
        task_agent_models_llm = self.trace_task("AgentModelsLLM", analyze_latency_grouped(group_by="agent_name,model_name", view_id="llm_events_view", time_range=self.time_range_desc, percentile=self.percentile))
        
        limit_slow = self.config.get("num_slowest_queries", 5)
        limit_error = self.config.get("num_error_queries", 5)
        
        task_agent_slow = self.trace_task("AgentSlow", get_slowest_queries(limit=limit_slow, view_id="agent_events_view", time_range=self.time_range_desc))
        task_tool_slow = self.trace_task("ToolSlow", fetch_tool_bottlenecks(limit=limit_slow, time_range=self.time_range_desc))
        task_llm_slow = self.trace_task("LLMSlow", self.fetch_llm_bottlenecks_with_details(limit=limit_slow))
        
        task_root_errors = self.trace_task("RootErrors", self.fetch_root_errors(limit=limit_error))
        task_agent_errors = self.trace_task("AgentErrors", self.fetch_agent_errors(limit=limit_error))
        task_tool_errors = self.trace_task("ToolErrors", self.fetch_tool_errors(limit=limit_error))
        task_llm_errors = self.trace_task("LLMErrors", self.fetch_llm_errors(limit=limit_error))
        
        limit_empty = self.config.get("num_empty_llm_responses", 20)
        task_empty = self.trace_task("EmptyLLM", analyze_empty_llm_responses(limit=limit_empty, time_range=self.time_range_desc))
        
        task_correlation = self.trace_task("Correlation", fetch_correlation_data(time_range=self.time_range_desc, limit=2000))
        task_raw_llm = self.trace_task("RawLLM", self.fetch_raw_llm_data(time_range=self.time_range_desc))

        results = await asyncio.gather(
            task_agents, task_roots, task_tools, task_models, task_agent_models_e2e, task_agent_models_llm,
            task_agent_slow, task_tool_slow, task_llm_slow,
            task_root_errors, task_agent_errors, task_tool_errors, task_llm_errors,
            task_empty, task_correlation, task_raw_llm
        )

        (
            raw_agents, raw_roots, raw_tools, raw_models, raw_agent_models_e2e, raw_agent_models_llm,
            raw_agent_slow, raw_tool_slow, raw_llm_slow,
            df_root_errors, df_agent_errors, df_tool_errors, df_llm_errors,
            raw_empty, raw_correlation, df_raw_llm_data
        ) = results

        # Process Results
        data = {}
        data['df_agents'] = self.json_to_df(raw_agents)
        data['df_roots'] = self.json_to_df(raw_roots)
        data['df_tools'] = self.json_to_df(raw_tools)
        data['df_models'] = self.json_to_df(raw_models)
        data['df_agent_models_e2e'] = self.json_to_df(raw_agent_models_e2e)
        data['df_agent_models_llm'] = self.json_to_df(raw_agent_models_llm)
        data['df_correlation'] = self.json_to_df(raw_correlation)
        
        # Clean up column merge artifacts if any
        for df_key in ['df_agent_models_e2e', 'df_agent_models_llm']:
             df = data[df_key]
             new_cols = {}
             for col in df.columns:
                 if col.endswith('_x'):
                     new_cols[col] = col[:-2]
             if new_cols:
                 df.rename(columns=new_cols, inplace=True)

        # Bottlenecks processing
        # Agents
        if isinstance(raw_agent_slow, str):
             try:
                 agent_data = json.loads(raw_agent_slow)
                 if isinstance(agent_data, dict) and "requests" in agent_data:
                     data['agent_bottlenecks'] = self.json_to_df(agent_data["requests"])
                 else:
                     data['agent_bottlenecks'] = self.json_to_df(agent_data)
             except json.JSONDecodeError:
                 data['agent_bottlenecks'] = pd.DataFrame()
        else:
             data['agent_bottlenecks'] = self.json_to_df(raw_agent_slow)

        # Tools
        if isinstance(raw_tool_slow, str):
             try:
                 tool_data = json.loads(raw_tool_slow)
                 if isinstance(tool_data, dict) and "requests" in tool_data:
                     data['tool_bottlenecks'] = self.json_to_df(tool_data["requests"])
                 else:
                     data['tool_bottlenecks'] = self.json_to_df(tool_data)
             except json.JSONDecodeError:
                 data['tool_bottlenecks'] = pd.DataFrame()
        else:
             data['tool_bottlenecks'] = self.json_to_df(raw_tool_slow)

        data['llm_bottlenecks'] = self.json_to_df(raw_llm_slow) # Already DF or processed in sub-function? 
        # Actually fetch_llm_bottlenecks_with_details returns DF. 
        # But wait, self.json_to_df handles DF input safely.

        # Errors
        data['root_errors'] = df_root_errors
        data['agent_errors'] = df_agent_errors
        data['tool_errors'] = df_tool_errors
        data['llm_errors'] = df_llm_errors

        # Raw Data
        data['df_raw_llm'] = df_raw_llm_data
        data['empty_responses'] = json.loads(raw_empty) if isinstance(raw_empty, str) else raw_empty
        data['outliers'] = {} # Placeholder

        return data
