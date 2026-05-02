"""
VTube Studio WebSocket API 클라이언트

감정별 Live2D 파라미터 애니메이션 제어
- 15가지 감정 × 각각 고유한 몸/얼굴 움직임
- 부드러운 키프레임 보간(interpolation)
- 상시 아이들 애니메이션 루프
"""

import os
import json
import asyncio
import math
import time
import websockets
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from src.utils.logger import setup_logger

logger = setup_logger()

# ──────────────────────────────────────────────
# Live2D 파라미터 상수 (VTube Studio 기본값)
# ──────────────────────────────────────────────
class P:
    FACE_X      = "FaceAngleX"       # 고개 좌우    (-30 ~ 30)
    FACE_Y      = "FaceAngleY"       # 고개 상하    (-30 ~ 30)
    FACE_Z      = "FaceAngleZ"       # 고개 기울기  (-30 ~ 30)
    BODY_X      = "BodyAngleX"       # 몸 좌우      (-10 ~ 10)
    BODY_Y      = "BodyAngleY"       # 몸 상하      (-10 ~ 10)
    EYE_L       = "EyeOpenLeft"      # 왼눈 크기    (0 ~ 1)
    EYE_R       = "EyeOpenRight"     # 오른눈 크기  (0 ~ 1)
    EYE_SMILE_L = "EyeSmileLeft"     # 왼눈 웃음    (0 ~ 1)
    EYE_SMILE_R = "EyeSmileRight"    # 오른눈 웃음  (0 ~ 1)
    MOUTH_OPEN  = "MouthOpen"        # 입 벌림      (0 ~ 1)
    MOUTH_SMILE = "MouthSmile"       # 입꼬리       (-1 ~ 1)
    BROW_L      = "BrowLeftY"        # 왼 눈썹      (-1 ~ 1)
    BROW_R      = "BrowRightY"       # 오른 눈썹    (-1 ~ 1)
    CHEEK       = "CheekPuff"        # 볼           (0 ~ 1)


# ──────────────────────────────────────────────
# 키프레임 정의
# ──────────────────────────────────────────────
@dataclass
class Keyframe:
    """단일 파라미터 상태 스냅샷"""
    params: dict[str, float]
    duration: float  # 이 프레임까지 걸리는 시간 (초)


@dataclass
class EmotionAnimation:
    """감정 하나의 전체 애니메이션 시퀀스"""
    name: str
    keyframes: list[Keyframe]
    loop: bool = False           # True: 루프, False: 끝나면 idle로
    priority: int = 1            # 높을수록 다른 감정 중단 가능


# ──────────────────────────────────────────────
# 감정 애니메이션 정의 (15종)
# ──────────────────────────────────────────────

# 기본 얼굴값 (neutral 기준)
_BASE = {
    P.FACE_X: 0, P.FACE_Y: 0, P.FACE_Z: 0,
    P.BODY_X: 0, P.BODY_Y: 0,
    P.EYE_L: 1, P.EYE_R: 1,
    P.EYE_SMILE_L: 0, P.EYE_SMILE_R: 0,
    P.MOUTH_OPEN: 0, P.MOUTH_SMILE: 0,
    P.BROW_L: 0, P.BROW_R: 0,
    P.CHEEK: 0,
}

def _b(**kwargs) -> dict:
    """베이스에 오버라이드 적용"""
    return {**_BASE, **kwargs}


