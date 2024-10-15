import os
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
MISTRAL_API_KEY = os.environ["MISTRAL_API_KEY"]
DATABASE_URL = os.environ["DATABASE_URL"]
model = os.environ.get("MODEL", "mistral-large-latest")