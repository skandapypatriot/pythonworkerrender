import os
import json

from dotenv import load_dotenv


load_dotenv()


DATABASE_URL = os.environ["FIREBASE_DATABASE_URL"]

SERVICE_ACCOUNT_JSON = json.loads(os.environ["FIREBASE_SERVICE_ACCOUNT_JSON"])

POLL_INTERVAL = int(os.getenv("POLL_INTERVAL_SECONDS", "5"))

DEFAULT_TIMEZONE = os.getenv("DEFAULT_TIMEZONE", "Asia/Kolkata")

LOG_BUFFER_SIZE = int(os.getenv("LOG_BUFFER_SIZE", "500"))
