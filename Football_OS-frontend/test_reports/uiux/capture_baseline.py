"""Phase 0 baseline capture for the Football Intelligence OS UI/UX transformation.

Uses the local dev gateway session (/dev/sign-in) and Playwright Chromium.
Writes screenshots + a machine-readable audit summary to test_reports/uiux/baseline.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent / "baseline"
OUT.mkdir(parents=True, exist_ok=True)

VIEWPORTS = [
    (1920, 1080),
    (1440, 900),
    (1280, 800),
    (1024, 768),
    (768, 900),
    (390, 844),
]

ROUTES = [
    ("dashboard", "/dashboard"),
    ("players", "/players"),
    ("compare", "/players/compare"),
    ("similarity", "/players/similarity"),
    ("roles", "/players/roles"),
    ("tactical-fit", "/tactical/fit"),
    ("recruitment-projects", "/recruitment/projects"),
    ("watchlists", "/watchlists"),
    ("decision-engine", "/decisions"),
    ("market", "/market"),
    ("valuation", "/market/valuation"),
    ("opportunities", "/market/opportunities"),
    ("replacements", "/market/replacements"),
    ("transfer-risk", "/market/risk"),
    ("matches", "/matches"),
    ("squad-builder", "/squad/builder"),
    ("squad-simulator", "/squad/simulator"),
    ("squad-scenarios", "/squad/scenarios"),
    ("scenarios", "/scenarios"),
    ("shortlists", "/shortlists"),
    ("research", "/research"),
    ("research-models", "/research/models"),
    ("research-data", "/research/data"),
    ("research-experiments", "/research/experiments"),
    ("data-quality", "/system/data-quality"),
    ("copilot", "/copilot"),
    ("operations", "/operations"),
    ("global-operations", "/operations/global"),
    ("continuous-learning", "/intelligence/continuous"),
    ("decision-lab", "/decision-lab"),
    ("outcome-intelligence", "/outcome-intelligence"),
]


def settle(page) -> None:
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    page.wait_for_timeout(1200)


def metrics(page) -> dict:
    return page.evaluate(
        """() => {
          const de = document.documentElement;
          const overflow = de.scrollWidth - de.clientWidth;
          const cards = document.querySelectorAll('.intelligence-card, .data-block, .card, .panel').length;
          const headings = [...document.querySelectorAll('h1')].map(h => h.innerText.trim()).filter(Boolean);
          return {
            title: document.title,
            h1: headings[0] || null,
            headingCount: headings.length,
            scrollWidth: de.scrollWidth,
            clientWidth: de.clientWidth,
            horizontalOverflowPx: overflow,
            documentHeight: de.scrollHeight,
            cardCount: cards,
            textLength: document.body.innerText.length,
          };
        }"""
    )


def main() -> int:
    summary = {"generatedAt": time.strftime("%Y-%m-%dT%H:%M:%S"), "routes": [], "viewports": []}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        page = context.new_page()
        console_errors: list[str] = []
        failed: list[str] = []

        def on_console(msg):
            if msg.type in ("error", "warning") and len(console_errors) < 400:
                console_errors.append(f"{msg.type}: {msg.text[:300]}")

        def on_failed(req):
            if len(failed) < 400:
                failed.append(f"{req.method} {req.url} -> {req.failure}")

        page.on("console", on_console)
        page.on("requestfailed", on_failed)

        # Establish the local dev session (cookie is host-scoped, shared across ports).
        page.goto("http://localhost:8004/dev/sign-in", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(800)
        print("signed in, landing:", page.url)

        # Desktop sweep.
        for slug, path in ROUTES:
            page.goto(f"http://localhost:3005/{path.lstrip('/')}", wait_until="domcontentloaded", timeout=45000)
            settle(page)
            m = metrics(page)
            m.update({"slug": slug, "path": path, "viewport": "1440x900"})
            summary["routes"].append(m)
            page.screenshot(path=str(OUT / f"baseline-{slug}-1440x900.png"), full_page=True)
            print(f"route {slug:24s} overflow={m['horizontalOverflowPx']:4d} h1={m['h1']!r}")

        # Player profile (requires a real id).
        try:
            api = context.request.get(
                "http://localhost:8004/api/v1/players/search?page=1&page_size=1"
            )
            pid = api.json()["items"][0]["id"]
            page.goto(f"http://localhost:3005/players/{pid}", wait_until="domcontentloaded", timeout=45000)
            settle(page)
            m = metrics(page)
            m.update({"slug": "player-profile", "path": f"/players/{pid}", "viewport": "1440x900", "playerId": pid})
            summary["routes"].append(m)
            page.screenshot(path=str(OUT / "baseline-player-profile-1440x900.png"), full_page=True)
            print("route player-profile           ok", pid)
        except Exception as exc:  # pragma: no cover - evidence capture only
            print("profile capture failed:", exc)

        # Six required viewport sizes on the three most information-dense routes.
        for width, height in VIEWPORTS:
            page.set_viewport_size({"width": width, "height": height})
            for slug, path in [("dashboard", "/dashboard"), ("players", "/players"), ("market", "/market")]:
                page.goto(f"http://localhost:3005/{path}", wait_until="domcontentloaded", timeout=45000)
                settle(page)
                m = metrics(page)
                m.update({"slug": slug, "path": path, "viewport": f"{width}x{height}"})
                summary["viewports"].append(m)
                page.screenshot(
                    path=str(OUT / f"baseline-{slug}-{width}x{height}.png"), full_page=True
                )
                print(f"viewport {width}x{height} {slug:10s} overflow={m['horizontalOverflowPx']}")

        summary["consoleErrors"] = console_errors
        summary["failedRequests"] = failed
        browser.close()

    (OUT / "baseline-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nWrote {len(summary['routes'])} route rows and {len(summary['viewports'])} viewport rows to {OUT}")
    print(f"console errors/warnings: {len(summary['consoleErrors'])}, failed requests: {len(summary['failedRequests'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
