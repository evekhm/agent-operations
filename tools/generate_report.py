import asyncio
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, Any

import pandas as pd

# Resolve FutureWarning: Downcasting object dtype arrays on .fillna, .ffill, .bfill is deprecated
pd.set_option('future.no_silent_downcasting', True)

# Ensure we can import agent modules
import sys

# Ensure we can import agent modules
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from agents.observability_agent.config import (
    DATASET_ID,
    PROJECT_ID,
    AGENT_VERSION,
    TABLE_ID,
)

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from agents.observability_agent.utils.views import ensure_all_views
from report_charts import ChartGenerator, OK_COLOR, ERR_COLOR
from report_data import ReportDataManager

logger = logging.getLogger(__name__)
class ReportGenerator:
    def __init__(self, data: Dict[str, Any], config: Dict[str, Any], base_dir: str = None):
        self.data = data
        self.config = config
        self.base_dir = base_dir or os.path.dirname(__file__)
        # Default report_dir
        default_report_dir = os.path.join(self.base_dir, "../reports")
        
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.generated_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        
        # Determine writable report_dir
        self.report_dir = default_report_dir
        if not os.path.exists(self.report_dir):
            try:
                os.makedirs(self.report_dir, exist_ok=True)
            except OSError:
                 self.report_dir = os.path.abspath(".")
        
        # Test write permission
        try:
            test_file = os.path.join(self.report_dir, f".write_test_{self.timestamp}")
            with open(test_file, "w") as f:
                f.write("test")
            os.remove(test_file)
        except OSError:
            logger.warning(f"Cannot write to {self.report_dir}. Falling back to current directory.")
            self.report_dir = os.path.abspath(".")
            # try again
            try:
                test_file = os.path.join(self.report_dir, f".write_test_{self.timestamp}")
                with open(test_file, "w") as f: f.write("test")
                os.remove(test_file)
            except OSError:
                import tempfile
                logger.warning(f"Cannot write to current directory. Falling back to temp dir.")
                self.report_dir = tempfile.gettempdir()

        # Create Assets Directory (Relative to Report)
        assets_dir_name = f"report_assets_{self.timestamp}"
        self.assets_dir = os.path.join(self.report_dir, assets_dir_name)
        
        try:
            os.makedirs(self.assets_dir, exist_ok=True)
        except OSError as e:
            logger.warning(f"Failed to create assets dir at {self.assets_dir}: {e}. Falling back to system temp (images links might break).")
            import tempfile
            self.assets_dir = tempfile.mkdtemp(prefix="report_assets_")
        
        # Unpack Data
        self.df_agents = data.get('df_agents', pd.DataFrame())
        self.df_roots = data.get('df_roots', pd.DataFrame())
        self.df_tools = data.get('df_tools', pd.DataFrame())
        self.df_models = data.get('df_models', pd.DataFrame())
        self.df_agent_models_e2e = data.get('df_agent_models_e2e', pd.DataFrame())
        self.df_agent_models_llm = data.get('df_agent_models_llm', pd.DataFrame())
        self.df_agent_models = self.df_agent_models_llm
        self.df_correlation = data.get('df_correlation', pd.DataFrame())
        self.df_raw_llm = data.get('df_raw_llm', pd.DataFrame())
        self.df_raw_agents = data.get('df_raw_agents', pd.DataFrame())
        self.df_raw_invocations = data.get('df_raw_invocations', pd.DataFrame())
        
        self.agent_bottlenecks = data.get('agent_bottlenecks', pd.DataFrame())
        self.root_bottlenecks = data.get('root_bottlenecks', pd.DataFrame())
        self.tool_bottlenecks = data.get('tool_bottlenecks', pd.DataFrame())
        self.llm_bottlenecks = data.get('llm_bottlenecks', pd.DataFrame())
        
        self.root_errors = data.get('root_errors', pd.DataFrame())
        self.agent_errors = data.get('agent_errors', pd.DataFrame())
        self.tool_errors = data.get('tool_errors', pd.DataFrame())
        self.llm_errors = data.get('llm_errors', pd.DataFrame())
        
        self.empty_responses = data.get('empty_responses', {})
        
        # Config Defaults
        self.data_config = self.config.get("data_retrieval", {})
        self.pres_config = self.config.get("data_presentation", {})
        self.num_slowest_queries = self.pres_config.get("num_slowest_queries", 5)
        self.num_error_queries = self.pres_config.get("num_error_queries", 5)
        self.time_range_desc = self.data_config.get("time_period", "24h")
        self.playbook = self.config.get("playbook", "overview")
        
        self.chart_scale = float(os.getenv("CHART_SCALE", self.pres_config.get("chart_scale", 1.0)))
        self.chart_gen = ChartGenerator(self.assets_dir, scale=self.chart_scale)
        
        self.report_content = []
        
        # Extract Percentile from config (default to 95.5 if not found)
        self.percentile = 95.5
        if "kpis" in self.config and "end_to_end" in self.config["kpis"]:
             self.percentile = self.config["kpis"]["end_to_end"].get("percentile_target", 95.5)
        
        self.max_column_width = int(os.getenv("MAX_COLUMN_WIDTH_CHARS",
                                              self.pres_config.get("max_column_width_chars", 250)))






    def _format_date(self, val):
        """Formats timestamp to YYYY-MM-DD HH:MM:SS."""
        if pd.isna(val) or val == "":
            return "N/A"
        
        # Determine if it's already a datetime object
        if hasattr(val, 'strftime'):
            return val.strftime("%Y-%m-%d %H:%M:%S")
            
        s = str(val)
        # Try simplistic truncation for ISO-like strings (most common)
        # Matches 2026-02-24T18:30:44.609050+00:00 OR 2026-02-24 18:30:44.609050
        if len(s) >= 19:
            # Check for YYYY-MM-DD
            if s[4] == '-' and s[7] == '-':
                # Check for T or space
                if s[10] in ('T', ' '):
                    return s[:19].replace('T', ' ')
        
        # Fallback to pandas parsing (slower but robust)
        try:
             dt = pd.to_datetime(val)
             return dt.strftime("%Y-%m-%d %H:%M:%S")
        except:
             return s


    def _standardize_formatting(self, df):
        """Standardize timestamps and durations in DataFrame.
           Modifies DataFrame in-place and returns it.
        """
        if df.empty: return df
        
        # Timestamp Formatting
        for col in ['timestamp', 'start_time', 'end_time']:
            if col in df.columns:
                df[col] = df[col].apply(self._format_date)
        return df

    def _format_as_code(self, x):
        """Wraps JSON-like strings or dicts in backticks for markdown."""
        if x is None or pd.isna(x) or x == "":
            return "N/A"
        
        # If it's a list or dict, dump it
        if isinstance(x, (list, dict)):
            try:
                val = json.dumps(x)
                return f"`{val}`"
            except:
                return f"`{str(x)}`"
        
        s = str(x).strip()
        # Generic check: if it looks like JSON/Code, wrap it
        # We check for starting { or [ 
        if len(s) > 0 and (s.startswith('{') or s.startswith('[')):
             return f"`{s}`"
             
        return s

    def _truncate_df(self, df: pd.DataFrame) -> pd.DataFrame:
        """Truncates string columns to max_column_width."""
        if df.empty:
            return df
            
        # Remove duplicate columns to avoid ambiguity
        df_trunc = df.loc[:, ~df.columns.duplicated()].copy()
        
        for col in df_trunc.columns:
            # Check dtype safely
            if df_trunc[col].dtype == 'object':
                # Convert to string and truncate
                df_trunc[col] = df_trunc[col].astype(str).apply(
                    lambda x: x[:self.max_column_width] + "..." if len(x) > self.max_column_width else x
                )
        return df_trunc



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
            # Add link to full resolution image
            
            # The URL should point to the 4k resolution
            image_4k_path = image_path.replace('.png', '_4K.png')
            if os.path.exists(image_4k_path):
                rel_4k_path = os.path.relpath(image_4k_path, start=self.report_dir)
                self.report_content.append(f"\n[![{title}]({rel_path})]({rel_4k_path})\n")
            else:
                self.report_content.append(f"\n[![{title}]({rel_path})]({rel_path})\n")



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
        
        # Calculate derived columns
        df_disp['Requests'] = df_disp['total_count']
        df_disp['%'] = (df_disp['total_count'] / total_reqs * 100).round(1).astype(str) + "%"
        df_disp['Mean (s)'] = (df_disp['avg_ms'] / 1000).round(3)
        
        # Percentile column
        raw_p_col = f"p{self.percentile}_ms"
        # Fallback if specific percentile col missing
        if raw_p_col not in df_disp.columns:
            raw_p_col = 'p95_ms' if 'p95_ms' in df_disp.columns else None
            
        disp_p_col = f"P{self.percentile} (s)"
        if raw_p_col:
            df_disp[disp_p_col] = (df_disp[raw_p_col] / 1000).round(3)
        else:
            df_disp[disp_p_col] = None

        df_disp['Target (s)'] = target_latency_sec
        df_disp['Status'] = df_disp[disp_p_col].apply(lambda x: self._pass_fail(x, target_latency_sec, inverse=True))
        
        df_disp['Err %'] = df_disp['error_rate_pct']
        df_disp['Target (%)'] = target_error_pct
        df_disp['Err Status'] = df_disp['error_rate_pct'].apply(lambda x: self._pass_fail(x, target_error_pct, inverse=True))
        
        def get_overall(row):
            if row['Status'] == "🔴" or row['Err Status'] == "🔴":
                return "🔴"
            return "🟢"
        df_disp['Overall'] = df_disp.apply(get_overall, axis=1)

        # Replace NaN with "-" in Latency columns AFTER status check
        df_disp['Mean (s)'] = df_disp['Mean (s)'].apply(lambda x: "-" if pd.isna(x) else x)
        df_disp[disp_p_col] = df_disp[disp_p_col].apply(lambda x: "-" if pd.isna(x) else x)

        if include_tokens:
            df_disp['Input Tok (Avg/P95)'] = df_disp.apply(lambda r: self._format_token_metric(r, 'avg_input_tokens', 'p95_input_tokens'), axis=1)
            df_disp['Output Tok (Avg/P95)'] = df_disp.apply(lambda r: self._format_token_metric(r, 'avg_output_tokens', 'p95_output_tokens'), axis=1)
            df_disp['Thought Tok (Avg/P95)'] = df_disp.apply(lambda r: self._format_token_metric(r, 'avg_thought_tokens', 'p95_thought_tokens'), axis=1)
            df_disp['Tokens Consumed (Avg/P95)'] = df_disp.apply(lambda r: self._format_token_metric(r, 'avg_total_tokens', 'p95_total_tokens'), axis=1)

        df_disp = df_disp.rename(columns={name_col: 'Name'})
        
        # Define output columns
        final_cols_order = [
            'Name', 'Requests', '%', 'Mean (s)', disp_p_col, 'Target (s)', 'Status', 
            'Err %', 'Target (%)', 'Err Status'
        ]
        if include_tokens:
            final_cols_order.extend(['Input Tok (Avg/P95)', 'Output Tok (Avg/P95)', 'Thought Tok (Avg/P95)', 'Tokens Consumed (Avg/P95)'])
        final_cols_order.append('Overall')
        
        # Only select columns that exist to prevent KeyError if some token columns are missing
        final_cols_valid = [c for c in final_cols_order if c in df_disp.columns]
        
        final_df = df_disp[final_cols_valid].copy()
        return self._bold_first_column(final_df)

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

            # Label matches requested format: "Name" (removing text status since color handles it)
            name = str(row['Name']).replace('**', '')
            label = name
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

        ok_shades = generate_shades(OK_COLOR, len(ok_items)) # Muted Green
        bad_shades = generate_shades(ERR_COLOR, len(bad_items)) # Muted Red
        
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

    def _render_agent_model_charts(self):
        """Generates separate bar charts for each agent, showing Pure LLM Latency by Model."""
        if not isinstance(self.df_agent_models_llm, pd.DataFrame) or self.df_agent_models_llm.empty:
            logger.warning("No data available for Agent-Model LLM Latency charts.")
            self.add_subsection("Detailed Agent Latency by Model (Pure LLM)")
            self.report_content.append("No data available for this section (df_agent_models_llm is empty).\n")
            return

        self.add_subsection("Detailed Agent Latency by Model (Pure LLM)")
        self.report_content.append(" Breakdown of **Pure LLM Latency** (P95) for each Agent across different Models.\n")

        # Get list of agents
        agents = sorted(self.df_agent_models_llm['agent_name'].unique())
        
        # Prepare a carousel or grid? Sequential for now.
        
        for agent in agents:
            # Filter
            agent_df = self.df_agent_models_llm[self.df_agent_models_llm['agent_name'] == agent].copy()
            if agent_df.empty: continue
            
            # Prepare data
            agent_df['p95_sec'] = (agent_df['p95_ms'] / 1000).round(3)
            
            # Skip if only 1 model? No, still useful to see the value visually? 
            # User wants "compare models", so mostly useful if > 1 model, but consistent to show all.
            
            # Filename safe agent name
            safe_name = "".join([c if c.isalnum() else "_" for c in agent]).strip('_')
            filename = f"llm_lat_{safe_name}.png"
            
            path = self.chart_gen.generate_bar_chart(
                agent_df, 
                x_col='model_name', 
                y_col='p95_sec', 
                title=f"{agent} - LLM P95 Latency", 
                filename=filename,
                color='#1f77b4', # Muted Blue
                figsize=self.chart_gen.SIZE_SMALL # Smaller charts since we have many
            )
            
            if path:
                self.add_image(f"{agent} Latency", path)

    def _render_performance_section(self, title: str, df: pd.DataFrame, time_col: str, name_col: str, kpi_target_key: str, kpi_error_key: str, include_tokens: bool = False, include_usage_chart: bool = True):
        self.add_subsection(title)
        if df.empty:
            self.report_content.append(f"No {title.lower()} data available.\n")
            return

        target_latency = self.config.get(kpi_target_key, 2.0)
        target_error = self.config.get(kpi_error_key, 5.0)

        # 1. Performance Table
        table_df = self._build_standard_table(
            df, 
            target_latency_sec=target_latency, 
            target_error_pct=target_error,
            name_col=name_col,
            include_tokens=include_tokens
        )
        self.report_content.append(table_df.to_markdown(index=False))
        self.report_content.append("\n<br>\n")
        
        # 2. Charts
        chart_prefix = title.lower().replace(" ", "_").replace("level", "").strip()
        
        if include_usage_chart and 'total_count' in df.columns:
            # Usage Distribution (Donut Chart)
            usage_path = self.chart_gen.generate_pie_chart(
                df.set_index(name_col)['total_count'],
                f"{title}",
                f"{chart_prefix}_usage.png"
            )
            if usage_path: self.add_image(f"{title} Usage", usage_path)

        # Latency Status
        self._add_status_pie_chart(
            table_df, 
            metric_col=f"P{self.percentile} (s)", 
            target=target_latency, 
            title=f"{title} Latency (Target: {target_latency}s)",
            filename=f"{chart_prefix}_lat_status.png",
            size_col="Requests"
        )
        
        # Error Status
        if 'Err %' in table_df.columns:
            self._add_status_pie_chart(
                table_df, 
                metric_col="Err %", 
                target=target_error, 
                title=f"{title} Error (Target: {target_error}%)",
                filename=f"{chart_prefix}_err_status.png",
                size_col="Requests"
            )
        
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
        self.report_content.append("This section provides a high-level scorecard for End to End, Sub Agent, Tool, and LLM levels, assessing compliance against defined Service Level Objectives (SLOs).\n")
        self.report_content.append("\n---\n")

        # End to End (Roots)
        self.add_subsection("End to End")
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

            # E2E Sequence Chart
            try:
                df_invocations = self.data.get('df_raw_invocations', pd.DataFrame())
                if not df_invocations.empty and 'agent_name' in df_invocations.columns:
                    self.report_content.append("### Root Agent E2E Execution Sequence\n")
                    self.report_content.append("The following charts display the end-to-end execution latency for each top-level Root Agent over the course of the test run, plotted in the order the requests were received. This helps identify degradation in overall system performance over time.\n\n")
                    
                    for root_agent in df_invocations['agent_name'].unique():
                        root_df = df_invocations[df_invocations['agent_name'] == root_agent]
                        if root_df.empty: continue
                        
                        safe_name = str(root_agent).replace(' ', '_').replace('/', '_').lower()
                        chart_filename = f'e2e_sequence_{safe_name}.png'
                        chart_title = f"{root_agent} E2E Execution Latency (Request Order)"
                        
                        self.chart_gen.generate_sequence_plot(
                            root_df, 'latency_seconds', chart_title, chart_filename
                        )
                        self.add_image(chart_title, os.path.join(self.assets_dir, chart_filename))
                        
            except Exception as e:
                logger.error(f"Failed to generate E2E sequence plot: {e}")

            # Detailed Latency Histogram (E2E)
            try:
                df_invocations = self.data.get('df_raw_invocations', pd.DataFrame()).copy()
                if not df_invocations.empty and 'duration_ms' in df_invocations.columns:
                    df_invocations['latency_seconds'] = df_invocations['duration_ms'] / 1000.0
                    self.chart_gen.generate_histogram(
                        df_invocations, 'latency_seconds', 
                        'Detailed E2E Latency Histogram', 
                        'latency_histogram.png',
                        figsize=(10, 6)
                    )
                    self.add_image("Detailed E2E Latency Histogram", os.path.join(self.assets_dir, 'latency_histogram.png'))
            except Exception as e:
                logger.error(f"Failed to generate latency histogram: {e}")

        self.report_content.append("\n---\n")

        # --- Agent Level ---
        self._render_performance_section(
            title="Agent Level",
            df=self.df_agents,
            time_col="avg_ms",
            name_col="agent_name",
            kpi_target_key="kpis.agent.latency_target",
            kpi_error_key="kpis.agent.error_target",
            include_usage_chart=True # Default, but explicit
        )
        


        # --- Tool Level ---
        self._render_performance_section(
            title="Tool Level",
            df=self.df_tools,
            time_col="avg_ms",
            name_col="tool_name",
            kpi_target_key="kpis.tool.latency_target",
            kpi_error_key="kpis.tool.error_target",
            include_tokens=False,
            include_usage_chart=True
        )
        self.report_content.append("\n---\n")

        # --- Model Level ---
        self._render_performance_section(
            title="Model Level",
            df=self.df_models,
            time_col="avg_ms",
            name_col="model_name",
            kpi_target_key="kpis.llm.latency_target",
            kpi_error_key="kpis.llm.error_target",
            include_tokens=True,
            include_usage_chart=True
        )
        self.report_content.append("\n---\n")


        self.add_section("Agent Decomposition")
        
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

             # Total LLM Calls per Agent (Stacked)
             if hasattr(self, 'df_raw_llm') and not self.df_raw_llm.empty:
                 try:
                     self.chart_gen.generate_stacked_bar(
                         self.df_raw_llm.copy(), 'agent_name', 'None', 'model_name',
                         'Total LLM Calls per Agent (Stacked by Model)',
                         'agent_calls_stacked.png',
                         figsize=(10, 6)
                     )
                     self.add_image("Total LLM Calls per Agent", os.path.join(self.assets_dir, 'agent_calls_stacked.png'))
                 except Exception as e:
                     logger.error(f"Failed to generate stacked bar: {e}")

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
                 self.report_content.append("\n<br>\n")
             except Exception as e:
                 logger.error(f"Failed to build LLM Generation Performance pivot: {e}")

        self.add_subsection("Agent Overhead Analysis")
        self.report_content.append("This chart visualizes the time spent actively generating LLM responses versus the time spent on agent internal overhead (processing, tool execution, networking).\n")
        
        if hasattr(self, 'df_raw_llm') and not self.df_raw_llm.empty and hasattr(self, 'df_raw_agents') and not self.df_raw_agents.empty:
            try:
                # Calculate mean LLM duration per agent
                llm_agg = self.df_raw_llm.groupby('agent_name')['latency_seconds'].mean().reset_index()
                llm_agg.rename(columns={'latency_seconds': 'pure_llm_sec'}, inplace=True)
                
                # Calculate mean Agent duration per agent
                agent_agg = self.df_raw_agents.groupby('agent_name')['latency_seconds'].mean().reset_index()
                agent_agg.rename(columns={'latency_seconds': 'total_agent_sec'}, inplace=True)
                
                # Merge and calculate overhead
                overhead_df = pd.merge(agent_agg, llm_agg, on='agent_name', how='inner')
                overhead_df['overhead_sec'] = overhead_df['total_agent_sec'] - overhead_df['pure_llm_sec']
                overhead_df['overhead_sec'] = overhead_df['overhead_sec'].clip(lower=0) # Handle async anomalies where LLM > Agent
                
                # Sort by total for display
                overhead_df = overhead_df.sort_values('total_agent_sec', ascending=False).head(10)
                overhead_df['agent_name'] = overhead_df['agent_name'].astype(str)
                
                # Report Agent Overhead as a Markdown Table
                table_df = overhead_df.copy()
                table_df.columns = ['Agent Name', 'Total Agent Latency (s)', 'Pure LLM Latency (s)', 'Agent Overhead (s)']
                for col in ['Total Agent Latency (s)', 'Pure LLM Latency (s)', 'Agent Overhead (s)']:
                    table_df[col] = table_df[col].round(3).astype(str) + "s"
                table_df = table_df.rename(columns=lambda x: f"**{x}**")
                table_df['**Agent Name**'] = "**" + table_df['**Agent Name**'].astype(str) + "**"
                self.report_content.append("#### Overhead Data Summary\n")
                self.report_content.append(table_df.to_markdown(index=False))
                self.report_content.append("\n<br>\n")
                
                path = self.chart_gen.generate_stacked_bar_chart(
                    overhead_df, 
                    x_col='agent_name', 
                    y_cols=['pure_llm_sec', 'overhead_sec'], 
                    title="Agent Overhead vs Pure LLM Latency", 
                    filename="agent_overhead_composition.png",
                    colors=['#66b3ff', '#ff9999'] # Light Blue (LLM), Light Red (Overhead)
                )
                if path:
                    self.add_image("Agent Overhead Comparison", path)
                
            except Exception as e:
                logger.error(f"Failed to generate Agent Overhead chart: {e}")

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
                                if abs_corr >= 0.85:
                                    metrics_data["Correlation Strength"][m] = "🟧 **Strong**"
                                elif abs_corr >= 0.5:
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

        # Agent Level Sequence Charts moved to Agent Decomposition
        try:
            df_agents = self.df_raw_agents
            if not df_agents.empty and 'agent_name' in df_agents.columns and 'model_name' in df_agents.columns:
                
                self.add_subsection("Agent Execution Latency (Request Order)")
                self.report_content.append("The following charts display the end-to-end latency for each specific Agent over time, highlighting performance trends and potential internal degradation.\n\n")
                
                # Per Agent Overall
                for agent in df_agents['agent_name'].unique():
                    agent_df = df_agents[df_agents['agent_name'] == agent]
                    if agent_df.empty: continue
                    safe_name = str(agent).replace(' ', '_').replace('/', '_').lower()
                    chart_filename = f'seq_agent_overall_{safe_name}.png'
                    chart_title = f"{agent} Execution Latency Sequence (Request Order)"
                    self.chart_gen.generate_sequence_plot(
                        agent_df, 'latency_seconds', chart_title, chart_filename
                    )
                    self.add_image(chart_title, os.path.join(self.assets_dir, chart_filename))
                
                self.add_subsection("Agent Execution Latency By Model")
                self.report_content.append("These charts breakdown the Agent execution sequences further by the underlying LLM model used for that request. This helps isolate whether an Agent's latency spike is tied to a specific model's degradation.\n\n")

                # Per Agent Per Model
                for agent in df_agents['agent_name'].unique():
                    agent_df = df_agents[df_agents['agent_name'] == agent]
                    for model in agent_df['model_name'].unique():
                        am_df = agent_df[agent_df['model_name'] == model]
                        if am_df.empty: continue
                        safe_a = str(agent).replace(' ', '_').replace('/', '_').lower()
                        safe_m = str(model).replace(' ', '_').replace('/', '_').replace('.', '_').lower()
                        chart_filename = f'seq_agent_model_{safe_a}_{safe_m}.png'
                        chart_title = f"{agent} via {model} Latency Sequence"
                        self.chart_gen.generate_sequence_plot(
                            am_df, 'latency_seconds', chart_title, chart_filename
                        )
                        self.add_image(chart_title, os.path.join(self.assets_dir, chart_filename))

        except Exception as e:
            logger.error(f"Failed to generate Agent sequence plots: {e}")

        self.report_content.append("\n---\n")

        self.add_section("Model Composition")
        
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
             path = self.chart_gen.generate_pie_chart(usage_series, "", "model_usage_pie.png", colors=None)
             if path: self.add_image("Model Usage", path)

             # Latency Distribution by Category
             if hasattr(self, 'df_raw_llm') and not self.df_raw_llm.empty:
                 try:
                     df_cat = self.df_raw_llm.copy()
                     df_cat['latency_seconds'] = df_cat['duration_ms'] / 1000.0
                     def categorize_latency(latency):
                         if latency < 1.0: return 'Very Fast (< 1s)'
                         elif latency < 2.0: return 'Fast (1-2s)'
                         elif latency < 3.0: return 'Medium (2-3s)'
                         elif latency < 5.0: return 'Slow (3-5s)'
                         elif latency < 8.0: return 'Very Slow (5-8s)'
                         else: return 'Outliers (8s+)'

                     df_cat['latency_category'] = df_cat['latency_seconds'].apply(categorize_latency)
                     category_order = ['Very Fast (< 1s)', 'Fast (1-2s)', 'Medium (2-3s)', 'Slow (3-5s)', 'Very Slow (5-8s)', 'Outliers (8s+)']
                     colors = ['#77DD77', '#A0E57D', '#FDFD96', '#FFB347', '#FF6961', '#E5aeae']

                     self.chart_gen.generate_category_bar(
                         df_cat, 'latency_category',
                         'Latency Distribution by Category',
                         'latency_category_dist.png',
                         order=category_order,
                         colors=colors,
                         figsize=(10, 6)
                     )
                     self.add_image("Latency Distribution by Category", os.path.join(self.assets_dir, 'latency_category_dist.png'))
                 except Exception as e:
                     logger.error(f"Failed to generate latency category distribution: {e}")

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

        # Model Level Sequence Charts
        try:
            df_llm = self.df_raw_llm
            if not df_llm.empty and 'model_name' in df_llm.columns:
                self.report_content.append("\n### Model Latency Sequences\n")
                self.report_content.append("The following charts display the pure LLM execution latency (excluding agent overhead) for each generated response throughout the test run.\n\n")

                for model in df_llm['model_name'].unique():
                    model_df = df_llm[df_llm['model_name'] == model]
                    if model_df.empty: continue
                    safe_name = str(model).replace(' ', '_').replace('/', '_').replace('.', '_').lower()
                    chart_filename = f'seq_model_{safe_name}.png'
                    chart_title = f"{model} LLM Latency Sequence (Request Order)"
                    self.chart_gen.generate_sequence_plot(
                        model_df, 'latency_seconds', chart_title, chart_filename
                    )
                    self.add_image(chart_title, os.path.join(self.assets_dir, chart_filename))
        except Exception as e:
            logger.error(f"Failed to generate Model sequence plots: {e}")

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
                             if model_corr_df['duration_ms'].std() > 0 and model_corr_df['candidates_token_count'].std() > 0:
                                 corr_out = model_corr_df['duration_ms'].corr(model_corr_df['candidates_token_count'])
                             else:
                                 corr_out = float('nan')
                             
                             correlation_map[model] = {'out': corr_out}
                             
                             if has_thoughts:
                                 # Output + Thinking
                                 # FillNA for thoughts just in case
                                 model_corr_df['thoughts_token_count'] = model_corr_df['thoughts_token_count'].fillna(0)
                                 model_corr_df['total_gen'] = model_corr_df['candidates_token_count'] + model_corr_df['thoughts_token_count']
                                 
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
                     if abs_v > 0.85: s_str = "🟧 **Strong**"
                     elif abs_v > 0.5: s_str = "🟨 **Moderate**"
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
            


            # --- Advanced Token Tracking Charts ---
            if hasattr(self, 'df_raw_llm') and not self.df_raw_llm.empty:
                df_llm = self.df_raw_llm.copy()
                df_llm['latency_seconds'] = df_llm['duration_ms'] / 1000.0
                df_llm['input_tokens'] = df_llm['prompt_token_count'].fillna(0) if 'prompt_token_count' in df_llm.columns else 0
                df_llm['output_tokens'] = df_llm['candidates_token_count'].fillna(0) if 'candidates_token_count' in df_llm.columns else 0
                df_llm['thought_tokens'] = df_llm['thoughts_token_count'].fillna(0) if 'thoughts_token_count' in df_llm.columns else 0
                
                # Filter out pure errors with no tokens mapping?
                if 'output_tokens' in df_llm.columns:
                    df_llm = df_llm[df_llm['output_tokens'] > 0]
                
                # 4. Latency vs Output Token Count (Linear)
                try:
                    self.chart_gen.generate_scatter_with_trend(
                        df_llm, 'output_tokens', 'latency_seconds', 'input_tokens',
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
                        df_llm, 'output_tokens', 'latency_seconds', 'input_tokens',
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
                    if df_llm['thought_tokens'].sum() > 0:
                        df_llm['total_generated_tokens'] = df_llm['output_tokens'] + df_llm['thought_tokens']
                        title_suffix = "(Output + Thought)"
                        x_col = 'total_generated_tokens'
                    else:
                        df_llm['total_generated_tokens'] = df_llm['output_tokens']
                        title_suffix = "(Output Only - No Thoughts)"
                        x_col = 'output_tokens'
                        
                    self.chart_gen.generate_scatter_with_trend(
                        df_llm, x_col, 'latency_seconds', 'input_tokens',
                        f'Latency vs Generated Tokens {title_suffix}',
                        'latency_vs_generated_tokens.png',
                        scale='linear'
                    )
                    self.add_image(f"Latency vs Generated Tokens {title_suffix}", os.path.join(self.assets_dir, 'latency_vs_generated_tokens.png'))
                except Exception as e:
                    logger.error(f"Failed to generate token scatter: {e}")
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

        # Status to Emoji
        def status_to_emoji(s):
            if str(s) == "OK": return "🟢"
            if str(s) == "ERROR": return "🔴"
            return str(s)

        # Helper to format timestamp column if present
        def fmt_ts_col(df):
            if 'timestamp' in df.columns:
                df['timestamp'] = df['timestamp'].apply(self._format_date)
            return df

        self.add_subsection("Slowest Invocations")
        if isinstance(self.root_bottlenecks, pd.DataFrame) and not self.root_bottlenecks.empty:
            df_root = fmt_ts_col(self._standardize_formatting(self.root_bottlenecks.copy()))
            if hasattr(self, 'num_slowest_queries') and self.num_slowest_queries:
                df_root = df_root.head(self.num_slowest_queries)
            # Rank | Timestamp | Root Agent | Duration (s) | Error Message | User Message | Trace ID | Span ID
            df_root['Rank'] = range(1, len(df_root) + 1)
            
            if 'duration_ms' in df_root.columns:
                df_root['duration_ms'] = (df_root['duration_ms'] / 1000).round(3)
            else:
                df_root['duration_ms'] = 0.0

            # RCA placeholder if not present
            if 'rca_analysis' not in df_root.columns:
                df_root['RCA'] = "N/A"
            else:
                df_root['RCA'] = df_root['rca_analysis'].fillna("N/A")

            if 'status' in df_root.columns:
                df_root['status'] = df_root['status'].apply(status_to_emoji)
            else:
                df_root['status'] = "N/A"

            # Mapping
            cols_map_root = {
                'Rank': 'Rank',
                'timestamp': 'Timestamp',
                'root_agent_name': 'Root Agent',
                'duration_ms': 'Duration (s)',
                'status': 'Status',
                'content_text_summary': 'User Message',
                'session_id': 'Session ID',
                'trace_id': 'Trace ID',
                'RCA': 'RCA',
            }
            
            final_cols_root = []
            rename_map_root = {}
            for src, dst in cols_map_root.items():
                if src in df_root.columns or src == 'Rank':
                    final_cols_root.append(src)
                    rename_map_root[src] = dst
            
            df_final_root = df_root[final_cols_root].rename(columns=rename_map_root)
            
            # Format Links
            for idx, row in df_final_root.iterrows():
                t_id = row.get('Trace ID')
                p_id = PROJECT_ID
                if t_id and not str(t_id).startswith('['):
                     link = f"https://console.cloud.google.com/traces/explorer;traceId={t_id}?project={p_id}"
                     df_final_root.at[idx, 'Trace ID'] = f"[`{t_id}`]({link})"

            # Bolding for Root Agent
            df_final_root = self._bold_columns_by_pattern(df_final_root, "Root Agent")
            self.report_content.append(self._bold_first_column(df_final_root).to_markdown(index=False))
            self.report_content.append("\n<br>\n")
        else:
            self.report_content.append("No root bottlenecks found.\n")

        self.add_subsection("Slowest Agent queries")
        
        # Helper to format Agent Bottlenecks
        if isinstance(self.agent_bottlenecks, pd.DataFrame) and not self.agent_bottlenecks.empty:
            df_top = fmt_ts_col(self._standardize_formatting(self._truncate_df(self.agent_bottlenecks.copy())))
            if hasattr(self, 'num_slowest_queries') and self.num_slowest_queries:
                df_top = df_top.head(self.num_slowest_queries)

            # Ensure columns exist or create them
            if 'duration_ms' in df_top.columns:
                df_top['duration_s'] = (df_top['duration_ms'] / 1000).round(3)
            else:
                df_top['duration_s'] = 0.0

            # Generate Rank
            df_top['Rank'] = range(1, len(df_top) + 1)
            
            # RCA placeholder if not present
            if 'rca_analysis' not in df_top.columns:
                df_top['RCA'] = "N/A"
            else:
                df_top['RCA'] = df_top['rca_analysis'].fillna("N/A")

            # Root Duration (ms to s)
            if 'root_duration_ms' in df_top.columns:
                 df_top['root_duration_s'] = (df_top['root_duration_ms'] / 1000).round(3)
            else:
                 df_top['root_duration_s'] = 0.0

            df_top['impact'] = df_top.apply(
                lambda row: (f"{(row.get('duration_ms', 0) / row.get('root_duration_ms') * 100):.1f}%"
                             if row.get('root_duration_ms') and row.get('root_duration_ms') > 0 else "N/A"),
                axis=1
            )

            if 'status' in df_top.columns:
                df_top['status'] = df_top['status'].apply(status_to_emoji)
            else:
                df_top['status'] = "N/A"

            if 'root_status' in df_top.columns:
                df_top['root_status'] = df_top['root_status'].apply(status_to_emoji)
            else:
                df_top['root_status'] = "N/A"

            # Select and Order Columns
            cols_map = {
                'Rank': 'Rank',
                'timestamp': 'Timestamp',
                'agent_name': 'Name',
                'duration_s': 'Latency (s)',
                'status': 'Status',
                'content_text_summary': 'User Message',
                'root_agent_name': 'Root Agent',
                'root_duration_s': 'E2E (s)',
                'root_status': 'Root Status',
                'impact': 'Impact (%)',
                'session_id': 'Session ID',
                'trace_id': 'Trace ID',
                'span_id': 'Span ID',
                'RCA': 'RCA',
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
            
            # Use generic bolding for Name columns and Root Agent
            df_final_top = self._bold_columns_by_pattern(df_final_top, "Name")
            df_final_top = self._bold_columns_by_pattern(df_final_top, "Root Agent")
            self.report_content.append(self._bold_first_column(df_final_top).to_markdown(index=False))
            self.report_content.append("\n<br>\n")
        else:
            self.report_content.append("No data available for top bottlenecks.\n")
        
        self.add_subsection("Slowest LLM queries")
        if isinstance(self.llm_bottlenecks, pd.DataFrame) and not self.llm_bottlenecks.empty:
             df_llm = fmt_ts_col(self._standardize_formatting(self.llm_bottlenecks.copy()))
             if hasattr(self, 'num_slowest_queries') and self.num_slowest_queries:
                 df_llm = df_llm.head(self.num_slowest_queries)
             
             # Calculate/Ensure Columns
             df_llm['Rank'] = range(1, len(df_llm) + 1)
             
             if 'duration_s' in df_llm.columns: # Already in seconds from query
                 df_llm['LLM (s)'] = df_llm['duration_s'].round(3)
             elif 'duration_ms' in df_llm.columns:
                 df_llm['LLM (s)'] = (df_llm['duration_ms'] / 1000).round(3)
             else:
                 df_llm['LLM (s)'] = 0.0
                 
             if 'ttft_s' in df_llm.columns: 
                 df_llm['TTFT (s)'] = df_llm['ttft_s'].round(3)
             elif 'ttft_ms' in df_llm.columns:
                 df_llm['TTFT (s)'] = (pd.to_numeric(df_llm['ttft_ms'], errors='coerce') / 1000).round(3)
             else:
                 df_llm['TTFT (s)'] = 0.0
             
             # Duration maps
             if 'agent_duration_ms' in df_llm.columns:
                 df_llm['Agent (s)'] = (pd.to_numeric(df_llm['agent_duration_ms'], errors='coerce') / 1000).round(3)
             if 'root_duration_ms' in df_llm.columns:
                 df_llm['E2E (s)'] = (pd.to_numeric(df_llm['root_duration_ms'], errors='coerce') / 1000).round(3)

             # Impact % = LLM Duration / E2E Duration (Root Duration)
             try:
                 # Ensure numeric
                 dur_llm = pd.to_numeric(df_llm.get('duration_ms', 0), errors='coerce').fillna(0)
                 dur_e2e = pd.to_numeric(df_llm.get('root_duration_ms', 0), errors='coerce').fillna(0)
                 
                 # Avoid division by zero
                 df_llm['Impact %'] = df_llm.apply(
                    lambda row: (f"{(row.get('duration_ms', 0) / row.get('root_duration_ms') * 100):.1f}%" 
                                 if row.get('root_duration_ms') and row.get('root_duration_ms') > 0 else "N/A"), 
                    axis=1
                 )
             except Exception:
                 df_llm['Impact %'] = "N/A"

             df_llm['RCA'] = df_llm.get('rca_analysis', "N/A")
             
             # Ensure columns exist before operations
             for col in ['prompt_token_count', 'candidates_token_count', 'thoughts_token_count']:
                 if col not in df_llm.columns:
                     df_llm[col] = 0

             # Input/Output/Thought from specific keys if available
             # Force integer formatting (no decimals) for tokens
             df_llm['Input'] = pd.to_numeric(df_llm['prompt_token_count'], errors='coerce').fillna(0).astype(int)
             df_llm['Output'] = pd.to_numeric(df_llm['candidates_token_count'], errors='coerce').fillna(0).astype(int)
             df_llm['Thought'] = pd.to_numeric(df_llm['thoughts_token_count'], errors='coerce').fillna(0).astype(int)
             
             # Total Tokens
             df_llm['Total Tokens'] = (
                 df_llm['Input'] + df_llm['Output'] + df_llm['Thought']
             )
             
             # TTFT (s)
             if 'time_to_first_token_ms' in df_llm.columns:
                 df_llm['TTFT (s)'] = (pd.to_numeric(df_llm['time_to_first_token_ms'], errors='coerce') / 1000).fillna(0).round(3)
             else:
                 df_llm['TTFT (s)'] = 0.0

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
                'LLM (s)': 'LLM (s)',
                'TTFT (s)': 'TTFT (s)',
                'model_name': 'Model Name',
                'LLM Status': 'LLM Status',
                'Input': 'Input',
                'Output': 'Output',
                'Thought': 'Thought',
                'Total Tokens': 'Total Tokens',
                'response_text': 'Response Text',
                'agent_name': 'Agent Name',
                'Agent (s)': 'Agent (s)',
                'Agent Status': 'Agent Status impact',
                'root_agent_name': 'Root Agent Name',
                'E2E (s)': 'E2E (s)',
                'Root Status': 'Root Status',
                'Impact %': 'Impact %',
                'content_text_summary': 'User Message',
                'session_id': 'Session ID',
                'trace_id': 'Trace ID',
                'span_id': 'Span ID',
                'RCA': 'RCA'
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
             df_final_llm = self._bold_columns_by_pattern(df_final_llm, "Root Agent")
             self.report_content.append(self._bold_first_column(df_final_llm).to_markdown(index=False))
             self.report_content.append("\n<br>\n")

        # Slowest Tools Queries
        self.add_subsection("Slowest Tools Queries")
        if isinstance(self.tool_bottlenecks, pd.DataFrame) and not self.tool_bottlenecks.empty:
             df_tool = fmt_ts_col(self._standardize_formatting(self.tool_bottlenecks.copy()))
             if hasattr(self, 'num_slowest_queries') and self.num_slowest_queries:
                 df_tool = df_tool.head(self.num_slowest_queries)
             # Rank | Timestamp | Tool (s) | Tool Name | Tool Status | Tool Args | Impact % | Agent | Agent (s) | Agent Status | Root Agent | E2E (s) | Root Status | User Message | Session ID | Trace ID | Span ID
             df_tool['Rank'] = range(1, len(df_tool) + 1)
             
             if 'duration_ms' in df_tool.columns:
                 df_tool['Tool (s)'] = (df_tool['duration_ms'] / 1000).round(3)
             else:
                 df_tool['Tool (s)'] = 0.0
             
             # Convert Agent Duration and E2E Duration to seconds
             if 'agent_duration_ms' in df_tool.columns:
                 df_tool['agent_duration_s'] = (pd.to_numeric(df_tool['agent_duration_ms'], errors='coerce') / 1000).round(3)
             else:
                 df_tool['agent_duration'] = 0.0
             
             if 'root_duration_ms' in df_tool.columns:
                 df_tool['root_duration_s'] = (pd.to_numeric(df_tool['root_duration_ms'], errors='coerce') / 1000).round(3)

             # Impact % calculation
             # Impact % calculation
             def calc_impact1(row):
                 try:
                     dur_s = float(row.get('duration_ms', 0)) / 1000
                     agent_s = float(row.get('agent_duration_ms', 0)) / 1000
                     
                     if agent_s > 0:
                         return round((dur_s / agent_s) * 100, 2)
                     return 0.00
                 except:
                     return 0.00

             def calc_impact2(row):
                 try:
                     dur_s = float(row.get('duration_ms', 0)) / 1000
                     root_agent_s = float(row.get('root_duration_ms', 0)) / 1000

                     if root_agent_s > 0:
                         return round((dur_s / root_agent_s) * 100, 2)
                     return 0.00
                 except:
                     return 0.00

             df_tool['impact_agent'] = df_tool.apply(calc_impact1, axis=1)
             df_tool['impact_root'] = df_tool.apply(calc_impact2, axis=1)

             # Format generic code columns
             if 'tool_args' in df_tool.columns:
                 df_tool['tool_args'] = df_tool['tool_args'].apply(self._format_as_code)
             if 'tool_result' in df_tool.columns:
                 df_tool['tool_result'] = df_tool['tool_result'].apply(self._format_as_code)

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
                 'tool_args': 'Arguments',
                 'tool_result': 'Result',
                 'agent_name': 'Agent Name',
                 'agent_duration_s': 'Agent (s)',
                 'Agent Status': 'Agent Status',
                 'impact_agent': 'Impact %',
                 'root_agent_name': 'Root Agent',
                 'root_duration_s': 'E2E (s)',
                 'Root Status': 'Root Status',
                 'impact_root': 'Impact %',
                 'content_text_summary': 'User Message',
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

        # --- Error Analysis ---
        self.add_section("Error Analysis")
        
        # Helper for Error Tables
        def format_error_table(df, cols_mapping):
            if df.empty: return None
            df_err = self._standardize_formatting(df.copy())
            df_err['Rank'] = range(1, len(df_err) + 1)
            
            # Formats
            # Timestamp handled by _standardize_formatting
            
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
            df_final = self._bold_columns_by_pattern(df_final, "Root Agent")
            return self._bold_first_column(df_final).to_markdown(index=False)

        # 1. Root Agent Errors
        self.add_subsection("Root Errors")
        # Rank | Timestamp | Root Agent | Error Message | User Message | Trace ID | Invocation ID
        root_map = {
            'Rank': 'Rank',
            'timestamp': 'Timestamp',
            'root_agent_name': 'Root Agent',
            'error_message': 'Error Message',
            'content_text_summary': 'User Message',
            'trace_id': 'Trace ID',
            'invocation_id': 'Invocation ID'
        }
        if not self.root_errors.empty:
            tbl = format_error_table(self._truncate_df(self.root_errors.head(self.num_error_queries)), root_map)
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
            'content_text_summary': 'User Message',
            'trace_id': 'Trace ID',
            'span_id': 'Span ID'
        }
        if not self.agent_errors.empty:
            if 'root_status' in self.agent_errors.columns:
                self.agent_errors['root_status'] = self.agent_errors['root_status'].apply(self._status_emoji)

            tbl = format_error_table(self._truncate_df(self.agent_errors.head(self.num_error_queries)), agent_map)
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
            'agent_name': 'Agent Name',
            'agent_status': 'Agent Status',
            'root_agent_name': 'Root Agent',
            'root_status': 'Root Status',
            'content_text_summary': 'User Message',
            'trace_id': 'Trace ID',
            'span_id': 'Span ID' 
        }
        if not self.tool_errors.empty:
             # Map status emoji
             if 'agent_status' in self.tool_errors.columns:
                 self.tool_errors['agent_status'] = self.tool_errors['agent_status'].apply(self._status_emoji)
             if 'root_status' in self.tool_errors.columns:
                 self.tool_errors['root_status'] = self.tool_errors['root_status'].apply(self._status_emoji)
                 
             if 'tool_args' in self.tool_errors.columns:
                 self.tool_errors['tool_args'] = self.tool_errors['tool_args'].apply(self._format_as_code)

             tbl = format_error_table(self._truncate_df(self.tool_errors.head(self.num_error_queries)), tool_map)
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
            'duration_s': 'Latency (s)', 
            'agent_name': 'Parent Agent',
            'agent_status': 'Agent Status',
            'root_agent_name': 'Root Agent',
            'root_status': 'Root Status',
            'content_text_summary': 'User Message',
            'trace_id': 'Trace ID',
            'span_id': 'Span ID' 
        }
        if not self.llm_errors.empty:
             if 'agent_status' in self.llm_errors.columns:
                 self.llm_errors['agent_status'] = self.llm_errors['agent_status'].apply(self._status_emoji)
             if 'root_status' in self.llm_errors.columns:
                 self.llm_errors['root_status'] = self.llm_errors['root_status'].apply(self._status_emoji)

             # Robustly format llm_config
             if 'llm_config' in self.llm_errors.columns:
                 self.llm_errors['llm_config'] = self.llm_errors['llm_config'].apply(self._format_as_code)

             # Convert duration_ms to duration_s
             if 'duration_ms' in self.llm_errors.columns:
                 self.llm_errors['duration_s'] = (self.llm_errors['duration_ms'] / 1000).round(2)
             else:
                 self.llm_errors['duration_s'] = 0.0

             tbl = format_error_table(self._truncate_df(self.llm_errors.head(self.num_error_queries)), llm_map)
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
                    rec_df = self._standardize_formatting(self._truncate_df(rec_df))
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
                        'content_text_summary': 'User Message',
                        'prompt_tokens': 'Prompt Tokens',
                        'prompt_token_count': 'Prompt Tokens', # Fallback
                        'Latency (s)': 'Latency (s)',
                        'trace_id': 'Trace ID',
                        'span_id': 'Span ID' 
                    }

                    # Format Timestamp handled by _standardize_formatting
                    
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

            # 1. Detailed Latency Histogram moved to E2E
            # 2. Total LLM Calls per Agent moved to Agent Decomposition
            # 3. Latency Distribution by Category moved to Model Composition


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
        md.append(f"- **Avg Input Tokens**: {averages.get('prompt_token_count', 0):.1f}")
        md.append(f"- **Avg Output Tokens**: {averages.get('candidates_token_count', 0):.1f}")
        
        # Samples
        md.append("\n### Sample Outliers\n")
        md.append("| Agent | Model | Duration (s) | Input Tokens | Status | Trace ID |")
        md.append("|:------|:------|-------------:|-------------:|:-------|:---------|")
        
        for s in samples[:5]:
             trace_link = f"[{s.get('trace_id')[:8]}](https://console.cloud.google.com/traces/explorer;traceId={s.get('trace_id')}?project={PROJECT_ID})"
             md.append(f"| {s.get('agent_name')} | {s.get('model_name')} | {s.get('duration_ms', 0)/1000:.2f} | {s.get('input_token_count')} | {s.get('status')} | {trace_link} |")
             
        md.append("\n\n---\n")
        return "\n".join(md)

def load_config() -> Dict[str, Any]:
    try:
        config_path = os.path.join(os.path.dirname(__file__), "../agents/observability_agent/config.json")
        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                data = json.load(f)
                return data.get("config", {})
        return {}
    except Exception as e:
        logger.warning(f"Failed to load config.json: {e}")
        return {}

async def generate_report_content(save_file: bool = True) -> str:
    # Ensure views exist before querying
    try:
        ensure_all_views()
    except Exception as e:
        logger.warning(f"Failed to ensure views: {e}")

    config = load_config()
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    data_manager = ReportDataManager(config)
    data = await data_manager.fetch_all_data()
    
    generator = ReportGenerator(data, config, base_dir=base_dir)
    # await generator.fetch_data() # Removed as data is passed in
    generator.build_report()
    
    if save_file:
        return generator.save()
    return "\n".join(generator.report_content)

async def main():
    await generate_report_content()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
