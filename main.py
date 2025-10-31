import os
import sys
import asyncio
import subprocess
from aiohttp import web
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

# ✅ Always flush logs immediately on Render
sys.stdout.reconfigure(line_buffering=True)

# ✅ Persistent browser install path on Render
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "/opt/render/project/src/.playwright-browsers"

async def ensure_chromium_installed():
    """Ensure Playwright Chromium exists in persistent path."""
    chromium_path = "/opt/render/project/src/.playwright-browsers/chromium-1117/chrome-linux/chrome"
    if not os.path.exists(chromium_path):
        print("🧩 Chromium not found, installing it now...", flush=True)
        process = await asyncio.create_subprocess_exec(
            "python", "-m", "playwright", "install", "chromium",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            print(line.decode().strip(), flush=True)
        await process.wait()
        print("✅ Chromium installed successfully!", flush=True)
    else:
        print("✅ Chromium already exists — skipping install.", flush=True)


# 🌐 WATI Bot Config
WATI_URL = "https://live.wati.io/1037246/teamInbox/"
STORAGE_STATE = "storageState.json"
CHECK_INTERVAL = 180  # 3 minutes between loops


async def run_wati_bot():
    print("🌐 Launching WATI automation...", flush=True)

    while True:
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(storage_state=STORAGE_STATE)
                page = await context.new_page()

                print("🌍 Navigating to WATI Inbox...", flush=True)
                await page.goto(WATI_URL, timeout=60000)
                await asyncio.sleep(2)

                try:
                    await page.wait_for_selector("text=Team Inbox", timeout=60000)
                    print("✅ WATI Inbox loaded successfully!", flush=True)
                except PlaywrightTimeout:
                    print("⚠️ Login expired — restarting in 10s...", flush=True)
                    await browser.close()
                    await asyncio.sleep(10)
                    continue

                while True:
                    print("🔎 Checking for unread chats...", flush=True)
                    try:
                        await page.wait_for_selector("div.conversation-item__unread-count", timeout=10000)
                    except PlaywrightTimeout:
                        print("😴 No unread chats found. Waiting 3 mins...", flush=True)
                        await asyncio.sleep(CHECK_INTERVAL)
                        await page.reload()
                        continue

                    unread_elements = await page.query_selector_all("div.conversation-item__unread-count")
                    if not unread_elements:
                        print("😴 No unread chats. Waiting 3 mins before rechecking...", flush=True)
                        await asyncio.sleep(CHECK_INTERVAL)
                        await page.reload()
                        continue

                    print(f"💬 Found {len(unread_elements)} unread chat(s). Processing...", flush=True)
                    processed = 0

                    while True:
                        unread_elements = await page.query_selector_all("div.conversation-item__unread-count")
                        if not unread_elements:
                            print("✅ All unread chats cleared for now.", flush=True)
                            break

                        elem = unread_elements[0]
                        processed += 1
                        print(f"👉 Opening unread chat {processed}/{len(unread_elements)}", flush=True)

                        try:
                            clicked = await page.evaluate(
                                """(node) => {
                                    const chatRow = node.closest('.conversation-item');
                                    if (chatRow) {
                                        chatRow.scrollIntoView({ behavior: 'smooth', block: 'center' });
                                        chatRow.click();
                                        return true;
                                    }
                                    return false;
                                }""",
                                elem,
                            )
                            if not clicked:
                                print("⚠️ Parent .conversation-item not found, clicking directly...", flush=True)
                                await elem.scroll_into_view_if_needed()
                                await elem.click(force=True)

                            print("🟢 Clicked unread chat successfully", flush=True)
                            await asyncio.sleep(2.5)

                            try:
                                await page.wait_for_selector("div.chat-area", timeout=10000)
                            except PlaywrightTimeout:
                                print("⚠️ Chat area not loaded, skipping this chat.", flush=True)
                                continue

                            print("⚙️ Clicking message options...", flush=True)
                            await page.click(
                                "#mainTeamInbox div.chat-side-content div span.chat-input__icon-option",
                                timeout=10000,
                            )
                            await asyncio.sleep(1.5)

                            print("📢 Clicking 'Ads (CTWA)'...", flush=True)
                            ads_ctwa = await page.query_selector("#flow-nav-68ff67df4f393f0757f108d8")
                            if ads_ctwa:
                                await ads_ctwa.click()
                                print("✅ Clicked Ads (CTWA) successfully!\n", flush=True)
                            else:
                                print("⚠️ Couldn’t find Ads (CTWA) element.", flush=True)

                            await asyncio.sleep(2)

                        except Exception as e:
                            print(f"⚠️ Error in unread chat #{processed}: {e}", flush=True)
                            await asyncio.sleep(2)
                            continue

                        print("🔄 Reloading inbox for next unread...", flush=True)
                        await page.reload()
                        await page.wait_for_selector("text=Team Inbox", timeout=30000)
                        await asyncio.sleep(2)

                    print(f"🕒 Completed {processed} unread chats. Waiting before next scan...", flush=True)
                    await asyncio.sleep(CHECK_INTERVAL)
                    await page.reload()

        except Exception as e:
            print(f"🚨 Fatal error: {e}", flush=True)
            print("🔁 Restarting bot in 10 seconds...", flush=True)
            await asyncio.sleep(10)


async def start_web_server():
    async def handle(request):
        return web.Response(text="✅ WATI AutoBot running successfully on Render!")

    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", 10000)))
    await site.start()
    print(f"🌍 Web server running on port {os.getenv('PORT', 10000)}", flush=True)


async def main():
    print("🚀 Initializing environment...", flush=True)
    await ensure_chromium_installed()

    print("🚀 Starting both web server and WATI bot...", flush=True)
    server_task = asyncio.create_task(start_web_server())
    await asyncio.sleep(2)
    bot_task = asyncio.create_task(run_wati_bot())
    await asyncio.gather(server_task, bot_task)


if __name__ == "__main__":
    asyncio.run(main())
