import asyncio
from src.bot import setup_bot
from src.database import create_pool, create_database
from src.config import DISCORD_TOKEN

async def main():
    bot = await setup_bot()
    await create_pool()
    await create_database()
    await bot.start(DISCORD_TOKEN)

if __name__ == "__main__":
    asyncio.run(main())