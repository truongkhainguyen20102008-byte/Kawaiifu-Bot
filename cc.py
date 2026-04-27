import discord
from discord.ext import commands
import aiohttp
import asyncio
import json
import base64
import re
import time
import urllib.parse
from urllib.parse import quote, unquote
import os

# 🌸 ── Config ──────────────────────────────────────────────────────────────────

BOT_TOKEN       = os.environ.get("BOT_TOKEN", "")
GITHUB_TOKEN    = os.environ.get("GITHUB_TOKEN", "")
GITHUB_USER     = os.environ.get("GITHUB_USER",     "truongkhainguyen20102008-byte")
GITHUB_REPO     = os.environ.get("GITHUB_REPO",     "thumbnails.json")
GITHUB_FILE     = os.environ.get("GITHUB_FILE",     "thumbnails.lua")   # Lua table format: ["name"] = "url"
GITHUB_FILE2    = os.environ.get("GITHUB_FILE2",    "thumbnails1.json")  # JSON format:      {"name": "url"}
GITHUB_BRANCH   = os.environ.get("GITHUB_BRANCH",   "main")
SCRAPER_API_KEY = os.environ.get("SCRAPER_API_KEY", "e8199d05cb8cb7de6e00cc1cc9820fc8")
RAILWAY_PROXY   = "https://ioioioioioioi.up.railway.app/img"
FANDOM_BASE     = "https://stealabrainrot.fandom.com/wiki/"
BOT_NAME        = "𝐊𝐚𝐢𝐰𝐚𝐢𝐢𝐟𝐮"

def make_footer() -> str:
    ts = int(time.time())
    return f"-# discord.gg/kawaiifunotifier  |  ✿  |  <t:{ts}:F>"

FOOTER_TEXT = "-# discord.gg/kawaiifunotifier  |  ✿"
FLAGS_V2       = 32768
FLAGS_EPHEMERAL = 64
FLAGS_V2_EPH   = FLAGS_V2 | FLAGS_EPHEMERAL   # Components V2 + ephemeral
OWNER_ID        = 698675478093103136
STEAL_CHANNEL   = os.environ.get("STEAL_CHANNEL", "0")   # Discord channel ID for steal notifications

# 🌸 ── Steal Storage (persistent JSON) ─────────────────────────────────────────

DATA_FILE = "steal_data.json"  # saved next to c.py on disk

def _load_data() -> tuple[dict, dict, list]:
    """Load user_map, discord_map, steal_log from disk. Returns defaults if missing."""
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
        um  = d.get("user_map",    {})
        dm  = d.get("discord_map", {})
        sl  = d.get("steal_log",   [])
        return um, dm, sl
    except (FileNotFoundError, json.JSONDecodeError):
        return {}, {}, []

def _save_data():
    """Persist current state to disk."""
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump({"user_map": user_map, "discord_map": discord_map, "steal_log": steal_log}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[KW] ⚠️ Failed to save data: {e}")

# user_map:     { roblox_username_lower -> discord_id_str }
# discord_map:  { discord_id_str -> roblox_username_lower }  (reverse lookup)
# steal_log:    list of dicts { pet, value, mutation, roblox_user, discord_id, ts, og }
user_map, discord_map, steal_log = _load_data()

OG_PETS = {
    "strawberry elephant", "meowl", "skibidi toilet", "headless horseman",
    "griffin", "signore carapace", "love love bear", "dragon cannelloni",
    "dragon gingerini", "hydra dragon cannelloni", "la supreme combinasion",
    "ginger gerat",
}

def is_og(name: str) -> bool:
    return name.lower() in OG_PETS

GITHUB_IMG_BASE = "https://raw.githubusercontent.com/venom-picture/venom-hub-pets1/main/"

# In-memory thumbnail cache (loaded from GitHub JSON at startup and after each push)
_thumb_cache: dict[str, str] = {}

def pet_img(name: str) -> str:
    """Return thumbnail URL for a pet. Uses GitHub cache if available, else fallback."""
    if not name:
        return ""
    key = name.lower().strip()
    if key in _thumb_cache:
        return _thumb_cache[key]
    # Fallback: build URL from GITHUB_IMG_BASE (old behaviour)
    return GITHUB_IMG_BASE + key.replace(" ", "_") + ".png"

async def refresh_thumb_cache():
    """Load thumbnail URLs from GitHub JSON file into _thumb_cache."""
    global _thumb_cache
    try:
        url     = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/{GITHUB_FILE2}?ref={GITHUB_BRANCH}"
        headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers=headers) as r:
                if r.status == 200:
                    result  = await r.json()
                    decoded = base64.b64decode(result["content"]).decode()
                    loaded  = json.loads(decoded)
                    _thumb_cache = {k.lower().strip(): v for k, v in loaded.items()}
                    print(f"[KW] ✅ Thumbnail cache refreshed — {len(_thumb_cache)} pets")
    except Exception as e:
        print(f"[KW] ⚠️ Could not refresh thumbnail cache: {e}")

# 🌸 ── Bot Setup ───────────────────────────────────────────────────────────────

intents = discord.Intents.default()
bot     = commands.Bot(command_prefix="!", intents=intents)
tree    = bot.tree

# 🌸 ── Owner Guard ─────────────────────────────────────────────────────────────

async def owner_check(interaction: discord.Interaction) -> bool:
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message(
            "🚫 **Access Denied** — This command is for the owner only.",
            ephemeral=True
        )
        return False
    return True

# 🌸 ── Components V2 ───────────────────────────────────────────────────────────

def txt(content: str) -> dict:
    return {"type": 10, "content": content}

def sep() -> dict:
    return {"type": 14, "divider": True, "spacing": 1}

def sep_sm() -> dict:
    return {"type": 14, "divider": False, "spacing": 1}

def footer() -> list:
    return [sep(), txt(make_footer())]

def section(content: str, thumbnail_url: str) -> dict:
    return {
        "type": 9,
        "components": [{"type": 10, "content": content}],
        "accessory": {
            "type": 11,
            "media": {"url": thumbnail_url, "loading_state": 2},
            "spoiler": False,
        },
    }

def container(*items: dict, color: int = 16738740) -> dict:
    return {"type": 17, "accent_color": color, "components": list(items)}

def action_row(*buttons: dict) -> dict:
    return {"type": 1, "components": list(buttons)}

def button(label: str, custom_id: str, style: int = 2) -> dict:
    return {"type": 2, "style": style, "label": label, "custom_id": custom_id}

# 🌸 ── Discord Helpers ─────────────────────────────────────────────────────────

def webhook_url(interaction: discord.Interaction) -> str:
    return f"https://discord.com/api/v10/webhooks/{interaction.application_id}/{interaction.token}"

async def send_v2(interaction: discord.Interaction, components: list[dict]):
    url = webhook_url(interaction)
    async with aiohttp.ClientSession() as s:
        async with s.post(url, json={"flags": FLAGS_V2, "components": components}) as r:
            if r.status not in (200, 204):
                raise Exception(f"Discord {r.status}: {(await r.text())[:200]}")

async def send_v2_eph(interaction: discord.Interaction, components: list[dict]):
    """Send an ephemeral response — only visible to the user who ran the command."""
    url = webhook_url(interaction)
    async with aiohttp.ClientSession() as s:
        async with s.post(url, json={"flags": FLAGS_V2_EPH, "components": components}) as r:
            if r.status not in (200, 204):
                raise Exception(f"Discord {r.status}: {(await r.text())[:200]}")

