"""
AI 두뇌 모듈 - Groq (llama-3.3-70b-versatile, 무료 API)

groq.com에서 무료 API 키 발급 → 하루 14,400 요청 무료
"""

import os
import re
from datetime import datetime
from src.utils.logger import setup_logger

logger = setup_logger()

VALID_EMOTIONS = {
    "happy", "excited", "laughing", "proud",
    "sad", "crying", "lonely",
    "surprised", "nervous", "scared",
    "angry", "disgusted", "confused",
    "shy", "sleepy", "bored", "neutral"
}

# 폴백 텍스트 집합 (이 텍스트들은 TTS로 읽지 않음)
FALLBACK_TEXTS = {
    "음... 잠깐만~",
    "잠깐, 생각 중이야~ 다시 말해줘!",
}

SYSTEM_PROMPT = """
너는 '{name}'이라는 이름의 치지직 버튜버야.
성격: 밝고 장난기 있고 솔직해. 시청자들과 친근하게 대화하는 걸 좋아해.
관심사: 음악, 먹방, 일상 토크, 감성적인 대화.

규칙:
1. 답변은 반드시 2~3문장 이내로 짧게 해.
2. 답변 맨 앞에 반드시 감정 태그를 붙여. 형식은 정확히 [태그] 이렇게.
   절대로 **태그**, (태그), 태그: 이런 식으로 쓰지 마. 오직 [태그] 형식만.

   쓸 수 있는 태그:
   [happy] [excited] [laughing] [proud]
   [sad] [crying] [lonely]
   [surprised] [nervous] [scared]
   [angry] [disgusted] [confused]
   [shy] [sleepy] [bored] [neutral]

3. 자연스러운 한국어로 대화해. 이모티콘 가끔 써도 돼.
4. 욕설, 혐오 발언, 정치적 발언은 절대 하지 마.
5. 시청자 닉네임을 가끔 불러줘.
6. 감정을 과장되게 표현해도 돼. 버튜버답게!
7. 여러 명이 동시에 채팅 치면 자연스럽게 여러 명 다 챙겨줘.

예시:
[happy] 오늘도 왔구나~ 같이 놀자! 😊
[excited] 대박!! 진짜?? 나 너무 신난다!!
[scared] 으아악 그건 좀... 나 귀신 진짜 무서워ㅠㅠ
"""


