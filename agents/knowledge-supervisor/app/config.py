import os
import google.auth
from dotenv import load_dotenv
import subprocess
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

env_path = os.path.join(os.path.dirname(__file__), "../../../.env")
if os.path.exists(env_path):
    logger.info(f"Loading .env from {env_path}")
    load_dotenv(dotenv_path=env_path, override=True)
else:
    logger.info(f".env not found at {env_path}, relying on environment variables.")

_, project_id = google.auth.default()
os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
os.environ["GOOGLE_CLOUD_LOCATION"] = "global"
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"

SUPERVISOR_MODEL_ID = os.getenv('SUPERVISOR_MODEL_ID', 'gemini-2.5-pro')
SUPERVISOR_DISPLAY_NAME = os.getenv('SUPERVISOR_DISPLAY_NAME', "knowledge_supervisor")

# A2A PTO Agent
PTO_AGENT_URL = os.getenv('PTO_AGENT_URL')
PTO_AGENT_LOCATION = os.getenv('PTO_AGENT_LOCATION', "us-central1")
PTO_SERVICE_NAME = os.getenv('PTO_AGENT_SERVICE_NAME', "ptoagent")

# Big Query
DATASET_ID = os.getenv('TEST_DATASET_ID')
DATASET_LOCATION = os.getenv('TEST_BQ_LOCATION')
TABLE_ID = os.getenv('TEST_TABLE_ID')

logger.info(f"Loaded config: SUPERVISOR_MODEL_ID={SUPERVISOR_MODEL_ID}, SUPERVISOR_DISPLAY_NAME={SUPERVISOR_DISPLAY_NAME}")
logger.info(f"Loaded config: PTO_AGENT_URL={PTO_AGENT_URL}, PTO_AGENT_LOCATION={PTO_AGENT_LOCATION}")
logger.info(f"Loaded config: DATASET_ID={DATASET_ID}, DATASET_LOCATION={DATASET_LOCATION}, TABLE_ID={TABLE_ID}")


def discover_pto_agent_url() -> str:
    """Discovers the pto_agent URL using .env fallback to Cloud Run."""
    global PTO_AGENT_URL
    if PTO_AGENT_URL:
        return PTO_AGENT_URL

    # Fallback to Cloud Run discovery
    region = PTO_AGENT_LOCATION
    if not project_id:
        return "http://localhost:8000" # Fallback to local if no project

    cmd = [
        "gcloud", "run", "services", "describe", PTO_SERVICE_NAME,
        f"--project={project_id}",
        f"--region={region}",
        "--format=value(status.url)"
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        discovered_url = result.stdout.strip()
        if discovered_url:
            PTO_AGENT_URL = discovered_url
            os.environ['PTO_AGENT_URL'] = discovered_url
            return discovered_url
    except Exception:
        pass

    return "http://localhost:8000"