EMOTIONS: dict[str, EmotionAnimation] = {

    # ── 기쁨 계열 ──────────────────────────────

    "happy": EmotionAnimation(
        name="행복",
        keyframes=[
            Keyframe(_b(FACE_Z=8, EYE_SMILE_L=0.7, EYE_SMILE_R=0.7,
                        MOUTH_SMILE=0.8, CHEEK=0.3, BODY_X=3), 0.3),
            Keyframe(_b(FACE_Z=6, EYE_SMILE_L=0.6, EYE_SMILE_R=0.6,
                        MOUTH_SMILE=0.7, CHEEK=0.2, BODY_X=2), 0.5),
            Keyframe(_b(FACE_Z=8, EYE_SMILE_L=0.7, EYE_SMILE_R=0.7,
                        MOUTH_SMILE=0.8, CHEEK=0.3, BODY_X=3), 0.5),
        ]
    ),

    "excited": EmotionAnimation(
        name="흥분/신남",
        keyframes=[
            Keyframe(_b(BODY_Y=3, FACE_Y=5,  EYE_L=1.2, EYE_R=1.2,
                        EYE_SMILE_L=0.5, EYE_SMILE_R=0.5,
                        MOUTH_OPEN=0.4, MOUTH_SMILE=1.0), 0.15),
            Keyframe(_b(BODY_Y=-2, FACE_Y=-2, EYE_SMILE_L=0.8, EYE_SMILE_R=0.8,
                        MOUTH_SMILE=1.0, BODY_X=4), 0.15),
            Keyframe(_b(BODY_Y=3, FACE_Y=5,  EYE_L=1.2, EYE_R=1.2,
                        MOUTH_OPEN=0.5, MOUTH_SMILE=1.0), 0.15),
            Keyframe(_b(BODY_Y=-2, FACE_Y=-2, EYE_SMILE_L=0.8, EYE_SMILE_R=0.8,
                        MOUTH_SMILE=1.0, BODY_X=-4), 0.15),
            Keyframe(_b(EYE_SMILE_L=0.6, EYE_SMILE_R=0.6,
                        MOUTH_SMILE=0.9, BODY_X=0), 0.4),
        ]
    ),

    "laughing": EmotionAnimation(
        name="웃음/폭소",
        keyframes=[
            Keyframe(_b(BODY_Y=-4, FACE_Y=-8, FACE_Z=5,
                        EYE_SMILE_L=1.0, EYE_SMILE_R=1.0,
                        EYE_L=0.1, EYE_R=0.1,
                        MOUTH_OPEN=0.8, MOUTH_SMILE=1.0, CHEEK=0.5), 0.2),
            Keyframe(_b(BODY_Y=2,  FACE_Y=2,  FACE_Z=-3,
                        EYE_SMILE_L=0.9, EYE_SMILE_R=0.9,
                        EYE_L=0.2, EYE_R=0.2,
                        MOUTH_OPEN=0.6, MOUTH_SMILE=1.0, CHEEK=0.4), 0.2),
            Keyframe(_b(BODY_Y=-4, FACE_Y=-8, FACE_Z=5,
                        EYE_SMILE_L=1.0, EYE_SMILE_R=1.0,
                        EYE_L=0.1, EYE_R=0.1,
                        MOUTH_OPEN=0.8, MOUTH_SMILE=1.0, CHEEK=0.5), 0.2),
            Keyframe(_b(BODY_Y=2,  FACE_Y=2,
                        EYE_SMILE_L=0.8, EYE_SMILE_R=0.8,
                        MOUTH_OPEN=0.4, MOUTH_SMILE=0.9), 0.3),
        ]
    ),

    "proud": EmotionAnimation(
        name="뿌듯/자신감",
        keyframes=[
            Keyframe(_b(FACE_Y=10, FACE_Z=-5, BODY_X=-3, BODY_Y=2,
                        EYE_L=0.9, EYE_R=0.9,
                        MOUTH_SMILE=0.6, BROW_L=0.3, BROW_R=0.3), 0.5),
            Keyframe(_b(FACE_Y=8,  FACE_Z=-4, BODY_X=-2, BODY_Y=1,
                        MOUTH_SMILE=0.5, BROW_L=0.2, BROW_R=0.2), 0.6),
        ]
    ),

    # ── 슬픔 계열 ──────────────────────────────

    "sad": EmotionAnimation(
        name="슬픔",
        keyframes=[
            Keyframe(_b(FACE_Y=-10, FACE_Z=5, BODY_Y=-3,
                        EYE_L=0.5, EYE_R=0.5,
                        MOUTH_SMILE=-0.6, BROW_L=-0.4, BROW_R=-0.4), 0.6),
            Keyframe(_b(FACE_Y=-8,  FACE_Z=4, BODY_Y=-2,
                        EYE_L=0.4, EYE_R=0.4,
                        MOUTH_SMILE=-0.5, BROW_L=-0.3, BROW_R=-0.3), 0.8),
        ]
    ),

    "crying": EmotionAnimation(
        name="울음",
        keyframes=[
            Keyframe(_b(FACE_Y=-15, FACE_Z=8, BODY_Y=-5, BODY_X=2,
                        EYE_L=0.1, EYE_R=0.1,
                        MOUTH_OPEN=0.3, MOUTH_SMILE=-1.0,
                        BROW_L=-0.8, BROW_R=-0.8), 0.3),
            Keyframe(_b(FACE_Y=-12, FACE_Z=6, BODY_Y=-4, BODY_X=-2,
                        EYE_L=0.2, EYE_R=0.2,
                        MOUTH_OPEN=0.2, MOUTH_SMILE=-0.9,
                        BROW_L=-0.7, BROW_R=-0.7), 0.3),
            Keyframe(_b(FACE_Y=-15, FACE_Z=8, BODY_Y=-5, BODY_X=2,
                        EYE_L=0.0, EYE_R=0.0,
                        MOUTH_OPEN=0.4, MOUTH_SMILE=-1.0,
                        BROW_L=-0.9, BROW_R=-0.9), 0.3),
            Keyframe(_b(FACE_Y=-13, BODY_Y=-4,
                        EYE_L=0.2, EYE_R=0.2,
                        MOUTH_SMILE=-0.8, BROW_L=-0.6, BROW_R=-0.6), 0.5),
        ]
    ),

    "lonely": EmotionAnimation(
        name="외로움",
        keyframes=[
            Keyframe(_b(FACE_Z=12, FACE_X=-5, FACE_Y=-5, BODY_X=-3,
                        EYE_L=0.5, EYE_R=0.5,
                        MOUTH_SMILE=-0.3, BROW_L=-0.2, BROW_R=-0.2), 0.8),
            Keyframe(_b(FACE_Z=10, FACE_X=-3, FACE_Y=-4, BODY_X=-2,
                        EYE_L=0.4, EYE_R=0.4,
                        MOUTH_SMILE=-0.2), 1.0),
        ]
    ),

    # ── 놀람/긴장 계열 ─────────────────────────

    "surprised": EmotionAnimation(
        name="놀람",
        priority=2,
        keyframes=[
            Keyframe(_b(FACE_Y=-10, BODY_Y=-5,
                        EYE_L=1.5, EYE_R=1.5,
                        MOUTH_OPEN=0.7,
                        BROW_L=0.9, BROW_R=0.9), 0.1),
            Keyframe(_b(FACE_Y=-5, BODY_Y=-2,
                        EYE_L=1.3, EYE_R=1.3,
                        MOUTH_OPEN=0.4,
                        BROW_L=0.7, BROW_R=0.7), 0.3),
            Keyframe(_b(EYE_L=1.1, EYE_R=1.1,
                        MOUTH_OPEN=0.1,
                        BROW_L=0.3, BROW_R=0.3), 0.5),
        ]
    ),

    "nervous": EmotionAnimation(
        name="긴장/불안",
        keyframes=[
            Keyframe(_b(FACE_X=2,  BODY_X=1,
                        EYE_L=0.8, EYE_R=0.9,
                        BROW_L=0.2, BROW_R=-0.1,
                        MOUTH_SMILE=-0.1), 0.15),
            Keyframe(_b(FACE_X=-2, BODY_X=-1,
                        EYE_L=0.9, EYE_R=0.7,
                        BROW_L=-0.1, BROW_R=0.2,
                        MOUTH_SMILE=-0.2), 0.15),
            Keyframe(_b(FACE_X=1,  BODY_X=0.5,
                        EYE_L=0.8, EYE_R=0.8,
                        BROW_L=0.1, BROW_R=0.1), 0.15),
            Keyframe(_b(FACE_X=-1, BODY_X=-0.5,
                        MOUTH_SMILE=-0.1), 0.15),
            Keyframe(_b(), 0.4),
        ]
    ),

    "scared": EmotionAnimation(
        name="무서움",
        priority=2,
        keyframes=[
            Keyframe(_b(FACE_Y=-5, FACE_Z=-8, BODY_X=-6, BODY_Y=-4,
                        EYE_L=1.4, EYE_R=1.4,
                        MOUTH_OPEN=0.5,
                        BROW_L=0.8, BROW_R=0.8), 0.2),
            Keyframe(_b(FACE_Y=-4, FACE_Z=-6, BODY_X=-5, BODY_Y=-3,
                        EYE_L=1.3, EYE_R=1.3,
                        MOUTH_OPEN=0.3,
                        BROW_L=0.7, BROW_R=0.7), 0.3),
            Keyframe(_b(FACE_Z=-5, BODY_X=-4,
                        EYE_L=1.2, EYE_R=1.2,
                        BROW_L=0.5, BROW_R=0.5), 0.5),
        ]
    ),

    # ── 부정 계열 ──────────────────────────────

    "angry": EmotionAnimation(
        name="화남",
        priority=2,
        keyframes=[
            Keyframe(_b(FACE_Y=5, BODY_X=3, BODY_Y=2,
                        EYE_L=0.6, EYE_R=0.6,
                        MOUTH_OPEN=0.2, MOUTH_SMILE=-0.8,
                        BROW_L=-1.0, BROW_R=-1.0), 0.2),
            Keyframe(_b(FACE_Y=4, FACE_X=2, BODY_X=4, BODY_Y=1,
                        EYE_L=0.5, EYE_R=0.5,
                        MOUTH_SMILE=-0.9,
                        BROW_L=-0.9, BROW_R=-0.9), 0.2),
            Keyframe(_b(FACE_Y=5, FACE_X=-2, BODY_X=3, BODY_Y=2,
                        EYE_L=0.6, EYE_R=0.6,
                        MOUTH_SMILE=-0.8,
                        BROW_L=-1.0, BROW_R=-1.0), 0.2),
            Keyframe(_b(FACE_Y=3, BODY_X=2,
                        EYE_L=0.7, EYE_R=0.7,
                        MOUTH_SMILE=-0.6, BROW_L=-0.7, BROW_R=-0.7), 0.5),
        ]
    ),

    "disgusted": EmotionAnimation(
        name="역겨움/싫음",
        keyframes=[
            Keyframe(_b(FACE_X=15, FACE_Z=-8, FACE_Y=3, BODY_X=5,
                        EYE_L=0.4, EYE_R=0.7,
                        MOUTH_SMILE=-0.7, BROW_L=-0.5, BROW_R=-0.2), 0.4),
            Keyframe(_b(FACE_X=12, FACE_Z=-6, FACE_Y=2, BODY_X=4,
                        EYE_L=0.3, EYE_R=0.6,
                        MOUTH_SMILE=-0.6, BROW_L=-0.4, BROW_R=-0.2), 0.6),
        ]
    ),

    "confused": EmotionAnimation(
        name="혼란/의문",
        keyframes=[
            Keyframe(_b(FACE_Z=15, FACE_X=5, FACE_Y=2,
                        EYE_L=0.9, EYE_R=0.7,
                        BROW_L=0.6, BROW_R=-0.3,
                        MOUTH_OPEN=0.1, MOUTH_SMILE=-0.1), 0.3),
            Keyframe(_b(FACE_Z=12, FACE_X=3, FACE_Y=1,
                        EYE_L=0.8, EYE_R=0.6,
                        BROW_L=0.5, BROW_R=-0.2,
                        MOUTH_OPEN=0.1), 0.5),
            Keyframe(_b(FACE_Z=14, FACE_X=4,
                        EYE_L=0.9, EYE_R=0.7,
                        BROW_L=0.6, BROW_R=-0.3), 0.4),
        ]
    ),

    # ── 기타 계열 ──────────────────────────────

    "shy": EmotionAnimation(
        name="수줍음",
        keyframes=[
            Keyframe(_b(FACE_Y=-8, FACE_Z=10, FACE_X=-5,
                        BODY_X=-3, BODY_Y=-2,
                        EYE_L=0.6, EYE_R=0.5,
                        EYE_SMILE_L=0.3, EYE_SMILE_R=0.3,
                        MOUTH_SMILE=0.3, CHEEK=0.6,
                        BROW_L=-0.1, BROW_R=-0.1), 0.5),
            Keyframe(_b(FACE_Y=-7, FACE_Z=8, FACE_X=-4,
                        BODY_X=-2,
                        EYE_L=0.5, EYE_R=0.4,
                        EYE_SMILE_L=0.2, EYE_SMILE_R=0.2,
                        MOUTH_SMILE=0.2, CHEEK=0.5), 0.7),
        ]
    ),

    "sleepy": EmotionAnimation(
        name="졸림",
        loop=True,
        keyframes=[
            Keyframe(_b(FACE_Y=-5, FACE_Z=5, BODY_Y=-3,
                        EYE_L=0.3, EYE_R=0.3,
                        MOUTH_OPEN=0.1,
                        BROW_L=-0.2, BROW_R=-0.2), 1.0),
            Keyframe(_b(FACE_Y=-8, FACE_Z=6, BODY_Y=-4,
                        EYE_L=0.1, EYE_R=0.1,
                        BROW_L=-0.3, BROW_R=-0.3), 1.5),
            Keyframe(_b(FACE_Y=-3, FACE_Z=4, BODY_Y=-2,
                        EYE_L=0.4, EYE_R=0.4), 0.8),
        ]
    ),

    "bored": EmotionAnimation(
        name="지루함",
        loop=True,
        keyframes=[
            Keyframe(_b(FACE_X=10, FACE_Y=-3, BODY_X=4,
                        EYE_L=0.4, EYE_R=0.4,
                        MOUTH_SMILE=-0.2), 1.2),
            Keyframe(_b(FACE_X=-8, FACE_Y=-2, BODY_X=-3,
                        EYE_L=0.4, EYE_R=0.4,
                        MOUTH_SMILE=-0.1), 1.4),
            Keyframe(_b(FACE_X=5, BODY_X=2,
                        EYE_L=0.3, EYE_R=0.3), 1.0),
        ]
    ),

    "neutral": EmotionAnimation(
        name="기본",
        loop=True,
        keyframes=[
            Keyframe(_b(BODY_X=1.5, FACE_X=1), 1.5),
            Keyframe(_b(BODY_X=-1.5, FACE_X=-1), 1.5),
        ]
    ),
}


