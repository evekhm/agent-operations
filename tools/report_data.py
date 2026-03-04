import asyncio
import json
import logging
import os
import sys
from typing import Dict, Any

import pandas as pd
from dotenv import load_dotenv

# Ensure we can import agent modules
dir_path = os.path.dirname(__file__)
sys.path.append(os.path.join(dir_path, ".."))

from agents.observability_agent.agent_tools.analytics.latency import (
    analyze_latency_grouped,
    get_agent_requests,
    get_llm_requests,
    get_tool_requests,
    get_invocation_requests
)

from agents.observability_agent.config import TOOL_EVENTS_VIEW_ID, LLM_EVENTS_VIEW_ID
from agents.observability_agent.agent_tools.analytics.llm_diagnostics import (
    analyze_empty_llm_responses
)
from agents.observability_agent.agent_tools.analytics.correlation import fetch_correlation_data
from agents.observability_agent.config import (
    AGENT_EVENTS_VIEW_ID,
    INVOCATION_EVENTS_VIEW_ID,
    PROJECT_ID,
    DATASET_ID
)
from agents.observability_agent.utils.common import build_standard_where_clause
from agents.observability_agent.utils.bq import execute_bigquery

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
        if "kpis" in self.config:
             kpis = self.config["kpis"]
             self.percentile_e2e = kpis.get("end_to_end", {}).get("percentile_target", 95.5)
             self.percentile_agent = kpis.get("agent", {}).get("percentile_target", 95.5)
             self.percentile_llm = kpis.get("llm", {}).get("percentile_target", 95.5)
             self.percentile_tool = kpis.get("tool", {}).get("percentile_target", 95.5)
        else:
             self.percentile_e2e = 95.5
             self.percentile_agent = 95.5
             self.percentile_llm = 95.5
             self.percentile_tool = 95.5
        
        # Configurable Limits
        self.num_slowest = self.data_config.get("num_slowest_queries", 20)
        self.num_errors = self.data_config.get("num_error_queries", 20)

        self.presentation_config = self.config.get("data_presentation", {})
        self.presentation_num_slowest = self.presentation_config.get("num_slowest_queries", 20)
        self.presentation_num_errors = self.presentation_config.get("num_error_queries", 20)

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


    async def fetch_raw_llm_data(self, time_range: str = "24h"):
        """Fetches raw LLM event data using fetch_correlation_data tool."""
        try:
            raw_json = await fetch_correlation_data(time_range=time_range, limit=5000)
            df = self.json_to_df(raw_json)
            
            if df.empty:
                return df

            # Calculate seconds fields
            if 'duration_ms' in df.columns:
                df['latency_seconds'] = pd.to_numeric(df['duration_ms'], errors='coerce') / 1000.0
            
            if 'time_to_first_token_ms' in df.columns:
                df['ttft_seconds'] = pd.to_numeric(df['time_to_first_token_ms'], errors='coerce') / 1000.0
            else:
                df['ttft_seconds'] = 0.0

            # Ensure numeric
            # correlation.py returns prompt_token_count, candidates_token_count, thoughts_token_count
            cols_to_numeric = ['prompt_token_count', 'candidates_token_count', 'thoughts_token_count']
            for col in cols_to_numeric:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            
            if 'timestamp' in df.columns:
                 df['timestamp'] = pd.to_datetime(df['timestamp'])

            # Map columns for ReportGenerator compatibility
            # correlation.py: prompt_token_count, candidates_token_count, thoughts_token_count
            # generate_report.py expects: input_tokens, output_tokens, thought_tokens
            if 'prompt_token_count' in df.columns:
                df['input_tokens'] = df['prompt_token_count']
            if 'candidates_token_count' in df.columns:
                df['output_tokens'] = df['candidates_token_count']
            if 'thoughts_token_count' in df.columns:
                df['thought_tokens'] = df['thoughts_token_count']

            return df
        except Exception as e:
            logger.error(f"Failed to fetch raw LLM data: {e}")
            return pd.DataFrame()

    async def fetch_raw_invocation_data(self, time_range: str = "24h", limit: int = 2000):
        """Fetches raw E2E invocation event data from BigQuery."""
        where_clause = build_standard_where_clause(time_range=time_range)
        query = f"""
        SELECT
            root_agent_name as agent_name,
            duration_ms,
            timestamp
        FROM `{PROJECT_ID}.{DATASET_ID}.invocation_events_view` AS T
        WHERE {where_clause}
          AND duration_ms > 0
        ORDER BY timestamp DESC
        LIMIT {limit}
        """
        try:
            df = await execute_bigquery(query)
            if df.empty: return df
            df['latency_seconds'] = pd.to_numeric(df['duration_ms'], errors='coerce') / 1000.0
            if 'timestamp' in df.columns:
                 df['timestamp'] = pd.to_datetime(df['timestamp'])
            return df
        except Exception as e:
            logger.error(f"Failed to fetch raw invocation data: {e}")
            return pd.DataFrame()

    async def fetch_raw_agent_data(self, time_range: str = "24h", limit: int = 5000):
        """Fetches raw Agent execution event data from BigQuery."""
        where_clause = build_standard_where_clause(time_range=time_range)
        query = f"""
        WITH Agents AS (
            SELECT * FROM `{PROJECT_ID}.{DATASET_ID}.agent_events_view` AS T WHERE {where_clause}
        )
        SELECT
            A.span_id,
            A.agent_name,
            L.model_name,
            A.duration_ms,
            A.timestamp
        FROM Agents AS A
        LEFT JOIN `{PROJECT_ID}.{DATASET_ID}.llm_events_view` AS L
          ON A.trace_id = L.trace_id AND A.span_id = L.parent_span_id
        WHERE A.duration_ms > 0
          AND A.agent_name != A.root_agent_name
        ORDER BY A.timestamp DESC
        LIMIT {limit}
        """
        try:
            df = await execute_bigquery(query)
            if df.empty: return df
            df['latency_seconds'] = pd.to_numeric(df['duration_ms'], errors='coerce') / 1000.0
            if 'timestamp' in df.columns:
                 df['timestamp'] = pd.to_datetime(df['timestamp'])
            return df
        except Exception as e:
            logger.error(f"Failed to fetch raw agent data: {e}")
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
            view_id=AGENT_EVENTS_VIEW_ID,
            percentile=self.percentile_agent,
            exclude_root=True
        ))
        task_roots = self.trace_task("Roots", analyze_latency_grouped(
            time_range=self.time_range_desc,
            group_by="root_agent_name",
            view_id=INVOCATION_EVENTS_VIEW_ID,
            percentile=self.percentile_e2e
        ))
        task_tools = self.trace_task("Tools", analyze_latency_grouped(group_by="tool_name",
                                                                      view_id=TOOL_EVENTS_VIEW_ID, time_range=self.time_range_desc, percentile=self.percentile_tool))
        
        task_models = self.trace_task("Models", analyze_latency_grouped(group_by="model_name",
                                                                        view_id=LLM_EVENTS_VIEW_ID,
                                                                        time_range=self.time_range_desc, percentile=self.percentile_llm))
        
        task_agent_models_e2e = self.trace_task("AgentModelsE2E", analyze_latency_grouped(group_by="agent_name,model_name",
                                                                                          view_id=AGENT_EVENTS_VIEW_ID,
                                                                                          time_range=self.time_range_desc,
                                                                                          percentile=self.percentile_agent))
        task_agent_models_llm = self.trace_task("AgentModelsLLM", analyze_latency_grouped(group_by="agent_name,model_name",
                                                                    percentile=self.percentile_llm))

        limit_slow = self.presentation_num_slowest
        limit_error = self.presentation_num_errors
        
        task_e2e_slow = self.trace_task("E2ESlow", get_invocation_requests(limit=limit_slow, time_range=self.time_range_desc, sort_by="slowest"))
        task_agent_slow = self.trace_task("AgentSlow", get_agent_requests(limit=limit_slow, exclude_root_agent=True, time_range=self.time_range_desc, sort_by="slowest"))
        task_tool_slow = self.trace_task("ToolSlow", get_tool_requests(limit=limit_slow, time_range=self.time_range_desc, sort_by="slowest"))
        task_llm_slow = self.trace_task("LLMSlow", get_llm_requests(limit=limit_slow, time_range=self.time_range_desc, sort_by="slowest"))
        
        task_root_errors = self.trace_task("RootErrors", get_invocation_requests(limit=limit_error, time_range=self.time_range_desc, failed_only=True, sort_by="latest"))
        task_agent_errors = self.trace_task("AgentErrors", get_agent_requests(limit=limit_error, exclude_root_agent=True,
                                                                              time_range=self.time_range_desc, failed_only=True, sort_by="latest"))
        task_tool_errors = self.trace_task("ToolErrors", get_tool_requests(limit=limit_error, time_range=self.time_range_desc, failed_only=True, sort_by="latest"))
        task_llm_errors = self.trace_task("LLMErrors", get_llm_requests(limit=limit_error, time_range=self.time_range_desc, failed_only=True, sort_by="latest"))
        
        limit_empty = self.data_config.get("num_empty_llm_responses", 20)
        task_empty = self.trace_task("EmptyLLM", analyze_empty_llm_responses(limit=limit_empty, time_range=self.time_range_desc))
        
        task_correlation = self.trace_task("Correlation", fetch_correlation_data(time_range=self.time_range_desc, limit=2000))
        task_raw_llm = self.trace_task("RawLLM", self.fetch_raw_llm_data(time_range=self.time_range_desc))
        task_raw_invocations = self.trace_task("RawInvocations", self.fetch_raw_invocation_data(time_range=self.time_range_desc))
        task_raw_agents = self.trace_task("RawAgents", self.fetch_raw_agent_data(time_range=self.time_range_desc))

        results = await asyncio.gather(
            task_agents, task_roots, task_tools, task_models, task_agent_models_e2e,
            task_agent_models_llm,
            task_e2e_slow, task_agent_slow, task_tool_slow, task_llm_slow,
            task_root_errors, task_agent_errors, task_tool_errors, task_llm_errors,
            task_empty, task_correlation, task_raw_llm, task_raw_invocations, task_raw_agents
        )

        (
            raw_agents, raw_roots, raw_tools, raw_models, raw_agent_models_e2e, raw_agent_models_llm,
            raw_e2e_slow, raw_agent_slow, raw_tool_slow, raw_llm_slow,
            raw_root_errors, raw_agent_errors, raw_tool_errors, raw_llm_errors,
            raw_empty, raw_correlation, df_raw_llm_data, df_raw_invocations, df_raw_agents
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

        # Bottlenecks processing helper
        def process_bottlenecks(raw_data):
            if isinstance(raw_data, str):
                 try:
                     parsed = json.loads(raw_data)
                     if isinstance(parsed, dict) and "requests" in parsed:
                         return self.json_to_df(parsed["requests"])
                     else:
                         return self.json_to_df(parsed)
                 except json.JSONDecodeError:
                     return pd.DataFrame()
            else:
                 return self.json_to_df(raw_data)

        data['root_bottlenecks'] = process_bottlenecks(raw_e2e_slow)
        data['agent_bottlenecks'] = process_bottlenecks(raw_agent_slow)
        data['tool_bottlenecks'] = process_bottlenecks(raw_tool_slow)
        data['llm_bottlenecks'] = process_bottlenecks(raw_llm_slow)

        # Errors processing (similar logic, get_failed_* returns JSON like requests)
        data['root_errors'] = process_bottlenecks(raw_root_errors)
        data['agent_errors'] = process_bottlenecks(raw_agent_errors)
        data['tool_errors'] = process_bottlenecks(raw_tool_errors)
        data['llm_errors'] = process_bottlenecks(raw_llm_errors)

        # Raw Data
        data['df_raw_llm'] = df_raw_llm_data
        data['df_raw_invocations'] = df_raw_invocations
        data['df_raw_agents'] = df_raw_agents
        data['empty_responses'] = json.loads(raw_empty) if isinstance(raw_empty, str) else raw_empty
        data['outliers'] = {} # Placeholder

        return data
