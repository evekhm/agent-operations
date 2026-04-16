# PTO Agent

This agent calculates PTO balances, sick leave balances, working days for specific date ranges, and remaining work days in a month/quarter/year. It supports vacation planning by telling users how many PTO days a planned trip would cost.

## Capabilities

- **PTO & Sick Leave Balances** (`calculate_pto_details`): Reports current PTO balance, sick leave balance, accrued/used days, and remaining holidays based on company policy (20 PTO + 10 sick days/year, accrued monthly).
- **Vacation Planning** (`calculate_working_days_for_period`): Given a start and end date, calculates working days, weekends, and holidays in the range, plus how many PTO days the vacation would consume.
- **Remaining Working Days** (`get_remaining_working_days`): Calculates remaining working days until end of the current month, quarter, or year.

## Deployment

To deploy this agent to Google Cloud Run, follow these steps:

1. Ensure you have established your environment variables in a `.env` file at the root of the project.

    ```shell
    cp .env.sample .env
    ```

2. Run the deployment script from this directory:
    ```bash
    ./deploy.sh
    ```
    This script will set up necessary IAM permissions and use `adk deploy cloud_run` to deploy the agent.

## Programmatic URL Retrieval

You can programmatically retrieve the URL of the deployed Cloud Run service using the following `gcloud` command:

```bash
PTO_AGENT_URL=$(gcloud run services describe ptoagent --platform managed --region us-central1 --format 'value(status.url)')
```
*(Replace `us-central1` with the appropriate region if different).*

## Testing

We provide several scripts to test the agent both locally and after deployment. All test files are located in the `tests/` directory.

### Local Testing

To test the agent's logic and tool execution locally without deploying:

```bash
python3 tests/test_local_agent.py
```

### Remote Testing

Since the agent is deployed with authentication required (`--no-allow-unauthenticated`), you must use an identity token to access it.

#### Using Python Script
To test the deployed agent via Python (using `RemoteA2aAgent`), which verifies full A2A communication and tool execution:

```bash
python3 tests/test_remote_agent.py
```

*Expect a response with PTO balance, sick leave balance, and remaining work days information.*

#### Using Bash Script
You can also use the bash script to automate the `curl` steps described below:

```bash
./tests/test_remote_card.sh
```

### 1. Generate an Identity Token

```bash
ID_TOKEN=$(gcloud auth print-identity-token --quiet)
```

### 2. Verify Reachability (GET)

To verify that the agent is reachable and see its capabilities:

```bash
curl -i -H "Authorization: Bearer $ID_TOKEN" $PTO_AGENT_URL/a2a/pto_agent/.well-known/agent-card.json
```
*(Replace the URL with your actual service URL if different).*

### 3. Verify JSON-RPC Health (POST)

To test if the endpoint handles JSON-RPC traffic:

```bash
curl -i -X POST -H "Authorization: Bearer $ID_TOKEN" -H "Content-Type: application/json" -d '{"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {}}' $PTO_AGENT_URL/a2a/pto_agent
```
*(Expect a `200 OK` with a "Method not found" error, indicating the server is alive and communicating).*

### Generating `agent_card.json` Locally

To generate or update the `agent_card.json` file locally, follow these steps:

1. **Enable A2A mode**: Open `pto_agent/agent.py` and uncomment the line:
   ```python
   app = to_a2a(root_agent)
   ```
2. **Run Uvicorn**: From the `agents` directory, run:
   ```shell
   uvicorn pto_agent.agent:app --host localhost --port 8000
   ```
3. **Fetch the Card**: In another terminal, fetch the generated card and save it:
   ```shell
   curl -s http://localhost:8000/.well-known/agent-card.json -o pto_agent/agent_card.json
   ```
   *(Note: Locally the card is served at the root `/.well-known/agent-card.json` rather than the prefixed path used in deployment).*
4. **Restore File**: Stop the `uvicorn` server and comment the line back out in `agent.py` to restore standard ADK app functionality.