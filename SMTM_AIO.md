# SMTM_AIO 작업 내역

**날짜**: 2026-03-15
**작업 범위**: SMTM 프로젝트를 단일 Jupyter 노트북으로 재구성 (암호화폐·주식 각 1개)

---

## 1. 작업 개요

| 산출물 | 설명 | 셀 수 | 크기 |
|--------|------|-------|------|
| `SMTM_AIO.ipynb` | Upbit 암호화폐 멀티에셋 전략 | 26셀 (코드 18, MD 8) | 60 KB |
| `SMTM_AIO_kw.ipynb` | Kiwoom REST API 주식 멀티에셋 전략 | 28셀 (코드 20, MD 8) | 74 KB |

---

## 2. 작업 1 — 재구성 계획 수립 (`SMTM_AIO.ipynb` 설계)

### 배경
프로젝트의 전체 데이터 흐름 파악을 위해 smtm2 소스코드를 단일 `.ipynb` 파일로 재구성하는 작업을 계획했다. 멀티에셋 전략(`StrategyMultiMinute`, `UpbitMultiDataProvider`, `UpbitMultiTrader`)만을 대상으로 하기로 결정했다.

### 확정된 단계별 구성

| 섹션 | 내용 |
|------|------|
| 0 | 환경 설정 (imports, 로깅) |
| 1 | KRW 전체 마켓 조회 및 가격 필터 |
| 2 | 10분간 지속 상승 필터 + 상승비율 랭킹 시각화 |
| 3 | `KRWRisingDataProvider` 구현 및 테스트 |
| 4 | `StrategyKRWRising` 구현 및 초기화 |
| 5 | `MockMultiTrader` 구현 및 테스트 |
| 6 | 트레이딩 루프 — 1턴 단계별 + 다수 턴 시뮬레이션 |
| 7 | 결과 분석 및 시각화 |

### 유의사항 (설계 단계에서 확정)

1. **스레딩 제거** — `Operator`/`SimulationOperator`의 `Worker` 스레드를 사용하지 않고, `_execute_trading_sync()` 함수로 5단계를 동기 직접 호출
2. **상태 관리** — 섹션마다 새 인스턴스를 생성하여 셀 재실행 시 상태 오염 방지
3. **로깅 노이즈 억제** — `NbLogCapture` 핸들러로 DEBUG 이상 누적, 에러 발생 셀에서만 `flush_on_error()` 로 전체 로그 출력
4. **SQLite 경로** — 노트북 실행 디렉토리가 프로젝트 루트(`smtm2/`)임을 명시
5. **실거래 API 격리** — `MockMultiTrader` 사용, `UpbitMultiTrader`/실거래 API 미사용
6. **matplotlib 백엔드 충돌 방지** — `smtm.analyzer` 미임포트 (내부에서 `matplotlib.use("Agg")` 호출), `%matplotlib inline`을 최상단 셀에 배치
7. **멀티에셋 인터페이스** — `info` 리스트에 `market` 필드로 종목 구분, 요청 딕셔너리에 `"market"` 필드 포함 (UpbitMultiTrader 라우팅용)
8. **셀 실행 순서 의존성** — 섹션 헤더에 전제 조건 명시

---

## 3. 작업 2 — `SMTM_AIO.ipynb` 구현 (Upbit 암호화폐)

### 전략 설계 — `StrategyKRWRising`

기존 `StrategyMultiMinute`(EMA+RSI 기반)와 달리, KRW 전체 마켓에서 **10분간 종가 지속 상승**이라는 단순하고 직관적인 조건으로 종목을 선별한다.

**선별 조건**

```
candles = [c0, c1, ..., c9]  # Upbit 1분봉 종가 10개 (시간순)
지속 상승 ↔ all(c[i] > c[i-1] for i in range(1, 10))
상승비율  = (c9 - c0) / c0
```

**매수 조건**
- 상승비율 기준 상위 `MAX_BUY_COUNT(=3)` 종목
- 보유 중이지 않고 매수 대기 주문도 없음
- 잔고 ≥ `min_price`

**매도 조건**
1. **추세 소멸**: 다음 턴에 지속 상승 목록에서 이탈
2. **손절**: 매수 평균가 대비 `STOP_LOSS_RATIO(=3%)` 이상 하락

### 신규 구현 클래스

#### `KRWRisingDataProvider`

