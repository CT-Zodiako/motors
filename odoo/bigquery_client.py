import json
import logging
import os
from pathlib import Path

from google.cloud import bigquery
from google.oauth2 import service_account

DEFAULT_CREDENTIALS_PATH = Path(__file__).parent / "bigquery.txt"
logger = logging.getLogger(__name__)


def _credentials_path() -> Path:
    env_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if env_path:
        return Path(env_path)
    logger.warning(
        "GOOGLE_APPLICATION_CREDENTIALS is not set; falling back to %s. "
        "Prefer the environment variable for production environments.",
        DEFAULT_CREDENTIALS_PATH,
    )
    return DEFAULT_CREDENTIALS_PATH


def get_bigquery_client() -> bigquery.Client:
    credentials_path = _credentials_path()
    if not credentials_path.exists():
        raise FileNotFoundError(
            f"BigQuery credentials not found at {credentials_path}. "
            "Set GOOGLE_APPLICATION_CREDENTIALS or place a service-account JSON at odoo/bigquery.txt."
        )
    with open(credentials_path, "r") as f:
        info = json.load(f)
    credentials = service_account.Credentials.from_service_account_info(info)
    return bigquery.Client(credentials=credentials, project=credentials.project_id)
