import os
import sys
import asyncio
import subprocess
import zipfile
from aiohttp import web
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

# ✅ Flush logs immediately
sys.stdout.reconfigure(line_buffering=True)

# ✅ Detect environment
ON_RENDER = os.environ.get("RENDER") == "true"

# ✅ Browser path handling
if ON_RENDER:
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "/opt/render/project/src/.playwright-browsers"
else:
    os.environ.pop("PLAYWRIGHT_BROWSERS_PATH", None)

# ✅ Paths
USER_DATA_DIR = (
    "/opt/render/project/src/wati_profile" if ON_RENDER else os.path.join(os.getcwd(), "wati_profile")
)
ZIP_PATH = os.path.join(os.getcwd(), "wati_profile.zip")

# 🧩 Unzip profile on Render
def unzip_wati_profile():
    print("Checking for saved login ZIP:", os.path.exists(ZIP_PATH), flush=True)
    if ON_RENDER and os.path.exists(ZIP_PATH):
        if not os.path.exists(USER_DATA_DIR):
            print("📦 Extracting saved login (wati_profile.zip)...", flush=True)
            with zipfile.ZipFile(ZIP_PATH, "r") as zip_ref:
                zip_ref.extractall(os.path.dirname(USER_DATA_DIR))
            print("✅ Login data extracted successfully!", flush=True)
        else:
            print("✅ Existing login folder detected — skipping unzip.", flush=True)
    elif not ON_RENDER:
        print("ℹ️ Running locally — unzip not required.", flush=True)
    else:
        print("⚠️ No wati_profile.zip found in Render build.", flush=True)

# ✅ Ensure Chromium exists
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

# 🌐 WATI settings
WATI_URL = "https://live.wati.io/1037246/teamInbox/"
CHECK_INTERVAL = 180  # seconds

# 🧠 Main automation
async def run_wati_bot():
    print("🌐 Launching WATI automation with persistent browser...", flush=True)

    while True:
        try:
            async with async_playwright() as p:
                browser_context = await p.chromium.launch_persistent_context(
                    user_data_dir=USER_DATA_DIR,
                    headless=ON_RENDER,
                )
                page = await browser_context.new_page()
                print("🌍 Navigating to WATI Inbox...", flush=True)
                await page.goto(WATI_URL, timeout=60000)
                await asyncio.sleep(5)

                try:
                    await page.wait_for_selector("text=Team Inbox", timeout=20000)
                    print("✅ Already logged in — saving session anyway!", flush=True)
                except PlaywrightTimeout:
                    print("⚠️ Login required — please log in manually (locally).", flush=True)
                    print("💾 Once logged in, DO NOT close the browser — wait 60s to save session.", flush=True)
                    try:
                        await page.wait_for_selector("text=Team Inbox", timeout=60000)
                        print("✅ Login detected after manual login!", flush=True)
                    except PlaywrightTimeout:
                        print("⏳ Still not logged in after 60s — retrying...", flush=True)
                        await asyncio.sleep(10)
                        continue

                # ✅ Save session
                print("💾 Saving full login session to:", USER_DATA_DIR, flush=True)
                try:
                    await browser_context.storage_state(path=os.path.join(USER_DATA_DIR, "storage.json"))
                    print("✅ storage.json saved successfully!", flush=True)
                except Exception as e:
                    print(f"⚠️ Failed to save storage.json: {e}", flush=True)

                # ✅ Safe zipping — skips cache and volatile files
                if not ON_RENDER:
                    print("📦 Creating wati_profile.zip including full Chrome profile...", flush=True)
                    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as zipf:
                        for root, dirs, files in os.walk(USER_DATA_DIR):
                            # Skip cache folders to prevent race conditions
                            if "Cache" in root or "GPUCache" in root or "Code Cache" in root:
                                continue
                            for file in files:
                                file_path = os.path.join(root, file)
                                rel_path = os.path.relpath(file_path, os.path.dirname(USER_DATA_DIR))
                                if any(skip in file_path for skip in [
                                    "SingletonLock", "SingletonSocket",
                                    "SingletonCookie", "RunningChromeVersion"
                                ]):
                                    print(f"⚠️ Skipping system file during zip: {file_path}", flush=True)
                                    continue
                                try:
                                    zipf.write(file_path, rel_path)
                                except FileNotFoundError:
                                    print(f"⚠️ Skipped missing file: {file_path}", flush=True)
                    print("✅ wati_profile.zip created successfully (FULL profile, no cache)!", flush=True)
                    print("📤 Upload this ZIP to GitHub for Render deploy.", flush=True)

                await browser_context.close()
                print("✅ Login session saved permanently! You can rerun the bot now.", flush=True)
                return

        except Exception as e:
            print(f"🚨 Fatal error: {e}", flush=True)
            await asyncio.sleep(10)

# ✅ Web server for Render + ZIP download
async def start_web_server():
    async def handle_root(request):
        return web.Response(text="✅ WATI AutoBot running successfully!")
    async def handle_zip(request):
        if os.path.exists(ZIP_PATH):
            return web.FileResponse(ZIP_PATH)
        else:
            return web.Response(text="❌ ZIP not found", status=404)
    app = web.Application()
    app.router.add_get("/", handle_root)
    app.router.add_get("/wati_profile.zip", handle_zip)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", 10000)))
    await site.start()
    print("🌍 Web server running on port", os.getenv("PORT", 10000), flush=True)
    print("📥 Download your ZIP at /wati_profile.zip", flush=True)

# ✅ Entry point
async def main():
    print("🚀 Initializing environment...", flush=True)
    unzip_wati_profile()
    await ensure_chromium_installed()
    print("🚀 Starting bot and web server...", flush=True)
    await asyncio.gather(start_web_server(), run_wati_bot())

if __name__ == "__main__":
    asyncio.run(main())
