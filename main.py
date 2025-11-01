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
ZIP_PATH = os.path.join(os.getcwd(), "wati_profile.zip")

# 🧩 Auto-unzip saved login for Render
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
                browser_context = await p.chromium.launch_persistent_context(
                    user_data_dir=USER_DATA_DIR,
                    headless=ON_RENDER,  # ✅ headless only on Render
                )
                page = await browser_context.new_page()

                print("🌍 Navigating to WATI Inbox...", flush=True)
                await page.goto(WATI_URL, timeout=60000)
                await asyncio.sleep(5)

                # ✅ Always ensure login and save it
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

                # ✅ Always save login session
                print("💾 Saving login session to:", USER_DATA_DIR, flush=True)
                storage_path = os.path.join(USER_DATA_DIR, "storage.json")
                try:
                    await browser_context.storage_state(path=storage_path)
                    print(f"✅ storage.json saved successfully at {storage_path}", flush=True)
                except Exception as e:
                    print(f"⚠️ Failed to save storage.json: {e}", flush=True)

                # ✅ Zip the folder safely (skip sockets/locks)
                if not ON_RENDER:
                    print("📦 Creating wati_profile.zip automatically...", flush=True)
                    skip_keywords = ["Socket", "lock", "Singleton", "Crashpad", "Temp"]
                    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as zipf:
                        for root, _, files in os.walk(USER_DATA_DIR):
                            for file in files:
                                file_path = os.path.join(root, file)
                                if any(word.lower() in file.lower() for word in skip_keywords):
                                    print(f"⚠️ Skipping temp/socket file: {file_path}", flush=True)
                                    continue
                                try:
                                    zipf.write(file_path, os.path.relpath(file_path, os.path.dirname(USER_DATA_DIR)))
                                except Exception as e:
                                    print(f"⚠️ Skipping problematic file {file_path}: {e}", flush=True)
                                    continue
                    print("✅ wati_profile.zip created successfully!", flush=True)
                    print("📤 You can now upload this ZIP to GitHub for Render deploy.", flush=True)

                await browser_context.close()
                print("✅ Login session saved permanently! You can rerun the bot now.", flush=True)
                return  # Stop after saving login once

        except Exception as e:
            print(f"🚨 Fatal error: {e}", flush=True)
            await asyncio.sleep(10)


# ✅ Web server — serves ZIP file for direct download
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
    app.router.add_get("/wati_profile.zip", handle_zip)  # 🧩 Download endpoint
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", 10000)))
    await site.start()
    print("🌍 Web server running on port", os.getenv("PORT", 10000), flush=True)
    print("📥 Download your ZIP at /wati_profile.zip", flush=True)


async def main():
    print("🚀 Initializing environment...", flush=True)
    unzip_wati_profile()
    await ensure_chromium_installed()
    print("🚀 Starting bot and web server...", flush=True)
    await asyncio.gather(start_web_server(), run_wati_bot())


if __name__ == "__main__":
    asyncio.run(main())
