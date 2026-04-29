import os
import json
import asyncio
import websockets
from pathlib import Path
from src.utils.logger import setup_logger

logger = setup_logger()

# 감정 태그 → VTube Studio 핫키 이름 매핑
# VTube Studio에서 핫키 이름을 동일하게 설정해야 함
EMOTION_HOTKEY_MAP = {
    "happy":     "emotion_happy",
    "sad":       "emotion_sad",
    "surprised": "emotion_surprised",
    "angry":     "emotion_angry",
    "neutral":   "emotion_neutral",
}


class VTubeStudioClient:
    """
    VTube Studio WebSocket API 클라이언트
    감정 태그에 따라 표정 핫키를 트리거함
    """

    def __init__(self):
        self.port = int(os.getenv("VTUBE_STUDIO_PORT", "8001"))
        self.plugin_name = os.getenv("VTUBE_STUDIO_PLUGIN_NAME", "AI_Streamer")
        self.token_file = Path(os.getenv("VTUBE_STUDIO_TOKEN_FILE", ".vtube_token"))
        self.ws = None
        self.token: str | None = None
        self._request_id = 0

    def _next_id(self) -> str:
        self._request_id += 1
        return str(self._request_id)

    async def connect(self):
        """VTube Studio에 WebSocket 연결 및 인증"""
        uri = f"ws://localhost:{self.port}"
        try:
            self.ws = await websockets.connect(uri)
            logger.info(f"VTube Studio WebSocket 연결 완료 (포트: {self.port})")
            await self._authenticate()
        except Exception as e:
            logger.warning(f"VTube Studio 연결 실패: {e} — 표정/립싱크 기능 비활성화")
            self.ws = None

    async def _authenticate(self):
        """토큰 파일이 있으면 재사용, 없으면 신규 발급"""
        if self.token_file.exists():
            self.token = self.token_file.read_text().strip()
            success = await self._auth_with_token(self.token)
            if success:
                logger.info("VTube Studio 인증 완료 (저장된 토큰)")
                return

        # 신규 토큰 발급
        self.token = await self._request_new_token()
        if self.token:
            self.token_file.write_text(self.token)
            logger.info("VTube Studio 새 토큰 저장 완료")

    async def _request_new_token(self) -> str | None:
        """VTube Studio에 플러그인 토큰 요청"""
        payload = {
            "apiName": "VTubeStudioPublicAPI",
            "apiVersion": "1.0",
            "requestID": self._next_id(),
            "messageType": "AuthenticationTokenRequest",
            "data": {
                "pluginName": self.plugin_name,
                "pluginDeveloper": "AIStreamer",
            }
        }
        await self.ws.send(json.dumps(payload))
        resp = json.loads(await self.ws.recv())
        return resp.get("data", {}).get("authenticationToken")

    async def _auth_with_token(self, token: str) -> bool:
        """발급된 토큰으로 인증"""
        payload = {
            "apiName": "VTubeStudioPublicAPI",
            "apiVersion": "1.0",
            "requestID": self._next_id(),
            "messageType": "AuthenticationRequest",
            "data": {
                "pluginName": self.plugin_name,
                "pluginDeveloper": "AIStreamer",
                "authenticationToken": token
            }
        }
        await self.ws.send(json.dumps(payload))
        resp = json.loads(await self.ws.recv())
        return resp.get("data", {}).get("authenticated", False)

    async def trigger_emotion(self, emotion: str):
        """감정 태그에 해당하는 핫키 트리거"""
        if not self.ws:
            return

        hotkey_name = EMOTION_HOTKEY_MAP.get(emotion, "emotion_neutral")

        # 핫키 목록에서 ID 조회
        hotkey_id = await self._get_hotkey_id(hotkey_name)
        if not hotkey_id:
            logger.debug(f"핫키 없음: {hotkey_name}")
            return

        # 핫키 실행
        payload = {
            "apiName": "VTubeStudioPublicAPI",
            "apiVersion": "1.0",
            "requestID": self._next_id(),
            "messageType": "HotkeyTriggerRequest",
            "data": {"hotkeyID": hotkey_id}
        }
        try:
            await self.ws.send(json.dumps(payload))
            await self.ws.recv()
            logger.debug(f"핫키 트리거: {hotkey_name}")
        except Exception as e:
            logger.warning(f"핫키 트리거 실패: {e}")

    async def _get_hotkey_id(self, name: str) -> str | None:
        """핫키 이름으로 ID 조회"""
        payload = {
            "apiName": "VTubeStudioPublicAPI",
            "apiVersion": "1.0",
            "requestID": self._next_id(),
            "messageType": "HotkeysInCurrentModelRequest",
            "data": {}
        }
        try:
            await self.ws.send(json.dumps(payload))
            resp = json.loads(await self.ws.recv())
            hotkeys = resp.get("data", {}).get("availableHotkeys", [])
            for hk in hotkeys:
                if hk.get("name", "").lower() == name.lower():
                    return hk.get("hotkeyID")
        except Exception as e:
            logger.warning(f"핫키 목록 조회 실패: {e}")
        return None

    async def close(self):
        if self.ws:
            await self.ws.close()
            logger.info("VTube Studio 연결 종료")
