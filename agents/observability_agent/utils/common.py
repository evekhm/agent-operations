import json
import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional, List, Dict, Tuple, Union

import numpy as np
import pandas as pd

from .time import parse_time_range

logger = logging.getLogger(__name__)


def _create_bq_where_clause(filters: List[str], time_range: str, table_alias: str = "T"):
    if not filters: filters = []

    time_range_dict = json.loads(parse_time_range(time_range))
    start_time, end_time = time_range_dict['start_date'], time_range_dict['end_date']

    filters.append(f"{table_alias}.timestamp BETWEEN '{start_time}' AND '{end_time}'")

    where_clause = " AND ".join(filters)
    logger.info(f"[create_bq_where_clause] Generated WHERE clause: {where_clause}")
    return where_clause


def build_standard_where_clause(
    time_range: str,
    filter_config: Optional[Dict[str, Tuple[Union[str, int, float, None], str]]] = None,
    extra_filters: Optional[List[str]] = None,
    table_alias: str = "T"
) -> str:

    """
    Builds a standard WHERE clause using a configuration dictionary for cleaner extensibility.
    
    Args:
        time_range: Time range string.
        filter_config: Dictionary mapping column_name -> (value, operator). e.g. {"agent_name": ("foo", "=")}
        extra_filters: List of raw SQL filter strings.
        table_alias: Table alias to use.
    """
    filters = []
    if extra_filters:
        filters.extend(extra_filters)

    if filter_config:
        for col, (val, op) in filter_config.items():
            if val is not None and val != "": # Handle empty strings as None for cleaner calls
                if isinstance(val, (int, float)):
                    filters.append(f"{table_alias}.{col} {op} {val}")
                else:
                    filters.append(f"{table_alias}.{col} {op} '{val}'")

    return _create_bq_where_clause(filters=filters, time_range=time_range, table_alias=table_alias)



def _sanitize_for_markdown(text: Any) -> str:
    """Sanitize text to be safe for inclusion in Markdown tables."""
    if text is None:
        return ""
    s = str(text)
    # Replace pipes and newlines to prevent table breakage
    s = s.replace("|", "/").replace("\n", " ").replace("\r", "")
    return s.strip()


# Custom JSON encoder to handle Decimal and datetime types
class AnalysisEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, (datetime, pd.Timestamp)):
            return obj.isoformat()
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.bool_):
            return bool(obj)
        if pd.isna(obj):
            return None
        return super(AnalysisEncoder, self).default(obj)