```
[Upbit /v1/market/all]
    → 전체 KRW 마켓 목록
    → 가격 필터 (MIN_PRICE=100 ~ MAX_PRICE=100,000 KRW)
    → Upbit /v1/candles/minutes/1?count=10 (종목별)
    → is_continuously_rising() 판별
    → 상승비율 내림차순 정렬 → 상위 TOP_N
    → primary_candle 리스트 반환 (rise_ratio, rank 필드 추가)
```

**반환 스키마 (`primary_candle` 확장)**

| 필드 | 설명 |
|------|------|
| `type` | `"primary_candle"` |
| `market` | currency 코드 (`"XRP"`, `"DOGE"` 등) |
| `market_full` | `"KRW-XRP"` |
| `closing_price` | 현재 종가 |
| `rise_ratio` | 상승비율 (소수) |
| `rank` | 상승비율 순위 |

#### `StrategyKRWRising(Strategy)`

- `update_trading_info()`: `rise_ratio` / `rank` 기반 랭킹 갱신, 현재가 캐시(`_last_prices`) 갱신
- `get_request()`: 매도 우선(손절·추세소멸) → 매수(상위 종목 소수점 수량)
- `update_result()`: 잔고 / 보유량 반영 (수수료 `COMMISSION_RATIO=0.0005`)
- `_create_buy_req()`: 수량 = `floor(net_budget / price * 10000) / 10000` (소수점 4자리)

#### `MockMultiTrader`

- `send_request(request_list, callback)`: 요청을 즉시 체결 처리 후 callback 호출
- 매수: `balance -= round(total + fee)`
- 매도: `balance += round(total - fee)`
- 잔고 부족 / 보유량 부족 시 `msg="insufficient_balance"` / `"insufficient_asset"` 반환

### 트레이딩 루프 — `_execute_trading_sync()`

```python
def _execute_trading_sync(dp, strategy, trader):
    trading_info = dp.get_info()                   # Step 1
    strategy.update_trading_info(trading_info)     # Step 2
    requests_out = strategy.get_request()          # Step 3
    if requests_out:
        trader.send_request(requests_out,
            lambda r: strategy.update_result(r))   # Step 4+5
    return trading_info, requests_out, results
```

### 글로벌 파라미터

| 파라미터 | 값 | 설명 |
|---------|-----|------|
| `DEMO_MODE` | `True` | `False` 시 Upbit 실시간 API 호출 |
| `MIN_PRICE` | `100` | 가격 하한 (KRW) |
| `MAX_PRICE` | `100,000` | 가격 상한 (KRW) |
| `CANDLE_COUNT` | `10` | 1분봉 수 |
| `TOP_N` | `15` | 상위 반환 종목 수 |
| `INITIAL_BUDGET` | `300,000` | 초기 예산 (KRW) |
| `N_TURNS` | `5` | 시뮬레이션 턴 수 |

### 실행 검증 결과

```
DEMO_MODE=True, 가격 필터: 100~100,000 KRW, 20개 종목 대상
→ 지속 상승 종목: 턴마다 0~2개 (합성 데이터 랜덤 특성)
→ Turn 4: [BUY]STX×26주 @ 1,921원 | [BUY]XRP×56주 @ 878원
→ 최종 잔고: 200,000 KRW / 총자산: 299,950 KRW / 수익률: -0.0167%
→ trade_log: 2건 체결
```

### 노트북 셀 구성

```
c00 [MD]  타이틀 및 데이터 흐름 개요
c01 [코드] %matplotlib inline, imports, 전역 파라미터
c02 [코드] NbLogCapture 로깅 설정
c03 [MD]  섹션 1 헤더
c04 [코드] DEMO_MARKETS_BASE 정의 / Upbit 전체 KRW 마켓 조회
c05 [코드] 현재가 조회 + 가격 필터 → price_filtered
c06 [MD]  섹션 2 헤더
c07 [코드] 헬퍼 함수 (_fetch_real_candles, _make_demo_candles, is_continuously_rising, calc_rise_ratio)
c08 [코드] 전체 필터링 → rising_assets 리스트
c09 [코드] 상승비율 바차트 + 상위 5종목 가격 추이 시각화
c10 [MD]  섹션 3 헤더
c11 [코드] KRWRisingDataProvider 클래스 정의
c12 [코드] KRWRisingDataProvider.get_info() 테스트
c13 [MD]  섹션 4 헤더
c14 [코드] StrategyKRWRising 클래스 정의
c15 [코드] 전략 초기화 테스트
c16 [MD]  섹션 5 헤더
c17 [코드] MockMultiTrader 클래스 정의
c18 [코드] 매수/매도 테스트
c19 [MD]  섹션 6 헤더
c20 [코드] _execute_trading_sync() 정의 + 1턴 단계별 실행
c21 [코드] N_TURNS 다수 턴 시뮬레이션
c22 [MD]  섹션 7 헤더
c23 [코드] 체결 내역 테이블
c24 [코드] 최종 수익률 요약
c25 [코드] 2×2 시각화 (총자산, 구성, 상승종목수, 보유종목수)
```

