"""Generate a self-signed TLS certificate for local HTTPS (port 8445)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

CERTS_DIR = Path(__file__).resolve().parents[1] / "certs"
KEY_PATH = CERTS_DIR / "key.pem"
CERT_PATH = CERTS_DIR / "cert.pem"


def generate_certs() -> None:
    CERTS_DIR.mkdir(parents=True, exist_ok=True)
    if KEY_PATH.exists() and CERT_PATH.exists():
        print(f"Certificates already exist in {CERTS_DIR}")
        return

    cmd = [
        "openssl",
        "req",
        "-x509",
        "-newkey",
        "rsa:2048",
        "-nodes",
        "-keyout",
        str(KEY_PATH),
        "-out",
        str(CERT_PATH),
        "-days",
        "365",
        "-subj",
        "/CN=localhost",
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise SystemExit("openssl is required to generate TLS certificates.") from exc
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f"openssl failed: {exc.stderr}") from exc

    print(f"Wrote {KEY_PATH} and {CERT_PATH}")


if __name__ == "__main__":
    generate_certs()
    sys.exit(0)
