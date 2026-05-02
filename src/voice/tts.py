"""
Edge TTS 엔진 (Microsoft - 완전 무료, API 키 불필요)

감정 태그에 따라 목소리 속도/피치가 달라짐
- excited/laughing → 빠르고 높게
- sad/crying       → 느리고 낮게
- sleepy           → 매우 느리게
- angry            → 빠르고 강하게
"""

import os
import io
import asyncio
import tempfile
import sounddevice as sd
import numpy as np
from src.utils.logger import setup_logger

logger = setup_logger()

# ── 감정별 Edge TTS 음성 세팅 ────────────────────────────────
# rate  : 속도 조절  (+20% = 20% 빠르게, -15% = 15% 느리게)
# pitch : 피치 조절  (+3Hz = 높게, -3Hz = 낮게)
# volume: 볼륨 조절  (+10% = 크게, -10% = 작게)
EMOTION_VOICE_MAP: dict[str, dict] = {
    "happy":     {"rate": "+8%",  "pitch": "+1Hz",  "volume": "+0%"},
    "excited":   {"rate": "+22%", "pitch": "+4Hz",  "volume": "+10%"},
    "laughing":  {"rate": "+18%", "pitch": "+3Hz",  "volume": "+8%"},
    "proud":     {"rate": "+5%",  "pitch": "+2Hz",  "volume": "+5%"},
    "sad":       {"rate": "-18%", "pitch": "-3Hz",  "volume": "-5%"},
    "crying":    {"rate": "-22%", "pitch": "-4Hz",  "volume": "-8%"},
    "lonely":    {"rate": "-15%", "pitch": "-2Hz",  "volume": "-5%"},
    "surprised": {"rate": "+15%", "pitch": "+5Hz",  "volume": "+8%"},
    "nervous":   {"rate": "+10%", "pitch": "+1Hz",  "volume": "-5%"},
    "scared":    {"rate": "+12%", "pitch": "+3Hz",  "volume": "-3%"},
    "angry":     {"rate": "+15%", "pitch": "+2Hz",  "volume": "+10%"},
    "disgusted": {"rate": "-5%",  "pitch": "-1Hz",  "volume": "+0%"},
    "confused":  {"rate": "-8%",  "pitch": "+1Hz",  "volume": "+0%"},
    "shy":       {"rate": "-10%", "pitch": "-1Hz",  "volume": "-8%"},
    "sleepy":    {"rate": "-28%", "pitch": "-5Hz",  "volume": "-10%"},
    "bored":     {"rate": "-15%", "pitch": "-2Hz",  "volume": "-5%"},
    "neutral":   {"rate": "+0%",  "pitch": "+0Hz",  "volume": "+0%"},
}


class TTSEngine:
    def __init__(self):
        self.voice        = os.getenv("TTS_VOICE", "ko-KR-SunHiNeural")
        self.output_device = os.getenv("AUDIO_OUTPUT_DEVICE", "")
        self._device_index = None

    def setup(self):
        try:
            import edge_tts  # noqa: F401
            self._device_index = self._find_device()
            logger.info(f"Edge TTS 초기화 완료 (목소리: {self.voice})")
            logger.info(f"오디오 출력: {self.output_device or '기본 장치'}")
        except ImportError:
            logger.error("edge-tts 미설치! `pip install edge-tts` 필요")
            raise

    def _find_device(self) -> int | None:
        if not self.output_device:
            return None
        for i, d in enumerate(sd.query_devices()):
            if self.output_device.lower() in d["name"].lower() and d["max_output_channels"] > 0:
                logger.info(f"오디오 장치: [{i}] {d['name']}")
                return i
        logger.warning(f"'{self.output_device}' 장치 없음 → 기본 장치 사용")
        return None

    async def speak(self, text: str, emotion: str = "neutral"):
        """감정에 맞는 목소리로 TTS 재생 (비동기)"""
        settings = EMOTION_VOICE_MAP.get(emotion, EMOTION_VOICE_MAP["neutral"])
        try:
            import edge_tts
            communicate = edge_tts.Communicate(
                text=text,
                voice=self.voice,
                rate=settings["rate"],
                pitch=settings["pitch"],
                volume=settings["volume"],
            )

            # 메모리에 오디오 생성
            audio_bytes = b""
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_bytes += chunk["data"]

            if not audio_bytes:
                logger.warning("TTS 오디오 데이터 없음")
                return

            # 재생
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._play, audio_bytes)
            logger.debug(f"TTS [{emotion}] 재생 완료: {text[:30]}...")

        except Exception as e:
            logger.error(f"TTS 실패: {e}")

    def _play(self, audio_bytes: bytes):
        """bytes → numpy array 변환 후 재생"""
        try:
            import soundfile as sf
            data, sr = sf.read(io.BytesIO(audio_bytes), dtype="float32")
            sd.play(data, samplerate=sr, device=self._device_index)
            sd.wait()
        except Exception:
            try:
                from pydub import AudioSegment
                seg = AudioSegment.from_mp3(io.BytesIO(audio_bytes))
                samples = np.array(seg.get_array_of_samples(), dtype=np.float32) / 2**15
                if seg.channels == 2:
                    samples = samples.reshape(-1, 2)
                sd.play(samples, samplerate=seg.frame_rate, device=self._device_index)
                sd.wait()
            except Exception as e:
                logger.error(f"오디오 재생 실패: {e}")

    def list_devices(self):
        """사용 가능한 오디오 출력 장치 출력"""
        print("\n=== 오디오 출력 장치 ===")
        for i, d in enumerate(sd.query_devices()):
            if d["max_output_channels"] > 0:
                print(f"[{i}] {d['name']}")
        print("\n.env에 이렇게 입력:")
        print("AUDIO_OUTPUT_DEVICE=VoiceMeeter Input\n")

    def list_voices(self):
        """사용 가능한 한국어 목소리 출력"""
        print("\n=== 한국어 Edge TTS 목소리 ===")
        print("ko-KR-SunHiNeural   - 여성 (밝고 또렷한)")
        print("ko-KR-InJoonNeural  - 남성 (차분하고 안정적)")
        print("\n.env에 이렇게 입력:")
        print("TTS_VOICE=ko-KR-SunHiNeural\n")
