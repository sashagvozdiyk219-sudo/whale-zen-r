from __future__ import annotations

import os
import json
import time
import asyncio
import io
from pathlib import Path
from datetime import datetime, timedelta, timezone

import disnake
from disnake.ext import commands
import aiohttp
from PIL import Image, ImageDraw, ImageFont, ImageOps

# FIX для asyncio петель
try:
    asyncio.get_running_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

# =========================================================
# CONFIGURATION & CONSTANTS
# =========================================================
TOKEN = os.getenv("TOKEN") or os.getenv("DISCORD_TOKEN", "").strip()
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN / TOKEN не заданий в переменной окружения!")

GUILD_ID = 1428840740607496332

# Каналы логов
MESSAGE_LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", "1471502498538979410"))
BAN_LOG_CHANNEL_ID = 1430109571317235813
MUTE_LOG_CHANNEL_ID = 1477964449355665479
WARN_LOG_CHANNEL_ID = 1481819684125806673

# Каналы и панели
COMPLAINTS_CHANNEL_ID = 1463712939692527710
ROLES_DASHBOARD_CHANNEL_ID = 1474940159740088492
ROLE_PANEL_CHANNEL_ID = 1463680824325967938
ROLE_PANEL_MESSAGE_ID = 1487929795667824751
DASHBOARD_MESSAGE_ID = 1488292186759106581

MUTED_ROLE_ID = 1498451422939840825
BLOCK_ROLE_ID = 1463693317047844956
AUTO_ROLE_ID = 1443413500016853174

MUTE_ROLE_IDS = [1463676866857664663, 1429300139930947805, 1463733343689375927, 1429300518920126514, 1429301055774134404]
BAN_ROLE_IDS = [1429300139930947805, 1463676866857664663]
WARN_ROLE_IDS = [1429300139930947805, 1463676866857664663]
PROTECTED_ROLE_IDS = [1463676866857664663, 1429301055774134404, 1463661840083980288, 1457909630528262185]

OWNER_ROLE_ID = 1429301055774134404  
HRN_ROLE_ID = 1429300518920126514
MANAGER_ROLE_ID = 1463676866857664663
HEAD_MODERATOR_ROLE_ID = 1477803900013773001
MODERATOR_ROLE_ID = 1429300139930947805
EVENTER_ROLE_ID = 1463733343689375927

DASHBOARD_ROLE_IDS = [OWNER_ROLE_ID, HRN_ROLE_ID, MANAGER_ROLE_ID, HEAD_MODERATOR_ROLE_ID, MODERATOR_ROLE_ID, EVENTER_ROLE_ID]
COMPLAINT_PING_ROLE_IDS = [MODERATOR_ROLE_ID]
STAFF_ACTION_ROLE_IDS = DASHBOARD_ROLE_IDS

THREAD_AUTO_ARCHIVE_MINUTES = 4320
DASHBOARD_REFRESH_SECONDS = 43200

IGNORED_CHANNELS = {
    1430014338567241829, 1463704587470110761, 1443140223285334067, 1430014501079744534,
    1462057794147717335, 1463957541976539293, 1457828760937037824, 1457534568365035584,
    1463322698263302448, 1470202574270497059, 1475284171105632437, 1430109571317235813,
    1471502498538979410, 1459959016288686232, 1477964449355665479, 1464361340637413376,
    1481819684125806673,
}

BAD_WORDS = ["!г¡л"]

REACTION_ROLE_MAP = {
    1485116638578872422: 1460718308788535328, # Сповіщення про Івенти
    1431835098424279151: 1463646838241624186, # SFW / Мінор
    1429286343510458388: 1457534795532996628, # NSFW
    1487154187770007623: 1470140921218859235, # Furry gay NSFW
}

REACTION_ROLE_TEXT = {
    1485116638578872422: "Сповіщення про Івенти",
    1431835098424279151: "SFW",
    1429286343510458388: "NSFW",
    1487154187770007623: "Furry gay NSFW",
}

WELCOME_TEXTS = {
    "uk": "Привіт, {mention}! Тобі точно сподобається у **Whale Zen**. Ми створили затишний куточок без токсичності для фанатів аніме та ігор. Заходь ділитися контентом, шукати однодумців та просто спілкуватися про своє. Чекаємо саме на тебе!",
}

# BOT INITIALIZATION
intents = disnake.Intents.all()
bot = commands.InteractionBot(
    intents=intents,
    test_guilds=[GUILD_ID]
)

# STATE MANAGEMENT
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

WARNS_FILE = DATA_DIR / "warns.json"
TEMP_BANS_FILE = DATA_DIR / "temp_bans.json"
TEMP_MUTES_FILE = DATA_DIR / "temp_mutes.json"
STATE_FILE = Path("bot_state.json")
WELCOME_CONFIG_FILE = "config_welcome.json"
PROFILE_DATA_FILE = "users_profile.json"

badword_tracker: dict[int, int] = {}
temp_bans: dict[int, dict] = {}
temp_mutes: dict[int, dict] = {}
voice_connected_users: dict[int, float] = {}
MESSAGE_CACHE: dict[int, dict] = {}
_bg_started = False

def _load_json(path: Path, default):
    if not path.exists(): return default
    try:
        with path.open("r", encoding="utf-8") as f: return json.load(f)
    except Exception: return default

