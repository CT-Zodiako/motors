import xmlrpc.client
import ssl
import certifi
import os
from dotenv import load_dotenv
from functools import lru_cache

load_dotenv()

URL      = os.getenv("ODOO_URL")
DB       = os.getenv("ODOO_DB")
USERNAME = os.getenv("ODOO_USERNAME")
PASSWORD = os.getenv("ODOO_PASSWORD")


def _transport():
    ctx = ssl.create_default_context(cafile=certifi.where())
    return xmlrpc.client.SafeTransport(context=ctx)


@lru_cache(maxsize=1)
def _uid() -> int:
    common = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/common", transport=_transport())
    uid = common.authenticate(DB, USERNAME, PASSWORD, {})
    if not uid:
        raise RuntimeError("Odoo authentication failed — check credentials in .env")
    return uid


def execute(model: str, method: str, args: list, kwargs: dict = None) -> list:
    models = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/object", transport=_transport())
    return models.execute_kw(DB, _uid(), PASSWORD, model, method, args, kwargs or {})
