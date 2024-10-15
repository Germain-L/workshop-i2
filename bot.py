import os
import discord
from discord.ext import commands
from mistralai import Mistral
from dotenv import load_dotenv
import asyncio
import json
import logging
import asyncpg

load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get the tokens from environment variables
DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
MISTRAL_API_KEY = os.environ["MISTRAL_API_KEY"]
DATABASE_URL = os.environ["DATABASE_URL"]
model = os.environ.get("MODEL", "mistral-large-latest")

# Initialize the Mistral client
mistral_client = Mistral(api_key=MISTRAL_API_KEY)

# Create an intents object and specify the intents you need
intents = discord.Intents.all()
intents.messages = True
intents.guilds = True

# Set up the bot with a command prefix and intents
bot = commands.Bot(command_prefix='!', intents=intents)
bot.remove_command('help')  # Remove the default help command

# Dictionary to store active conversations
active_conversations = {}

# Database connection
db = None

async def create_pool():
    global db
    db = await asyncpg.create_pool(DATABASE_URL)

# Database setup
async def create_database():
    async with db.acquire() as conn:
        await conn.execute('''CREATE TABLE IF NOT EXISTS users
                              (id BIGINT PRIMARY KEY, username TEXT, score INTEGER)''')
        await conn.execute('''CREATE TABLE IF NOT EXISTS moderated_messages
                              (message_id BIGINT PRIMARY KEY, channel_id BIGINT)''')

async def get_user_score(user_id):
    async with db.acquire() as conn:
        return await conn.fetchval("SELECT score FROM users WHERE id = $1", user_id) or 0

async def update_user_score(user_id, username, score_change):
    async with db.acquire() as conn:
        await conn.execute("""
            INSERT INTO users (id, username, score) 
            VALUES ($1, $2, $3)
            ON CONFLICT (id) DO UPDATE 
            SET username = EXCLUDED.username, score = users.score + $3
        """, user_id, username, score_change)

async def is_message_moderated(message_id, channel_id):
    async with db.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM moderated_messages WHERE message_id = $1 AND channel_id = $2", message_id, channel_id) is not None

async def mark_message_as_moderated(message_id, channel_id):
    async with db.acquire() as conn:
        await conn.execute("INSERT INTO moderated_messages (message_id, channel_id) VALUES ($1, $2)", message_id, channel_id)

async def get_top_users(limit=10):
    async with db.acquire() as conn:
        return await conn.fetch("SELECT username, score FROM users ORDER BY score DESC LIMIT $1", limit)

async def get_moderation_stats():
    async with db.acquire() as conn:
        total_moderated = await conn.fetchval("SELECT COUNT(*) FROM moderated_messages")
        channels_moderated = await conn.fetchval("SELECT COUNT(DISTINCT channel_id) FROM moderated_messages")
    return total_moderated, channels_moderated

@bot.event
async def on_ready():
    await create_pool()
    await create_database()
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

    if not await is_message_moderated(message.id, conversation_id):
        active_conversations[conversation_id]["messages"].append(message.content)
        active_conversations[conversation_id]["user_messages"].append(f"{message.author.name}: {message.content}")
        logger.info(f"Added message to conversation {conversation_id}: {message.content}")

    await reset_conversation_timer(conversation_id)
    await bot.process_commands(message)

@bot.command()
async def moderate_now(ctx):
    conversation_id = ctx.channel.id

    if conversation_id in active_conversations:
        messages = active_conversations[conversation_id]["messages"]
        user_messages = active_conversations[conversation_id]["user_messages"]
        logger.info(f"Manual moderation requested for conversation {conversation_id}: {messages}")

        if not messages:
            await ctx.send("No new messages to moderate.")
            return

        moderation_response = await moderate_messages(" ".join(messages), user_messages)

        if moderation_response:
            harmfulness_level = moderation_response.get("harmfulness_level", "none")
            reasons = moderation_response.get("reasons", [])
            action_required = moderation_response.get("action_required", "")
            user_scores = moderation_response.get("user_scores", {})

            # Update user scores based on the AI's assessment
            async for message in ctx.channel.history(limit=len(messages)):
                if not await is_message_moderated(message.id, conversation_id):
                    author_id = message.author.id
                    author_name = message.author.name
                    score_change = user_scores.get(author_name, 0)
                    await update_user_score(author_id, author_name, score_change)
                    await mark_message_as_moderated(message.id, conversation_id)

            log_moderation(conversation_id, reasons, action_required, user_scores)
            
            # Respond to the moderator with the moderation results
            await ctx.send(f"Moderation completed for {len(messages)} new messages. Harmfulness level: {harmfulness_level}. Reasons: {', '.join(reasons)}")
            
            # Clear the moderated messages from the active conversation
            active_conversations[conversation_id]["messages"] = []
            active_conversations[conversation_id]["user_messages"] = []
        else:
            await ctx.send("No harmful content detected in the new messages.")
    else:
        await ctx.send("No ongoing conversation to moderate.")
        logger.info(f"No active conversation found for moderation in channel {conversation_id}.")

