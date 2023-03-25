# Import modules
import os
import json
import logging
import requests
import coloredlogs
import logging
import uuid
from typing import List, Dict, Optional, Union, Any, Mapping
from dotenv import load_dotenv
from requests.exceptions import RequestException, HTTPError, Timeout, ConnectionError
import pandas as pd
from msal import ConfidentialClientApplication, TokenCache
from azure.identity import ClientSecretCredential
from azure.mgmt.authorization import AuthorizationManagementClient
from azure.mgmt.authorization.models import RoleDefinition
from azure.core.exceptions import (
    AzureError,
    ClientAuthenticationError,
    HttpResponseError,
)

# Load environment variables
load_dotenv()

# Set logging
logger = logging.getLogger(__name__)
coloredlogs.install(
    fmt="%(asctime)s | %(hostname)s | %(levelname)s | %(name)s | %(filename)s:%(lineno)d | %(message)s",
    level="WARNING",
)


def create_azure_ad_client(
    tenant_id: Optional[str] = None,
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None,
) -> Union[ClientSecretCredential, None]:
    """
    Get an authenticated client using the ClientSecretCredential from the Azure Identity library.

    :param tenant_id: The tenant ID for the Azure Active Directory instance.
    :type tenant_id: Optional[str] = None
    :param client_id: The application (client) ID of the app service principal.
    :type client_id: Optional[str] = None
    :param client_secret: The client secret for the app service principal.
    :type client_secret: Optional[str] = None
    :return: An instance of ClientSecretCredential if successful, None otherwise.
    :rtype: Union[ClientSecretCredential, None]
    """

    # Check if the required parameters are provided
    if tenant_id is None:
        raise ValueError("Tenant ID is required to create a ClientSecretCredential.")
    if client_id is None:
        raise ValueError("Client ID is required to create a ClientSecretCredential.")
    if client_secret is None:
        raise ValueError(
            "Client secret is required to create a ClientSecretCredential."
        )

    try:
        # Create a ClientSecretCredential instance with the provided tenant_id, client_id, and client_secret
        credential = ClientSecretCredential(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret,
        )
        return credential
    except ClientAuthenticationError as e:
        # Log the error and return None if there's an issue with client authentication
        logger.error(
            f"Client authentication error when creating ClientSecretCredential: {e}"
        )
        return None
    except HttpResponseError as e:
        # Log the error and return None if there's an issue with the HTTP response from the Azure service
        logger.error(f"HTTP response error when creating ClientSecretCredential: {e}")
        return None
    except AzureError as e:
        # Log the error and return None if there's a general Azure error
        logger.error(f"Error creating ClientSecretCredential: {e}")
        return None
    except Exception as e:
        # Log any other exceptions that were not caught explicitly
        logger.error(f"Unexpected error creating ClientSecretCredential: {e}")
        return None


def acquire_azure_ad_access_token(
    tenant_id: Optional[str] = None,
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None,
) -> Optional[str]:
    """
    Acquire an access token for a given tenant_id, client_id, and client_secret.

    :param tenant_id: The ID of the tenant in Azure AD.
    :param client_id: The ID of the registered application (client) in Azure AD.
    :param client_secret: The secret key for the registered application.
    :return: The access token as a string if successful, None otherwise.
    """

    # Check if the required parameters are provided
    if tenant_id is None:
        raise ValueError("Tenant ID is required to create a ClientSecretCredential.")
    if client_id is None:
        raise ValueError("Client ID is required to create a ClientSecretCredential.")
    if client_secret is None:
        raise ValueError(
            "Client secret is required to create a ClientSecretCredential."
        )

    try:
        app = ConfidentialClientApplication(
            client_id=client_id,
            authority=f"https://login.microsoftonline.com/{tenant_id}",
            client_credential=client_secret,
            token_cache=TokenCache(),
        )
    except ValueError as e:
        logger.error(f"Invalid input for ConfidentialClientApplication: {e}")
        return None
    except RequestException as e:
        logger.error(f"Request error while creating ConfidentialClientApplication: {e}")
        return None
    except Exception as e:
        logger.error(f"Error creating ConfidentialClientApplication: {e}")
        return None

    try:
        # Acquire token for the Microsoft Graph API
        result = app.acquire_token_for_client(
            scopes=["https://graph.microsoft.com/.default"]
        )

        if "access_token" in result:
            return result["access_token"]
        else:
            logger.warning("Access token not found in the result")
            if "error" in result:
                logger.error(
                    f"Error acquiring access token: {result['error']}: {result['error_description']}"
                )
            return None
    except RequestException as e:
        logger.error(f"Request error while acquiring access token: {e}")
        return None
    except Exception as e:
        logger.error(f"Error acquiring access token: {e}")
        return None


