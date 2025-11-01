import os
import sys
import asyncio
import subprocess
import zipfile
from aiohttp import web
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

# ✅ Flush logs immediately
sys.stdout.reconfigure(line_buffering=True)

# ✅ Detect Render
ON_RENDER = os.environ.get("RENDER") == "true"

# ✅ Playwright browser path
if ON_RENDER:
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "/tmp/playwright-browsers"
else:
    local_browser_path = os.path.join(os.getcwd(), "playwright_browsers")
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = local_browser_path
os.makedirs(os.environ["PLAYWRIGHT_BROWSERS_PATH"], exist_ok=True)

# ✅ Persistent profile directory
USER_DATA_DIR = (
    "/opt/render/project/src/wati_profile" if ON_RENDER else os.path.join(os.getcwd(), "wati_profile")
)

# 🧩 Unzip saved login if exists
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

# ✅ Ensure Chromium installed
async def ensure_chromium_installed():
    chromium_path = "/tmp/playwright-browsers/chromium-1117/chrome-linux/chrome"
    if not os.path.exists(chromium_path):
        print("🧩 Installing Chromium...", flush=True)
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "playwright", "install", "chromium",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            print(line.decode().strip(), flush=True)
        await process.wait()
        print("✅ Chromium installed successfully!", flush=True)
    else:
        print("✅ Chromium already installed.", flush=True)

# 🌐 Bot setup
WATI_URL = "https://live.wati.io/1037246/teamInbox/"
CHECK_INTERVAL = 180

async def run_wati_bot():
    print("🌐 Launching WATI automation with persistent browser...", flush=True)

    # 🧠 If on Render: open visible browser once for login
    # headless_mode = False if ON_RENDER else True
    headless_mode = True
    

    while True:
        try:
            async with async_playwright() as p:
                browser_context = await p.chromium.launch_persistent_context(
                    user_data_dir=USER_DATA_DIR,
                    headless=headless_mode,
                )
                page = await browser_context.new_page()
                print("🌍 Navigating to WATI Inbox...", flush=True)
                await page.goto(WATI_URL, timeout=60000)

                # 🕵️‍♀️ Wait for login if needed
                try:
                    await page.wait_for_selector("text=Team Inbox", timeout=60000)
                    print("✅ Logged in — session active!", flush=True)
                except PlaywrightTimeout:
                    print("⚠️ Please log in manually inside this browser window.", flush=True)
                    print("⏳ Waiting 90s for you to complete login...", flush=True)
                    await asyncio.sleep(90)

                # 💾 Save native Render session
                print("💾 Saving session...", flush=True)
                try:
                    await browser_context.storage_state(path=os.path.join(USER_DATA_DIR, "storage.json"))
                    print("✅ storage.json saved successfully.", flush=True)
                except Exception as e:
                    print(f"⚠️ Failed to save storage.json: {e}", flush=True)

                await browser_context.close()
                print("✅ Login session saved successfully! You can now redeploy in headless mode.", flush=True)
                return

        except Exception as e:
            print(f"🚨 Fatal error: {e}", flush=True)
            await asyncio.sleep(10)

# ✅ Web server
async def start_web_server():
    async def handle(request):
        return web.Response(text="✅ WATI AutoBot running successfully on Render!")
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", 10000)))
    await site.start()
    print("🌍 Web server running!", flush=True)

# 🚀 Main
async def main():
    print("🚀 Initializing environment...", flush=True)
    unzip_wati_profile()
    await ensure_chromium_installed()
    print("🚀 Starting bot (Render login mode)...", flush=True)
    await asyncio.gather(start_web_server(), run_wati_bot())

if __name__ == "__main__":
    asyncio.run(main())


