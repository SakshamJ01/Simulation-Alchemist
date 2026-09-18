"""End-to-end browser tests for the Simulation Alchemist Researcher Workbench via Playwright."""

from __future__ import annotations

import threading
import time
from typing import Generator
import pytest
from playwright.sync_api import sync_playwright, expect
from werkzeug.serving import make_server
from workbench.app import app


@pytest.fixture(scope="session")
def live_workbench_url() -> Generator[str, None, None]:
    """Start an ephemeral test server on port 5055 to ensure fresh template and route testing."""
    port = 5055
    server = make_server("127.0.0.1", port, app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.4)
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


def test_workbench_homepage_loads(live_workbench_url: str) -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(live_workbench_url, timeout=30000)

        # Title or main heading check
        content = page.content()
        assert "Simulation Alchemist" in content or "Workbench" in content

        # Check for body visibility
        expect(page.locator("body")).to_be_visible()

        # Capture visual screenshot of the loaded workbench
        page.screenshot(path="figures/workbench_e2e_screenshot.png")
        browser.close()


def test_workbench_api_endpoints(live_workbench_url: str) -> None:
    with sync_playwright() as p:
        request_context = p.request.new_context(base_url=live_workbench_url, timeout=90000)

        # 1. Check root page returns 200
        resp = request_context.get("/")
        assert resp.status == 200
        assert "Simulation Alchemist" in resp.text()

        # 2. Check history API
        hist_resp = request_context.get("/api/history")
        assert hist_resp.status == 200
        hist_data = hist_resp.json()
        assert "records" in hist_data
        assert "total" in hist_data

        # 3. Check coupling primitives catalog API
        prims_resp = request_context.get("/api/couplings/primitives")
        assert prims_resp.status == 200
        prims_data = prims_resp.json()
        assert prims_data.get("success") is True
        assert len(prims_data.get("primitives", [])) >= 4

        # 4. Test run simulation endpoint with small step count
        run_resp = request_context.post(
            "/run",
            data={
                "exp_id": "field_guided_movers",
                "max_steps": 2,
                "seed": 42,
                "tags": ["e2e_test"],
            },
            timeout=90000,
        )
        assert run_resp.status in (200, 201)
        res_json = run_resp.json()
        assert "record_id" in res_json or "metrics" in res_json

        # 5. Test sensitivity analysis endpoint
        sens_resp = request_context.post(
            "/api/sensitivity/analyze",
            data={
                "template": "gated_movers",
                "n_trajectories": 2,
                "seed": 42,
            },
            timeout=90000,
        )
        assert sens_resp.status == 200
        sens_json = sens_resp.json()
        assert sens_json.get("success") is True
        assert "result" in sens_json

        # 6. Test intelligent multi-objective search endpoint
        search_resp = request_context.post(
            "/api/intelligent_search/run",
            data={
                "template": "gated_movers",
                "n_initial_samples": 2,
                "n_iterations": 1,
                "candidates_per_iter": 2,
                "seed": 42,
            },
            timeout=90000,
        )
        assert search_resp.status == 200
        search_json = search_resp.json()
        assert search_json.get("success") is True
        assert "result" in search_json

        request_context.dispose()


def test_workbench_3d_viewport_toggle(live_workbench_url: str) -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(live_workbench_url, timeout=30000)

        # Ensure initial 2D view is active
        btn_2d = page.locator("#btn-view-2d")
        btn_3d = page.locator("#btn-view-3d")
        canvas_2d = page.locator("#sim-canvas")
        container_3d = page.locator("#sim-canvas-3d-container")
        toolbar_3d = page.locator("#controls-3d-toolbar")

        expect(btn_2d).to_have_class("view-mode-btn active")
        expect(canvas_2d).to_be_visible()

        # Switch to 3D View Mode
        btn_3d.click()
        page.wait_for_timeout(500)

        expect(btn_3d).to_have_class("view-mode-btn active")
        expect(canvas_2d).not_to_be_visible()
        expect(container_3d).to_be_visible()
        expect(toolbar_3d).to_be_visible()

        # Capture visual proof of 3D Viewport
        page.screenshot(path="figures/workbench_3d_viewport.png")

        # Switch back to 2D View Mode
        btn_2d.click()
        page.wait_for_timeout(300)

        expect(btn_2d).to_have_class("view-mode-btn active")
        expect(canvas_2d).to_be_visible()
        expect(container_3d).not_to_be_visible()

        browser.close()

