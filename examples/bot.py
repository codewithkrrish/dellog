"""Minimal bot that loads the dellog cog.

Run it with:
    pip install git+https://github.com/codewithkrrish/dellog.git
    DISCORD_TOKEN=your-token python examples/bot.py

Then in your server, run /dellog setup and point it at a mod channel.
"""

import os

import discord
from discord.ext import commands

intents = discord.Intents.default()
intents.message_content = True  # needed to log message text
intents.messages = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready() -> None:
    print(f"Logged in as {bot.user} — syncing slash commands...")
    await bot.tree.sync()
    print("Ready. /dellog setup is waiting for you.")


async def main() -> None:
    async with bot:
        await bot.load_extension("dellog")
        await bot.start(os.environ["DISCORD_TOKEN"])


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
