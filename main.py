"""
AI 버튜버 스트리머 - 메인 진입점

기능:
  - 치지직 채팅 수신 (멀티 배치 처리)
  - Claude AI 응답 생성
  - 감정별 TTS 목소리 변화
  - VTube Studio 표정/움직임 제어
  - 자체 콘텐츠 (TMI / 고민 상담 / 토크 주제)
  - 방송 시작/종료 루틴 (시그니처 멘트)
"""

import asyncio
import os
import sys
import time
from dotenv import load_dotenv

load_dotenv()

from src.utils.logger import setup_logger
from src.ai.brain import AIBrain
from src.chat.chzzk_client import ChzzkChatClient
from src.chat.multi_handler import MultiChatHandler
from src.voice.tts import TTSEngine
from src.vtuber.vtube_studio import VTubeStudioClient
from src.content.self_content import SelfContentEngine
from src.broadcast.routines import BroadcastRoutines

logger = setup_logger()


async def main():
    name = os.getenv("STREAMER_NAME", "하나")
    logger.info("=" * 50)
    logger.info(f"  AI 버튜버 '{name}' 시작!")
    logger.info("=" * 50)

    # ── 설정값 로드 ───────────────────────────────────────────
    cooldown          = float(os.getenv("RESPONSE_COOLDOWN", "8"))
    soliloquy_interval = float(os.getenv("SOLILOQUY_INTERVAL", "120"))
    tmi_interval       = float(os.getenv("TMI_INTERVAL", "300"))

    # ── 컴포넌트 초기화 ───────────────────────────────────────
    chat_queue: asyncio.Queue = asyncio.Queue()
    brain  = AIBrain()
    tts    = TTSEngine()
    vtube  = VTubeStudioClient()

    tts.setup()
    await vtube.connect()

    multi_handler = MultiChatHandler(queue=chat_queue)
    self_content  = SelfContentEngine(brain=brain)
    routines      = BroadcastRoutines(brain=brain, tts=tts, vtube=vtube)

    # ── 채팅 리스너 시작 ──────────────────────────────────────
    chat_client = ChzzkChatClient(queue=chat_queue)
    chat_task   = asyncio.create_task(chat_client.start())

    # ── 방송 시작 루틴 ────────────────────────────────────────
    await routines.run_start()

    # ── 타이머 초기화 ─────────────────────────────────────────
    last_response_time  = time.time()
    last_soliloquy_time = time.time()
    last_tmi_time       = time.time()

    logger.info("메인 루프 시작 — 채팅 대기 중...")

    async def say(emotion: str, text: str):
        """표정 + TTS 동시 실행 헬퍼"""
        await vtube.trigger_emotion(emotion)
        await tts.speak(text, emotion)

    try:
        while True:
            now = time.time()

            # ── 배치 채팅 처리 ────────────────────────────────
            batch = await multi_handler.get_batch()

            if batch:
                if now - last_response_time < cooldown:
                    await asyncio.sleep(0.1)
                    continue

                # 고민 상담 감지 (첫 번째 메시지 기준)
                first = batch.messages[0]
                is_consultation = self_content.detect_consultation(
                    first.content, first.username
                )

                if is_consultation:
                    # 상담 모드 전용 응답
                    emotion, response = brain.generate_consultation_response(
                        first.content, first.username
                    )
                else:
                    # 일반 멀티 채팅 응답
                    self_content.end_consultation()
                    batch_prompt = multi_handler.format_for_ai(batch)
                    if len(batch.messages) == 1:
                        emotion, response = brain.generate_response(
                            first.content, first.username
                        )
                    else:
                        emotion, response = brain.generate_multi_response(batch_prompt)

                await say(emotion, response)

                # 방송 로그 기록
                for m in batch.messages:
                    routines.log_exchange(m.username, m.content, response)

                last_response_time  = time.time()
                last_soliloquy_time = time.time()

            else:
                # ── 채팅 없을 때 자체 콘텐츠 ─────────────────

                # TMI 타임
                if now - last_tmi_time >= tmi_interval:
                    import random
                    from src.content.self_content import TMI_TOPICS
                    topic = random.choice(TMI_TOPICS)
                    emotion, text = brain.generate_tmi(topic)
                    await say(emotion, text)
                    last_tmi_time       = time.time()
                    last_soliloquy_time = time.time()

                # 독백 / 토크 주제 전환
                elif now - last_soliloquy_time >= soliloquy_interval:
                    # 50% 확률로 새 토크 주제, 50% 독백
                    import random
                    if random.random() < 0.5:
                        emotion, text = brain.generate_topic_change()
                    else:
                        emotion, text = brain.generate_soliloquy()
                    await say(emotion, text)
                    last_soliloquy_time = time.time()

            await asyncio.sleep(0.1)

    except KeyboardInterrupt:
        logger.info("종료 신호 수신 (Ctrl+C)")

        # ── 방송 종료 루틴 ────────────────────────────────────
        await routines.run_end()

    except Exception as e:
        logger.error(f"메인 루프 오류: {e}", exc_info=True)
        raise

    finally:
        chat_task.cancel()
        await chat_client.stop()
        await vtube.close()
        logger.info("AI 버튜버 종료 완료")


if __name__ == "__main__":
    asyncio.run(main())
