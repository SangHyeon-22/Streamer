"""
ElevenLabs TTS 엔진

감정 태그에 따라 목소리 톤/속도/안정성이 달라짐
- excited/laughing → 빠르고 불안정(더 표현적)
- sad/crying       → 느리고 안정적(잔잔하게)
- shy/sleepy       → 부드럽고 조용하게
- angry/scared     → 강하고 불안정하게
"""

import os
import io
import asyncio
import sounddevice as sd
import numpy as np
from src.utils.logger import setup_logger

logger = setup_logger()

# ── 감정별 ElevenLabs Voice Settings ─────────────────────────
# stability     : 0.0(표현적/불안정) ~ 1.0(안정적/단조)
# similarity    : 원본 목소리 유사도
# style         : 스타일 과장 (0.0 ~ 1.0)
# speed         : 말하기 속도 (0.7 ~ 1.3)
EMOTION_VOICE_MAP: dict[str, dict] = {
    "happy":     {"stability": 0.50, "similarity_boost": 0.80, "style": 0.55, "speed": 1.05},
    "excited":   {"stability": 0.25, "similarity_boost": 0.75, "style": 0.85, "speed": 1.20},
    "laughing":  {"stability": 0.15, "similarity_boost": 0.70, "style": 0.90, "speed": 1.15},
    "proud":     {"stability": 0.60, "similarity_boost": 0.85, "style": 0.50, "speed": 1.00},
    "sad":       {"stability": 0.80, "similarity_boost": 0.90, "style": 0.15, "speed": 0.82},
    "crying":    {"stability": 0.70, "similarity_boost": 0.88, "style": 0.25, "speed": 0.78},
    "lonely":    {"stability": 0.75, "similarity_boost": 0.88, "style": 0.18, "speed": 0.85},
    "surprised": {"stability": 0.28, "similarity_boost": 0.78, "style": 0.75, "speed": 1.08},
    "nervous":   {"stability": 0.35, "similarity_boost": 0.78, "style": 0.50, "speed": 1.05},
    "scared":    {"stability": 0.30, "similarity_boost": 0.78, "style": 0.65, "speed": 1.12},
    "angry":     {"stability": 0.28, "similarity_boost": 0.80, "style": 0.80, "speed": 1.10},
    "disgusted": {"stability": 0.38, "similarity_boost": 0.80, "style": 0.60, "speed": 0.95},
    "confused":  {"stability": 0.48, "similarity_boost": 0.80, "style": 0.42, "speed": 0.92},
    "shy":       {"stability": 0.82, "similarity_boost": 0.90, "style": 0.18, "speed": 0.88},
    "sleepy":    {"stability": 0.90, "similarity_boost": 0.92, "style": 0.08, "speed": 0.72},
    "bored":     {"stability": 0.85, "similarity_boost": 0.90, "style": 0.10, "speed": 0.80},
    "neutral":   {"stability": 0.60, "similarity_boost": 0.82, "style": 0.30, "speed": 1.00},
}


class TTSEngine:
    def __init__(self):
        self.api_key = os.getenv("ELEVENLABS_API_KEY")
        self.voice_id = os.getenv("ELEVENLABS_VOICE_ID")
        self.output_device = os.getenv("AUDIO_OUTPUT_DEVICE", "")
        self.client = None
        self._device_index = None

    def setup(self):
        try:
            from elevenlabs.client import ElevenLabs
            self.client = ElevenLabs(api_key=self.api_key)
            self._device_index = self._find_device()
            logger.info(f"TTS 초기화 완료 (장치: {self.output_device or '기본값'})")
        except ImportError:
            logger.error("elevenlabs 미설치! `pip install elevenlabs` 필요")
            raise

    def _find_device(self) -> int | None:
        if not self.output_device:
            return None
        for i, d in enumerate(sd.query_devices()):
            if self.output_device.lower() in d["name"].lower() and d["max_output_channels"] > 0:
                logger.info(f"오디오 장치: [{i}] {d['name']}")
                return i
        logger.warning(f"'{self.output_device}' 없음. 기본 장치 사용")
        return None

    async def speak(self, text: str, emotion: str = "neutral"):
        """감정에 맞는 목소리 세팅으로 TTS 재생"""
        if not self.client:
            return
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._speak_sync, text, emotion)

    def _speak_sync(self, text: str, emotion: str):
        settings = EMOTION_VOICE_MAP.get(emotion, EMOTION_VOICE_MAP["neutral"])
        try:
            from elevenlabs import VoiceSettings
            audio_data = self.client.generate(
                text=text,
                voice=self.voice_id,
                model="eleven_multilingual_v2",
                voice_settings=VoiceSettings(
                    stability=settings["stability"],
                    similarity_boost=settings["similarity_boost"],
                    style=settings["style"],
                    use_speaker_boost=True,
                )
            )
            audio_bytes = b"".join(audio_data)
            audio_array, sample_rate = self._decode_audio(audio_bytes)

            # speed 조절: 리샘플링으로 구현
            target_speed = settings.get("speed", 1.0)
            if target_speed != 1.0:
                audio_array, sample_rate = self._adjust_speed(audio_array, sample_rate, target_speed)

            sd.play(audio_array, samplerate=sample_rate, device=self._device_index)
            sd.wait()
            logger.debug(f"TTS [{emotion}] 재생 완료: {text[:30]}...")
        except Exception as e:
            logger.error(f"TTS 실패: {e}")

    def _adjust_speed(self, audio: np.ndarray, sr: int, speed: float):
        """속도 조절 - 샘플레이트 변조 방식 (간단하고 빠름)"""
        new_sr = int(sr * speed)
        return audio, new_sr

    def _decode_audio(self, audio_bytes: bytes) -> tuple:
        try:
            import soundfile as sf
            data, sr = sf.read(io.BytesIO(audio_bytes), dtype="float32")
            return data, sr
        except Exception:
            try:
                from pydub import AudioSegment
                seg = AudioSegment.from_mp3(io.BytesIO(audio_bytes))
                samples = np.array(seg.get_array_of_samples(), dtype=np.float32) / 2**15
                if seg.channels == 2:
                    samples = samples.reshape(-1, 2)
                return samples, seg.frame_rate
            except Exception as e:
                logger.error(f"오디오 디코딩 실패: {e}")
                return np.zeros(1000, dtype=np.float32), 44100

    def list_devices(self):
        print("\n=== 오디오 출력 장치 ===")
        for i, d in enumerate(sd.query_devices()):
            if d["max_output_channels"] > 0:
                print(f"[{i}] {d['name']}")
        print("AUDIO_OUTPUT_DEVICE=VoiceMeeter Input  ← .env에 이렇게 입력\n")
