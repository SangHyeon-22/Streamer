# 🎭 AI 버튜버 스트리머

치지직(Chzzk) 플랫폼 기반 AI 버튜버 자동 방송 시스템

## 흐름

```
치지직 채팅 수신 → Claude AI 응답 → ElevenLabs TTS → VTube Studio 립싱크 → OBS 송출
```

## 빠른 시작

### 1. 의존성 설치

```bash
pip install -r requirements.txt
```

### 2. 환경변수 설정

```bash
cp .env.example .env
# .env 파일을 열어 API 키 입력
```

필요한 키:
- `ANTHROPIC_API_KEY` — [Anthropic Console](https://console.anthropic.com)
- `ELEVENLABS_API_KEY` + `ELEVENLABS_VOICE_ID` — [ElevenLabs](https://elevenlabs.io)
- `CHZZK_NID_AUT` + `CHZZK_NID_SES` — 네이버 로그인 쿠키 (아래 참고)
- `CHZZK_CHANNEL_ID` — 치지직 채널 ID

### 3. 네이버 쿠키 추출 방법

1. 크롬에서 [chzzk.naver.com](https://chzzk.naver.com) 로그인
2. F12 → Application → Cookies → `https://nid.naver.com`
3. `NID_AUT`, `NID_SES` 값 복사 → `.env`에 입력

### 4. VTube Studio 설정

1. VTube Studio 실행
2. Settings → Plugins → Enable 체크
3. 핫키 이름을 다음과 같이 설정:
   - `emotion_happy`, `emotion_sad`, `emotion_surprised`, `emotion_angry`, `emotion_neutral`

### 5. 오디오 라우팅 (립싱크용)

```
ElevenLabs 출력 → VoiceMeeter Input → VTube Studio 마이크 입력 → 립싱크
```

오디오 장치 목록 확인:
```bash
python -c "from src.voice.tts import TTSEngine; TTSEngine().list_devices()"
```

### 6. 실행

```bash
# 일반 실행
python main.py

# 무중단 실행 (1주일 방송용)
python run_forever.py

# Docker로 실행
docker-compose up -d
```

## 프로젝트 구조

```
Streamer/
├── main.py                   # 메인 루프
├── run_forever.py            # 자동 재시작 래퍼
├── docker-compose.yml        # 1주일 무중단 운영
└── src/
    ├── ai/brain.py           # Claude AI 두뇌
    ├── chat/chzzk_client.py  # 치지직 채팅 수신
    ├── voice/tts.py          # ElevenLabs TTS
    ├── vtuber/vtube_studio.py # VTube Studio 연동
    └── utils/logger.py       # 로깅
```

## 주요 설정값 (.env)

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `STREAMER_NAME` | `하나` | 버튜버 이름 |
| `RESPONSE_COOLDOWN` | `8` | 채팅 응답 쿨다운 (초) |
| `SOLILOQUY_INTERVAL` | `120` | 채팅 없을 때 독백 간격 (초) |
| `AUDIO_OUTPUT_DEVICE` | 기본값 | VoiceMeeter 장치 이름 |
