import pandas as pd

class ReportMarkdownBuilder:
    """Handles Markdown string construction, tables, headings, and link formatting."""

    def __init__(self, project_id: str):
        self.project_id = project_id
        self.content = []

    def get_content(self) -> str:
        return "\n".join(self.content)

    def add_header(self, title: str):
        self.content.append(f"# {title}\n")

    def add_section(self, title: str, content: str = ""):
        self.content.append(f"\n## {title}\n")
        if content: self.content.append(content + "\n")

    def add_subsection(self, title: str, content: str = ""):
        self.content.append(f"\n### {title}\n")
        if content: self.content.append(content + "\n")

    def add_text(self, text: str):
        self.content.append(text + "\n")
        
    def add_divider(self):
        self.content.append("\n---\n")

    def format_trace_url(self, t_id: str) -> str:
        return f"https://console.cloud.google.com/traces/explorer;traceId={t_id}?project={self.project_id}"

    def format_span_url(self, t_id: str, s_id: str) -> str:
        return f"https://console.cloud.google.com/traces/explorer;traceId={t_id};spanId={s_id}?project={self.project_id}"

    def format_trace_md_link(self, t_id: str, label: str = None) -> str:
        if not t_id or pd.isna(t_id) or str(t_id) == 'N/A' or str(t_id).startswith('['): return str(t_id)
        display = label if label else t_id
        return f"[{display}]({self.format_trace_url(t_id)})"

    def format_span_md_link(self, s_id: str, t_id: str, label: str = None) -> str:
        if not s_id or pd.isna(s_id) or str(s_id) == 'N/A' or str(s_id).startswith('['): return str(s_id)
        if not t_id or pd.isna(t_id) or str(t_id) == 'N/A': return str(s_id)
        display = label if label else s_id
        return f"[{display}]({self.format_span_url(t_id, s_id)})"

    @staticmethod
    def bold_index(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty: return df
        df = df.copy()
        df.index = [f"**{x}**" if pd.notna(x) and str(x).strip() and not str(x).strip().startswith("**") else x for x in df.index]
        return df

    @staticmethod
    def bold_first_column(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty: return df
        df = df.copy()
        first_col = df.columns[0]
        df[first_col] = df[first_col].apply(lambda x: f"**{x}**" if pd.notna(x) and str(x).strip() and not str(x).strip().startswith("**") else x)
        return df

    @staticmethod
    def bold_columns(df: pd.DataFrame, columns: list) -> pd.DataFrame:
        if df.empty: return df
        df = df.copy()
        for col in columns:
            if col in df.columns:
                df[col] = df[col].apply(lambda x: f"**{x}**" if pd.notna(x) and str(x).strip() and not str(x).strip().startswith("**") else x)
        return df

    @staticmethod
    def bold_columns_by_pattern(df: pd.DataFrame, pattern: str = "Name") -> pd.DataFrame:
        if df.empty: return df
        df = df.copy()
        for col in df.columns:
            clean_col = col.replace('*', '').strip()
            if pattern.lower() in clean_col.lower():
                 df[col] = df[col].apply(lambda x: f"**{x}**" if pd.notna(x) and str(x).strip() and not str(x).strip().startswith("**") else x)
        return df

    def bold_standard_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        standard_cols = ['Agent Name', 'Model Name', 'Tool Name', 'Root Agent', 'Name']
        return self.bold_columns(df, standard_cols)
