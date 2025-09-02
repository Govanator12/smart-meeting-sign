# config.py - Configuration for Meeting Light

# Import secrets from separate file
try:
    from config_secrets import *
except ImportError:
    print("ERROR: config_secrets.py not found!")
    print("Please copy config_secrets_template.py to config_secrets.py and add your credentials")
    raise

# Calendar Settings
CALENDAR_ID = "primary"  # or "your.email@gmail.com"

# Hardware Settings
RELAY_PIN = 15  # GP15
LED_PIN = "LED"  # Built-in LED

# Timing Settings (in seconds)
CALENDAR_REFRESH_INTERVAL = 900  # 15 minutes
STATUS_CHECK_INTERVAL = 10  # 10 seconds
MEETING_BUFFER_MINUTES = 2  # Turn on 2 min early, off 2 min late

# Calendar Filters
IGNORE_DECLINED = True
IGNORE_ALL_DAY = True
IGNORE_OOO = True  # Ignore Out of Office
PERSONAL_WORK_COLOR_ID = "6"  # Tangerine color
FOCUS_TIME_COLOR_ID = "5"  # Banana color

# OAuth2 URLs (don't change these)
DEVICE_CODE_URL = "https://oauth2.googleapis.com/device/code"
TOKEN_URL = "https://oauth2.googleapis.com/token"
CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.readonly"

# Token storage
TOKEN_FILE = "oauth_token.json"