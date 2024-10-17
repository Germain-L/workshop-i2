import os
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
MISTRAL_API_KEY = os.environ["MISTRAL_API_KEY"]
DATABASE_URL = os.environ["DATABASE_URL"]
model = os.environ.get("MODEL", "mistral-large-latest")
SCORE_ALERT_THRESHOLD = os.environ.get("SCORE_ALERT_THRESHOLD", -5)

active_conversations = {}
last_alert_time = {}  # New dictionary to track last alert time for each user
ALERT_COOLDOWN = 3600  # Cooldown period in seconds (e.g., 1 hour)