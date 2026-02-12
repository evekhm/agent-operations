import logging
import json
from datetime import datetime, timedelta, timezone
from typing import Optional
from dateutil import parser
from dateutil.relativedelta import relativedelta

logger = logging.getLogger(__name__)

# =========================================
# GLOBAL REFERENCE TIME (FOR CACHING)
# =========================================
_REFERENCE_TIME: Optional[datetime] = None

def set_reference_time(dt: datetime):
    """
    Set a global reference time for the analysis session.
    This ensures that all relative time calculations (e.g. 'last 24h') 
    resolve to the exact same timestamp, maximizing cache hits.
    """
    global _REFERENCE_TIME
    _REFERENCE_TIME = dt
    logger.info(f"[TIME] Global reference time set to: {dt}")

def parse_time_range(time_range: str) -> str:
    """
    Parse time range string into start and end timestamps.
    
    Supports formats:
    - "24h", "7d" (last N hours/days)
    - "24h ago", "7d ago" (relative past)
    - "YYYY-MM-DD" (specific date)
    - "now" (current time)
    - "2 september" (natural language)
    - Ranges: "start to end", "from start to end"
    """

    # Use timezone-aware UTC then strip tzinfo to maintain naive compatibility (matches utcnow behavior)
    # Use global reference time if set (for cache consistency)
    if _REFERENCE_TIME:
        now = _REFERENCE_TIME.replace(tzinfo=timezone.utc).replace(tzinfo=None)
    else:
        now = datetime.now(timezone.utc).replace(tzinfo=None)

    time_range = time_range.strip().lower()
    
    if not time_range or time_range == 'all' or time_range == '':
        start = datetime(2000, 1, 1)
        end = now
        return json.dumps({"start_date": start.strftime('%Y-%m-%d %H:%M:%S'), "end_date": end.strftime('%Y-%m-%d %H:%M:%S')})

    # Strip "from " prefix if present
    if time_range.startswith('from '):
        time_range = time_range[5:].strip()
    
    # Helper to parse single date point
    def parse_point(s: str) -> datetime:
        s = s.strip()
        if s == 'now':
            return now
        
        # Handle relative "ago" formats
        if s.endswith(' ago'):
            s = s[:-4].strip()
        
        # Handle simple relative formats (with or without "ago")
        if s.endswith('h'):
            try:
                return now - timedelta(hours=int(s[:-1]))
            except ValueError:
                pass
        if s.endswith('d'):
            try:
                return now - timedelta(days=int(s[:-1]))
            except ValueError:
                pass
        
        # Handle "last X days/hours/months"
        if s.startswith('last '):
            val = s[5:].strip()
            if val.endswith(' days'):
                try:
                    return now - timedelta(days=int(val[:-5]))
                except ValueError:
                    pass
            if val.endswith(' hours'):
                try:
                    return now - timedelta(hours=int(val[:-6]))
                except ValueError:
                    pass
            if val.endswith(' month'):
                 return now - relativedelta(months=1)
            if val.endswith(' months'):
                try:
                    return now - relativedelta(months=int(val[:-7]))
                except ValueError:
                    pass

        # Use dateutil for everything else (absolute dates, natural language)
        try:
            # default to current year if missing, fuzzy=True allows ignoring noise
            return parser.parse(s, default=now, fuzzy=True)
        except (ValueError, TypeError):
            pass
            
        # Fallback/Error
        raise ValueError(f"Could not parse date format: '{s}'")

    try:
        if ' to ' in time_range:
            parts = time_range.split(' to ')
            start_str, end_str = parts[0], parts[1]
        elif '-' in time_range and len(time_range.split('-')) == 3 and time_range.count('.') == 2: # Heuristic for DD.MM.YYYY-DD.MM.YYYY
             parts = time_range.split('-')
             if len(parts) == 2: # e.g. 10.10.2025-12.12.2025
                 start_str, end_str = parts[0], parts[1]
             else: # Likely not a range of this type
                 start_str, end_str = time_range, None
        else:
            start_str, end_str = time_range, None

        if end_str:
            start = parse_point(start_str)
            end = parse_point(end_str)
            # If end seems to be just a date, extend to end of day
            if end.hour == 0 and end.minute == 0 and end.second == 0 and len(end_str.strip()) <= 10:
                end += timedelta(days=1, microseconds=-1)
        else:
            # Single value: "24h" means last 24 hours (end=now)
            start = parse_point(time_range)
            end = now
            
    except Exception as e:
        logger.warning(f"Error parsing time range '{time_range}': {e}. Defaulting to all.")
        start = datetime(2000, 1, 1)
        end = now
    
    return json.dumps({"start_date": start.strftime('%Y-%m-%d %H:%M:%S'), "end_date": end.strftime('%Y-%m-%d %H:%M:%S')})