async def patch_original(wh_url: str, components: list[dict]):
    url = f"{wh_url}/messages/@original"
    async with aiohttp.ClientSession() as s:
        await s.patch(url, json={"flags": FLAGS_V2, "components": components})

# 🌸 ── URL Helpers ─────────────────────────────────────────────────────────────

def is_railway(url: str) -> bool:
    return "ioioioioioioi.up.railway.app" in url

def is_cdn_attachment(url: str) -> bool:
    return "media.discordapp.net/attachments" in url or "cdn.discordapp.com/attachments" in url

def extract_wikia_url(url: str) -> str | None:
    if is_railway(url) or is_cdn_attachment(url):
        return None
    if url.startswith("https://static.wikia.nocookie.net"):
        return url
    decoded = url
    for _ in range(5):
        new = unquote(decoded)
        if new == decoded:
            break
        decoded = new
    m = re.search(r'/https/(static\.wikia\.nocookie\.net/[^\s?#]+)', decoded)
    if m:
        return "https://" + m.group(1)
    m = re.search(r'(https?://static\.wikia\.nocookie\.net/[^\s"\'<>?#]+)', decoded)
    if m:
        return m.group(1)
    return None

def convert_to_railway(url: str) -> str:
    if is_railway(url) or is_cdn_attachment(url):
        return url
    wikia = extract_wikia_url(url)
    return f"{RAILWAY_PROXY}?url={quote(wikia, safe='')}" if wikia else url

def shorten(url: str, limit: int = 260) -> str:
    return url[:limit] + "..." if len(url) > limit else url

# 🌸 ── GitHub Helpers ──────────────────────────────────────────────────────────

def parse_lua_table(text: str) -> dict:
    data = {}
    for m in re.finditer(r'\["([^"\\]|\\.)*?"\]\s*=\s*"([^"\\]|\\.)*?"', text):
        raw = m.group(0)
        km  = re.match(r'\["((?:[^"\\]|\\.)*)"\]', raw)
        vm  = re.search(r'=\s*"((?:[^"\\]|\\.)*)"', raw)
        if km and vm:
            key   = km.group(1).replace('\\"', '"').replace("\\\\", "\\")
            value = vm.group(1).replace('\\"', '"').replace("\\\\", "\\")
            data[key] = value
    return data

async def fetch_thumbnails() -> tuple[dict, str]:
    url     = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/{GITHUB_FILE}?ref={GITHUB_BRANCH}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    async with aiohttp.ClientSession() as s:
        async with s.get(url, headers=headers) as r:
            if r.status != 200:
                raise Exception(f"GitHub Fetch {r.status}: {(await r.text())[:200]}")
            result  = await r.json()
            content = base64.b64decode(result["content"]).decode()
            try:
                data = json.loads(content)
            except Exception:
                data = parse_lua_table(content)
            return data, result["sha"]

def to_lua_table(data: dict) -> str:
    max_len = max((len(k) for k in data), default=0)
    lines   = []
    for key, value in data.items():
        ek  = key.replace("\\", "\\\\").replace('"', '\\"')
        ev  = value.replace("\\", "\\\\").replace('"', '\\"')
        pad = " " * (max_len - len(key) + 1)
        lines.append(f'    ["{ek}"]{pad}= "{ev}",')
    return "\n".join(lines)

async def _get_file_sha(session: aiohttp.ClientSession, filename: str) -> str | None:
    """Get current SHA of a file on GitHub (needed for PUT). Returns None if file doesn't exist."""
    url     = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/{filename}?ref={GITHUB_BRANCH}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    async with session.get(url, headers=headers) as r:
        if r.status == 200:
            return (await r.json()).get("sha")
        return None

async def push_thumbnails(data: dict, sha: str, msg: str):
    """Push sorted data to BOTH GitHub files: Lua table + JSON."""
    sorted_data = dict(sorted(data.items(), key=lambda x: x[0].lower()))
    headers     = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept":        "application/vnd.github.v3+json",
        "Content-Type":  "application/json",
    }

    # ── File 1: Lua table  ["name"] = "url", ─────────────────────────────────
    lua_encoded  = base64.b64encode(to_lua_table(sorted_data).encode()).decode()
    url1         = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/{GITHUB_FILE}"

    # ── File 2: JSON  {"name": "url"} ────────────────────────────────────────
    json_content = json.dumps(sorted_data, ensure_ascii=False, indent=2)
    json_encoded = base64.b64encode(json_content.encode()).decode()
    url2         = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/{GITHUB_FILE2}"

    async with aiohttp.ClientSession() as s:
        # Push Lua file
        async with s.put(url1, headers=headers,
            json={"message": msg, "content": lua_encoded, "sha": sha, "branch": GITHUB_BRANCH}
        ) as r:
            if r.status not in (200, 201):
                raise Exception(f"GitHub Push (lua) {r.status}: {(await r.text())[:300]}")

        # Get SHA for JSON file (may not exist yet)
        sha2 = await _get_file_sha(s, GITHUB_FILE2)
        payload2: dict = {"message": msg, "content": json_encoded, "branch": GITHUB_BRANCH}
        if sha2:
            payload2["sha"] = sha2

        # Push JSON file
        async with s.put(url2, headers=headers, json=payload2) as r:
            if r.status not in (200, 201):
                # Non-fatal — log warning but don't crash
                print(f"[KW] ⚠️ GitHub JSON push failed {r.status}: {(await r.text())[:200]}")

    # Refresh in-memory cache after successful push
    await refresh_thumb_cache()

# 🌸 ── Fandom Scraper ──────────────────────────────────────────────────────────

async def scrape_fandom_image(pet_name: str) -> tuple[str | None, str]:
    slug     = pet_name.replace(" ", "_")
    page_url = f"https://stealabrainrot.fandom.com/wiki/{urllib.parse.quote(slug)}"
    debug    = []
    timeout  = aiohttp.ClientTimeout(total=40)

    async with aiohttp.ClientSession() as session:
        try:
            hdrs = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0"}
            async with session.get(page_url, headers=hdrs, timeout=timeout) as r:
                body = await r.text()
                debug.append(f"Direct {r.status}: {body[:80]}")
                if r.status == 200 and "<!DOCTYPE" in body:
                    html = body
                else:
                    raise Exception(f"Blocked ({r.status})")
        except Exception as e:
            debug.append(f"Direct Err: {e} → ScraperAPI...")
            async with session.get(
                "https://api.scraperapi.com",
                params={"api_key": SCRAPER_API_KEY, "url": page_url, "render": "false"},
                timeout=timeout,
            ) as r:
                body = await r.text()
                debug.append(f"ScraperAPI {r.status}: {body[:80]}")
                if r.status != 200:
                    return None, "\n".join(debug)
                html = body

        m = re.search(r'<meta property=["\']og:image["\']\s+content=["\']([^"\']+)["\']', html)
        if not m:
            m = re.search(r'<meta content=["\']([^"\']+)["\']\s+property=["\']og:image["\']', html)
        if m:
            img_url = m.group(1)
            debug.append(f"Og:Image: {img_url[:100]}")
            if "wikia.nocookie.net" in img_url:
                return re.sub(r'/revision/latest.*', '', img_url), "\n".join(debug)

        imgs = re.findall(r'https://static\.wikia\.nocookie\.net/[^"\'\s<>]+\.(?:png|jpg|webp)', html)
        imgs = [u for u in imgs if not any(
            x in u.lower() for x in ["icon", "logo", "favicon", "placeholder", "wordmark", "fandom-heart"]
        )]
        if imgs:
            debug.append(f"Infobox: {imgs[0][:100]}")
            return re.sub(r'/revision/latest.*', '', imgs[0]), "\n".join(debug)

        debug.append("No image found in HTML.")
    return None, "\n".join(debug)

