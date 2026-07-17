"""One-off helper: grant all seeded permissions to the default support user.

Run this once after deploying the permission system if the support user
already existed before the migration.
"""
from dotenv import load_dotenv

load_dotenv()

from config_store import set_store
from config_store.bq_store import BigQueryConfigStore
from config_store.bootstrap import ensure_schema, seed_defaults


def main():
    store = BigQueryConfigStore()
    ensure_schema(store)
    seed_defaults(store)
    set_store(store)

    store.seed_permission_defaults()

    user = store.get_user_by_email("soporte@gmail.com")
    if not user:
        print("Usuario soporte@gmail.com no encontrado")
        return 1

    permissions = store.list_permissions()
    assigned = 0
    for perm in permissions:
        try:
            store.assign_user_permission(user["id"], perm["id"])
            assigned += 1
        except Exception as e:
            print(f"No se pudo asignar {perm['id']}: {e}")

    print(f"Se asignaron {assigned} permisos a soporte@gmail.com")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
