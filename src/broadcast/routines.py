"""
방송 루틴 (Feature 8)

시작/종료/자리비움 루틴 + 하나만의 시그니처 멘트
- 시작: 오프닝 멘트 → 오늘의 운세 → 인사
- 종료: 오늘 방송 요약 → 클로징 멘트
- 자리비움: 대기 멘트 → 복귀 멘트
"""

import os
import time
import random
import asyncio
from datetime import datetime
from src.utils.logger import setup_logger
from src.ai.brain import FALLBACK_TEXTS

logger = setup_logger()

# ──────────────────────────────────────────────────────────────
#  시그니처 오프닝 멘트 (매 방송 랜덤 1개 선택)
# ──────────────────────────────────────────────────────────────
OPENING_SIGNATURES = [
    "야 왔어!! 기다렸지? 솔직히 말해봐~",
    "어서와어서와~ 여기는 항상 열려있어!",
    "나 왔다고!! 오늘도 나랑 놀다가~",
    "켰다! 살아있다! 오늘도 방송한다!",
    "늦지 않았지? 아 늦었어? 미안 미안~ 그래도 왔잖아!",
]

# ──────────────────────────────────────────────────────────────
#  시그니처 클로징 멘트
# ──────────────────────────────────────────────────────────────
CLOSING_SIGNATURES = [
    "간다간다~ 근데 사실 안 가고 싶어... 아 가야지. 다음에 또 와줘!",
    "오늘도 같이 있어줘서 고마워~ 나 없어도 잘 살아야 해?",
    "꿈에서 보면 놀라지 마~ 또 올게!",
    "다음 방송도 꼭 와줘. 안 오면 내가 찾아간다?",
    "오늘 재밌었다! 다들 조심히 들어가고~ 밥 꼭 챙겨 먹어!",
]

# ──────────────────────────────────────────────────────────────
#  자리비움 멘트
# ──────────────────────────────────────────────────────────────
AFK_MESSAGES = [
    "잠깐 자리 비웠다 올게~ 도망간 거 아니야!",
    "화장실 다녀올게 진짜 금방이야!!",
    "물 한 잔만 마시고 올게~ 잠깐만!",
    "잠깐 기다려! 곧 올게~",
]

RETURN_MESSAGES = [
    "나 왔어!! 오래 기다렸어?",
    "돌아왔다~! 많이 기다렸지?",
    "왔어왔어! 채팅 많이 쌓였겠다 ㅋㅋ",
    "나 없는 사이에 뭔 일 있었어?",
]

# 운세 풀
FORTUNE_CONTENTS = [
    "오늘은 예상치 못한 행운이 찾아올 것 같은 날! 작은 것도 소중히 여겨봐.",
    "약간 피곤한 하루가 될 수 있어. 그래도 괜찮아, 쉬어가는 것도 필요하잖아.",
    "오늘 말 한마디 한마디가 다 복이 되는 날이래! 좋은 말만 해~",
    "뭔가 새로운 걸 시작하기 좋은 날이야. 오늘 방송도 그 일부가 될 수 있어!",
    "오늘은 느긋하게 가는 게 정답! 서두르면 안 돼~",
    "연락 안 됐던 사람한테 연락이 올 수도? 핸드폰 잘 챙겨봐!",
    "오늘은 먹는 복이 터지는 날이래! 맛있는 거 먹어야 해~",
    "예상치 못한 곳에서 웃음이 터지는 날. 오늘 방송이 그거일 수도!",
]


class BroadcastRoutines:
    def __init__(self, brain, tts, vtube):
        self.brain  = brain
        self.tts    = tts
        self.vtube  = vtube
        self.streamer_name  = os.getenv("STREAMER_NAME", "하나")
        self._broadcast_log: list[str] = []
        self._start_time: float = 0.0
        self._afk_start:  float = 0.0

    # ── 방송 시작 루틴 ─────────────────────────────────────────

    async def run_start(self):
        """방송 시작: 시그니처 오프닝 → AI 즉흥 인사 → 운세 → 주제 소개"""
        logger.info("[루틴] 방송 시작")
        self._start_time = time.time()
        now = datetime.now()

        # 1. 시그니처 오프닝 (고정 멘트, 항상 출력)
        signature = random.choice(OPENING_SIGNATURES)
        await self._say("excited", signature)
        await asyncio.sleep(0.8)

        # 2. AI 즉흥 인사 (매 방송 다르게)
        emotion, text = self.brain.generate_opening_greeting(now)
        await self._say(emotion, text)
        await asyncio.sleep(0.6)

        # 3. 오늘의 운세 (고정 풀에서 선택, 항상 출력)
        fortune = f"오늘의 운세: {random.choice(FORTUNE_CONTENTS)} 🔮"
        await self._say("happy", fortune)
        await asyncio.sleep(0.5)

        # 4. 오늘 방송 주제 소개 (AI 생성)
        emotion, text = self.brain.generate_topic_intro()
        await self._say(emotion, text)

    # ── 방송 종료 루틴 ─────────────────────────────────────────

    async def run_end(self):
        """방송 종료: AI 방송 요약 → 시그니처 클로징 → AI 작별"""
        logger.info("[루틴] 방송 종료")

        # 1. AI 방송 요약
        duration_min = int((time.time() - self._start_time) / 60)
        emotion, text = self.brain.generate_closing_summary(
            duration_min=duration_min,
            log=self._broadcast_log[-10:]
        )
        await self._say(emotion, text)
        await asyncio.sleep(0.8)

        # 2. 시그니처 클로징 (항상 출력)
        signature = random.choice(CLOSING_SIGNATURES)
        await self._say("happy", signature)
        await asyncio.sleep(0.5)

        # 3. AI 즉흥 작별 인사
        emotion, text = self.brain.generate_farewell()
        await self._say(emotion, text)

    # ── 자리비움 루틴 ──────────────────────────────────────────

    async def run_afk(self):
        """자리 비울 때"""
        logger.info("[루틴] 자리비움")
        self._afk_start = time.time()
        await self._say("neutral", random.choice(AFK_MESSAGES))

    async def run_return(self):
        """자리 복귀"""
        afk_sec = int(time.time() - self._afk_start)
        logger.info(f"[루틴] 자리 복귀 ({afk_sec}초 후)")
        await self._say("happy", random.choice(RETURN_MESSAGES))

    # ── 대화 로그 기록 ─────────────────────────────────────────

    def log_exchange(self, username: str, message: str, response: str):
        """방송 중 대화 기록 (종료 요약용)"""
        entry = f"{username}: {message[:30]} → {response[:40]}"
        self._broadcast_log.append(entry)
        if len(self._broadcast_log) > 100:
            self._broadcast_log = self._broadcast_log[-100:]

    # ── 내부 유틸 ──────────────────────────────────────────────

    async def _say(self, emotion: str, text: str):
        """VTube 표정 + TTS 발화 (폴백 텍스트는 무시)"""
        if not text or text in FALLBACK_TEXTS:
            logger.debug(f"[루틴] 폴백 텍스트 무시: {text!r}")
            return
        await self.vtube.trigger_emotion(emotion)
        await self.tts.speak(text, emotion)
