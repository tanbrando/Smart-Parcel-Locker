"""
Dual-listener launcher for the FastAPI app.

Runs the same app on:
  * HTTP  (default :8000) - used by the Edge controller, lifespan ON (DB init + Telegram polling)
  * HTTPS (default :8443) - optional, for phones/laptops opening the web portal over the LAN.
    Browsers only allow camera access (getUserMedia) in a secure context, so Face ID
    enrollment with a live preview needs HTTPS when not on localhost.
    Lifespan is OFF here so Telegram polling / startup tasks never run twice.

Usage:
  python -m server.serve --port 8000 --https-port 8443 \
      --ssl-certfile certs/dev-cert.pem --ssl-keyfile certs/dev-key.pem
"""
import argparse
import asyncio
import contextlib
import signal

import uvicorn


class _ManagedServer(uvicorn.Server):
    """uvicorn.Server whose signal handling is done by this launcher (shared by both listeners)."""

    @contextlib.contextmanager
    def capture_signals(self):  # uvicorn >= 0.29
        yield

    def install_signal_handlers(self) -> None:  # older uvicorn
        pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smart Parcel Locker API (HTTP + optional HTTPS)")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000, help="HTTP port (Edge controller)")
    parser.add_argument("--https-port", type=int, default=8443, help="HTTPS port (web portal camera)")
    parser.add_argument("--ssl-certfile", default=None)
    parser.add_argument("--ssl-keyfile", default=None)
    return parser.parse_args()


async def serve(args: argparse.Namespace) -> None:
    from server.main import app

    servers = [
        _ManagedServer(uvicorn.Config(app, host=args.host, port=args.port, lifespan="on")),
    ]
    if args.ssl_certfile and args.ssl_keyfile:
        servers.append(
            _ManagedServer(
                uvicorn.Config(
                    app,
                    host=args.host,
                    port=args.https_port,
                    ssl_certfile=args.ssl_certfile,
                    ssl_keyfile=args.ssl_keyfile,
                    lifespan="off",
                )
            )
        )

    def request_exit(*_):
        for srv in servers:
            srv.should_exit = True

    signal.signal(signal.SIGINT, request_exit)
    signal.signal(signal.SIGTERM, request_exit)

    # If one listener stops (e.g. port in use), stop the other one too.
    async def run(srv: _ManagedServer) -> None:
        try:
            await srv.serve()
        finally:
            request_exit()

    await asyncio.gather(*(run(srv) for srv in servers))


if __name__ == "__main__":
    asyncio.run(serve(parse_args()))
