# PTO Agent

This agent calculates remaining days in the year, work days, weekends, and US public holidays, and applies a funny logic for calculating remaining PTO days.

## Deployment

To deploy this agent to Google Cloud Run, follow these steps:

1. Ensure you have established your environment variables in a `.env` file at the root of the project.
2. Run the deployment script from this directory:
    ```bash
    ./deploy_to_cloudrun.sh
    ```
    This script will set up necessary IAM permissions and use `adk deploy cloud_run` to deploy the agent.

## Programmatic URL Retrieval

You can programmatically retrieve the URL of the deployed Cloud Run service using the following `gcloud` command:

```bash
PTO_AGENT_URL=$(gcloud run services describe ptoagent --platform managed --region us-central1 --format 'value(status.url)')
```
*(Replace `us-central1` with the appropriate region if different).*

## Testing Deployment

Since the agent is deployed with authentication required (`--no-allow-unauthenticated`), you must use an identity token to access it.

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
