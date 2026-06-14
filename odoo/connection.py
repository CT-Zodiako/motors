import xmlrpc.client
import ssl
import certifi
from dotenv import load_dotenv
import os

load_dotenv()

# ─── CREDENCIALES ────────────────────────────────────────────────────────────
# Opción A (recomendada): cargá tus datos en el archivo .env
#   ODOO_URL=https://miempresa.odoo.com
#   ODOO_DB=nombre_de_tu_base
#   ODOO_USERNAME=tu_email@ejemplo.com
#   ODOO_PASSWORD=tu_password_o_api_key
#
# Opción B: hardcodeá directo acá solo para pruebas locales (nunca a git)
#   URL      = "https://miempresa.odoo.com"
#   DB       = "mycompany"
#   USERNAME = "admin@miempresa.com"
#   PASSWORD = "tu_password_o_api_key"
# ─────────────────────────────────────────────────────────────────────────────

URL      = os.getenv("ODOO_URL")
DB       = os.getenv("ODOO_DB")
USERNAME = os.getenv("ODOO_USERNAME")
PASSWORD = os.getenv("ODOO_PASSWORD")


def _ssl_context():
    # macOS Python.org build doesn't bundle system certs — use certifi
    ctx = ssl.create_default_context(cafile=certifi.where())
    return xmlrpc.client.SafeTransport(context=ctx)


def get_connection():
    """Returns (uid, models_proxy) ready to call execute_kw."""
    common = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/common", transport=_ssl_context())

    version = common.version()
    print(f"Odoo {version['server_version']} — connected")

    uid = common.authenticate(DB, USERNAME, PASSWORD, {})
    if not uid:
        raise ValueError("Authentication failed — check credentials")

    models = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/object", transport=_ssl_context())
    return uid, models


def check_access(uid, models, model="res.partner"):
    """Quick sanity check: can we read the given model?"""
    result = models.execute_kw(
        DB, uid, PASSWORD,
        model, "check_access_rights",
        ["read"],
        {"raise_exception": False},
    )
    print(f"Read access on {model}: {result}")
    return result


if __name__ == "__main__":
    uid, models = get_connection()
    check_access(uid, models)
