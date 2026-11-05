#!/usr/bin/env python3
"""Forward 0.0.0.0:11435 to the host's Ollama on 127.0.0.1:11434.

Docker Desktop on macOS can reach the host as host.docker.internal, but Ollama often
binds only to 127.0.0.1. Bifrost (inside Docker) therefore cannot reach it directly.
This tiny TCP proxy gives the container a host-reachable port without changing Ollama's
configuration.

    python3 scripts/ollama-proxy.py

`scripts/run-bifrost.sh` starts it automatically when 11435 is not already listening.
"""
from __future__ import annotations

import socketserver
import threading
import socket


class Handler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        upstream = socket.create_connection(("127.0.0.1", 11434))

        def pump(src, dst) -> None:
            try:
                while data := src.recv(65536):
                    dst.sendall(data)
            except OSError:
                pass
            finally:
                try:
                    dst.shutdown(socket.SHUT_WR)
                except OSError:
                    pass

        thread = threading.Thread(target=pump, args=(self.request, upstream), daemon=True)
        thread.start()
        pump(upstream, self.request)
        thread.join(timeout=1)
        upstream.close()


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    print("Ollama proxy: 0.0.0.0:11435 -> 127.0.0.1:11434", flush=True)
    Server(("0.0.0.0", 11435), Handler).serve_forever()