# 🌸 ── /ping ───────────────────────────────────────────────────────────────────

@tree.command(name="ping", description="Check the bot's latency and connection status.")
async def ping(interaction: discord.Interaction):
    if not await owner_check(interaction): return
    start      = time.monotonic()
    await interaction.response.defer(thinking=True)
    latency_ms = round((time.monotonic() - start) * 1000)
    ws_ms      = round(bot.latency * 1000)
    status     = "🟢 Excellent" if ws_ms < 80 else "🟡 Normal" if ws_ms < 150 else "🔴 Slow"

    await send_v2(interaction, [container(
        txt("## 🏓 Pong!"),
        sep(),
        txt(
            f"📡 **Websocket Latency:** `{ws_ms}ms`\n"
            f"⚡ **Response Time:** `{latency_ms}ms`\n"
            f"📶 **Status:** {status}"
        ),
        *footer(),
    )])

# 🌸 ── /addpet ─────────────────────────────────────────────────────────────────

@tree.command(name="addpet", description="Add a new pet with its thumbnail URL to GitHub.")
async def addpet(interaction: discord.Interaction, name: str, url: str):
    if not await owner_check(interaction): return
    await interaction.response.defer(thinking=True)

    converted = convert_to_railway(url)
    label     = "🚂 Railway Proxy — Converted" if converted != url else "📎 Discord CDN — Kept as-is"

    try:
        data, sha = await fetch_thumbnails()
    except Exception as e:
        await send_v2(interaction, [container(
            txt("## 🌩️ GitHub Error"),
            sep(),
            txt(f"💾 **Operation:** Add Pet\n🐾 **Pet:** `{name}`\n\n⛔ **Error:**\n```\n{e}\n```"),
            *footer(),
        )])
        return

    if name in data:
        exist = data[name]
        await send_v2(interaction, [container(
            txt("## 🚧 Pet Already Exists"),
            sep(),
            section(
                f"🐾 **{name}**\n\n"
                f"⚠️ Already in GitHub!\n\n"
                f"🔗 **Current URL**\n```\n{shorten(exist, 240)}\n```",
                exist
            ),
            sep(),
            txt(f"💡 Use `/updatepet` to change the URL instead.\n🆕 **New URL you tried**\n```\n{shorten(converted, 240)}\n```"),
            *footer(),
        )])
        return

    try:
        data[name] = converted
        await push_thumbnails(data, sha, f"[KW] Added: {name}")
        ok = True
    except Exception as e:
        ok  = False
        err = str(e)

    if ok:
        await send_v2(interaction, [container(
            txt("## ✅ Pet Added Successfully"),
            sep(),
            section(f"🐾 **{name}**\n\n{label}\n```\n{shorten(converted)}\n```", converted),
            sep(),
            txt("📦 **GitHub** — ✅ Pushed & sorted"),
            *footer(),
        )])
    else:
        await send_v2(interaction, [container(
            txt("## 💥 Failed To Add Pet"),
            sep(),
            txt(f"🐾 **Pet:** `{name}`\n\n📦 **GitHub** — ❌ Push failed\n```\n{err[:200]}\n```"),
            *footer(),
        )])

# 🌸 ── /updatepet ──────────────────────────────────────────────────────────────

@tree.command(name="updatepet", description="Update the thumbnail URL of an existing pet.")
async def updatepet(interaction: discord.Interaction, name: str, url: str):
    if not await owner_check(interaction): return
    await interaction.response.defer(thinking=True)

    converted = convert_to_railway(url)
    label     = "🚂 Railway Proxy — Converted" if converted != url else "📎 Discord CDN — Kept as-is"

    try:
        data, sha = await fetch_thumbnails()
    except Exception as e:
        await send_v2(interaction, [container(
            txt("## 🌩️ GitHub Error"),
            sep(),
            txt(f"💾 **Operation:** Update Pet\n🐾 **Pet:** `{name}`\n\n⛔ **Error:**\n```\n{e}\n```"),
            *footer(),
        )])
        return

    if name not in data:
        suggestions = [k for k in data if name.lower() in k.lower()]
        items = [txt(f"## 🔎 Pet Not Found\n🐾 **Pet:** `{name}`")]
        if suggestions:
            items += [sep(), txt("**🧩 Similar pets:**\n" + "\n".join(f"• `{s}`" for s in suggestions[:8]))]
        items += footer()
        await send_v2(interaction, [container(*items)])
        return

    old_url = data[name]

    try:
        data[name] = converted
        await push_thumbnails(data, sha, f"[KW] Updated: {name}")
        ok = True
    except Exception as e:
        ok  = False
        err = str(e)

    if ok:
        await send_v2(interaction, [container(
            txt("## ✏️ Pet Updated Successfully"),
            sep(),
            section(f"🐾 **{name}**\n\n{label}\n```\n{shorten(converted, 240)}\n```", converted),
            sep(),
            txt(f"🔁 **Previous URL**\n```\n{shorten(old_url, 200)}\n```"),
            sep(),
            txt("📦 **GitHub** — ✅ Pushed & sorted"),
            *footer(),
        )])
    else:
        await send_v2(interaction, [container(
            txt("## 💥 Failed To Update Pet"),
            sep(),
            txt(f"🐾 **Pet:** `{name}`\n\n📦 **GitHub** — ❌ Push failed\n```\n{err[:200]}\n```"),
            *footer(),
        )])

# 🌸 ── /deletepet ──────────────────────────────────────────────────────────────

@tree.command(name="deletepet", description="Delete a pet and its thumbnail URL from GitHub.")
async def deletepet(interaction: discord.Interaction, name: str):
    if not await owner_check(interaction): return
    await interaction.response.defer(thinking=True)

    try:
        data, sha = await fetch_thumbnails()
    except Exception as e:
        await send_v2(interaction, [container(
            txt("## 🌩️ GitHub Error"),
            sep(),
            txt(f"💾 **Operation:** Delete Pet\n🐾 **Pet:** `{name}`\n\n⛔ **Error:**\n```\n{e}\n```"),
            *footer(),
        )])
        return

    if name not in data:
        suggestions = [k for k in data if name.lower() in k.lower()]
        items = [txt(f"## 🗑️ Pet Not Found\n🐾 **Pet:** `{name}`")]
        if suggestions:
            items += [sep(), txt("**🧩 Similar pets:**\n" + "\n".join(f"• `{s}`" for s in suggestions[:8]))]
        items += footer()
        await send_v2(interaction, [container(*items)])
        return

    deleted_url = data[name]

    try:
        del data[name]
        await push_thumbnails(data, sha, f"[KW] Deleted: {name}")
        ok = True
    except Exception as e:
        ok  = False
        err = str(e)

    if ok:
        await send_v2(interaction, [container(
            txt("## 🗑️ Pet Deleted Successfully"),
            sep(),
            section(f"🐾 **{name}**\n\n🔗 **Deleted URL**\n```\n{shorten(deleted_url, 240)}\n```", deleted_url),
            sep(),
            txt(f"📦 **GitHub** — ✅ Deleted & sorted\n🔢 **Remaining pets:** {len(data)}"),
            *footer(),
        )])
    else:
        await send_v2(interaction, [container(
            txt("## 💥 Failed To Delete Pet"),
            sep(),
            txt(f"🐾 **Pet:** `{name}`\n\n📦 **GitHub** — ❌ Push failed\n```\n{err[:200]}\n```"),
            *footer(),
        )])

