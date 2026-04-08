import asyncio
import sys
import os
import httpx
import subprocess
import json
import urllib.parse

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google.adk.agents.remote_a2a_agent import RemoteA2aAgent, AGENT_CARD_WELL_KNOWN_PATH
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

class CardInterceptAsyncClient(httpx.AsyncClient):
    def __init__(self, target_url: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.target_url = target_url

    async def request(self, method, url, *args, **kwargs):
        resp = await super().request(method, url, *args, **kwargs)
        if str(url).endswith(".well-known/agent-card.json") and resp.status_code == 200:
            try:
                data = resp.json()
                parsed = urllib.parse.urlparse(self.target_url)
                data['url'] = f"{parsed.scheme}://{parsed.netloc}/a2a/pto_agent"
                resp._content = json.dumps(data).encode('utf-8')
                print(f"Successfully rewrote agent card URL to: {data['url']}")
            except Exception as e:
                print(f"Failed to rewrite card: {e}")
        return resp

    async def __aexit__(self, exc_type, exc_value, traceback):
        try:
            await super().__aexit__(exc_type, exc_value, traceback)
        except RuntimeError as e:
            if "Event loop is closed" in str(e):
                pass
            else:
                raise

async def test_remote():
    print("Testing pto_agent deployed to Cloud Run...")
    
    # Get the Cloud Run URL
    service_name = "ptoagent"
    region = "us-central1"
    project_id = "agent-operations-ek-05"
    
    url_cmd = f"gcloud run services describe {service_name} --platform managed --region {region} --format 'value(status.url)' --project {project_id}"
    try:
        url = subprocess.check_output(url_cmd, shell=True).decode("utf-8").strip()
    except Exception as e:
        print(f"Failed to get Cloud Run URL: {e}")
        return
        
    print(f"Cloud Run URL: {url}")
    
    # Get Identity Token for authentication
    try:
        token = subprocess.check_output(["gcloud", "auth", "print-identity-token"]).decode("utf-8").strip()
    except Exception as e:
        print(f"Failed to get ID token: {e}")
        return
        
    # Create custom client with auth header and interception, and longer timeout (60s)
    async with CardInterceptAsyncClient(target_url=url, headers={"Authorization": f"Bearer {token}"}, timeout=60.0) as client:
        
        # The agent card is served at /a2a/pto_agent/.well-known/agent-card.json when deployed with --a2a
        agent_card_url = f"{url}/a2a/pto_agent{AGENT_CARD_WELL_KNOWN_PATH}"
        print(f"Using Agent Card URL: {agent_card_url}")
        
        agent = RemoteA2aAgent(
            name="pto_agent",
            description="PTO Agent",
            agent_card=agent_card_url,
            httpx_client=client
        )
        
        session_service = InMemorySessionService()
        runner = Runner(
            agent=agent,
            session_service=session_service,
            app_name="test_remote"
        )
        
        session = session_service.create_session_sync(user_id="test_user", app_name="test_remote")
        
        message = types.Content(
            role="user", parts=[types.Part.from_text(text="Hi how many PTO days are left")]
        )
        
        print("Sending query to remote agent...")
        try:
            result = runner.run(new_message=message, user_id="test_user", session_id=session.id)
            print("\n--- Response ---")
            # Handle generator or simple object
            if hasattr(result, '__iter__') or hasattr(result, '__aiter__'):
                for chunk in result:
                    if hasattr(chunk, 'text'):
                        print(chunk.text, end="")
                    else:
                        print(chunk, end="")
            elif hasattr(result, 'text'):
                print(result.text)
            else:
                print(result)
            print()
        except Exception as e:
            print(f"Error during remote call: {e}")

if __name__ == "__main__":
    asyncio.run(test_remote())
