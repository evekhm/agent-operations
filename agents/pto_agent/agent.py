# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import datetime
from zoneinfo import ZoneInfo
from google.adk.plugins import LoggingPlugin
from google.adk.plugins.bigquery_agent_analytics_plugin import BigQueryLoggerConfig, BigQueryAgentAnalyticsPlugin

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.adk.tools import LongRunningFunctionTool
from google.genai import types
from google.adk.a2a.utils.agent_to_a2a import to_a2a
import os
import google.auth

from dotenv import load_dotenv

# Load .env from project root
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"))
_, project_id = google.auth.default()
os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
os.environ["GOOGLE_CLOUD_LOCATION"] = "global"
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"
DATASET_ID = os.getenv('DATASET_ID', "agent_ops_demo")
DATASET_LOCATION = os.getenv('DATASET_LOCATION', "us-central1")
TABLE_ID = os.getenv('TABLE_ID', "agent_events")

def calculate_pto_details() -> str:
    """Calculates remaining days in the year, work days, weekends, and US public holidays,
    and calculates remaining PTO days based on a funny logic.

    Returns:
        A string with the calculated details and a humorous summary.
    """
    import datetime
    
    # Current date is fixed to 2026-04-03 as per user environment metadata
    today = datetime.date(2026, 4, 3)
    year = today.year
    end_of_year = datetime.date(year, 12, 31)
    
    total_remaining_days = (end_of_year - today).days + 1
    
    weekends = 0
    current_date = today
    while current_date <= end_of_year:
        if current_date.weekday() in [5, 6]: # 5 is Saturday, 6 is Sunday
            weekends += 1
        current_date += datetime.timedelta(days=1)
        
    # US Public Holidays 2026
    holidays = [
        datetime.date(2026, 5, 25),  # Memorial Day
        datetime.date(2026, 6, 19),  # Juneteenth
        datetime.date(2026, 7, 4),   # Independence Day
        datetime.date(2026, 9, 7),   # Labor Day
        datetime.date(2026, 10, 12), # Columbus Day
        datetime.date(2026, 11, 11), # Veterans Day
        datetime.date(2026, 11, 26), # Thanksgiving
        datetime.date(2026, 12, 25), # Christmas
    ]
    
    remaining_holidays = [h for h in holidays if h >= today]
    num_holidays = len(remaining_holidays)
    
    work_days = total_remaining_days - weekends - num_holidays
    
    pto_base = work_days / 10
    pto_bonus = 5 if work_days > 100 else 0
    remaining_pto = pto_base + pto_bonus
    
    result = (
        f"As of today, {today.strftime('%Y-%m-%d')}:\n"
        f"- Total days remaining in the year: {total_remaining_days}\n"
        f"- Weekends remaining: {weekends}\n"
        f"- Public holidays remaining: {num_holidays}\n"
        f"- Work days remaining: {work_days}\n\n"
        f"Based on our highly scientific and non-negotiable funny logic:\n"
        f"You have approximately {remaining_pto:.1f} PTO days remaining to use or lose!\n"
        f"(Formula: 10% of work days + a bonus of {pto_bonus} days for surviving the grind.)"
    )
    return result



def request_user_input(message: str) -> dict:
    """Request additional input from the user.

    Use this tool when you need more information from the user to complete a task.
    Calling this tool will pause execution until the user responds.

    Args:
        message: The question or clarification request to show the user.
    """
    return {"status": "pending", "message": message}


root_agent = Agent(
    name="pto_agent",
    model=Gemini(
        model="gemini-3-flash-preview",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    description="An agent that calculates remaining time off and work days.",
    instruction="You are a humorous AI assistant designed to calculate remaining days in the year and PTO. Use the calculate_pto_details tool to get the data and report it to the user in a fun way.",
    tools=[
        calculate_pto_details,
        LongRunningFunctionTool(func=request_user_input),
    ],
)

bq_config = BigQueryLoggerConfig(
    enabled=True,
    max_content_length=500 * 1024,
    batch_size=1,
    shutdown_timeout=10.0
)
bq_logging_plugin = BigQueryAgentAnalyticsPlugin(
    project_id=project_id,
    dataset_id=DATASET_ID,
    table_id=TABLE_ID,
    config=bq_config,
    location=DATASET_LOCATION
)
app = App(
    root_agent=root_agent,
    name="app",
    plugins=[bq_logging_plugin, LoggingPlugin()]
)

# # Make agent A2A-compatible
# app = to_a2a(root_agent)