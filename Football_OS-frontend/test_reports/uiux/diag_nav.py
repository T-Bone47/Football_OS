from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    c = b.new_context(viewport={"width": 1440, "height": 900})
    page = c.new_page()
    page.goto("http://localhost:8004/dev/sign-in", wait_until="domcontentloaded")
    page.wait_for_timeout(500)
    for path in ["/dashboard", "/players", "/market", "/players/roles"]:
        r = page.goto("http://localhost:3005" + path, wait_until="domcontentloaded", timeout=45000)
        try:
            page.wait_for_load_state("networkidle", timeout=12000)
        except Exception:
            pass
        page.wait_for_timeout(1500)
        before = page.evaluate("() => ({url: location.href, h1: document.querySelector('h1')?.innerText, len: document.body.innerText.length})")
        page.screenshot(path=f"diag-{path.strip('/').replace('/','-')}.png", full_page=True)
        after = page.evaluate("() => ({url: location.href, h1: document.querySelector('h1')?.innerText, len: document.body.innerText.length})")
        print(path, "status", r.status if r else None, "before", before, "after", after)
    b.close()
