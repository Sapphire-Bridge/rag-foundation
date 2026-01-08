import asyncio

from app import worker


def test_reset_stuck_documents_forwards_session_factory(monkeypatch) -> None:
    called: dict[str, object] = {}

    def fake_reset(*, session_factory=None) -> None:
        called["session_factory"] = session_factory

    monkeypatch.setattr(worker, "_reset_stuck_documents", fake_reset)
    sf = object()
    asyncio.run(worker.reset_stuck_documents({}, session_factory=sf))
    assert called["session_factory"] is sf
