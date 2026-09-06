# Railway에 n8n 셀프 호스팅 (2026년 9월 기준)

> **중요 — 인터넷에 돌아다니는 대부분의 n8n 셀프호스팅 글은 낡았습니다.**
> 2025년 12월에 **n8n 2.0**이 나오면서 셀프호스팅 설정이 여러 개 바뀌었습니다.
> 아래 세 가지는 옛날 가이드를 그대로 따라 하면 반드시 터집니다.
>
> | 옛날 가이드 | 현재(2.x) |
> |---|---|
> | `N8N_BASIC_AUTH_ACTIVE=true` 로 로그인 보호 | **삭제됨.** 최초 접속 시 만드는 owner 계정이 인증입니다. 이 변수를 넣으면 무시되거나 경고만 뜹니다 |
> | 바이너리 데이터 기본값 = 메모리 | **`default`(메모리) 모드 제거됨.** `N8N_DEFAULT_BINARY_DATA_MODE=filesystem` 를 직접 넣어야 안정적입니다 |
> | Code 노드가 n8n 프로세스 안에서 실행 | **Task Runner가 기본 ON.** Code 노드는 격리된 러너에서 돌고, `process.env` 접근이 막혀 있습니다 |
> | 워크플로 저장 = 즉시 반영 | **Save와 Publish가 분리됨.** 저장만으로는 프로덕션에 안 올라갑니다 |

---

## 0. 준비물

- GitHub 계정 (Railway 로그인 + 포트폴리오 저장소용)
- Railway 계정 — https://railway.com
  - Railway는 사용량 기반 과금입니다. 체험 크레딧이 끝나면 Hobby 플랜(월 $5 크레딧 포함)이 필요합니다.
  - n8n 1개 서비스 + 1GB 볼륨 정도면 대체로 Hobby 크레딧 안에서 돌아가지만, **정확한 현재 요금은 배포 전에 railway.com/pricing 에서 직접 확인하세요.**
- 결제 카드 (Railway 등록용)

예상 소요: **25~40분**

---

## 1. 프로젝트 & 서비스 생성

1. Railway 대시보드 → **New Project** → **Empty Project**
2. 프로젝트 이름을 `n8n-market-intel` 로 변경 (좌측 상단 이름 클릭)
3. 캔버스에서 **New** → **Docker Image** 선택
4. 이미지 이름에 입력:

```
n8nio/n8n:latest
```

5. 배포가 시작되면 곧바로 **한 번 실패하거나 재시작 루프**에 빠집니다. 정상입니다 — 아직 포트와 볼륨 설정을 안 했기 때문입니다. 다음 단계로 넘어가세요.

> **버전 고정 팁:** 첫 배포는 `latest` 로 띄우고, Deploy 로그 첫 줄에 찍히는 버전(예: `Version: 2.37.10`)을 확인한 뒤 이미지 태그를 그 버전으로 바꿔 고정하세요. 포트폴리오 스크린샷을 찍은 뒤에 n8n이 자동 업데이트되어 UI가 달라지는 사고를 막습니다.

---

## 2. 볼륨 붙이기 (이걸 빼먹으면 재배포마다 전부 날아갑니다)

1. 서비스 카드 우클릭 → **Attach Volume** (또는 서비스 → Settings → Volumes → New Volume)
2. **Mount path** 를 정확히 입력:

```
/home/node/.n8n
```

3. 크기는 기본값(보통 1GB)이면 충분합니다.

여기에 워크플로, 자격증명(암호화 상태), 실행 이력, SQLite DB가 전부 저장됩니다.

---

## 3. 공개 도메인 생성

1. 서비스 → **Settings** → **Networking** → **Generate Domain**
2. 포트를 물어보면 **5678** 을 넣습니다 (n8n 기본 포트. 다음 단계의 `N8N_PORT=5678` 과 맞춥니다)
3. `xxxxx.up.railway.app` 형태의 도메인이 생성됩니다

---

## 4. 환경변수 입력

서비스 → **Variables** → **Raw Editor** 를 열고 아래를 통째로 붙여넣습니다.

