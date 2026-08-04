# AICC

고객 질문에 따라 공통 API를 호출하는 Tool 기능을 구현하는 영역이다.

## 현재 구현 상태

Tool 호출과 오류 처리를 구현했다. 질문 유형은 LLM 없이 키워드로 나눈다.

| 질문 유형 | 예시 | Tool | 공통 API |
|---|---|---|---|
| 메뉴·가격·품절 | 아메리카노 얼마예요? | Menu | `GET /api/stores/{store_id}/menus` |
| 인원·혼잡도 | 지금 사람 많나요? | State | `GET /api/stores/{store_id}/state` |
| 예상 대기시간 | 얼마나 기다려야 해요? | ETA | `GET /api/stores/{store_id}/eta` |
| 영업시간·주차·환불 | 주차 되나요? | Policy | `GET /api/stores/{store_id}/policies` |
| 그 외 | 화장실 어디예요? | 없음 | 호출하지 않음 |

정책 질문은 고객 질문을 임베딩으로 검색(RAG)해 관련된 정책만 돌려준다. 임베딩을 못 쓰면 전체 정책으로 물러난다.

네 유형에 해당하지 않는 질문은 Tool을 호출하지 않고 `unsupported_question`을 돌려준다. 모르는 질문에 매장 상태 같은 엉뚱한 값을 주면 LLM이 그걸 근거로 틀린 답을 지어낼 수 있기 때문이다.

키워드 방식이라 한계가 있다. `아메리카노 포장 얼마예요?`처럼 메뉴와 정책 키워드가 섞이면 정책으로 분류된다. 질문의 의도를 읽는 일은 LLM을 연결할 때 해결한다.

## 폴더 구성

```text
services/aicc/
├── aicc/
│   ├── client.py     # 공통 API 호출과 상태 코드 해석
│   ├── tools.py      # Tool 4개
│   ├── router.py     # 질문 유형 분기
│   ├── errors.py     # 오류 종류와 안내 문장
│   └── config.py     # 환경변수 설정
└── tests/
```

## 사용법

질문을 그대로 넘기면 알맞은 Tool을 호출한다.

```python
from aicc.router import QuestionRouter

with QuestionRouter() as router:
    answer = router.handle("얼마나 기다려야 해요?")
    # {'question_type': 'eta', 'tool': 'eta', 'result': {'ok': True, 'estimated_wait_minutes': 6, ...}}
```

Tool을 직접 부를 수도 있다.

```python
from aicc.tools import StoreTools

with StoreTools() as tools:
    tools.get_menus(menu_name="아메리카노")
```

## 환경변수

| 이름 | 기본값 | 설명 |
|---|---|---|
| `AICC_API_BASE_URL` | `http://localhost:8000` | 공통 API 주소 |
| `AICC_REQUEST_TIMEOUT_SECONDS` | `5` | 요청 제한 시간(초) |
| `AICC_DEFAULT_STORE_ID` | `store-001` | store_id를 넘기지 않았을 때 쓰는 매장 |

## 오류 처리

Tool은 예외를 던지지 않고 `ok: False` 결과를 돌려준다. LLM이 대화를 끊지 않고 고객에게 상황을 설명할 수 있어야 하기 때문이다. `message`는 고객에게 그대로 전달해도 되는 문장이다.

| `error` | 발생 상황 |
|---|---|
| `store_not_found` | 매장 상태가 없음 (`404`) |
| `invalid_request` | 요청 형식 오류 (`422`) |
| `sample_data_unavailable` | 샘플 파일 누락 (`503`) |
| `api_unavailable` | 공통 API에 연결 실패 |
| `unexpected_response` | 응답 형식이 계약과 다름 |
| `unsupported_question` | 답할 수 있는 네 유형이 아님 (Tool 호출 안 함) |

앞의 세 가지는 `docs/api-contract.md`의 오류 규격을 따른다.

## 슈퍼바이저 인사이트 API

집계 결과를 Gemini로 분석해 슈퍼바이저용 인사이트를 HTTP로 돌려준다. 대시보드 등 다른
서비스가 `franchise_insights.py`를 파이썬으로 직접 부르지 않고 HTTP로 쓸 수 있게 한다.

### 실행

Docker Compose로 공통 API와 함께 실행하는 방법을 권장한다.

