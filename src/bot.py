import discord
from discord.ext import commands
from .config import DISCORD_TOKEN
import logging
from .moderation import active_conversations, reset_conversation_timer

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def setup_bot():
    intents = discord.Intents.all()
    intents.messages = True
    intents.guilds = True

    bot = commands.Bot(command_prefix='!', intents=intents)
    bot.remove_command('help')

    @bot.event
    async def on_ready():
        logger.info(f'Logged in as {bot.user}!')

    @bot.event
    async def on_message(message):
        if message.author == bot.user:
            return

        conversation_id = message.channel.id

        if conversation_id not in active_conversations:
            active_conversations[conversation_id] = {
                "messages": [],
                "user_messages": [],
                "timer": None,
            }
            logger.info(f"Started new conversation for channel {conversation_id}.")

        active_conversations[conversation_id]["messages"].append(message.content)
        active_conversations[conversation_id]["user_messages"].append(f"{message.author.name}: {message.content}")
        logger.info(f"Added message to conversation {conversation_id}: {message.content}")

        await reset_conversation_timer(conversation_id, bot)
        await bot.process_commands(message)

    return bot