# 🌸 ── /getpet ─────────────────────────────────────────────────────────────────

@tree.command(name="getpet", description="Get the thumbnail URL of a specific pet.")
async def getpet(interaction: discord.Interaction, name: str):
    if not await owner_check(interaction): return
    await interaction.response.defer(thinking=True, ephemeral=True)

    try:
        data, _ = await fetch_thumbnails()
    except Exception as e:
        await send_v2_eph(interaction, [container(
            txt("## 🌩️ GitHub Error"),
            sep(),
            txt(f"💾 **Operation:** Get Pet\n🐾 **Pet:** `{name}`\n\n⛔ **Error:**\n```\n{e}\n```"),
            *footer(),
        )])
        return

    if name not in data:
        suggestions = [k for k in data if name.lower() in k.lower()]
        items = [txt(f"## 🔍 Pet Not Found\n🐾 **Pet:** `{name}`")]
        if suggestions:
            items += [sep(), txt("**💡 Did you mean:**\n" + "\n".join(f"• `{s}`" for s in suggestions[:5]))]
        items += footer()
        await send_v2_eph(interaction, [container(*items)])
        return

    url_val = data[name]
    await send_v2_eph(interaction, [container(
        txt("## 🖼️ Pet Thumbnail"),
        sep(),
        section(f"🐾 **{name}**\n\n🔗 **URL**\n```\n{shorten(url_val)}\n```", url_val),
        *footer(),
    )])

# 🌸 ── /searchpet ──────────────────────────────────────────────────────────────

@tree.command(name="searchpet", description="Search for pets by name or keyword.")
async def searchpet(interaction: discord.Interaction, query: str):
    if not await owner_check(interaction): return
    await interaction.response.defer(thinking=True, ephemeral=True)

    try:
        data, _ = await fetch_thumbnails()
    except Exception as e:
        await send_v2_eph(interaction, [container(
            txt("## 🌩️ GitHub Error"),
            sep(),
            txt(f"💾 **Operation:** Search Pet\n🔑 **Query:** `{query}`\n\n⛔ **Error:**\n```\n{e}\n```"),
            *footer(),
        )])
        return

    matches = sorted([k for k in data if query.lower() in k.lower()])

    if not matches:
        await send_v2_eph(interaction, [container(
            txt(f"## 🌫️ No Results Found\n🔑 **Query:** `{query}`"),
            *footer(),
        )])
        return

    top     = matches[0]
    top_url = data[top]
    items   = [
        txt(f"## 🔎 Search Results For `{query}`"),
        sep(),
        section(f"🥇 **Top Match:** `{top}`\n\n🔗 **URL**\n```\n{shorten(top_url, 240)}\n```", top_url),
    ]
    if len(matches) > 1:
        others = matches[1:26]
        items += [sep(), txt(f"**📋 Other matches ({len(matches) - 1}):**\n" + "\n".join(f"• `{m}`" for m in others))]
    items += [sep(), txt(f"🔢 **Total matches:** {len(matches)} / {len(data)} pets")]
    items += footer()
    await send_v2_eph(interaction, [container(*items)])

# 🌸 ── /listpets ───────────────────────────────────────────────────────────────

@tree.command(name="listpets", description="List all pets and their thumbnails stored in GitHub.")
async def listpets(interaction: discord.Interaction):
    if not await owner_check(interaction): return
    await interaction.response.defer(thinking=True, ephemeral=True)

    try:
        data, _ = await fetch_thumbnails()
    except Exception as e:
        await send_v2_eph(interaction, [container(
            txt("## 🌩️ GitHub Error"),
            sep(),
            txt(f"💾 **Operation:** List Pets\n\n⛔ **Error:**\n```\n{e}\n```"),
            *footer(),
        )])
        return

    railway_count = sum(1 for v in data.values() if is_railway(v))
    cdn_count     = sum(1 for v in data.values() if is_cdn_attachment(v))
    other_count   = len(data) - railway_count - cdn_count
    pet_names     = sorted(data.keys(), key=lambda x: x.lower())
    wh_url        = webhook_url(interaction)

    async def post_followup(components: list[dict]):
        payload = {"flags": FLAGS_V2_EPH, "components": components}
        for _ in range(5):
            async with aiohttp.ClientSession() as s:
                async with s.post(wh_url, json=payload) as r:
                    if r.status in (200, 204):
                        return
                    body = await r.text()
                    if r.status == 429:
                        try:
                            retry_after = json.loads(body).get("retry_after", 1.5)
                        except Exception:
                            retry_after = 1.5
                        await asyncio.sleep(float(retry_after) + 0.2)
                        continue
                    raise Exception(f"Discord {r.status}: {body[:200]}")
        raise Exception("Rate limited — max retries exceeded")

    await post_followup([container(
        txt("## 📋 Full Pet List"),
        sep(),
        txt(
            f"🐾 **Total Pets:** {len(data)}  •  "
            f"🚂 **Railway:** {railway_count}  •  "
            f"📎 **CDN:** {cdn_count}  •  "
            f"🔗 **Other:** {other_count}"
        ),
        sep_sm(),
        txt("**🌸 All Pets — Loading thumbnails below...**"),
    )])

    for i in range(0, len(pet_names), 5):
        chunk = pet_names[i:i + 5]
        items = [txt(f"**🐾 Pets ({i + 1}–{i + len(chunk)}):**")]
        for j, pname in enumerate(chunk):
            if j > 0:
                items.append(sep())
            items.append(section(f"**{pname}**", data[pname]))
        # Interleave dividers between section cards
        interleaved = []
        for idx, item in enumerate(items):
            if idx > 0:
                interleaved.append({"type": 14, "divider": True, "spacing": 1})
            interleaved.append(item)
        await post_followup([{"type": 17, "accent_color": 3092790, "components": interleaved}])
        await asyncio.sleep(0.8)

    await post_followup([container(
        txt(f"✅ **Done — {len(pet_names)} pets listed.**"),
        *footer(),
    )])

# 🌸 ── /fetchpet ───────────────────────────────────────────────────────────────

