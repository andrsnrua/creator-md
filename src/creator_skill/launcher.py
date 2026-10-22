from __future__ import annotations

import socket
import threading
import webbrowser
from pathlib import Path

from .web_ui import serve

HOST = "127.0.0.1"
PORT = 8770
URL = f"http://{HOST}:{PORT}/"


def _is_running() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
        connection.settimeout(0.5)
        return connection.connect_ex((HOST, PORT)) == 0


def main() -> None:
    if _is_running():
        webbrowser.open(URL)
        return
    threading.Timer(1.0, lambda: webbrowser.open(URL)).start()
    workspace = Path(__file__).resolve().parents[2] / "workspaces"
    serve(workspace, HOST, PORT)


if __name__ == "__main__":
    main()
