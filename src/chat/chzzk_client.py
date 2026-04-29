import os
import asyncio
from dataclasses import dataclass
from src.utils.logger import setup_logger

logger = setup_logger()


@dataclass
class ChatMessage:
    username: str
    content: str


class ChzzkChatClient:
    """
    치지직 채팅 클라이언트
    chzzkpy 라이브러리를 사용해 실시간 채팅 수신
    """

    def __init__(self, queue: asyncio.Queue):
        self.queue = queue
        self.channel_id = os.getenv("CHZZK_CHANNEL_ID")
        self.nid_aut = os.getenv("CHZZK_NID_AUT")
        self.nid_ses = os.getenv("CHZZK_NID_SES")
        self.client = None

    async def start(self):
        """채팅 리스너 시작"""
        try:
            from chzzkpy.chat import ChatClient, ChatMessage as ChzzkMessage

            self.client = ChatClient(
                channel_id=self.channel_id,
                nid_aut=self.nid_aut,
                nid_ses=self.nid_ses
            )

            @self.client.event
            async def on_chat(message: ChzzkMessage):
                if not message.content or not message.profile:
                    return

                username = message.profile.nickname or "익명"
                content = message.content.strip()

                if not content:
                    return

                logger.info(f"[채팅] {username}: {content}")
                await self.queue.put(ChatMessage(username=username, content=content))

            @self.client.event
            async def on_connect():
                logger.info(f"치지직 채팅 연결 완료 (채널: {self.channel_id})")

            @self.client.event
            async def on_disconnect():
                logger.warning("치지직 채팅 연결 끊김, 재연결 시도 중...")

            await self.client.connect()

        except ImportError:
            logger.error("chzzkpy 미설치! `pip install chzzkpy` 실행 필요")
            raise
        except Exception as e:
            logger.error(f"치지직 채팅 연결 실패: {e}")
            raise

    async def stop(self):
        if self.client:
            await self.client.close()
            logger.info("치지직 채팅 클라이언트 종료")