```bash
cp .env.example .env
docker compose up -d --build api aicc
curl http://localhost:8100/healthz
```

컨테이너 안의 AICC는 공통 API를 `http://api:8000`으로 호출한다. 호스트 주소나
Tailscale 주소를 컨테이너 설정에 직접 넣을 필요가 없다.

Docker를 쓰지 않고 개발할 때는 다음과 같이 실행한다.

```bash
pip install -r services/aicc/requirements.txt
uvicorn aicc.api:app --app-dir services/aicc --port 8100
```

### 필요한 환경변수

| 환경변수 | 설명 | 기본값 |
|---|---|---|
| `AICC_API_BASE_URL` | 공통 API 주소 (집계 호출 대상) | `http://localhost:8000` |
| `AICC_CORS_ORIGINS` | 브라우저 호출을 허용할 대시보드 주소. 여러 개는 쉼표로 구분 | `http://localhost:5173` |
| `AICC_VERTEX_PROJECT` | 팀 크레딧 Vertex 프로젝트. 있으면 Vertex 사용 | (없음) |
| `AICC_VERTEX_LOCATION` | Vertex 리전 | `us-central1` |
| `AICC_GEMINI_MODEL` | Gemini 모델 | `gemini-2.5-flash` |
| `GOOGLE_API_KEY` | Vertex 대신 무료 등급을 쓸 때만 | (없음) |

키·인증정보는 코드에 넣지 않고 위 환경변수와 `gcloud` 인증으로 읽는다.

### Docker에서 Vertex 인증

호스트에서 ADC 로그인을 한 뒤 `.env`에 생성된 파일의 절대 경로를 지정한다.

```bash
gcloud auth application-default login
```

```env
GOOGLE_APPLICATION_CREDENTIALS_HOST_PATH=/home/user/.config/gcloud/application_default_credentials.json
```

Compose는 이 파일을 `/run/secrets/google_adc.json`에 읽기 전용으로 연결한다.
인증 JSON을 프로젝트 폴더로 복사하거나 Docker 이미지에 넣지 않는다. ADC를 지정하지
않아도 AICC 컨테이너와 `/healthz`는 실행되지만 Vertex를 호출하는 `/insights`는
정상 동작하지 않는다.

실행 상태와 로그는 다음 명령으로 확인한다.

```bash
docker compose ps aicc
docker compose logs --tail=100 aicc
curl http://localhost:8100/healthz
```

### 엔드포인트

`POST /insights` — 기간을 받아 집계를 분석한다.

요청(기간은 선택, 주면 시작<끝):
```json
{ "start_at": "2026-07-21T15:00:00Z", "end_at": "2026-07-22T14:59:59Z" }
```

응답:
```json
{
  "insights": [
    { "store_id": "store-001", "insight_type": "congestion", "severity": "high",
      "summary": "...", "evidence": { "peak_visible_person_count": 28 }, "recommendation": "..." }
  ],
  "comparison": { "summary": "...", "recommendation": "..." }
}
```

`GET /healthz` — 상태 확인.

### 오류 구분

| 상태 | error | 언제 |
|---|---|---|
| `422` | (검증) | 기간 형식 오류, start_at ≥ end_at |
| `502` | `store_api_error` | 공통(집계) API 호출 실패 |
| `503` | `insights_unavailable` | Gemini 분석 실패 |

## 카카오톡 손님 챗봇 (스킬 웹훅)

손님이 카카오톡 채널에 물어보면, 대시보드가 아니라 **카카오톡에서** 매장 혼잡도·대기시간·
메뉴·정책을 안내한다. 답을 만드는 두뇌는 `/chat`과 같은 `StoreAgent`(Gemini + 키워드
fallback)를 그대로 재사용하고, `kakao.py`는 **카카오 스킬 형식 ↔ 우리 답변**의 변환만 한다.

`/chat`은 점주 로그인(firebase)이 필요하지만, 손님은 로그인하지 않으므로 웹훅은 공개
엔드포인트다. 대신 공유 토큰(`AICC_KAKAO_SKILL_TOKEN`)으로 보호한다.

### 엔드포인트

`POST /kakao/skill` — 카카오 i 오픈빌더 스킬 서버 규약(요청/응답 2.0)을 따른다.

