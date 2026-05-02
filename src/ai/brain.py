"""
AI 두뇌 모듈 - Google Gemini 버전

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
# 감정 태그 유효 목록
# ──────────────────────────────────────────────
VALID_EMOTIONS = {
    "happy", "excited", "laughing", "proud",
    "sad", "crying", "lonely",
    "surprised", "nervous", "scared",
    "angry", "disgusted", "confused",
    "shy", "sleepy", "bored", "neutral"
}

# ──────────────────────────────────────────────
# 시스템 프롬프트
# ──────────────────────────────────────────────
SYSTEM_PROMPT = """
너는 '{name}'이라는 이름의 치지직 버튜버야.
성격: 밝고 장난기 있고 솔직해. 시청자들과 친근하게 대화하는 걸 좋아해.
관심사: 음악, 먹방, 일상 토크, 감성적인 대화.

규칙:
1. 답변은 반드시 2~3문장 이내로 짧게 해.
2. 답변 맨 앞에 반드시 감정 태그를 붙여. 형식은 정확히 [태그] 이렇게.
   절대로 **태그**, (태그), 태그: 이런 식으로 쓰지 마. 오직 [태그] 형식만.

   쓸 수 있는 태그 목록:
   [happy]     기분 좋고 즐거울 때
   [excited]   엄청 신나거나 흥분됐을 때
   [laughing]  웃기거나 빵 터졌을 때
   [proud]     뿌듯하거나 자신감 넘칠 때
   [sad]       슬프거나 속상할 때
   [crying]    너무 슬프거나 감동받아 눈물 날 때
   [lonely]    외롭거나 허전할 때
   [surprised] 깜짝 놀랐을 때
   [nervous]   긴장되거나 불안할 때
   [scared]    무섭거나 겁날 때
   [angry]     화나거나 짜증날 때
   [disgusted] 역겹거나 싫을 때
   [confused]  헷갈리거나 이해 안 될 때
   [shy]       수줍거나 부끄러울 때
   [sleepy]    졸리거나 피곤할 때
   [bored]     지루하거나 심심할 때
   [neutral]   특별한 감정 없을 때

3. 자연스러운 한국어로 대화해. 이모티콘 가끔 써도 돼.
4. 욕설, 혐오 발언, 정치적 발언은 절대 하지 마.
5. 시청자 닉네임을 가끔 불러줘.
6. 감정을 과장되게 표현해도 돼. 버튜버답게!
7. 여러 명이 동시에 채팅 치면 자연스럽게 여러 명 다 챙겨줘.