@tree.command(name="fetchpet", description="Auto-fetch a pet's image from the Fandom wiki and save it.")
async def fetchpet(interaction: discord.Interaction, name: str):
    if not await owner_check(interaction): return
    await interaction.response.defer(thinking=True, ephemeral=True)

    try:
        wikia_url, debug_info = await scrape_fandom_image(name)
    except Exception as e:
        await send_v2_eph(interaction, [container(
            txt("## 🌐 Scrape Failed"),
            sep(),
            txt(f"🐾 **Pet:** `{name}`\n\n⚠️ **Exception:**\n```\n{e}\n```"),
            *footer(),
        )])
        return

    if not wikia_url:
        page_url = FANDOM_BASE + quote(name.replace(" ", "_"))
        await send_v2_eph(interaction, [container(
            txt("## 🔍 Image Not Found On Wiki"),
            sep(),
            txt(
                f"🐾 **Pet:** `{name}`\n\n"
                f"❌ No image found on the wiki page.\n\n"
                f"🌐 **Page checked:**\n```\n{page_url}\n```\n\n"
                f"💡 Make sure the pet name matches the wiki page title exactly.\n\n"
                f"🛠️ **Debug info:**\n```\n{debug_info[:600]}\n```"
            ),
            *footer(),
        )])
        return

    railway_url = convert_to_railway(wikia_url)
    short_url   = shorten(railway_url)

    try:
        data, sha = await fetch_thumbnails()
    except Exception as e:
        await send_v2_eph(interaction, [container(
            txt("## 🌩️ GitHub Error"),
            sep(),
            txt(f"💾 **Operation:** Fetch Pet\n🐾 **Pet:** `{name}`\n\n⛔ **Error:**\n```\n{e}\n```"),
            *footer(),
        )])
        return

    if name in data:
        existing_url = data[name]
        wh_url       = webhook_url(interaction)
        payload = {
            "flags": FLAGS_V2_EPH,
            "components": [
                container(
                    txt("## 🚧 Pet Already Exists"),
                    sep(),
                    section(
                        f"🐾 **{name}**\n\n"
                        f"⚠️ Already in GitHub — Overwrite?\n\n"
                        f"🔗 **Current URL**\n```\n{shorten(existing_url)}\n```\n\n"
                        f"🌐 **Fetched URL**\n```\n{short_url}\n```",
                        existing_url
                    ),
                    *footer(),
                ),
                action_row(
                    button("✅ Yes — Overwrite",    f"overwrite_yes:{name}", style=3),
                    button("❌ No — Keep Existing", f"overwrite_no:{name}",  style=4),
                ),
            ],
        }
        async with aiohttp.ClientSession() as s:
            async with s.post(wh_url, json=payload) as r:
                if r.status not in (200, 204):
                    raise Exception(f"Discord {r.status}: {(await r.text())[:200]}")

        bot._fetchpet_pending       = getattr(bot, "_fetchpet_pending", {})
        bot._fetchpet_pending[name] = {"railway_url": railway_url, "data": data, "sha": sha}
        return

    try:
        data[name] = railway_url
        await push_thumbnails(data, sha, f"[KW] Auto-Fetch Added: {name}")
        ok = True
    except Exception as e:
        ok  = False
        err = str(e)

    if ok:
        await send_v2_eph(interaction, [container(
            txt("## 🌐 Pet Image Added Successfully"),
            sep(),
            section(f"🐾 **{name}**\n\n🚂 **Railway URL**\n```\n{short_url}\n```", railway_url),
            sep(),
            txt("📦 **GitHub** — ✅ Pushed & sorted"),
            *footer(),
        )])
    else:
        await send_v2_eph(interaction, [container(
            txt("## 💥 Failed To Save Pet"),
            sep(),
            txt(f"🐾 **Pet:** `{name}`\n\n📦 **GitHub** — ❌ Push failed\n```\n{err[:200]}\n```"),
            *footer(),
        )])

# 🌸 ── /syncpets ───────────────────────────────────────────────────────────────

@tree.command(name="syncpets", description="Sync all pet URLs to Railway proxy format.")
async def syncpets(interaction: discord.Interaction):
    if not await owner_check(interaction): return
    await interaction.response.defer(thinking=True)

    try:
        data, sha = await fetch_thumbnails()
    except Exception as e:
        await send_v2(interaction, [container(
            txt("## 🌩️ GitHub Error"),
            sep(),
            txt(f"💾 **Operation:** Sync Pets\n\n⛔ **Error:**\n```\n{e}\n```"),
            *footer(),
        )])
        return

    to_convert = {}
    to_refetch = {}

    for name, url in data.items():
        if is_railway(url):
            continue
        if extract_wikia_url(url):
            to_convert[name] = url
        else:
            to_refetch[name] = url

    needs_sync = {**to_convert, **to_refetch}

    if not needs_sync:
        await send_v2(interaction, [container(
            txt("## ✅ Already Fully Synced"),
            sep(),
            txt(
                f"🐾 **Total Pets:** {len(data)}\n\n"
                f"🚂 All URLs are already on Railway!\n\n"
                f"Nothing to sync."
            ),
            *footer(),
        )])
        return

    preview_names = sorted(needs_sync.keys())[:10]
    preview_lines = "\n".join(
        f"• `{n}`{' *(re-fetch from wiki)*' if n in to_refetch else ''}"
        for n in preview_names
    )
    more_note    = f"\n*...And {len(needs_sync) - 10} more*" if len(needs_sync) > 10 else ""
    refetch_note = (
        f"\n\n⚠️ **{len(to_refetch)} pet(s) with non-wikia URLs will be re-fetched from the wiki.**"
        if to_refetch else ""
    )

    wh_url  = webhook_url(interaction)
    payload = {
        "flags": FLAGS_V2,
        "components": [
            container(
                txt("## 🔄 Sync Pets To Railway"),
                sep(),
                txt(
                    f"🐾 **Total Pets:** {len(data)}\n"
                    f"⚠️ **Found {len(needs_sync)} pet(s) not on Railway:**\n\n"
                    f"{preview_lines}{more_note}{refetch_note}\n\n"
                    f"Convert all to Railway proxy?"
                ),
                *footer(),
            ),
            action_row(
                button("✅ Yes — Sync Now", "syncpets_yes", style=3),
                button("❌ No — Cancel",    "syncpets_no",  style=4),
            ),
        ],
    }
    async with aiohttp.ClientSession() as s:
        async with s.post(wh_url, json=payload) as r:
            if r.status not in (200, 204):
                raise Exception(f"Discord {r.status}: {(await r.text())[:200]}")

    bot._syncpets_pending           = getattr(bot, "_syncpets_pending", {})
    bot._syncpets_pending["latest"] = {"data": data, "sha": sha, "to_convert": to_convert, "to_refetch": to_refetch}

# 🌸 ── Button Handlers ─────────────────────────────────────────────────────────

def progress_bar(done: int, total: int, width: int = 20) -> str:
    pct    = done / total if total else 1
    filled = int(pct * width)
    return f"`[{'█' * filled}{'░' * (width - filled)}]` {done}/{total} ({int(pct * 100)}%)"

