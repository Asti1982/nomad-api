import os
import sys

from nomad_api import serve, serve_in_thread
from telegram_bot import NomadBot


def _render_foreground_http_api() -> bool:
    """If Render runs `python main.py` with no flags, keep the process alive with the Nomad HTTP server (health checks)."""
    if (os.environ.get("RENDER") or "").strip().lower() != "true":
        return False
    # `python main.py` → argv is only the script path; any extra token is --cli, --mcp, etc.
    return len(sys.argv) == 1


def main() -> None:
    if _render_foreground_http_api():
        serve()
        return

    if len(sys.argv) > 1 and sys.argv[1] == "--cli":
        from nomad_cli import main as cli_main

        cli_main(sys.argv[2:] or ["self"])
        return
    if len(sys.argv) > 1 and sys.argv[1] == "--mcp":
        from nomad_mcp import serve_stdio

        serve_stdio()
        return

    serve_in_thread()
    bot = NomadBot()
    bot.run()


if __name__ == "__main__":
    main()
