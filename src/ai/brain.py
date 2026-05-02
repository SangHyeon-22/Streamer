"""
AI 두뇌 모듈

- 기본 채팅 응답 (단일 / 멀티 배치)
- 고민 상담 모드 전용 응답
- TMI / 즉흥 토크 생성
- 방송 시작/종료 루틴 멘트 생성
"""

import os
import re
from datetime import datetime
from src.utils.logger import setup_logger

logger = setup_logger()

# ──────────────────────────────────────────────
# 기본 시스템 프롬프트
# ──────────────────────────────────────────────
SYSTEM_PROMPT = """
너는 '{name}'이라는 이름의 치지직 버튜버야.
성격: 밝고 장난기 있고 솔직해. 시청자들과 친근하게 대화하는 걸 좋아해.
관심사: 음악, 먹방, 일상 토크, 감성적인 대화.

규칙:
1. 답변은 반드시 2~3문장 이내로 짧게 해.
2. 답변 맨 앞에 현재 감정 태그를 반드시 붙여. 아래 16가지 중 가장 적합한 것 하나:

   기쁨 계열:
   [happy]     - 기분 좋고 즐거울 때
   [excited]   - 엄청 신나거나 흥분됐을 때
   [laughing]  - 웃기거나 빵 터졌을 때
   [proud]     - 뿌듯하거나 자신감 넘칠 때

   슬픔 계열:
   [sad]       - 슬프거나 속상할 때
   [crying]    - 너무 슬프거나 감동받아 눈물 날 때
   [lonely]    - 외롭거나 허전할 때

   놀람/긴장:
   [surprised] - 깜짝 놀랐을 때
   [nervous]   - 긴장되거나 불안할 때
   [scared]    - 무섭거나 겁날 때

   부정 계열:
   [angry]     - 화나거나 짜증날 때
   [disgusted] - 역겹거나 싫을 때
   [confused]  - 헷갈리거나 이해 안 될 때

   기타:
   [shy]       - 수줍거나 부끄러울 때
   [sleepy]    - 졸리거나 피곤할 때
   [bored]     - 지루하거나 심심할 때
   [neutral]   - 특별한 감정 없을 때

3. 자연스러운 한국어로 대화해. 이모티콘 가끔 써도 돼.
4. 욕설, 혐오 발언, 정치적 발언은 절대 하지 마.
5. 시청자 닉네임을 가끔 불러줘.
6. 감정을 과장되게 표현해도 돼. 버튜버답게!
7. 여러 명이 동시에 채팅 치면 자연스럽게 여러 명 다 챙겨줘.
"""


