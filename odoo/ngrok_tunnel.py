#!/usr/bin/env python3
"""
Start ngrok tunnels for the Odoo backend (8000) and the Angular frontend (4200),
then print the public URLs and optionally update the backend CORS config.

Requires ngrok to be installed and available in PATH.
Optional: set NGROK_AUTHTOKEN env var if ngrok requires authentication.
"""

import os
import subprocess
import sys
import time
from urllib.parse import urljoin

import requests

# Ensure prints reach the terminal/log file immediately.
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

NGROK_API = "http://127.0.0.1:4040"


def wait_for_ngrok(timeout: float = 15.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(f"{NGROK_API}/api/tunnels", timeout=1)
            if r.status_code == 200:
                return
        except requests.RequestException:
            pass
        time.sleep(0.5)
    print("Timeout waiting for ngrok API to start", file=sys.stderr)
    sys.exit(1)


def fetch_tunnels() -> dict[str, str]:
    r = requests.get(f"{NGROK_API}/api/tunnels")
    r.raise_for_status()
    data = r.json()
    urls: dict[str, str] = {}
    for tunnel in data.get("tunnels", []):
        name = tunnel.get("name", "")
        url = tunnel.get("public_url", "")
        if name and url:
            urls[name] = url
    return urls


def wait_for_all_tunnels(expected: int = 2, timeout: float = 15.0) -> dict[str, str]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        urls = fetch_tunnels()
        if len(urls) >= expected:
            return urls
        time.sleep(0.5)
    return fetch_tunnels()


def main() -> None:
    if subprocess.run(["ngrok", "--version"], capture_output=True).returncode != 0:
        print("ngrok no está instalado o no está en PATH", file=sys.stderr)
        print("Instalalo desde https://ngrok.com/download", file=sys.stderr)
        sys.exit(1)

    auth_token = os.getenv("NGROK_AUTHTOKEN")
    ngrok_args = ["ngrok", "start", "--all", "--config=ngrok.yml"]

    if not os.path.exists("ngrok.yml"):
        print("Creando ngrok.yml con túneles para backend (8000) y frontend (4200)...", flush=True)
        with open("ngrok.yml", "w") as f:
            f.write("""version: "3"
tunnels:
  backend:
    addr: 8000
    proto: http
    host_header: rewrite
  frontend:
    addr: 4200
    proto: http
    host_header: rewrite
""")

    if auth_token:
        # ngrok v3 stores the authtoken under the 'agent:' key in the YAML config
        # or via the CLI command 'ngrok config add-authtoken'. We do both.
        with open("ngrok.yml", "r") as f:
            contents = f.read()
        if f"authtoken: {auth_token}" not in contents:
            subprocess.run(
                ["ngrok", "config", "add-authtoken", auth_token],
                check=False,
                capture_output=True,
            )
            # Also persist it in the local config file under 'agent:' for clarity.
            if "agent:" not in contents:
                contents = contents.replace(
                    'version: "3"',
                    f'version: "3"\nagent:\n  authtoken: {auth_token}',
                )
                with open("ngrok.yml", "w") as f:
                    f.write(contents)

    print("Iniciando ngrok con túneles para backend (8000) y frontend (4200)...", flush=True)
    print("Presioná Ctrl+C para detener.\n", flush=True)

    proc = subprocess.Popen(ngrok_args)

    try:
        wait_for_ngrok()
        urls = wait_for_all_tunnels(expected=2)

        backend_url = urls.get("backend")
        frontend_url = urls.get("frontend")

        if not backend_url or not frontend_url:
            print("No se pudieron obtener las URLs públicas de ngrok.", file=sys.stderr)
            print(f"Túneles encontrados: {urls}", file=sys.stderr)
            sys.exit(1)

        print("=" * 60, flush=True)
        print("Túneles activos:", flush=True)
        print(f"  Backend:   {backend_url}", flush=True)
        print(f"  Frontend:  {frontend_url}", flush=True)
        print("=" * 60, flush=True)
        print(flush=True)
        print("Para que el backend acepte requests del frontend expuesto:", flush=True)
        print(f"  NGROK_FRONTEND_URL={frontend_url} python -m uvicorn main:app --reload", flush=True)
        print(flush=True)
        print("Para exponer el frontend Angular:", flush=True)
        print(f"  cd ../odoo-ui && ng serve --host 0.0.0.0 --port 4200", flush=True)
        print(flush=True)
        print("Si no levantaste los servicios, las URLs no funcionarán.", flush=True)

        proc.wait()
    except KeyboardInterrupt:
        print("\nDeteniendo ngrok...", flush=True)
        proc.terminate()
        proc.wait()


if __name__ == "__main__":
    main()
