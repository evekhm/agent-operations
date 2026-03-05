import pandas as pd
import json

class ReportDataFormatter:
    """Handles Pandas DataFrame standardization and formatting transformations."""

    def __init__(self, max_column_width: int = 250):
        self.max_column_width = max_column_width

    @staticmethod
    def format_date(val) -> str:
        """Formats timestamp to YYYY-MM-DD HH:MM:SS."""
        if pd.isna(val) or val == "": return "N/A"
        if hasattr(val, 'strftime'): return val.strftime("%Y-%m-%d %H:%M:%S")
        s = str(val)
        if len(s) >= 19 and s[4] == '-' and s[7] == '-' and s[10] in ('T', ' '):
            return s[:19].replace('T', ' ')
        try:
             import pandas as pd
             return pd.to_datetime(val).strftime("%Y-%m-%d %H:%M:%S")
        except: return s

    def standardize_formatting(self, df: pd.DataFrame) -> pd.DataFrame:
        """Standardize timestamps in DataFrame. Modifies in-place and returns."""
        if df.empty: return df
        for col in ['timestamp', 'start_time', 'end_time']:
            if col in df.columns:
                df[col] = df[col].apply(self.format_date)
        return df

    @staticmethod
    def format_as_code(x) -> str:
        """Wraps JSON-like strings or dicts in backticks for markdown."""
        if x is None or pd.isna(x) or x == "": return "N/A"
        if isinstance(x, (list, dict)):
            try: return f"`{json.dumps(x)}`"
            except: return f"`{str(x)}`"
        s = str(x).strip()
        if len(s) > 0 and (s.startswith('{') or s.startswith('[')):
             return f"`{s}`"
        return s

    def truncate_df(self, df: pd.DataFrame) -> pd.DataFrame:
        """Truncates string columns to max_column_width."""
        if df.empty: return df
        df_trunc = df.loc[:, ~df.columns.duplicated()].copy()
        for col in df_trunc.columns:
            if df_trunc[col].dtype == 'object':
                df_trunc[col] = df_trunc[col].astype(str).apply(
                    lambda x: x[:self.max_column_width] + "..." if len(x) > self.max_column_width else x
                )
        return df_trunc

    @staticmethod
    def status_emoji(status: str) -> str:
        return "🟢" if status == "OK" else "🔴"

    @staticmethod
    def pass_fail(value, target, inverse=False) -> str:
        import pandas as pd
        if value is None or pd.isna(value): return "⚪"
        if inverse: return "🟢" if value <= target else "🔴"
        return "🟢" if value >= target else "🔴"

    @staticmethod
    def format_token_metric(row, avg_col, p95_col) -> str:
        import pandas as pd
        avg = row.get(avg_col)
        p95 = row.get(p95_col)
        if pd.isna(avg) or pd.isna(p95): return "-"
        return f"{int(avg)} / {int(p95)}"

    def standardize_table_formatting(self, df: pd.DataFrame) -> pd.DataFrame:
        """Standardizes durations to seconds, applies status emojis, and formats code."""
        import pandas as pd
        if df.empty: return df
        df = df.copy()
        
        ms_cols = ['duration_ms', 'root_duration_ms', 'agent_duration_ms']
        for ms_col in ms_cols:
            s_col = ms_col.replace('_ms', '_s')
            if ms_col in df.columns:
                df[s_col] = (pd.to_numeric(df[ms_col], errors='coerce') / 1000).round(3)
            elif s_col not in df.columns:
                df[s_col] = 0.0
                
        status_cols = ['status', 'agent_status', 'root_status', 'tool_status', 'llm_status']
        for col in status_cols:
            if col in df.columns:
                df[col] = df[col].apply(self.status_emoji)
                
        code_cols = ['llm_config', 'tool_args', 'tool_output']
        for col in code_cols:
            if col in df.columns:
                df[col] = df[col].apply(self.format_as_code)
                
        return df