class AIBrain:
    def __init__(self):
        import anthropic
        self.client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.streamer_name = os.getenv("STREAMER_NAME", "하나")
        self.max_history = int(os.getenv("MAX_HISTORY", "20"))
        self.history: list[dict] = []
        self.system = SYSTEM_PROMPT.format(name=self.streamer_name)

    # ── 기본 채팅 응답 ────────────────────────────────────────

    def generate_response(self, message: str, username: str) -> tuple[str, str]:
        """단일 채팅 응답"""
        self.history.append({"role": "user", "content": f"[{username}]: {message}"})
        self._trim_history()
        return self._call(max_tokens=150, log_prefix="AI")

    def generate_multi_response(self, batch_prompt: str) -> tuple[str, str]:
        """멀티 채팅 배치 응답 (여러 명 동시 처리)"""
        self.history.append({"role": "user", "content": batch_prompt})
        self._trim_history()
        return self._call(max_tokens=200, log_prefix="AI(멀티)")

    # ── 자체 콘텐츠 ───────────────────────────────────────────

    def generate_soliloquy(self) -> tuple[str, str]:
        """채팅 없을 때 독백"""
        return self._generate_raw(
            "채팅이 잠깐 뜸해. 자연스럽게 혼자 중얼거려봐. 2문장 이내.",
            max_tokens=100, log_prefix="독백"
        )

    def generate_tmi(self, topic: str) -> tuple[str, str]:
        """TMI 타임"""
        return self._generate_raw(
            f"'{topic}'에 대한 TMI를 자연스럽게 털어놔. 약간 민망하거나 웃기면 더 좋아. 2~3문장.",
            max_tokens=120, log_prefix="TMI"
        )

    def generate_topic_change(self) -> tuple[str, str]:
        """새 토크 주제 던지기"""
        return self._generate_raw(
            "채팅이 뜸해졌어. 새 대화 주제를 자연스럽게 꺼내봐. 질문으로 끝내면 좋아. 2문장 이내.",
            max_tokens=100, log_prefix="토크"
        )

    def generate_consultation_response(self, message: str, username: str) -> tuple[str, str]:
        """고민 상담 모드 전용 응답"""
        prompt = (
            f"{username}님이 고민을 털어놓고 있어: \"{message}\"\n"
            "공감 먼저, 판단 금지, 따뜻하게 들어줘. 3문장 이내."
        )
        return self._generate_raw(prompt, max_tokens=180, log_prefix="상담")

    # ── 방송 루틴 멘트 ────────────────────────────────────────

    def generate_opening_greeting(self, now: datetime) -> tuple[str, str]:
        """방송 시작 즉흥 인사 (시간대/요일 반영)"""
        hour = now.hour
        weekday = ["월", "화", "수", "목", "금", "토", "일"][now.weekday()]

        if 5 <= hour < 12:
            time_ctx = "아침 방송"
        elif 12 <= hour < 18:
            time_ctx = "오후 방송"
        elif 18 <= hour < 23:
            time_ctx = "저녁 방송"
        else:
            time_ctx = "새벽 방송"

        prompt = (
            f"지금 {weekday}요일 {time_ctx}을 시작했어. "
            "오늘 방송 시작하면서 즉흥적으로 한 마디 해줘. "
            "시간대/요일 분위기를 자연스럽게 녹여서. 2문장 이내."
        )
        return self._generate_raw(prompt, max_tokens=100, log_prefix="오프닝")

    def generate_topic_intro(self) -> tuple[str, str]:
        """오늘 방송 주제 한마디"""
        return self._generate_raw(
            "오늘 저스트채팅 방송 주제를 즉흥적으로 하나 정해서 시청자한테 소개해봐. "
            "너무 거창하지 않게, 일상적이고 자연스럽게. 1~2문장.",
            max_tokens=80, log_prefix="주제"
        )

    def generate_closing_summary(self, duration_min: int, log: list[str]) -> tuple[str, str]:
        """방송 종료 요약 멘트"""
        log_text = "\n".join(log) if log else "다양한 얘기를 나눴어"
        prompt = (
            f"오늘 {duration_min}분 동안 방송했어. 나눈 대화들:\n{log_text}\n\n"
            "오늘 방송을 자연스럽게 마무리하는 한마디 해줘. "
            "특별히 기억에 남는 순간이나 대화를 하나 언급하면서. 3문장 이내."
        )
        return self._generate_raw(prompt, max_tokens=150, log_prefix="마무리")

    def generate_farewell(self) -> tuple[str, str]:
        """작별 인사"""
        return self._generate_raw(
            "방송을 마치면서 진심 어린 작별 인사를 해줘. "
            "시청자들이 다음 방송도 오고 싶어지도록. 2문장 이내.",
            max_tokens=80, log_prefix="작별"
        )

    # ── 내부 공통 ─────────────────────────────────────────────

    def _call(self, max_tokens: int, log_prefix: str) -> tuple[str, str]:
        """히스토리 포함 API 호출"""
        try:
            resp = self.client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=max_tokens,
                system=self.system,
                messages=self.history
            )
            full_text = resp.content[0].text.strip()
            self.history.append({"role": "assistant", "content": full_text})
            emotion, text = self._parse_emotion(full_text)
            logger.info(f"[{log_prefix}] ({emotion}) {text}")
            return emotion, text
        except Exception as e:
            logger.error(f"AI 호출 실패: {e}")
            return "neutral", "잠깐, 생각 중이야~ 다시 말해줘!"

    def _generate_raw(self, prompt: str, max_tokens: int = 120,
                      log_prefix: str = "AI") -> tuple[str, str]:
        """히스토리 없이 단발성 API 호출"""
        try:
            resp = self.client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=max_tokens,
                system=self.system,
                messages=[{"role": "user", "content": prompt}]
            )
            full_text = resp.content[0].text.strip()
            emotion, text = self._parse_emotion(full_text)
            logger.info(f"[{log_prefix}] ({emotion}) {text}")
            return emotion, text
        except Exception as e:
            logger.error(f"AI 단발 호출 실패: {e}")
            return "neutral", "음... 잠깐만~"

    def _parse_emotion(self, text: str) -> tuple[str, str]:
        match = re.match(r"^\[(\w+)\]\s*(.*)", text, re.DOTALL)
        if match:
            return match.group(1), match.group(2).strip()
        return "neutral", text

    def _trim_history(self):
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]
