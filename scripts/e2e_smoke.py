"""Browser end-to-end smoke test (Playwright).

Runs the full user journey against a running server: register, log sleep, set up attendance,
add a task, ask the assistant, download the PDF, change settings, delete the account.

    pip install playwright && playwright install chromium
    BASE_URL=http://127.0.0.1:5000 python scripts/e2e_smoke.py
"""

import asyncio
import os
import time

from playwright.async_api import async_playwright, expect

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:5000")
CHROME = os.environ.get("CHROME_PATH")  # optional: use a system Chrome instead of Playwright's


async def main() -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch(**({"executable_path": CHROME, "args": ["--no-sandbox"]} if CHROME else {}))
        ctx = await browser.new_context(viewport={"width": 1280, "height": 900}, accept_downloads=True)
        pg = await ctx.new_page()
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.on("dialog", lambda d: asyncio.ensure_future(d.accept("4") if d.type == "prompt" else d.accept()))

        def step(msg: str) -> None:
            print(f"✓ {msg}")

        email = f"e2e{int(time.time())}@test.dev"
        await pg.goto(f"{BASE}/register")
        await pg.fill("#name", "Riya Test")
        await pg.fill("#email", email)
        await pg.fill("#password", "weak")
        await pg.click("button[type=submit]")
        await expect(pg.locator(".form-error")).to_contain_text("8")
        step("weak password rejected with a field message")

        await pg.fill("#password", "Strong123")
        await pg.click("button[type=submit]")
        await pg.wait_for_url("**/dashboard")
        await expect(pg.locator("text=No score yet")).to_be_visible()
        step("registered; empty-state dashboard shown")

        await pg.goto(f"{BASE}/sleep")
        await pg.click("#saveBtn")
        await expect(pg.locator("#result")).to_contain_text("Your score")
        step("night logged and scored")

        await pg.goto(f"{BASE}/attendance")
        await pg.click('[data-act="new-sem"]')
        await pg.fill("#semName", "Sem 5")
        await pg.click("#semForm button[type=submit]")
        await pg.click('[data-act="add-sub"]')
        await pg.fill("#subName", "Compilers")
        await pg.fill("#subHeld", "20")
        await pg.fill("#subAtt", "14")
        await pg.click("#subForm button[type=submit]")
        await expect(pg.locator(".subject")).to_contain_text("70.0%")
        await expect(pg.locator(".subject")).to_contain_text("Attend the next 4 classes")
        await pg.click('[data-mark="present"]')
        await expect(pg.locator(".subject")).to_contain_text("71.4%")
        step("semester + subject created, shortage maths correct, class marked")

        await pg.goto(f"{BASE}/planner")
        await pg.click("#addTaskBtn")
        await pg.fill("#tTitle", "Compiler assignment")
        await pg.fill("#tEst", "180")
        await pg.click("#taskForm button[type=submit]")
        await expect(pg.locator("#tasks")).to_contain_text("Compiler assignment")
        step("task added to planner")

        await pg.goto(f"{BASE}/assistant")
        await pg.fill("#msg", "How many classes can I skip?")
        await pg.press("#msg", "Enter")
        await expect(pg.locator(".msg.assistant").last).to_contain_text("Compilers")
        step("assistant answered from the user's own attendance data")

        await pg.goto(f"{BASE}/insights")
        async with pg.expect_download() as dl:
            await pg.click("a[href='/api/v1/reports/weekly.pdf']")
        step(f"PDF report downloaded ({(await dl.value).suggested_filename})")

        await pg.goto(f"{BASE}/settings")
        await pg.fill("#sleep_goal_hours", "7.5")
        await pg.click("#settingsForm button[type=submit]")
        await expect(pg.locator(".toast").last).to_contain_text("saved")
        step("settings saved")

        await pg.fill("#del_password", "Strong123")
        await pg.click("#delForm button[type=submit]")
        await pg.wait_for_url(f"{BASE}/")
        await pg.goto(f"{BASE}/dashboard")
        assert "/login" in pg.url
        step("account deleted; dashboard now requires login")

        assert not errors, errors
        print("All steps passed, no JavaScript errors.")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
