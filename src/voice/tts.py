import os
import io
import asyncio
import sounddevice as sd
import numpy as np
from src.utils.logger import setup_logger

logger = setup_logger()


class TTSEngine:
    """
    ElevenLabs TTS 엔진
    생성된 음성을 VoiceMeeter 가상 오디오 장치로 출력 (VTube Studio 립싱크용)
    """

    def __init__(self):
        self.api_key = os.getenv("ELEVENLABS_API_KEY")
        self.voice_id = os.getenv("ELEVENLABS_VOICE_ID")
        self.output_device = os.getenv("AUDIO_OUTPUT_DEVICE", "")
        self.client = None
        self._device_index = None

    def setup(self):
        """ElevenLabs 클라이언트 초기화"""
        try:
            from elevenlabs.client import ElevenLabs
            self.client = ElevenLabs(api_key=self.api_key)
            self._device_index = self._find_device()
            logger.info(f"TTS 엔진 초기화 완료 (출력 장치: {self.output_device or '기본값'})")
        except ImportError:
            logger.error("elevenlabs 미설치! `pip install elevenlabs` 실행 필요")
            raise

    def _find_device(self) -> int | None:
        """출력 장치 인덱스 검색"""
        if not self.output_device:
            return None

        devices = sd.query_devices()
        for i, device in enumerate(devices):
            if self.output_device.lower() in device["name"].lower() and device["max_output_channels"] > 0:
                logger.info(f"오디오 출력 장치 발견: [{i}] {device['name']}")
                return i

        logger.warning(f"'{self.output_device}' 장치를 찾지 못했습니다. 기본 장치를 사용합니다.")
        return None

    async def speak(self, text: str):
        """텍스트를 음성으로 변환 후 재생 (비동기)"""
        if not self.client:
            logger.warning("TTS 엔진이 초기화되지 않았습니다.")
            return

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._speak_sync, text)

    def _speak_sync(self, text: str):
        """동기 TTS 재생"""
        try:
            audio_data = self.client.generate(
                text=text,
                voice=self.voice_id,
                model="eleven_multilingual_v2"
            )

            # bytes로 수집
            audio_bytes = b"".join(audio_data)

            # mp3 → numpy array 변환
            audio_array, sample_rate = self._decode_audio(audio_bytes)

            # 재생
            sd.play(audio_array, samplerate=sample_rate, device=self._device_index)
            sd.wait()  # 재생 완료까지 대기

            logger.debug(f"TTS 재생 완료: {text[:30]}...")

        except Exception as e:
            logger.error(f"TTS 재생 실패: {e}")

    def _decode_audio(self, audio_bytes: bytes) -> tuple:
        """MP3 bytes → numpy array 변환"""
        try:
            import soundfile as sf
            buffer = io.BytesIO(audio_bytes)
            data, sample_rate = sf.read(buffer, dtype="float32")
            return data, sample_rate
        except Exception:
            # fallback: pydub 시도
            try:
                from pydub import AudioSegment
                buffer = io.BytesIO(audio_bytes)
                segment = AudioSegment.from_mp3(buffer)
                samples = np.array(segment.get_array_of_samples(), dtype=np.float32)
                samples /= 2 ** 15  # 정규화
                if segment.channels == 2:
                    samples = samples.reshape(-1, 2)
                return samples, segment.frame_rate
            except Exception as e2:
                logger.error(f"오디오 디코딩 실패: {e2}")
                return np.zeros(1000, dtype=np.float32), 44100

    def list_devices(self):
        """사용 가능한 오디오 출력 장치 출력 (설정 도우미)"""
        print("\n=== 사용 가능한 오디오 출력 장치 ===")
        devices = sd.query_devices()
        for i, device in enumerate(devices):
            if device["max_output_channels"] > 0:
                print(f"[{i}] {device['name']}")
        print("=====================================\n")
        print(".env의 AUDIO_OUTPUT_DEVICE에 장치 이름 일부를 입력하세요.")
        print("예: AUDIO_OUTPUT_DEVICE=VoiceMeeter Input")
