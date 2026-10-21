from sqlalchemy import create_engine, URL
from sqlalchemy.orm import Session

with open("secrets/db_token", "r") as db_token_file:
    db_token = db_token_file.read()

engine_url = URL.create(
    "mysql+pymysql",
    host="GeraldPython.mysql.pythonanywhere-services.com",
    port=3306,
    username="GeraldPython",
    password=db_token,
    database="Phoinix",
)
engine = create_engine(engine_url)


def get_session():
    with Session(engine) as session:
        yield session
