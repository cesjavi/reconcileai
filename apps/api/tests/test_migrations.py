import os
import subprocess
import sys
import tempfile
from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine

API = Path(__file__).resolve().parents[1]


def test_migrations_match_models():
    """`alembic upgrade head` must produce exactly the schema the ORM models describe."""
    with tempfile.TemporaryDirectory() as d:
        url = f"sqlite:///{Path(d, 'm.db').as_posix()}"
        env = {**os.environ, "DATABASE_URL": url, "PYTHONPATH": os.pathsep.join(sys.path)}
        r = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=API, env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        from app import models  # noqa: F401
        from app.db import Base
        eng = create_engine(url)
        with eng.connect() as conn:
            diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
        eng.dispose()
    assert diff == [], diff