def _save_json(path: Path, data):
    try:
        with path.open("w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e: print(f"[DATA] save {path.name} failed: {type(e).__name__}: {e}")

def load_state():
    global badword_tracker, temp_bans, temp_mutes
    badword_tracker = {int(k): int(v) for k, v in _load_json(WARNS_FILE, {}).items()}
    temp_bans = {int(k): v for k, v in _load_json(TEMP_BANS_FILE, {}).items()}
    temp_mutes = {int(k): v for k, v in _load_json(TEMP_MUTES_FILE, {}).items()}

    if not STATE_FILE.exists(): return {"cases": {}, "dashboards": {}, "role_panel": {}}
    try: return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception: return {"cases": {}, "dashboards": {}, "role_panel": {}}

def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")

STATE = load_state()

def save_warns(): _save_json(WARNS_FILE, {str(k): v for k, v in badword_tracker.items()})
def save_temp_bans(): _save_json(TEMP_BANS_FILE, {str(k): v for k, v in temp_bans.items()})
def save_temp_mutes(): _save_json(TEMP_MUTES_FILE, {str(k): v for k, v in temp_mutes.items()})

def load_welcome_config():
    if not os.path.exists(WELCOME_CONFIG_FILE): return {}
    with open(WELCOME_CONFIG_FILE, "r", encoding="utf-8") as f: return json.load(f)

def load_profile_data():
    if not os.path.exists(PROFILE_DATA_FILE): data = {}
    else:
        with open(PROFILE_DATA_FILE, "r", encoding="utf-8") as f:
            try: data = json.load(f)
            except json.JSONDecodeError: data = {}
    return data

def save_profile_data(data):
    with open(PROFILE_DATA_FILE, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=4)

# UTILITIES
def now_utc() -> datetime: return datetime.now(timezone.utc)
def utc_ts() -> float: return time.time()
def fmt_until_from_ts(ts: float) -> str: return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%d.%m.%Y %H:%M UTC")

def is_admin(member: disnake.Member) -> bool:
    try: return bool(member.guild_permissions.administrator) or member.id == member.guild.owner_id
    except Exception: return False

def has_role(member: disnake.Member, role_id: int) -> bool:
    return any(r.id == role_id for r in getattr(member, "roles", []))

def has_any_role(member: disnake.Member, role_ids: list[int]) -> bool:
    return any(role.id in role_ids for role in getattr(member, "roles", []))

def is_staff(member: disnake.Member) -> bool: return has_any_role(member, STAFF_ACTION_ROLE_IDS)
def can_mute(member: disnake.Member) -> bool: return is_admin(member) or has_any_role(member, MUTE_ROLE_IDS)
def can_ban(member: disnake.Member) -> bool: return is_admin(member) or has_any_role(member, BAN_ROLE_IDS)

def is_protected(target: disnake.Member) -> bool:
    if target.id == target.guild.owner_id or target.guild_permissions.administrator: return True
    return has_any_role(target, PROTECTED_ROLE_IDS)

def can_punish(actor: disnake.Member, target: disnake.Member, guild: disnake.Guild) -> bool:
    if actor.id == target.id or is_protected(target): return False
    if not is_admin(actor) and target.top_role >= actor.top_role: return False
    me = guild.me or (guild.get_member(bot.user.id) if bot.user else None)
    if me and target.top_role >= me.top_role: return False
    return True

def is_ignored_channel(channel: disnake.abc.GuildChannel | disnake.Thread | None) -> bool:
    if channel is None: return False
    channel_id = getattr(channel, "id", None)
    if channel_id in IGNORED_CHANNELS: return True
    if isinstance(channel, disnake.Thread) and channel.parent_id in IGNORED_CHANNELS: return True
    return False

def _clip(text: str | None, limit: int = 1800) -> str:
    if not text: return ""
    text = text.strip()
    return text if len(text) <= limit else text[: limit - 3] + "..."

def channel_display(channel) -> str:
    if isinstance(channel, disnake.Thread):
        parent = f" / {channel.parent.mention}" if channel.parent else ""
        return f"{channel.mention}{parent}\n`{channel.id}`"
    return f"{getattr(channel, 'mention', str(channel))}\n`{getattr(channel, 'id', 'unknown')}`"
    # LOGGING
async def _get_text_channel(channel_id: int, guild: disnake.Guild) -> disnake.TextChannel | disnake.Thread | None:
    cached = guild.get_channel(channel_id)
    if isinstance(cached, (disnake.TextChannel, disnake.Thread)): return cached
    try:
        fetched = await bot.fetch_channel(channel_id)
        if isinstance(fetched, (disnake.TextChannel, disnake.Thread)): return fetched
    except Exception: pass
    return None

async def send_embed_to_channel(guild: disnake.Guild, channel_id: int, embed: disnake.Embed, tag: str):
    ch = await _get_text_channel(channel_id, guild)
    if not ch: return None
    try:
        me = guild.me or (guild.get_member(bot.user.id) if bot.user else None)
        if me and isinstance(ch, disnake.TextChannel):
            perms = ch.permissions_for(me)
            if not (perms.view_channel and perms.send_messages and perms.embed_links): return None
        return await ch.send(embed=embed)
    except Exception as e:
        print(f"[{tag}] send failed: {type(e).__name__}: {e}")
        return None

async def log_message_event(guild: disnake.Guild, embed: disnake.Embed): await send_embed_to_channel(guild, MESSAGE_LOG_CHANNEL_ID, embed, "MSG_LOG")
async def log_ban_event(guild: disnake.Guild, embed: disnake.Embed): return await send_embed_to_channel(guild, BAN_LOG_CHANNEL_ID, embed, "BAN_LOG")
async def log_mute_event(guild: disnake.Guild, embed: disnake.Embed): return await send_embed_to_channel(guild, MUTE_LOG_CHANNEL_ID, embed, "MUTE_LOG")
async def log_warn_event(guild: disnake.Guild, embed: disnake.Embed): return await send_embed_to_channel(guild, WARN_LOG_CHANNEL_ID, embed, "WARN_LOG")

def cache_message(message: disnake.Message):
    if not message.guild or message.author.bot: return
    MESSAGE_CACHE[message.id] = {
        "author": message.author,
        "content": message.content,
        "channel": message.channel,
        "attachments": [(a.filename, a.url) for a in message.attachments],
    }
    if len(MESSAGE_CACHE) > 5000:
        MESSAGE_CACHE.pop(next(iter(MESSAGE_CACHE)))

async def get_deleter(guild, target_id):
    try:
        async for entry in guild.audit_logs(limit=5, action=disnake.AuditLogAction.message_delete):
            if entry.target and entry.target.id == target_id:
                if (now_utc() - entry.created_at).total_seconds() < 5:
                    return entry.user
    except Exception: pass
    return None

async def log_deleted(data, guild):
    author = data.get("author")
    content = _clip(data.get("content") or "") or "*[без текста]*"
    channel = data.get("channel")
    deleter = await get_deleter(guild, author.id if author else 0)

    embed = disnake.Embed(title="🗑 Видалене повідомлення", description=content, color=disnake.Color.red(), timestamp=now_utc())
    if author: embed.add_field(name="Автор", value=f"{author.mention}\n`{author.id}`", inline=False)
    embed.add_field(name="Видалив", value=f"{deleter.mention}\n`{deleter.id}`" if deleter else "Сам користувач або невідомо", inline=False)
    if channel: embed.add_field(name="Канал", value=channel_display(channel), inline=False)
    await log_message_event(guild, embed)

async def log_edit(before_data, after: disnake.Message):
    if not after.guild or after.author.bot or is_ignored_channel(after.channel): return
    before_text = _clip(before_data.get("content") or "", 1000) or "*[без текста]*"
    after_text = _clip(after.content or "", 1000) or "*[без текста]*"
    if before_text == after_text: return

    embed = disnake.Embed(title="Відредаговане повідомлення", color=disnake.Color.orange(), timestamp=now_utc())
    embed.add_field(name="Автор", value=f"{after.author.mention}\n`{after.author.id}`", inline=False)
    embed.add_field(name="Канал", value=channel_display(after.channel), inline=False)
    embed.add_field(name="Було", value=before_text, inline=False)
    embed.add_field(name="Стало", value=after_text, inline=False)
    try: embed.add_field(name="Посилання", value=after.jump_url, inline=False)
    except Exception: pass
    await log_message_event(after.guild, embed)

# IMAGE GENERATION LOGIC
def get_safe_font(font_path, size):
    if font_path and os.path.exists(font_path):
        try: return ImageFont.truetype(font_path, size)
        except Exception: pass
    fallback_fonts = ["arial.ttf", "DejaVuSans.ttf", "Segoe UI.ttf", "Ubuntu-R.ttf"]
    for f in fallback_fonts:
        try: return ImageFont.truetype(f, size)
        except IOError: continue
    return ImageFont.load_default()

# ОБНОВЛЕННЫЙ ШАГ ОПЫТА: 150 * lvl + 100
def calculate_xp_for_next_level(level): return 100 + (level * 150)

def add_user_xp(user_id: str, amount: int):
    profiles = load_profile_data()
    if user_id not in profiles: profiles[user_id] = {"xp": 0, "level": 1}
    profiles[user_id]["xp"] += amount
    
    iterations = 0
    while iterations < 1000:
        current_xp = profiles[user_id]["xp"]
        current_lvl = profiles[user_id]["level"]
        xp_needed = calculate_xp_for_next_level(current_lvl)
        if xp_needed <= 0: break
        if current_xp >= xp_needed:
            profiles[user_id]["level"] += 1
            profiles[user_id]["xp"] = current_xp - xp_needed
            iterations += 1
        else: break
    save_profile_data(profiles)

async def generate_welcome_image(member: disnake.Member):
    config = load_welcome_config()
    base_image_path = "welcome_bg.png"
    font_path = config.get("font_path")
    avatar_url = member.display_avatar.url
    if not os.path.exists(base_image_path): return None
    try:
        background = Image.open(base_image_path).convert("RGBA")
        width, height = background.size
        async with aiohttp.ClientSession() as session:
            async with session.get(str(avatar_url)) as response:
                if response.status != 200: return None
                avatar_bytes = await response.read()
                avatar_image = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
        size = (300, 300)
        avatar_image = avatar_image.resize(size, Image.Resampling.LANCZOS)
        mask = Image.new('L', size, 0)
        ImageDraw.Draw(mask).ellipse((0, 0) + size, fill=255)
        circular_avatar = ImageOps.fit(avatar_image, mask.size, centering=(0.5, 0.5))
        circular_avatar.putalpha(mask)

        overlay = Image.new("RGBA", background.size, (255, 255, 255, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        avatar_pos = ((width - size[0]) // 2, (height - size[1]) // 2 - 40)
        overlay.paste(circular_avatar, avatar_pos, circular_avatar)

        username = f"{member.display_name}"
        font = get_safe_font(font_path, 65)
        text_bbox = overlay_draw.textbbox((0, 0), username, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_pos = ((width - text_width) // 2, avatar_pos[1] + size[1] + 25)
        overlay_draw.text((text_pos[0] + 3, text_pos[1] + 3), username, fill=(20, 20, 20, 160), font=font)
        overlay_draw.text(text_pos, username, fill=(255, 255, 255, 255), font=font)

        combined = Image.alpha_composite(background, overlay).convert("RGB")
        image_bytes = io.BytesIO()
        combined.save(image_bytes, format='PNG')
        image_bytes.seek(0)
        return disnake.File(image_bytes, filename="welcome.png")
    except Exception as e:
        print(f"❌ Error during image generation: {e}")
        return None

async def generate_profile_card(member: disnake.Member):
    config = load_welcome_config()
    base_image_path = "welcome_bg.png"
    font_path = config.get("font_path")
    avatar_url = member.display_avatar.url
    if not os.path.exists(base_image_path): return None

    profiles = load_profile_data()
    user_data = profiles.get(str(member.id), {"xp": 0, "level": 1})
    level, xp = user_data["level"], user_data["xp"]
    xp_needed = calculate_xp_for_next_level(level)

    sorted_profiles = sorted(profiles.items(), key=lambda x: (x[1]['level'], x[1]['xp']), reverse=True)
    rank = "#?"
    for index, (u_id, _) in enumerate(sorted_profiles):
        if u_id == str(member.id):
            rank = f"#{index + 1}"
            break
    try:
        background = Image.open(base_image_path).convert("RGBA")
        card_size = (950, 280)
        left, top = (background.width - card_size[0]) // 2, (background.height - card_size[1]) // 2
        background = background.crop((left, top, left + card_size[0], top + card_size[1]))

        overlay = Image.new("RGBA", card_size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        draw.rounded_rectangle((10, 10, card_size[0] - 10, card_size[1] - 10), radius=18, fill=(15, 12, 22, 180))

        async with aiohttp.ClientSession() as session:
            async with session.get(str(avatar_url)) as response:
                if response.status != 200: return None
                avatar_bytes = await response.read()
                avatar_image = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")

        av_size = (160, 160)
        avatar_image = avatar_image.resize(av_size, Image.Resampling.LANCZOS)
        mask = Image.new('L', av_size, 0)
        ImageDraw.Draw(mask).ellipse((0, 0) + av_size, fill=255)
        circular_avatar = ImageOps.fit(avatar_image, mask.size, centering=(0.5, 0.5))
        circular_avatar.putalpha(mask)

        overlay.paste(circular_avatar, (40, (card_size[1] - av_size[1]) // 2), circular_avatar)
        font_name = get_safe_font(font_path, 52)
        font_stats = get_safe_font(font_path, 32)

        draw.text((230, 45), member.display_name, fill=(255, 255, 255, 255), font=font_name)
        draw.text((230, 115), f"LVL {level}", fill=(245, 245, 245, 255), font=font_stats)
        draw.text((390, 115), f"RANK {rank}", fill=(218, 160, 255, 255), font=font_stats)

        xp_text = f"{xp} / {xp_needed} EXP"
        xp_bbox = draw.textbbox((0, 0), xp_text, font=font_stats)
        draw.text((card_size[0] - 50 - (xp_bbox[2] - xp_bbox[0]), 115), xp_text, fill=(195, 195, 195, 255), font=font_stats)

        bar_x1, bar_y1, bar_x2, bar_y2 = 230, 180, card_size[0] - 50, 210
        draw.rounded_rectangle((bar_x1, bar_y1, bar_x2, bar_y2), radius=8, fill=(45, 38, 58, 255))
        pct = min(xp / xp_needed, 1.0)
        if pct > 0:
            draw.rounded_rectangle((bar_x1, bar_y1, bar_x1 + int((bar_x2 - bar_x1) * pct), bar_y2), radius=8, fill=(150, 95, 224, 255))

        combined = Image.alpha_composite(background, overlay).convert("RGB")
        image_bytes = io.BytesIO()
        combined.save(image_bytes, format='PNG')
        image_bytes.seek(0)
        return disnake.File(image_bytes, filename="profile_card.png")
    except Exception as e:
        print(f"❌ Error generating profile card: {e}")
        return None

async def generate_leaderboard_image(guild: disnake.Guild, top_users):
    config = load_welcome_config()
    font_path = config.get("font_path")
    item_height, padding, img_width = 80, 20, 750
    img_height = padding * 2 + len(top_users) * item_height

    image = Image.new("RGBA", (img_width, img_height), (15, 12, 22, 255))
    draw = ImageDraw.Draw(image)

    font_rank = get_safe_font(font_path, 30)
    font_name = get_safe_font(font_path, 28)
    font_level = get_safe_font(font_path, 26)

    async with aiohttp.ClientSession() as session:
        for i, (user_id, data) in enumerate(top_users):
            y_offset = padding + i * item_height
            box_color = (45, 35, 65, 150) if i < 3 else (25, 22, 35, 100)
            draw.rounded_rectangle((padding, y_offset, img_width - padding, y_offset + item_height - 10), radius=10, fill=box_color)
            draw.text((40, y_offset + 18), f"#{i+1}", fill=(218, 160, 255, 255), font=font_rank)

            member = guild.get_member(int(user_id))
            name_text = member.display_name if member else f"Member {user_id}"
            avatar_url = member.display_avatar.url if member else None

            if avatar_url:
                try:
                    async with session.get(str(avatar_url)) as response:
                        if response.status == 200:
                            av_bytes = await response.read()
                            av_img = Image.open(io.BytesIO(av_bytes)).convert("RGBA").resize((50, 50), Image.Resampling.LANCZOS)
                            mask = Image.new('L', (50, 50), 0)
                            ImageDraw.Draw(mask).ellipse((0, 0, 50, 50), fill=255)
                            av_img.putalpha(mask)
                            image.paste(av_img, (110, y_offset + 10), av_img)
                except Exception:
                    draw.ellipse((110, y_offset + 10, 160, y_offset + 60), fill=(100, 100, 100, 255))
            else:
                draw.ellipse((110, y_offset + 10, 160, y_offset + 60), fill=(100, 100, 100, 255))

            draw.text((180, y_offset + 20), name_text, fill=(255, 255, 255, 255), font=font_name)
            lvl_text = f"Lvl. {data['level']}"
            lvl_bbox = draw.textbbox((0, 0), lvl_text, font=font_level)
            draw.text((img_width - 60 - (lvl_bbox[2] - lvl_bbox[0]), y_offset + 22), lvl_text, fill=(150, 95, 224, 255), font=font_level)

    image_bytes = io.BytesIO()
    image.convert("RGB").save(image_bytes, format='PNG')
    image_bytes.seek(0)
    return disnake.File(image_bytes, filename="leaderboard.png")

# UI VIEWS & MODALS
class UnbanView(disnake.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @disnake.ui.button(label="Розблокувати", style=disnake.ButtonStyle.danger, custom_id="unban_button_persistent")
    async def unban_button(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        await inter.response.defer(ephemeral=True)
        if not can_ban(inter.author) or not inter.message.embeds:
            return await inter.edit_original_message("❌ Немає доступу.")
        embed = inter.message.embeds[0]
        footer = (embed.footer.text or "").strip()
        if not footer.startswith("BAN_UID:"): return await inter.edit_original_message("❌ Не знайдено ID")
        member_id = int(footer.split("BAN_UID:")[1])
        try:
            user = await bot.fetch_user(member_id)
            await inter.guild.unban(user, reason=f"Unban by {inter.author}")
        except Exception: return await inter.edit_original_message("ℹ️ Вже розабанений.")
        temp_bans.pop(member_id, None)
        save_temp_bans()
        embed.color = disnake.Color.green()
        embed.add_field(name="✅ Розблокував", value=f"{inter.author.mention}\n`ID: {inter.author.id}`", inline=False)
        button.label, button.style, button.disabled = "Розблоковано", disnake.ButtonStyle.success, True
        await inter.message.edit(embed=embed, view=self)
        await inter.edit_original_message("✅ Розблоковано.")

class UnmuteView(disnake.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @disnake.ui.button(label="Розмутити", style=disnake.ButtonStyle.danger, custom_id="unmute_button_persistent")
    async def unmute_button(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        await inter.response.defer(ephemeral=True)
        if not can_mute(inter.author) or not inter.message.embeds:
            return await inter.edit_original_message("❌ Немає доступу.")
        embed = inter.message.embeds[0]
        footer = (embed.footer.text or "").strip()
        if not footer.startswith("MUTE_UID:"): return await inter.edit_original_message("❌ Не знайдено ID")
        member_id = int(footer.split("MUTE_UID:")[1])
        member = inter.guild.get_member(member_id)
        if not member: return await inter.edit_original_message("❌ Користувач не знайдений.")
        try:
            await member.timeout(until=None, reason=f"Unmute by {inter.author}")
        except TypeError:
            try: await member.timeout(duration=None, reason=f"Unmute by {inter.author}")
            except Exception: return await inter.edit_original_message("❌ Не вдалося розмутити.")
        except Exception: return await inter.edit_original_message("❌ Не вдалося розмутити.")

        temp_mutes.pop(member_id, None)
        save_temp_mutes()
        embed.color = disnake.Color.green()
        embed.add_field(name="✵ Розмучено", value=f"{inter.author.mention}\n`ID: {inter.author.id}`", inline=False)
        button.label, button.style, button.disabled = "Розмучено", disnake.ButtonStyle.success, True
        await inter.message.edit(embed=embed, view=self)
        await inter.edit_original_message("㊙︎ Розмучено.")

class ClearWarnView(disnake.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @disnake.ui.button(label="Скинути преди", style=disnake.ButtonStyle.danger, custom_id="clear_warns_button_persistent")
    async def clear_warns_button(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        await inter.response.defer(ephemeral=True)
        if not can_mute(inter.author) or not inter.message.embeds: return await inter.edit_original_message("❌ Нет прав.")
        embed = inter.message.embeds[0]
        footer = (embed.footer.text or "").strip()
        if not footer.startswith("WARN_UID:"): return await inter.edit_original_message("❌ ID не найден.")
        member_id = int(footer.split("WARN_UID:")[1])
        badword_tracker[member_id] = 0
        save_warns()
        embed.color = disnake.Color.green()
        embed.add_field(name="⚖︎ Скинув преди", value=f"{inter.author.mention}\n`ID: {inter.author.id}`", inline=False)
        button.label, button.style, button.disabled = "Преди скинуто", disnake.ButtonStyle.success, True
        await inter.message.edit(embed=embed, view=self)
        await inter.edit_original_message("☠︎ Преди скинуто.")

def build_embed(inter, title, fields):
    embed = disnake.Embed(title=title, color=0xfac7ff, timestamp=now_utc())
    embed.set_thumbnail(url=inter.author.display_avatar.url)
    for name, value in fields.items(): embed.add_field(name=name, value=value, inline=False)
    embed.set_footer(text=str(inter.author), icon_url=inter.author.display_avatar.url)
    return embed

def build_case_view(mid):
    view = disnake.ui.View(timeout=None)
    view.add_item(disnake.ui.Button(label="Розглядається", custom_id=f"review:{mid}", style=disnake.ButtonStyle.primary))
    view.add_item(disnake.ui.Button(label="Прийняти", custom_id=f"accept:{mid}", style=disnake.ButtonStyle.success))
    view.add_item(disnake.ui.Button(label="Відхилити", custom_id=f"reject:{mid}", style=disnake.ButtonStyle.danger))
    return view

class ComplaintModal(disnake.ui.Modal):
    def __init__(self):
        super().__init__(title="Скарга", components=[
            disnake.ui.TextInput(label="Порушник", custom_id="user"),
            disnake.ui.TextInput(label="Правило", custom_id="rule"),
            disnake.ui.TextInput(label="Час", custom_id="time"),
            disnake.ui.TextInput(label="Опис", custom_id="desc", style=disnake.TextInputStyle.paragraph),
        ])
    async def callback(self, inter):
        ch = inter.guild.get_channel(COMPLAINTS_CHANNEL_ID)
        pings = " ".join([f"<@&{r}>" for r in COMPLAINT_PING_ROLE_IDS])
        embed = build_embed(inter, "Скарга на Учасника", {
            "Порушник": self.text_values["user"], "Правило": self.text_values["rule"],
            "Час": self.text_values["time"], "Опис": self.text_values["desc"]
        })
        msg = await ch.send(content=f"🔔 **Нове звернення:** {pings}", embed=embed)
        thread = await msg.create_thread(name=f"Скарга #{msg.id}", auto_archive_duration=THREAD_AUTO_ARCHIVE_MINUTES)
        await thread.send("❦ Додайте докази тут")
        STATE["cases"][str(msg.id)] = {"status": "open", "thread": thread.id}
        save_state(STATE)
        await msg.edit(view=build_case_view(msg.id))
        await inter.response.send_message("Створено", ephemeral=True)
        # REACTION ROLE HANDLER
async def handle_reaction(payload, add: bool):
    guild = bot.get_guild(payload.guild_id)
    if not guild or payload.message_id != ROLE_PANEL_MESSAGE_ID: return
    member = guild.get_member(payload.user_id) or await guild.fetch_member(payload.user_id)
    if member.bot: return

    role_id = REACTION_ROLE_MAP.get(getattr(payload.emoji, "id", None))
    if not role_id: return
    role = guild.get_role(role_id)
    if not role: return

    try:
        if add:
            if has_role(member, BLOCK_ROLE_ID) and role_id in {1463646838241624186, 1457534795532996628, 1470140921218859235}: return
            await member.add_roles(role)
        else:
            await member.remove_roles(role)
    except Exception as e: print(f"Reaction error: {e}")

@bot.event
async def on_raw_reaction_add(payload): await handle_reaction(payload, add=True)
@bot.event
async def on_raw_reaction_remove(payload): await handle_reaction(payload, add=False)

# AUTOMOD & WARN SYSTEM
def make_ban_embed(member: disnake.Member, moderator: disnake.Member, hours: int, rule: str) -> disnake.Embed:
    ends_str = fmt_until_from_ts(utc_ts() + hours * 3600)
    embed = disnake.Embed(title="꧁⎝ 𓆩༺✧༻𓆪 ⎠꧂", color=disnake.Color.red(), timestamp=now_utc())
    embed.add_field(name="Користувач", value=f"{member.mention}\n`ID: {member.id}`", inline=False)
    embed.add_field(name="Модератор", value=f"{moderator.mention}\n`ID: {moderator.id}`", inline=False)
    embed.add_field(name="Порушене правило", value=rule, inline=False)
    embed.add_field(name="Термін блокування", value=f"{hours} год. (до {ends_str})", inline=False)
    embed.set_footer(text=f"BAN_UID:{member.id}")
    return embed

def make_mute_embed(member: disnake.Member, moderator: disnake.Member | None, minutes: int, reason: str, end_ts: float) -> disnake.Embed:
    ends_str = fmt_until_from_ts(end_ts)
    mod_text = f"{moderator.mention}\n`ID: {moderator.id}`" if moderator else "Автомод"
    embed = disnake.Embed(title="𖣘 Мут", color=disnake.Color.red(), timestamp=now_utc())
    embed.add_field(name="Користувач", value=f"{member.mention}\n`ID: {member.id}`", inline=False)
    embed.add_field(name="Модератор", value=mod_text, inline=False)
    embed.add_field(name="Причина", value=reason, inline=False)
    embed.add_field(name="Термін муту", value=f"{minutes} хв. (до {ends_str})", inline=False)
    embed.set_footer(text=f"MUTE_UID:{member.id}")
    return embed

def make_warn_embed(member: disnake.Member, moderator: disnake.Member | None, reason: str, count: int) -> disnake.Embed:
    mod_text = f"{moderator.mention}\n`ID: {moderator.id}`" if moderator else "Автомод"
    embed = disnake.Embed(title="⚠ Попередження", color=disnake.Color.orange(), timestamp=now_utc())
    embed.add_field(name="Користувач", value=f"{member.mention}\n`ID: {member.id}`", inline=False)
    embed.add_field(name="Модератор", value=mod_text, inline=False)
    embed.add_field(name="Причина", value=reason, inline=False)
    embed.add_field(name="Кількість предів", value=f"{count}/3", inline=False)
    embed.set_footer(text=f"WARN_UID:{member.id}")
    return embed

async def apply_warn(guild: disnake.Guild, member: disnake.Member, moderator: disnake.Member | None, reason: str, channel: disnake.abc.Messageable):
    if is_protected(member): return await channel.send("❌ Іgnored")
    uid = member.id
    badword_tracker[uid] = badword_tracker.get(uid, 0) + 1
    count = badword_tracker[uid]
    save_warns()

    warn_embed = make_warn_embed(member, moderator, reason, count)
    sent = await log_warn_event(guild, warn_embed)
    if sent:
        try: await sent.edit(view=ClearWarnView())
        except Exception: pass

    mod_text = moderator.mention if moderator else "Автомод"
    await channel.send(f"⚠ {member.mention} отримав пред (**{count}/3**). Модератор: {mod_text}. Причина: {reason}")

    if count >= 3:
        badword_tracker[uid] = 0
        save_warns()
        me = guild.me or (guild.get_member(bot.user.id) if bot.user else None)
        if me and member.top_role >= me.top_role: return

        end_ts = utc_ts() + 3600
        try: await member.timeout(duration=timedelta(hours=1), reason="Мут за 3/3 предів")
        except Exception as e: print(f"[AUTOMOD] Timeout failed: {e}"); return

        await channel.send(f"🔇 {member.mention} отримав мут на **1 годину** (3/3).")
        mute_embed = make_mute_embed(member, moderator, 60, reason, end_ts)
        mute_msg = await log_mute_event(guild, mute_embed)
        if mute_msg:
            try: await mute_msg.edit(view=UnmuteView())
            except Exception: pass
        temp_mutes[member.id] = {"guild_id": guild.id, "end_ts": end_ts, "log_message_id": mute_msg.id if mute_msg else None, "log_channel_id": MUTE_LOG_CHANNEL_ID}
        save_temp_mutes()

# TASKS, PANELS, AND LOOPS
async def update_member_count(guild: disnake.Guild):
    try:
        config = load_welcome_config()
        stats_channel_id = config.get("stats_channel_id")
        if not stats_channel_id: return
        channel = guild.get_channel(stats_channel_id) or await bot.fetch_channel(stats_channel_id)
        if isinstance(channel, disnake.VoiceChannel):
            new_name = f" ☄ ⁝ {guild.member_count} Member"
            if channel.name != new_name: await channel.edit(name=new_name)
    except Exception as e: print(f"❌ Error updating member counter: {e}")

# Оновлення/створення повідомлення ролей для реакцій
async def ensure_role_panel(guild):
    global ROLE_PANEL_MESSAGE_ID
    ch = guild.get_channel(ROLE_PANEL_CHANNEL_ID)
    if not ch: return
    
    lines = ["Натисни реакцію щоб отримати або зняти роль:\n"]
    for eid in REACTION_ROLE_MAP:
        emoji = bot.get_emoji(eid)
        if emoji: lines.append(f"{emoji} — {REACTION_ROLE_TEXT[eid]}")
    content_text = "\n".join(lines)

    msg = None
    try: 
        msg = await ch.fetch_message(ROLE_PANEL_MESSAGE_ID)
    except Exception:
        # Если старое сообщение не найдено — создаем новое в указанном канале
        try:
            msg = await ch.send(content=content_text)
            ROLE_PANEL_MESSAGE_ID = msg.id
            print(f"✅ Создано новое сообщение ролей с ID: {ROLE_PANEL_MESSAGE_ID}")
            for eid in REACTION_ROLE_MAP:
                emoji = bot.get_emoji(eid)
                if emoji: await msg.add_reaction(emoji)
            return
        except Exception as e:
            print(f"❌ Помилка створення повідомлення ролей: {e}")
            return

    if msg:
        await msg.edit(content=content_text)

async def ensure_dashboard(guild):
    ch = guild.get_channel(ROLES_DASHBOARD_CHANNEL_ID)
    if not ch: return
    try: msg = await ch.fetch_message(DASHBOARD_MESSAGE_ID)
    except Exception: return
    embed = disnake.Embed(title="Staff", color=0xfac7ff)
    processed = set()
    for rid in DASHBOARD_ROLE_IDS:
        role = guild.get_role(rid)
        members = role.members if role else []
        unique_staff = [m.mention for m in members if m.id not in processed and not processed.add(m.id)]
        embed.add_field(name=role.name if role else "?", value="\n".join(unique_staff) or "-", inline=False)
    await msg.edit(embed=embed)

async def dashboard_loop():
    await bot.wait_until_ready()
    while True:
        for g in bot.guilds: await ensure_dashboard(g)
        await asyncio.sleep(DASHBOARD_REFRESH_SECONDS)

async def check_temp_bans():
    await bot.wait_until_ready()
    while True:
        now = utc_ts()
        for uid, info in list(temp_bans.items()):
            if now >= float(info.get("end_ts", 0)):
                guild = bot.get_guild(info.get("guild_id"))
                if guild:
                    try:
                        bans = await guild.bans()
                        for entry in bans:
                            if entry.user.id == uid:
                                await guild.unban(entry.user, reason="Авто-розбан по таймеру")
                                auto_embed = disnake.Embed(title="⏱️ Авто-розбан", color=disnake.Color.green(), timestamp=now_utc())
                                auto_embed.add_field(name="Користувач", value=f"{entry.user}\n`ID: {entry.user.id}`", inline=False)
                                await log_ban_event(guild, auto_embed)
                                break
                    except Exception: pass
                temp_bans.pop(uid, None)
                save_temp_bans()
        await asyncio.sleep(60)

async def check_temp_mutes():
    await bot.wait_until_ready()
    while True:
        now = utc_ts()
        for uid, info in list(temp_mutes.items()):
            if now >= float(info.get("end_ts", 0)):
                guild = bot.get_guild(info.get("guild_id"))
                if guild:
                    member = guild.get_member(uid)
                    if member:
                        role = guild.get_role(MUTED_ROLE_ID)
                        if role and role in member.roles:
                            try: await member.remove_roles(role, reason="Авто-розмут")
                            except Exception: pass
                        try: await member.timeout(until=None, reason="Авто-розмут по таймеру")
                        except Exception: pass
                    auto_embed = disnake.Embed(title="⏱️ Авто-розмут", color=disnake.Color.green(), timestamp=now_utc())
                    auto_embed.add_field(name="Користувач", value=f"<@{uid}>\n`ID: {uid}`", inline=False)
                    await log_mute_event(guild, auto_embed)
                temp_mutes.pop(uid, None)
                save_temp_mutes()
        await asyncio.sleep(30)
        # GLOBAL EVENTS
@bot.event
async def on_message(message: disnake.Message):
    if message.author.bot or not message.guild: return
    if is_ignored_channel(message.channel): return

    cache_message(message)
    add_user_xp(str(message.author.id), 50)

    content_lower = (message.content or "").lower()
    if any(word in content_lower for word in BAD_WORDS):
        member = message.guild.get_member(message.author.id)
        if member:
            try: await message.delete()
            except Exception: pass
            await apply_warn(message.guild, member, None, "Нецензурні слова (автомод)", message.channel)

@bot.event
async def on_message_delete(message):
    data = MESSAGE_CACHE.pop(message.id, None)
    if data and message.guild: await log_deleted(data, message.guild)

@bot.event
async def on_raw_message_delete(payload):
    guild = bot.get_guild(payload.guild_id)
    if not guild: return
    data = MESSAGE_CACHE.pop(payload.message_id, None)
    if data: await log_deleted(data, guild)

@bot.event
async def on_message_edit(before, after):
    before_data = MESSAGE_CACHE.get(before.id, {"content": before.content})
    await log_edit(before_data, after)
    cache_message(after)

@bot.event
async def on_member_join(member: disnake.Member):
    try:
        role = member.guild.get_role(AUTO_ROLE_ID)
        if role: await member.add_roles(role)
    except Exception: pass

    await update_member_count(member.guild)
    try:
        config = load_welcome_config()
        channel_id = config.get("welcome_channel_id")
        if not channel_id: return
        channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
        img = await generate_welcome_image(member)
        final_text = f"{WELCOME_TEXTS['uk'].format(mention=member.mention)}\n\n{WELCOME_TEXTS['en'].format(mention=member.mention)}\n\n{WELCOME_TEXTS['ru'].format(mention=member.mention)}"
        if img: await channel.send(content=final_text, file=img)
        else: await channel.send(content=final_text)
    except Exception as e: print(f"❌ Error on_member_join: {e}")

@bot.event
async def on_member_remove(member: disnake.Member): await update_member_count(member.guild)

# Подсчет XP в голосовых/временных голосовых каналах
@bot.event
async def on_voice_state_update(member: disnake.Member, before: disnake.VoiceState, after: disnake.VoiceState):
    if member.bot: return
    user_id = member.id
    if after.channel is not None and before.channel is None:
        voice_connected_users[user_id] = time.time()
    elif after.channel is None and before.channel is not None:
        join_time = voice_connected_users.pop(user_id, None)
        if join_time:
            # Каждые 5 минут нахождения дают 15 XP
            intervals = int(((time.time() - join_time) / 60) / 5)
            if intervals > 0: add_user_xp(str(user_id), intervals * 75)

@bot.listen("on_button_click")
async def case_buttons(inter):
    if not is_staff(inter.author) or ":" not in inter.component.custom_id: return
    action, mid = inter.component.custom_id.split(":")
    case = STATE["cases"].get(mid)
    if not case: return
    msg = await inter.channel.fetch_message(int(mid))
    thread = bot.get_channel(case["thread"])
    embed = msg.embeds[0]
    fields = [(f.name, f.value) for f in embed.fields if f.name != "Статус"]
    embed.clear_fields()
    for name, value in fields: embed.add_field(name=name, value=value, inline=False)

    if action == "review":
        status, embed.color, view = f"🟣 Розглядається {inter.author.display_name}", 0x5865F2, build_case_view(mid)
    elif action == "accept":
        status, embed.color, view = f"🟢 Прийнято {inter.author.display_name}", 0x57F287, disnake.ui.View()
        if thread: await thread.edit(archived=True, locked=True)
    elif action == "reject":
        status, embed.color, view = f"🔴 Відхилено {inter.author.display_name}", 0xED4245, disnake.ui.View()
        if thread: await thread.edit(archived=True, locked=True)

    embed.add_field(name="Статус", value=status, inline=False)
    save_state(STATE)
    await msg.edit(embed=embed, view=view)
    await inter.response.defer()

# SLASH COMMANDS
@bot.slash_command(description="Бан користувача")
async def ban(inter: disnake.ApplicationCommandInteraction, member: disnake.Member, hours: int, правило: str = "Порушення"):
    await inter.response.defer(ephemeral=True)
    if not can_ban(inter.author) or not can_punish(inter.author, member, inter.guild): return await inter.edit_original_message("❌ Бракує прав.")
    try: await member.ban(reason=правило)
    except Exception as e: return await inter.edit_original_message(f"❌ Помилка: {e}")
    embed = make_ban_embed(member, inter.author, hours, правило)
    sent = await log_ban_event(inter.guild, embed)
    if sent:
        try: await sent.edit(view=UnbanView())
        except Exception: pass
    temp_bans[member.id] = {"guild_id": inter.guild.id, "end_ts": utc_ts() + hours * 3600, "log_message_id": sent.id if sent else None, "log_channel_id": BAN_LOG_CHANNEL_ID}
    save_temp_bans()
    await inter.edit_original_message("✅ Успішно забанено.")

@bot.slash_command(description="Замутити користувача")
async def mute(inter: disnake.ApplicationCommandInteraction, member: disnake.Member, хвилини: int = 1, причина: str = "Порушення"):
    await inter.response.defer(ephemeral=True)
    if not can_mute(inter.author) or not can_punish(inter.author, member, inter.guild): return await inter.edit_original_message("❌ Бракує прав.")
    end_ts = utc_ts() + хвилини * 60
    try: await member.timeout(duration=timedelta(minutes=хвилини), reason=причина)
    except Exception as e: return await inter.edit_original_message(f"❌ Помилка: {e}")
    embed = make_mute_embed(member, inter.author, хвилини, причина, end_ts)
    sent = await log_mute_event(inter.guild, embed)
    if sent:
        try: await sent.edit(view=UnmuteView())
        except Exception: pass
    temp_mutes[member.id] = {"guild_id": inter.guild.id, "end_ts": end_ts, "log_message_id": sent.id if sent else None, "log_channel_id": MUTE_LOG_CHANNEL_ID}
    save_temp_mutes()
    await inter.edit_original_message(f"✅ {member.mention} замучено")

@bot.slash_command(description="Видати пред користувачу (3/3 -> мут 1 год)")
async def warn(inter: disnake.ApplicationCommandInteraction, member: disnake.Member, причина: str = "Порушення"):
    await inter.response.defer(ephemeral=True)
    if not can_mute(inter.author) or not can_punish(inter.author, member, inter.guild): return await inter.edit_original_message("❌ Бракує прав.")
    await apply_warn(inter.guild, member, inter.author, причина, inter.channel)
    await inter.edit_original_message("☸ Пред видано.")

# Новая команда для снятия предпреждений/варнов
@bot.slash_command(description="Скинути попередження користувачу")
async def unwarn(inter: disnake.ApplicationCommandInteraction, member: disnake.Member, кількість: int = 1):
    await inter.response.defer(ephemeral=True)
    if not can_mute(inter.author): return await inter.edit_original_message("❌ Бракує прав.")
    
    current = badword_tracker.get(member.id, 0)
    if current == 0:
        return await inter.edit_original_message("ℹ️ У користувача немає попереджень.")
    
    new_count = max(0, current - кількість)
    badword_tracker[member.id] = new_count
    save_warns()
    
    await inter.edit_original_message(f"✅ Скинуто **{кількість}** пред(ів) для {member.mention}. Поточний рахунок: **{new_count}/3**.")

# Исправленная функция /звернення
@bot.slash_command(name="звернення", description="Створити скаргу")
async def ticket(inter: disnake.ApplicationCommandInteraction): 
    await inter.response.send_modal(ComplaintModal())

@bot.slash_command(name="user", description="Посмотреть профиль участника")
async def user_slash(inter: disnake.ApplicationCommandInteraction, member: disnake.Member = None):
    member = member or inter.author
    await inter.response.defer()
    embed = disnake.Embed(title=f"Информация о {member.display_name}", color=disnake.Color.from_rgb(150, 95, 224))
    embed.add_field(name="ID:", value=f"`{member.id}`", inline=False)
    embed.add_field(name="Имя:", value=f"{member.name}", inline=False)
    card_file = await generate_profile_card(member)
    if card_file:
        embed.set_image(url="attachment://profile_card.png")
        await inter.edit_original_message(embed=embed, file=card_file)
    else: await inter.edit_original_message(embed=embed)

@bot.slash_command(name="top", description="Посмотреть топ лидеров")
async def top_slash(inter: disnake.ApplicationCommandInteraction):
    await inter.response.defer()
    profiles = load_profile_data()
    top_10 = sorted(profiles.items(), key=lambda x: (x[1]['level'], x[1]['xp']), reverse=True)[:10]
    leaderboard_file = await generate_leaderboard_image(inter.guild, top_10)
    embed = disnake.Embed(title=f"🏆 Таблица лидеров — {inter.guild.name}", color=disnake.Color.from_rgb(218, 160, 255))
    if leaderboard_file:
        embed.set_image(url="attachment://leaderboard.png")
        await inter.edit_original_message(embed=embed, file=leaderboard_file)
    else: await inter.edit_original_message("❌ Ошибка генерации.")

# ON READY & BOT START
@bot.event
async def on_ready():
    global _bg_started
    bot.add_view(UnbanView())
    bot.add_view(UnmuteView())
    bot.add_view(ClearWarnView())

    load_state()
    try:
        synced = await bot.sync_commands()
        print(f"🔁 Synced commands: {len(synced)}")
    except Exception as e: print(f"Sync error: {e}")

    print(f"=== READY === bot={bot.user}")

    if not _bg_started:
        _bg_started = True
        asyncio.create_task(check_temp_bans())
        asyncio.create_task(check_temp_mutes())
        asyncio.create_task(dashboard_loop())

    for guild in bot.guilds:
        try:
            await update_member_count(guild)
            await ensure_role_panel(guild)
            for vc in guild.voice_channels:
                for member in getattr(vc, "members", []):
                    if not member.bot: voice_connected_users[member.id] = time.time()
        except Exception as e: print(f"Guild init error: {e}")

if __name__ == "__main__":
    bot.run(TOKEN)
