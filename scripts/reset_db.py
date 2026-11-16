"""Resets the database to the demo data: python -m scripts.reset_db"""

from app import db
from app.seed import seed

with db.pool:
    db.init_schema()
    seed()
print("Database reset to demo data.")