# ──────────────────────────────────────────────
# VTube Studio 클라이언트
# ──────────────────────────────────────────────

class VTubeStudioClient:

    def __init__(self):
        self.port = int(os.getenv("VTUBE_STUDIO_PORT", "8001"))
        self.plugin_name = os.getenv("VTUBE_STUDIO_PLUGIN_NAME", "AI_Streamer")
        self.token_file = Path(os.getenv("VTUBE_STUDIO_TOKEN_FILE", ".vtube_token"))
        self.ws = None
        self.token: Optional[str] = None
        self._request_id = 0
        self._current_emotion: str = "neutral"
        self._anim_task: Optional[asyncio.Task] = None
        self._idle_task: Optional[asyncio.Task] = None

    def _next_id(self) -> str:
        self._request_id += 1
        return str(self._request_id)

    # ── 연결 / 인증 ───────────────────────────

    async def connect(self):
        uri = f"ws://localhost:{self.port}"
        try:
            self.ws = await websockets.connect(uri)
            logger.info(f"VTube Studio 연결 완료 (포트: {self.port})")
            await self._authenticate()
            # 연결 성공 시 아이들 애니메이션 시작
            self._idle_task = asyncio.create_task(self._idle_loop())
        except Exception as e:
            logger.warning(f"VTube Studio 연결 실패: {e} — 표정 기능 비활성화")
            self.ws = None

    async def _authenticate(self):
        if self.token_file.exists():
            self.token = self.token_file.read_text().strip()
            if await self._auth_with_token(self.token):
                logger.info("VTube Studio 인증 완료 (저장된 토큰)")
                return
        self.token = await self._request_new_token()
        if self.token:
            self.token_file.write_text(self.token)
            logger.info("VTube Studio 새 토큰 저장 완료")

    async def _request_new_token(self) -> Optional[str]:
        payload = {
            "apiName": "VTubeStudioPublicAPI", "apiVersion": "1.0",
            "requestID": self._next_id(),
            "messageType": "AuthenticationTokenRequest",
            "data": {"pluginName": self.plugin_name, "pluginDeveloper": "AIStreamer"}
        }
        await self.ws.send(json.dumps(payload))
        resp = json.loads(await self.ws.recv())
        return resp.get("data", {}).get("authenticationToken")

    async def _auth_with_token(self, token: str) -> bool:
        payload = {
            "apiName": "VTubeStudioPublicAPI", "apiVersion": "1.0",
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

    # ── 파라미터 인젝션 ───────────────────────

    async def _inject(self, params: dict[str, float]):
        """여러 파라미터를 한 번에 VTube Studio로 전송"""
        if not self.ws:
            return
        payload = {
            "apiName": "VTubeStudioPublicAPI", "apiVersion": "1.0",
            "requestID": self._next_id(),
            "messageType": "InjectParameterDataRequest",
            "data": {
                "faceFound": False,
                "mode": "set",
                "parameterValues": [
                    {"id": k, "value": round(v, 4)} for k, v in params.items()
                ]
            }
        }
        try:
            await self.ws.send(json.dumps(payload))
        except Exception as e:
            logger.debug(f"파라미터 전송 오류: {e}")

    # ── 보간 유틸 ─────────────────────────────

    @staticmethod
    def _lerp(a: float, b: float, t: float) -> float:
        """선형 보간"""
        return a + (b - a) * t

    @staticmethod
    def _ease_in_out(t: float) -> float:
        """ease-in-out 커브 (더 자연스러운 움직임)"""
        return t * t * (3 - 2 * t)

    async def _animate_to(self, target: dict[str, float], duration: float,
                          current: dict[str, float]):
        """현재 상태에서 target까지 duration초 동안 부드럽게 전환"""
        start_time = time.time()
        fps = 30
        interval = 1.0 / fps

        while True:
            elapsed = time.time() - start_time
            t = min(elapsed / duration, 1.0)
            t_eased = self._ease_in_out(t)

            frame = {k: self._lerp(current.get(k, 0), target.get(k, 0), t_eased)
                     for k in set(current) | set(target)}

            await self._inject(frame)
            current.update(frame)

            if t >= 1.0:
                break
            await asyncio.sleep(interval)

    # ── 감정 실행 ─────────────────────────────

    async def play_emotion(self, emotion_name: str):
        """감정 이름으로 애니메이션 재생"""
        if not self.ws:
            return

        emotion = EMOTIONS.get(emotion_name, EMOTIONS["neutral"])
        logger.info(f"[표정] {emotion.name} ({emotion_name})")

        # 기존 애니메이션 중단
        if self._anim_task and not self._anim_task.done():
            self._anim_task.cancel()

        self._current_emotion = emotion_name
        self._anim_task = asyncio.create_task(self._run_emotion(emotion))

    async def _run_emotion(self, emotion: EmotionAnimation):
        """키프레임 시퀀스 실행"""
        try:
            current = dict(_BASE)
            while True:
                for kf in emotion.keyframes:
                    await self._animate_to(kf.params, kf.duration, current)
                    current = dict(kf.params)
                if not emotion.loop:
                    break
        except asyncio.CancelledError:
            pass
        finally:
            # 루프 아닌 감정은 끝나면 idle로 복귀
            if not emotion.loop and self._current_emotion != "neutral":
                await asyncio.sleep(0.5)
                if self._current_emotion != "neutral":
                    await self.play_emotion("neutral")

    # ── 아이들 루프 ───────────────────────────

    async def _idle_loop(self):
        """
        neutral 상태일 때 상시 실행되는 미세 움직임 루프
        - 눈 깜빡임 (랜덤 주기)
        - 호흡에 맞춘 몸 상하
        """
        import random
        blink_interval = random.uniform(3, 6)
        blink_timer = 0.0
        breath_phase = 0.0

        while True:
            try:
                await asyncio.sleep(0.05)
                blink_timer += 0.05
                breath_phase += 0.05

                # 호흡 효과 (사인파)
                breath = math.sin(breath_phase * 0.4) * 0.8
                await self._inject({P.BODY_Y: breath})

                # 눈 깜빡임
                if blink_timer >= blink_interval:
                    await self._blink()
                    blink_timer = 0
                    blink_interval = random.uniform(3, 7)

            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(1)

    async def _blink(self):
        """눈 깜빡임 애니메이션"""
        for v in [0.3, 0.0, 0.3, 0.7, 1.0]:
            await self._inject({P.EYE_L: v, P.EYE_R: v})
            await asyncio.sleep(0.04)

    # ── 공개 인터페이스 ───────────────────────

    async def trigger_emotion(self, emotion: str):
        """외부(main.py)에서 호출하는 감정 트리거"""
        await self.play_emotion(emotion)

    async def close(self):
        if self._anim_task:
            self._anim_task.cancel()
        if self._idle_task:
            self._idle_task.cancel()
        if self.ws:
            await self.ws.close()
            logger.info("VTube Studio 연결 종료")
