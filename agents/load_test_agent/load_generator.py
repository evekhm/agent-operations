import asyncio
import json
import os
import signal
import sys
import time
import google.auth
from google.cloud import aiplatform
import vertexai
from vertexai.preview import reasoning_engines
from google.genai import Client
from google.genai import types
from pydantic import BaseModel
from dotenv import load_dotenv
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("load_generator")

env_path = os.path.join(os.path.dirname(__file__), "../../.env")
if os.path.exists(env_path):
    logger.info(f"Loading .env from {env_path}")
    load_dotenv(dotenv_path=env_path, override=True)
else:
    logger.info(f".env not found at {env_path}, relying on environment variables.")


_, project_id = google.auth.default()
PROJECT_ID =  os.getenv('PROJECT_ID', project_id)
REGION = os.getenv('REGION', 'us-central1')

os.environ["GOOGLE_CLOUD_PROJECT"] = PROJECT_ID
os.environ["GOOGLE_CLOUD_LOCATION"] = REGION
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"

class QuestionList(BaseModel):
    questions: list[str]

TOPIC_CAPABILITIES = {
    "pto": (
        "The agent can calculate: current PTO balance, sick leave balance, "
        "working days for specific date ranges (e.g., July 15 to July 26), "
        "remaining working days in the current month/quarter/year, "
        "how many PTO days a planned vacation would use, and general leave policy information."
    ),
    "company policies": (
        "The agent can answer questions about: PTO policy, sick leave policy, remote work policy, "
        "expense report procedures, onboarding process, performance review process, "
        "hiring process and policy, compliance and ethics guidelines, and employee benefits."
    ),
    "adk": (
        "The agent can answer questions about the Python Agent Development Kit (ADK): "
        "how to create agents, use tools, configure models, deploy agents, "
        "agent orchestration patterns, and ADK best practices."
    ),
    "bigquery": (
        "The agent can query BigQuery datasets, list tables, run SQL queries, "
        "and analyze data stored in BigQuery."
    ),
    "general": (
        "The agent can answer general knowledge questions by searching the web, "
        "including questions about technology, current events, and factual lookups."
    ),
    "database": (
        "The agent can look up items by ID from a simulated database "
        "and perform numerical calculations on data."
    ),
    "google cloud": (
        "The agent can search Google Developer documentation covering "
        "Google Cloud Platform (GCP), Firebase, Android, Google Maps, and other Google APIs. "
        "It can find technical guides, code snippets, API references, and best practices "
        "from the official Google developer documentation."
    ),
}

def _get_capability_description(topic: str) -> str:
    """Match topic to known capability descriptions."""
    topic_lower = topic.lower()
    for key, desc in TOPIC_CAPABILITIES.items():
        if key in topic_lower:
            return desc
    # Check for keyword matches
    keyword_map = {
        "paid time off": "pto", "vacation": "pto", "sick leave": "pto",
        "leave": "pto", "working days": "pto", "time off": "pto",
        "policy": "company policies", "hr": "company policies", "onboarding": "company policies",
        "expense": "company policies", "compliance": "company policies", "benefits": "company policies",
        "hiring process": "company policies", "remote work": "company policies",
        "documentation": "adk", "agent development": "adk", "tools": "adk",
        "tracing": "google cloud", "monitoring": "google cloud", "telemetry": "google cloud",
        "data analysis": "bigquery", "sql": "bigquery", "query": "bigquery",
        "knowledge": "general", "search": "general", "technology": "general",
        "lookup": "database", "calculation": "database", "item": "database",
        "gcp": "google cloud", "firebase": "google cloud", "android": "google cloud",
        "google api": "google cloud", "cloud run": "google cloud", "vertex ai": "google cloud",
        "developer docs": "google cloud", "google developer": "google cloud",
    }
    for keyword, cap_key in keyword_map.items():
        if keyword in topic_lower:
            return TOPIC_CAPABILITIES[cap_key]
    return TOPIC_CAPABILITIES["general"]


async def generate_questions(client: Client, topic: str, count: int) -> list[str]:
    """Uses Gemini to generate realistic test questions."""
    logger.info(f"Generating {count} questions about topic: '{topic}'...")

    capability = _get_capability_description(topic)

    prompt = (
        f"Generate {count} diverse and realistic questions that a user might ask an AI assistant "
        f"about the topic: '{topic}'.\n\n"
        f"The agent has these specific capabilities for this topic:\n{capability}\n\n"
        f"IMPORTANT: Only generate questions that the agent CAN answer using these capabilities. "
        f"Do NOT generate questions about real-time candidate tracking, specific employee records, "
        f"or information that would require access to external systems the agent doesn't have.\n\n"
        f"Generate practical, answerable questions."
    )

    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=QuestionList,
                temperature=0.7,
            ),
        )

        data = json.loads(response.text)
        questions = data.get("questions", [])
        return questions[:count]
    except Exception as e:
        logger.info(f"Error generating questions: {e}")
        return [
            f"Tell me about {topic}",
            f"What information can you provide about {topic}?",
            f"What is the company policy on {topic}?"
        ][:count]

