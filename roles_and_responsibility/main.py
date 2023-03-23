# Import modules
import os
import json
import logging
import requests
import coloredlogs
import logging
import uuid
from typing import List, Dict
from dotenv import load_dotenv
import pandas as pd
from msal import ConfidentialClientApplication
from azure.identity import ClientSecretCredential
from azure.mgmt.authorization import AuthorizationManagementClient
from azure.mgmt.authorization.models import RoleDefinition

# Load environment variables
load_dotenv()

# Set logging
logger = logging.getLogger(__name__)
coloredlogs.install(
    fmt="%(asctime)s | %(hostname)s | %(levelname)s | %(name)s | %(filename)s:%(lineno)d | %(message)s",
    level="WARNING",
)


def get_auth_client(tenant_id, client_id, client_secret):
    """
    Get auth client
    """
    try:
        return ClientSecretCredential(
            client_id=client_id,
            authority=f"https://login.microsoftonline.com/{tenant_id}",
            client_credential=client_secret,
        )
    except Exception as e:
        logger.error("Error creating ClientSecretCredential: {}".format(e))


def acquire_token_by_service_principal(tenant_id, client_id, client_secret):
    """
    Acquire token by service principal
    """
    try:
        return ConfidentialClientApplication(
            client_id=client_id,
            authority=f"https://login.microsoftonline.com/{tenant_id}",
            client_credential=client_secret,
        )
    except Exception as e:
        logger.error("Error creating ConfidentialClientApplication: {}".format(e))


def get_users_from_ad(tenant_id, client_id, client_secret):
    """
    Get all users from AD
    """
    app = acquire_token_by_service_principal(tenant_id, client_id, client_secret)
    try:
        result = app.acquire_token_for_client(
            scopes=["https://graph.microsoft.com/.default"]
        )
        users = requests.get(  # Use token to call downstream service
            "https://graph.microsoft.com/v1.0/users",
            headers={"Authorization": "Bearer " + result["access_token"]},
        ).json()
        return users
    except Exception as e:
        logger.error("Error getting users from AD: {}".format(e))


def get_users_from_csv(file_path):
    """
    Get users from CSV
    """
    file_path = os.getcwd() + file_path
    raw_users = pd.read_csv(file_path)
    users = {"value": raw_users.to_dict("records")}
    return users


def add_custom_roles(
    role_data: dict[str, str],  # List of string values for creating a custom role.
    subscription_id: str,  # Subscription ID for the Azure subscription.
    tenant_id: str,  # Tenant ID for the Azure account.
    client_id: str,  # Client ID for the Azure account.
    client_secret: str,  # Client secret for the Azure account.
) -> bool:
    """
    Adds custom roles to an Azure subscription.

    This function creates a new custom role with the specified permissions and assigns it to the specified subscription.

    Parameters:
    role_data (Dict[str, str]): A Dict of string keys & values that contain data for creating a custom role.
        The values should be in the following order:
        - id (str): The ID of the custom role in GUID format.
        - role_name (str): The name of the custom role.
        - description (str): A description of the custom role.
        - actions (List[str]): A list of strings representing the actions allowed by the custom role.
    subscription_id (str): The ID of the subscription to which the custom role will be assigned.
    tenant_id (str): The ID of the tenant in which the Azure account is registered.
    client_id (str): The ID of the client to be used to authenticate with Azure.
    client_secret (str): The client secret to be used to authenticate with Azure.

    Returns:
    bool: A boolean value that indicates if the custom role was created successfully. Returns True if successful, False otherwise.
    """
    # Get credentials to authenticate the client.
    credentials = ClientSecretCredential(
        tenant_id=tenant_id,  # Tenant ID for the Azure account.
        client_id=client_id,  # Client ID for the Azure account.
        client_secret=client_secret,  # Client secret for the Azure account.
    )

    # Define the custom role permissions.
    permissions = [
        {
            "actions": role_data["actions"],
            "notActions": [],
            "dataActions": [],
            "notDataActions": [],
            "assignableScopes": [f"/subscriptions/{subscription_id}"],
        }
    ]

    # Generate a GUID for the custom role ID.
    role_definition_id = uuid.uuid4()

    # Define the custom role definition.
    role_definition = RoleDefinition(
        id=role_definition_id,
        role_name=role_data["role_name"],
        description=role_data["description"],
        type="CustomRole",
        assignable_scopes=[f"/subscriptions/{subscription_id}"],
        permissions=permissions,
    )

    try:
        # Authenticate using the specified credentials and create the custom role.
        authorization_client = AuthorizationManagementClient(
            credentials, subscription_id
        )
        result = authorization_client.role_definitions.create_or_update(
            scope=f"/subscriptions/{subscription_id}",
            role_definition_id=role_definition_id,
            role_definition=role_definition,
        )
        return result
    except Exception as e:
        # Log error message if custom role creation fails.
        logger.error("Error adding custom roles: {}".format(e))


