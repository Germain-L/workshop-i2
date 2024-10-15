import asyncio
import json
import logging
from mistralai import Mistral
from .config import MISTRAL_API_KEY, model
from .database import update_user_score, mark_message_as_moderated, is_message_moderated

logger = logging.getLogger(__name__)

mistral_client = Mistral(api_key=MISTRAL_API_KEY)

active_conversations = {}

async def reset_conversation_timer(conversation_id, bot):
    if active_conversations[conversation_id]["timer"]:
        active_conversations[conversation_id]["timer"].cancel()

    active_conversations[conversation_id]["timer"] = asyncio.create_task(close_conversation(conversation_id, bot))

async def close_conversation(conversation_id, bot):
    await asyncio.sleep(180)
    await moderate_conversation(bot.get_channel(conversation_id), bot)

async def moderate_conversation(ctx, bot):
    conversation_id = ctx.channel.id

    if conversation_id in active_conversations:
        messages = active_conversations[conversation_id]["messages"]
        user_messages = active_conversations[conversation_id]["user_messages"]
        logger.info(f"Moderation requested for conversation {conversation_id}: {messages}")

        if not messages:
            await ctx.send("No new messages to moderate.")
            return

        moderation_response = await moderate_messages(" ".join(messages), user_messages)

        if moderation_response:
            harmfulness_level = moderation_response.get("harmfulness_level", "none")
            reasons = moderation_response.get("reasons", [])
            action_required = moderation_response.get("action_required", "")
            user_scores = moderation_response.get("user_scores", {})

            async for message in ctx.channel.history(limit=len(messages)):
                if not await is_message_moderated(message.id, conversation_id):
                    author_id = message.author.id
                    author_name = message.author.name
                    score_change = user_scores.get(author_name, 0)
                    await update_user_score(author_id, author_name, score_change)
                    await mark_message_as_moderated(message.id, conversation_id)

            log_moderation(conversation_id, reasons, action_required, user_scores)
            
            await ctx.send(f"Moderation completed for {len(messages)} new messages. Harmfulness level: {harmfulness_level}. Reasons: {', '.join(reasons)}")
            
            active_conversations[conversation_id]["messages"] = []
            active_conversations[conversation_id]["user_messages"] = []
        else:
            await ctx.send("No harmful content detected in the new messages.")
    else:
        await ctx.send("No ongoing conversation to moderate.")
        logger.info(f"No active conversation found for moderation in channel {conversation_id}.")

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