---

## 4. 작업 3 — `SMTM_AIO_kw.ipynb` 구현 (Kiwoom REST API 주식)

### 암호화폐 → 주식 주요 차이점

| 항목 | 암호화폐 (`SMTM_AIO.ipynb`) | 주식 (`SMTM_AIO_kw.ipynb`) |
|------|------------------------------|---------------------------|
| API 인증 | 불필요 (공개 API) | APP_KEY + APP_SECRET → Bearer 토큰 |
| 종목코드 | `"KRW-XRP"` | `"005930"` (6자리) |
| 주문 수량 타입 | `float` (소수점 허용) | `int` **(정수 주 필수)** |
| 주문 가격 | 현재가 그대로 | **호가 단위 절사** (`floor_to_tick`) |
| 매수 비용 | 수수료 0.05% | 수수료 **0.015%** |
| 매도 비용 | 수수료 0.05% | 수수료 0.015% + **거래세 0.18%** |
| 장 운영시간 | 24시간 | **평일 09:00~15:30** |
| 가격 제한 | 없음 | 전일 종가 ±30% |
| 결제 | 즉시 | T+2 (시뮬에서 즉시) |
| 시장 구분 | 없음 | KOSPI / KOSDAQ |

### 신규 추가 함수

#### 호가 단위

```python
def calc_tick_size(price: float) -> int:
    """국내 주식시장 호가 단위 (2023년 기준)"""
    if price < 1_000:      return 1
    elif price < 5_000:    return 5
    elif price < 10_000:   return 10
    elif price < 50_000:   return 50
    elif price < 100_000:  return 100
    elif price < 500_000:  return 500
    else:                  return 1_000

def floor_to_tick(price: float) -> int:
    """호가 단위 아래로 절사 — 매수 주문 시 사용"""
    tick = calc_tick_size(price)
    return (int(price) // tick) * tick
```

#### 장 운영시간

```python
def is_market_open() -> bool:
    """평일 09:00~15:30 (한국 로컬 시간 기준)"""
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    return now.replace(hour=9, minute=0) <= now <= now.replace(hour=15, minute=30)
```

### Kiwoom REST API 엔드포인트

| 역할 | 메서드 | 엔드포인트 |
|------|--------|-----------|
| 토큰 발급 | `POST` | `/oauth2/token` |
| 현재가 조회 | `GET` | `/api/dostk/stkinfo?stk_code={code}` |
| 1분봉 조회 | `GET` | `/api/dostk/minchart?stk_code={code}&tic_scope=1` |
| 시장 종목 조회 | `GET` | `/api/dostk/mrktlstinfo?market=K0` (K0=KOSPI, K1=KOSDAQ) |

**현재가 응답 특이사항**: `cur_prc` 필드가 하락 시 음수로 반환 → `abs()` 처리 필수

```json
{"output": {"stk_code": "005930", "cur_prc": "-67400", ...}}
```

### 신규 구현 클래스

#### `KosdaqRisingDataProvider`

```
[Kiwoom /oauth2/token]
    → Bearer Access Token
    → [/api/dostk/mrktlstinfo] KOSPI + KOSDAQ 전체 종목
    → 가격 필터 (MIN_PRICE=5,000 ~ MAX_PRICE=200,000 KRW)
    → [/api/dostk/minchart] 1분봉 10개 (종목별)
    → is_continuously_rising() 판별
    → 상승비율 내림차순 → 상위 TOP_N
    → primary_candle 리스트 반환 (name, market_type, rise_ratio, rank 추가)
```

**반환 스키마 확장 필드**

