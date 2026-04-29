"""
AI 버튜버 스트리머 - 메인 진입점

흐름:
  치지직 채팅 수신
  → Claude AI 응답 생성
  → VTube Studio 표정 트리거
  → ElevenLabs TTS 재생 (VoiceMeeter → VTube Studio 립싱크 → OBS 송출)
"""

import asyncio
import os
import time
from dotenv import load_dotenv

load_dotenv()

from src.utils.logger import setup_logger
from src.ai.brain import AIBrain
from src.chat.chzzk_client import ChzzkChatClient
from src.voice.tts import TTSEngine
from src.vtuber.vtube_studio import VTubeStudioClient

logger = setup_logger()


async def main():
    logger.info("=" * 50)
    logger.info(f"  AI 버튜버 '{os.getenv('STREAMER_NAME', '하나')}' 시작!")
    logger.info("=" * 50)

    # 설정값
    cooldown = float(os.getenv("RESPONSE_COOLDOWN", "8"))
    soliloquy_interval = float(os.getenv("SOLILOQUY_INTERVAL", "120"))

    # 컴포넌트 초기화
    chat_queue: asyncio.Queue = asyncio.Queue()
    brain = AIBrain()
    tts = TTSEngine()
    vtube = VTubeStudioClient()

    # TTS 설정
    tts.setup()

    # VTube Studio 연결 (실패해도 계속 실행)
    await vtube.connect()

    # 채팅 리스너 백그라운드 시작
    chat_client = ChzzkChatClient(queue=chat_queue)
    chat_task = asyncio.create_task(chat_client.start())

    last_response_time = 0.0
    last_soliloquy_time = time.time()

    logger.info("메인 루프 시작 — 채팅을 기다리는 중...")

    try:
        while True:
            now = time.time()

            # --- 채팅 처리 ---
            try:
                msg = chat_queue.get_nowait()
                if now - last_response_time >= cooldown:
                    emotion, response = brain.generate_response(msg.content, msg.username)
                    await vtube.trigger_emotion(emotion)
                    await tts.speak(response)
                    last_response_time = time.time()
                    last_soliloquy_time = time.time()  # 채팅 있으면 독백 타이머 리셋
                else:
                    remaining = cooldown - (now - last_response_time)
                    logger.debug(f"쿨다운 중 ({remaining:.1f}초 남음), 메시지 스킵: {msg.content[:20]}")

            except asyncio.QueueEmpty:
                # --- 독백 (채팅 없을 때) ---
                if now - last_soliloquy_time >= soliloquy_interval:
                    logger.info("채팅이 없어 독백 중...")
                    emotion, response = brain.generate_soliloquy()
                    await vtube.trigger_emotion(emotion)
                    await tts.speak(response)
                    last_soliloquy_time = time.time()

            await asyncio.sleep(0.1)

    except KeyboardInterrupt:
        logger.info("종료 신호 수신 (Ctrl+C)")
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
