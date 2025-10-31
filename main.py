import os
import sys
import asyncio
import subprocess
import zipfile
from aiohttp import web
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

# ✅ Always flush logs immediately (important for Render)
sys.stdout.reconfigure(line_buffering=True)

# ✅ Detect environment (local vs Render)
ON_RENDER = os.environ.get("RENDER") == "true"

# ✅ Set Playwright browser path based on environment
if ON_RENDER:
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "/opt/render/project/src/.playwright-browsers"
else:
    os.environ.pop("PLAYWRIGHT_BROWSERS_PATH", None)  # Use default local install

# ✅ Persistent user data directory (saves login)
USER_DATA_DIR = (
    "/opt/render/project/src/wati_profile" if ON_RENDER else os.path.join(os.getcwd(), "wati_profile")
)

# 🧩 Auto-unzip saved login for Render
def unzip_wati_profile():
    zip_path = os.path.join(os.getcwd(), "wati_profile.zip")
    if ON_RENDER and os.path.exists(zip_path):
        if not os.path.exists(USER_DATA_DIR):
            print("📦 Extracting saved login (wati_profile.zip)...", flush=True)
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(os.path.dirname(USER_DATA_DIR))
            print("✅ Login data extracted successfully!", flush=True)
        else:
            print("✅ Existing login folder detected — skipping unzip.", flush=True)


# ✅ Ensure Chromium is installed
async def ensure_chromium_installed():
    chromium_path = "/opt/render/project/src/.playwright-browsers/chromium-1117/chrome-linux/chrome"
    if ON_RENDER and not os.path.exists(chromium_path):
        print("🧩 Chromium not found, installing it now...", flush=True)
        process = await asyncio.create_subprocess_exec(
            "python3", "-m", "playwright", "install", "chromium",
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
        print("✅ Chromium already exists or running locally — skipping install.", flush=True)


# 🌐 Bot configuration
WATI_URL = "https://live.wati.io/1037246/teamInbox/"
CHECK_INTERVAL = 180  # seconds


async def run_wati_bot():
    print("🌐 Launching WATI automation with persistent browser...", flush=True)

    while True:
        try:
            async with async_playwright() as p:
                # ✅ Launch persistent Chromium (saves session)
                browser_context = await p.chromium.launch_persistent_context(
                    user_data_dir=USER_DATA_DIR,
                    headless=ON_RENDER,  # ✅ headless only on Render
                )
                page = await browser_context.new_page()

                print("🌍 Navigating to WATI Inbox...", flush=True)
                await page.goto(WATI_URL, timeout=60000)
                await asyncio.sleep(2)

                # ✅ Check login
                try:
                    await page.wait_for_selector("text=Team Inbox", timeout=60000)
                    print("✅ Logged in and WATI Inbox loaded successfully!", flush=True)
                except PlaywrightTimeout:
                    print("⚠️ Login required — please log in manually (locally).", flush=True)
                    print("💾 Once logged in, DO NOT close the browser — wait 60s to save session.", flush=True)
                    await asyncio.sleep(60)
                    print("💾 Saving login session to:", USER_DATA_DIR, flush=True)

                    # ✅ Save storage state and close browser
                    await browser_context.storage_state(path=os.path.join(USER_DATA_DIR, "storage.json"))
                    await browser_context.close()

                    # ✅ Auto-zip wati_profile for Render upload
                    zip_path = os.path.join(os.getcwd(), "wati_profile.zip")
                    if not ON_RENDER:
                        print("📦 Creating wati_profile.zip for Render...", flush=True)
                        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                            for root, _, files in os.walk(USER_DATA_DIR):
                                for file in files:
                                    file_path = os.path.join(root, file)
                                    zipf.write(file_path, os.path.relpath(file_path, os.path.dirname(USER_DATA_DIR)))
                        print("✅ wati_profile.zip created successfully!", flush=True)

                    print("✅ Login session saved permanently! Please rerun the bot.", flush=True)
                    return  # Stop loop after saving login

                # ✅ Main automation loop
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
                        print("😴 No unread chats. Waiting 3 mins...", flush=True)
                        await asyncio.sleep(CHECK_INTERVAL)
                        await page.reload()
                        continue

                    print(f"💬 Found {len(unread_elements)} unread chat(s). Processing...", flush=True)
                    processed = 0

                    for elem in unread_elements:
                        processed += 1
                        print(f"👉 Opening unread chat {processed}/{len(unread_elements)}", flush=True)
                        try:
                            await elem.scroll_into_view_if_needed()
                            await elem.click()
                            print("🟢 Clicked unread chat successfully", flush=True)

                            await asyncio.sleep(2.5)
                            await page.click(
                                "#mainTeamInbox div.chat-side-content div span.chat-input__icon-option",
                                timeout=10000,
                            )
                            await asyncio.sleep(1.5)

                            ads_ctwa = await page.query_selector("#flow-nav-68ff67df4f393f0757f108d8")
                            if ads_ctwa:
                                await ads_ctwa.click()
                                print("✅ Clicked Ads (CTWA) successfully!", flush=True)
                            else:
                                print("⚠️ 'Ads (CTWA)' not found.", flush=True)

                            await asyncio.sleep(2)

                        except Exception as e:
                            print(f"⚠️ Error in chat #{processed}: {e}", flush=True)
                            continue

                    print("🕒 Waiting before next check...", flush=True)
                    await asyncio.sleep(CHECK_INTERVAL)
                    await page.reload()

        except Exception as e:
            print(f"🚨 Fatal error: {e}", flush=True)
            await asyncio.sleep(10)


# ✅ Web server
async def start_web_server():
    async def handle(request):
        return web.Response(text="✅ WATI AutoBot running successfully!")

    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", 10000)))
    await site.start()
    print("🌍 Web server running!", flush=True)


async def main():
    print("🚀 Initializing environment...", flush=True)
    unzip_wati_profile()
    await ensure_chromium_installed()

    print("🚀 Starting bot and web server...", flush=True)
    await asyncio.gather(start_web_server(), run_wati_bot())


if __name__ == "__main__":
    asyncio.run(main())
