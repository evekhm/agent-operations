import asyncio
import os
import sys
import logging
import pandas as pd
import json
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Any

# Ensure we can import agent modules
dir_path = os.path.dirname(__file__)
sys.path.append(os.path.join(dir_path, ".."))

# Import analytics tools
from agents.observability_agent.agent_tools.analytics.latency import (
    analyze_latency_grouped,
    analyze_latency_performance,
    get_slowest_queries,
    analyze_root_cause
)
from agents.observability_agent.agent_tools.analytics.errors import classify_errors_by_type
from agents.observability_agent.agent_tools.analytics.llm_diagnostics import (
    analyze_empty_llm_responses,
    fetch_slowest_requests
)
from agents.observability_agent.agent_tools.analytics.correlation import fetch_correlation_data
from agents.observability_agent.agent_tools.analytics.outliers import analyze_outlier_patterns
from agents.observability_agent.utils.bq import execute_bigquery
from agents.observability_agent.utils.common import build_standard_where_clause
from agents.observability_agent.config import (
    DATASET_ID,
    PROJECT_ID,
    AGENT_VERSION,
    TABLE_ID,
    AGENT_TABLE_ID
)
from dotenv import load_dotenv

# Load Environment from root
load_dotenv(os.path.join(dir_path, "../.env"), override=True)

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ReportGenerator")

# Configure Plotting Style
plt.style.use('seaborn-v0_8-darkgrid')
sns.set_theme(style="whitegrid")

