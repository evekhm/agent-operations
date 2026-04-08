import asyncio
import json
import os
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
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

env_path = os.path.join(os.path.dirname(__file__), "../../../.env")
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

async def generate_questions(client: Client, topic: str, count: int) -> list[str]:
    """Uses Gemini to generate realistic test questions."""
    logger.info(f"Generating {count} questions about topic: '{topic}'...")
    
    prompt = f"Generate {count} diverse and realistic questions that a user might ask an AI assistant about the topic: '{topic}'. The questions should be answerable by the agent based on its capabilities: it can calculate remaining PTO and work days, and it can track hiring contexts and candidates. Do not generate questions it cannot answer using these capabilities."
    
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
            f"How do I use {topic}?",
            f"What is the best way to handle {topic}?"
        ][:count]

async def main():
    # Read configuration from environment variables
    topics_config_str = os.getenv("TOPICS_CONFIG")
    concurrency = int(os.getenv("CONCURRENCY", "1"))
    duration_minutes = float(os.getenv("DURATION_MINUTES", "1.0"))
    
    logger.info(f"--- Load Test Configuration ---")
    logger.info(f"TOPICS_CONFIG: {topics_config_str}")
    logger.info(f"CONCURRENCY: {concurrency}")
    logger.info(f"DURATION_MINUTES: {duration_minutes}")
    logger.info(f"--------------------------------")

    topics_config = {}
    try:
        logger.info("Attempting to parse TOPICS_CONFIG as JSON...")
        topics_config = json.loads(topics_config_str)
    except json.JSONDecodeError:
        logger.info("Failed to parse as JSON, attempting to parse as string format 'topic:count'...")
        try:
            for item in topics_config_str.split(","):
                if ":" in item:
                    topic, count = item.split(":")
                    topics_config[topic.strip()] = int(count.strip())
        except Exception as e:
            logger.info(f"Failed to parse TOPICS_CONFIG as string format: {e}")
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
        logger.info("ERROR: Reasoning Engine 'knowledge-supervisor' not found!")
        return
    engine = engines[0]
    logger.info(f"Using Reasoning Engine: {engine.resource_name}")

    sem = asyncio.Semaphore(concurrency)
    start_time = time.time()
    max_duration_seconds = duration_minutes * 60
    query_count = 0

    async def run_single_query(q):
        nonlocal query_count
        async with sem:
            current_query_num = query_count + 1
            query_count += 1
            logger.info(f"\n=== Starting Query {current_query_num}: {q} ===")
            
            try:
                logger.info(f"[{current_query_num}] Sending request...")
                # engine.query is synchronous, so run it in a thread
                response = await asyncio.to_thread(engine.query, input={"message": q})
                logger.info(f"[{current_query_num}] Received response.")
                
                # Extract answer, assume response might be a dict or string
                if isinstance(response, dict):
                    final_answer = response.get("output", str(response))
                else:
                    final_answer = str(response)
            except Exception as e:
                logger.info(f"Error running query '{q}': {e}")
                final_answer = f"Error: {e}"
            
            logger.info(f"\n=== Finished Query {current_query_num} ===")
            logger.info(f"Question: {q}")
            logger.info(f"Answer: {final_answer}")
            logger.info("=" * 50)

    logger.info(f"Starting continuous load test for {duration_minutes} minutes...")
    
    while time.time() - start_time < max_duration_seconds:
        logger.info(f"\n--- Starting new batch of {len(all_questions)} queries ---")
        tasks = [run_single_query(q) for q in all_questions]
        await asyncio.gather(*tasks)
        
        # Check if time is up before starting next batch
        if time.time() - start_time >= max_duration_seconds:
            break
            
        logger.info("\nBatch completed. Repeating...")
        
    logger.info(f"\nLoad test completed. Total queries executed: {query_count}")

if __name__ == "__main__":
    asyncio.run(main())
