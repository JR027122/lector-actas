import os
from sqlalchemy import create_engine
import pandas as pd

DB_FOLDER = os.path.join(os.environ["LOCALAPPDATA"], "ProyectoOCR")

os.makedirs(DB_FOLDER, exist_ok=True)

DB_PATH = os.path.join(DB_FOLDER, "actas.db")

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
    echo=False
)

def save_to_db(data):
    df = pd.DataFrame([data])
    df.to_sql('actas', engine, if_exists='append', index=False)