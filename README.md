# YouTube 한국사 다큐멘터리 자동화 파이프라인

매일 한국 역사를 주제로 한 5~10분 아랍어(MSA) 다큐멘터리 영상을 자동 생성하여 YouTube에 공개(public)로 업로드하는 파이프라인입니다.

## 구성 요소

| 단계 | 사용 기술 |
|---|---|
| 대본 (제목/설명/태그/장면별 내레이션은 아랍어, 이미지프롬프트는 영어) | OpenAI GPT (`pipeline/script_gen.py`) |
| 장면 이미지 | OpenAI gpt-image-1 (`pipeline/image_gen.py`) |
| 내레이션 음성 (아랍어, 남성 보이스 "Mustafa") | ElevenLabs TTS + 타임스탬프 (`pipeline/tts.py`) |
| 자막(SRT, 아랍어) | ElevenLabs 문자 단위 타임스탬프 기반 자동 생성 (`pipeline/subtitles.py`) |
| 영상 합성 (Ken Burns 줌/패닝 + Amiri 폰트 자막 합성) | ffmpeg (`pipeline/video.py`) |
| 썸네일 (아랍어 제목, Amiri 폰트) | gpt-image-1 + PIL 텍스트 오버레이 (`pipeline/thumbnail.py`) |
| 업로드 (자동, 확인 절차 없음, 기본 공개범위 public) | YouTube Data API v3 (`pipeline/youtube_upload.py`) |
| 매일 실행 | GitHub Actions 스케줄 (`.github/workflows/daily.yml`) |

## 로컬 설정

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Ubuntu/Debian 계열
sudo apt-get install -y ffmpeg fonts-hosny-amiri
```

`.env` 파일 생성 (`.env.example` 참고):

```
OPENAI_API_KEY=sk-...
ELEVENLABS_API_KEY=...
ELEVENLABS_VOICE_ID=...   # ElevenLabs Voice Library에서 아랍어 남성 보이스 "Mustafa"의 ID를 찾아 입력
```

## 1. 샘플 영상 생성 (업로드 없이 결과 확인)

```bash
python main.py --no-upload
```

`output/<timestamp>/final.mp4` 에 완성된 영상, `thumbnail.jpg` 에 썸네일, `script.json` 에 생성된 대본이 저장됩니다.
결과를 확인한 뒤 만족스러우면 매일 자동화를 활성화하세요.

특정 주제로 테스트하려면:

```bash
python main.py --no-upload --topic "世宗大王与韩文的创制"
```

업로드까지 포함해서 바로 실행하려면(확인 절차 없이 자동으로 public 업로드):

```bash
python main.py
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
| `ELEVENLABS_VOICE_ID` | 아랍어 남성 보이스 "Mustafa"의 ElevenLabs Voice ID |
| `YOUTUBE_CLIENT_SECRET_JSON` | `credentials/client_secret.json` 파일 내용 전체 |
| `YOUTUBE_TOKEN_JSON` | 1회 인증 후 생성된 `credentials/token.json` 파일 내용 전체 |

등록 후에는 매일 자동으로 새로운 주제의 영상이 생성되어 업로드됩니다. 수동 실행은 Actions 탭에서 "Run workflow" 로도 가능합니다 (주제/공개범위 직접 지정 가능).

## 주제 관리

고정 주제 목록은 사용하지 않습니다. `pipeline/trends.py` 가 매일 Google Trends(일별 인기 검색어 RSS)와 Reddit(`r/all` 일간 인기글)에서 실시간 트렌드를 가져와 그중 하나를 주제로 선택합니다. 이미 사용한 주제는 `pipeline/used_topics.json` 에 기록되어 중복을 피합니다. 두 소스 모두에서 가져올 트렌드가 없으면(또는 전부 이미 사용됨) 파이프라인은 샘플 데이터로 대체하지 않고 오류를 발생시킵니다.

## 주의사항

- AI 정지 이미지 + Ken Burns(줌/패닝) 효과로 영상처럼 보이게 합성하며, 실제 AI 영상 클립 생성 API는 비용 문제로 사용하지 않습니다.
- 영상 길이는 대본 분량에 따라 자동으로 5~10분 범위로 조절됩니다.
- 업로드는 확인 절차 없이 영상 생성 후 바로 진행되며, 공개범위는 기본 `public`입니다. 검수가 필요하면 `--privacy unlisted`/`private` 또는 `--no-upload`를 사용하세요.
