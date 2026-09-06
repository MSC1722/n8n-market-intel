# 커스텀 FastAPI 서비스 배포 (Railway 두 번째 서비스)

n8n과 **같은 Railway 프로젝트** 안에 두 번째 서비스로 올립니다. 같은 프로젝트에 두면 나중에 Private Networking으로 붙일 수도 있고, 포트폴리오 스크린샷에서 "서비스 두 개짜리 아키텍처"가 한눈에 보입니다.

## 1. GitHub에 올리기

```bash
cd n8n-market-intel
git init
git add .
git commit -m "n8n market intelligence pipeline"
gh repo create n8n-market-intel --public --source=. --push
```

> `.gitignore`에 `.env`, `*.db` 가 들어 있는지 반드시 확인하세요. API 키가 공개 저장소에 올라가면 포트폴리오가 아니라 감점 요소가 됩니다.

## 2. Railway 서비스 생성

1. 기존 `n8n-market-intel` 프로젝트 안에서 **New** → **GitHub Repo** → 방금 만든 저장소 선택
2. 서비스 이름을 `enrich-api` 로 변경
3. **Settings** → **Build** → **Root Directory** 를 다음으로 설정:

```
fastapi-service
```

   (저장소 루트에 n8n 워크플로 JSON과 문서도 같이 있으므로, 빌드 루트를 잡아줘야 Dockerfile을 찾습니다.)

4. Builder는 `Dockerfile` 이 자동 감지됩니다. 안 되면 Settings → Build → Builder → **Dockerfile**.

## 3. 볼륨 붙이기

스토리 클러스터 이력이 재배포마다 날아가면 "실행 간 중복 제거"라는 핵심 기능이 무의미해집니다.

- **Attach Volume** → Mount path: `/data`

## 4. 환경변수

```env
API_KEY=REPLACE_ME
STORE_PATH=/data/market_intel.db
CLUSTER_WINDOW_HOURS=72
SIMHASH_BLOCK_DISTANCE=22
JACCARD_THRESHOLD=0.45
RETENTION_DAYS=30
LOG_LEVEL=INFO
```

`API_KEY` 생성:

```bash
openssl rand -hex 24
```

이 값을 그대로 n8n의 Header Auth 자격증명에도 넣습니다.

## 5. 도메인 & 헬스체크

- **Settings** → **Networking** → **Generate Domain**
- **Settings** → **Deploy** → Healthcheck Path: `/health`

## 6. 동작 확인

```bash
API=https://your-enrich-api.up.railway.app
KEY=여기에_API_KEY

curl -s $API/health | jq

curl -s -X POST $API/v1/enrich \
  -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Fed holds interest rates steady as inflation cools",
    "summary": "The Federal Reserve kept its benchmark rate unchanged.",
    "url": "https://www.reuters.com/markets/fed-holds/?utm_source=twitter",
    "source": "Reuters",
    "published_at": "2026-09-06T02:00:00Z",
    "category": "monetary_policy",
    "impact_score": 8.5,
    "sentiment": "neutral",
    "tickers": ["SPX"],
    "client_ref": "demo-1"
  }' | jq
```

기대 출력:

```json
{
  "id": "…",
  "client_ref": "demo-1",
  "canonical_url": "https://reuters.com/markets/fed-holds",
  "cluster_id": "c_…",
  "is_followup": false,
  "cluster_size": 1,
  "entities": [{ "symbol": "FED", "name": "US Federal Reserve", "…": "…" }],
  "sectors": ["macro"],
  "relevance_score": 9…,
  "priority": "high",
  "score_breakdown": { "impact": 0.85, "entity": …, "recency": …, "source": 1.0, "novelty": 1.0 },
  "reason": "top contributor: …"
}
```

**같은 요청을 제목만 살짝 바꿔서 다시 보내보세요.** `is_followup: true`, `cluster_size: 2`, 그리고 `relevance_score` 가 눈에 띄게 떨어지면 클러스터링이 살아 있는 것입니다. — 이게 포트폴리오 스크린샷 소재입니다.

## 7. 문서 페이지

`https://your-enrich-api.up.railway.app/docs` 에 FastAPI 자동 생성 Swagger UI가 뜹니다. 이 화면도 스크린샷으로 남기세요. "n8n만 쓸 줄 아는 사람"과 가장 확실히 갈리는 한 장입니다.

---

## 로컬에서 먼저 돌려보기

```bash
cd fastapi-service
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install pytest httpx
STORE_PATH=./local.db API_KEY=dev pytest -q      # 20 tests
STORE_PATH=./local.db API_KEY=dev uvicorn app.main:app --reload
```
