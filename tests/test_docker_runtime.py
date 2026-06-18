from __future__ import annotations

from pathlib import Path


def test_server_image_runs_migrations_before_api_start() -> None:
    dockerfile = Path("Dockerfile").read_text()
    start_script = Path("docker/start-api.sh").read_text()

    assert "COPY docker/start-api.sh /usr/local/bin/testflying-start-api" in dockerfile
    assert 'CMD ["testflying-start-api"]' in dockerfile
    assert "TESTFLYING_AUTO_MIGRATE" in start_script
    assert "alembic upgrade head" in start_script
    assert "exec uvicorn testflying_api.main:app" in start_script