```env
# --- 네트워크 / Railway 바인딩 ---
N8N_PORT=5678
N8N_LISTEN_ADDRESS=0.0.0.0
N8N_HOST=${{RAILWAY_PUBLIC_DOMAIN}}
N8N_PROTOCOL=https
WEBHOOK_URL=https://${{RAILWAY_PUBLIC_DOMAIN}}
N8N_EDITOR_BASE_URL=https://${{RAILWAY_PUBLIC_DOMAIN}}
N8N_PROXY_HOPS=1

# --- 필수: 암호화 키 (아래 값을 쓰지 말고 직접 생성한 값으로 교체) ---
N8N_ENCRYPTION_KEY=REPLACE_ME_WITH_YOUR_OWN_48_HEX_CHARS

# --- n8n 2.x 필수 설정 ---
N8N_DEFAULT_BINARY_DATA_MODE=filesystem
N8N_RUNNERS_MODE=internal

# --- Railway 볼륨 권한 (이 두 줄이 없으면 100% 터집니다. 8절 참고) ---
RAILWAY_RUN_UID=0
N8N_USER_FOLDER=/home/node

# --- 시간대 ---
GENERIC_TIMEZONE=Asia/Seoul
TZ=Asia/Seoul

# --- 운영 ---
EXECUTIONS_DATA_PRUNE=true
EXECUTIONS_DATA_MAX_AGE=168
N8N_LOG_LEVEL=info
N8N_DIAGNOSTICS_ENABLED=false
N8N_PERSONALIZATION_ENABLED=false
N8N_HIRING_BANNER_ENABLED=false
```

### `N8N_ENCRYPTION_KEY` 생성

터미널에서:

```bash
openssl rand -hex 24
```

출력된 48자리 문자열을 넣으세요. **이 값은 절대 바꾸면 안 됩니다.** 바꾸는 순간 저장된 모든 자격증명(Google, Slack, OpenAI 키)이 복호화 불가가 되어 다시 등록해야 합니다. 비밀번호 관리자에 따로 백업해 두세요.

### 각 변수가 하는 일 (면접에서 물어볼 수 있는 것들)

| 변수 | 이유 |
|---|---|
| `N8N_PORT=5678` | 3절에서 도메인의 target port를 5678로 지정했으므로 여기서도 5678로 맞춥니다 (`${{PORT}}` 참조도 동작하지만 값이 명시적인 쪽이 디버깅이 쉽습니다) |
| `RAILWAY_RUN_UID=0` | Railway 볼륨은 root 소유로 마운트되는데 `n8nio/n8n` 이미지는 `node`(uid 1000)로 실행됩니다. 없으면 부팅 시 `EACCES: permission denied, open '/home/node/.n8n/config'` 로 크래시 루프 |
| `N8N_USER_FOLDER=/home/node` | 위에서 root로 돌리면 `$HOME`이 `/root`가 되어 n8n이 데이터를 **볼륨 밖** `/root/.n8n` 에 씁니다. 이 변수로 데이터 폴더를 볼륨 위에 고정합니다 |
| `N8N_LISTEN_ADDRESS=0.0.0.0` | 기본값 `localhost`는 컨테이너 밖에서 접근이 안 됩니다 |
| `N8N_PROXY_HOPS=1` | Railway 엣지 프록시 뒤에 있으므로, 이 값이 없으면 클라이언트 IP를 프록시 IP로 오인해 레이트리밋과 보안 쿠키가 오작동합니다 |
| `WEBHOOK_URL` / `N8N_EDITOR_BASE_URL` | n8n이 웹훅 URL과 OAuth 콜백 URL을 생성할 때 씁니다. 없으면 `localhost:5678` 로 만들어져 Google OAuth 연결이 실패합니다 |
| `N8N_DEFAULT_BINARY_DATA_MODE=filesystem` | 2.0에서 메모리 모드가 제거됨 |
| `EXECUTIONS_DATA_PRUNE` | 실행 이력이 무한정 쌓여 볼륨을 채우는 것을 방지 (168시간 = 7일 보관) |

---

## 5. 헬스체크 설정

서비스 → **Settings** → **Deploy** → **Healthcheck Path**:

```
/healthz
```

이걸 넣어두면 Railway가 n8n이 실제로 뜬 뒤에 트래픽을 넘겨줍니다. 재배포 중 502가 나는 걸 막습니다.

---

## 6. 재배포 & 최초 로그인

1. **Deploy** 버튼 클릭 (또는 변수 저장 시 자동 재배포)
2. Deploy Logs에서 아래 줄이 보이면 성공:

```
Editor is now accessible via:
https://<your-domain>.up.railway.app
```

3. 생성된 도메인으로 접속 → **Set up owner account** 화면에서 이메일/비밀번호 등록
   - 이 owner 계정이 유일한 인증 수단입니다. 아무나 URL로 들어와서 계정을 만들기 전에 **배포 직후 바로** 만드세요.
4. 라이선스 키를 요구하는 화면이 뜨면 건너뛰어도 됩니다 (Community 에디션으로 계속 사용 가능)

---

