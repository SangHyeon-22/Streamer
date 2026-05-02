"""
자체 콘텐츠 엔진 (Feature 3)

- TMI 타임: 주기적으로 자기 얘기 꺼내기
- 고민 상담 모드: 시청자 고민 진지하게 들어주기
- 즉흥 토크 주제: 채팅 흐름이 끊길 때 새 주제 던지기
"""

import re
import os
import time
import random
from src.utils.logger import setup_logger

logger = setup_logger()

# 고민 상담 모드 트리거 키워드
CONSULTATION_TRIGGERS = [
    "고민", "상담", "힘들어", "힘든데", "우울", "슬퍼", "외로워",
    "모르겠어", "어떡해", "어떡하지", "도와줘", "조언",
]

# TMI 토픽 풀 (매번 랜덤 선택)
TMI_TOPICS = [
    "오늘 먹은 거",
    "요즘 꽂혀있는 것",
    "최근에 당황했던 일",
    "어릴 때 기억",
    "요즘 자주 하는 생각",
    "갑자기 생각난 소름 돋는 기억",
    "오늘 기분이 이런 이유",
    "요즘 꿈에 자주 나오는 것",
    "나만 이상한 건지 모를 습관",
    "최근에 웃겼던 일",
    "한 번도 말 안 했던 비밀 TMI",
    "요즘 가고 싶은 곳",
]


class SelfContentEngine:
    """AI 버튜버의 자체 콘텐츠 생성기"""

    def __init__(self, brain):
        self.brain = brain
        self._consultation_mode = False
        self._consultation_user: str | None = None
        self._last_tmi_time = time.time()
        self._tmi_interval = float(os.getenv("TMI_INTERVAL", "300"))  # 기본 5분

    # ── 고민 상담 감지 ─────────────────────────────

    def detect_consultation(self, message: str, username: str) -> bool:
        """고민 상담 요청인지 감지"""
        msg_lower = message.lower()
        for keyword in CONSULTATION_TRIGGERS:
            if keyword in msg_lower:
                if not self._consultation_mode:
                    self._consultation_mode = True
                    self._consultation_user = username
                    logger.info(f"[상담 모드] {username}님 고민 감지")
                return True
        return False

    def end_consultation(self):
        """상담 모드 종료"""
        if self._consultation_mode:
            self._consultation_mode = False
            self._consultation_user = None
            logger.info("[상담 모드] 종료")

    def generate_consultation_response(self, message: str, username: str) -> tuple[str, str]:
        """
        상담 모드 전용 응답 생성
        - 공감 우선, 짧은 조언, 판단 금지
        """
        prompt = f"""
지금 {username}님이 고민을 털어놓고 있어.
상담사처럼 따뜻하게 들어주고 공감해줘.

고민 내용: "{message}"

규칙:
- 절대 판단하거나 가르치려 하지 마
- 먼저 충분히 공감해줘
- 짧은 위로 한 마디 + 조심스럽게 한 가지만 물어봐
- 3문장 이내로
"""
        return self.brain._generate_raw(prompt, max_tokens=180)

    # ── TMI 타임 ───────────────────────────────────

    def should_tmi(self) -> bool:
        """TMI 타임 발동 조건 체크"""
        return time.time() - self._last_tmi_time >= self._tmi_interval

    def generate_tmi(self) -> tuple[str, str]:
        """랜덤 주제로 TMI 생성"""
        topic = random.choice(TMI_TOPICS)
        prompt = f"""
지금 채팅이 잠깐 조용한 틈에 갑자기 '{topic}'에 대한 TMI를 털어놔.
버튜버답게 자연스럽게, 약간 민망하거나 웃긴 내용이면 더 좋아.
2~3문장으로 짧게.
"""
        result = self.brain._generate_raw(prompt, max_tokens=120)
        self._last_tmi_time = time.time()
        logger.info(f"[TMI] 토픽: {topic}")
        return result

    # ── 즉흥 토크 주제 ─────────────────────────────

    def generate_topic_change(self) -> tuple[str, str]:
        """채팅 흐름이 끊길 때 새 주제 자연스럽게 던지기"""
        prompt = """
채팅이 뜸해졌어. 자연스럽게 새로운 대화 주제를 꺼내봐.
예: 갑자기 생각난 질문 던지기, 오늘 있었던 일 꺼내기, 시청자한테 뭔가 물어보기.
2문장 이내로. 질문으로 끝내면 더 좋아.
"""
        return self.brain._generate_raw(prompt, max_tokens=100)

    @property
    def is_consultation_mode(self) -> bool:
        return self._consultation_mode

    @property
    def consultation_user(self) -> str | None:
        return self._consultation_user
