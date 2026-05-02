import os
import aiohttp
import secrets
from fastapi import APIRouter, HTTPException, Header
from fastapi.responses import RedirectResponse
from dotenv import load_dotenv
from event_queue import EVENT_QUEUE

load_dotenv()

router = APIRouter()

# =========================
# 🔐 ENV
# =========================
CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")
EVENTSUB_SECRET = os.getenv("TWITCH_EVENTSUB_SECRET")

REDIRECT_URI = "https://sharan-bot-kp71.onrender.com/auth/twitch/callback"
CALLBACK_URL = "https://sharan-bot-kp71.onrender.com/eventsub"

SCOPES = "user:read:email chat:read chat:edit channel:read:subscriptions"

# =========================
# 🧠 SIMPLE TOKEN STORE
# =========================
USER_TOKENS = {}  # {channel: access_token}

# =========================
# 🔹 LOGIN ROUTE
# =========================
@router.get("/auth/twitch/login")
async def twitch_login():

    state = secrets.token_urlsafe(16)

    url = (
        "https://id.twitch.tv/oauth2/authorize"
        f"?client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        "&response_type=code"
        f"&scope={SCOPES}"
        f"&state={state}"
    )

    return RedirectResponse(url)


# =========================
# 🔹 CALLBACK ROUTE
# =========================
@router.get("/auth/twitch/callback")
async def twitch_callback(code: str, state: str = None):

    async with aiohttp.ClientSession() as session:

        # 1️⃣ Exchange code → user access token
        token_resp = await session.post(
            "https://id.twitch.tv/oauth2/token",
            params={
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": REDIRECT_URI,
            },
        )

        token_data = await token_resp.json()
        access_token = token_data.get("access_token")

        if not access_token:
            raise HTTPException(status_code=400, detail=token_data)

        # 2️⃣ Get user info
        user_resp = await session.get(
            "https://api.twitch.tv/helix/users",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Client-Id": CLIENT_ID,
            },
        )

        user_data = await user_resp.json()

        if "data" not in user_data or not user_data["data"]:
            raise HTTPException(status_code=400, detail=user_data)

        user = user_data["data"][0]
        login = user["login"]
        broadcaster_id = user["id"]

        print(f"✅ OAuth success for {login}")

        # ✅ STORE TOKEN (IMPORTANT FIX)
        USER_TOKENS[login] = access_token

        # 3️⃣ Get APP token (EventSub)
        app_token_resp = await session.post(
            "https://id.twitch.tv/oauth2/token",
            params={
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "grant_type": "client_credentials",
            },
        )

        app_token_data = await app_token_resp.json()
        app_access_token = app_token_data.get("access_token")

        headers = {
            "Authorization": f"Bearer {app_access_token}",
            "Client-Id": CLIENT_ID,
            "Content-Type": "application/json",
        }

        # 🧹 CLEAN OLD EVENTSUBS
        sub_resp = await session.get(
            "https://api.twitch.tv/helix/eventsub/subscriptions",
            headers=headers
        )

        sub_data = await sub_resp.json()

        for sub in sub_data.get("data", []):
            if sub.get("condition", {}).get("broadcaster_user_id") == broadcaster_id:
                await session.delete(
                    "https://api.twitch.tv/helix/eventsub/subscriptions",
                    headers=headers,
                    params={"id": sub["id"]},
                )

        # 🎯 CREATE EVENTSUB
        event_types = [
            "stream.online",
            "stream.offline",
            "channel.follow",
            "channel.subscribe",
            "channel.cheer",
        ]

        for event_type in event_types:
            await session.post(
                "https://api.twitch.tv/helix/eventsub/subscriptions",
                headers=headers,
                json={
                    "type": event_type,
                    "version": "1",
                    "condition": {
                        "broadcaster_user_id": broadcaster_id
                    },
                    "transport": {
                        "method": "webhook",
                        "callback": CALLBACK_URL,
                        "secret": EVENTSUB_SECRET,
                    },
                },
            )

        print(f"🎯 EventSub created for {login}")

        # 🚀 Queue onboarding
        EVENT_QUEUE.append({
            "type": "channel.added",
            "event": {
                "login": login,
                "broadcaster_user_login": login
            }
        })

        # ❌ REMOVE TOKEN FROM URL
        return RedirectResponse(
            url=f"https://itsfrosea.github.io/dashboard/dashboard.html?channel={login}",
            status_code=302
        )


# =========================
# 🔐 VERIFY USER (FIXED)
# =========================
async def verify_user(channel: str, authorization: str):

    # get stored token instead of trusting frontend
    token = USER_TOKENS.get(channel)

    if not token:
        raise HTTPException(status_code=403, detail="No stored token")

    async with aiohttp.ClientSession() as session:

        resp = await session.get(
            "https://api.twitch.tv/helix/users",
            headers={
                "Authorization": f"Bearer {token}",
                "Client-Id": CLIENT_ID
            }
        )

        if resp.status != 200:
            print("❌ Twitch API error:", resp.status)
            raise HTTPException(status_code=403, detail="Invalid token")

        data = await resp.json()

        if not data.get("data"):
            raise HTTPException(status_code=403, detail="User not found")

        return data["data"][0]["login"]
    
async def get_current_user(token: str):

    if not token:
        return None

    async with aiohttp.ClientSession() as session:

        resp = await session.get(
            "https://api.twitch.tv/helix/users",
            headers={
                "Authorization": f"Bearer {token}",
                "Client-Id": CLIENT_ID
            }
        )

        if resp.status != 200:
            print("❌ Twitch API error:", resp.status)
            return None

        data = await resp.json()

        if "data" not in data or not data["data"]:
            return None

        return data["data"][0]["login"]