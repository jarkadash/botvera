from dotenv import load_dotenv

import os

load_dotenv()

db_host = os.getenv('DB_HOST')
db_port = os.getenv('DB_PORT')
db_name = os.getenv('DB_NAME')
db_user = os.getenv('DB_USER')
db_password = os.getenv('DB_PASS')

connect = f"postgresql+asyncpg://{db_user}:{db_password.strip() }@{db_host}:{db_port}/{db_name}"
