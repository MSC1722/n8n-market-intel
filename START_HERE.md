# 진행 순서 (총 6~9시간, 이틀에 나눠서)

산출물은 이미 다 만들어져 있습니다. 남은 일은 **배포하고 실제로 돌린 뒤 스크린샷을 찍는 것**입니다.

## Day 1 — 인프라 (3~4시간)

| 순서 | 할 일 | 문서 | 예상 |
|---|---|---|---|
| 1 | ~~Railway에 n8n 셀프 호스팅~~ ✅ **완료 (2026-09-06)** | `docs/RAILWAY_SETUP.md` | — |
| 2 | GitHub 공개 저장소 push | `docs/DEPLOY_API.md` §1 | 15분 |
| 3 | FastAPI 서비스 Railway 배포 + curl 확인 | `docs/DEPLOY_API.md` §2-6 | 40분 |
| 4 | OpenAI · Header Auth 자격증명 등록 | `docs/CREDENTIALS_SETUP.md` §1-2 | 10분 |
| 5 | Google Sheets OAuth (제일 번거로움) | `docs/CREDENTIALS_SETUP.md` §3 | 40분 |
| 6 | Slack 앱 + 봇 토큰 | `docs/CREDENTIALS_SETUP.md` §4 | 20분 |

**1단계 완료 상태 (2026-09-06)**

| 항목 | 값 |
|---|---|
| n8n URL | https://n8n-production-02fc9.up.railway.app |
| Railway 프로젝트 / 서비스 | `graceful-light` / `n8n` |
| 이미지 | `n8nio/n8n:2.37.10` (버전 고정됨) |
| 볼륨 | `n8n-volume` → `/home/node/.n8n` (재배포 영속성 검증 완료) |
| 포트 / 헬스체크 | 5678 / `/healthz` |
| 환경변수 | 20개 |
| 플랜 | Railway Hobby ($5/월) |

세팅 중 걸린 함정 두 개는 `docs/RAILWAY_SETUP.md` 4절·8절에 반영해 뒀습니다:
`RAILWAY_RUN_UID=0` (볼륨 root 소유 vs `node` 유저 실행 → `EACCES` 크래시 루프)와
`N8N_USER_FOLDER=/home/node` (root로 돌리면 `$HOME`이 바뀌어 데이터가 볼륨 밖에 쌓임).
**둘 다 넣어야** 풀립니다.

## Day 2 — 워크플로 (2026-09-06 완료)

| 순서 | 할 일 | 상태 |
|---|---|---|
| 7 | 워크플로 Import, 자격증명 연결 | ✅ |
| 8 | RSS 피드 5개 생존 확인 | ✅ 140건 수집 |
| 9 | 전체 실행 | ✅ **Success in 11.795s** |
| 10 | 에러 브랜치 실증 | ⏳ 남음 |
| 11 | 스크린샷 5~7장 | ⏳ 남음 |
| 12 | README 삽입 후 push | ⏳ 남음 |
| 13 | 업워크 포트폴리오 등록 | ⏳ 남음 |

**최종 실행 파이프라인**

```
Every 6 Hours 1 → Feed Registry 5 → Fetch RSS 140 → Normalize & Deduplicate 10
→ Summarize & Classify 10 → Parse LLM Output 10 → Enrich via Custom API 10
→ Assemble Record 10 → Route by Priority (high 0 / rest 10) → Google Sheets 10 ✅
```

## Day 3 — 스크린샷 (평일 장중)

Slack 알림은 `relevance_score >= 70` 에서만 나갑니다. 2026-09-06(일요일) 실행에서는 최고 점수가 **63**이라 알림이 안 갔습니다. 시장 휴장 + 뉴스 한산이 원인입니다.

**평일 미국 장중(한국시간 22:30~05:00)에 Execute workflow 를 다시 눌러 주세요.** 그때 `#market-alerts` 알림 스크린샷을 찍으면 됩니다.

임계값은 `Route by Priority` 노드의 `rightValue` 에 있습니다. 평일 데이터를 보고도 계속 안 걸리면 그때 55~60으로 재보정하는 게 맞습니다 — 실측 분포를 근거로 조정하는 건 정당한 튜닝입니다.

## 지금 바로 확인할 수 있는 것

n8n이나 Railway 없이도 로컬에서 핵심 로직이 도는 걸 볼 수 있습니다.

```bash
# Code 노드 로직 (node만 있으면 됨)
cd code-nodes && node tests/run_dedupe_test.js && node tests/run_nodes_test.js

# FastAPI (20개 테스트)
cd fastapi-service && pip install -r requirements.txt pytest httpx && pytest -q
```

## 막힐 만한 지점 3개

1. **Google OAuth 콜백이 localhost로 감** → `N8N_EDITOR_BASE_URL` 미설정. Railway 환경변수 확인 후 재배포.
2. **RSS 피드가 403** → 뉴스 사이트 RSS는 자주 죽거나 차단됩니다. `code-nodes/js_feed_registry.js`의 `FEEDS` 배열을 교체하고 `python3 code-nodes/build_workflow.py` 로 JSON을 다시 빌드하거나, n8n UI에서 직접 고치세요. 5개 중 3개만 살아 있어도 데모로 충분합니다.
3. **스케줄이 안 돎** → n8n 2.0은 저장(Save)이 아니라 **Publish** 를 눌러야 실행됩니다.

## 포트폴리오에서 밀고 갈 한 줄

> "n8n 계정 하나 만들어 노드를 이어 붙인 게 아니라, Docker로 직접 호스팅하고, 노드로 안 되는 부분은 내 API를 만들어 붙였습니다."

`README.md`의 "Why this is not a drag-and-drop workflow" 섹션이 이 문장을 근거로 뒷받침합니다.
