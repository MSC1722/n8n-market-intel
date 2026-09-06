# 스크린샷 체크리스트

업워크에서 클라이언트는 설명을 안 읽습니다. 썸네일 한 장으로 판단합니다. 아래 5장을 확보하세요. 1번이 대표 이미지입니다.

## 1. 워크플로 캔버스 전체 ★ 대표 이미지

**촬영 방법**
- n8n 에디터에서 `Ctrl/Cmd + A` → 우측 하단 **Zoom to fit** 버튼
- 브라우저를 전체화면(F11), 창 너비 1920px 이상
- 좌측 사이드바 접기 (노드가 더 크게 보입니다)

**반드시 보여야 하는 것**
- [ ] 13개 노드가 전부 한 화면에
- [ ] 노드 연결선 (특히 **아래로 갈라지는 에러 브랜치** 2줄)
- [ ] 스티키 노트 4개의 제목이 읽힐 것 — 이게 설명을 대신합니다
- [ ] IF 노드에서 갈라지는 true/false 두 갈래
- [ ] 각 노드의 아이콘 (OpenAI, Slack, Google Sheets 로고가 보이면 신뢰도가 올라갑니다)

**하지 말 것**
- 다크 모드 + 저해상도 조합 → 캔버스가 뭉개집니다. 라이트 모드 권장
- 노드가 화면 밖으로 잘리는 것

## 2. 실행 성공 화면

- **Executions** 탭 → 성공한 실행 하나 열기
- [ ] 모든 노드에 초록 체크
- [ ] 각 연결선 위에 아이템 개수 뱃지 (`5 items` → `3 items` 식으로 **중복 제거로 숫자가 줄어드는 게 보이면 최고**)
- [ ] 실행 소요 시간

## 3. Normalize & Deduplicate 노드 상세 ★ 차별점 1

- 해당 노드를 더블클릭 → 좌측 INPUT / 우측 OUTPUT
- [ ] OUTPUT 아이템 개수가 INPUT보다 적을 것
- [ ] 노드 하단 **Logs** 탭에 `dedupe: fetched=… kept=… near=… seen_before=…` 로그가 찍힌 화면
- 코드 스크롤을 상단 주석이 보이는 위치에 두고 한 장 더 (왜 만들었는지가 주석에 있습니다)

## 4. FastAPI Swagger UI + 응답 ★ 차별점 2

- `https://your-enrich-api.up.railway.app/docs`
- [ ] `/v1/enrich` 를 **Try it out** 으로 실제 실행한 응답 본문
- [ ] `score_breakdown` 과 `entities` 가 펼쳐진 상태
- 보너스: 같은 스토리를 두 번 보내 `is_followup: true`, 점수가 떨어진 응답을 나란히 캡처 → 이 두 장이 "n8n만 쓰는 사람"과 가장 크게 갈리는 지점입니다

## 5. 결과물 (Slack + Google Sheets)

- [ ] `#market-alerts` 채널의 실제 알림 메시지 (점수, 엔티티, 스코어링 근거가 보이게)
- [ ] Google Sheets — 헤더 고정 + `relevance_score` 조건부 서식 색상 스케일이 들어간 상태로 10행 이상

## 보너스 6. Railway 프로젝트 캔버스

- 서비스 2개(`n8n`, `enrich-api`)와 각각의 볼륨이 보이는 프로젝트 화면
- "셀프 호스팅"이 말뿐이 아니라는 증거

---

## 에러 핸들링도 증명하고 싶다면 (선택, 5분) ★ 차별점 3

의도적으로 한 번 실패시켜서 에러 알림 스크린샷을 남기세요.

1. **Enrich via Custom API** 노드의 URL 끝에 `x` 를 붙여 404를 만듭니다
2. Execute Workflow
3. 3회 재시도 후 → Handle Failure → `#ops-alerts` 에 알림이 뜹니다
4. 캡처: (a) 에러 브랜치가 빨갛게 표시된 캔버스, (b) Slack의 분류된 실패 메시지
5. URL 원복

이 두 장이 있으면 "에러 핸들링 넣었습니다"가 아니라 "에러 핸들링 이렇게 동작합니다"가 됩니다.

---

## 파일 정리

```
screenshots/
  01-canvas-full.png
  02-execution-success.png
  03-dedupe-node.png
  04-fastapi-swagger.png
  05-slack-and-sheets.png
  06-railway-services.png
  07-error-branch.png
```

GitHub README 상단에 1번을 넣고, 업워크 포트폴리오 항목에도 1번을 커버로 씁니다.
