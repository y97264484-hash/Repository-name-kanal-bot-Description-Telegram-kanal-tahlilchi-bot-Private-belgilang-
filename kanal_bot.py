import asyncio
import pandas as pd
from pyrogram import Client, filters, idle
from pyrogram.types import BotCommand
from io import BytesIO
import time
import logging
from datetime import datetime

# SOZLAMALAR
API_ID       = 31819893
API_HASH     = "dcac1a0061b3ba42f9665b8d2665ffcf"
BOT_TOKEN    = "8853304831:AAEq74MmOY_CUsKHEwxMvE4i9scjWtyguLY"

COOLDOWN_SEC  = 30
DEFAULT_LIMIT = 50
ADMIN_IDS     = []

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger(__name__)

app  = Client("kanal_bot",     api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
user = Client("kanal_userbot", api_id=API_ID, api_hash=API_HASH)

user_state: dict[int, dict] = {}


def extract_target(text: str) -> tuple[str, int | None]:
    text = text.strip()
    if "t.me/c/" in text:
        parts = text.split("t.me/c/")[-1].split("?")[0].split("/")
        channel_id = f"-100{parts[0]}"
        msg_id = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
        return channel_id, msg_id
    if "t.me/" in text:
        parts = text.split("t.me/")[-1].split("?")[0].split("/")
        username = parts[0]
        msg_id = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
        return username, msg_id
    return text.lstrip("@"), None


def cooldown_remaining(user_id: int) -> int:
    last = user_state.get(user_id, {}).get("last_req", 0)
    diff = time.time() - last
    return max(0, int(COOLDOWN_SEC - diff))


def build_excel(messages: list[dict], channel_title: str) -> BytesIO:
    df = pd.DataFrame(messages)
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Xabarlar")
        ws = writer.sheets["Xabarlar"]
        col_widths = {"Sana": 20, "Xabar": 60, "Turli": 12, "Reaksiyalar": 14}
        for col, width in col_widths.items():
            if col in df.columns:
                col_letter = chr(64 + df.columns.get_loc(col) + 1)
                ws.column_dimensions[col_letter].width = width
    output.seek(0)
    return output


def _media_type(msg) -> str:
    if msg.photo:      return "🖼 Rasm"
    if msg.video:      return "🎬 Video"
    if msg.audio:      return "🎵 Audio"
    if msg.voice:      return "🎤 Ovozli"
    if msg.document:   return "📎 Fayl"
    if msg.animation:  return "🎞 GIF"
    if msg.sticker:    return "🃏 Stiker"
    if msg.video_note: return "📹 Video-xabar"
    return "✏️ Matn"


async def fetch_messages(target: str, limit: int, offset_msg_id: int | None = None) -> dict:
    result = {
        "channel_title": target,
        "texts": [],
        "media_count": 0,
        "total": 0,
    }
    try:
        channel = await user.get_chat(target)
        result["channel_title"] = getattr(channel, "title", target)
    except Exception as e:
        raise ValueError(f"Kanal topilmadi: {e}")

    kwargs = {"limit": limit}
    if offset_msg_id:
        kwargs["offset_id"] = offset_msg_id + 1

    async for msg in user.get_chat_history(target, **kwargs):
        result["total"] += 1
        if any([msg.voice, msg.video, msg.video_note, msg.audio,
                msg.document, msg.photo, msg.animation, msg.sticker]):
            result["media_count"] += 1
        text_content = msg.text or msg.caption
        if text_content:
            reactions = 0
            if msg.reactions:
                reactions = sum(r.count for r in msg.reactions.reactions)
            result["texts"].append({
                "Sana":        msg.date.strftime("%Y-%m-%d %H:%M"),
                "Xabar":       str(text_content)[:3000],
                "Turli":       _media_type(msg),
                "Reaksiyalar": reactions,
            })
    result["texts"].reverse()
    return result


@app.on_message(filters.command("start") & filters.private)
async def cmd_start(client, message):
    name = message.from_user.first_name or "Do'st"
    await message.reply(
        f"👋 Salom, **{name}**!\n\n"
        "📡 **Kanal Tahlilchi Bot**\n\n"
        "Ishlash tartibi:\n"
        "1️⃣ Public kanal: `https://t.me/kanal_nomi`\n"
        "2️⃣ Private kanal: `https://t.me/c/2152172943/119`\n"
        "3️⃣ Yoki shunchaki: `@kanal_nomi`\n\n"
        "Bot oxirgi **50 ta xabar**ni yuklab, Excel tahlil fayl yuboradi.\n\n"
        "📌 Boshqa buyruqlar: /help",
        parse_mode="markdown"
    )


@app.on_message(filters.command("help") & filters.private)
async def cmd_help(client, message):
    await message.reply(
        "ℹ️ **Yordam**\n\n"
        "**Public kanal:**\n"
        "• `https://t.me/username`\n"
        "• `https://t.me/username/42` — 42-xabardan boshlab\n"
        "• `@username` yoki `username`\n\n"
        "**Private kanal:**\n"
        "• `https://t.me/c/2152172943/119` — 119-xabardan boshlab\n\n"
        "**Buyruqlar:**\n"
        "• `/limit 100` — nechta xabar olishni belgilash (10–200)\n"
        "• `/stats` — shaxsiy statistika\n\n"
        f"⏱ So'rovlar orasidagi kutish: **{COOLDOWN_SEC} soniya**",
        parse_mode="markdown"
    )


@app.on_message(filters.command("stats") & filters.private)
async def cmd_stats(client, message):
    uid = message.from_user.id
    count = user_state.get(uid, {}).get("count", 0)
    await message.reply(f"📊 Siz jami **{count}** marta so'rov yubordingiz.", parse_mode="markdown")


@app.on_message(filters.command("limit") & filters.private)
async def cmd_limit(client, message):
    uid = message.from_user.id
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.reply("❌ Foydalanish: `/limit 100`", parse_mode="markdown")
        return
    val = max(10, min(200, int(parts[1])))
    if uid not in user_state:
        user_state[uid] = {}
    user_state[uid]["limit"] = val
    await message.reply(f"✅ Limit **{val}** ga o'rnatildi.", parse_mode="markdown")


@app.on_message(filters.text & filters.private & ~filters.command(["start", "help", "stats", "limit"]))
async def process_channel(client, message):
    uid = message.from_user.id

    wait = cooldown_remaining(uid)
    if wait > 0:
        await message.reply(f"⏳ Iltimos kuting! Keyingi so'rov **{wait}** soniyadan keyin.", parse_mode="markdown")
        return

    target, msg_id = extract_target(message.text)
    if not target or len(target) < 3:
        await message.reply("❌ Kanal manzilini to'g'ri kiriting.\nMisol: `@example_channel`", parse_mode="markdown")
        return

    limit = user_state.get(uid, {}).get("limit", DEFAULT_LIMIT)

    if uid not in user_state:
        user_state[uid] = {}
    user_state[uid]["last_req"] = time.time()
    user_state[uid]["count"] = user_state.get(uid, {}).get("count", 0) + 1

    from_note = f"(#{msg_id} xabardan boshlab)" if msg_id else ""
    wait_msg = await message.reply(
        f"⌛ **{target}** tahlil qilinmoqda... {from_note}\n"
        f"📥 Oxirgi {limit} ta xabar yuklanmoqda",
        parse_mode="markdown"
    )

    try:
        data = await fetch_messages(target, limit, offset_msg_id=msg_id)
    except ValueError as e:
        await wait_msg.edit(f"❌ {e}")
        return
    except Exception as e:
        log.exception("fetch_messages xatosi")
        await wait_msg.edit(f"❌ Kutilmagan xato: {e}")
        return

    total       = data["total"]
    text_count  = len(data["texts"])
    media_count = data["media_count"]
    title       = data["channel_title"]

    summary = (
        f"📊 **{title}** tahlili:\n\n"
        f"📨 Jami xabarlar: `{total}`\n"
        f"✏️ Matnli xabarlar: `{text_count}`\n"
        f"🎥 Media fayllar: `{media_count}`\n"
        f"📅 Vaqt: `{datetime.now().strftime('%Y-%m-%d %H:%M')}`"
    )

    if data["texts"]:
        excel = build_excel(data["texts"], title)
        await message.reply_document(
            document=excel,
            file_name=f"{target}_tahlil.xlsx",
            caption=summary,
            parse_mode="markdown"
        )
    else:
        await message.reply(summary + "\n\n⚠️ Matnli xabar topilmadi.", parse_mode="markdown")

    await wait_msg.delete()
    log.info(f"[{uid}] {target} → {total} xabar tahlil qilindi")


async def main():
    print("=" * 40)
    print("  📡  KANAL TAHLILCHI BOT  |  v2.1")
    print("=" * 40)

    await app.start()
    await app.set_bot_commands([
        BotCommand("start",  "Botni boshlash"),
        BotCommand("help",   "Yordam"),
        BotCommand("limit",  "Xabarlar sonini belgilash"),
        BotCommand("stats",  "Mening statistikam"),
    ])
    log.info("✅ Bot ishga tushdi")

    await user.start()
    log.info("✅ Userbot ishga tushdi")
    log.info("🎉 Tayyor! Xabarlar kutilmoqda...")

    await idle()

    await user.stop()
    await app.stop()
    log.info("👋 Bot to'xtatildi")


if __name__ == "__main__":
    asyncio.run(main())