async def reset_conversation_timer(conversation_id):
    if active_conversations[conversation_id]["timer"]:
        active_conversations[conversation_id]["timer"].cancel()

    active_conversations[conversation_id]["timer"] = asyncio.create_task(close_conversation(conversation_id))

async def close_conversation(conversation_id):
    await asyncio.sleep(180)
    messages = active_conversations[conversation_id]["messages"]
    user_messages = active_conversations[conversation_id]["user_messages"]
    logger.info(f"Closing conversation {conversation_id} and moderating messages: {messages}")

    moderation_response = await moderate_messages(" ".join(messages), user_messages)

    if moderation_response:
        harmfulness_level = moderation_response.get("harmfulness_level", "none")
        reasons = moderation_response.get("reasons", [])
        action_required = moderation_response.get("action_required", "")
        user_scores = moderation_response.get("user_scores", {})

        channel = bot.get_channel(conversation_id)

        # Update user scores based on the AI's assessment
        async for message in channel.history(limit=len(messages)):
            if not await is_message_moderated(message.id, conversation_id):
                author_id = message.author.id
                author_name = message.author.name
                score_change = user_scores.get(author_name, 0)
                await update_user_score(author_id, author_name, score_change)
                await mark_message_as_moderated(message.id, conversation_id)

        log_moderation(conversation_id, reasons, action_required, user_scores)

    del active_conversations[conversation_id]

async def moderate_messages(conversation_text, user_messages):
    messages = [
        {
            "role": "user",
            "content": f"Moderate the following conversation: '{conversation_text}'. Each message is preceded by the user's name. Respond with a JSON object that includes 'harmfulness_level', 'reasons', 'action_required', and 'user_scores'. The 'user_scores' should be an object where keys are usernames and values are integers representing the score change for that user (-2 for highly harmful, -1 for moderately harmful, 0 for neutral, 1 for positive contributions)."
        }
    ]

    try:
        chat_response = mistral_client.chat.complete(
            model=model,
            messages=messages,
            response_format={
                "type": "json_object",
            }
        )

        if chat_response.choices:
            response_json = json.loads(chat_response.choices[0].message.content)
            return response_json
        else:
            return {"harmfulness_level": "none", "reasons": [], "action_required": "", "user_scores": {}}
    except Exception as e:
        logger.error(f"An error occurred while calling Mistral: {e}")
        return {"harmfulness_level": "none", "reasons": [], "action_required": "", "user_scores": {}}

def log_moderation(conversation_id, reasons, action_required, user_scores):
    with open("moderation_log.txt", "a") as log_file:
        log_file.write(f"{conversation_id} - Action Required: {action_required} - Reasons: {', '.join(reasons)} - User Scores: {json.dumps(user_scores)}\n")
    logger.info(f"Moderation logged for conversation {conversation_id}. Reasons: {', '.join(reasons)}, User Scores: {user_scores}")

@bot.command()
async def user_score(ctx, user: discord.User):
    """Check the score of a specific user."""
    score = await get_user_score(user.id)
    await ctx.send(f"{user.name}'s score: {score}")

@bot.command()
async def leaderboard(ctx):
    """Display the top 10 users with the highest scores."""
    top_users = await get_top_users(10)
    leaderboard_message = "🏆 Top 10 Users:\n\n"
    for i, (username, score) in enumerate(top_users, 1):
        leaderboard_message += f"{i}. {username}: {score} points\n"
    await ctx.send(leaderboard_message)

@bot.command()
async def modstats(ctx):
    """Display moderation statistics."""
    total_moderated, channels_moderated = await get_moderation_stats()
    stats_message = f"📊 Moderation Statistics:\n\n"
    stats_message += f"Total messages moderated: {total_moderated}\n"
    stats_message += f"Channels moderated: {channels_moderated}\n"
    await ctx.send(stats_message)

@bot.command()
async def help(ctx):
    """Displays a list of available commands."""
    help_message = (
        "Here are the commands you can use:\n"
        "`!moderate_now`: Manually moderate the ongoing conversation in this channel.\n"
        "`!user_score @user`: Check the score of a specific user.\n"
        "`!leaderboard`: Display the top 10 users with the highest scores.\n"
        "`!modstats`: Display moderation statistics.\n"
        "The score will be adjusted based on message harmfulness.\n"
        "\n"
        "For additional assistance, please reach out to a moderator."
    )
    await ctx.send(help_message)

# Run the bot
bot.run(DISCORD_TOKEN)