@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type != discord.InteractionType.component:
        return

    custom_id = interaction.data.get("custom_id", "")
    wh_url    = webhook_url(interaction)
    orig_url  = f"{wh_url}/messages/@original"

    async def patch_orig(components: list[dict]):
        async with aiohttp.ClientSession() as s:
            await s.patch(orig_url, json={"flags": FLAGS_V2, "components": components})

    # 🌸 Steal — Yes / No confirm (change roblox username for a Discord ID)

    if custom_id.startswith("steal_confirm_yes:") or custom_id.startswith("steal_confirm_no:"):
        did    = custom_id.split(":")[1]
        action = "yes" if custom_id.startswith("steal_confirm_yes") else "no"

        await interaction.response.defer()

        pending = getattr(bot, "_pending_steal", {}).get(did)

        if action == "no" or not pending:
            async with aiohttp.ClientSession() as s:
                await s.patch(orig_url, json={"flags": FLAGS_V2_EPH, "components": [container(
                    txt("## ❌ Cancelled"),
                    sep(),
                    txt("No changes were made. Current registration is kept."),
                    *footer(),
                )]})
        else:
            key        = pending["key"]
            roblox_str = pending["roblox_user"]

            # Remove old reverse entry
            old_roblox = discord_map.get(did)
            if old_roblox:
                user_map.pop(old_roblox, None)

            user_map[key]    = did
            discord_map[did] = key
            _save_data()
            getattr(bot, "_pending_steal", {}).pop(did, None)

            async with aiohttp.ClientSession() as s:
                await s.patch(orig_url, json={"flags": FLAGS_V2_EPH, "components": [container(
                    txt("## ✅ Registration Updated"),
                    sep(),
                    txt(
                        f"🎮 **New Roblox:** `{roblox_str}`\n"
                        f"🆔 **Discord:** <@{did}>\n\n"
                        f"🔄 Username successfully changed."
                    ),
                    *footer(),
                )]})
        return

    # 🌸 Mypets — Prev / Next pagination

    if custom_id.startswith("mypets_prev:") or custom_id.startswith("mypets_next:"):
        parts      = custom_id.split(":")
        action     = parts[0]          # mypets_prev or mypets_next
        discord_id = parts[1]
        cur_page   = int(parts[2])
        new_page   = cur_page - 1 if action == "mypets_prev" else cur_page + 1

        await interaction.response.defer()

        cache    = getattr(bot, "_mypets_pages", {}).get(discord_id)
        logs     = cache["logs"] if isinstance(cache, dict) else cache or []
        username = cache.get("username", "") if isinstance(cache, dict) else ""
        if not logs:
            await interaction.followup.send("⚠️ Session expired — please run `/mypets` again.", ephemeral=True)
            return

        components = build_mypets_page(logs, new_page, discord_id, username)
        async with aiohttp.ClientSession() as s:
            await s.patch(orig_url, json={"flags": FLAGS_V2_EPH, "components": components})
        return

    # 🌸 Fetchpet — Overwrite Yes

    if custom_id.startswith("overwrite_yes:"):
        pet_name = custom_id[len("overwrite_yes:"):]
        info     = getattr(bot, "_fetchpet_pending", {}).pop(pet_name, None)
        if not info:
            await interaction.response.send_message("⚠️ Session expired.", ephemeral=True)
            return
        await interaction.response.defer()

        railway_url = info["railway_url"]
        data        = info["data"]
        sha         = info["sha"]
        old_url     = data.get(pet_name, "")
        short_url   = shorten(railway_url)

        try:
            data[pet_name] = railway_url
            await push_thumbnails(data, sha, f"[KW] Auto-Fetch Updated: {pet_name}")
            ok = True
        except Exception as e:
            ok  = False
            err = str(e)

        if ok:
            extra = f"\n\n🔁 **Previous URL**\n```\n{shorten(old_url, 200)}\n```" if old_url else ""
            await patch_orig([container(
                txt("## 🌐 Pet Image Updated Successfully"),
                sep(),
                section(f"🐾 **{pet_name}**\n\n🚂 **Railway URL**\n```\n{short_url}\n```{extra}", railway_url),
                sep(),
                txt("📦 **GitHub** — ✅ Pushed & sorted"),
                *footer(),
            )])
        else:
            await patch_orig([container(
                txt("## 💥 Failed To Save Pet"),
                sep(),
                txt(f"🐾 **Pet:** `{pet_name}`\n\n📦 **GitHub** — ❌ Push failed\n```\n{err[:200]}\n```"),
                *footer(),
            )])

    # 🌸 Fetchpet — Overwrite No

    elif custom_id.startswith("overwrite_no:"):
        pet_name = custom_id[len("overwrite_no:"):]
        info     = getattr(bot, "_fetchpet_pending", {}).pop(pet_name, None)
        exist    = info["data"].get(pet_name, "") if info else ""
        await interaction.response.defer()
        await patch_orig([container(
            txt("## 🚫 Overwrite Cancelled"),
            sep(),
            section(
                f"🐾 **{pet_name}**\n\n🔗 **Kept existing URL**\n```\n{shorten(exist)}\n```",
                exist
            ) if exist else txt(f"🐾 **{pet_name}** — Kept existing entry."),
            *footer(),
        )])

    # 🌸 Syncpets — Yes

    elif custom_id == "syncpets_yes":
        pending = getattr(bot, "_syncpets_pending", {}).pop("latest", None)
        if not pending:
            await interaction.response.send_message("⚠️ Session expired.", ephemeral=True)
            return
        await interaction.response.defer()

        data       = pending["data"]
        sha        = pending["sha"]
        to_convert = pending["to_convert"]
        to_refetch = pending["to_refetch"]
        total      = len(to_convert) + len(to_refetch)
        done       = 0

        converted_list = []
        failed_list    = []

        async def update_progress(current: str):
            bar = progress_bar(done, total)
            await patch_orig([container(
                txt("## 🔄 Syncing To Railway..."),
                sep(),
                txt(f"⏳ **Progress:** {bar}\n\n🐾 **Processing:** `{current}`"),
                *footer(),
            )])

        for cname, old_url in to_convert.items():
            await update_progress(cname)
            try:
                data[cname] = convert_to_railway(old_url)
                converted_list.append(cname)
            except Exception as ce:
                failed_list.append(f"{cname}: {ce}")
            done += 1

        for cname in to_refetch:
            await update_progress(cname)
            try:
                wikia_url, _ = await scrape_fandom_image(cname)
                if wikia_url:
                    data[cname] = convert_to_railway(wikia_url)
                    converted_list.append(cname)
                else:
                    failed_list.append(f"{cname}: Wiki image not found")
            except Exception as ce:
                failed_list.append(f"{cname}: {ce}")
            done += 1

        try:
            await push_thumbnails(data, sha, f"[KW] SyncPets: Converted {len(converted_list)} URLs to Railway")
            push_ok  = True
            push_err = ""
        except Exception as pe:
            push_ok  = False
            push_err = str(pe)

        if push_ok:
            preview  = "\n".join(f"• `{n}`" for n in sorted(converted_list)[:20])
            more     = f"\n*...And {len(converted_list) - 20} more*" if len(converted_list) > 20 else ""
            fail_txt = (
                f"\n\n⚠️ **Failed ({len(failed_list)}):**\n" + "\n".join(f"• {x}" for x in failed_list[:5])
                if failed_list else ""
            )
            await patch_orig([container(
                txt("## 🚂 Sync Complete!"),
                sep(),
                txt(
                    f"✅ **Converted {len(converted_list)} pet(s) to Railway:**\n\n"
                    f"{preview}{more}{fail_txt}\n\n"
                    f"📦 **GitHub** — ✅ Pushed & sorted"
                ),
                *footer(),
            )])
        else:
            await patch_orig([container(
                txt("## 💥 Sync Failed"),
                sep(),
                txt(f"📦 **GitHub push failed:**\n```\n{push_err[:300]}\n```"),
                *footer(),
            )])

    # 🌸 Syncpets — No

    elif custom_id == "syncpets_no":
        getattr(bot, "_syncpets_pending", {}).pop("latest", None)
        await interaction.response.defer()
        await patch_orig([container(
            txt("## 🚫 Sync Cancelled"),
            sep(),
            txt("No changes were made to GitHub."),
            *footer(),
        )])

