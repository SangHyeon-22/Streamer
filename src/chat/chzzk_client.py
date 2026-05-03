"""
치지직 채팅 클라이언트 (직접 WebSocket 구현)
chzzkpy v2가 OAuth 방식으로 바뀌어서 직접 구현
"""

import os
import json
import asyncio
import aiohttp
from dataclasses import dataclass
from src.utils.logger import setup_logger

logger = setup_logger()

CHAT_SOCK_URL = "wss://kr-ss1.chat.naver.com/chat"


@dataclass
class ChatMessage:
    username: str
    content: str


class ChzzkChatClient:
    def __init__(self, queue: asyncio.Queue):
        self.queue      = queue
        self.channel_id = os.getenv("CHZZK_CHANNEL_ID")
        self.nid_aut    = os.getenv("CHZZK_NID_AUT")
        self.nid_ses    = os.getenv("CHZZK_NID_SES")
        self._running   = False

    async def start(self):
        self._running = True
        while self._running:
            try:
                await self._connect()
            except Exception as e:
                logger.warning(f"채팅 연결 끊김: {e} — 5초 후 재연결")
                await asyncio.sleep(5)

    async def _connect(self):
        # 1. 채팅 채널 UID 조회
        chat_channel_id = await self._get_chat_channel_id()
        if not chat_channel_id:
            logger.error("채팅 채널 ID 조회 실패 — 방송 중인지 확인해줘!")
            await asyncio.sleep(15)
            return

        # 2. 액세스 토큰 조회
        access_token, extra_token = await self._get_access_token(chat_channel_id)

        # 3. WebSocket 연결
        headers = {"Cookie": f"NID_AUT={self.nid_aut}; NID_SES={self.nid_ses}"}
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(CHAT_SOCK_URL, headers=headers) as ws:
                logger.info("✅ 치지직 채팅 연결 완료!")

                # 연결 초기화 패킷
                await self._send_connect(ws, chat_channel_id, access_token)

                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        await self._handle_message(msg.data)
                    elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        logger.warning("WebSocket 연결 종료")
                        break

    async def _get_chat_channel_id(self) -> str | None:
        """방송 중인 채팅 채널 ID 조회"""
        url = f"https://api.chzzk.naver.com/service/v1/channels/{self.channel_id}/live-detail"
        cookies = {"NID_AUT": self.nid_aut, "NID_SES": self.nid_ses}
        try:
            async with aiohttp.ClientSession(cookies=cookies) as session:
                async with session.get(url) as resp:
                    data = await resp.json()
                    chat_id = data.get("content", {}).get("chatChannelId")
                    if chat_id:
                        logger.info(f"채팅 채널 ID: {chat_id}")
                    return chat_id
        except Exception as e:
            logger.error(f"채팅 채널 ID 조회 실패: {e}")
            return None

    async def _get_access_token(self, chat_channel_id: str) -> tuple[str, str]:
        """채팅 액세스 토큰 조회"""
        url = f"https://comm-api.game.naver.com/nng_main/v1/chats/access-token?channelId={chat_channel_id}&chatType=STREAMING"
        cookies = {"NID_AUT": self.nid_aut, "NID_SES": self.nid_ses}
        try:
            async with aiohttp.ClientSession(cookies=cookies) as session:
                async with session.get(url) as resp:
                    data = await resp.json()
                    content = data.get("content", {})
                    return content.get("accessToken", ""), content.get("extraToken", "")
        except Exception as e:
            logger.error(f"액세스 토큰 조회 실패: {e}")
            return "", ""

    async def _send_connect(self, ws, chat_channel_id: str, access_token: str):
        """WebSocket 연결 초기화 패킷 전송"""
        payload = {
            "ver": "2",
            "cmd": 100,
            "svcid": "game",
            "cid": chat_channel_id,
            "bdy": {
                "uid": None,
                "devType": 2001,
                "accTkn": access_token,
                "auth": "READ",
                "devName": "AI_Streamer",
                "libVer": "4.9.0",
                "osVer": "Windows/10",
                "locale": "ko",
                "timezone": "Asia/Seoul",
            },
            "tid": 1,
        }
        await ws.send_str(json.dumps(payload))

    async def _handle_message(self, raw: str):
        """수신 메시지 파싱"""
        try:
            data = json.loads(raw)
            cmd  = data.get("cmd")

            if cmd == 93101:  # 채팅 메시지
                for item in data.get("bdy", []):
                    if item.get("msgTypeCode", 0) != 1:  # 일반 텍스트만
                        continue
                    content  = item.get("msg", "").strip()
                    profile  = json.loads(item.get("profile", "{}"))
                    username = profile.get("nickname", "익명")
                    if not content:
                        continue
                    logger.info(f"[채팅] {username}: {content}")
                    await self.queue.put(ChatMessage(username=username, content=content))

        except Exception as e:
            logger.debug(f"메시지 파싱 오류: {e}")

    async def stop(self):
        self._running = False
        logger.info("채팅 클라이언트 종료")
