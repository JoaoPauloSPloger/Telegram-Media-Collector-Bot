import os
os.environ['BOT_TOKEN'] = "TEST_TOKEN"
os.environ['AES_KEY'] = "INVALID_KEY"
from src.database.db import config
print("Token:", config['bot_token'])
print("Syntax OK")
