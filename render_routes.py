from fastapi import APIRouter, Header, HTTPException
from twitchio import channel
from event_queue import EVENT_QUEUE
from twitch.oauth import get_current_user
from twitch.oauth import TWITCH_USER_TOKENS
import aiohttp
import os

import asyncio
import json

router = APIRouter()

LEADERBOARD_CACHE = {}
COMMANDS_CACHE = {}
SETTINGS_CACHE = {}
TIMED_CACHE = {}
ACCESS_CACHE = {}

# =========================
# 🔐 AUTH HELPER
# =========================
async def verify_user(channel: str, authorization: str):

    channel = channel.lower()

    # =========================
    # 1️⃣ VERIFY TWITCH LOGIN
    # =========================

    token = authorization.replace("Bearer ", "") if authorization else None

    user = await get_current_user(token)

    if not user or user.lower() != channel:
        raise HTTPException(
            status_code=403,
            detail="Unauthorized"
        )

    print("AUTH HEADER:", authorization)
    print("CHANNEL:", channel)

    # =========================
    # 2️⃣ ASK SPARKED FOR ACCESS
    # =========================

    ACCESS_CACHE.pop(channel, None)

    EVENT_QUEUE.append({
        "type": "access.check",
        "event": {
            "channel": channel
        }
    })

    print("🔐 Access check requested:", channel)

    # =========================
    # 3️⃣ WAIT FOR SPARKED
    # =========================

    for _ in range(60):

        if channel in ACCESS_CACHE:

            has_access = ACCESS_CACHE.pop(channel)

            print("========== ACCESS RESULT ==========")
            print("CHANNEL:", channel)
            print("ACCESS:", has_access)
            print("===================================")

            if not has_access:
                raise HTTPException(
                    status_code=402,
                    detail="Trial expired or premium subscription required"
                )

            return user

        await asyncio.sleep(0.1)

    # Sparked didn't respond
    raise HTTPException(
        status_code=503,
        detail="Unable to verify subscription"
    )

# =========================
# 💬 ADD CUSTOM COMMAND
# =========================
@router.post("/command/add")
async def add_command(data: dict, authorization: str = Header(None)):

    await verify_user(data["channel"], authorization)

    data["command"] = data["command"].strip().lower()
    data["response"] = data["response"].strip()

    EVENT_QUEUE.append({
        "type": "command.add",
        "event": data
    })

    return {"success": True}


# =========================
# 📜 GET COMMAND LIST
# =========================
@router.get("/commands")
async def get_commands(channel: str, authorization: str = Header(None)):

    await verify_user(channel, authorization)

    COMMANDS_CACHE.pop(channel, None)

    EVENT_QUEUE.append({
        "type": "commands.list",
        "event": {"channel": channel}
    })

    for _ in range(60):
        if channel in COMMANDS_CACHE:
            return COMMANDS_CACHE[channel]
        await asyncio.sleep(0.1)

    return []


# =========================
# 🏆 LEADERBOARD
# =========================
@router.get("/leaderboard")
async def leaderboard(channel: str, authorization: str = Header(None)):

    await verify_user(channel, authorization)

    LEADERBOARD_CACHE.pop(channel, None)

    EVENT_QUEUE.append({
        "type": "leaderboard.request",
        "event": {"channel": channel}
    })

    for _ in range(60):
        if channel in LEADERBOARD_CACHE:
            return LEADERBOARD_CACHE[channel]
        await asyncio.sleep(0.1)

    return []


# =========================
# 🗑 DELETE COMMAND
# =========================
@router.post("/command/delete")
async def delete_command(data: dict, authorization: str = Header(None)):

    await verify_user(data["channel"], authorization)

    EVENT_QUEUE.append({
        "type": "command.delete",
        "event": data
    })

    return {"success": True}

@router.post("/command/update")
async def update_command(data: dict, authorization: str = Header(None)):

    await verify_user(data["channel"], authorization)

    data["command"] = data["command"].strip().lower()
    data["response"] = data["response"].strip()

    EVENT_QUEUE.append({
        "type": "command.update",
        "event": data
    })

    return {"success": True}


# =========================
# 💰 ECONOMY
# =========================
@router.post("/economy/save")
async def save_economy(data: dict, authorization: str = Header(None)):

    await verify_user(data["channel"], authorization)

    EVENT_QUEUE.append({
        "type": "economy.save",
        "event": data
    })

    return {"success": True}


@router.post("/currency/set")
async def set_currency(data: dict, authorization: str = Header(None)):

    await verify_user(data["channel"], authorization)

    EVENT_QUEUE.append({
        "type": "currency.set",
        "event": data
    })

    return {"success": True}


@router.post("/medals/set")
async def set_medals(data: dict, authorization: str = Header(None)):

    await verify_user(data["channel"], authorization)

    EVENT_QUEUE.append({
        "type": "medals.set",
        "event": data
    })

    return {"success": True}


@router.post("/points/settings")
async def set_points_settings(data: dict, authorization: str = Header(None)):

    await verify_user(data["channel"], authorization)

    EVENT_QUEUE.append({
        "type": "points.settings",
        "event": data
    })

    return {"success": True}


