import asyncpg
from .config import DATABASE_URL, SCORE_ALERT_THRESHOLD
db = None

async def create_pool():
    global db
    db = await asyncpg.create_pool(DATABASE_URL)

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
            RETURNING score
        """, user_id, username, score_change)

        new_score = await conn.fetchval("SELECT score FROM users WHERE id = $1", user_id)

        if new_score <= SCORE_ALERT_THRESHOLD:
            return True
        return False

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