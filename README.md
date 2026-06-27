# YouTube 한국사 다큐멘터리 자동화 파이프라인

매일 한국 역사를 주제로 한 5~10분 중국어 다큐멘터리 영상을 자동 생성하여 YouTube에 업로드하는 파이프라인입니다.

## 구성 요소

| 단계 | 사용 기술 |
|---|---|
| 대본 (제목/설명/태그/장면별 내레이션+이미지프롬프트) | OpenAI GPT (`pipeline/script_gen.py`) |
| 장면 이미지 | OpenAI DALL-E 3 (`pipeline/image_gen.py`) |
| 내레이션 음성 (중국어, 차분한 남성) | ElevenLabs TTS + 타임스탬프 (`pipeline/tts.py`) |
| 자막(SRT) | ElevenLabs 문자 단위 타임스탬프 기반 자동 생성 (`pipeline/subtitles.py`) |
| 영상 합성 (Ken Burns 줌/패닝 + 자막 합성) | ffmpeg (`pipeline/video.py`) |
| 썸네일 | DALL-E + PIL 텍스트 오버레이 (`pipeline/thumbnail.py`) |
| 업로드 | YouTube Data API v3 (`pipeline/youtube_upload.py`) |
| 매일 실행 | GitHub Actions 스케줄 (`.github/workflows/daily.yml`) |

## 로컬 설정

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Ubuntu/Debian 계열
sudo apt-get install -y ffmpeg fonts-noto-cjk
```

`.env` 파일 생성 (`.env.example` 참고):

```
OPENAI_API_KEY=sk-...
ELEVENLABS_API_KEY=...
ELEVENLABS_VOICE_ID=onwK4e9ZLuTAKqWW03F9   # Daniel - Steady Broadcaster (차분한 남성, 다국어 지원)
```

## 1. 샘플 영상 생성 (업로드 없이 결과 확인)

```bash
python main.py sample
```

`output/<timestamp>/final.mp4` 에 완성된 영상, `thumbnail.jpg` 에 썸네일, `script.json` 에 생성된 대본이 저장됩니다.
결과를 확인한 뒤 만족스러우면 매일 자동화를 활성화하세요.

특정 주제로 테스트하려면:

```bash
python main.py sample --topic "世宗大王与韩文的创制"
```

## 2. YouTube 업로드 1회 인증 (최초 1회만 직접 진행)

1. [Google Cloud Console](https://console.cloud.google.com/) 에서 프로젝트 생성 → YouTube Data API v3 활성화
2. OAuth 동의 화면 구성 (테스트 사용자에 본인 계정 추가)
3. OAuth 클라이언트 ID 생성 (애플리케이션 유형: **데스크톱 앱**) → JSON 다운로드
4. 다운로드한 파일을 `credentials/client_secret.json` 으로 저장
5. 아래 명령으로 1회 로그인 (브라우저 창이 열림):

```bash
python -m pipeline.youtube_upload --authorize
```

   인증이 완료되면 `credentials/token.json` 이 생성됩니다. 이 파일이 있으면 이후 모든 업로드는 완전 자동으로 진행됩니다(액세스 토큰은 자동 갱신됩니다).

## 3. 매일 자동 실행 (GitHub Actions)

`.github/workflows/daily.yml` 이 매일 01:00 UTC(한국시간 오전 10시)에 실행되어 영상 생성 + 업로드를 수행합니다.

GitHub 저장소 **Settings → Secrets and variables → Actions** 에 아래 Secret을 등록하세요:

| Secret 이름 | 값 |
|---|---|
| `OPENAI_API_KEY` | OpenAI API 키 |
| `ELEVENLABS_API_KEY` | ElevenLabs API 키 |
| `ELEVENLABS_VOICE_ID` | (선택) 보이스 ID, 기본값 사용 시 생략 가능 |
| `YOUTUBE_CLIENT_SECRET_JSON` | `credentials/client_secret.json` 파일 내용 전체 |
| `YOUTUBE_TOKEN_JSON` | 1회 인증 후 생성된 `credentials/token.json` 파일 내용 전체 |

등록 후에는 매일 자동으로 새로운 주제의 영상이 생성되어 업로드됩니다. 수동 실행은 Actions 탭에서 "Run workflow" 로도 가능합니다 (주제/공개범위 직접 지정 가능).

## 주제 관리

`pipeline/topics.py` 의 `TOPIC_BANK` 목록에서 매일 자동으로 순환 선택되며, 이미 사용한 주제는 `pipeline/used_topics.json` 에 기록되어 중복을 피합니다. 목록을 모두 사용하면 처음부터 다시 순환합니다. 필요시 주제를 추가/수정하세요.

## 주의사항

- DALL-E 정지 이미지 + Ken Burns(줌/패닝) 효과로 영상처럼 보이게 합성하며, 실제 AI 영상 클립 생성 API는 비용 문제로 사용하지 않습니다.
- 영상 길이는 대본 분량에 따라 자동으로 5~10분 범위로 조절됩니다.
- 업로드 공개범위는 기본 `public`이며, 검수가 필요하면 `--privacy unlisted` 또는 `private` 사용을 권장합니다.