def add_ad_groups(
    group_data: Dict[str, str], tenant_id: str, client_id: str, client_secret: str
) -> bool:
    """
    Add Azure AD groups to the system using Microsoft Graph API.

    Parameters:
        group_data (Dict[str, str]): A dictionary containing group data including
            display name and mail nickname.
        tenant_id (str): The tenant ID of the Azure AD instance.
        client_id (str): The client ID of the Azure AD application used to authenticate.
        client_secret (str): The client secret of the Azure AD application used to authenticate.

    Returns:
        bool: True if the group was created successfully, False otherwise.

    Raises:
        requests.exceptions.HTTPError: If an HTTP error is encountered while making
            the API call.

    """
    # Acquire an access token using the MSAL library
    app = ConfidentialClientApplication(
        client_id=client_id,
        client_credential=client_secret,
        authority=f"https://login.microsoftonline.com/{tenant_id}",
    )
    result = app.acquire_token_for_client(
        scopes=["https://graph.microsoft.com/.default"]
    )
    access_token = result["access_token"]

    # Set the API request headers
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    # Define the group display name and mail nickname
    group_display_name = group_data["displayName"]
    group_mail_nickname = group_data["mailNickname"]

    # Create the group
    group_url = "https://graph.microsoft.com/v1.0/groups"
    group_payload = {
        "displayName": group_display_name,
        "mailNickname": group_mail_nickname,
        "groupTypes": [],
        "mailEnabled": False,
        "securityEnabled": True,
        "description": "Azure AD Group",
    }
    try:
        response = requests.post(
            group_url, headers=headers, data=json.dumps(group_payload)
        )
        response.raise_for_status()
        return True
    except requests.exceptions.HTTPError as e:
        # Log the error and return False to indicate that the group was not created
        logger.error(f"Error adding AD group: {e}")
        return False


def add_users_to_group(
    user_id: str,
    group_id: str,
    client_id: str,
    client_secret: str,
    tenant_id: str,
):
    """
    some docstring
    """
    # Acquire an access token using the MSAL library
    app = ConfidentialClientApplication(
        client_id=client_id,
        client_credential=client_secret,
        authority=f"https://login.microsoftonline.com/{tenant_id}",
    )
    result = app.acquire_token_for_client(
        scopes=["https://graph.microsoft.com/.default"]
    )
    access_token = result["access_token"]

    # Set the API request headers
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    # Add user to group
    user_add_url = f"https://graph.microsoft.com/v1.0/groups/{group_id}/members/$ref"
    user_add_payload = {
        "@odata.id": f"https://graph.microsoft.com/v1.0/directoryObjects/{user_id}"
    }
    try:
        response = requests.post(
            user_add_url, headers=headers, data=json.dumps(user_add_payload)
        )
        response.raise_for_status()
        return True
    except requests.exceptions.HTTPError as e:
        # Log the error and return False to indicate that the group was not created
        logger.error(f"Error adding user to AD group: {e}")
        return False

if __name__ == "__main":
    tenant_id = (os.getenv("TENANT_ID"),)
    client_id = (os.getenv("CLIENT_ID"),)
    client_secret = (os.getenv("CLIENT_SECRET"),)