요청(카카오가 보냄, 필요한 부분만):
```json
{ "userRequest": { "utterance": "지금 붐벼요?" },
  "action": { "clientExtra": { "store_id": "store-001" } } }
```
- `utterance`가 손님 질문. 매장은 채널 1개=매장 1개가 기본(`AICC_DEFAULT_STORE_ID`)이고,
  멀티 매장이면 봇 설정에서 `store_id`를 `clientExtra`로 넘겨 덮어쓴다.

응답(우리가 돌려줌):
```json
{ "version": "2.0",
  "template": { "outputs": [ { "simpleText": { "text": "현재 5명, 대기 주문 2건이에요." } } ],
                "quickReplies": [ { "label": "대기시간", "action": "message", "messageText": "..." } ] } }
```
- 카카오는 **비-200이면 문장 대신 시스템 오류만** 보여주므로, 두뇌가 실패해도 정중한
  안내문을 담은 **200 스킬 응답**으로 답한다.

### 환경변수

| 이름 | 기본값 | 설명 |
|---|---|---|
| `AICC_KAKAO_SKILL_TOKEN` | (없음) | 스킬 웹훅 공유 토큰. 넣으면 헤더 `X-Kakao-Skill-Token` 또는 쿼리 `?token=`이 일치해야 한다. 비우면 검사 생략(로컬) |
| `AICC_DEFAULT_STORE_ID` | `store-001` | 채널이 안내하는 기본 매장 |

### 카카오 콘솔 연결 (한 번만)

1. [카카오 비즈니스](https://business.kakao.com)에서 **채널** 개설.
2. [카카오 i 오픈빌더](https://i.kakao.com)에서 봇 생성 → 채널 연결.
3. **스킬** 등록 → URL에 우리 웹훅 주소를 넣는다.
   - 배포 서버: `https://<도메인>/kakao/skill` (AICC 8100 포트를 HTTPS로 노출)
   - 로컬 개발: 공개 HTTPS 터널이 필요하다. 예) `ngrok http 8100` → 나온 주소 뒤에
     `/kakao/skill`을 붙여 등록.
   - 토큰을 쓰면 스킬 헤더에 `X-Kakao-Skill-Token: <토큰>`을 추가하거나 URL에
     `?token=<토큰>`을 붙인다.
4. 시나리오의 **폴백 블록**(또는 원하는 블록)에서 이 스킬을 호출하도록 연결한다.
5. 봇을 **배포**한 뒤 채널에서 실제로 물어본다.

로컬에서 형식만 빠르게 확인하려면(카카오 없이):
```bash
curl -X POST http://localhost:8100/kakao/skill \
  -H 'Content-Type: application/json' \
  -d '{"userRequest":{"utterance":"지금 붐벼요?"}}'
```

## 테스트

```bash
pip install -r services/aicc/requirements.txt
pytest services/aicc/tests
```

공통 API나 Gemini를 띄우지 않아도 된다. HTTP·Gemini 호출은 테스트에서 가짜 응답으로 대신한다.

## 다음 작업

- 실제 LLM API와 비밀키는 아직 연결하지 않았다. 질문에서 메뉴 이름을 뽑아내는 일은 LLM이 맡는다. `get_menus(menu_name=...)`로 넘기면 해당 메뉴만 걸러진다.
- 직원 연결 요청은 처리 방식과 API를 팀에서 정한 뒤 추가한다.
- 주문 조회 API가 공통 API에 없어 "3번 주문 어디쯤이야?" 같은 질문은 답할 수 없다. `GET /api/orders/{order_id}`가 필요하다.

## 팀에 공유할 것: 패키지 이름

이 서비스의 패키지를 `app`에서 `aicc`로 바꿨다. `services/api`도 패키지 이름이 `app`이라, 두 서비스를 같은 파이썬에 함께 올리면 먼저 등록된 쪽만 잡히고 다른 쪽은 `No module named 'app.main'`으로 실패한다. 컨테이너 안에서는 서로 격리되어 문제가 없지만, 테스트를 `tests/` 한 곳으로 합치거나 CI를 붙이면 드러난다.

`vision-worker`도 패키지를 만들 때 `app`을 쓰면 같은 문제가 생긴다. 서비스마다 폴더명과 같은 패키지 이름을 쓰면 피할 수 있다.