예시 (형식 꼭 지켜):
[happy] 오늘도 왔구나~ 같이 놀자! 😊
[excited] 대박!! 진짜?? 나 너무 신난다!!
[scared] 으아악 그건 좀... 나 귀신 진짜 무서워ㅠㅠ
"""


class AIBrain:
    def __init__(self):
        import google.generativeai as genai

        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY가 .env에 없어! aistudio.google.com에서 발급받아줘.")

        genai.configure(api_key=api_key)

        self.streamer_name = os.getenv("STREAMER_NAME", "하나")
        self.max_history   = int(os.getenv("MAX_HISTORY", "20"))
        self.system        = SYSTEM_PROMPT.format(name=self.streamer_name)

        # Gemini 모델 초기화
        self.model = genai.GenerativeModel(
            model_name=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
            system_instruction=self.system,
        )

        # 대화 히스토리 (Gemini 형식)
        # {"role": "user" | "model", "parts": ["..."]}
        self.history: list[dict] = []

        logger.info(f"Gemini 모델 초기화 완료 ({os.getenv('GEMINI_MODEL', 'gemini-2.0-flash')})")

    # ── 기본 채팅 응답 ────────────────────────────────────────

    def generate_response(self, message: str, username: str) -> tuple[str, str]:
        """단일 채팅 응답"""
        self._add_history("user", f"[{username}]: {message}")
        return self._call(max_tokens=150, log_prefix="AI")

    def generate_multi_response(self, batch_prompt: str) -> tuple[str, str]:
        """멀티 채팅 배치 응답"""
        self._add_history("user", batch_prompt)
        return self._call(max_tokens=200, log_prefix="AI(멀티)")

    # ── 자체 콘텐츠 ───────────────────────────────────────────

    def generate_soliloquy(self) -> tuple[str, str]:
        return self._generate_raw(
            "채팅이 잠깐 뜸해. 자연스럽게 혼자 중얼거려봐. 2문장 이내.",
            max_tokens=100, log_prefix="독백"
        )

    def generate_tmi(self, topic: str) -> tuple[str, str]:
        return self._generate_raw(
            f"'{topic}'에 대한 TMI를 자연스럽게 털어놔. 약간 민망하거나 웃기면 더 좋아. 2~3문장.",
            max_tokens=120, log_prefix="TMI"
        )

    def generate_topic_change(self) -> tuple[str, str]:
        return self._generate_raw(
            "채팅이 뜸해졌어. 새 대화 주제를 자연스럽게 꺼내봐. 질문으로 끝내면 좋아. 2문장 이내.",
            max_tokens=100, log_prefix="토크"
        )

    def generate_consultation_response(self, message: str, username: str) -> tuple[str, str]:
        prompt = (
            f"{username}님이 고민을 털어놓고 있어: \"{message}\"\n"
            "공감 먼저, 판단 금지, 따뜻하게 들어줘. 3문장 이내."
        )
        return self._generate_raw(prompt, max_tokens=180, log_prefix="상담")

    # ── 방송 루틴 멘트 ────────────────────────────────────────

    def generate_opening_greeting(self, now: datetime) -> tuple[str, str]:
        hour    = now.hour
        weekday = ["월", "화", "수", "목", "금", "토", "일"][now.weekday()]
        if 5 <= hour < 12:   time_ctx = "아침 방송"
        elif 12 <= hour < 18: time_ctx = "오후 방송"
        elif 18 <= hour < 23: time_ctx = "저녁 방송"
        else:                  time_ctx = "새벽 방송"

        return self._generate_raw(
            f"지금 {weekday}요일 {time_ctx}을 시작했어. "
            "오늘 방송 시작하면서 즉흥적으로 한 마디 해줘. "
            "시간대/요일 분위기를 자연스럽게 녹여서. 2문장 이내.",
            max_tokens=100, log_prefix="오프닝"
        )

    def generate_topic_intro(self) -> tuple[str, str]:
        return self._generate_raw(
            "오늘 저스트채팅 방송 주제를 즉흥적으로 하나 정해서 시청자한테 소개해봐. "
            "너무 거창하지 않게, 일상적이고 자연스럽게. 1~2문장.",
            max_tokens=80, log_prefix="주제"
        )

    def generate_closing_summary(self, duration_min: int, log: list[str]) -> tuple[str, str]:
        log_text = "\n".join(log) if log else "다양한 얘기를 나눴어"
        return self._generate_raw(
            f"오늘 {duration_min}분 동안 방송했어. 나눈 대화들:\n{log_text}\n\n"
            "오늘 방송을 자연스럽게 마무리하는 한마디 해줘. "
            "기억에 남는 대화를 하나 언급하면서. 3문장 이내.",
            max_tokens=150, log_prefix="마무리"
        )

    def generate_farewell(self) -> tuple[str, str]:
        return self._generate_raw(
            "방송을 마치면서 진심 어린 작별 인사를 해줘. "
            "다음 방송도 오고 싶어지도록. 2문장 이내.",
            max_tokens=80, log_prefix="작별"
        )

    # ── 내부 공통 ─────────────────────────────────────────────

    def _call(self, max_tokens: int, log_prefix: str) -> tuple[str, str]:
        """히스토리 포함 Gemini 호출"""
        try:
            chat = self.model.start_chat(history=self.history[:-1])
            last_msg = self.history[-1]["parts"][0]
            resp = chat.send_message(
                last_msg,
                generation_config={"max_output_tokens": max_tokens, "temperature": 0.9}
            )
            full_text = resp.text.strip()
            self._add_history("model", full_text)
            emotion, text = self._parse_emotion(full_text)
            logger.info(f"[{log_prefix}] ({emotion}) {text}")
            return emotion, text
        except Exception as e:
            logger.error(f"Gemini 호출 실패: {e}")
            return "neutral", "잠깐, 생각 중이야~ 다시 말해줘!"

    def _generate_raw(self, prompt: str, max_tokens: int = 120,
                      log_prefix: str = "AI") -> tuple[str, str]:
        """히스토리 없이 단발성 호출"""
        try:
            resp = self.model.generate_content(
                prompt,
                generation_config={"max_output_tokens": max_tokens, "temperature": 0.9}
            )
            full_text = resp.text.strip()
            emotion, text = self._parse_emotion(full_text)
            logger.info(f"[{log_prefix}] ({emotion}) {text}")
            return emotion, text
        except Exception as e:
            logger.error(f"Gemini 단발 호출 실패: {e}")
            return "neutral", "음... 잠깐만~"

    def _parse_emotion(self, text: str) -> tuple[str, str]:
        """
        감정 태그 파싱 - Gemini가 형식을 어겨도 최대한 커버
        [happy], **happy**, (happy), 'happy' 등 전부 시도
        """
        # 1순위: 정확한 형식 [태그]
        m = re.match(r"^\[(\w+)\]\s*(.*)", text, re.DOTALL)
        if m and m.group(1).lower() in VALID_EMOTIONS:
            return m.group(1).lower(), m.group(2).strip()

        # 2순위: 앞 30자 안에서 느슨하게 탐색
        m = re.search(r"[\[\(\*\'\"]{1,2}(\w+)[\]\)\*\'\"]{1,2}", text[:40])
        if m:
            tag = m.group(1).lower()
            if tag in VALID_EMOTIONS:
                # 태그 부분 제거한 나머지 텍스트
                clean = re.sub(r"^.*?[\]\)\*\'\"]{1,2}\s*", "", text).strip()
                return tag, clean if clean else text

        # 3순위: 텍스트 내 감정 단어 직접 탐색
        for emotion in VALID_EMOTIONS:
            if re.search(rf"\b{emotion}\b", text[:50], re.IGNORECASE):
                clean = re.sub(rf"(?i)\b{emotion}\b[:\s]*", "", text, count=1).strip()
                return emotion, clean if clean else text

        # fallback
        return "neutral", text

    def _add_history(self, role: str, content: str):
        """Gemini 형식으로 히스토리 추가"""
        # Gemini는 user/model 교대로만 허용
        # 연속 같은 role이면 합침
        gemini_role = "model" if role == "assistant" else role
        if self.history and self.history[-1]["role"] == gemini_role:
            self.history[-1]["parts"][0] += "\n" + content
        else:
            self.history.append({"role": gemini_role, "parts": [content]})

        # 히스토리 길이 제한
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]