# =========================
# ⏰ TIMED MESSAGES
# =========================
@router.post("/timed/add")
async def add_timed_message(data: dict, authorization: str = Header(None)):

    await verify_user(data["channel"], authorization)

    EVENT_QUEUE.append({
        "type": "timed.add",
        "event": data
    })

    return {"success": True}


@router.post("/timed/delete")
async def delete_timed_message(data: dict, authorization: str = Header(None)):

    await verify_user(data["channel"], authorization)

    EVENT_QUEUE.append({
        "type": "timed.delete",
        "event": data
    })

    return {"success": True}

@router.post("/timed/update")
async def update_timed_message(data: dict, authorization: str = Header(None)):

    await verify_user(data["channel"], authorization)

    EVENT_QUEUE.append({
        "type": "timed.update",
        "event": data
    })

    return {"success": True}

@router.get("/timed/list")
async def timed_list(channel: str, authorization: str = Header(None)):

    await verify_user(channel, authorization)

    TIMED_CACHE.pop(channel, None)

    EVENT_QUEUE.append({
        "type": "timed.list",
        "event": {"channel": channel}
    })

    for _ in range(60):
        if channel in TIMED_CACHE:
            return TIMED_CACHE[channel]
        await asyncio.sleep(0.1)

    return []


# =========================
# ⚙️ SETTINGS
# =========================
@router.get("/settings")
async def get_settings(channel: str, authorization: str = Header(None)):

    await verify_user(channel, authorization)

    SETTINGS_CACHE.pop(channel, None)

    EVENT_QUEUE.append({
        "type": "settings.request",
        "event": {"channel": channel}
    })

    for _ in range(60):
        if channel in SETTINGS_CACHE:
            return SETTINGS_CACHE[channel]
        await asyncio.sleep(0.1)

    return {"medals_enabled": 1}


# =========================
# 🔁 INTERNAL (NO AUTH)
# =========================
@router.post("/internal/leaderboard")
async def leaderboard_response(data: dict):

    LEADERBOARD_CACHE[data["channel"]] = data["data"]
    return {"ok": True}


@router.post("/internal/commands")
async def commands_response(data: dict):

    commands = data["data"]

    if isinstance(commands, str):
        commands = json.loads(commands)

    COMMANDS_CACHE[data["channel"]] = commands
    return {"ok": True}


@router.post("/internal/settings")
async def settings_response(data: dict):

    SETTINGS_CACHE[data["channel"]] = data["data"]
    return {"ok": True}


@router.post("/internal/timed")
async def timed_response(data: dict):

    TIMED_CACHE[data["channel"]] = data["data"]
    return {"ok": True}

@router.post("/clip/create")
async def create_clip(
    data: dict,
    authorization: str = Header(None)
):

    channel = data.get("channel", "").lower()

    if not channel:
        raise HTTPException(
            status_code=400,
            detail="Channel is required"
        )

    # =========================
    # 🔐 VERIFY USER + ACCESS
    # =========================

    await verify_user(channel, authorization)

    # =========================
    # 🎟️ GET STREAMER TOKEN
    # =========================

    token = TWITCH_USER_TOKENS.get(channel)

    print("CHANNEL:", channel)
    print("TOKEN FOUND:", bool(token))

    if token:
        print("TOKEN PREFIX:", token[:20])

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Streamer not authenticated with Twitch dashboard"
        )

    # =========================
    # 🎬 CREATE CLIP
    # =========================

    async with aiohttp.ClientSession() as session:

        # -------------------------
        # Get broadcaster ID
        # -------------------------

        user_resp = await session.get(
            "https://api.twitch.tv/helix/users",
            headers={
                "Authorization": f"Bearer {token}",
                "Client-Id": os.getenv("TWITCH_CLIENT_ID"),
            }
        )

        user_data = await user_resp.json()

        print("USER STATUS:", user_resp.status)
        print("USER DATA:", user_data)

        if user_resp.status != 200 or not user_data.get("data"):
            raise HTTPException(
                status_code=401,
                detail={
                    "error": "Twitch token is invalid or expired",
                    "twitch_response": user_data
                }
            )

        broadcaster_id = user_data["data"][0]["id"]

        print("BROADCASTER ID:", broadcaster_id)

        # -------------------------
        # Create clip
        # -------------------------

        clip_resp = await session.post(
            "https://api.twitch.tv/helix/clips",
            headers={
                "Authorization": f"Bearer {token}",
                "Client-Id": os.getenv("TWITCH_CLIENT_ID"),
            },
            params={
                "broadcaster_id": broadcaster_id
            }
        )

        clip_data = await clip_resp.json()

        print("CLIP STATUS:", clip_resp.status)
        print("CLIP DATA:", clip_data)

        if clip_resp.status != 202 or not clip_data.get("data"):
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "Clip creation failed",
                    "twitch_response": clip_data
                }
            )

        clip_id = clip_data["data"][0]["id"]

        print("🎬 CLIP CREATED:", clip_id)

        return {
            "success": True,
            "clip_id": clip_id,
            "clip_url": f"https://clips.twitch.tv/{clip_id}"
        }

@router.post("/internal/access")
async def access_response(data: dict):

    channel = data["channel"].lower()

    ACCESS_CACHE[channel] = bool(data["has_access"])

    print("🔐 ACCESS RESPONSE:", channel, data["has_access"])

    return {"ok": True}