# 🌸 ── /steal ─────────────────────────────────────────────────────────────────
# Chỉ đăng ký mapping Roblox username → Discord ID
# Khi Lua script gửi thông báo steal, bot sẽ tra cứu mapping này để tag đúng users

@tree.command(name="steal", description="Register a Roblox username and Discord ID for a stealer.")
@discord.app_commands.describe(
    roblox_user = "Roblox username of the stealer",
    discord_id  = "Discord ID (numbers only) of the stealer",
)
async def steal_cmd(
    interaction: discord.Interaction,
    roblox_user: str,
    discord_id:  str,
):
    if not await owner_check(interaction): return
    await interaction.response.defer(thinking=True, ephemeral=True)

    if not discord_id.strip().isdigit():
        await send_v2_eph(interaction, [container(
            txt("## ❌ Invalid Discord ID"),
            sep(),
            txt(f"Discord ID must be numbers only.\n**You entered:** `{discord_id}`"),
            *footer(),
        )])
        return

    key = roblox_user.strip().lower()
    did = discord_id.strip()

    roblox_already_linked = key in user_map        # this roblox name is registered
    discord_already_has   = did in discord_map     # this discord id already has a roblox
    same_roblox_same_did  = roblox_already_linked and user_map[key] == did
    same_did_diff_roblox  = discord_already_has and discord_map[did] != key

    wh_url = webhook_url(interaction)

    # ── Case 1: exact same pair already registered ────────────────────────────
    if same_roblox_same_did:
        await send_v2_eph(interaction, [container(
            txt("## ✅ Already Registered"),
            sep(),
            txt(
                f"🎮 **Roblox:** `{roblox_user.strip()}`\n"
                f"🆔 **Discord:** <@{did}>\n\n"
                f"This mapping is already active. No changes made."
            ),
            *footer(),
        )])
        return

    # ── Case 2: Discord ID already linked to a DIFFERENT Roblox username ─────
    if same_did_diff_roblox:
        old_roblox = discord_map[did]

        # Store pending change so button handler can apply it
        if not hasattr(bot, "_pending_steal"):
            bot._pending_steal = {}
        bot._pending_steal[did] = {"key": key, "roblox_user": roblox_user.strip(), "did": did}

        confirm_components = [container(
            txt("## ⚠️ Discord Already Registered"),
            sep(),
            txt(
                f"<@{did}> is already linked to `{old_roblox}`\n\n"
                f"Do you want to change it to `{roblox_user.strip()}`?"
            ),
            sep(),
            {
                "type": 1,
                "components": [
                    {
                        "type": 2, "style": 3,
                        "label": "✅  Yes, change it",
                        "custom_id": f"steal_confirm_yes:{did}",
                    },
                    {
                        "type": 2, "style": 4,
                        "label": "❌  No, keep current",
                        "custom_id": f"steal_confirm_no:{did}",
                    },
                ],
            },
            *footer(),
        )]

        async with aiohttp.ClientSession() as s:
            await s.post(wh_url, json={"flags": FLAGS_V2_EPH, "components": confirm_components})
        return

    # ── Case 3: fresh registration or roblox-key change ──────────────────────
    # Remove old reverse entry if roblox key was previously mapped to another discord
    if roblox_already_linked:
        old_did = user_map[key]
        discord_map.pop(old_did, None)

    user_map[key]    = did
    discord_map[did] = key
    _save_data()

    status = "🔄 **Updated** — Roblox username changed." if roblox_already_linked else "✅ **Newly registered**"

    await send_v2_eph(interaction, [container(
        txt("## 👤 Stealer Registered"),
        sep(),
        txt(
            f"🎮 **Roblox:** `{roblox_user.strip()}`\n"
            f"🆔 **Discord:** <@{did}>\n\n"
            f"{status}"
        ),
        *footer(),
    )])

# 🌸 ── /mypets ───────────────────────────────────────────────────────────────
# Per-user paginated steal history, style like the screenshot
# Pages stored in bot._mypets_pages keyed by user_id

PAGE_SIZE = 5

def _parse_value(val: str) -> float:
    """Parse pet value string like '$1.4B/s' into a float."""
    try:
        v = val.replace("$","").replace(",","").strip()
        for suffix, exp in [("B/s",1e9),("M/s",1e6),("K/s",1e3),("B",1e9),("M",1e6),("K",1e3)]:
            if v.endswith(suffix):
                return float(v[:-len(suffix)]) * exp
        return float(v)
    except Exception:
        return 0.0

def _fmt_value(n: float) -> str:
    """Format float back to compact string like 1.4B."""
    if n >= 1e9: return f"{n/1e9:.2f}B".rstrip("0").rstrip(".")
    if n >= 1e6: return f"{n/1e6:.2f}M".rstrip("0").rstrip(".")
    if n >= 1e3: return f"{n/1e3:.2f}K".rstrip("0").rstrip(".")
    return str(int(n))

PINK = 16758725  # 0xFFB7C5 sakura pink

