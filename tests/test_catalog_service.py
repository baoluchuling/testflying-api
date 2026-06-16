from __future__ import annotations

from sqlalchemy.orm import Session

from testflying_api.catalog_repository import CatalogRepository
from testflying_api.catalog_service import CatalogService
from testflying_api.seed import seed_demo_catalog


def test_workspace_contains_distribution_facts_only(db_session: Session) -> None:
    seed_demo_catalog(db_session)
    workspace = CatalogService(CatalogRepository(db_session)).workspace_for_device(
        device_id="device-001",
        platform="ios",
    )

    assert workspace.apps
    assert workspace.builds
    assert {build.install_info.platform for build in workspace.builds} == {"ios"}
    assert workspace.install_tasks == []
    assert workspace.sort_order.build_ids == []
