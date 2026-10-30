from sqlalchemy import create_engine, URL
from sqlalchemy.orm import Session

with open("secrets/db_token", "r") as db_token_file:
    db_token = db_token_file.read().strip('\n')

engine_url = URL.create(
    "mysql+pymysql",
    host="GeraldPython.mysql.pythonanywhere-services.com",
    username="GeraldPython",
    password=db_token,
    database="GeraldPython$Phoinix",
)
engine = create_engine(
    engine_url,
    pool_pre_ping=True,
    pool_recycle=120,
)


def get_session():
    return Session(engine)