def build_mypets_page(logs: list[dict], page: int, discord_id: str, username: str = "") -> list[dict]:
    """Build Components V2 for one page of /mypets."""
    total_pages  = max(1, -(-len(logs) // PAGE_SIZE))  # ceil div
    start        = page * PAGE_SIZE
    chunk        = logs[start:start + PAGE_SIZE]
    total_steals = len(logs)
    total_val    = sum(_parse_value(e["value"]) for e in logs if e.get("value"))
    val_str      = _fmt_value(total_val)

    display_name = f"@{username}" if username else f"<@{discord_id}>"

    # ── Header text ──────────────────────────────────────────────────────────
    header_text = (
        f"**Steal Profile**\n"
        f"{display_name}\n"
        f"Total Steals: {total_steals}  ·  Total Value: {val_str}"
    )

    # ── Pet rows ─────────────────────────────────────────────────────────────
    components: list[dict] = [
        {"type": 10, "content": header_text},
        {"type": 14, "divider": True, "spacing": 1},
    ]

    for i, e in enumerate(chunk):
        pet_block = (
            f"### {e['pet']}\n"
            f"Generation: {e['value']}\n"
            f"-# <t:{e['ts']}:R>"
        )
        components.append({
            "type": 9,
            "components": [{"type": 10, "content": pet_block}],
            "accessory": {
                "type":    11,
                "media":   {"url": pet_img(e["pet"]), "loading_state": 2},
                "spoiler": False,
            },
        })
        if i < len(chunk) - 1:
            components.append({"type": 14, "divider": True, "spacing": 1})

    components.append({"type": 14, "divider": True, "spacing": 1})
    components.append({"type": 10, "content": make_footer()})

    container_block = {"type": 17, "accent_color": PINK, "components": components}

    # ── Prev / Next buttons ───────────────────────────────────────────────────
    prev_btn = {
        "type": 2, "style": 2,
        "label": "◀  Previous",
        "custom_id": f"mypets_prev:{discord_id}:{page}",
        "disabled": page == 0,
    }
    next_btn = {
        "type": 2, "style": 2,
        "label": "Next  ▶",
        "custom_id": f"mypets_next:{discord_id}:{page}:{total_pages}",
        "disabled": page >= total_pages - 1,
    }
    btn_row = {"type": 1, "components": [prev_btn, next_btn]}

    return [container_block, btn_row]


@tree.command(name="mypets", description="View your stolen pets with pagination.")
async def mypets_cmd(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True, ephemeral=True)

    discord_id = str(interaction.user.id)

    # Find this user's logs
    logs = [e for e in steal_log if e.get("discord_id") == discord_id]

    if not logs:
        wh_url = webhook_url(interaction)
        async with aiohttp.ClientSession() as s:
            await s.post(wh_url, json={
                "flags": FLAGS_V2_EPH,
                "components": [container(
                    txt("## 📋 No Steals Found"),
                    sep(),
                    txt(
                        f"No stolen pets recorded for <@{discord_id}> yet.\n"
                        "Make sure your Roblox username is registered with `/steal`."
                    ),
                    *footer(),
                )],
            })
        return

    # Cache logs + username for button navigation
    if not hasattr(bot, "_mypets_pages"):
        bot._mypets_pages = {}
    username = interaction.user.display_name
    bot._mypets_pages[discord_id] = {"logs": logs, "username": username}

    components = build_mypets_page(logs, 0, discord_id, username)
    wh_url = webhook_url(interaction)
    async with aiohttp.ClientSession() as s:
        await s.post(wh_url, json={"flags": FLAGS_V2_EPH, "components": components})

# 🌸 ── /stealclear ─────────────────────────────────────────────────────────────

@tree.command(name="stealclear", description="Clear all steal history for this session.")
async def stealclear_cmd(interaction: discord.Interaction):
    if not await owner_check(interaction): return
    count = len(steal_log)
    steal_log.clear()
    _save_data()
    await interaction.response.send_message(
        f"🗑️ Cleared `{count}` steal records.", ephemeral=True
    )

# 🌸 ── /stealusers ─────────────────────────────────────────────────────────────

@tree.command(name="stealusers", description="View all registered Roblox → Discord mappings.")
async def stealusers_cmd(interaction: discord.Interaction):
    if not await owner_check(interaction): return
    await interaction.response.defer(thinking=True, ephemeral=True)

    if not user_map:
        await send_v2_eph(interaction, [container(
            txt("## 👥 No Users Registered"),
            sep(),
            txt("No one registered yet.\nUse `/steal` to link a Roblox username to a Discord ID."),
            *footer(),
        )])
        return

    lines = "\n".join(
        f"• `{rblx}` → <@{did}> (`{did}`)"
        for rblx, did in sorted(user_map.items())
    )
    await send_v2_eph(interaction, [container(
        txt("## 👥 Registered Stealers"),
        sep(),
        txt(f"📋 **Total:** `{len(user_map)}` users\n\n{lines}"),
        *footer(),
    )])

# 🌸 ── HTTP endpoint nhận thông báo từ Lua script ─────────────────────────────
# Bot expose một endpoint đơn giản để Lua gọi tới, bot tự gửi Components V2

async def handle_steal_notify(request):
    """POST /steal-notify  body: { secret, roblox_user, pet, value, mutation }"""
    try:
        data       = await request.json()
        secret     = data.get("secret", "")
        API_SECRET = os.environ.get("STEAL_SECRET", "kaiwaifu-secret")

        if secret != API_SECRET:
            from aiohttp.web import Response
            return Response(status=401, text="Unauthorized")

        roblox_user = data.get("roblox_user", "Unknown")
        pet_name    = data.get("pet", "Unknown")
        value       = data.get("value", "???")
        mutation    = data.get("mutation", "None")
        ts          = int(time.time())
        og          = is_og(pet_name)
        # Use img_url sent by Lua (already resolved from GitHub JSON cache)
        # Fall back to bot's own cache, then static URL
        img_url     = data.get("img_url") or pet_img(pet_name)
        color       = 16753920 if og else 3092790

        # Look up Discord ID from user_map
        discord_id  = user_map.get(roblox_user.lower())
        stolen_by   = f"<@{discord_id}>" if discord_id else f"@{roblox_user}"

        # Log the steal entry
        steal_log.append({
            "pet":         pet_name,
            "value":       value,
            "mutation":    mutation,
            "roblox_user": roblox_user,
            "discord_id":  discord_id or "",
            "ts":          ts,
            "og":          og,
        })
        _save_data()

        channel_id = int(STEAL_CHANNEL)
        if not channel_id:
            from aiohttp.web import Response
            return Response(status=200, text="No channel configured")

        payload = {
            "flags": FLAGS_V2,
            "components": [
                {
                    "type": 17,
                    "accent_color": PINK,
                    "components": [
                        # Title
                        {"type": 10, "content": "# 🌸 Kawaiifu Notifier | Steals 🌸"},
                        {"type": 14, "divider": True, "spacing": 1},
                        # Pet row with thumbnail
                        {
                            "type": 9,
                            "components": [{
                                "type":    10,
                                "content": (
                                    f"### 🪨 {pet_name}  {value}\n"
                                    f"Stolen by: {stolen_by}"
                                ),
                            }],
                            "accessory": {
                                "type":    11,
                                "media":   {"url": img_url, "loading_state": 2},
                                "spoiler": False,
                            },
                        },
                        {"type": 14, "divider": True, "spacing": 1},
                        {"type": 10, "content": f"-# Steal Detected | <t:{ts}:F>"},
                        {"type": 14, "divider": True, "spacing": 1},
                        {"type": 10, "content": make_footer()},
                    ],
                }
            ],
        }

        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"https://discord.com/api/v10/channels/{channel_id}/messages",
                json=payload,
                headers={
                    "Authorization": f"Bot {BOT_TOKEN}",
                    "Content-Type":  "application/json",
                },
            ) as r:
                from aiohttp.web import Response
                return Response(status=r.status, text=await r.text())

    except Exception as e:
        from aiohttp.web import Response
        return Response(status=500, text=str(e))

# 🌸 ── !sync ───────────────────────────────────────────────────────────────────

@bot.command(name="sync")
async def sync_cmd(ctx: commands.Context):
    if ctx.author.id != OWNER_ID:
        await ctx.send("🚫 **Access Denied.**")
        return
    await tree.sync()
    await ctx.send(f"✅ **Slash commands synced!** `{len(tree.get_commands())}` commands registered.")

# 🌸 ── on_ready ────────────────────────────────────────────────────────────────

@bot.event
async def on_ready():
    await tree.sync()
    print(f"[KW] 🌸 Logged in as: {bot.user}")
    print(f"[KW] ✅ Slash commands synced!")

    # Start HTTP server to receive steal notifications from Lua script
    from aiohttp import web as aio_web

    app = aio_web.Application()
    app.router.add_post("/steal-notify", handle_steal_notify)

    port   = int(os.environ.get("PORT", 10000))
    runner = aio_web.AppRunner(app)
    await runner.setup()
    site   = aio_web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"[KW] 🌐 HTTP server running on port {port}")
    await refresh_thumb_cache()

# 🌸 ── Run ─────────────────────────────────────────────────────────────────────

bot.run(BOT_TOKEN)