| 필드 | 설명 |
|------|------|
| `market` | 종목코드 (`"005930"`) — strategy/trader 라우팅 키 |
| `name` | 종목명 (`"삼성전자"`) |
| `market_type` | `"KOSPI"` 또는 `"KOSDAQ"` |
| `rise_ratio` | 상승비율 (소수) |
| `rank` | 상승비율 순위 |

#### `StrategyStockRising(Strategy)`

**매수 주문 생성 로직 (정수 주)**

```python
order_price = floor_to_tick(current_price)    # 호가 단위 절사
net_budget  = budget / (1 + BUY_COMMISSION)   # 수수료 고려
shares      = max(1, int(net_budget // order_price))
# 실제 비용 재확인 루프 (잔고 초과 시 shares--)
```

**매도 비용 계산 (시장구분별 거래세)**

```python
tax_rate = SELL_TAX_KOSDAQ if market_type == "KOSDAQ" else SELL_TAX_KOSPI
cost     = round(total * (SELL_COMMISSION + tax_rate))
balance  += (total - cost)
```

**파라미터 변경**

| 파라미터 | 암호화폐 | 주식 | 이유 |
|---------|---------|------|------|
| `STOP_LOSS_RATIO` | 3% | **5%** | 주식 intraday 변동폭 더 큼 |
| `MAX_BUY_AMOUNT` | 50,000원 | **1,000,000원** | 최소 1주 매수를 위한 충분한 예산 |
| `INITIAL_BUDGET` | 300,000원 | **5,000,000원** | 주식 1주 단가가 높음 |

#### `MockStockTrader`

- 매수: `balance -= (total + fee)` (fee = total × 0.015%)
- 매도: `balance += (total - fee - tax)` (fee=0.015%, tax=0.18%)
- `trade_log`에 `fee`, `tax` 필드 분리 기록
- 정수 `shares` 타입 강제

### 데모 종목 목록 (21개)

**KOSPI (가격 필터 통과 예상)**

| 코드 | 종목명 | 가격(KRW) |
|------|--------|----------|
| 005930 | 삼성전자 | 67,400 |
| 003550 | LG | 68,000 |
| 066570 | LG전자 | 73,600 |
| 055550 | 신한지주 | 47,250 |
| 105560 | KB금융 | 68,400 |
| 086790 | 하나금융지주 | 52,400 |
| 035720 | 카카오 | 38,500 |
| 028260 | 삼성물산 | 106,500 |
| 068270 | 셀트리온 | 148,000 |
| 352820 | 하이브 | 165,000 |

**KOSDAG**

| 코드 | 종목명 | 가격(KRW) |
|------|--------|----------|
| 263750 | 펄어비스 | 39,850 |
| 251270 | 넷마블 | 49,200 |
| 112040 | 위메이드 | 24,850 |
| 041510 | 에스엠 | 65,800 |
| 035900 | JYP엔터 | 49,000 |
| 086520 | 에코프로 | 65,200 |
| 196170 | 알테오젠 | 148,000 |
| 293490 | 카카오게임즈 | 14,100 |

### 거래 비용 검증 결과

```
삼성전자(KOSPI) 10주 매수 @ 67,400원
  수수료: 101원 (0.015%)
  총 비용: 674,101원

삼성전자(KOSPI) 10주 매도 @ 67,900원
  수수료:   102원 (0.015%)
  거래세: 1,222원 (0.18%)
  실수령: 677,676원
  손익:     +3,575원 (0.015주가상승 - 비용)
```

### 실행 검증 결과

```
DEMO_MODE=True, 가격 필터: 5,000~200,000 KRW, 20개 종목
→ Turn 1: [BUY]LG전자×13주 @ 75,600원 (호가단위 100원 적용)
→ Turn 2~5: 상승 종목 0개 (합성 데이터 특성)
→ 체결 내역: 매수 1건, 수수료 147원, 거래세 0원(미매도)
→ 총자산: 4,999,853 KRW / 수익률: -0.0029%
```

### 노트북 셀 구성

