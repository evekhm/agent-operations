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

# Resolve FutureWarning: Downcasting object dtype arrays on .fillna, .ffill, .bfill is deprecated
pd.set_option('future.no_silent_downcasting', True)

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

    def generate_horizontal_bar_chart(self, df: pd.DataFrame, x_col: str, y_col: str, title: str, filename: str, c_col: str = None, cmap: str = 'viridis', figsize=None):
        if df.empty: return None
        
        # Use provided figsize or default (10, len(df) * 0.5 + 2)
        base_size = figsize if figsize else (10, max(6, len(df) * 0.5 + 2))
        plt.figure(figsize=self._get_figsize(*base_size))
        
        # Color mapping if c_col is provided
        colors = None
        if c_col and c_col in df.columns:
            # Normalize c_col for color mapping
            norm = plt.Normalize(df[c_col].min(), df[c_col].max())
            colors = plt.cm.get_cmap(cmap)(norm(df[c_col].values))
        
        bars = plt.barh(df[y_col], df[x_col], color=colors if colors is not None else "skyblue", edgecolor='black', alpha=0.8)
        plt.title(title, fontsize=14, fontweight='bold')
        return self.save_plot(filename)

    def generate_stacked_bar_chart(self, df: pd.DataFrame, x_col: str, y_cols: List[str], title: str, filename: str, colors: List[str] = None, figsize=None):
        if df.empty: return None
        
        base_size = figsize if figsize else (10, 8)
        plt.figure(figsize=self._get_figsize(*base_size))
        
        # Plot bottom layer first, then add subsequent layers
        bottom = None
        
        # Use provided colors or default palette
        if not colors:
            colors = sns.color_palette("muted", len(y_cols))
            
        for i, col in enumerate(y_cols):
            plt.bar(
                df[x_col], 
                df[col], 
                bottom=bottom, 
                label=col, 
                color=colors[i] if i < len(colors) else None,
                edgecolor='black',
                alpha=0.8
            )
            if bottom is None:
                bottom = df[col]
            else:
                bottom += df[col]
                
        plt.title(title, fontsize=14, fontweight='bold')
        plt.xlabel(x_col, fontsize=12)
        plt.ylabel("Latency (s)", fontsize=12)
        plt.xticks(rotation=45, ha='right')
        plt.legend()
        return self.save_plot(filename)
        plt.xlabel(x_col, fontsize=12)
        plt.ylabel(y_col, fontsize=12)
        
        # Add value labels
        for i, bar in enumerate(bars):
            width = bar.get_width()
            label = f"{width:.2f}s"
            if c_col and c_col in df.columns:
                val = df.iloc[i][c_col]
                label += f" ({int(val)} req)"
            
            plt.text(width, bar.get_y() + bar.get_height()/2, 
                     f' {label}', 
                     va='center', fontweight='bold', fontsize=9)
            
        plt.gca().invert_yaxis() # Top to bottom
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
        self.config = self._load_config()
        self.playbook = self.config.get("playbook", "overview")
        self.config = self._load_config()
        self.data_config = self.config.get("data_retrieval", {})
        self.pres_config = self.config.get("presentation", {})
        
        # Data Retrieval Settings
        self.time_range_desc = self.data_config.get("time_period", "24h")
        self.generated_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        self.playbook = self.config.get("playbook", "overview")
        
        # Extract Percentile from config (default to 95.5 if not found)
        self.percentile = 95.5
        if "kpis" in self.config and "end_to_end" in self.config["kpis"]:
             self.percentile = self.config["kpis"]["end_to_end"].get("percentile_target", 95.5)
        
        # Configurable Limits (Data)
        self.num_slowest = self.data_config.get("num_slowest_queries", 20)
        self.num_errors = self.data_config.get("num_error_queries", 20)
        
        # Presentation Settings (with Env Override)
        self.max_column_width = int(os.getenv("MAX_COLUMN_WIDTH_CHARS", self.pres_config.get("max_column_width_chars", 250)))
        self.chart_scale = float(os.getenv("CHART_SCALE", self.pres_config.get("chart_scale", 1.0)))

    def _truncate_df(self, df: pd.DataFrame) -> pd.DataFrame:
        """Truncates string columns to max_column_width."""
        if df.empty:
            return df
            
        df_trunc = df.copy()
        for col in df_trunc.columns:
            if df_trunc[col].dtype == 'object':
                # Convert to string and truncate
                df_trunc[col] = df_trunc[col].astype(str).apply(
                    lambda x: x[:self.max_column_width] + "..." if len(x) > self.max_column_width else x
                )
        return df_trunc

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
        if os.path.exists(image_path):
            rel_path = os.path.relpath(image_path, start=self.report_dir)
            # Changed self.output_dir to self.report_dir to match existing code's context
            # self.report_content.append(f"### {title}\n") # Title often redundant if image has title or section header
            # Add link to full resolution image
            # [![Title](path)](path)
            self.report_content.append(f"\n[![{title}]({rel_path})]({rel_path})\n")

    def json_to_df(self, json_input: Any) -> pd.DataFrame:
        try:
            if isinstance(json_input, pd.DataFrame):
                return json_input
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

    async def fetch_tool_errors(self, limit: int = 5):
        """Fetches detailed tool errors with context."""
        where_clause = build_standard_where_clause(time_range=self.time_range_desc)
        # T = Tool, A = Agent, I = Invocation
        query = f"""
        SELECT
            T.timestamp,
            T.tool_name,
            T.tool_args,
            T.error_message,
            T.agent_name,
            A.status AS agent_status,
            I.root_agent_name,
            I.status AS root_status,
            I.content_text_summary AS user_message,
            T.trace_id,
            T.span_id
        FROM `{PROJECT_ID}.{DATASET_ID}.tool_events_view` AS T
        LEFT JOIN `{PROJECT_ID}.{DATASET_ID}.agent_events_view` AS A ON T.parent_span_id = A.span_id
        LEFT JOIN `{PROJECT_ID}.{DATASET_ID}.invocation_events_view` AS I ON REPLACE(T.trace_id, '-', '') = REPLACE(I.trace_id, '-', '')
        WHERE {where_clause}
        AND T.status = 'ERROR'
        ORDER BY T.timestamp DESC
        LIMIT {limit}
        """
        try:
            return await execute_bigquery(query)
        except Exception as e:
            logger.error(f"Failed to fetch tool errors: {e}")
            return pd.DataFrame()

    async def fetch_llm_errors(self, limit: int = 5):
        """Fetches detailed LLM errors with context."""
        where_clause = build_standard_where_clause(time_range=self.time_range_desc, table_alias="L")
        # L = LLM, A = Agent, I = Invocation, R = Root Agent (fallback)
        query = f"""
        SELECT
            L.timestamp,
            L.model_name,
            TO_JSON_STRING(L.llm_config) AS llm_config,
            L.error_message,
            L.agent_name,
            A.status AS agent_status,
            COALESCE(I.root_agent_name, R.agent_name) AS root_agent_name,
            COALESCE(I.status, R.status) AS root_status,
            COALESCE(I.content_text_summary, R.instruction) AS user_message,
            L.trace_id,
            L.span_id
        FROM `{PROJECT_ID}.{DATASET_ID}.llm_events_view` AS L
        LEFT JOIN `{PROJECT_ID}.{DATASET_ID}.agent_events_view` AS A ON L.parent_span_id = A.span_id
        LEFT JOIN `{PROJECT_ID}.{DATASET_ID}.invocation_events_view` AS I ON REPLACE(L.trace_id, '-', '') = REPLACE(I.trace_id, '-', '')
        LEFT JOIN `{PROJECT_ID}.{DATASET_ID}.agent_events_view` AS R 
            ON REPLACE(L.trace_id, '-', '') = REPLACE(R.trace_id, '-', '') 
            AND R.parent_span_id IS NULL
        WHERE {where_clause}
        AND L.status = 'ERROR'
        ORDER BY L.timestamp DESC
        LIMIT {limit}
        """
        try:
            return await execute_bigquery(query)
        except Exception as e:
            logger.error(f"Failed to fetch LLM errors: {e}")
            return pd.DataFrame()

    async def fetch_agent_errors(self, limit: int = 5):
        """Fetches detailed Agent errors (excluding Root Agents)."""
        where_clause = build_standard_where_clause(time_range=self.time_range_desc, table_alias="A")
        # A = Agent, I = Invocation, R = Root Agent (fallback)
        query = f"""
        SELECT
            A.timestamp,
            A.agent_name,
            A.error_message,
            COALESCE(I.root_agent_name, R.agent_name) AS root_agent_name,
            COALESCE(I.status, R.status) AS root_status,
            COALESCE(I.content_text_summary, R.instruction) AS user_message,
            A.trace_id,
            A.span_id
        FROM `{PROJECT_ID}.{DATASET_ID}.agent_events_view` AS A
        LEFT JOIN `{PROJECT_ID}.{DATASET_ID}.invocation_events_view` AS I ON REPLACE(A.trace_id, '-', '') = REPLACE(I.trace_id, '-', '')
        LEFT JOIN `{PROJECT_ID}.{DATASET_ID}.agent_events_view` AS R
            ON REPLACE(A.trace_id, '-', '') = REPLACE(R.trace_id, '-', '')
            AND R.parent_span_id IS NULL
        WHERE {where_clause}
        AND A.status = 'ERROR'

        ORDER BY A.timestamp DESC
        LIMIT {limit}
        """
        try:
            return await execute_bigquery(query)
        except Exception as e:
            logger.error(f"Failed to fetch agent errors: {e}")
            return pd.DataFrame()

    async def fetch_root_errors(self, limit: int = 5):
        """Fetches detailed Root Agent errors (Invocation level)."""
        where_clause = build_standard_where_clause(time_range=self.time_range_desc)
        query = f"""
        SELECT
            timestamp,
            root_agent_name,
            error_message,
            content_text_summary AS user_message,
            trace_id,
            invocation_id
        FROM `{PROJECT_ID}.{DATASET_ID}.invocation_events_view` AS T
        WHERE {where_clause}
        AND status = 'ERROR'
        ORDER BY timestamp DESC
        LIMIT {limit}
        """
        try:
            return await execute_bigquery(query)
        except Exception as e:
            logger.error(f"Failed to fetch root errors: {e}")
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
            time_to_first_token_ms / 1000.0 AS ttft_seconds,
            prompt_token_count AS input_tokens,
            candidates_token_count AS output_tokens,
            thoughts_token_count AS thought_tokens
        FROM `{PROJECT_ID}.{DATASET_ID}.llm_events_view` AS T
        WHERE {where_clause}
        AND duration_ms > 0
        ORDER BY timestamp ASC
        LIMIT 5000
        """
        try:
            print(f"   DEBUG: Executing raw LLM query with LIMIT 5000...")
            df = await execute_bigquery(query)
            print(f"   DEBUG: Raw LLM query returned {len(df)} rows.")
            # Ensure numeric columns
            df['latency_seconds'] = pd.to_numeric(df['latency_seconds'], errors='coerce')
            df['ttft_seconds'] = pd.to_numeric(df['ttft_seconds'], errors='coerce').fillna(0)
            df['input_tokens'] = pd.to_numeric(df['input_tokens'], errors='coerce').fillna(0)
            df['output_tokens'] = pd.to_numeric(df['output_tokens'], errors='coerce').fillna(0)
            df['thought_tokens'] = pd.to_numeric(df['thought_tokens'], errors='coerce').fillna(0)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            return df
        except Exception as e:
            logger.error(f"Failed to fetch raw LLM data: {e}")
            return pd.DataFrame()


    async def fetch_llm_bottlenecks_with_details(self, limit: int = 5):
        """Fetches LLM bottlenecks with detailed join for agent and root info."""
        where_clause = build_standard_where_clause(time_range=self.time_range_desc)
        # Fix alias for root_agent_name to use Invocation view (I), then map rest to L
        where_fixed = where_clause.replace('T.root_agent_name', 'I.root_agent_name').replace('T.', 'L.')
        
        query = f"""
        SELECT
            L.timestamp,
            L.duration_ms / 1000.0 AS duration_s,
            L.time_to_first_token_ms / 1000.0 AS ttft_s,
            L.model_name,
            L.status AS status,
            SUBSTR(TO_JSON_STRING(L.full_request), 1, 50) AS input_preview,
            L.prompt_token_count,
            L.candidates_token_count AS response_token_count,
            L.thoughts_token_count AS thought_tokens,
            CAST(NULL AS STRING) AS rca_analysis,
            L.agent_name,
            A.duration_ms / 1000.0 AS agent_duration_s,
            A.status AS agent_status,
            I.root_agent_name,
            I.duration_ms / 1000.0 AS e2e_duration_s,
            I.status AS root_status,
            I.content_text_summary AS user_message,
            L.session_id,
            L.trace_id,
            L.span_id
        FROM `{PROJECT_ID}.{DATASET_ID}.llm_events_view` AS L
        LEFT JOIN `{PROJECT_ID}.{DATASET_ID}.agent_events_view` AS A ON L.parent_span_id = A.span_id
        LEFT JOIN `{PROJECT_ID}.{DATASET_ID}.invocation_events_view` AS I ON REPLACE(L.trace_id, '-' , '') = REPLACE(I.trace_id, '-' , '')
        WHERE ({where_fixed})
        AND L.duration_ms > 0
        ORDER BY L.duration_ms DESC
        LIMIT {limit}
        """
        
        try:
            df = await execute_bigquery(query) # Assuming execute_bigquery is still used, but the instruction implies self.bq_client.query
            # Reverting to original execute_bigquery as the instruction's change to self.bq_client.query().to_dataframe()
            # would require bq_client to be initialized in ReportGenerator, which is not in the provided context.
            # If the user intended to introduce bq_client, that would be a larger change.
            # Sticking to the logging part and the query string change.
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
            # For other tasks, maybe return empty list/dict/df based on type? 
            # But let's just re-raise for now to not break unpacking, unless we handle it.
            # If we re-raise, we know what failed.
            raise e

    async def fetch_data(self):
        logger.info(f"Fetching data using analytics tools in parallel (Time Range: {self.time_range_desc})...")
        
        # Define independent tasks for parallel execution
        # 1. Agent Stats (Exclude Root to avoid duplication in Agent Level)
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
        
        # 3. Model Performance
        task_models = self.trace_task("Models", analyze_latency_grouped(group_by="model_name", view_id="llm_events_view", time_range=self.time_range_desc, percentile=self.percentile))
        
        # 4. Agent Composition (Pivot Data)
        # 4. Agent Composition (Pivot Data)
        # Fetch E2E (Agent View) and LLM (LLM View) separately
        task_agent_models_e2e = self.trace_task("AgentModelsE2E", analyze_latency_grouped(group_by="agent_name,model_name", view_id="agent_events_view", time_range=self.time_range_desc, percentile=self.percentile))
        task_agent_models_llm = self.trace_task("AgentModelsLLM", analyze_latency_grouped(group_by="agent_name,model_name", view_id="llm_events_view", time_range=self.time_range_desc, percentile=self.percentile))
        
        # 5. Bottlenecks
        limit_slow = self.config.get("num_slowest_queries", 5)
        limit_error = self.config.get("num_error_queries", 5)
        
        task_agent_slow = self.trace_task("AgentSlow", get_slowest_queries(limit=limit_slow, view_id="agent_events_view", time_range=self.time_range_desc))
        task_tool_slow = self.trace_task("ToolSlow", get_slowest_queries(limit=limit_slow, view_id="tool_events_view", time_range=self.time_range_desc))
        task_llm_slow = self.trace_task("LLMSlow", self.fetch_llm_bottlenecks_with_details(limit=limit_slow))
        
        # 6. Errors (Custom Fetch)
        task_root_errors = self.trace_task("RootErrors", self.fetch_root_errors(limit=limit_error))
        task_agent_errors = self.trace_task("AgentErrors", self.fetch_agent_errors(limit=limit_error))
        task_tool_errors = self.trace_task("ToolErrors", self.fetch_tool_errors(limit=limit_error))
        task_llm_errors = self.trace_task("LLMErrors", self.fetch_llm_errors(limit=limit_error))
        
        # 7. Empty LLM Responses
        limit_empty = self.config.get("num_empty_llm_responses", 20)
        task_empty = self.trace_task("EmptyLLM", analyze_empty_llm_responses(limit=limit_empty, time_range=self.time_range_desc))
        
        # 8. Correlation Data
        task_correlation = self.trace_task("Correlation", fetch_correlation_data(time_range=self.time_range_desc, limit=2000))

        # 9. Raw LLM Data for Advanced Charts
        task_raw_llm = self.trace_task("RawLLM", self.fetch_raw_llm_data(time_range=self.time_range_desc))

        # Execute all tasks concurrently
        # task_outliers = analyze_outlier_patterns(time_range=self.time_range_desc, metric="duration_ms", threshold_percentile=0.95)

        results = await asyncio.gather(
            task_agents, task_roots, task_tools, task_models, task_agent_models_e2e, task_agent_models_llm,
            task_agent_slow, task_tool_slow, task_llm_slow,
            task_root_errors, task_agent_errors, task_tool_errors, task_llm_errors,
            task_empty, task_correlation, task_raw_llm #, task_outliers
        )
        
        # Unpack results
        (
            raw_agents, raw_roots, raw_tools, raw_models, raw_agent_models_e2e, raw_agent_models_llm,
            raw_agent_slow, raw_tool_slow, raw_llm_slow,
            self.root_errors, self.agent_errors, self.tool_errors, self.llm_errors,
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
        self.df_models = self.json_to_df(raw_models)
        self.df_agent_models_e2e = self.json_to_df(raw_agent_models_e2e)
        self.df_agent_models_llm = self.json_to_df(raw_agent_models_llm)
        
        # Default self.df_agent_models to LLM for backward compatibility if needed, 
        # but we should be explicit in usage. 
        # Token stats use LLM usually, but E2E is 'Performance'.
        # Let's alias df_agent_models to df_agent_models_llm for token stats for now, 
        # but use distinct names in sections.
        self.df_agent_models = self.df_agent_models_llm 
        self.df_correlation = self.json_to_df(raw_correlation)
        self.data['empty_llm'] = json.loads(raw_empty)
        self.data['correlation'] = json.loads(raw_correlation)
        self.data['outliers'] = json.loads(raw_outliers)
        
        # Determine and fix column names if _x/_y suffix exists (due to merge)
        for df in [self.df_agent_models_e2e, self.df_agent_models_llm, self.df_agent_models]:
             new_cols = {}
             for col in df.columns:
                 if col.endswith('_x'):
                     new_cols[col] = col[:-2]
             if new_cols:
                 df.rename(columns=new_cols, inplace=True)

        # Bottlenecks
        if isinstance(raw_agent_slow, str):
             self.agent_bottlenecks = self.json_to_df(json.loads(raw_agent_slow).get("requests", []))
        else:
             self.agent_bottlenecks = self.json_to_df(raw_agent_slow)

        if isinstance(raw_tool_slow, str):
             self.tool_bottlenecks = self.json_to_df(json.loads(raw_tool_slow).get("requests", []))
        else:
             self.tool_bottlenecks = self.json_to_df(raw_tool_slow)

        # raw_llm_slow is already a DataFrame from fetch_llm_bottlenecks_with_details
        self.llm_bottlenecks = self.json_to_df(raw_llm_slow)
        


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
        
        final_df = df_disp.copy()
        return self._bold_first_column(final_df[final_cols_order])

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
            # Clean name from bold markdown if present
            name = str(row['Name']).replace('**', '')
            label = f"{name} ({status_str})"
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

    def _bold_first_column(self, df: pd.DataFrame) -> pd.DataFrame:
        """Bolds the values in the first column of the DataFrame."""
        if df.empty:
            return df
        df = df.copy()
        first_col = df.columns[0]
        # Only apply bold if not already bolded (basic check)
        df[first_col] = df[first_col].apply(lambda x: f"**{x}**" if pd.notna(x) and str(x).strip() and not str(x).strip().startswith("**") else x)
        return df

    def _bold_index(self, df: pd.DataFrame) -> pd.DataFrame:
        """Bolds the index of the DataFrame."""
        if df.empty:
            return df
        df = df.copy()
        df.index = df.index.map(lambda x: f"**{x}**" if pd.notna(x) and not str(x).strip().startswith("**") else x)
        return df

    def _bold_columns(self, df: pd.DataFrame, columns: list) -> pd.DataFrame:
        """Bolds value in specific columns."""
        if df.empty:
            return df
        df = df.copy()
        for col in columns:
            if col in df.columns:
                df[col] = df[col].apply(lambda x: f"**{x}**" if pd.notna(x) and str(x).strip() and not str(x).strip().startswith("**") else x)
        return df

    def _bold_columns_by_pattern(self, df: pd.DataFrame, pattern: str = "Name") -> pd.DataFrame:
        """Bolds values in columns matching the pattern (case-insensitive)."""
        if df.empty:
            return df
        df = df.copy()
        for col in df.columns:
            # Check if pattern is in column name (handling bold markdown wrappers in col name)
            clean_col = col.replace('*', '').strip()
            if pattern.lower() in clean_col.lower():
                 df[col] = df[col].apply(lambda x: f"**{x}**" if pd.notna(x) and str(x).strip() and not str(x).strip().startswith("**") else x)
        return df

    def build_report(self):
        logger.info("   [BUILD] Starting build_report...")
        # --- Header ---
        self.report_content = [f"# Autonomous Observability Intelligence Report\n"]
        
        # Calculate Analysis Window
        end_dt = datetime.utcnow()
        start_dt = end_dt - timedelta(days=7) # Default
        if self.time_range_desc.endswith("d"):
            try:
                days = int(self.time_range_desc[:-1])
                start_dt = end_dt - timedelta(days=days)
            except ValueError:
                pass
        elif self.time_range_desc.endswith("h"):
            try:
                hours = int(self.time_range_desc[:-1])
                start_dt = end_dt - timedelta(hours=hours)
            except ValueError:
                pass
        
        window_str = f"{start_dt.strftime('%Y-%m-%d %H:%M:%S')} to {end_dt.strftime('%Y-%m-%d %H:%M:%S')} UTC"

        header_data = [
            ["**Playbook**", f"`{self.playbook}`"],
            ["**Time Range**", f"`{self.time_range_desc}`"],
            ["**Analysis Window**", f"`{window_str}`"],
            ["**Datastore ID**", f"`{DATASET_ID}`"],
            ["**Table ID**", f"`{TABLE_ID}`"],
            ["**Generated**", f"`{self.generated_at}`"],
            ["**Agent Version**", f"`{AGENT_VERSION}`"],
        ]
        self.report_content.append(pd.DataFrame(header_data, columns=["Property", "Value"]).to_markdown(index=False, headers=["**Property**", "**Value**"]))
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
            headers = [f"**{h}**" if h != 'Err Status' else '**Status**' for h in headers]
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
            headers = [f"**{h}**" if h != 'Err Status' else '**Status**' for h in headers]
            total_requests = self.df_agents['total_count'].sum() if 'total_count' in self.df_agents.columns else 0
            self.report_content.append(f"**Total Requests:** {total_requests}\n")
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
            headers = [f"**{h}**" if h != 'Err Status' else '**Status**' for h in headers]
            total_requests = self.df_tools['total_count'].sum() if 'total_count' in self.df_tools.columns else 0
            self.report_content.append(f"**Total Requests:** {total_requests}\n")
            self.report_content.append(std_table.to_markdown(index=False, headers=headers))
            self.report_content.append("\n<br>\n")
             


            # Tool Pie Charts
            self._add_status_pie_chart(std_table, f'P{target_p} (s)', target_lat, f"Tool Latency (P{target_p})", "tool_latency_pie.png", size_col=f'P{target_p} (s)')
            self._add_status_pie_chart(std_table, 'Err %', target_err, f"Tool Error Status ({target_err:.0f}%)", "tool_error_pie.png", size_col='Requests')

            # Tool Latency Horizontal Bar Chart (P-value + Usage)
            # Use P{target_p} (s) instead of Mean
            p_col = f'P{target_p} (s)'
            if p_col in std_table.columns:
                 # Sort by P-value desc for chart
                 df_display = std_table.sort_values(by=p_col, ascending=False).head(15).copy()
                 # Clean Name for chart
                 df_display['Name'] = df_display['Name'].astype(str).str.replace('**', '')
                 
                 path = self.chart_gen.generate_horizontal_bar_chart(
                     df_display, 
                     x_col=p_col, 
                     y_col='Name', 
                     title=f"Top Tool Latency ({p_col}) & Usage", 
                     filename="tool_latency_horizontal.png", 
                     c_col='Requests', # Color by usage
                     cmap='plasma', # Nice color map
                     figsize=(10, 8)
                 )
                 self.add_image("Tool Latency & Usage", path)

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
            headers = [f"**{h}**" if h != 'Err Status' else '**Status**' for h in headers]
            total_requests = self.df_models['total_count'].sum() if 'total_count' in self.df_models.columns else 0
            self.report_content.append(f"**Total Requests:** {total_requests}\n")
            self.report_content.append(std_table.to_markdown(index=False, headers=headers))
            self.report_content.append("\n<br>\n")
            


            # Model Pie Charts
            self._add_status_pie_chart(std_table, f'P{target_p} (s)', target_lat, f"Model Latency Status (P{target_p})", "model_latency_pie.png", size_col=f'P{target_p} (s)')
            self._add_status_pie_chart(std_table, 'Err %', target_err, f"Model Error Status ({target_err:.0f}%)", "model_error_pie.png", size_col='Requests')

            # Model Latency Horizontal Bar Chart (P-value + Usage)
            # Use P{target_p} (s) instead of Mean
            p_col = f'P{target_p} (s)'
            if p_col in std_table.columns:
                 # Sort by P-value desc for chart
                 df_display = std_table.sort_values(by=p_col, ascending=False).head(15).copy()
                 # Clean Name for chart
                 df_display['Name'] = df_display['Name'].astype(str).str.replace('**', '')
                 
                 path = self.chart_gen.generate_horizontal_bar_chart(
                     df_display, 
                     x_col=p_col, 
                     y_col='Name', 
                     title=f"Model Latency ({p_col}) & Usage", 
                     filename="model_latency_horizontal.png", 
                     c_col='Requests', # Color by usage
                     cmap='plasma', # Nice color map
                     figsize=(10, 8)
                 )
                 self.add_image("Model Latency & Usage", path)

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
             # Create temporary bold headers for markdown
             dist_table_disp = dist_table.rename(columns=lambda x: f"**{x}**")
             self.report_content.append(f"**Total Requests:** {total}\n")
             self.report_content.append(self._bold_first_column(dist_table_disp).to_markdown(index=False))
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
                 formatted_pivot.index.name = "**Agent Name**"
                 formatted_pivot.columns = [f"**{c}**" for c in formatted_pivot.columns]
                 self.report_content.append(self._bold_index(formatted_pivot).to_markdown())
                 self.report_content.append("\n<br>\n")
                 

                 






             except Exception as e:
                 logger.error(f"Failed to build Model Traffic pivot: {e}")

        self.add_subsection("Model Performance (Agent End-to-End)")
        self.report_content.append("This table compares how specific agents perform when running on different models. **Values represent Agent End-to-End Latency** (including tool execution and overhead), not just LLM generation time.\n")
        if isinstance(self.df_agent_models_e2e, pd.DataFrame) and not self.df_agent_models_e2e.empty:
             # Pivot: Index=Agent, Col=Model, Value=P95 (Err%)
             try:
                 # We need to construct the value string first
                 am_df = self.df_agent_models_e2e.copy()
                 am_df['p95_sec'] = (am_df['p95_ms'] / 1000).round(3)
                 
                 def format_perf(row):
                     if pd.isna(row['p95_sec']):
                         return "-"
                     val = f"{row['p95_sec']}s ({row['error_rate_pct']}%)"
                     # Determine status (simplified check against configurable targets would be better, using hardcoded for now based on report)
                     # Assuming target 8s for agents, 5% error
                     is_bad = row['p95_sec'] > 8.0 or row['error_rate_pct'] > 5.0
                     return ("🔴 " if is_bad else "🟢 ") + val

                 am_df['perf_str'] = am_df.apply(format_perf, axis=1)
                 
                 pivot_perf = am_df.pivot(index='agent_name', columns='model_name', values='perf_str').fillna("")
                 pivot_perf.index.name = "**Agent Name**"
                 pivot_perf.columns = [f"**{c}**" for c in pivot_perf.columns]
                 self.report_content.append(self._bold_index(pivot_perf).to_markdown())
                 self.report_content.append("\n<br>\n")
             except Exception as e:
                 logger.error(f"Failed to build Model Performance (E2E) pivot: {e}")

        self.add_subsection("LLM Generation Performance")
        self.report_content.append("This table compares the raw LLM generation time for specific agents and models. **Values represent Pure LLM Latency** (excluding agent overhead).\n")
        if isinstance(self.df_agent_models_llm, pd.DataFrame) and not self.df_agent_models_llm.empty:
             # Pivot: Index=Agent, Col=Model, Value=P95 (Err%)
             try:
                 # We need to construct the value string first
                 am_df = self.df_agent_models_llm.copy()
                 am_df['p95_sec'] = (am_df['p95_ms'] / 1000).round(3)
                 
                 def format_perf(row):
                     if pd.isna(row['p95_sec']):
                         return "-"
                     val = f"{row['p95_sec']}s ({row['error_rate_pct']}%)"
                     # Target for pure LLM is lower (e.g. 5s)
                     is_bad = row['p95_sec'] > 5.0 or row['error_rate_pct'] > 5.0
                     return ("🔴 " if is_bad else "🟢 ") + val

                 am_df['perf_str'] = am_df.apply(format_perf, axis=1)
                 
                 pivot_perf = am_df.pivot(index='agent_name', columns='model_name', values='perf_str').fillna("")
                 pivot_perf.index.name = "**Agent Name**"
                 pivot_perf.columns = [f"**{c}**" for c in pivot_perf.columns]
                 self.report_content.append(self._bold_index(pivot_perf).to_markdown())
                 self.report_content.append("\n<br>\n")
             except Exception as e:
                 logger.error(f"Failed to build LLM Generation Performance pivot: {e}")

        self.add_subsection("Latency Composition (TTFT vs Generation)")
        if hasattr(self, 'df_raw_llm') and not self.df_raw_llm.empty and 'ttft_seconds' in self.df_raw_llm.columns:
            try:
                # Group by Agent, calc mean TTFT and Generation Time (Total - TTFT)
                # Filter to top 7 agents by count
                top_agents = self.df_raw_llm['agent_name'].value_counts().head(7).index
                
                lat_comp = self.df_raw_llm[self.df_raw_llm['agent_name'].isin(top_agents)].copy()
                
                # Sanity check: Ensure ttft <= latency
                lat_comp['ttft_seconds'] = lat_comp[['ttft_seconds', 'latency_seconds']].min(axis=1) # Cap TTFT at Total Latency
                lat_comp['gen_seconds'] = lat_comp['latency_seconds'] - lat_comp['ttft_seconds']
                
                # Aggregation
                agg_df = lat_comp.groupby('agent_name')[['ttft_seconds', 'gen_seconds']].mean().reset_index()
                agg_df['total'] = agg_df['ttft_seconds'] + agg_df['gen_seconds']
                agg_df = agg_df.sort_values('total', ascending=False)
                
                # Clean names
                agg_df['agent_name'] = agg_df['agent_name'].astype(str)
                
                path = self.chart_gen.generate_stacked_bar_chart(
                    agg_df, 
                    x_col='agent_name', 
                    y_cols=['ttft_seconds', 'gen_seconds'], 
                    title="Avg Latency Composition (Top Agents)", 
                    filename="latency_composition.png",
                    colors=['#ffcc99', '#66b3ff'] # Light Orange (TTFT), Light Blue (Gen) or similar
                )
                self.add_image("Latency Composition", path)
                self.report_content.append(" Breakdown of **Time to First Token (TTFT)** vs **Generation Time**. High TTFT suggests network/queuing issues or large prompts. High Generation Time suggests complex output or slow model decoding.\n")
                
            except Exception as e:
                logger.error(f"Failed to generate Latency Composition chart: {e}")

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
                            if subset['latency_seconds'].std() > 0 and subset['output_tokens'].std() > 0:
                                corr_out = subset['latency_seconds'].corr(subset['output_tokens'])
                                metrics_data["Latency vs Output Corr."][m] = f"{corr_out:.3f}" if not pd.isna(corr_out) else "N/A"
                            else:
                                metrics_data["Latency vs Output Corr."][m] = "N/A"
                            
                            # Latency vs Output + Thinking
                            total_gen = subset['output_tokens'] + subset['thought_tokens']
                            if subset['latency_seconds'].std() > 0 and total_gen.std() > 0:
                                corr_gen = subset['latency_seconds'].corr(total_gen)
                                metrics_data["Latency vs Output+Thinking Corr."][m] = f"{corr_gen:.3f}" if not pd.isna(corr_gen) else "N/A"
                            else:
                                metrics_data["Latency vs Output+Thinking Corr."][m] = "N/A"
                                corr_gen = float('nan') # Ensure variables exist for next block
                            
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
                stats_df.columns = [f"**{c}**" for c in stats_df.columns]
                stats_df.index.name = "**Metric**"
                
                self.report_content.append(f"\n**{agent}**\n")
                self.report_content.append(self._bold_index(stats_df).to_markdown())
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
             dist_table.columns = ['**Name**', '**Requests**', '**%**']
             self.report_content.append(f"**Total Requests:** {total}\n")
             self.report_content.append(self._bold_first_column(dist_table).to_markdown(index=False))
             self.report_content.append("\n<br>\n")

             # Model Usage Pie Chart
             usage_series = self.df_models.set_index('model_name')['total_count']
             path = self.chart_gen.generate_pie_chart(usage_series, "Model Usage (Distribution)", "model_usage_pie.png", colors=None)
             if path: self.add_image("Model Usage", path)

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
            stats_df.columns = [f"**{c}**" for c in stats_df.columns]
            stats_df.index.name = "**Metric**"
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
                             # Check for constant values to avoid RuntimeWarning
                            # Check for constant values to avoid RuntimeWarning
                             # use > 0 instead of != 0 to be safe against negative variance technically impossilbe but good practice
                             if model_corr_df['duration_ms'].std() > 0 and model_corr_df['output_token_count'].std() > 0:
                                 corr_out = model_corr_df['duration_ms'].corr(model_corr_df['output_token_count'])
                             else:
                                 corr_out = float('nan')
                             
                             correlation_map[model] = {'out': corr_out}
                             
                             if has_thoughts:
                                 # Output + Thinking
                                 # FillNA for thoughts just in case
                                 model_corr_df['thoughts_token_count'] = model_corr_df['thoughts_token_count'].fillna(0)
                                 model_corr_df['total_gen'] = model_corr_df['output_token_count'] + model_corr_df['thoughts_token_count']
                                 
                                 if model_corr_df['duration_ms'].std() > 0 and model_corr_df['total_gen'].std() > 0:
                                     corr_total = model_corr_df['duration_ms'].corr(model_corr_df['total_gen'])
                                 else:
                                     corr_total = float('nan')
                                 
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
             token_df.columns = [f"**{c}**" for c in token_df.columns]
             self.report_content.append(self._bold_first_column(token_df).to_markdown(index=False))
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
                    dist_df.columns = [f"**{c}**" for c in dist_df.columns]
                    self.report_content.append(self._bold_first_column(dist_df).to_markdown(index=False))
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
        logger.info("   [BUILD] Generating Advanced Charts section...")
        self.add_section("Advanced Charts")
        self.generate_advanced_charts()

        # --- System Bottlenecks ---
        self.add_section("System Bottlenecks & Impact")
        self.report_content.append("\n(AI_SUMMARY: System Bottlenecks & Impact)\n")
        self.add_subsection("Top Bottlenecks")
        
        # Helper to format Top Bottlenecks
        if isinstance(self.agent_bottlenecks, pd.DataFrame) and not self.agent_bottlenecks.empty:
            df_top = self._truncate_df(self.agent_bottlenecks.copy())
            
            # Ensure columns exist or create them
            if 'duration_ms' in df_top.columns:
                df_top['Latency (s)'] = (df_top['duration_ms'] / 1000).round(3)
            else:
                df_top['Latency (s)'] = 0.0

            # Generate Rank
            df_top['Rank'] = range(1, len(df_top) + 1)
            
            # RCA placeholder if not present
            if 'rca_analysis' not in df_top.columns:
                df_top['RCA'] = "N/A"
            else:
                df_top['RCA'] = df_top['rca_analysis'].fillna("N/A")

            # Type might be 'agent' hardcoded or from span_kind
            df_top['Type'] = 'agent' # Mostly agents in this table?
            
            # Details (Trunk) -> Truncated input/output or error message?
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
            
            # Apply link formatting manually to the final DF to ensure correct column names
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

            df_final_top.columns = [f"**{c}**" for c in df_final_top.columns]
            
            # Use generic bolding for Name columns
            df_final_top = self._bold_columns_by_pattern(df_final_top, "Name")
            self.report_content.append(self._bold_first_column(df_final_top).to_markdown(index=False))
            self.report_content.append("\n<br>\n")
        else:
            self.report_content.append("No data available for top bottlenecks.\n")
        
        self.add_subsection("LLM Bottlenecks")
        if isinstance(self.llm_bottlenecks, pd.DataFrame) and not self.llm_bottlenecks.empty:
             df_llm = self.llm_bottlenecks.copy()
             
             # Calculate/Ensure Columns
             df_llm['Rank'] = range(1, len(df_llm) + 1)
             
             if 'duration_s' in df_llm.columns: # Already in seconds from query
                 df_llm['LLM (s)'] = df_llm['duration_s'].round(3)
             else:
                 df_llm['LLM (s)'] = 0.0
                 
             if 'ttft_s' in df_llm.columns: # Already in seconds from query
                 df_llm['TTFT (s)'] = df_llm['ttft_s'].round(3)
             else:
                 df_llm['TTFT (s)'] = 0.0
                 
             # Impact % = LLM Duration / E2E Duration (Trace Duration)
             try:
                 # Ensure numeric
                 df_llm['duration_s'] = pd.to_numeric(df_llm['duration_s'], errors='coerce').fillna(0)
                 df_llm['e2e_duration_s'] = pd.to_numeric(df_llm['e2e_duration_s'], errors='coerce').fillna(0)
                 
                 # Calculate percentage
                 df_llm['Impact %'] = (df_llm['duration_s'] / df_llm['e2e_duration_s'] * 100).round(2).apply(lambda x: f"{x}%" if pd.notnull(x) else "N/A")
             except Exception:
                 df_llm['Impact %'] = "N/A"

             df_llm['RCA'] = df_llm.get('rca_analysis', "N/A")
             
             # Ensure columns exist before operations
             for col in ['prompt_token_count', 'response_token_count', 'thought_tokens']:
                 if col not in df_llm.columns:
                     df_llm[col] = 0

             # Input/Output/Thought from specific keys if available
             df_llm['Input'] = df_llm['prompt_token_count']
             df_llm['Output'] = df_llm['response_token_count']
             df_llm['Thought'] = df_llm['thought_tokens']
             
             # Total Tokens
             df_llm['Total Tokens'] = (
                 pd.to_numeric(df_llm['Input'], errors='coerce').fillna(0) + 
                 pd.to_numeric(df_llm['Output'], errors='coerce').fillna(0) + 
                 pd.to_numeric(df_llm['Thought'], errors='coerce').fillna(0)
             )
 
             # Status to Emoji
             def status_to_emoji(s):
                 if str(s) == "OK": return "🟢"
                 if str(s) == "ERROR": return "🔴"
                 return str(s)
            
             if 'status' in df_llm.columns:
                  df_llm['LLM Status'] = df_llm['status'].apply(status_to_emoji)
             else:
                  df_llm['LLM Status'] = "N/A"

             if 'agent_status' in df_llm.columns:
                  df_llm['Agent Status'] = df_llm['agent_status'].apply(status_to_emoji)
             else:
                  df_llm['Agent Status'] = "N/A"

             if 'root_status' in df_llm.columns:
                  df_llm['Root Status'] = df_llm['root_status'].apply(status_to_emoji)
             else:
                  df_llm['Root Status'] = "N/A"

             # Select and Order Columns
             cols_map = {
                'Rank': 'Rank',
                'timestamp': 'Timestamp',
                'duration_s': 'LLM (s)',
                'ttft_s': 'TTFT (s)',
                'model_name': 'Model Name',
                'LLM Status': 'LLM Status',
                'Input': 'Input',
                'Output': 'Output',
                'Thought': 'Thought',
                'Total Tokens': 'Total Tokens',
                'Impact %': 'Impact %',
                'RCA': 'RCA',
                'agent_name': 'Agent Name',
                'agent_duration_s': 'Agent (s)',
                'Agent Status': 'Agent Status',
                'root_agent_name': 'Root Agent Name',
                'e2e_duration_s': 'E2E (s)',
                'Root Status': 'Root Status',
                'user_message': 'User Message',
                'session_id': 'Session ID',
                'trace_id': 'Trace ID',
                'span_id': 'Span ID'
            }
             
             # Fill missing columns with N/A to match user request
             cols_map.update({
                 'root_agent_name': 'Root Agent Name'
             })
             
             # Select and Rename
             final_cols_llm = []
             rename_dict_llm = {}
             for src, dst in cols_map.items():
                 # We force all these columns to exist (some created above)
                 if src not in df_llm.columns:
                      df_llm[src] = "N/A" # Fallback
                 else:
                      # Convert to object to allow "N/A" strings in numeric columns
                      df_llm[src] = df_llm[src].astype(object).fillna("N/A")
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

             df_final_llm.columns = [f"**{c}**" for c in df_final_llm.columns]
             
             # Generic Bolding
             df_final_llm = self._bold_columns_by_pattern(df_final_llm, "Name")
             self.report_content.append(self._bold_first_column(df_final_llm).to_markdown(index=False))
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
             def calc_impact(row):
                 try:
                     dur_s = float(row.get('duration_ms', 0)) / 1000
                     e2e_s = float(row.get('e2e_duration', 0))
                     
                     if e2e_s > 0:
                         return round((dur_s / e2e_s) * 100, 2)
                     return 0.00
                 except:
                     return 0.00
            
             df_tool['Impact %'] = df_tool.apply(calc_impact, axis=1)
             
             # Fill missing
             req_cols = ['timestamp', 'tool_name', 'status', 'tool_args', 'agent_name', 'agent_duration', 'agent_status', 'root_agent_name', 'e2e_duration', 'root_status', 'user_message', 'session_id', 'trace_id', 'span_id', 'input_token_count', 'output_token_count', 'rca_analysis']
             for c in req_cols:
                 if c not in df_tool.columns:
                     df_tool[c] = "N/A"
                     
             # Status to Emoji
             def status_to_emoji(s):
                 if str(s) == "OK": return "🟢"
                 if str(s) == "ERROR": return "🔴"
                 return str(s)
            
             if 'status' in df_tool.columns:
                  df_tool['Tool Status'] = df_tool['status'].apply(status_to_emoji)
             else:
                  df_tool['Tool Status'] = "N/A"

             if 'agent_status' in df_tool.columns:
                  df_tool['Agent Status'] = df_tool['agent_status'].apply(status_to_emoji)
             else:
                  df_tool['Agent Status'] = "N/A"

             if 'root_status' in df_tool.columns:
                  df_tool['Root Status'] = df_tool['root_status'].apply(status_to_emoji)
             else:
                  df_tool['Root Status'] = "N/A"

             # Mapping
             cols_map = {
                 'Rank': 'Rank',
                 'timestamp': 'Timestamp',
                 'Tool (s)': 'Tool (s)',
                 'tool_name': 'Tool Name',
                 'Tool Status': 'Tool Status',
                 'tool_args': 'Input',
                 'Impact %': 'Impact %',
                 'agent_name': 'Agent Name',
                 'agent_duration': 'Agent (s)',
                 'Agent Status': 'Agent Status',
                 'root_agent_name': 'Root Agent Name',
                 'e2e_duration': 'E2E (s)',
                 'Root Status': 'Root Status',
                 'user_message': 'User Message',
                 'session_id': 'Session ID',
                 'trace_id': 'Trace ID',
                 'span_id': 'Span ID'
             }
             
             final_cols = []
             rename_map = {}
             for src, dst in cols_map.items():
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

             df_final.columns = [f"**{c}**" for c in df_final.columns]
             
             # Generic Bolding
             df_final = self._bold_columns_by_pattern(df_final, "Name")
             self.report_content.append(self._bold_first_column(df_final).to_markdown(index=False))
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
            
            # Formats
            if 'timestamp' in df_err.columns:
                df_err['Timestamp'] = df_err['timestamp']
            
            # Fill missing
            for k, v in cols_mapping.items():
                if k not in df_err.columns and k != 'Rank':
                    df_err[k] = "N/A"
            
            # Select and Rename
            final_c = []
            ren_m = {}
            for src, dst in cols_mapping.items():
                if src in df_err.columns or src == 'Rank':
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
                     df_final.at[idx, 'Span ID'] = f"[`{s_id}`]({link})"
                
                # Invocation ID link if present
                inv_id = row.get('Invocation ID')
                if inv_id and not str(inv_id).startswith('`'):
                    df_final.at[idx, 'Invocation ID'] = f"`{inv_id}`"

            df_final.columns = [f"**{c}**" for c in df_final.columns]
            
            # Generic Bolding
            df_final = self._bold_columns_by_pattern(df_final, "Name")
            return self._bold_first_column(df_final).to_markdown(index=False)

        # 1. Root Agent Errors
        self.add_subsection("Root Errors")
        # Rank | Timestamp | Root Agent | Error Message | User Message | Trace ID | Invocation ID
        root_map = {
            'Rank': 'Rank',
            'timestamp': 'Timestamp',
            'root_agent_name': 'Root Agent',
            'error_message': 'Error Message',
            'user_message': 'User Message',
            'trace_id': 'Trace ID',
            'invocation_id': 'Invocation ID'
        }
        if not self.root_errors.empty:
            tbl = format_error_table(self._truncate_df(self.root_errors.head(self.config.get("num_error_queries", 20))), root_map)
            self.report_content.append(tbl)
            self.report_content.append("\n<br>\n")
        else:
            self.report_content.append("No Root Agent errors found.\n")

        self.report_content.append("\n---\n")


        # 2. Agent Errors
        self.add_subsection("Agent Errors")
        # Rank | Timestamp | Agent Name | Error Message | Root Agent | Root Status | User Message | Trace ID | Span ID
        agent_map = {
            'Rank': 'Rank',
            'timestamp': 'Timestamp',
            'agent_name': 'Agent Name',
            'error_message': 'Error Message',
            'root_agent_name': 'Root Agent',
            'root_status': 'Root Status',
            'user_message': 'User Message',
            'trace_id': 'Trace ID',
            'span_id': 'Span ID'
        }
        if not self.agent_errors.empty:
            if 'root_status' in self.agent_errors.columns:
                self.agent_errors['root_status'] = self.agent_errors['root_status'].apply(status_to_emoji)

            tbl = format_error_table(self._truncate_df(self.agent_errors.head(self.config.get("num_error_queries", 20))), agent_map)
            self.report_content.append(tbl)
            self.report_content.append("\n<br>\n")
        else:
            self.report_content.append("No Agent errors found.\n")

        # 3. Tool Errors
        self.add_subsection("Tool Errors")
        # Rank | Timestamp | Tool Name | Tool Args | Error Message | Parent Agent | Agent Status | Root Agent | Root Status | User Message | Trace ID | Span ID
        tool_map = {
            'Rank': 'Rank',
            'timestamp': 'Timestamp',
            'tool_name': 'Tool Name',
            'tool_args': 'Tool Args',
            'error_message': 'Error Message',
            'agent_name': 'Parent Agent',
            'agent_status': 'Agent Status',
            'root_agent_name': 'Root Agent',
            'root_status': 'Root Status',
            'user_message': 'User Message',
            'trace_id': 'Trace ID',
            'span_id': 'Span ID' 
        }
        if not self.tool_errors.empty:
             # Map status emoji
             if 'agent_status' in self.tool_errors.columns:
                 self.tool_errors['agent_status'] = self.tool_errors['agent_status'].apply(status_to_emoji)
             if 'root_status' in self.tool_errors.columns:
                 self.tool_errors['root_status'] = self.tool_errors['root_status'].apply(status_to_emoji)
                 
             tbl = format_error_table(self._truncate_df(self.tool_errors.head(self.config.get("num_error_queries", 20))), tool_map)
             self.report_content.append(tbl)
             self.report_content.append("\n<br>\n")
        else:
             self.report_content.append("No Tool errors found.\n")

        # 4. LLM Errors
        self.add_subsection("LLM Errors")
        # Rank | Timestamp | Model Name | LLM Config | Error Message | Parent Agent | Agent Status | Root Agent | Root Status | User Message | Trace ID | Span ID
        llm_map = {
            'Rank': 'Rank',
            'timestamp': 'Timestamp',
            'model_name': 'Model Name',
            'llm_config': 'LLM Config',
            'error_message': 'Error Message',
            'agent_name': 'Parent Agent',
            'agent_status': 'Agent Status',
            'root_agent_name': 'Root Agent',
            'root_status': 'Root Status',
            'user_message': 'User Message',
            'trace_id': 'Trace ID',
            'span_id': 'Span ID' 
        }
        if not self.llm_errors.empty:
             if 'agent_status' in self.llm_errors.columns:
                 self.llm_errors['agent_status'] = self.llm_errors['agent_status'].apply(status_to_emoji)
             if 'root_status' in self.llm_errors.columns:
                 self.llm_errors['root_status'] = self.llm_errors['root_status'].apply(status_to_emoji)

             tbl = format_error_table(self._truncate_df(self.llm_errors.head(self.config.get("num_error_queries", 20))), llm_map)
             self.report_content.append(tbl)
             self.report_content.append("\n<br>\n")
        else:
             self.report_content.append("No LLM errors found.\n")




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
                        'count': 'Empty Response Count',
                        'empty_response_count': 'Empty Response Count'
                    }, inplace=True, errors='ignore')
                    
                    # Reorder: Agent Name | Model Name | Count
                    cols = ['Agent Name', 'Model Name', 'Empty Response Count']
                    stat_df = stat_df[[c for c in cols if c in stat_df.columns]]
                    
                    # Bold Agent and Model Name
                    if 'Agent Name' in stat_df.columns:
                        stat_df['Agent Name'] = stat_df['Agent Name'].apply(lambda x: f"**{x}**")
                    if 'Model Name' in stat_df.columns:
                        stat_df['Model Name'] = stat_df['Model Name'].apply(lambda x: f"**{x}**")
                        
                    self.report_content.append(stat_df.to_markdown(index=False))
                    self.report_content.append("\n<br>\n")
            
            if "records" in self.empty_responses:
                self.add_subsection("Details")
                # Rank | Timestamp | Model Name | Agent Name | User Message | Prompt Tokens | Latency (s) | Trace ID | Span ID
                rec_df = pd.DataFrame(self.empty_responses["records"])
                
                if not rec_df.empty:
                    rec_df = self._truncate_df(rec_df)
                    rec_df['Rank'] = range(1, len(rec_df) + 1)
                    
                    # Ensure Latency (s)
                    if 'duration_ms' in rec_df.columns:
                        rec_df['Latency (s)'] = (rec_df['duration_ms'] / 1000).round(3)
                    else:
                        rec_df['Latency (s)'] = 0.0
                        
                    # Map
                    rec_map = {
                        'Rank': 'Rank',
                        'timestamp': 'Timestamp',
                        'start_time': 'Timestamp', # Fallback
                        'model_name': 'Model Name',
                        'agent_name': 'Agent Name',
                        'user_message': 'User Message',
                        'input_trunc': 'User Message', # Fallback
                        'prompt_tokens': 'Prompt Tokens',
                        'prompt_token_count': 'Prompt Tokens', # Fallback
                        'Latency (s)': 'Latency (s)',
                        'trace_id': 'Trace ID',
                        'span_id': 'Span ID' 
                    }
                    
                    # Use helper formatted table logic (or manually here since we have custom Latency calc)
                    # Reuse generic logic for missing cols & renaming
                    final_r = []
                    ren_r = {}
                    
                    # Prioritize keys that actually exist in rec_df
                    seen_targets = set()
                    
                    # Define desired order of Target Columns
                    desired_order = ['Rank', 'Timestamp', 'Agent Name', 'Model Name', 'User Message', 'Prompt Tokens', 'Latency (s)', 'Trace ID', 'Span ID']
                    
                    for target in desired_order:
                        # Find source key in rec_map that exists in rec_df
                        found = False
                        for src, tgt in rec_map.items():
                            if tgt == target and src in rec_df.columns:
                                final_r.append(src)
                                ren_r[src] = tgt
                                found = True
                                break
                        if not found:
                             # If not found, add N/A column
                             rec_df[target] = "N/A"
                             final_r.append(target)
                             ren_r[target] = target

                    df_final_rec = rec_df[final_r].rename(columns=ren_r)
                    
                    # Bold Agent and Model in Details too
                    if 'Agent Name' in df_final_rec.columns:
                        df_final_rec['Agent Name'] = df_final_rec['Agent Name'].apply(lambda x: f"**{x}**")
                    if 'Model Name' in df_final_rec.columns:
                        df_final_rec['Model Name'] = df_final_rec['Model Name'].apply(lambda x: f"**{x}**")
                    
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
                    
                    df_final_rec.columns = [f"**{c}**" for c in df_final_rec.columns]
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
        filename = f"observability_{self.playbook}_report_{self.timestamp}.md"
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

        logger.info("Generating advanced charts...")
        try:
            df = self.df_raw_llm.copy()
            
            self.add_subsection("Detailed Visualization Analysis")

            # 1. Detailed Latency Histogram
            try:
                self.chart_gen.generate_histogram(
                    df, 'latency_seconds', 
                    'Detailed Latency Histogram', 
                    'latency_histogram.png'
                )
                self.add_image("Detailed Latency Histogram", os.path.join(self.assets_dir, 'latency_histogram.png'))
            except Exception as e:
                logger.error(f"Failed to generate latency histogram: {e}")

            # 2. Total LLM Calls per Agent (Stacked)
            try:
                self.chart_gen.generate_stacked_bar(
                    df, 'agent_name', 'None', 'model_name',
                    'Total LLM Calls per Agent (Stacked by Model)',
                    'agent_calls_stacked.png'
                )
                self.add_image("Total LLM Calls per Agent", os.path.join(self.assets_dir, 'agent_calls_stacked.png'))
            except Exception as e:
                logger.error(f"Failed to generate stacked bar: {e}")

            # 3. Latency Distribution by Category
            try:
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
            except Exception as e:
                logger.error(f"Failed to generate latency category distribution: {e}")

            # 4. Latency vs Output Token Count (Linear)
            try:
                self.chart_gen.generate_scatter_with_trend(
                    df, 'output_tokens', 'latency_seconds', 'input_tokens',
                    'Latency vs Output Token Count (Linear)',
                    'latency_vs_output_linear.png',
                    scale='linear'
                )
                self.add_image("Latency vs Output Token Count (Linear)", os.path.join(self.assets_dir, 'latency_vs_output_linear.png'))
            except Exception as e:
                logger.error(f"Failed to generate linear scatter: {e}")

            # 5. Latency vs Output Token Count (Log)
            try:
                self.chart_gen.generate_scatter_with_trend(
                    df, 'output_tokens', 'latency_seconds', 'input_tokens',
                    'Latency vs Output Token Count (Log Scale)',
                    'latency_vs_output_log.png',
                    scale='log'
                )
                self.add_image("Latency vs Output Token Count (Log)", os.path.join(self.assets_dir, 'latency_vs_output_log.png'))
            except Exception as e:
                logger.error(f"Failed to generate log scatter: {e}")

            # 6. Latency vs Output + Thought Tokens
            try:
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
            except Exception as e:
                logger.error(f"Failed to generate token scatter: {e}")

            # 7. Load Test Sequence
            try:
                self.chart_gen.generate_sequence_plot(
                    df, 'latency_seconds',
                    'Load Test Sequence (Request Order vs Latency)',
                    'load_test_sequence.png'
                )
                self.add_image("Load Test Sequence", os.path.join(self.assets_dir, 'load_test_sequence.png'))
            except Exception as e:
                logger.error(f"Failed to generate sequence plot: {e}")

        except Exception as e:
            logger.error(f"Critical error in generate_advanced_charts: {e}")
            self.report_content.append(f"\n*Error generating advanced charts: {e}*\n")

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
