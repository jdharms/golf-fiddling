"""The app served by uvicorn in a background thread, for tools and tests that drive a real browser."""

import socket
import threading
import time

import uvicorn

START_SECONDS = 15


class LiveServer:
    """The app under uvicorn on a free port of 127.0.0.1. Entering yields its base URL."""

    def __init__(self, app):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind(("127.0.0.1", 0))
        self.server = uvicorn.Server(uvicorn.Config(app, log_level="warning"))
        self.thread = threading.Thread(target=self.server.run, kwargs={"sockets": [self.sock]}, daemon=True)

    def __enter__(self) -> str:
        self.thread.start()
        deadline = time.monotonic() + START_SECONDS
        while not self.server.started:
            if not self.thread.is_alive() or time.monotonic() > deadline:
                raise RuntimeError("the site did not start")
            time.sleep(0.05)
        return f"http://127.0.0.1:{self.sock.getsockname()[1]}"

    def __exit__(self, *exc) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=10)
        self.sock.close()
