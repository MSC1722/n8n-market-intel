# 자격증명 & 연동 세팅

n8n에서 **Credentials** → **Add credential** 로 4개를 등록합니다. 워크플로 JSON에는 자격증명 ID만 들어가고 키 자체는 절대 들어가지 않습니다 — 그래서 이 저장소를 공개해도 안전합니다.

| # | Credential 타입 | 쓰는 노드 |
|---|---|---|
| 1 | OpenAI | Summarize & Classify |
| 2 | Header Auth | Enrich via Custom API |
| 3 | Google Sheets OAuth2 API | Log to Google Sheets |
| 4 | Slack API | Slack 노드 2개 |

---

## 1. OpenAI (5분)

1. https://platform.openai.com/api-keys → **Create new secret key**
2. n8n → Credentials → **OpenAI** → API Key 붙여넣기
3. 결제 수단이 등록돼 있어야 합니다. 이 워크플로는 1회 실행에 기사 최대 10건 × `gpt-4o-mini` 이라 비용은 실행당 1센트 미만입니다.

---

## 2. Header Auth — 커스텀 API (2분)

1. n8n → Credentials → **Header Auth**
2. Name: `Enrichment API key`
3. **Name**: `X-API-Key`
4. **Value**: `docs/DEPLOY_API.md` 4단계에서 만든 `API_KEY` 값

---

## 3. Google Sheets OAuth2 (15분 — 여기가 제일 번거롭습니다)

### 3-1. Google Cloud 프로젝트

1. https://console.cloud.google.com → 새 프로젝트 `n8n-market-intel`
2. **APIs & Services** → **Library** → 두 개 모두 사용 설정:
   - **Google Sheets API**
   - **Google Drive API**  ← 빠뜨리면 시트 목록 조회가 실패합니다

### 3-2. OAuth 동의 화면

1. **APIs & Services** → **OAuth consent screen**
2. User Type: **External** → 앱 이름/이메일만 채우고 저장
3. **Scopes** 단계는 그냥 넘어가도 됩니다
4. **Test users** 에 본인 Gmail 주소를 추가 ← 이걸 빼면 로그인 시 `access_denied` 가 납니다
5. 게시 상태는 **Testing** 으로 두면 됩니다 (본인만 쓸 것이므로 검증 절차 불필요)

### 3-3. 자격증명 발급

1. n8n → Credentials → **Google Sheets OAuth2 API** 를 먼저 엽니다
2. 화면에 표시된 **OAuth Redirect URL** 을 복사 (`https://<n8n도메인>/rest/oauth2-credential/callback`)
   - 여기가 `localhost:5678` 로 보이면 `N8N_EDITOR_BASE_URL` 환경변수가 안 잡힌 것입니다. `docs/RAILWAY_SETUP.md` 4단계 확인 후 재배포하세요.
3. Google Cloud → **Credentials** → **Create Credentials** → **OAuth client ID**
   - Application type: **Web application**
   - Authorized redirect URIs: 2번에서 복사한 URL 붙여넣기
4. 발급된 **Client ID / Client Secret** 을 n8n 자격증명 화면에 붙여넣고 **Sign in with Google** 클릭
5. "이 앱은 확인되지 않았습니다" 경고 → **고급** → **이동(안전하지 않음)** — 본인 앱이므로 정상입니다

### 3-4. 시트 준비

새 Google 스프레드시트를 만들고, 첫 번째 시트 이름을 **`articles`** 로 바꾼 뒤 **1행에 아래 헤더를 그대로** 넣습니다. 워크플로가 auto-map 모드라 **헤더 이름이 곧 매핑 키**입니다. 오타가 나면 그 열만 조용히 비게 됩니다.

```
timestamp	id	published_at	age_hours	source	title	summary	category	sentiment	impact_score	entities	sectors	relevance_score	priority	cluster_id	is_followup	score_reason	score_recency	score_novelty	url
```

> 위 줄은 탭으로 구분돼 있습니다. 그대로 복사해서 A1 셀에 붙여넣으면 20개 열로 나뉘어 들어갑니다.

스프레드시트 URL에서 시트 ID를 꺼내 워크플로의 **Log to Google Sheets** 노드 Document ID에 넣습니다:

```
https://docs.google.com/spreadsheets/d/  ←여기부터 →1AbC...XYZ←  /edit
                                            이 부분이 Sheet ID
```

**보기 좋게 만들기 (스크린샷용, 3분):**
- 1행 고정: 보기 → 고정 → 행 1개
- `relevance_score` 열에 색상 스케일 조건부 서식 (빨강 0 → 초록 100)
- `priority` 열에 `high` 면 빨간 배경 조건부 서식