def fetch_users_from_azure_ad(
    access_token: Optional[str] = None,
) -> Union[List[Dict[str, str]], None]:
    """
    Retrieves a list of all users from the Azure Active Directory using the provided access token.

    :param access_token: The access token used to authenticate and authorize the request.
    :return: A list of dictionaries representing users, where each dictionary contains key-value pairs
             representing a user's property name and value, respectively. None if an error occurs.

    :raises: RequestException if there was an error sending the request or receiving the response.
    """

    # Check if the required parameters are provided
    if access_token is None:
        raise ValueError("Access token is required to create a group.")

    try:
        response = requests.get(
            "https://graph.microsoft.com/v1.0/users",
            headers={"Authorization": "Bearer " + access_token},
        )

        if response.status_code == 200:
            return response.json()["value"]
        elif response.status_code == 401:
            logger.error("Unauthorized access. Please check your access token.")
        elif response.status_code == 403:
            logger.error(
                "Forbidden access. Insufficient privileges to perform the operation."
            )
        elif response.status_code == 429:
            logger.error("Too many requests. Throttling limit has been reached.")
        else:
            response.raise_for_status()  # Raises an HTTPError if the response status code is not successful
    except RequestException as error:
        logger.error(f"Error fetching users from Azure AD: {error}")
        return None


def read_users_from_csv(file_path: str) -> Dict[str, Any]:
    """
    Reads users' data from a CSV file and returns them as a dictionary.

    Args:
        file_path (str): The relative path to the CSV file containing users' data.

    Returns:
        Dict[str, Any]: A dictionary containing the users' data with the key "value" and a list of dictionaries
        representing the individual users as values.

    Raises:
        FileNotFoundError: If the specified file is not found.
        pd.errors.EmptyDataError: If the specified file is empty.
        pd.errors.ParserError: If there is an error while parsing the file.
    """
    abs_file_path = os.path.join(os.getcwd(), file_path)

    try:
        users_df = pd.read_csv(abs_file_path)
    except FileNotFoundError as error:
        logger.exception(f"File not found: {error}")
        raise
    except pd.errors.EmptyDataError as error:
        logger.exception(f"Empty data in CSV file: {error}")
        raise
    except pd.errors.ParserError as error:
        logger.exception(f"Error parsing CSV file: {error}")
        raise

    users_dict = {"value": users_df.to_dict("records")}
    return users_dict


def fetch_ad_groups(
    access_token: Optional[str] = None,
) -> Union[List[Dict[str, str]], None]:
    """
    Retrieves a dictionary of all groups from the Azure Active Directory using the provided access token.

    :param access_token: The access token used to authenticate and authorize the request.
    :type access_token: str

    :return: A dictionary of groups, where each key-value pair represents a group's property name and value, respectively.
             For example, {"displayName": "My Group", "description": "My group description", ...}
    :rtype: Union[List[Dict[str, str]], None]

    :raises: requests.exceptions.RequestException: If there was an error sending the request or receiving the response.
    """

    # Check if the required parameters are provided
    if access_token is None:
        raise ValueError("Access token is required to create a group.")

    try:
        url = "https://graph.microsoft.com/v1.0/groups"
        headers = {"Authorization": f"Bearer {access_token}"}

        response = requests.get(url, headers=headers)
        response.raise_for_status()  # Raises an HTTPError if the response status code is not successful

        json_response = response.json()

        if "value" in json_response:
            return json_response["value"]
        else:
            logger.error(f"Unexpected response structure: {json_response}")

    except HTTPError as error:
        status_code = error.response.status_code
        if status_code == 401:
            logger.exception(
                f"HTTPError (Unauthorized): Invalid access token provided: {error}"
            )
        elif status_code == 403:
            logger.exception(
                f"HTTPError (Forbidden): Insufficient permissions to access groups: {error}"
            )
        else:
            logger.exception(
                f"HTTPError: An error occurred during the request: {error}"
            )

    except Timeout as error:
        logger.exception(f"Timeout: The request timed out: {error}")

    except ConnectionError as error:
        logger.exception(f"ConnectionError: A network problem occurred: {error}")

    except RequestException as error:
        logger.exception(
            f"RequestException: An error occurred while fetching groups from AD: {error}"
        )

    return None


