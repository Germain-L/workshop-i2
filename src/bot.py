import discord
from discord.ext import commands
import logging
from .moderation import active_conversations, reset_conversation_timer, start_auto_moderation
from .commands import ModCommands

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def setup_bot():
    intents = discord.Intents.all()
    intents.messages = True
    intents.guilds = True

    bot = commands.Bot(command_prefix='!', intents=intents)
    bot.remove_command('help')

    # Add this line to load the commands
    await bot.add_cog(ModCommands(bot))

    @bot.event
    async def on_ready():
        logger.info(f'Logged in as {bot.user}!')
        bot.loop.create_task(start_auto_moderation(bot))

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
        active_conversations[conversation_id]["user_messages"].append({
            "id": message.author.id,
            "name": message.author.name,
            "content": message.content,
            "message_id": message.id  # Store the message ID
        })
        logger.info(f"Added message to conversation {conversation_id}: {message.content}")

        await reset_conversation_timer(conversation_id, bot)
        await bot.process_commands(message)

    return bot