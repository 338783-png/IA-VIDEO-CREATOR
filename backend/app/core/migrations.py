"""Mises à jour légères du schéma SQLite (ajout de colonnes) sans perte de données.

create_all() crée les tables manquantes mais n'ajoute pas de colonnes aux tables existantes :
chaque entrée ci-dessous est appliquée si la colonne est absente.
"""
import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

log = logging.getLogger("migrations")

COLUMNS = [
    ("projects", "project_type", "VARCHAR(4) NOT NULL DEFAULT '2d'"),
]


def apply(engine: Engine) -> list[str]:
    done = []
    insp = inspect(engine)
    with engine.begin() as conn:
        for table, column, ddl in COLUMNS:
            if table in insp.get_table_names() and column not in {c["name"] for c in insp.get_columns(table)}:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
                done.append(f"{table}.{column}")
                log.info("Migration : colonne %s.%s ajoutée", table, column)
    return done