def create_custom_role(
    access_token: str,
    role_data: Dict[str, Union[str, List[str]]],
    subscription_id: str,
) -> Optional[Dict]:
    """
    Adds a custom role to an Azure subscription using Azure REST APIs.

    :param access_token: The access token used to authenticate and authorize the request.
    :type access_token: str
    :param role_data: A dictionary containing data for creating a custom role.
                      The keys should include:
                      - role_name (str): The name of the custom role.
                      - description (str): A description of the custom role.
                      - actions (List[str]): A list of strings representing the actions allowed by the custom role.
    :type role_data: Dict[str, Union[str, List[str]]]
    :param subscription_id: The ID of the subscription to which the custom role will be assigned.
    :type subscription_id: str

    :return: A dictionary representing the created custom role, or None if the creation fails.
    :rtype: Optional[Dict]
    """
    role_definition_id = str(uuid.uuid4())

    role_definition = {
        "properties": {
            "roleName": role_data["role_name"],
            "description": role_data["description"],
            "type": "CustomRole",
            "permissions": [
                {
                    "actions": role_data["actions"],
                    "notActions": [],
                    "dataActions": [],
                    "notDataActions": [],
                }
            ],
            "assignableScopes": [f"/subscriptions/{subscription_id}"],
        }
    }

    url = f"https://management.azure.com/subscriptions/{subscription_id}/providers/Microsoft.Authorization/roleDefinitions/{role_definition_id}?api-version=2018-07-01"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.put(url, headers=headers, data=json.dumps(role_definition))
        response.raise_for_status()

        return response.json()

    except HTTPError as error:
        status_code = error.response.status_code
        if status_code == 401:
            logger.exception(
                f"HTTPError (Unauthorized): Invalid access token provided: {error}"
            )
        elif status_code == 403:
            logger.exception(
                f"HTTPError (Forbidden): Insufficient permissions to access groups: {error}"
            )
        elif status_code == 429:
            logger.exception("Too many requests. Throttling limit has been reached.")
        else:
            logger.exception(
                f"HTTPError: An error occurred during the request: {error}"
            )

    except Timeout as error:
        logger.exception(f"Timeout: The request timed out: {error}")

    except ConnectionError as error:
        logger.exception(f"ConnectionError: A network problem occurred: {error}")

    except RequestException as error:
        logger.exception(
            f"RequestException: An error occurred while fetching groups from AD: {error}"
        )


def create_azure_ad_group(
    group_data: Mapping[str, str], access_token: Optional[str] = None
) -> bool:
    """
    Creates a new Azure Active Directory group using the Microsoft Graph API.

    :param group_data: A dictionary containing group data including
        display name, mail nickname, and description.
    :type group_data: Dict[str, str]

    :param access_token: The access token for authentication.
    :type access_token: str

    :return: True if the group was created successfully, False otherwise.
    :rtype: bool

    :raises requests.exceptions.HTTPError: If an HTTP error is encountered while making
        the API call.
    """

    # Check if the required parameters are provided
    if access_token is None:
        raise ValueError("Access token is required to create a group.")

    # Set the API request headers
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    # Define the group display name, mail nickname, and description
    group_display_name = group_data["display_name"]
    group_mail_nickname = group_data["mail_nickname"]
    group_description = group_data["description"]

    # Create the group
    group_url = "https://graph.microsoft.com/v1.0/groups"
    group_payload = {
        "displayName": group_display_name,
        "mailNickname": group_mail_nickname,
        "groupTypes": [],
        "mailEnabled": False,
        "securityEnabled": True,
        "description": group_description,
    }

    response = None
    try:
        # Send the API request with POST method
        response = requests.post(group_url, headers=headers, json=group_payload)
        response.raise_for_status()

        # Check the response status code and return False if it's not a success code
        if response.status_code != 201:
            logger.error(f"Error creating Azure AD group: {response.text}")
            return False

        # Return True to indicate the group was created successfully
        return True

    except requests.exceptions.HTTPError as e:
        if response is not None and response.status_code == 401:
            # Unauthorized: access token is invalid or expired
            logger.error("Error creating Azure AD group: unauthorized access token")
        elif response is not None and response.status_code == 403:
            # Forbidden: insufficient permissions to perform the action
            logger.error("Error creating Azure AD group: insufficient permissions")
        elif response is not None and response.status_code == 429:
            # Too many requests: API call rate limit exceeded
            logger.warning("Error creating Azure AD group: rate limit exceeded")
        else:
            # Other HTTP errors
            logger.error(f"Error creating Azure AD group: {e}")
        return False


