import sys
import asyncio
from nomad_api import serve_in_thread
from workflow import NomadAgent
from telegram_bot import NomadBot

async def run_cli():
    agent = NomadAgent()
    print("--- Nomad Active (CLI Mode) ---")
    query = "/best"
    result = agent.run(query)
    print(result)

def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--cli":
        asyncio.run(run_cli())
        return

    serve_in_thread()
    bot = NomadBot()
    bot.run()

if __name__ == "__main__":
    main()