class ChartGenerator:
    def __init__(self, output_dir: str, scale: float = 1.0):
        self.output_dir = output_dir
        self.scale = scale
        os.makedirs(self.output_dir, exist_ok=True)

    def _get_figsize(self, w, h):
        return (w * self.scale, h * self.scale)

    def save_plot(self, filename: str):
        path = os.path.join(self.output_dir, filename)
        plt.tight_layout()
        plt.savefig(path, bbox_inches='tight', dpi=150)
        plt.close()
        return path

    def generate_pie_chart(self, data: pd.Series, title: str, filename: str, colors: Dict[str, str] = None):
        if data.empty:
            logger.warning(f"No data for pie chart: {title}")
            return None
        
        # Sanitize data: Drop NaNs and zeros
        data = data.fillna(0)
        data = data[data > 0]
        if data.empty:
            logger.warning(f"No positive data for pie chart: {title}")
            return None

        plt.figure(figsize=self._get_figsize(6, 4.5))
        color_list = None
        if colors:
            color_list = [colors.get(x, '#cccccc') for x in data.index]

        wedges, texts, autotexts = plt.pie(
            data, 
            labels=None, # No labels on pie
            autopct='%1.1f%%', 
            startangle=90, 
            colors=color_list,
            textprops=dict(color="black"),
            radius=0.9 # Smaller radius as requested (was 1.2)
        )
        
        # Determine label text color based on wedge color brightness could be nice, but black is safe for now.
        plt.setp(autotexts, size=7, weight="bold") # Smaller font
        plt.setp(texts, size=8)
        
        # Add Legend
        plt.legend(
            wedges, 
            data.index, 
            title=None, 
            loc="center left", 
            bbox_to_anchor=(1.1, 0, 0.5, 1), # Move legend slightly further right
            fontsize=7 # Smaller legend font
        )
        
        plt.title(title, fontsize=12, fontweight='bold')
        return self.save_plot(filename)

    def generate_bar_chart(self, df: pd.DataFrame, x_col: str, y_col: str, title: str, filename: str, color: str = None, figsize=None):
        if df.empty:
            return None
        
        # Sanitize
        df = df.copy()
        df[y_col] = df[y_col].fillna(0)
        
        # Use provided figsize or default (10, 6)
        base_size = figsize if figsize else (10, 6)
        plt.figure(figsize=self._get_figsize(*base_size))
        
        sns.barplot(data=df, x=x_col, y=y_col, color=color or "skyblue")
        plt.title(title, fontsize=14, fontweight='bold')
        plt.xlabel(x_col, fontsize=12)
        plt.ylabel(y_col, fontsize=12)
        plt.xticks(rotation=45, ha='right')
        return self.save_plot(filename)

    def generate_xy_chart(self, df: pd.DataFrame, x_col: str, y_col: str, title: str, filename: str):
        if df.empty: return None
        plt.figure(figsize=(10, 6))
        sns.barplot(data=df, x=x_col, y=y_col, color="lightblue")
        plt.title(title)
        return self.save_plot(filename)

    def generate_scatter_plot(self, df: pd.DataFrame, x_col: str, y_col: str, hue_col: str, title: str, filename: str):
        if df.empty: return None
        plt.figure(figsize=(10, 6))
        sns.scatterplot(data=df, x=x_col, y=y_col, hue=hue_col, style=hue_col)
        plt.title(title)
        return self.save_plot(filename)

    def generate_histogram(self, df: pd.DataFrame, col: str, title: str, filename: str, bins=50, color='skyblue'):
        if df.empty: return None
        plt.figure(figsize=(10, 6))
        
        # Calculate statistics
        mean_val = df[col].mean()
        std_val = df[col].std()
        p95_val = df[col].quantile(0.95)
        
        plt.hist(df[col], bins=bins, alpha=0.7, color=color, edgecolor='black')
        plt.title(title, fontsize=14, fontweight='bold')
        plt.xlabel(col.replace('_', ' ').title())
        plt.ylabel('Frequency')
        
        # Add summary lines
        plt.axvline(mean_val, color='red', linestyle='--', linewidth=2, label=f'Mean: {mean_val:.2f}')
        plt.axvline(p95_val, color='orange', linestyle='-.', linewidth=2, label=f'P95: {p95_val:.2f}')
        plt.legend()
        
        return self.save_plot(filename)

    def generate_stacked_bar(self, df: pd.DataFrame, x_col: str, y_col: str, hue_col: str, title: str, filename: str):
        if df.empty: return None
        
        # Aggregate data for stacking
        pivot_df = df.groupby([x_col, hue_col]).size().unstack(fill_value=0)
        
        plt.figure(figsize=(12, 6))
        pivot_df.plot(kind='bar', stacked=True, figsize=(12, 6), colormap='viridis', edgecolor='black', alpha=0.8)
        
        plt.title(title, fontsize=14, fontweight='bold')
        plt.xlabel(x_col.replace('_', ' ').title())
        plt.ylabel('Count')
        plt.xticks(rotation=45, ha='right')
        plt.legend(title=hue_col.replace('_', ' ').title(), bbox_to_anchor=(1.05, 1), loc='upper left')
        
        return self.save_plot(filename)

    def generate_category_bar(self, df: pd.DataFrame, col: str, title: str, filename: str, order=None, colors=None):
        if df.empty: return None
        
        counts = df[col].value_counts()
        if order:
            counts = counts.reindex(order, fill_value=0)
            
        plt.figure(figsize=(10, 6))
        bars = plt.bar(counts.index, counts.values, color=colors if colors else 'skyblue', edgecolor='black')
        
        plt.title(title, fontsize=14, fontweight='bold')
        plt.xlabel(col.replace('_', ' ').title())
        plt.ylabel('Count')
        plt.xticks(rotation=45, ha='right')
        
        # Add labels
        for bar in bars:
            height = bar.get_height()
            if height > 0:
                plt.text(bar.get_x() + bar.get_width()/2., height,
                         f'{int(height)}', ha='center', va='bottom')
                 
        return self.save_plot(filename)

    def generate_scatter_with_trend(self, df: pd.DataFrame, x_col: str, y_col: str, c_col: str, title: str, filename: str, scale='linear'):
        if df.empty: return None
        
        plt.figure(figsize=(10, 8))
        
        # Filter positive values for log scale
        plot_df = df.copy()
        if scale == 'log':
            plot_df = plot_df[(plot_df[x_col] > 0) & (plot_df[y_col] > 0)]
            if plot_df.empty: return None
        
        scatter = plt.scatter(plot_df[x_col], plot_df[y_col], 
                             c=plot_df[c_col] if c_col else 'blue', 
                             cmap='viridis' if c_col else None, 
                             alpha=0.6, s=20, edgecolor='black', linewidth=0.1)
        
        if c_col:
            plt.colorbar(scatter, label=c_col.replace('_', ' ').title())
            
        if scale == 'log':
            plt.xscale('log')
            # plt.yscale('log') # Optional: log-log
            
        plt.title(title, fontsize=14, fontweight='bold')
        plt.xlabel(x_col.replace('_', ' ').title() + (' (Log Scale)' if scale == 'log' else ''))
        plt.ylabel(y_col.replace('_', ' ').title())
        plt.grid(True, alpha=0.3)
        
        # Add Trend Line (Polynomial fit)
        try:
            import numpy as np
            x = plot_df[x_col]
            y = plot_df[y_col]
            
            if scale == 'log':
                x = np.log10(x)
                # y = np.log10(y) # If log-log
            
            z = np.polyfit(x, y, 1)
            p = np.poly1d(z)
            
            x_trend = np.linspace(x.min(), x.max(), 100)
            y_trend = p(x_trend)
            
            if scale == 'log':
                x_plot = 10**x_trend
                y_plot = y_trend # 10**y_trend if log-log
            else:
                x_plot = x_trend
                y_plot = y_trend
                
            plt.plot(x_plot, y_plot, "r--", linewidth=2, alpha=0.8, label='Trend')
            plt.legend()
        except Exception as e:
            logger.warning(f"Could not add trend line: {e}")

        return self.save_plot(filename)

    def generate_sequence_plot(self, df: pd.DataFrame, y_col: str, title: str, filename: str):
        if df.empty: return None
        
        df = df.sort_values('timestamp').reset_index(drop=True)
        df['request_order'] = df.index + 1
        
        plt.figure(figsize=(12, 6))
        plt.scatter(df['request_order'], df[y_col], alpha=0.6, s=15, c=df[y_col], cmap='viridis')
        
        # Moving Average
        window = max(5, len(df) // 20)
        ma = df[y_col].rolling(window=window, center=True).mean()
        plt.plot(df['request_order'], ma, color='red', linewidth=2, alpha=0.8, label=f'{window}-pt Moving Avg')
        
        plt.title(title, fontsize=14, fontweight='bold')
        plt.xlabel('Request Order')
        plt.ylabel(y_col.replace('_', ' ').title())
        plt.legend()
        plt.grid(True, alpha=0.3)
        
        return self.save_plot(filename)

class ReportGenerator:
    def __init__(self, base_dir: str = None):
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.base_dir = base_dir or os.path.dirname(__file__)
        self.report_dir = os.path.join(self.base_dir, "../reports")
        self.assets_dir = os.path.join(self.report_dir, "img", self.timestamp)
        
        # Load Config First to get scale
        self.config = self._load_config()
        self.chart_scale = self.config.get("chart_scale", 1.0)
        self.chart_gen = ChartGenerator(self.assets_dir, scale=self.chart_scale)
        
        self.report_content = []
        self.traces = {} # Stores trace_id -> spans list
        self.data = {}
        # Report Metadata
        # Report Metadata
        self.config = self._load_config()
        self.playbook = self.config.get("playbook", "overview")
        self.time_range_desc = self.config.get("time_period", "24h")
        self.generated_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        
        # Extract Percentile from config (default to 95.5 if not found)
        self.percentile = 95.5
        if "kpis" in self.config and "end_to_end" in self.config["kpis"]:
             self.percentile = self.config["kpis"]["end_to_end"].get("percentile_target", 95.5)

    def _load_config(self) -> Dict[str, Any]:
        try:
            config_path = os.path.join(dir_path, "../agents/observability_agent/config.json")
            if os.path.exists(config_path):
                with open(config_path, "r") as f:
                    data = json.load(f)
                    return data.get("config", {})
            return {}
        except Exception as e:
            logger.warning(f"Failed to load config.json: {e}")
            return {}

    def add_section(self, title: str, content: str = ""):
        self.report_content.append(f"\n## {title}\n")
        if content:
            self.report_content.append(content + "\n")

    def add_subsection(self, title: str, content: str = ""):
        self.report_content.append(f"\n### {title}\n")
        if content:
            self.report_content.append(content + "\n")

    def add_image(self, title: str, image_path: str):
        if image_path:
            rel_path = os.path.relpath(image_path, self.report_dir)
            # self.report_content.append(f"### {title}\n") # Title often redundant if image has title or section header
            self.report_content.append(f"![{title}]({rel_path})\n")

    def json_to_df(self, json_input: Any) -> pd.DataFrame:
        try:
            if isinstance(json_input, str):
                data = json.loads(json_input)
            else:
                data = json_input
                
            if isinstance(data, dict) and "data" in data and isinstance(data["data"], list):
                return pd.DataFrame(data["data"])
            if isinstance(data, list):
                return pd.DataFrame(data)
            return pd.DataFrame()
        except Exception as e:
            logger.error(f"Failed to parse JSON/Data to DataFrame: {e}")
            return pd.DataFrame()

    async def fetch_error_records(self, view_id: str, limit: int = 5, time_range: str = "24h"):
        """Fetches recent error records for a specific view."""
        where_clause = build_standard_where_clause(time_range=time_range)
        # Append error status filter
        where_clause += " AND status = 'ERROR'"
        
        query = f"""
        SELECT
            span_id, trace_id, timestamp, agent_name, root_agent_name, error_message, 
            {'model_name' if 'llm' in view_id else 'NULL as model_name'},
            {'tool_name, tool_args' if 'tool' in view_id else 'NULL as tool_name, NULL as tool_args'}
        FROM `{PROJECT_ID}.{DATASET_ID}.{view_id}` AS T
        WHERE {where_clause}
        ORDER BY timestamp DESC
        LIMIT {limit}
        """
        try:
            df = await execute_bigquery(query)
            return df
        except Exception as e:
            logger.error(f"Failed to fetch errors for {view_id}: {e}")
            return pd.DataFrame()

    async def fetch_raw_llm_data(self, time_range: str = "24h"):
        """Fetches raw LLM event data for advanced visualization."""
        where_clause = build_standard_where_clause(time_range=time_range)
        
        query = f"""
        SELECT
            timestamp,
            model_name,
            agent_name,
            duration_ms / 1000.0 AS latency_seconds,
            prompt_token_count AS input_tokens,
            candidates_token_count AS output_tokens,
            thoughts_token_count AS thought_tokens
        FROM `{PROJECT_ID}.{DATASET_ID}.llm_events_view` AS T
        WHERE {where_clause}
        AND duration_ms > 0
        ORDER BY timestamp ASC
        """
        try:
            df = await execute_bigquery(query)
            # Ensure numeric columns
            df['latency_seconds'] = pd.to_numeric(df['latency_seconds'], errors='coerce')
            df['input_tokens'] = pd.to_numeric(df['input_tokens'], errors='coerce').fillna(0)
            df['output_tokens'] = pd.to_numeric(df['output_tokens'], errors='coerce').fillna(0)
            df['thought_tokens'] = pd.to_numeric(df['thought_tokens'], errors='coerce').fillna(0)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            return df
        except Exception as e:
            logger.error(f"Failed to fetch raw LLM data: {e}")
            return pd.DataFrame()

    async def fetch_data(self):
        logger.info(f"Fetching data using analytics tools in parallel (Time Range: {self.time_range_desc})...")
        
        # Define independent tasks for parallel execution
        # 1. Agent Stats (Exclude Root to avoid duplication in Agent Level)
        task_agents = analyze_latency_grouped(
            group_by="agent_name", 
            time_range=self.time_range_desc, 
            view_id="agent_events_view", 
            percentile=self.percentile,
            exclude_root=True
        )
        task_roots = analyze_latency_grouped(
            time_range=self.time_range_desc,
            group_by="root_agent_name",
            view_id="invocation_events_view",
            percentile=self.percentile
        )
        task_tools = analyze_latency_grouped(group_by="tool_name", view_id="tool_events_view", time_range=self.time_range_desc, percentile=self.percentile)
        
        # 3. Model Performance
        task_models = analyze_latency_grouped(group_by="model_name", view_id="llm_events_view", time_range=self.time_range_desc, percentile=self.percentile)
        
        # 4. Agent Composition (Pivot Data)
        task_agent_models = analyze_latency_grouped(group_by="agent_name,model_name", view_id="llm_events_view", time_range=self.time_range_desc, percentile=self.percentile)
        
        # 5. Bottlenecks
        task_agent_slow = get_slowest_queries(limit=5, view_id="agent_events_view", time_range=self.time_range_desc)
        task_tool_slow = get_slowest_queries(limit=5, view_id="tool_events_view", time_range=self.time_range_desc)
        task_llm_slow = get_slowest_queries(limit=5, view_id="llm_events_view", time_range=self.time_range_desc)
        
        # 6. Errors (Custom Fetch)
        # Note: fetch_error_records needs to accept time_range if we want it to be dynamic there too. 
        # But for now it's hardcoded to 24h in its SQL. Let's look at fetch_error_records implementation.
        # It has `INTERVAL 24 HOUR` hardcoded. We need to fix that too if we want it to match.
        # For now, let's just fix the tool calls.
        # 6. Errors (Custom Fetch)
        task_root_errors = self.fetch_error_records("agent_events_view", 5, time_range=self.time_range_desc)
        task_tool_errors = self.fetch_error_records("tool_events_view", 5, time_range=self.time_range_desc)
        task_llm_errors = self.fetch_error_records("llm_events_view", 5, time_range=self.time_range_desc)
        
        # 7. Empty LLM Responses
        task_empty = analyze_empty_llm_responses(limit=10, time_range=self.time_range_desc)
        
        # 8. Correlation Data
        task_correlation = fetch_correlation_data(time_range=self.time_range_desc, limit=2000)

        # 9. Raw LLM Data for Advanced Charts
        task_raw_llm = self.fetch_raw_llm_data(time_range=self.time_range_desc)

        # Execute all tasks concurrently
        # task_outliers = analyze_outlier_patterns(time_range=self.time_range_desc, metric="duration_ms", threshold_percentile=0.95)

        results = await asyncio.gather(
            task_agents, task_roots, task_tools, task_models, task_agent_models,
            task_agent_slow, task_tool_slow, task_llm_slow,
            task_root_errors, task_tool_errors, task_llm_errors,
            task_empty, task_correlation, task_raw_llm #, task_outliers
        )
        
        # Unpack results
        (
            raw_agents, raw_roots, raw_tools, raw_models, raw_agent_models,
            raw_agent_slow, raw_tool_slow, raw_llm_slow,
            self.root_errors, self.tool_errors, self.llm_errors,
            raw_empty, raw_correlation, self.df_raw_llm #, raw_outliers
        ) = results
        
        raw_outliers = "{}" # Placeholder

        # Process Traces for Top Slow Queries
        # We parse raw_agent_slow immediately to get trace IDs
        # try:
        #     slow_data = json.loads(raw_agent_slow) if isinstance(raw_agent_slow, str) else raw_agent_slow
        #     # Ensure slow_data is a list of dictionaries
        #     if isinstance(slow_data, dict) and "requests" in slow_data:
        #         slow_data = slow_data["requests"]
        #     
        #     top_traces = [item.get('trace_id') for item in slow_data[:3] if item.get('trace_id')]
        #     if top_traces:
        #         trace_results = await asyncio.gather(*[fetch_trace_spans(tid) for tid in top_traces])
        #         for tid, spans in zip(top_traces, trace_results):
        #             self.traces[tid] = spans
        # except Exception as e:
        #     logger.error(f"Error fetching traces: {e}")

        # Process Results
        self.df_agents = self.json_to_df(raw_agents)
        self.df_roots = self.json_to_df(raw_roots)
        self.df_tools = self.json_to_df(raw_tools)
        self.df_models = self.json_to_df(raw_models)
        self.df_agent_models = self.json_to_df(raw_agent_models)
        self.df_correlation = self.json_to_df(raw_correlation)
        self.data['empty_llm'] = json.loads(raw_empty)
        self.data['correlation'] = json.loads(raw_correlation)
        self.data['outliers'] = json.loads(raw_outliers)
        
        # Determine and fix column names if _x/_y suffix exists (due to merge)
        new_cols = {}
        for col in self.df_agent_models.columns:
            if col.endswith('_x'):
                new_cols[col] = col[:-2]
        if new_cols:
            self.df_agent_models = self.df_agent_models.rename(columns=new_cols)

        # Bottlenecks
        self.agent_bottlenecks = self.json_to_df(json.loads(raw_agent_slow).get("requests", []))
        self.tool_bottlenecks = self.json_to_df(json.loads(raw_tool_slow).get("requests", []))
        self.llm_bottlenecks = self.json_to_df(json.loads(raw_llm_slow).get("requests", []))
        
        # Errors (Mirror root errors to agent errors as in original logic)
        self.agent_errors = self.root_errors 

        # Empty Responses
        self.empty_responses = json.loads(raw_empty)

    def _status_emoji(self, status: str) -> str:
        return "🟢" if status == "OK" else "🔴"

    def _pass_fail(self, value, target, inverse=False):
        if value is None or pd.isna(value): return "⚪"
        if inverse: # Lower is better
            return "🟢" if value <= target else "🔴"
        return "🟢" if value >= target else "🔴"

    def _format_token_metric(self, row, avg_col, p95_col):
        avg = row.get(avg_col)
        p95 = row.get(p95_col)
        if pd.isna(avg) or pd.isna(p95):
            return "-"
        return f"{int(avg)} / {int(p95)}"

    def _build_standard_table(self, df: pd.DataFrame, target_latency_sec: float, target_error_pct: float, name_col: str, include_tokens: bool = True) -> pd.DataFrame:
        if df.empty: return pd.DataFrame()
        
        df_disp = df.copy()
        total_reqs = df_disp['total_count'].sum()
        
        # Requests & %
        df_disp['Requests'] = df_disp['total_count']
        df_disp['%'] = (df_disp['total_count'] / total_reqs * 100).round(1).astype(str) + "%"
        
        # Latency (ms -> s)
        df_disp['Mean (s)'] = (df_disp['avg_ms'] / 1000).round(3)
        
        # Dynamic Percentile Column
        raw_p_col = f"p{self.percentile}_ms"
        disp_p_col = f"P{self.percentile} (s)"
        
        # Fallback if specific percentile col missing (should correspond to what was fetched)
        if raw_p_col not in df_disp.columns:
            # Try p95_ms as fallback if 95.5 was requested but somehow p95 returned?? 
            # Actually analyze_latency_grouped guarantees the key name based on input.
            # But let's be safe or just use it.
            pass

        df_disp[disp_p_col] = (df_disp.get(raw_p_col, df_disp.get('p95_ms', 0)) / 1000).round(3)
        df_disp['Target (s)'] = target_latency_sec
        
        # Latency Status
        df_disp['Status'] = df_disp[disp_p_col].apply(lambda x: self._pass_fail(x, target_latency_sec, inverse=True))
        
        # Replace NaN with "-" in Latency columns AFTER status check
        df_disp['Mean (s)'] = df_disp['Mean (s)'].apply(lambda x: "-" if pd.isna(x) else x)
        df_disp[disp_p_col] = df_disp[disp_p_col].apply(lambda x: "-" if pd.isna(x) else x)
        
        # Error & Status
        df_disp['Err %'] = df_disp['error_rate_pct']
        df_disp['Target (%)'] = target_error_pct
        df_disp['Err Status'] = df_disp['error_rate_pct'].apply(lambda x: self._pass_fail(x, target_error_pct, inverse=True))
        
        # Overall Status (Red if either is Red)
        def get_overall(row):
            if row['Status'] == "🔴" or row['Err Status'] == "🔴":
                return "🔴"
            return "🟢"
        df_disp['Overall'] = df_disp.apply(get_overall, axis=1)
        
        cols = [
            'Name', 'Requests', '%', 'Mean (s)', disp_p_col, 'Target (s)', 'Status', 
            'Err %', 'Target (%)', 'Err Status', 'Overall'
        ]
        
        if include_tokens:
            # Token Stats (Avg/P95)
            df_disp['Input Tok (Avg/P95)'] = df_disp.apply(lambda r: self._format_token_metric(r, 'avg_input_tokens', 'p95_input_tokens'), axis=1)
            df_disp['Output Tok (Avg/P95)'] = df_disp.apply(lambda r: self._format_token_metric(r, 'avg_output_tokens', 'p95_output_tokens'), axis=1)
            df_disp['Thought Tok (Avg/P95)'] = df_disp.apply(lambda r: self._format_token_metric(r, 'avg_thought_tokens', 'p95_thought_tokens'), axis=1)
            df_disp['Tokens Consumed (Avg/P95)'] = df_disp.apply(lambda r: self._format_token_metric(r, 'avg_total_tokens', 'p95_total_tokens'), axis=1)
            
            cols.insert(10, 'Status') # Insert extra status column alias if needed? User asked for "Status" twice.
            # User format: ... Status | Err % | Target (%) | Status | Input ...
            # My cols: ... Status | Err % | Target (%) | Err Status | Input ...
            # I'll rename 'Err Status' to 'Status' just before returning, but might be confusing in code.
            # Let's keep strict list.
            
            token_cols = ['Input Tok (Avg/P95)', 'Output Tok (Avg/P95)', 'Thought Tok (Avg/P95)', 'Tokens Consumed (Avg/P95)']
            # Insert before Overall
            cols = cols[:-1] + token_cols + cols[-1:]

        # Rename Name col
        df_disp = df_disp.rename(columns={name_col: 'Name'})
        
        # Handle duplicate 'Status' formatting
        # Pandas allows duplicate columns but markdown export might be tricky.
        # Markdown allows it.
        
        # Final Selection
        final_df = df_disp.copy()
        # Rename 'Err Status' to 'Status' to match user request of two 'Status' columns
        # We can't easily have duplicate column names in pandas DataFrame select.
        # We can simulate it by constructing a list of lists or renaming columns at the very end with a wrapper.
        # Or just leave it as 'Err Status' which is clearer?
        # User request: "Status | Err % | Target (%) | Status"
        # I will strictly follow if possible, but Pandas makes duplicate cols hard.
        # I'll use 'Status ' (with space) for the second one if needed to trick it, or just 'Err Status'.
        # 'Err Status' is objectively better for the reader. I will stick to 'Err Status' unless forced.
        # Actually user asked for "Status". I'll try to stick to "Status" for both if I can, but standard dataframe limits apply.
        # I'll use "Lat Status" and "Err Status" for clarity unless the user *strictly* enforced exact strings.
        # User said "Status" twice.
        # I'll use "Status" and "Status " (trailing space) or similar if I really want to match,
        # but for now "Err Status" is cleaner and safer.
        # I will modify the column list to match requested order.
        
        # Re-map columns for final output
        final_cols_order = [
            'Name', 'Requests', '%', 'Mean (s)', disp_p_col, 'Target (s)', 'Status', 
            'Err %', 'Target (%)', 'Err Status'
        ]
        if include_tokens:
            final_cols_order.extend(['Input Tok (Avg/P95)', 'Output Tok (Avg/P95)', 'Thought Tok (Avg/P95)', 'Tokens Consumed (Avg/P95)'])
        final_cols_order.append('Overall')
        
        return final_df[final_cols_order]

    def _format_links(self, df: pd.DataFrame) -> pd.DataFrame:
        """Formats trace_id and span_id as Markdown links."""
        if df.empty: return df
        df = df.copy()
        
        # Helper to safely format
        def fmt_trace(tid):
            if not tid or tid == 'N/A' or pd.isna(tid): return tid
            return f"[{tid}](https://console.cloud.google.com/traces/explorer;traceId={tid}?project={PROJECT_ID})"

        def fmt_span(row):
            tid = row.get('trace_id')
            sid = row.get('span_id')
            if not sid or sid == 'N/A' or pd.isna(sid): return sid
            if not tid or tid == 'N/A' or pd.isna(tid): return sid
            return f"[{sid}](https://console.cloud.google.com/traces/explorer;traceId={tid};spanId={sid}?project={PROJECT_ID})"

        if 'span_id' in df.columns:
            # Requires trace_id to be present for the link
            if 'trace_id' in df.columns:
                df['span_id'] = df.apply(fmt_span, axis=1)

        if 'trace_id' in df.columns:
            df['trace_id'] = df['trace_id'].apply(fmt_trace)
        
        return df

    def _add_status_pie_chart(self, df: pd.DataFrame, metric_col: str, target: float, title: str, filename: str, size_col: str = None):
        if df.empty: return

        def get_data_row(row):
            # Metric Value (for Color/Status)
            val = row.get(metric_col, 0)
            if isinstance(val, str): 
                 try: val = float(val.replace('%', ''))
                 except: val = 0
            
            # Size Value (for Slice Size)
            # If size_col is provided, use it. Otherwise use metic value.
            # Using size_col is useful for Error Status where we want to show all agents (by count) 
            # but color them by error rate.
            size_val = val
            if size_col:
                size_val = row.get(size_col, 0)
                if isinstance(size_val, str):
                    try: size_val = float(size_val.replace('%', ''))
                    except: size_val = 0

            is_good = val <= target
            status_str = "OK" if is_good else f"Exceeded > {target}" # More descriptive status
            if metric_col == 'Err %':
                 status_str = "OK" if is_good else f"Err > {target}%"

            # Label matches requested format: "Name (Status)"
            label = f"{row['Name']} ({status_str})"
            return label, size_val, is_good

        # Prepare data
        items = []
        for _, row in df.iterrows():
            lbl, size, is_good = get_data_row(row)
            if size > 0:
                items.append((lbl, size, is_good))
        
        if not items: return
        
        # Unpack
        labels, sizes, goods = zip(*items)
        data_series = pd.Series(sizes, index=labels)
        
        # Custom Colors based on 'good' status
        # map label -> color
        # Re-introduce shading logic as requested
        import matplotlib.colors as mcolors
        import colorsys

        colors = {}
        
        def generate_shades(base_hex, count):
            if count == 0: return []
            if count == 1: return [base_hex]
            
            base_rgb = mcolors.hex2color(base_hex)
            h, l, s = colorsys.rgb_to_hls(*base_rgb)
            shades = []
            
            # Generate shades by varying lightness
            # Darker to Lighter or vice-versa
            # For "OK" (Green), maybe vary from standard to lighter?
            # For "Exceeded" (Red), maybe vary from standard to darker?
            
            # Let's try a safe range that preserves the "Green-ness" or "Red-ness"
            # Start from base L, go up/down
            
            # Simple approach: Linear interpolation of lightness
            # Avoid too dark (blackish) or too light (whitish)
            
            min_l = max(0.25, l - 0.15)
            max_l = min(0.85, l + 0.25)
            
            for i in range(count):
                # Distribute l
                ratio = i / (count - 1)
                new_l = min_l + (max_l - min_l) * ratio
                # Reverse for Red? Or just keep consistent? 
                # Let's keep consistent: Darker to Lighter
                
                r, g, b = colorsys.hls_to_rgb(h, new_l, s)
                shades.append(mcolors.to_hex((r, g, b)))
            
            # Return reversed so biggest slice (usually first?) gets a specific shade?
            # Pie slices are usually plotted counter-clockwise from startangle.
            # We just map label to color.
            return shades

        # Group items by status to assign shades
        ok_items = [x for x in zip(labels, sizes, goods) if x[2]]
        bad_items = [x for x in zip(labels, sizes, goods) if not x[2]]
        
        # Sort by size desc for better visual gradient mapping
        ok_items.sort(key=lambda x: x[1], reverse=True)
        bad_items.sort(key=lambda x: x[1], reverse=True)

        ok_shades = generate_shades("#4ade80", len(ok_items)) # Green
        bad_shades = generate_shades("#ef4444", len(bad_items)) # Red
        
        for i, item in enumerate(ok_items):
            colors[item[0]] = ok_shades[i]
            
        for i, item in enumerate(bad_items):
            colors[item[0]] = bad_shades[i]

        # Generate
        path = self.chart_gen.generate_pie_chart(data_series, title, filename, colors=colors)
        if path: self.add_image(title, path)

    def build_report(self):
        # --- Header ---
        self.report_content = [f"# Autonomous Observability Intelligence Report\n"]
        
        header_data = [
            ["**Playbook**", f"`{self.playbook}`"],
            ["**Time Range**", f"`{self.time_range_desc}`"],
            ["**Datastore ID**", f"`{DATASET_ID}`"],
            ["**Table ID**", f"`{TABLE_ID}`"],
            ["**Generated**", f"`{self.generated_at}`"],
            ["**Agent Version**", f"`{AGENT_VERSION}`"],
        ]
        self.report_content.append(pd.DataFrame(header_data, columns=["Property", "Value"]).to_markdown(index=False, headers=["Property", "Value"]))
        self.report_content.append("\n---\n")

        # --- Executive Summary ---
        self.add_section("Executive Summary")
        # Placeholder for AI augmentation
        self.report_content.append("\n(Executive Summary will be generated by AI Agent)\n")
        self.report_content.append("\n---\n")

        # --- Performance ---
        self.add_section("Performance")
        self.report_content.append("\n(AI_SUMMARY: Performance)\n")
        self.report_content.append("This section provides a high-level scorecard for End to End, Sub Agent, Tool, and LLM levels, assessing compliance against defined Service Level Objectives (SLOs).\n")
        self.report_content.append("\n---\n")

        # End to End (Roots)
        self.add_subsection("End to End")
        self.report_content.append("\n(AI_SUMMARY: End to End)\n")
        self.report_content.append("This shows user-facing performance from start to end of an invocation.\n")
        if not self.df_roots.empty:
            target_lat = self.config.get("kpis", {}).get("end_to_end", {}).get("latency_target", 10.0)
            target_err = self.config.get("kpis", {}).get("end_to_end", {}).get("error_target", 5.0)
            target_p = self.config.get("kpis", {}).get("end_to_end", {}).get("percentile_target", 95.0)
            
            std_table = self._build_standard_table(
                self.df_roots, target_lat, target_err, 'root_agent_name', include_tokens=True
            )
            # Hack to allow duplicate 'Status' column in markdown
            # Convert to list of lists
            headers = list(std_table.columns)
            # Rename 'Err Status' to 'Status' in headers
            headers = [h if h != 'Err Status' else 'Status' for h in headers]
            self.report_content.append(std_table.to_markdown(index=False, headers=headers))
            self.report_content.append("\n<br>\n")
            
            # Pie charts could go here
            self.report_content.append("\n")

            # E2E Pie Charts
            # Filter out "Root Agent" if it exists, as it's often an aggregate and not a specific agent
            df_for_pie = std_table[std_table['Name'] != 'Root Agent']
            if not df_for_pie.empty:
                # 1. Latency Status
                self._add_status_pie_chart(df_for_pie, f'P{target_p} (s)', target_lat, f"E2E Latency Status (P{target_p})", "e2e_latency_pie.png", size_col=f'P{target_p} (s)')
                # 2. Error Status
                self._add_status_pie_chart(df_for_pie, 'Err %', target_err, f"E2E Error Status ({target_err:.0f}%)", "e2e_error_pie.png", size_col='Requests')

        self.report_content.append("\n---\n")

        # Agent Level
        self.add_subsection("Agent Level")
        self.report_content.append("\n(AI_SUMMARY: Agent Level)\n")
        if not self.df_agents.empty:
            target_lat = self.config.get("kpis", {}).get("agent", {}).get("latency_target", 8.0)
            target_err = self.config.get("kpis", {}).get("agent", {}).get("error_target", 5.0)
            target_p = self.config.get("kpis", {}).get("agent", {}).get("percentile_target", 95.0)
            
            std_table = self._build_standard_table(
                self.df_agents, target_lat, target_err, 'agent_name', include_tokens=True
            )
            headers = list(std_table.columns)
            headers = [h if h != 'Err Status' else 'Status' for h in headers]
            self.report_content.append(std_table.to_markdown(index=False, headers=headers))
            self.report_content.append("\n<br>\n")
            
            # Sub Agent Pie Charts
            self._add_status_pie_chart(std_table, f'P{target_p} (s)', target_lat, f"Agent Latency Status (P{target_p})", "sub_agent_p95_pie.png", size_col=f'P{target_p} (s)')
            # For Error Status, use Requests as size so we see all agents, colored by error rate
            self._add_status_pie_chart(std_table, 'Err %', target_err, f"Error Status ({target_err:.0f}%)", "sub_agent_error_pie.png", size_col='Requests')

        self.report_content.append("\n---\n")

        # Tool Level
        self.add_subsection("Tool Level")
        self.report_content.append("\n(AI_SUMMARY: Tool Level)\n")
        if not self.df_tools.empty:
            target_lat = self.config.get("kpis", {}).get("tool", {}).get("latency_target", 3.0)
            target_err = self.config.get("kpis", {}).get("tool", {}).get("error_target", 5.0)
            target_p = self.config.get("kpis", {}).get("tool", {}).get("percentile_target", 95.0)
            
            std_table = self._build_standard_table(
                self.df_tools, target_lat, target_err, 'tool_name', include_tokens=False
            )
            headers = list(std_table.columns)
            headers = [h if h != 'Err Status' else 'Status' for h in headers]
            self.report_content.append(std_table.to_markdown(index=False, headers=headers))
            self.report_content.append("\n<br>\n")
             
            # Tool Latency Bar Chart (Smaller size requested)
            df_display = std_table
            path = self.chart_gen.generate_bar_chart(
                df_display.head(10), 
                'Name', 'Mean (s)', 
                "Top 10 Tools", 
                "tool_latency.png", 
                "#f59e0b",
                figsize=(8, 5)
            )
            self.add_image("Tool Latency", path)

            # Tool Pie Charts
            self._add_status_pie_chart(std_table, f'P{target_p} (s)', target_lat, f"Tool Latency (P{target_p})", "tool_latency_pie.png", size_col=f'P{target_p} (s)')
            self._add_status_pie_chart(std_table, 'Err %', target_err, f"Tool Error Status ({target_err:.0f}%)", "tool_error_pie.png", size_col='Requests')

        self.report_content.append("\n---\n")

        # Model Level
        self.add_subsection("Model Level")
        self.report_content.append("\n(AI_SUMMARY: Model Level)\n")
        if not self.df_models.empty:
            target_lat = self.config.get("kpis", {}).get("llm", {}).get("latency_target", 5.0)
            target_err = self.config.get("kpis", {}).get("llm", {}).get("error_target", 5.0)
            target_p = self.config.get("kpis", {}).get("llm", {}).get("percentile_target", 95.0)
            
            std_table = self._build_standard_table(
                self.df_models, target_lat, target_err, 'model_name', include_tokens=True
            )
            headers = list(std_table.columns)
            headers = [h if h != 'Err Status' else 'Status' for h in headers]
            self.report_content.append(std_table.to_markdown(index=False, headers=headers))
            self.report_content.append("\n<br>\n")
            
            # Model Latency Bar Chart (Smaller size requested)
            df_display = std_table
            path = self.chart_gen.generate_bar_chart(
                df_display, 
                'Name', 'Mean (s)', 
                "Model Latency", 
                "model_latency.png", 
                "#3b82f6",
                figsize=(8, 5)
            )
            self.add_image("Model Latency", path)

            # Model Pie Charts
            self._add_status_pie_chart(std_table, f'P{target_p} (s)', target_lat, f"Model Latency Status (P{target_p})", "model_latency_pie.png", size_col=f'P{target_p} (s)')
            self._add_status_pie_chart(std_table, 'Err %', target_err, f"Model Error Status ({target_err:.0f}%)", "model_error_pie.png", size_col='Requests')

        self.report_content.append("\n---\n")


        self.add_section("Agent Composition")
        self.report_content.append("\n(AI_SUMMARY: Agent Composition)\n")
        
        self.add_subsection("Distribution")
        if isinstance(self.df_agents, pd.DataFrame) and not self.df_agents.empty:
             dist_table = self.df_agents[['agent_name', 'total_count']].copy()
             
             # Robust Root Exclusion: Filter out any agent appearing in df_roots
             if isinstance(self.df_roots, pd.DataFrame) and not self.df_roots.empty and 'root_agent_name' in self.df_roots.columns:
                 root_names = self.df_roots['root_agent_name'].unique()
                 dist_table = dist_table[~dist_table['agent_name'].isin(root_names)]
             
             total = dist_table['total_count'].sum()
             dist_table['%'] = (dist_table['total_count'] / total * 100).round(2)
             dist_table.columns = ['Name', 'Requests', '%']
             self.report_content.append(dist_table.to_markdown(index=False))
             self.report_content.append("\n<br>\n")
             
             # Agent Composition Pie Chart (Neutral Distribution)
             dist_series = dist_table.set_index('Name')['Requests']
             path = self.chart_gen.generate_pie_chart(dist_series, "Agent Composition", "agent_composition_pie.png", colors=None)
             if path: self.add_image("Agent Composition", path)

        self.add_subsection("Model Traffic")
        if isinstance(self.df_agent_models, pd.DataFrame) and not self.df_agent_models.empty:
             # Pivot: Index=Agent, Col=Model, Value=Count (%)
             try:
                 pivot_df = self.df_agent_models.pivot(index='agent_name', columns='model_name', values='total_count').fillna(0).astype(int)
                 # Calculate row sums for percentages
                 row_sums = pivot_df.sum(axis=1)
                 
                 # Create formatted DataFrame
                 formatted_pivot = pivot_df.copy().astype(object)
                 for col in pivot_df.columns:
                     formatted_pivot[col] = pivot_df[col].astype(str) + " (" + (pivot_df[col] / row_sums * 100).round(0).astype(int).astype(str) + "%)"
                 
                 formatted_pivot = formatted_pivot.replace(r"^0 \(0%\)$", "-", regex=True)
                 formatted_pivot.index.name = "Agent Name"
                 self.report_content.append(formatted_pivot.to_markdown())
                 self.report_content.append("\n<br>\n")
                 
                 # Model Usage Pie Chart (aggregated across all agents)
                 model_usage = self.df_agent_models.groupby("model_name")["total_count"].sum().reset_index()
                 model_usage.columns = ["Name", "Requests"]
                 usage_series = model_usage.set_index('Name')['Requests']
                 path = self.chart_gen.generate_pie_chart(usage_series, "Model Usage (Distribution)", "model_usage_pie.png", colors=None)
                 if path: self.add_image("Model Usage", path)
                 
             except Exception as e:
                 logger.error(f"Failed to build Model Traffic pivot: {e}")

        self.add_subsection("Model Performance")
        self.report_content.append("This table compares how specific agents perform when running on different models, highlighting optimal model choices.\n")
        if isinstance(self.df_agent_models, pd.DataFrame) and not self.df_agent_models.empty:
             # Pivot: Index=Agent, Col=Model, Value=P95 (Err%)
             try:
                 # We need to construct the value string first
                 am_df = self.df_agent_models.copy()
                 am_df['p95_sec'] = (am_df['p95_ms'] / 1000).round(3)
                 
                 def format_perf(row):
                     if pd.isna(row['p95_sec']):
                         return "-"
                     val = f"{row['p95_sec']}s ({row['error_rate_pct']}%)"
                     # Determine status (simplified check against configurable targets would be better, using hardcoded for now based on report)
                     # Assuming target 8s for agents, 5% error
                     is_bad = row['p95_sec'] > 8.0 or row['error_rate_pct'] > 5.0
                     return val + (" 🔴" if is_bad else " 🟢")

                 am_df['perf_str'] = am_df.apply(format_perf, axis=1)
                 
                 pivot_perf = am_df.pivot(index='agent_name', columns='model_name', values='perf_str').fillna("")
                 pivot_perf.index.name = "Agent Name"
                 self.report_content.append(pivot_perf.to_markdown())
                 self.report_content.append("\n<br>\n")
             except Exception as e:
                 logger.error(f"Failed to build Model Performance pivot: {e}")

        self.report_content.append("\n---\n")

        self.add_subsection("Token Statistics")
        # Per Agent Token Stats
        if isinstance(self.df_agent_models, pd.DataFrame) and not self.df_agent_models.empty:
            agents = self.df_agent_models['agent_name'].unique()
            for agent in sorted(agents):
                agent_df = self.df_agent_models[self.df_agent_models['agent_name'] == agent]
                if agent_df.empty: continue
                
                # Transpose for the specific format: Cols = Models, Rows = Metrics
                # Metrics: Mean Output, Median Output, Min, Max, Corr Latency/Output, Corr Latency/Thought
                
                # We need to prepare a dict structure first
                metrics_data = {
                    "Mean Output Tokens": {},
                    "Median Output Tokens": {},
                    "Min Output Tokens": {},
                    "Max Output Tokens": {},
                    "Latency vs Output Corr.": {},
                    "Latency vs Output+Thinking Corr.": {},
                    "Correlation Strength": {},
                }
                
                for _, row in agent_df.iterrows():
                    m = row['model_name']
                    
                    def safe_round(val):
                        if isinstance(val, (int, float)):
                            return f"{val:.2f}"
                        return "N/A"

                    metrics_data["Mean Output Tokens"][m] = safe_round(row.get('avg_output_tokens'))
                    metrics_data["Median Output Tokens"][m] = safe_round(row.get('median_output_tokens'))
                    metrics_data["Min Output Tokens"][m] = safe_round(row.get('min_output_tokens'))
                    metrics_data["Max Output Tokens"][m] = safe_round(row.get('max_output_tokens'))
                    
                    # Calculate Correlations per Agent-Model using df_raw_llm
                    if hasattr(self, 'df_raw_llm') and not self.df_raw_llm.empty:
                        subset = self.df_raw_llm[
                            (self.df_raw_llm['agent_name'] == agent) & 
                            (self.df_raw_llm['model_name'] == m)
                        ]
                        
                        if len(subset) > 1:
                            # Latency vs Output
                            corr_out = subset['latency_seconds'].corr(subset['output_tokens'])
                            metrics_data["Latency vs Output Corr."][m] = f"{corr_out:.3f}" if not pd.isna(corr_out) else "N/A"
                            
                            # Latency vs Output + Thinking
                            total_gen = subset['output_tokens'] + subset['thought_tokens']
                            corr_gen = subset['latency_seconds'].corr(total_gen)
                            metrics_data["Latency vs Output+Thinking Corr."][m] = f"{corr_gen:.3f}" if not pd.isna(corr_gen) else "N/A"
                            
                            # Strength (using Output+Thinking as primary if valid, else Output)
                            primary_corr = corr_gen if not pd.isna(corr_gen) else corr_out
                            if pd.isna(primary_corr):
                                metrics_data["Correlation Strength"][m] = "N/A"
                            else:
                                abs_corr = abs(primary_corr)
                                if abs_corr >= 0.7:
                                    metrics_data["Correlation Strength"][m] = "🟧 **Strong**"
                                elif abs_corr >= 0.4:
                                    metrics_data["Correlation Strength"][m] = "🟨 **Moderate**"
                                else:
                                    metrics_data["Correlation Strength"][m] = "🟦 **Weak**"
                        else:
                            metrics_data["Latency vs Output Corr."][m] = "N/A"
                            metrics_data["Latency vs Output+Thinking Corr."][m] = "N/A"
                            metrics_data["Correlation Strength"][m] = "N/A"
                    else:
                        metrics_data["Latency vs Output Corr."][m] = "N/A"
                        metrics_data["Latency vs Output+Thinking Corr."][m] = "N/A"
                        metrics_data["Correlation Strength"][m] = "N/A"
                
                # Convert to DF
                stats_df = pd.DataFrame(metrics_data).T
                stats_df.index.name = "Metric"
                
                self.report_content.append(f"\n**{agent}**\n")
                self.report_content.append(stats_df.to_markdown())
                self.report_content.append("\n<br>\n")
        self.report_content.append("<br>")

        self.report_content.append("\n---\n")

        self.add_section("Model Composition")
        self.report_content.append("\n(AI_SUMMARY: Model Composition)\n")
        
        self.add_subsection("Distribution")
        if isinstance(self.df_models, pd.DataFrame) and not self.df_models.empty:
             dist_table = self.df_models[['model_name', 'total_count']].copy()
             total = dist_table['total_count'].sum()
             dist_table['%'] = (dist_table['total_count'] / total * 100).round(2)
             dist_table.columns = ['Name', 'Requests', '%']
             self.report_content.append(dist_table.to_markdown(index=False))
             self.report_content.append("\n<br>\n")

        self.add_subsection("Model Performance")
        if isinstance(self.df_models, pd.DataFrame) and not self.df_models.empty:
            # Columns: Models
            # Rows: Metrics
            model_stats = {
                "Total Requests": {},
                "Mean Latency (s)": {},
                "Std Deviation (s)": {},
                "Median Latency (s)": {},
                "P95 Latency (s)": {},
                "P99 Latency (s)": {},
                "Max Latency (s)": {},
                "Outliers 2 STD Count (Percent)": {},
                "Outliers 3 STD Count (Percent)": {},
            }
            
            for _, row in self.df_models.iterrows():
                m = row['model_name']
                model_stats["Total Requests"][m] = row['total_count']
                model_stats["Mean Latency (s)"][m] = round(row['avg_ms'] / 1000, 3)
                model_stats["Std Deviation (s)"][m] = round(row['std_latency_ms'] / 1000, 3)
                model_stats["Median Latency (s)"][m] = round(row['p50_ms'] / 1000, 3)
                model_stats["P95 Latency (s)"][m] = round(row['p95_ms'] / 1000, 3)
                
                # Outlier Counts (2 STD, 3 STD)
                # We need raw data for this, or we can approximate if we only have aggregates (impossible to count exactly without raw).
                # We use df_raw_llm which should be available.
                outlier_2std = "N/A"
                outlier_3std = "N/A"
                
                if hasattr(self, 'df_raw_llm') and not self.df_raw_llm.empty and 'std_latency_ms' in row:
                    subset = self.df_raw_llm[self.df_raw_llm['model_name'] == m]
                    mean_sec = row['avg_ms'] / 1000.0
                    std_sec = row['std_latency_ms'] / 1000.0
                    count = row['total_count']
                    
                    if not subset.empty and count > 0:
                        # 2 STD
                        threshold_2 = mean_sec + (2 * std_sec)
                        count_2 = len(subset[subset['latency_seconds'] > threshold_2])
                        pct_2 = (count_2 / count) * 100
                        outlier_2std = f"{count_2} ({pct_2:.1f}%)"
                        
                        # 3 STD
                        threshold_3 = mean_sec + (3 * std_sec)
                        count_3 = len(subset[subset['latency_seconds'] > threshold_3])
                        pct_3 = (count_3 / count) * 100
                        outlier_3std = f"{count_3} ({pct_3:.1f}%)"
                
                model_stats["Outliers 2 STD Count (Percent)"][m] = outlier_2std
                model_stats["Outliers 3 STD Count (Percent)"][m] = outlier_3std
                model_stats["P99 Latency (s)"][m] = round(row['p99_ms'] / 1000, 3)
                model_stats["Max Latency (s)"][m] = round(row['max_ms'] / 1000, 3)
            
            stats_df = pd.DataFrame(model_stats).T
            stats_df.index.name = "Metric"
            self.report_content.append(stats_df.to_markdown())
            self.report_content.append("\n<br>\n")

        self.add_subsection("Token Statistics")
        if isinstance(self.df_models, pd.DataFrame) and not self.df_models.empty:
             # Calculate Correlations per model if correlation data is available
             correlation_map = {}
             if not self.df_correlation.empty:
                 # Check for thoughts_token_count
                 has_thoughts = 'thoughts_token_count' in self.df_correlation.columns
                 
                 for model in self.df_models['model_name'].unique():
                     model_corr_df = self.df_correlation[self.df_correlation['model_name'] == model].copy()
                     if len(model_corr_df) > 5: # Need enough points
                         # Output Correlation
                         try:
                             corr_out = model_corr_df['duration_ms'].corr(model_corr_df['output_token_count'])
                             correlation_map[model] = {'out': corr_out}
                             
                             if has_thoughts:
                                 # Output + Thinking
                                 # FillNA for thoughts just in case
                                 model_corr_df['thoughts_token_count'] = model_corr_df['thoughts_token_count'].fillna(0)
                                 model_corr_df['total_gen'] = model_corr_df['output_token_count'] + model_corr_df['thoughts_token_count']
                                 corr_total = model_corr_df['duration_ms'].corr(model_corr_df['total_gen'])
                                 correlation_map[model]['total'] = corr_total
                         except Exception as e:
                             logger.warning(f"Correlation calc failed for {model}: {e}")

             
             stats_rows = []
             # Define rows: Metric Name -> Col Name (in df_models)
             stat_defs = [
                 ("Mean Output Tokens", "avg_output_tokens"),
                 ("Median Output Tokens", "median_output_tokens"),
                 ("Min Output Tokens", "min_output_tokens"),
                 ("Max Output Tokens", "max_output_tokens"),
             ]
             
             # Initial Stat Rows
             for label, col in stat_defs:
                 row = {"Metric": label}
                 for _, r in self.df_models.iterrows():
                     val = r.get(col, 'N/A')
                     if pd.isna(val):
                         val = "-"
                     elif isinstance(val, (int, float)):
                         val = f"{float(val):.2f}"
                     row[r['model_name']] = val
                 stats_rows.append(row)
             
             # Correlation Rows
             row_corr_out = {"Metric": "Latency vs Output Corr."}
             row_corr_tot = {"Metric": "Latency vs Output+Thinking Corr."}
             row_strength = {"Metric": "Correlation Strength"}
             
             for model in self.df_models['model_name'].unique():
                 corrs = correlation_map.get(model, {})
                 c_out = corrs.get('out', 'N/A')
                 c_tot = corrs.get('total', 'N/A')
                 
                 row_corr_out[model] = f"{c_out:.3f}" if isinstance(c_out, float) else "N/A"
                 row_corr_tot[model] = f"{c_tot:.3f}" if isinstance(c_tot, float) else "N/A"
                 
                 # Strength Logic (using c_out or max of both?)
                 # User example shows strength row. I'll use c_tot if available, else c_out
                 val_for_strength = c_tot if isinstance(c_tot, float) else (c_out if isinstance(c_out, float) else 0)
                 
                 if val_for_strength == 0:
                     row_strength[model] = "N/A"
                 else:
                     abs_v = abs(val_for_strength)
                     if abs_v > 0.7: s_str = "🟧 **Strong**"
                     elif abs_v > 0.3: s_str = "🟨 **Moderate**"
                     else: s_str = "⬜ **Weak**"
                     row_strength[model] = s_str

             stats_rows.append(row_corr_out)
             stats_rows.append(row_corr_tot)
             stats_rows.append(row_strength)

             token_df = pd.DataFrame(stats_rows)
             self.report_content.append(token_df.to_markdown(index=False))
             self.report_content.append("\n<br>\n")

        self.add_subsection("Requests Distribution")
        
        # Per Model Latency Distribution
        if isinstance(self.df_models, pd.DataFrame) and not self.df_models.empty:
            
            # Helper for categorization
            def get_latency_category_new(latency_sec):
                if latency_sec < 1.0: return 'Very Fast (< 1s)'
                elif latency_sec < 2.0: return 'Fast (1-2s)'
                elif latency_sec < 3.0: return 'Medium (2-3s)'
                elif latency_sec < 5.0: return 'Slow (3-5s)'
                elif latency_sec < 8.0: return 'Very Slow (5-8s)'
                else: return 'Outliers (8s+)'

            categories_order = [
                'Very Fast (< 1s)', 
                'Fast (1-2s)', 
                'Medium (2-3s)', 
                'Slow (3-5s)', 
                'Very Slow (5-8s)', 
                'Outliers (8s+)'
            ]

            if hasattr(self, 'df_raw_llm') and not self.df_raw_llm.empty:
               
                models = self.df_models['model_name'].unique()
                for model in sorted(models):
                    self.report_content.append(f"\n**{model}**\n")
                    
                    subset = self.df_raw_llm[self.df_raw_llm['model_name'] == model].copy()
                    if subset.empty:
                        self.report_content.append("\n*No data available*\n")
                        continue

                    subset['category'] = subset['latency_seconds'].apply(get_latency_category_new)
                    
                    # Count per category
                    counts = subset['category'].value_counts()
                    total_count = len(subset)
                    
                    # Build Table Data
                    table_rows = []
                    for cat in categories_order:
                        c = counts.get(cat, 0)
                        pct = (c / total_count * 100) if total_count > 0 else 0
                        table_rows.append({
                            "Category": cat,
                            "Count": c,
                            "Percentage": f"{pct:.1f}%"
                        })
                    
                    dist_df = pd.DataFrame(table_rows)
                    self.report_content.append(dist_df.to_markdown(index=False))
                    self.report_content.append("\n")

                    # Mermaid Chart
                    # Prepare data array for mermaid
                    data_array = [str(counts.get(cat, 0)) for cat in categories_order]
                    # Prepare x-axis labels (shortened if needed, but categories seem ok)
                     # x-axis ["0-1s", "1-2s", "2-3s", "3-5s", "5-8s", "8s+"] matches categories roughly
                    x_axis_labels = ['"0-1s"', '"1-2s"', '"2-3s"', '"3-5s"', '"5-8s"', '"8s+"'] 
                    
                    mermaid_block = f"""
<pre><code class="language-mermaid">xychart-beta
    title "Latency Distribution: {model}"
    x-axis [{', '.join(x_axis_labels)}]
    y-axis "Count" 0 --> {max(map(int, data_array)) + 1}
    bar [{', '.join(data_array)}]
</code></pre>
"""
                    self.report_content.append(mermaid_block)
                    self.report_content.append("\n<br>\n")
            else:
                 self.report_content.append("\n*Raw LLM data required for distribution analysis.*\n")

        self.report_content.append("\n---\n")


        # 7. Hypothesis Testing: Correlation Analysis
        self.add_section("Hypothesis Testing: Latency & Tokens")
        if not self.df_correlation.empty:
            # Latency (ms) to seconds for better readability
            self.df_correlation['duration_s'] = self.df_correlation['duration_ms'] / 1000.0
            
            # Scatter Plot: Latency vs Input Tokens
            scatter_path = self.chart_gen.generate_scatter_plot(
                self.df_correlation, 
                x_col='input_token_count', 
                y_col='duration_s', 
                hue_col='model_name', 
                title='Latency vs Input Tokens by Model', 
                filename='latency_vs_input_tokens.png'
            )
            self.add_image("Latency vs Input Tokens", scatter_path)
            
            # Scatter Plot: Latency vs Output Tokens
            scatter_path_out = self.chart_gen.generate_scatter_plot(
                self.df_correlation, 
                x_col='output_token_count', 
                y_col='duration_s', 
                hue_col='model_name', 
                title='Latency vs Output Tokens by Model', 
                filename='latency_vs_output_tokens.png'
            )
            self.add_image("Latency vs Output Tokens", scatter_path_out)
        else:
            self.report_content.append("No data available for correlation analysis.\n")

        self.report_content.append("\n---\n")

        # 7. Outlier Analysis
        self.report_content.append(self._generate_outlier_analysis_section())

        # --- Advanced Charts ---
        self.add_section("Advanced Charts")
        self.generate_advanced_charts()

        # --- System Bottlenecks ---
        self.add_section("System Bottlenecks & Impact")
        self.report_content.append("\n(AI_SUMMARY: System Bottlenecks & Impact)\n")
        self.add_subsection("Top Bottlenecks")
        
        # Helper to format Top Bottlenecks
        if isinstance(self.agent_bottlenecks, pd.DataFrame) and not self.agent_bottlenecks.empty:
            df_top = self.agent_bottlenecks.copy()
            
            # Ensure columns exist or create them
            if 'duration_ms' in df_top.columns:
                df_top['Latency (s)'] = (df_top['duration_ms'] / 1000).round(3)
            else:
                df_top['Latency (s)'] = 0.0

            # Map columns to requested format
            # Requested: Rank | Timestamp | Type | Latency (s) | Name | Details (Trunk) | RCA | Session ID | Trace ID | Span ID
            
            # Generate Rank
            df_top['Rank'] = range(1, len(df_top) + 1)
            
            # RCA placeholder if not present
            if 'rca_analysis' not in df_top.columns:
                df_top['RCA'] = "N/A"
            else:
                df_top['RCA'] = df_top['rca_analysis'].fillna("N/A")

            # Rename/Map columns
            # Assuming 'start_time' is Timestamp, 'span_kind' is Type, 'agent_name' is Name, 'attributes' or 'status_message' is Details?
            # Adjust based on available data.
            # Use 'agent_name' for Name.
            # Use 'start_time' for Timestamp.
            
            # Type might be 'agent' hardcoded or from span_kind
            df_top['Type'] = 'agent' # Mostly agents in this table?
            
            # Details (Trunk) -> Truncated input/output or error message?
            # existing 'error_message' or 'input_trunc'?
            # Let's use 'error_message' if present, else 'input_trunc'
            if 'error_message' in df_top.columns:
                 df_top['Details (Trunk)'] = df_top['error_message'].fillna(df_top.get('input_trunc', '')).fillna(df_top.get('instruction', ''))
            else:
                 df_top['Details (Trunk)'] = df_top.get('input_trunc', df_top.get('instruction', ''))

            # Select and Order Columns
            cols_map = {
                'Rank': 'Rank',
                'timestamp': 'Timestamp',
                'Type': 'Type',
                'Latency (s)': 'Latency (s)',
                'agent_name': 'Name',
                'Details (Trunk)': 'Details (Trunk)',
                'RCA': 'RCA',
                'session_id': 'Session ID',
                'trace_id': 'Trace ID',
                'span_id': 'Span ID'
            }
            
            # Filter only existing columns from map keys (except created ones)
            final_cols = []
            rename_dict = {}
            
            for src, dst in cols_map.items():
                if src in df_top.columns:
                    final_cols.append(src)
                    rename_dict[src] = dst
            
            df_final_top = df_top[final_cols].rename(columns=rename_dict)
            
            # Format Links for Trace/Span IDs using _format_links logic but applying manually/carefully or reusing
            # _format_links expects specific col names... let's use it on df_top BEFORE renaming if possible?
            # _format_links modifies 'trace_id' and 'span_id' columns.
            # Let's apply standard formatting to df_final_top if we rename back or just do it manually here.
            
            # Apply link formatting manually to the final DF to ensure correct column names
            # Logic from _format_links
            for idx, row in df_final_top.iterrows():
                t_id = row.get('Trace ID')
                s_id = row.get('Span ID')
                p_id = PROJECT_ID
                
                if t_id and not str(t_id).startswith('['):
                     link = f"https://console.cloud.google.com/traces/explorer;traceId={t_id}?project={p_id}"
                     df_final_top.at[idx, 'Trace ID'] = f"[`{t_id}`]({link})"
                
                if t_id and s_id and not str(s_id).startswith('['):
                     link = f"https://console.cloud.google.com/traces/explorer;traceId={t_id};spanId={s_id}?project={p_id}"
                     df_final_top.at[idx, 'Span ID'] = f"[`{s_id}`]({link})"

            self.report_content.append(df_final_top.to_markdown(index=False))
            self.report_content.append("\n<br>\n")
        else:
            self.report_content.append("No data available for top bottlenecks.\n")
        
        self.add_subsection("LLM Bottlenecks")
        if isinstance(self.llm_bottlenecks, pd.DataFrame) and not self.llm_bottlenecks.empty:
             df_llm = self.llm_bottlenecks.copy()
             
             # Calculate/Ensure Columns
             # Requested: Rank | Timestamp | LLM (s) | TTFT (s) | Model | LLM Status | Input | Output | Thought | Total Tokens | Impact % | RCA | Agent | Agent (s) | Agent Status | Root Agent | E2E (s) | Root Status | User Message | Session ID | Trace ID | Span ID
             
             df_llm['Rank'] = range(1, len(df_llm) + 1)
             
             if 'duration_ms' in df_llm.columns:
                 df_llm['LLM (s)'] = (df_llm['duration_ms'] / 1000).round(3)
             else:
                 df_llm['LLM (s)'] = 0.0
                 
             if 'time_to_first_token_ms' in df_llm.columns:
                 df_llm['TTFT (s)'] = (df_llm['time_to_first_token_ms'] / 1000).round(3)
             else:
                 df_llm['TTFT (s)'] = 0.0
                 
             # Impact % = LLM Duration / E2E Duration (Trace Duration)
             # We need trace duration. self.traces has spans, we can find root span duration or max end time - min start time?
             # Or maybe 'attributes.e2e_duration_ms' if available?
             # For now, let's look for a 'trace_duration_ms' or similar if joined?
             # If not available, we have to estimate or leave empty.
             # The user example has Agent columns... we might not have all of them in llm_bottlenecks json directly unless the SQL query joined them.
             # Assuming standard fields are present or we mock "N/A" for missing ones to preserve structure.
             
             df_llm['Impact %'] = "N/A" # Default
             # Try to calculate if we can find trace duration
             # In fetch_raw_llm_data or similar, we might have it.
             # If 'total_latency_ms' exists (from previous logic)? 
             
             df_llm['RCA'] = df_llm.get('rca_analysis', "N/A")
             
             # Ensure columns exist before operations
             # Ensure columns exist before operations
             for col in ['prompt_tokens', 'response_tokens', 'thought_tokens']:
                 if col not in df_llm.columns:
                     df_llm[col] = 0

             # Input/Output/Thought from specific keys if available
             df_llm['Input'] = df_llm.get('preview', df_llm.get('input_trunc', ''))
             df_llm['Output'] = df_llm['response_tokens']
             df_llm['Thought'] = df_llm['thought_tokens']
             
             # Total Tokens
             df_llm['Total Tokens'] = (
                 pd.to_numeric(df_llm['prompt_tokens'], errors='coerce').fillna(0) + 
                 pd.to_numeric(df_llm['Output'], errors='coerce').fillna(0) + 
                 pd.to_numeric(df_llm['Thought'], errors='coerce').fillna(0)
             )
 
             # Details (Trunk) is redundant if we have specific columns, but keeping for consistency if needed
             # Let's map 'full_request' or 'preview' to 'Input'
             
             if 'status' in df_llm.columns:
                  df_llm['LLM Status'] = df_llm['status']
             else:
                  df_llm['LLM Status'] = "N/A"
 
             # Select and Order Columns
             cols_map = {
                'Rank': 'Rank',
                'timestamp': 'Timestamp',
                'LLM (s)': 'LLM (s)',
                'TTFT (s)': 'TTFT (s)',
                'model_name': 'Model',
                'LLM Status': 'LLM Status',
                'Input': 'Input',
                'Output': 'Output',
                'Thought': 'Thought',
                'Total Tokens': 'Total Tokens',
                'Impact %': 'Impact %',
                'RCA': 'RCA',
                'agent_name': 'Agent',
                'agent_duration': 'Agent (s)',
                'agent_status': 'Agent Status',
                'root_agent_name': 'Root Agent',
                'e2e_duration': 'E2E (s)',
                'root_status': 'Root Status',
                'user_message': 'User Message',
                'session_id': 'Session ID',
                'trace_id': 'Trace ID',
                'span_id': 'Span ID'
            }
             
             # Fill missing columns with N/A to match user request
             missing_cols = ['thought_token_count', 'agent_duration', 'agent_status', 'e2e_duration', 'root_status']
             for mc in missing_cols:
                 if mc not in df_llm.columns:
                     df_llm[mc] = "N/A"

             # Update mapping for these new placeholders
             cols_map.update({
                 'thought_token_count': 'Thought',
                 'agent_duration': 'Agent (s)',
                 'agent_status': 'Agent Status',
                 'e2e_duration': 'E2E (s)',
                 'root_status': 'Root Status'
             })
             
             # Select and Rename
             final_cols_llm = []
             rename_dict_llm = {}
             for src, dst in cols_map.items():
                 # We force all these columns to exist (some created above)
                 if src not in df_llm.columns:
                      df_llm[src] = "N/A" # Fallback
                 final_cols_llm.append(src)
                 rename_dict_llm[src] = dst
             
             df_final_llm = df_llm[final_cols_llm].rename(columns=rename_dict_llm)
             
             # Format Links
             for idx, row in df_final_llm.iterrows():
                t_id = row.get('Trace ID')
                s_id = row.get('Span ID')
                p_id = PROJECT_ID
                
                if t_id and not str(t_id).startswith('['):
                     link = f"https://console.cloud.google.com/traces/explorer;traceId={t_id}?project={p_id}"
                     df_final_llm.at[idx, 'Trace ID'] = f"[`{t_id}`]({link})"
                
                if t_id and s_id and not str(s_id).startswith('['):
                     link = f"https://console.cloud.google.com/traces/explorer;traceId={t_id};spanId={s_id}?project={p_id}"
                     df_final_llm.at[idx, 'Span ID'] = f"[`{s_id}`]({link})"

             self.report_content.append(df_final_llm.to_markdown(index=False))
             self.report_content.append("\n<br>\n")

        self.add_subsection("Tool Bottlenecks")
        if isinstance(self.tool_bottlenecks, pd.DataFrame) and not self.tool_bottlenecks.empty:
             df_tool = self.tool_bottlenecks.copy()
             # Rank | Timestamp | Tool (s) | Tool Name | Tool Status | Tool Args | Impact % | Agent | Agent (s) | Agent Status | Root Agent | E2E (s) | Root Status | User Message | Session ID | Trace ID | Span ID
             df_tool['Rank'] = range(1, len(df_tool) + 1)
             
             if 'duration_ms' in df_tool.columns:
                 df_tool['Tool (s)'] = (df_tool['duration_ms'] / 1000).round(3)
             else:
                 df_tool['Tool (s)'] = 0.0
             
             # Convert Agent Duration and E2E Duration to seconds
             if 'agent_duration' in df_tool.columns:
                 df_tool['agent_duration'] = (df_tool['agent_duration'] / 1000).round(3)
             
             if 'e2e_duration' in df_tool.columns:
                 df_tool['e2e_duration'] = (df_tool['e2e_duration'] / 1000).round(3)

             # Impact % calculation
             # Impact % = (Tool Duration / E2E Duration) * 100
             # Note: both are now in seconds, so ratio is same.
             def calc_impact(row):
                 try:
                     dur = float(row.get('duration_ms', 0)) / 1000
                     e2e = float(row.get('e2e_duration', 0)) # Already converted to seconds above? 
                     # Wait, if I convert e2e_duration above, I should use it.
                     # But duration_ms is NOT converted in place, it's put into Tool (s).
                     # Let's use duration_ms directly (in seconds) or Tool (s).
                     
                     # Re-reading: duration_ms is original.
                     # e2e_duration is updated to seconds.
                     # So: (duration_ms / 1000) / e2e_duration
                     
                     dur_s = float(row.get('duration_ms', 0)) / 1000
                     e2e_s = float(row.get('e2e_duration', 0))
                     
                     if e2e_s > 0:
                         return round((dur_s / e2e_s) * 100, 2)
                     return 0.00
                 except:
                     return 0.00
            
             df_tool['Impact %'] = df_tool.apply(calc_impact, axis=1)
             
             # Fill missing
             req_cols = ['start_time', 'tool_name', 'status_message', 'tool_args', 'agent_name', 'agent_duration', 'agent_status', 'root_agent_name', 'e2e_duration', 'root_status', 'input_trunc', 'session_id', 'trace_id', 'span_id']
             req_cols = ['start_time', 'tool_name', 'status_message', 'tool_args', 'agent_name', 'agent_duration', 'agent_status', 'root_agent_name', 'e2e_duration', 'root_status', 'input_trunc', 'session_id', 'trace_id', 'span_id', 'input_token_count', 'output_token_count', 'rca_analysis']
             for c in req_cols:
                 if c not in df_tool.columns:
                     df_tool[c] = "N/A"
                     
             # Mapping
             col_map = {
                 'Rank': 'Rank',
                 'start_time': 'Timestamp',
                 'Tool (s)': 'Tool (s)',
                 'tool_name': 'Tool',
                 'input_token_count': 'Input',
                 'output_token_count': 'Output',
                 'rca_analysis': 'RCA',
                 'agent_name': 'Agent',
                 'root_agent_name': 'Root Agent',
                 'e2e_duration': 'E2E (s)',
                 'root_status': 'Root Status',
                 'input_trunc': 'User Message',
                 'session_id': 'Session ID',
                 'trace_id': 'Trace ID',
                 'span_id': 'Span ID'
             }
             
             final_cols = []
             rename_map = {}
             for src, dst in col_map.items():
                 final_cols.append(src)
                 rename_map[src] = dst
                 
             df_final = df_tool[final_cols].rename(columns=rename_map)
             
             # Links
             for idx, row in df_final.iterrows():
                t_id = row.get('Trace ID')
                s_id = row.get('Span ID')
                p_id = PROJECT_ID
                
                if t_id and not str(t_id).startswith('['):
                     link = f"https://console.cloud.google.com/traces/explorer;traceId={t_id}?project={p_id}"
                     df_final.at[idx, 'Trace ID'] = f"[`{t_id}`]({link})"
                
                if t_id and s_id and not str(s_id).startswith('['):
                     link = f"https://console.cloud.google.com/traces/explorer;traceId={t_id};spanId={s_id}?project={p_id}"
                     df_final.at[idx, 'Span ID'] = f"[`{s_id}`]({link})"

             self.report_content.append(df_final.to_markdown(index=False))
             self.report_content.append("\n<br>\n")

        self.report_content.append("\n---\n")

        # --- Error Analysis ---
        self.add_section("Error Analysis")
        self.report_content.append("\n(AI_SUMMARY: Error Analysis)\n")
        # Helper for Error Tables
        def format_error_table(df, cols_mapping):
            if df.empty: return None
            df_err = df.copy()
            df_err['Rank'] = range(1, len(df_err) + 1)
            
            # Fill missing
            for k in cols_mapping.keys():
                if k not in df_err.columns and k != 'Rank':
                    df_err[k] = "N/A"
            
            # Select and Rename
            final_c = []
            ren_m = {}
            for src, dst in cols_mapping.items():
                final_c.append(src)
                ren_m[src] = dst
            
            df_final = df_err[final_c].rename(columns=ren_m)
            
            # Links
            for idx, row in df_final.iterrows():
                t_id = row.get('Trace ID')
                s_id = row.get('Span ID')
                p_id = PROJECT_ID
                
                if t_id and not str(t_id).startswith('['):
                     link = f"https://console.cloud.google.com/traces/explorer;traceId={t_id}?project={p_id}"
                     df_final.at[idx, 'Trace ID'] = f"[`{t_id}`]({link})"
                
                if t_id and s_id and not str(s_id).startswith('['):
                     link = f"https://console.cloud.google.com/traces/explorer;traceId={t_id};spanId={s_id}?project={p_id}"
                     df_final.at[idx, 'Span ID'] = f"[`{s_id}`]({link})" # Span ID link if present
                
                # Invocation ID link if present
                inv_id = row.get('Invocation ID')
                if inv_id and not str(inv_id).startswith('`'):
                    df_final.at[idx, 'Invocation ID'] = f"`{inv_id}`"

            return df_final.to_markdown(index=False)

        # Root Agent Errors
        self.add_subsection("Root Agent Errors")
        # Rank | Timestamp | Root Agent | Error Message | User Message | Trace ID | Invocation ID
        root_map = {
            'Rank': 'Rank',
            'start_time': 'Timestamp',
            'agent_name': 'Root Agent',
            'error_message': 'Error Message',
            'input_trunc': 'User Message',
            'trace_id': 'Trace ID',
            'invocation_id': 'Invocation ID'
        }
        
        if not self.root_errors.empty:
             # Filter logic
             if 'root_agent_name' in self.root_errors.columns:
                 roots_only = self.root_errors[self.root_errors['agent_name'] == self.root_errors['root_agent_name']]
             else:
                 roots_only = self.root_errors
                 
             if not roots_only.empty:
                 tbl = format_error_table(roots_only.head(5), root_map)
                 self.report_content.append(tbl)
                 self.report_content.append("\n<br>\n")
             else:
                 self.report_content.append("No Root Agent errors found.")
        
        self.add_subsection("Agent Errors")
        # Rank | Timestamp | Agent Name | Error Message | Root Agent | Root Status | User Message | Trace ID | Span ID
        agent_map = {
            'Rank': 'Rank',
            'start_time': 'Timestamp',
            'agent_name': 'Agent Name',
            'error_message': 'Error Message',
            'root_agent_name': 'Root Agent',
            'root_status': 'Root Status',
            'input_trunc': 'User Message',
            'trace_id': 'Trace ID',
            'span_id': 'Span ID'
        }
        if not self.agent_errors.empty:
             tbl = format_error_table(self.agent_errors.head(5), agent_map)
             self.report_content.append(tbl)
             self.report_content.append("\n<br>\n")
 
        self.add_subsection("Tool Errors")
        # Rank | Timestamp | Tool Name | Tool Args | Error Message | Parent Agent | Agent Status | Root Agent | Root Status | User Message | Trace ID | Span ID
        tool_map = {
            'Rank': 'Rank',
            'start_time': 'Timestamp',
            'tool_name': 'Tool Name',
            'tool_args': 'Tool Args',
            'error_message': 'Error Message',
            'agent_name': 'Parent Agent', # Assuming tool's parent agent name is in agent_name col or similar
            'agent_status': 'Agent Status',
            'root_agent_name': 'Root Agent',
            'root_status': 'Root Status',
            'input_trunc': 'User Message',
            'trace_id': 'Trace ID',
            'span_id': 'Span ID' 
        }
        if not self.tool_errors.empty:
             tbl = format_error_table(self.tool_errors.head(5), tool_map)
             self.report_content.append(tbl)
             self.report_content.append("\n<br>\n")
 
        self.add_subsection("LLM Errors")
        # Rank | Timestamp | Model Name | LLM Config | Error Message | Parent Agent | Agent Status | Root Agent | Root Status | User Message | Trace ID | Span ID
        llm_map = {
            'Rank': 'Rank',
            'start_time': 'Timestamp',
            'model_name': 'Model Name',
            'llm_config': 'LLM Config',
            'error_message': 'Error Message',
            'agent_name': 'Parent Agent',
            'agent_status': 'Agent Status',
            'root_agent_name': 'Root Agent',
            'root_status': 'Root Status',
            'input_trunc': 'User Message',
            'trace_id': 'Trace ID',
            'span_id': 'Span ID' 
        }
        if not self.llm_errors.empty:
             tbl = format_error_table(self.llm_errors.head(5), llm_map)
             self.report_content.append(tbl)
             self.report_content.append("\n<br>\n")

        self.report_content.append("\n---\n")

        # --- Empty LLM Responses ---
        self.add_section("Empty LLM Responses")
        if self.empty_responses and isinstance(self.empty_responses, dict):
            if "stats" in self.empty_responses:
                self.add_subsection("Summary")
                # Model Name | Agent Name | Empty Response Count
                # existing stats might not map 1:1, check keys
                # Assuming stats is a list of dicts with these keys
                stat_df = pd.DataFrame(self.empty_responses["stats"])
                # Rename if needed
                if not stat_df.empty:
                    # Rename columns to match fixed report
                    stat_df.rename(columns={
                        'model_name': 'Model Name',
                        'agent_name': 'Agent Name',
                        'count': 'Empty Response Count'
                    }, inplace=True, errors='ignore')
                    self.report_content.append(stat_df.to_markdown(index=False))
                    self.report_content.append("\n<br>\n")
            
            if "records" in self.empty_responses:
                self.add_subsection("Details")
                # Rank | Timestamp | Model Name | Agent Name | User Message | Prompt Tokens | Latency (s) | Trace ID | Span ID
                rec_df = pd.DataFrame(self.empty_responses["records"])
                
                if not rec_df.empty:
                    rec_df['Rank'] = range(1, len(rec_df) + 1)
                    
                    # Ensure Latency (s)
                    if 'duration_ms' in rec_df.columns:
                        rec_df['Latency (s)'] = (rec_df['duration_ms'] / 1000).round(3)
                    else:
                        rec_df['Latency (s)'] = 0.0
                        
                    # Map
                    rec_map = {
                        'Rank': 'Rank',
                        'start_time': 'Timestamp',
                        'model_name': 'Model Name',
                        'agent_name': 'Agent Name',
                        'input_trunc': 'User Message',
                        'prompt_token_count': 'Prompt Tokens',
                        'Latency (s)': 'Latency (s)',
                        'trace_id': 'Trace ID',
                        'span_id': 'Span ID' 
                    }
                    
                    # Use helper formatted table logic (or manually here since we have custom Latency calc)
                    # Reuse generic logic for missing cols & renaming
                    for k in rec_map.keys():
                        if k not in rec_df.columns:
                            rec_df[k] = "N/A"
                    
                    final_r = []
                    ren_r = {}
                    for s, d in rec_map.items():
                        final_r.append(s)
                        ren_r[s] = d
                    
                    df_final_rec = rec_df[final_r].rename(columns=ren_r)
                    
                    # Links
                    for idx, row in df_final_rec.iterrows():
                        t_id = row.get('Trace ID')
                        s_id = row.get('Span ID')
                        p_id = PROJECT_ID
                        
                        if t_id and not str(t_id).startswith('['):
                             link = f"https://console.cloud.google.com/traces/explorer;traceId={t_id}?project={p_id}"
                             df_final_rec.at[idx, 'Trace ID'] = f"[`{t_id}`]({link})"
                        
                        if t_id and s_id and not str(s_id).startswith('['):
                             link = f"https://console.cloud.google.com/traces/explorer;traceId={t_id};spanId={s_id}?project={p_id}"
                             df_final_rec.at[idx, 'Span ID'] = f"[`{s_id}`]({link})"
                    
                    self.report_content.append(df_final_rec.to_markdown(index=False))
                    self.report_content.append("\n<br>\n")

        self.report_content.append("\n---\n")

        # --- Recommendations ---
        # --- Root Cause Insights ---
        # Insert BEFORE Recommendations
        self.add_section("Root Cause Insights")
        self.report_content.append("(Root Cause Insights will be generated by AI Agent)\n")

        # --- Recommendations ---
        self.add_section("Recommendations")
        self.report_content.append("(Recommendations will be generated by AI Agent)\n")

        # --- Configuration ---
        self.add_section("Configuration")
        # Load Raw Config File for accuracy
        try:
             config_path = os.path.join(dir_path, "../agents/observability_agent/config.json")
             with open(config_path, 'r') as f:
                 raw_config = json.load(f)
             self.report_content.append(f"```json\n{json.dumps(raw_config, indent=2)}\n```")
        except Exception:
             # Fallback
             self.report_content.append(f"```json\n{json.dumps(self.config, indent=2)}\n```")

    def save(self) -> str:
        filename = f"observability_report_{self.timestamp}.md"
        filepath = os.path.join(self.report_dir, filename)
        full_content = "\n".join(self.report_content)
        with open(filepath, "w") as f:
            f.write(full_content)
        logger.info(f"Report saved to {filepath}")
        return full_content

    def _generate_mermaid_sequence(self, spans: list) -> str:
        """Generates a Mermaid sequence diagram from a list of spans."""
        if not spans: return ""
        
        # Build span map
        span_map = {s['span_id']: s for s in spans}
        
        # Identify participants (Agent names, Tool names)
        # We can just use the names directly, but sanitize them
        
        diagram = ["sequenceDiagram", "    participant User"]
        
        # Sort by timestamp
        # processing...
        
        for s in spans:
            # Determine caller and callee
            # If parent is null, caller is User
            # If parent exists, caller is parent's agent_name
            
            parent = span_map.get(s.get('parent_span_id'))
            
            caller = "User"
            if parent:
                caller = parent.get('agent_name') or "UnknownAgent"
            
            callee = s.get('agent_name') or s.get('tool_name') or "Unknown"
            
            # Sanitize names for Mermaid (no spaces, special chars)
            def clean(n): return n.replace(" ", "_").replace("-", "_").replace(".", "_")
            
            caller_clean = clean(caller)
            callee_clean = clean(callee)
            
            label = s.get('tool_name') or s.get('agent_name')
            if s.get('error_message'):
                label += " (ERROR)"
                
            diagram.append(f"    {caller_clean}->>{callee_clean}: {label}")
            
            # Note: A real sequence diagram needs returns or ends.
        return "\n".join(diagram)

    def generate_advanced_charts(self):
        """Generates advanced visualizations using raw LLM data."""
        if not hasattr(self, 'df_raw_llm') or self.df_raw_llm.empty:
            logger.warning("No raw LLM data available for advanced charts")
            self.report_content.append("\n*No raw LLM data available for advanced visualization.*\n")
            return

        df = self.df_raw_llm.copy()
        
        self.add_subsection("Detailed Visualization Analysis")

        # 1. Detailed Latency Histogram
        self.chart_gen.generate_histogram(
            df, 'latency_seconds', 
            'Detailed Latency Histogram', 
            'latency_histogram.png'
        )
        self.add_image("Detailed Latency Histogram", os.path.join(self.assets_dir, 'latency_histogram.png'))

        # 2. Total LLM Calls per Agent (Stacked)
        self.chart_gen.generate_stacked_bar(
            df, 'agent_name', 'None', 'model_name',
            'Total LLM Calls per Agent (Stacked by Model)',
            'agent_calls_stacked.png'
        )
        self.add_image("Total LLM Calls per Agent", os.path.join(self.assets_dir, 'agent_calls_stacked.png'))

        # 3. Latency Distribution by Category
        def categorize_latency(latency):
            if latency < 1.0: return 'Very Fast (< 1s)'
            elif latency < 2.0: return 'Fast (1-2s)'
            elif latency < 3.0: return 'Medium (2-3s)'
            elif latency < 5.0: return 'Slow (3-5s)'
            elif latency < 8.0: return 'Very Slow (5-8s)'
            else: return 'Outliers (8s+)'

        df['latency_category'] = df['latency_seconds'].apply(categorize_latency)
        category_order = ['Very Fast (< 1s)', 'Fast (1-2s)', 'Medium (2-3s)', 'Slow (3-5s)', 'Very Slow (5-8s)', 'Outliers (8s+)']
        colors = ['green', 'lightgreen', 'yellow', 'orange', 'red', 'darkred']
        
        self.chart_gen.generate_category_bar(
            df, 'latency_category',
            'Latency Distribution by Category',
            'latency_category_dist.png',
            order=category_order,
            colors=colors
        )
        self.add_image("Latency Distribution by Category", os.path.join(self.assets_dir, 'latency_category_dist.png'))

        # 4. Latency vs Output Token Count (Linear)
        self.chart_gen.generate_scatter_with_trend(
            df, 'output_tokens', 'latency_seconds', 'input_tokens',
            'Latency vs Output Token Count (Linear)',
            'latency_vs_output_linear.png',
            scale='linear'
        )
        self.add_image("Latency vs Output Token Count (Linear)", os.path.join(self.assets_dir, 'latency_vs_output_linear.png'))

        # 5. Latency vs Output Token Count (Log)
        self.chart_gen.generate_scatter_with_trend(
            df, 'output_tokens', 'latency_seconds', 'input_tokens',
            'Latency vs Output Token Count (Log Scale)',
            'latency_vs_output_log.png',
            scale='log'
        )
        self.add_image("Latency vs Output Token Count (Log)", os.path.join(self.assets_dir, 'latency_vs_output_log.png'))

        # 6. Latency vs Output + Thought Tokens
        # Check if thought_tokens has data, otherwise just use output
        if df['thought_tokens'].sum() > 0:
            df['total_generated_tokens'] = df['output_tokens'] + df['thought_tokens']
            title_suffix = "(Output + Thought)"
            x_col = 'total_generated_tokens'
        else:
            df['total_generated_tokens'] = df['output_tokens']
            title_suffix = "(Output Only - No Thoughts)"
            x_col = 'output_tokens'
            
        self.chart_gen.generate_scatter_with_trend(
            df, x_col, 'latency_seconds', 'input_tokens',
            f'Latency vs Generated Tokens {title_suffix}',
            'latency_vs_generated_tokens.png',
            scale='linear'
        )
        self.add_image(f"Latency vs Generated Tokens {title_suffix}", os.path.join(self.assets_dir, 'latency_vs_generated_tokens.png'))

        # 7. Load Test Sequence
        self.chart_gen.generate_sequence_plot(
            df, 'latency_seconds',
            'Load Test Sequence (Request Order vs Latency)',
            'load_test_sequence.png'
        )
        self.add_image("Load Test Sequence", os.path.join(self.assets_dir, 'load_test_sequence.png'))

    def _generate_outlier_analysis_section(self) -> str:
        data = self.data.get('outliers', {})
        if not data or "metadata" not in data:
             return "\n## Outlier Analysis\n\nNo outlier data available.\n"
             
        metadata = data.get('metadata', {})
        distributions = data.get('distributions', {})
        averages = data.get('averages', {})
        samples = data.get('samples', [])
        
        md = ["\n## Outlier Analysis\n"]
        md.append(f"Analysis of top 5% slowest requests (Threshold: >{metadata.get('threshold_value', 0):.2f}ms).\n")
        
        md.append("\n### Key Characteristics\n")
        
        # Agent Distribution
        if 'agent_name' in distributions:
            md.append("\n**Agent Distribution in Outliers**\n")
            md.append("| Agent | % of Outliers |")
            md.append("|:------|--------------:|")
            for agent, pct in distributions['agent_name'].items():
                md.append(f"| {agent} | {pct} |")
        
        # Averages
        md.append("\n**Average Stats for Outliers**\n")
        md.append(f"- **Avg Duration**: {averages.get('duration_ms', 0)/1000:.2f}s")
        md.append(f"- **Avg Input Tokens**: {averages.get('input_tokens', 0):.1f}")
        md.append(f"- **Avg Output Tokens**: {averages.get('output_tokens', 0):.1f}")
        
        # Samples
        md.append("\n### Sample Outliers\n")
        md.append("| Agent | Model | Duration (s) | Input Tokens | Status | Trace ID |")
        md.append("|:------|:------|-------------:|-------------:|:-------|:---------|")
        
        for s in samples[:5]:
             trace_link = f"[{s.get('trace_id')[:8]}](https://console.cloud.google.com/traces/explorer;traceId={s.get('trace_id')}?project={PROJECT_ID})"
             md.append(f"| {s.get('agent_name')} | {s.get('model_name')} | {s.get('duration_ms', 0)/1000:.2f} | {s.get('input_token_count')} | {s.get('status')} | {trace_link} |")
             
        md.append("\n\n---\n")
        return "\n".join(md)

async def generate_report_content(save_file: bool = True) -> str:
    generator = ReportGenerator(os.path.dirname(os.path.abspath(__file__))) # Pass current file's directory
    await generator.fetch_data()
    generator.build_report()
    if save_file:
        return generator.save()
    return "\n".join(generator.report_content)

async def main():
    await generate_report_content()

if __name__ == "__main__":
    asyncio.run(main())
