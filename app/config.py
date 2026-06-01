import os
from pathlib import Path

# Rarity factor formula: 2 - share  (where share = fraction choosing same tendency)
# factor ranges from 1.0 (everyone agrees) to 2.0 (only you chose this tendency)
# Applied as a multiplier to base points (tendency + exactness + goal-rich)
RARITY_MAX_POINTS: float = 2.0

DATA_DIR = Path(os.environ.get("DATA_DIR", "data"))
SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-in-production-please")
PORT = int(os.environ.get("PORT", "8081"))
SESSION_LIFETIME_HOURS = int(os.environ.get("SESSION_LIFETIME_HOURS", "24"))
MAX_UPLOAD_SIZE_MB = int(os.environ.get("MAX_UPLOAD_SIZE_MB", "1"))
MAX_GOALS = int(os.environ.get("MAX_GOALS", "30"))
LOGIN_MAX_ATTEMPTS = int(os.environ.get("LOGIN_MAX_ATTEMPTS", "10"))
LOGIN_LOCKOUT_MINUTES = int(os.environ.get("LOGIN_LOCKOUT_MINUTES", "15"))
PAYMENT_LINK = os.environ.get("PAYMENT_LINK", "https://paypal.me/")

SAV_DOC_ID = "VT-SAV-01"
SAV_DOC_VERSION = "v1.0"
