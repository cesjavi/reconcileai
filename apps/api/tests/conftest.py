import os
import tempfile
from pathlib import Path

_tmp = tempfile.mkdtemp(prefix="reconcileai-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_tmp, 'test.db').as_posix()}"
os.environ["DEMO_DIR"] = str(Path(__file__).resolve().parents[3] / "demo")
os.environ["INFERENCE_PROVIDER"] = "mock"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import models  # noqa: E402,F401
from app.db import Base, get_engine  # noqa: E402
from app.main import app, get_extractor  # noqa: E402

H = {"X-Actor": "tester"}


@pytest.fixture()
def client():
    Base.metadata.drop_all(get_engine())
    Base.metadata.create_all(get_engine())
    app.dependency_overrides.clear()
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def fake_extractor():
    """Install an extractor that returns scripted refs, recording what it was asked."""
    from inference import ExtractionPayload, ExtractionResult
    import hashlib
    import uuid

    class Fake:
        is_mock = False
        calls: list[str] = []
        refs_by_text: dict[str, list[str]] = {}

        def extract(self, text):
            self.calls.append(text)
            refs = self.refs_by_text.get(text, [])
            from inference import Evidenced
            payload = ExtractionPayload(references=[Evidenced(value=r, evidence=r) for r in refs])
            return ExtractionResult(
                request_id=str(uuid.uuid4()), source="vllm", is_mock=False, model="fake-model", status="ok",
                original_text=text, text_sha256=hashlib.sha256(text.encode()).hexdigest(), extraction=payload,
                latency_ms=12.5, attempts=1)

    fake = Fake()
    fake.calls = []
    fake.refs_by_text = {}
    app.dependency_overrides[get_extractor] = lambda: fake
    return fake


def csv_bytes(*rows, header="id,date,amount,description,document,voucher"):
    return ("\n".join([header, *rows]) + "\n").encode()


def upload(client, kind, content, name="f.csv", headers=H):
    return client.post(f"/imports/{kind}", files={"file": (name, content, "text/csv")}, headers=headers)