## 7. 배포 확인 체크리스트

- [ ] 도메인 접속 시 n8n 에디터가 뜬다
- [ ] owner 계정으로 로그인된다
- [ ] Railway 서비스 → Settings → Volumes 에 `/home/node/.n8n` 볼륨이 붙어 있다
- [ ] Console 탭에서 `ls -la /home/node/.n8n` → `database.sqlite` 와 `lost+found` 가 보인다
- [ ] **재배포 테스트**: Railway에서 Redeploy 한 번 누른 뒤 다시 접속 → 로그인 화면이 뜨면 성공, `Set up owner account` 가 다시 뜨면 데이터가 날아간 것 (8절 참고)
- [ ] Settings → n8n 버전 확인 → 이미지 태그를 그 버전으로 고정

---

## 8. 자주 터지는 문제

**컨테이너가 계속 재시작함 / 502**
→ `N8N_PORT` 값과 도메인의 target port가 같은지, `N8N_LISTEN_ADDRESS=0.0.0.0` 인지 확인. Railway 변수 참조(`${{RAILWAY_PUBLIC_DOMAIN}}` 등)를 썼다면 Raw Editor에서 표기가 깨지지 않았는지도 확인.

**부팅 실패 `EACCES: permission denied, open '/home/node/.n8n/config'`**
→ Railway 볼륨은 root 소유로 마운트되는데 n8n 이미지는 `node` 유저로 돕니다. `RAILWAY_RUN_UID=0` 추가.
→ 주의: Railway 배포 화면은 이 상태에서도 **"Deployment successful"** 이라고 표시합니다. 컨테이너는 계속 죽고 있어요. Deploy Logs를 직접 봐야 보입니다.

**재배포하면 워크플로·계정이 다 사라짐 (에러는 안 남)**
→ 두 가지 중 하나입니다.
  1. 볼륨 마운트 경로 오타 — `/home/node/.n8n` 이 정확한지 확인.
  2. **`RAILWAY_RUN_UID=0` 만 넣고 `N8N_USER_FOLDER` 를 안 넣은 경우.** root로 실행되면 `$HOME`이 `/root` 라서 n8n이 데이터를 `/root/.n8n`(볼륨 밖)에 씁니다. 조용히 잘 도는 것처럼 보이다가 재배포 때 전부 날아갑니다. `N8N_USER_FOLDER=/home/node` 추가.

→ 확인 방법: 서비스 → **Console** 탭에서
```bash
ls -la /home/node/.n8n; df -h /home/node/.n8n
```
`database.sqlite` 와 `lost+found` 가 보이고 Filesystem이 `/dev/zd...` 면 볼륨 위에 제대로 앉은 것입니다.

**로그인은 되는데 저장된 자격증명이 전부 에러**
→ `N8N_ENCRYPTION_KEY` 가 바뀌었습니다. 원래 값으로 되돌리거나, 안 되면 자격증명을 전부 삭제하고 다시 등록해야 합니다.

**`Settings file permissions are not secure` 로 부팅 실패**
→ 2.0부터 `N8N_ENFORCE_SETTINGS_FILE_PERMISSIONS` 가 기본 `true` 입니다. Linux 컨테이너에서는 보통 문제없지만, 발생하면 `N8N_ENFORCE_SETTINGS_FILE_PERMISSIONS=false` 를 임시로 추가.

**Code 노드에서 `process.env` 가 undefined**
→ 2.0 정상 동작입니다. Task Runner가 환경변수 접근을 막습니다. 꼭 필요하면 `N8N_BLOCK_ENV_ACCESS_IN_NODE=false` 를 추가하되, **이번 워크플로는 이 설정이 필요 없습니다** (API 키는 전부 n8n Credential로 관리).

**Google OAuth 콜백이 `localhost` 로 감**
→ `N8N_EDITOR_BASE_URL` 미설정. 설정 후 재배포하고, 자격증명 화면의 콜백 URL을 다시 복사해서 Google Cloud에 등록.

**워크플로를 켰는데 스케줄이 안 돎**
→ 2.0에서 Activate 토글이 **Publish** 버튼으로 바뀌었습니다. 저장(Save)만으로는 실행되지 않습니다. 우측 상단 **Publish** 를 누르세요.

---

## 9. 다음 단계

1. `docs/CREDENTIALS_SETUP.md` — Google Sheets · Slack · OpenAI 자격증명 등록
2. `fastapi-service/` — 커스텀 API를 같은 Railway 프로젝트에 두 번째 서비스로 배포
3. `workflows/market-intel-pipeline.json` — n8n에 Import
