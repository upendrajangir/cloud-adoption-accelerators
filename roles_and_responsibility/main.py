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

if __name__ == "__main":
    tenant_id = (os.getenv("TENANT_ID"),)
    client_id = (os.getenv("CLIENT_ID"),)
    client_secret = (os.getenv("CLIENT_SECRET"),)
