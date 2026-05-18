import os
import aiohttp
import secrets
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from dotenv import load_dotenv
from event_queue import EVENT_QUEUE

load_dotenv()

router = APIRouter()
TWITCH_USER_TOKENS = {}

# =========================
# 🔐 ENV
# =========================
CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")
EVENTSUB_SECRET = os.getenv("TWITCH_EVENTSUB_SECRET")

REDIRECT_URI = "https://sharan-bot-kp71.onrender.com/auth/twitch/callback"
CALLBACK_URL = "https://sharan-bot-kp71.onrender.com/eventsub"

SCOPES = (
    "user:read:email "
    "chat:read "
    "chat:edit "
    "channel:read:subscriptions "
    "moderator:read:followers "
    "bits:read "
    "clips:edit"
)

if not CLIENT_ID or not CLIENT_SECRET:
    raise RuntimeError("TWITCH_CLIENT_ID or TWITCH_CLIENT_SECRET missing")


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

        # =========================
        # 1️⃣ EXCHANGE USER CODE
        # =========================
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

        # =========================
        # 2️⃣ GET USER INFO
        # =========================
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

        twitch_user = user_data["data"][0]
        login = twitch_user["login"]
        broadcaster_id = twitch_user["id"]


        print(f"✅ OAuth success for {login}")

        TWITCH_USER_TOKENS[login.lower()] = access_token
        print(f"🔐 Saved token for {login}")

        EVENT_QUEUE.append({
            "type": "twitch.token.save",
            "event": {
                "channel": login,
                "token": access_token
            }
        })

        # =========================
        # 3️⃣ GET APP TOKEN FOR EVENTSUB
        # =========================
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

        if not app_access_token:
            raise HTTPException(status_code=400, detail=app_token_data)

        headers = {
            "Authorization": f"Bearer {app_access_token}",
            "Client-Id": CLIENT_ID,
            "Content-Type": "application/json",
        }

        # =========================
        # 🧹 CLEAN OLD EVENTSUBS
        # =========================
        sub_resp = await session.get(
            "https://api.twitch.tv/helix/eventsub/subscriptions",
            headers=headers
        )

        sub_data = await sub_resp.json()

        for sub in sub_data.get("data", []):
            condition = sub.get("condition", {})

            if condition.get("broadcaster_user_id") == broadcaster_id:
                sub_id = sub["id"]

                await session.delete(
                    "https://api.twitch.tv/helix/eventsub/subscriptions",
                    headers=headers,
                    params={"id": sub_id},
                )

                print(f"🧹 Removed old EventSub: {sub_id}")

        # =========================
        # 🎯 CREATE EVENTSUBS
        # =========================

        subscriptions = [
            {
                "type": "stream.online",
                "version": "1",
                "condition": {
                    "broadcaster_user_id": broadcaster_id
                }
            },
            {
                "type": "stream.offline",
                "version": "1",
                "condition": {
                    "broadcaster_user_id": broadcaster_id
                }
            },
            {
                "type": "channel.subscribe",
                "version": "1",
                "condition": {
                    "broadcaster_user_id": broadcaster_id
                }
            },
            {
                "type": "channel.cheer",
                "version": "1",
                "condition": {
                    "broadcaster_user_id": broadcaster_id
                }
            },
            {
                "type": "channel.follow",
                "version": "2",
                "condition": {
                    "broadcaster_user_id": broadcaster_id,
                    "moderator_user_id": broadcaster_id
                }
            },
        ]

        for sub in subscriptions:
            resp = await session.post(
                "https://api.twitch.tv/helix/eventsub/subscriptions",
                headers=headers,
                json={
                    **sub,
                    "transport": {
                        "method": "webhook",
                        "callback": CALLBACK_URL,
                        "secret": EVENTSUB_SECRET,
                    },
                },
            )

            data = await resp.json()

            print(f"📡 {sub['type']} → {resp.status}")
            print(data)

        print(f"🎯 EventSub created for {login}")

        # =========================
        # 5️⃣ PUSH ONBOARD EVENT
        # =========================
        EVENT_QUEUE.append({
            "type": "channel.added",
            "event": {
                "login": login,
                "broadcaster_user_login": login
            }
        })

        print(f"🚀 Queued onboarding for {login}")

        # =========================
        # 6️⃣ REDIRECT TO DASHBOARD
        # =========================
        return RedirectResponse(
            url=(
                f"https://itsfrosea.github.io/dashboard/dashboard.html"
                f"?channel={login}"
                f"&token={access_token}"
            ),
            status_code=302
        )


# =========================
# 🔐 GET CURRENT USER
# =========================
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

        user = data["data"][0]["login"]

        print("TWITCH USER:", user)

        return user