def add_user_to_azure_ad_group(
    user_id: str,
    group_id: str,
    access_token: Optional[str] = None,
) -> bool:
    """
    Adds a user to an Azure Active Directory group using the Microsoft Graph API.

    :param user_id: The object ID of the user to add to the group.
    :type user_id: str

    :param group_id: The object ID of the group to add the user to.
    :type group_id: str

    :param access_token: The access token for authentication.
    :type access_token: str

    :return: True if the user was added successfully, False otherwise.
    :rtype: bool

    :raises requests.exceptions.HTTPError: If an HTTP error is encountered while making
        the API call.
    """

    # Check if the required parameters are provided
    if access_token is None:
        raise ValueError("Access token is required to add user to group.")

    # Set the API request headers
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    # Define the user add request payload
    user_add_url = f"https://graph.microsoft.com/v1.0/groups/{group_id}/members/$ref"
    user_add_payload = {
        "@odata.id": f"https://graph.microsoft.com/v1.0/directoryObjects/{user_id}"
    }

    response = None
    try:
        # Send the API request with POST method
        response = requests.post(user_add_url, headers=headers, json=user_add_payload)
        response.raise_for_status()

        # Check the response status code and return False if it's not a success code
        if response.status_code != 204:
            logger.error(f"Error adding user to Azure AD group: {response.text}")
            return False

        # Return True to indicate the user was added successfully
        return True

    except requests.exceptions.HTTPError as e:
        if response is not None and response.status_code == 400:
            # Bad request: the user or group ID is invalid
            logger.error(
                "Error adding user to Azure AD group: invalid user or group ID"
            )
        elif response is not None and response.status_code == 401:
            # Unauthorized: access token is invalid or expired
            logger.error(
                "Error adding user to Azure AD group: unauthorized access token"
            )
        elif response is not None and response.status_code == 403:
            # Forbidden: insufficient permissions to perform the action
            logger.error(
                "Error adding user to Azure AD group: insufficient permissions"
            )
        elif response is not None and response.status_code == 404:
            # Not found: the user or group ID does not exist
            logger.error("Error adding user to Azure AD group: user or group not found")
        elif response is not None and response.status_code == 429:
            # Too many requests: API call rate limit exceeded
            logger.warning("Error adding user to Azure AD group: rate limit exceeded")
        else:
            # Other HTTP errors
            logger.error(f"Error adding user to Azure AD group: {e}")
        return False


def assign_role_to_group(
    group_id: str,
    role_definition_id: str,
    subscription_id: str,
    access_token: str,
) -> bool:
    """
    Assigns a role to a group on a subscription in Azure.

    :param group_id: The ID of the group to assign the role to.
    :type group_id: str

    :param role_definition_id: The ID of the role definition to assign (e.g. "b24988ac-6180-42a0-ab88-20f7382dd24c").
    :type role_definition_id: str

    :param subscription_id: The ID of the subscription to assign the role on.
    :type subscription_id: str

    :param access_token: The access token for authentication.
    :type access_token: str

    :return: True if the role was successfully assigned, False otherwise.
    :rtype: bool

    :raises requests.exceptions.HTTPError: If an HTTP error is encountered while making
        the API call.
    """

    # Set the API request headers
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    # Define the role assignment endpoint URL and request body
    role_assign_endpoint = f"https://management.azure.com/subscriptions/{subscription_id}/providers/Microsoft.Authorization/roleAssignments/{group_id}?api-version=2022-04-01"
    role_assign_payload = {
        "properties": {
            "roleDefinitionId": f"/subscriptions/{subscription_id}/providers/Microsoft.Authorization/roleDefinitions/{role_definition_id}",
            "principalId": group_id,
        }
    }

    response = None
    try:
        # Send the API request with PUT method
        response = requests.put(
            role_assign_endpoint, headers=headers, json=role_assign_payload
        )
        response.raise_for_status()

        # Check the response status code and return False if it's not a success code
        if response.status_code not in (200, 201, 202):
            logger.error(f"Error assigning role to group: {response.text}")
            return False

        # Return True to indicate the role was assigned successfully
        return True

    except requests.exceptions.HTTPError as e:
        if response is not None and response.status_code == 400:
            # Bad request: the group, role or subscription ID is invalid
            logger.error(
                "Error assigning role to group: invalid group, role or subscription ID"
            )
        elif response is not None and response.status_code == 401:
            # Unauthorized: access token is invalid or expired
            logger.error("Error assigning role to group: unauthorized access token")
        elif response is not None and response.status_code == 403:
            # Forbidden: insufficient permissions to perform the action
            logger.error("Error assigning role to group: insufficient permissions")
        elif response is not None and response.status_code == 404:
            # Not found: the group, role or subscription ID does not exist
            logger.error(
                "Error assigning role to group: group, role or subscription not found"
            )
        elif response is not None and response.status_code == 409:
            # Conflict: role assignment already exists
            logger.warning(
                "Error assigning role to group: role assignment already exists"
            )
        elif response is not None and response.status_code == 429:
            # Too many requests: API call rate limit exceeded
            logger.warning("Error assigning role to group: rate limit exceeded")
        else:
            # Other HTTP errors
            logger.error(f"Error assigning role to group: {e}")
        return False


