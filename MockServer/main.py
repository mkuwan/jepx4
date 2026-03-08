import asyncio
from core.server import start_server

if __name__ == "__main__":
    try:
        asyncio.run(start_server())
    except KeyboardInterrupt:
        print("\nShutdown complete.")
