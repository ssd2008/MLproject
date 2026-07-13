import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text


load_dotenv()

user = os.getenv("POSTGRES_USER")
password = os.getenv("POSTGRES_PASSWORD")
host = os.getenv("POSTGRES_HOST")
port = os.getenv("POSTGRES_PORT")
db = os.getenv("POSTGRES_DB")

database_url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"

engine = create_engine(database_url)

with engine.connect() as conn:
    result = conn.execute(text("SELECT version();"))
    print(result.scalar())