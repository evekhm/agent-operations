
"""
BigQuery Connection Utility Module.

This module manages the lifecycle of the BigQuery Cloud Resource connection required for 
AI-powered analysis (e.g., `AI.GENERATE`).

It handles:
- Connection creation (`bqml_connection`).
- IAM role assignment (`roles/aiplatform.user`).
- Project-level permission management.
"""
import logging
from typing import Optional

from google.api_core import exceptions
from google.cloud import bigquery_connection_v1
from google.cloud import resourcemanager_v3
from google.iam.v1 import policy_pb2

from ..config import PROJECT_ID, LOCATION, CONNECTION_ID

logger = logging.getLogger(__name__)

ROLE = "roles/aiplatform.user"

def _get_connection(client: bigquery_connection_v1.ConnectionServiceClient, project_id: str, location: str, connection_id: str) -> Optional[bigquery_connection_v1.Connection]:
    """Get the BigQuery connection if it exists."""
    parent = f"projects/{project_id}/locations/{location}"
    name = f"{parent}/connections/{connection_id}"
    
    try:
        return client.get_connection(name=name)
    except exceptions.NotFound:
        return None
    except Exception as e:
        logger.error(f"Error checking connection {name}: {e}")
        return None

def _create_connection(client: bigquery_connection_v1.ConnectionServiceClient, project_id: str, location: str, connection_id: str) -> bigquery_connection_v1.Connection:
    """Create the BigQuery connection."""
    parent = f"projects/{project_id}/locations/{location}"
    
    connection = bigquery_connection_v1.Connection(
        cloud_resource=bigquery_connection_v1.CloudResource()
    )
    
    try:
        logger.info(f"Creating connection '{connection_id}' in '{parent}'...")
        return client.create_connection(
            parent=parent,
            connection_id=connection_id,
            connection=connection
        )
    except Exception as e:
        logger.error(f"Failed to create connection: {e}")
        raise

def _grant_iam_role(project_id: str, service_account: str, role: str):
    """Grant the necessary IAM role to the connection's service account on the project."""
    
    crm_client = resourcemanager_v3.ProjectsClient()
    project_name = f"projects/{project_id}"
    member = f"serviceAccount:{service_account}"

    try:
        # Get current policy
        policy = crm_client.get_iam_policy(resource=project_name)
        
        # Check if binding already exists
        binding_exists = False
        for binding in policy.bindings:
            if binding.role == role and member in binding.members:
                binding_exists = True
                break
        
        if binding_exists:
            return

        logger.info(f"Granting role '{role}' to service account '{service_account}' on project '{project_id}'...")
        
        # Add new binding
        new_binding = policy_pb2.Binding(role=role, members=[member])
        policy.bindings.append(new_binding)
        
        # Update policy
        crm_client.set_iam_policy(request={"resource": project_name, "policy": policy})
        logger.info(f"Successfully granted role '{role}'.")
        
    except Exception as e:
        logger.error(f"Failed to grant IAM role: {e}")
        logger.warning("Please verify permissions manually.")

def ensure_bq_connection_exists():
    """
    Ensures that the BigQuery Cloud Resource connection exists and has necessary permissions.
    
    This function:
    1. Checks if the `bqml_connection` exists in the US location.
    2. Creates it if it is missing (type: CLOUD_RESOURCE).
    3. Grants the `roles/aiplatform.user` IAM role to the connection's service account 
       on the project level, enabling it to invoke Vertex AI models (AI.GENERATE).
    """
    if not PROJECT_ID:
        logger.warning("PROJECT_ID not set, skipping BQ connection check.")
        return

    try:
        # Initialize client
        client = bigquery_connection_v1.ConnectionServiceClient()
        
        connection = _get_connection(client, PROJECT_ID, LOCATION, CONNECTION_ID)
        
        if not connection:
            connection = _create_connection(client, PROJECT_ID, LOCATION, CONNECTION_ID)
            logger.info(f"Successfully created connection '{CONNECTION_ID}'.")
            
        if connection and connection.cloud_resource and connection.cloud_resource.service_account_id:
            service_account = connection.cloud_resource.service_account_id
            _grant_iam_role(PROJECT_ID, service_account, ROLE)
        else:
            logger.warning(f"Could not retrieve service account ID from connection '{CONNECTION_ID}'.")
            
    except Exception as e:
        logger.error(f"Failed to ensure BigQuery connection: {e}")
