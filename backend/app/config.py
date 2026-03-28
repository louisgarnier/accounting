import os
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL: str = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY: str = os.environ["SUPABASE_SERVICE_KEY"]
FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:3000")
APP_USER_ID: str = os.getenv("APP_USER_ID", "")
ENABLE_BANKING_WEBHOOK_SECRET: str = os.getenv("ENABLE_BANKING_WEBHOOK_SECRET", "")
ENABLE_BANKING_APP_ID: str = os.getenv("ENABLE_BANKING_APP_ID", "")
ENABLE_BANKING_PRIVATE_KEY: str = os.getenv("ENABLE_BANKING_PRIVATE_KEY", "")