shutdown_requested = False

def handle_sigterm(signum, frame):
    global shutdown_requested
    logger.info("Received SIGTERM — finishing current batch and shutting down gracefully...")
    shutdown_requested = True

signal.signal(signal.SIGTERM, handle_sigterm)
signal.signal(signal.SIGINT, handle_sigterm)

async def main():
    global shutdown_requested
    # Read configuration from environment variables
    topics_config_str = os.getenv("TOPICS_CONFIG")
    if topics_config_str is None:
        logger.info("TOPICS_CONFIG is not set. Using default.")
        topics_config_str = '{"pto": 3, "hiring candidates": 2}'
    concurrency = int(os.getenv("CONCURRENCY", "1"))
    duration_minutes = float(os.getenv("DURATION_MINUTES", "1.0"))
    
    logger.info(f"--- Load Test Configuration ---")
    logger.info(f"TOPICS_CONFIG: {topics_config_str}")
    logger.info(f"CONCURRENCY: {concurrency}")
    logger.info(f"DURATION_MINUTES: {duration_minutes}")
    logger.info(f"--------------------------------")

    topics_config = {}
    logger.info("Parsing TOPICS_CONFIG as string format 'topic:count'...")
    try:
        for item in topics_config_str.split(","):
            if ":" in item:
                topic, count = item.split(":")
                topics_config[topic.strip()] = int(count.strip())
    except Exception as e:
        logger.info(f"Failed to parse TOPICS_CONFIG: {e}")
        logger.info("Using default fallback topic.")
        topics_config = {"general knowledge": 3}

    # Resolve Project ID and Region
    project_id = os.getenv("PROJECT_ID")
    if not project_id:
        import google.auth
        _, project_id = google.auth.default()
    region = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")

    logger.info(f"Initializing Clients (Project: {project_id}, Region: {region})...")
    genai_client = Client(project=project_id, location=region)
    aiplatform.init(project=project_id, location=region)
    vertexai.init(project=project_id, location=region)
    
    all_questions = []
    for topic, count in topics_config.items():
        questions = await generate_questions(genai_client, topic, count)
        all_questions.extend(questions)
        
    logger.info(f"\nTotal Generated Questions: {len(all_questions)}")
    for i, q in enumerate(all_questions):
        logger.info(f"{i+1}. {q}")
    logger.info("-" * 50)
    
    # Find reasoning engine
    logger.info("Searching for Reasoning Engine 'knowledge-supervisor'...")
    engines = reasoning_engines.ReasoningEngine.list(filter='display_name="knowledge-supervisor"')
    if not engines:
        logger.error("ERROR: Reasoning Engine 'knowledge-supervisor' not found!")
        return
    engine_resource = engines[0]
    engine_resource_name = engine_resource.resource_name
    logger.info(f"Using Reasoning Engine: {engine_resource_name}")
    
    from google.cloud import aiplatform_v1
    gapic_client = aiplatform_v1.ReasoningEngineExecutionServiceClient(
        client_options={"api_endpoint": f"{region}-aiplatform.googleapis.com"}
    )

    sem = asyncio.Semaphore(concurrency)
    start_time = time.time()
    max_duration_seconds = duration_minutes * 60
    query_count = 0

    async def run_single_query(q):
        nonlocal query_count
        async with sem:
            current_query_num = query_count + 1
            query_count += 1
            logger.info(f"[Query {current_query_num}] Sending request: {q}")
            
            start_query_time = time.time()
            try:
                from google.protobuf import struct_pb2
                input_struct = struct_pb2.Struct()
                input_struct.update({"query": q})
                
                request = aiplatform_v1.QueryReasoningEngineRequest(
                    name=engine_resource_name,
                    input=input_struct,
                    class_method="query"
                )
                
                response = await asyncio.to_thread(gapic_client.query_reasoning_engine, request=request)
                final_answer = response.output
            except Exception as e:
                logger.info(f"[Query {current_query_num}] Error: {e}")
                final_answer = f"Error: {e}"
            
            latency = time.time() - start_query_time
            logger.info(f"[Query {current_query_num}] Finished in {latency:.2f}s. Answer: {final_answer}")

    logger.info(f"Starting continuous load test for {duration_minutes} minutes...")

    while time.time() - start_time < max_duration_seconds and not shutdown_requested:
        logger.info(f"\n--- Starting new batch of {len(all_questions)} queries ---")
        tasks = [run_single_query(q) for q in all_questions]
        await asyncio.gather(*tasks)

        if shutdown_requested:
            logger.info("Shutdown requested — stopping after current batch.")
            break

        # Check if time is up before starting next batch
        if time.time() - start_time >= max_duration_seconds:
            break

        logger.info("\nBatch completed. Repeating...")

    elapsed = time.time() - start_time
    logger.info(f"\nLoad test completed. Total queries executed: {query_count} in {elapsed/60:.1f} minutes")
    logger.info("Exiting with code 0 (success).")
    sys.exit(0)

if __name__ == "__main__":
    asyncio.run(main())