```
k00 [MD]  타이틀, 비교표, 데이터 흐름 개요
k01 [코드] imports, Kiwoom API 설정, 전역 파라미터, 거래 비용 상수
k02 [코드] NbLogCapture 로깅 설정
k03 [MD]  섹션 1 헤더 (인증 + 종목 조회)
k04 [코드] DEMO_STOCK_LIST, _get_access_token(), 인증 + 전체 종목 조회
k05 [코드] 현재가 조회 + 가격 필터 → price_filtered
k06 [MD]  섹션 2 헤더 (10분간 지속 상승)
k07 [코드] calc_tick_size(), floor_to_tick(), ceil_to_tick(), is_market_open() — 호가단위 검증
k08 [코드] _fetch_real_candles(), _make_demo_candles(), is_continuously_rising(), calc_rise_ratio() — 함수 검증
k09 [코드] 전체 필터링 → rising_assets (장 운영시간 경고 포함)
k10 [코드] 상승비율 바차트 + 가격 추이 시각화
k11 [MD]  섹션 3 헤더 (KosdaqRisingDataProvider)
k12 [코드] KosdaqRisingDataProvider 클래스 정의
k13 [코드] get_info() 테스트 (호가단위·종목명·market_type 확인)
k14 [MD]  섹션 4 헤더 (StrategyStockRising)
k15 [코드] StrategyStockRising 클래스 정의
k16 [코드] 전략 초기화 + 호가단위 적용 검증
k17 [MD]  섹션 5 헤더 (MockStockTrader)
k18 [코드] MockStockTrader 클래스 정의 (fee + tax 분리)
k19 [코드] 매수/매도 테스트 (수수료·거래세 검증)
k20 [MD]  섹션 6 헤더 (트레이딩 루프)
k21 [코드] _execute_trading_sync() + 1턴 단계별 (호가단위 주문가 확인)
k22 [코드] 호가단위 적용 상세 확인 (상위 5종목 주문가·수량 계산 표)
k23 [코드] N_TURNS 다수 턴 시뮬레이션
k24 [MD]  섹션 7 헤더
k25 [코드] 체결 내역 (fee, tax 분리 표시)
k26 [코드] 최종 수익률 요약 (보유 종목별 평가손익 포함)
k27 [코드] 2×2 시각화
```

---

## 5. 공통 설계 원칙 (두 노트북 모두 적용)

### 에러 발생 셀 로그 출력 방식

```python
nb_log = NbLogCapture()   # 전역 핸들러

# 각 셀 시작 시
nb_log.clear()
try:
    # 리스크 있는 작업
    ...
except Exception as e:
    nb_log.flush_on_error("에러 발생 시 수집된 로그")
    raise
```

`NbLogCapture.flush_on_error()` 는 에러 발생 시에만 수집된 로그 전체를 출력하며, 정상 실행 시에는 아무것도 출력하지 않아 노트북 출력을 깔끔하게 유지한다.

### `DEMO_MODE` 동작 방식

| `DEMO_MODE` | 동작 |
|-------------|------|
| `True` | 하드코딩된 샘플 종목 + 합성 캔들 데이터 사용 (API 키 불필요) |
| `False` | 실시간 API 호출 (Upbit 공개 API 또는 Kiwoom Bearer 토큰 필요) |

합성 캔들 데이터는 `random` 모듈로 생성되므로 매 실행마다 달라진다. 지속 상승 조건(strict monotonic increase)은 주식의 경우 호가 단위 단위 이동으로 더 엄격하다.

### 트레이딩 루프 5단계 (동기 실행)

```
Step 1  DataProvider.get_info()              → trading_info
Step 2  Strategy.update_trading_info(info)   → 랭킹/현재가 캐시 갱신
Step 3  Strategy.get_request()               → 매수/매도 요청 리스트
Step 4  Trader.send_request(reqs, callback)  → 즉시 체결
Step 5  (callback 내) Strategy.update_result → 잔고/보유량 반영
```

스레딩 없이 `_execute_trading_sync()` 함수 한 번의 호출로 5단계를 완료한다.

---

## 6. 파일 위치

```
smtm2/
├── SMTM_AIO.ipynb        # 작업 2 산출물 — Upbit 암호화폐 멀티에셋 전략
├── SMTM_AIO_kw.ipynb     # 작업 3 산출물 — Kiwoom 주식 멀티에셋 전략
├── SMTM_AIO.md           # 본 문서 — 전체 작업 내역
└── output/
    ├── s2_rising_rank.png          # 섹션 2 상승비율 랭킹 차트 (암호화폐)
    ├── s7_simulation_result.png    # 섹션 7 시뮬레이션 결과 차트 (암호화폐)
    ├── kw_s2_rising_rank.png       # 섹션 2 상승비율 랭킹 차트 (주식)
    └── kw_s7_simulation_result.png # 섹션 7 시뮬레이션 결과 차트 (주식)
```
