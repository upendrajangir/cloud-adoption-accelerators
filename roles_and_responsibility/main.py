# Import modules
import os
import json
import logging
import requests
import coloredlogs
import logging
from dotenv import load_dotenv
import pandas as pd
from msal import ConfidentialClientApplication

# Load environment variables
load_dotenv()

# Set logging
logger = logging.getLogger(__name__)
coloredlogs.install(
    fmt="%(asctime)s | %(hostname)s | %(levelname)s | %(name)s | %(filename)s:%(lineno)d | %(message)s",
    level="DEBUG",
)


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

if __name__ == "__main":
    tenant_id = (os.getenv("TENANT_ID"),)
    client_id = (os.getenv("CLIENT_ID"),)
    client_secret = (os.getenv("CLIENT_SECRET"),)
