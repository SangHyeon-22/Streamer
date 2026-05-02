"""
멀티 채팅 핸들러

- 짧은 시간 윈도우 안에 들어온 채팅 여러 개를 묶어서 한 번에 처리
- 비슷한 질문 그룹핑
- 무시된 시청자 추적 → 챙겨주기
"""

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from src.utils.logger import setup_logger

logger = setup_logger()

WINDOW_SECONDS = 2.5   # 메시지를 모을 시간 윈도우
MAX_BATCH      = 5     # 한 번에 묶을 최대 메시지 수
IGNORED_LIMIT  = 3     # 이 횟수 이상 무시된 시청자는 우선 챙김


@dataclass
class ChatMessage:
    username: str
    content: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class ChatBatch:
    """한 번에 AI에게 전달할 채팅 묶음"""
    messages: list[ChatMessage]
    ignored_user: str | None = None   # 오래 무시된 시청자


class MultiChatHandler:
    def __init__(self, queue: asyncio.Queue):
        self.queue = queue
        self._buffer: list[ChatMessage] = []
        self._last_flush = time.time()
        self._ignore_count: dict[str, int] = {}   # 닉네임 → 무시 횟수
        self._recent_responders: deque = deque(maxlen=10)  # 최근 응답한 닉네임들

    async def get_batch(self) -> ChatBatch | None:
        """
        큐에서 메시지를 긁어모아 윈도우가 끝나면 배치로 반환.
        반환값이 None이면 아직 수집 중.
        """
        now = time.time()

        # 큐에서 꺼내기
        while True:
            try:
                msg = self.queue.get_nowait()
                self._buffer.append(msg)
            except asyncio.QueueEmpty:
                break

        if not self._buffer:
            return None

        # 윈도우 시간이 지났거나 버퍼가 꽉 찼으면 flush
        elapsed = now - self._last_flush
        if elapsed < WINDOW_SECONDS and len(self._buffer) < MAX_BATCH:
            return None

        return self._flush()

    def _flush(self) -> ChatBatch:
        """버퍼를 비우고 배치 반환"""
        batch_msgs = self._buffer[:MAX_BATCH]
        self._buffer = self._buffer[MAX_BATCH:]
        self._last_flush = time.time()

        # 무시 카운트 업데이트
        responded_names = {m.username for m in batch_msgs}
        for name in responded_names:
            self._ignore_count.pop(name, None)  # 응답받으면 카운트 초기화
            self._recent_responders.append(name)

        # 응답 못 받은 사람 카운트 증가
        all_names_in_queue = [m.username for m in self._buffer]
        for name in all_names_in_queue:
            if name not in responded_names:
                self._ignore_count[name] = self._ignore_count.get(name, 0) + 1

        # 오래 무시된 시청자 찾기
        ignored_user = self._find_most_ignored(responded_names)

        logger.debug(f"배치 생성: {len(batch_msgs)}개 메시지"
                     + (f" (무시됐던 {ignored_user} 챙김)" if ignored_user else ""))
        return ChatBatch(messages=batch_msgs, ignored_user=ignored_user)

    def _find_most_ignored(self, current_batch_names: set) -> str | None:
        """IGNORED_LIMIT 이상 무시된 시청자 중 가장 오래된 사람 반환"""
        candidates = {
            name: count
            for name, count in self._ignore_count.items()
            if count >= IGNORED_LIMIT and name not in current_batch_names
        }
        if not candidates:
            return None
        return max(candidates, key=candidates.get)

    def format_for_ai(self, batch: ChatBatch) -> str:
        """
        배치를 AI 프롬프트용 문자열로 변환
        예: "[유저A]: 안녕\n[유저B]: 뭐해\n[유저C]: 배고프다"
        """
        lines = [f"[{m.username}]: {m.content}" for m in batch.messages]
        prompt = "\n".join(lines)

        if batch.ignored_user:
            prompt += f"\n\n(참고: {batch.ignored_user}님이 아까부터 채팅 쳤는데 아직 못 챙겼어. 자연스럽게 한 번 언급해줘.)"

        return prompt

    def mark_responded(self, usernames: list[str]):
        """응답한 유저 무시 카운트 초기화"""
        for name in usernames:
            self._ignore_count.pop(name, None)
