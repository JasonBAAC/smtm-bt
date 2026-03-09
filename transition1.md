# 구현 내용 전체 요약 — 분봉 기반 다중 가상화폐 매매 전략 (MMT)

## 생성된 파일 (3개)

### 1. `smtm/data/upbit_multi_data_provider.py`
한 번의 `get_info()` 호출로 **12개 종목** 전체의 현재 분봉을 리스트로 반환한다.

```
지원 종목: BTC, ETH, XRP, DOGE, ADA, SOL, AVAX, MATIC, DOT, TRX, LINK, ATOM
```
- `currency_list` 파라미터로 관찰 종목 지정 가능 (None이면 전체)
- `interval` 파라미터: 60/180/300/600초 (→ 1/3/5/10분봉)

### 2. `smtm/trader/upbit_multi_trader.py`
요청의 `"market"` 필드를 보고 **종목별 UpbitTrader에 라우팅**하는 래퍼다.

```
send_request([{"market": "ETH", "type": "buy", ...}])
  → traders["ETH"].send_request(...)
```
- `budget_per_currency=50,000` (종목당 독립 예산)
- cancel, get_account_info 모두 전체 sub-trader에 위임

### 3. `smtm/strategy/strategy_multi_minute.py` (CODE=`MMT`)
핵심 전략 로직.

| 파라미터 | 값 | 설명 |
|---|---|---|
| `EMA_SHORT / EMA_LONG` | 5 / 20 | 골든/데드크로스 |
| `RSI_PERIOD` | 14 | RSI 기간 |
| `TREND_CANDLES_MIN` | 3 | 상위 3종목 매수 조건 |
| `TREND_CANDLES_MAX` | 5 | 4~5위 관찰 종목 매수 조건 |
| `MAX_BUY_COUNT` | 3 | 최대 동시 보유 종목 수 |
| `WATCH_COUNT` | 5 | 관찰 목록 크기 |
| `MAX_BUY_AMOUNT` | 50,000원 | 종목당 최대 매수 |
| `STOP_LOSS_RATIO` | 3% | 가격 손절 기준 |
| `MIN_PRICE / MAX_PRICE` | 1,000 / 999,999,999 | 모집단 가격 필터 |
| `CYCLE_CANDLES` | 10 | 재선정 주기 (10=10분, 20/30도 가능) |

**매매 흐름:**
```
매 분봉 수신
├── 종목별 EMA(5), EMA(20), RSI(14) 계산
├── 상승추세(EMA크로스 + RSI>50) 연속 횟수 갱신
├── CYCLE_CANDLES마다 → 추세 점수 재계산 → 상위 5종목 선정
│
get_request() 호출
├── [손절] 보유 종목 중: 가격 -3% or EMA 데드크로스 → SELL
└── [매수] 랭킹 1~3위(streak≥3) or 4~5위(streak≥5) → BUY (max 50,000/종목)
```

---

## 수정된 파일 (2개)

| 파일 | 변경 내용 |
|---|---|
| `smtm/strategy/strategy_factory.py` | `StrategyMultiMinute` (MMT) 등록 |
| `smtm/__init__.py` | 3개 신규 클래스 export 추가 |

---

## 사용 예시

```python
from smtm import (
    UpbitMultiDataProvider, UpbitMultiTrader,
    StrategyMultiMinute, Operator, Analyzer
)

# 12종목 1분봉
data_provider = UpbitMultiDataProvider(interval=60)

# 종목당 50,000원 예산
trader = UpbitMultiTrader(budget_per_currency=50000)

strategy = StrategyMultiMinute()
# CYCLE_CANDLES 변경: 20분 주기로 바꾸려면
# StrategyMultiMinute.CYCLE_CANDLES = 20

operator = Operator()
operator.initialize(
    data_provider, strategy, trader,
    Analyzer(), budget=300000  # 총 예산 30만원
)
operator.start()
```

---

## 아키텍처 연결 구조

```
Operator (기존 변경 없음)
  │
  ├── UpbitMultiDataProvider.get_info()
  │     └── 12종목 분봉 캔들 리스트 반환
  │
  ├── StrategyMultiMinute.update_trading_info(info)
  │     ├── 종목별 price_history 갱신
  │     ├── EMA/RSI 기반 uptrend_streak 갱신
  │     └── CYCLE_CANDLES마다 rankings 재계산
  │
  ├── StrategyMultiMinute.get_request()
  │     ├── 보유 종목 손절 체크 → sell 요청
  │     └── 랭킹 종목 매수 체크 → buy 요청 (market 필드 포함)
  │
  ├── UpbitMultiTrader.send_request(request_list, callback)
  │     └── request["market"] 기준으로 sub-UpbitTrader에 라우팅
  │
  └── StrategyMultiMinute.update_result(result)
        ├── balance 갱신
        └── holdings 갱신
```