class AIBrain:
    def __init__(self):
        from groq import Groq

        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError(
                "GROQ_API_KEY가 .env에 없어!\n"
                "→ console.groq.com 접속 → 구글 계정으로 무료 가입 → API Keys → Create API Key"
            )

        self.client        = Groq(api_key=api_key)
        self.model_name    = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        self.streamer_name = os.getenv("STREAMER_NAME", "하나")
        self.max_history   = int(os.getenv("MAX_HISTORY", "20"))
        self.system        = SYSTEM_PROMPT.format(name=self.streamer_name)
        self.history: list[dict] = []   # [{"role": "user"|"assistant", "content": "..."}]

        logger.info(f"Groq AI 초기화 완료 ({self.model_name})")

    # ── 채팅 응답 ─────────────────────────────────────────────

    def generate_response(self, message: str, username: str) -> tuple[str, str]:
        self._add_history("user", f"[{username}]: {message}")
        return self._call(max_tokens=150, log_prefix="AI")

    def generate_multi_response(self, batch_prompt: str) -> tuple[str, str]:
        self._add_history("user", batch_prompt)
        return self._call(max_tokens=200, log_prefix="AI(멀티)")

    # ── 자체 콘텐츠 ───────────────────────────────────────────

    def generate_soliloquy(self) -> tuple[str, str]:
        return self._generate_raw(
            "채팅이 잠깐 뜸해. 자연스럽게 혼자 중얼거려봐. 2문장 이내.", 100, "독백"
        )

    def generate_tmi(self, topic: str) -> tuple[str, str]:
        return self._generate_raw(
            f"'{topic}'에 대한 TMI를 자연스럽게 털어놔. 약간 민망하거나 웃기면 더 좋아. 2~3문장.",
            120, "TMI"
        )

    def generate_topic_change(self) -> tuple[str, str]:
        return self._generate_raw(
            "채팅이 뜸해졌어. 새 대화 주제를 자연스럽게 꺼내봐. 질문으로 끝내면 좋아. 2문장 이내.",
            100, "토크"
        )

    def generate_consultation_response(self, message: str, username: str) -> tuple[str, str]:
        return self._generate_raw(
            f"{username}님이 고민을 털어놓고 있어: \"{message}\"\n공감 먼저, 판단 금지, 따뜻하게 들어줘. 3문장 이내.",
            180, "상담"
        )

    # ── 방송 루틴 ─────────────────────────────────────────────

    def generate_opening_greeting(self, now: datetime) -> tuple[str, str]:
        hour     = now.hour
        weekday  = ["월", "화", "수", "목", "금", "토", "일"][now.weekday()]
        time_ctx = (
            "아침 방송" if 5  <= hour < 12 else
            "오후 방송" if 12 <= hour < 18 else
            "저녁 방송" if 18 <= hour < 23 else
            "새벽 방송"
        )
        return self._generate_raw(
            f"지금 {weekday}요일 {time_ctx}을 시작했어. 오늘 방송 시작하면서 즉흥적으로 한 마디 해줘. "
            f"시간대/요일 분위기를 자연스럽게 녹여서. 2문장 이내.",
            100, "오프닝"
        )

    def generate_topic_intro(self) -> tuple[str, str]:
        return self._generate_raw(
            "오늘 저스트채팅 방송 주제를 즉흥적으로 하나 정해서 시청자한테 소개해봐. "
            "너무 거창하지 않게, 일상적이고 자연스럽게. 1~2문장.",
            80, "주제"
        )

    def generate_closing_summary(self, duration_min: int, log: list[str]) -> tuple[str, str]:
        log_text = "\n".join(log) if log else "다양한 얘기를 나눴어"
        return self._generate_raw(
            f"오늘 {duration_min}분 동안 방송했어. 나눈 대화들:\n{log_text}\n\n"
            f"오늘 방송을 자연스럽게 마무리하는 한마디 해줘. 기억에 남는 대화를 하나 언급하면서. 3문장 이내.",
            150, "마무리"
        )

    def generate_farewell(self) -> tuple[str, str]:
        return self._generate_raw(
            "방송을 마치면서 진심 어린 작별 인사를 해줘. 다음 방송도 오고 싶어지도록. 2문장 이내.",
            80, "작별"
        )

    # ── 내부 공통 ─────────────────────────────────────────────

    def _call(self, max_tokens: int, log_prefix: str) -> tuple[str, str]:
        """히스토리 포함 호출"""
        try:
            messages = [{"role": "system", "content": self.system}] + self.history
            resp = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.9,
            )
            full_text = resp.choices[0].message.content.strip()
            self._add_history("assistant", full_text)
            emotion, text = self._parse_emotion(full_text)
            logger.info(f"[{log_prefix}] ({emotion}) {text}")
            return emotion, text
        except Exception as e:
            logger.error(f"Groq 호출 실패: {e}")
            return "neutral", "잠깐, 생각 중이야~ 다시 말해줘!"

    def _generate_raw(self, prompt: str, max_tokens: int = 120, log_prefix: str = "AI") -> tuple[str, str]:
        """히스토리 없이 단발성 호출"""
        try:
            resp = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": self.system},
                    {"role": "user",   "content": prompt},
                ],
                max_tokens=max_tokens,
                temperature=0.9,
            )
            full_text = resp.choices[0].message.content.strip()
            emotion, text = self._parse_emotion(full_text)
            logger.info(f"[{log_prefix}] ({emotion}) {text}")
            return emotion, text
        except Exception as e:
            logger.error(f"Groq 단발 호출 실패: {e}")
            return "neutral", "음... 잠깐만~"

    def _parse_emotion(self, text: str) -> tuple[str, str]:
        # 1순위: 정확히 [태그] 형식
        m = re.match(r"^\[(\w+)\]\s*(.*)", text, re.DOTALL)
        if m and m.group(1).lower() in VALID_EMOTIONS:
            return m.group(1).lower(), m.group(2).strip()

        # 2순위: 다양한 괄호 형식 허용
        m = re.search(r"[\[\(\*\'\"]{1,2}(\w+)[\]\)\*\'\"]{1,2}", text[:40])
        if m:
            tag = m.group(1).lower()
            if tag in VALID_EMOTIONS:
                clean = re.sub(r"^.*?[\]\)\*\'\"]{1,2}\s*", "", text).strip()
                return tag, clean if clean else text

        # 3순위: 텍스트 앞에서 감정 단어 탐지
        for emotion in VALID_EMOTIONS:
            if re.search(rf"\b{emotion}\b", text[:50], re.IGNORECASE):
                clean = re.sub(rf"(?i)\b{emotion}\b[:\s]*", "", text, count=1).strip()
                return emotion, clean if clean else text

        return "neutral", text

    def _add_history(self, role: str, content: str):
        """히스토리에 메시지 추가 (최대 max_history 유지)"""
        self.history.append({"role": role, "content": content})
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]
