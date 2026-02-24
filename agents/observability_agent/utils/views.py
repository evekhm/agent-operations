import os
import logging
from google.cloud import bigquery
from ..config import PROJECT_ID, DATASET_ID, LLM_EVENTS_VIEW_ID, TOOL_EVENTS_VIEW_ID, TABLE_ID, \
    AGENT_EVENTS_VIEW_ID, INVOCATION_EVENTS_VIEW_ID
from .bq import check_table_exists

logger = logging.getLogger(__name__)

def _ensure_view_exists(view_id, sql_file_name):
    """Generic function to create or update a BigQuery view from a SQL file."""
    client = bigquery.Client(project=PROJECT_ID)
    view_ref = f"{PROJECT_ID}.{DATASET_ID}.{view_id}"
    
    logger.info(f"Ensuring view {view_ref} exists and is up to date...")
        
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    sql_path = os.path.join(base_dir, 'sql', sql_file_name)
    
    if not os.path.exists(sql_path):
         logger.error(f"SQL definition not found at {sql_path}")
         return

    with open(sql_path, 'r') as f:
        sql_template = f.read()

    primary_table = TABLE_ID
    
    table_ref = f"{PROJECT_ID}.{DATASET_ID}.{primary_table}"
    if not check_table_exists(client, table_ref):
        logger.warning(f"Source table {table_ref} not found. Skipping {view_id} view creation.")
        return

    view_query = sql_template.format(
        project_id=PROJECT_ID,
        dataset_id=DATASET_ID,
        view_id=view_id,
        table_id=primary_table
    )

    logger.info(f"Creating view {view_ref}...")
    try:
        job = client.query(view_query)
        job.result()
        logger.info(f"{view_id} view created successfully.")
    except Exception as e:
        logger.error(f"Failed to create {view_id} view: {e}")

def ensure_llm_events_view_exists():
    _ensure_view_exists(LLM_EVENTS_VIEW_ID, 'create_llm_events_view.sql')

def ensure_tool_events_view_exists():
    _ensure_view_exists(TOOL_EVENTS_VIEW_ID, 'create_tool_events_view.sql')

def ensure_agent_events_view_exists():
    _ensure_view_exists(AGENT_EVENTS_VIEW_ID, 'create_agent_events_view.sql')

def ensure_invocation_events_view_exists():
    _ensure_view_exists(INVOCATION_EVENTS_VIEW_ID, 'create_invocation_events_view.sql')
