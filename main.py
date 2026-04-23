from nomad_api import serve_in_thread
from telegram_bot import NomadBot


def main():
    import sys

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