---

## 4. Slack (10분)

Slack 워크스페이스가 없으면 https://slack.com/get-started 에서 개인용으로 하나 새로 만드세요. 2분이면 되고, 포트폴리오 스크린샷용으로 오히려 깨끗합니다.

1. 채널 두 개 생성: `#market-alerts`, `#ops-alerts`
2. https://api.slack.com/apps → **Create New App** → **From scratch**
3. **OAuth & Permissions** → **Bot Token Scopes** 에 추가:
   - `chat:write`
   - `channels:read`
   - `chat:write.public` (봇을 채널에 초대하지 않고도 공개 채널에 쓰려면)
4. **Install to Workspace** → `xoxb-` 로 시작하는 **Bot User OAuth Token** 복사
5. n8n → Credentials → **Slack API** → Access Token 에 붙여넣기
6. Slack에서 두 채널에 각각 봇 초대: `/invite @앱이름`

### Slack을 못 쓰는 경우 (대체안)

Slack 노드 2개를 **HTTP Request** 노드로 바꾸고 Incoming Webhook URL로 POST하면 됩니다.

- Method: `POST`, URL: `https://hooks.slack.com/services/...`
- Body(JSON): `={{ JSON.stringify({ text: $json.title }) }}`

다만 **Slack 노드를 쓰는 쪽이 포트폴리오에서 더 좋게 보입니다** — 자격증명 관리와 채널 리졸빙까지 다뤘다는 뜻이기 때문입니다. 가능하면 Bot Token 방식으로 가세요.

---

## 5. 워크플로 Import & 연결

1. n8n → **Workflows** → **Import from File** → `workflows/market-intel-pipeline.json`
2. 노드 4개를 열어 값을 교체합니다:

| 노드 | 고칠 것 |
|---|---|
| Summarize & Classify | Credential 선택 (OpenAI) |
| Enrich via Custom API | URL의 `REPLACE-ME` → 실제 Railway 도메인 / Credential 선택 (Header Auth) |
| Log to Google Sheets | Document ID `REPLACE_WITH_YOUR_SHEET_ID` → 실제 시트 ID / Credential 선택 |
| Slack 노드 2개 | Credential 선택 / 채널 확인 |

3. **Fetch RSS 노드를 먼저 단독 테스트**하세요. Feed Registry → Fetch RSS 순서로 각각 **Test step** 을 눌러 아이템이 실제로 들어오는지 확인합니다.
   - 403이나 빈 결과가 나오는 피드는 Feed Registry 노드의 `FEEDS` 배열에서 빼거나 교체하세요. 뉴스 사이트 RSS는 수시로 죽습니다.
   - 대체 후보: `https://feeds.bbci.co.uk/news/business/rss.xml`, `https://www.investing.com/rss/news_25.rss`, `https://rss.nytimes.com/services/xml/rss/nyt/Business.xml`

4. 위에서부터 노드 하나씩 **Test step** 으로 내려가며 확인
5. 전체가 통과하면 **Execute Workflow** 로 풀 실행
6. 마지막으로 우측 상단 **Publish** — n8n 2.0에서는 저장(Save)만으로는 스케줄이 돌지 않습니다

---

## 6. 첫 실행 트러블슈팅

| 증상 | 원인 |
|---|---|
| Normalize 노드가 0건 반환 | 모든 기사가 24시간보다 오래됨(`MAX_AGE_HOURS`), 또는 이전 실행에서 이미 본 URL(`seen_before`). Code 노드 로그를 보면 `kept=0 seen_before=N` 으로 찍힙니다. 테스트 중이라면 워크플로를 잠깐 비활성화했다 다시 켜서 static data를 비우거나 `MEMORY_HOURS` 를 0으로 잠시 낮추세요 |
| Parse LLM Output 이 `llm_parse_ok:false` | 모델이 JSON이 아닌 걸 반환. `jsonOutput` 토글이 켜져 있는지 확인 |
| Enrich 노드 401 | Header Auth의 Name이 정확히 `X-API-Key` 인지, Value가 Railway의 `API_KEY` 와 같은지 |
| Sheets에 행은 생기는데 열이 비어 있음 | 1행 헤더 철자가 auto-map 키와 다릅니다. 위 3-4의 헤더를 그대로 다시 붙여넣으세요 |
| Slack `channel_not_found` | 봇을 채널에 초대하지 않았거나 `chat:write.public` 스코프 누락 |