def get_user_job_title_from_ad(
    access_token: str,
    user_email: str,
) -> Optional[str]:
    """
    Retrieve a user's job title from Azure Active Directory based on their email address.

    :param access_token: The access token used for authenticating with the Microsoft Graph API.
    :type access_token: str

    :param user_email: The email address of the user whose job title is to be fetched.
    :type user_email: str

    :return: The job title of the user if found, otherwise None.
    :rtype: Optional[str]
    """

    # Set the API request headers
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    # Set the API request parameters
    params = {"$select": "jobTitle", "$filter": f"mail eq '{user_email}'"}

    # Set the API request URL
    graph_url = "https://graph.microsoft.com/v1.0/users"

    response = None
    try:
        # Send a GET request to the Microsoft Graph API to retrieve the user's job title
        response = requests.get(graph_url, headers=headers, params=params)
        response.raise_for_status()

        # Check if a user is found with the provided email address
        users = response.json()["value"]
        if users:
            job_title = users[0]["jobTitle"]
            return job_title
        else:
            logger.error(f"No user found with email {user_email}")
            return None

    except requests.exceptions.HTTPError as e:
        # Handle different response status codes and log appropriate error messages
        if response is not None and response.status_code == 400:
            logger.error("Error fetching user job title: invalid parameters")
        elif response is not None and response.status_code == 401:
            logger.error("Error fetching user job title: unauthorized access token")
        elif response is not None and response.status_code == 403:
            logger.error("Error fetching user job title: insufficient permissions")
        elif response is not None and response.status_code == 404:
            logger.error(f"No user found with email {user_email}")
        elif response is not None and response.status_code == 429:
            logger.warning("Error fetching user job title: rate limit exceeded")
        else:
            logger.error(f"Error fetching user job title: {e}")

        return None

    except requests.exceptions.RequestException as e:
        # Log the error and return None to indicate that the job title could not be fetched
        logger.error(f"Error fetching user job title: {e}")
        return None


if __name__ == "__main__":
    tenant_id = os.getenv("TENANT_ID")
    client_id = os.getenv("CLIENT_ID")
    client_secret = os.getenv("CLIENT_SECRET")

    # Get access token
    access_token = acquire_azure_ad_access_token(
        tenant_id=tenant_id, client_id=client_id, client_secret=client_secret
    )

    # Creating groups list
    file_path = os.getcwd() + "/data/groups.json"
    with open(file_path, "r") as file:
        groups = json.load(file)["value"]

    # Create Azure AD groups
    for group in groups:
        group_data = {
            "displayName": group["displayName"],
            "mailNickname": group["mailNickname"],
            "description": group["description"],
        }
        create_azure_ad_group(access_token=access_token, group_data=group_data)

    # Generate all groups list
    groups = fetch_ad_groups(access_token=access_token)

    # Method A: Assign roles to users by AD job title

    # Get list of users from AD
    users = fetch_users_from_azure_ad(access_token=access_token)

    # Add users to the groups
    if groups and users:
        for group in groups:
            for user in users:
                if user.get("jobTitle") == group.get("displayName"):
                    success = add_user_to_azure_ad_group(
                        access_token=access_token,
                        group_id=group["id"],
                        user_id=user["id"],
                    )
                    if success:
                        logger.info(
                            f"User {user['mail']} added to group {group['displayName']}"
                        )
                    else:
                        logger.error(
                            f"Failed to add user {user['mail']} to group {group['displayName']}"
                        )
