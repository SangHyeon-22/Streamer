import os
import re
from typing import Optional
import anthropic
from src.utils.logger import setup_logger

logger = setup_logger()

SYSTEM_PROMPT = """
너는 '{name}'이라는 이름의 치지직 버튜버야.
성격: 밝고 장난기 있고 솔직해. 시청자들과 친근하게 대화하는 걸 좋아해.
관심사: 게임, 음악, 먹방, 일상 토크.

규칙:
1. 답변은 반드시 2~3문장 이내로 짧게 해.
2. 답변 맨 앞에 현재 감정 태그를 반드시 붙여. 아래 15가지 중 가장 적합한 것 하나를 골라:

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

예시:
- 시청자: "오늘 뭐해?"
  응답: "[happy] 오늘은 게임하면서 채팅 보고 있지~ 같이 놀자! 😊"
- 시청자: "배고프다"
  응답: "[excited] 나도!! 치킨 먹고 싶어서 미칠 것 같아!! 🍗"
- 시청자: "귀신 얘기 해줘"
  응답: "[scared] 으아악 그건 좀... 나 귀신 진짜 무서워ㅠㅠ 하지마!!!"
- 시청자: "오늘 방송 재미없다"
  응답: "[sad] ...그렇구나. 더 재밌게 해볼게 ㅠㅠ 미안해"
"""


class AIBrain:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.streamer_name = os.getenv("STREAMER_NAME", "하나")
        self.max_history = int(os.getenv("MAX_HISTORY", "20"))
        self.history: list[dict] = []
        self.system = SYSTEM_PROMPT.format(name=self.streamer_name)

    def generate_response(self, message: str, username: str) -> tuple[str, str]:
        """
        채팅 메시지에 대한 AI 응답 생성
        Returns: (emotion_tag, response_text)
        """
        self.history.append({
            "role": "user",
            "content": f"[{username}]: {message}"
        })

        # 히스토리 길이 제한
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]

        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=150,
                system=self.system,
                messages=self.history
            )
            full_text = response.content[0].text.strip()
            self.history.append({"role": "assistant", "content": full_text})

            # 감정 태그 추출
            emotion, text = self._parse_emotion(full_text)
            logger.info(f"[AI] ({emotion}) {text}")
            return emotion, text

        except Exception as e:
            logger.error(f"AI 응답 생성 실패: {e}")
            return "neutral", "잠깐, 생각 중이야~ 다시 말해줘!"

    def generate_soliloquy(self) -> tuple[str, str]:
        """채팅이 없을 때 혼자 중얼거리기"""
        prompt = "채팅이 없어서 혼자 중얼거리는 중이야. 자연스럽게 뭔가 해봐."
        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=100,
                system=self.system,
                messages=[{"role": "user", "content": prompt}]
            )
            full_text = response.content[0].text.strip()
            emotion, text = self._parse_emotion(full_text)
            logger.info(f"[독백] ({emotion}) {text}")
            return emotion, text
        except Exception as e:
            logger.error(f"독백 생성 실패: {e}")
            return "neutral", "음... 오늘 날씨 좋다~"

    def _parse_emotion(self, text: str) -> tuple[str, str]:
        """감정 태그 파싱: '[happy] 텍스트' → ('happy', '텍스트')"""
        match = re.match(r"^\[(\w+)\]\s*(.*)", text, re.DOTALL)
        if match:
            return match.group(1), match.group(2).strip()
        return "neutral", text
