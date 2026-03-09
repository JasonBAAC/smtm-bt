import copy
import math
from datetime import datetime

from .strategy import Strategy
from ..date_converter import DateConverter
from ..log_manager import LogManager


class StrategyMultiMinute(Strategy):
    """
    분봉 기반 다중 가상화폐 매매 전략 (CODE=MMT)

    동작 개요:
    1. 여러 종목의 분봉 데이터를 수신하여 EMA + RSI로 상승추세 점수를 계산한다.
    2. 가격 필터(MIN_PRICE ~ MAX_PRICE) 적용 후 상위 WATCH_COUNT(5)종목을 선정한다.
    3. 상위 3종목(uptrend streak >= TREND_CANDLES_MIN)을 종목당 최대 MAX_BUY_AMOUNT 매수한다.
    4. 4~5위 종목은 더 강한 추세 조건(streak >= TREND_CANDLES_MAX) 충족 시 매수한다.
    5. 손절 조건(가격 하락률 초과 or EMA 데드크로스) 충족 시 매도한다.
    6. CYCLE_CANDLES마다 종목 순위를 재계산한다.

    요청 딕셔너리에 "market" 필드가 추가된다 (UpbitMultiTrader 라우팅용).
    """

    NAME = "Multi-Minute"
    CODE = "MMT"

    # ── EMA / RSI 파라미터 ────────────────────────────────────────────────
    EMA_SHORT = 5         # 단기 EMA 기간
    EMA_LONG = 20         # 장기 EMA 기간
    RSI_PERIOD = 14       # RSI 기간

    # ── 추세 확인 조건 ────────────────────────────────────────────────────
    TREND_CANDLES_MIN = 3  # 상위 3종목 매수에 필요한 최소 상승 연속 캔들 수
    TREND_CANDLES_MAX = 5  # 4~5위 종목 매수에 필요한 최소 상승 연속 캔들 수

    # ── 히스토리 / 선정 조건 ─────────────────────────────────────────────
    HISTORY_SIZE = 50     # 종목별 가격 이력 최대 크기
    MAX_BUY_COUNT = 3     # 동시 보유 최대 종목 수
    WATCH_COUNT = 5       # 관찰 상위 종목 수 (3 매수 + 2 관찰)
    MAX_BUY_AMOUNT = 50000   # 종목당 최대 매수 금액 (KRW)
    MIN_PRICE = 1000         # 모집단 가격 하한
    MAX_PRICE = 999999999    # 모집단 가격 상한

    # ── 손절 / 수수료 ────────────────────────────────────────────────────
    STOP_LOSS_RATIO = 0.03   # 손절 가격 하락률 (3%)
    COMMISSION_RATIO = 0.0005

    # ── 주기 설정 (1분봉 기준) ────────────────────────────────────────────
    # 10 → 10분 주기, 20 → 20분 주기, 30 → 30분 주기
    CYCLE_CANDLES = 10

    def __init__(self):
        self.is_initialized = False
        self.is_simulation = False
        self.logger = LogManager.get_logger(__class__.__name__)

        self.budget = 0
        self.balance = 0
        self.min_price = 0

        # {currency: [closing_price, ...]}  rolling window
        self.price_history = {}

        # {currency: int}  연속 상승 캔들 수
        self.uptrend_streak = {}

        # {currency: {"amount": float, "avg_price": float}}  현재 보유
        self.holdings = {}

        # {request_id: {"market": str, "type": str}}  주문 대기
        self.waiting_requests = {}

        # [currency, ...]  상위 WATCH_COUNT 종목 (랭킹 순)
        self.rankings = []

        # 현재 주기 내 캔들 카운터
        self.cycle_counter = 0

        self.result = []
        self.add_spot_callback = None
        self.add_line_callback = None
        self.alert_callback = None

    # ── Strategy 인터페이스 ───────────────────────────────────────────────

    def initialize(self, budget, min_price=100, add_spot_callback=None,
                   add_line_callback=None, alert_callback=None):
        """전략 초기화

        budget: 초기 예산 (KRW)
        min_price: 최소 주문 금액 (Operator에서 전달, 기본 100)
        """
        self.budget = budget
        self.balance = budget
        self.min_price = min_price
        self.add_spot_callback = add_spot_callback
        self.add_line_callback = add_line_callback
        self.alert_callback = alert_callback
        self.is_initialized = True
        self.logger.info(
            f"[{self.NAME}] initialized budget={budget}, min_price={min_price}, "
            f"cycle={self.CYCLE_CANDLES}candles, stop_loss={self.STOP_LOSS_RATIO*100}%"
        )

    def update_trading_info(self, info):
        """새 분봉 데이터로 전략 상태를 갱신한다

        info: 캔들 딕셔너리 리스트 (type="primary_candle")
        한 번 호출 = 1 time-step (여러 종목 캔들이 동시에 도착)
        """
        if not self.is_initialized:
            return

        for item in info:
            if not isinstance(item, dict) or item.get("type") != "primary_candle":
                continue
            currency = item["market"]
            closing = float(item["closing_price"])

            if currency not in self.price_history:
                self.price_history[currency] = []

            hist = self.price_history[currency]
            hist.append(closing)
            if len(hist) > self.HISTORY_SIZE:
                hist.pop(0)

            self._update_uptrend_streak(currency)

        # 주기 관리
        self.cycle_counter += 1
        if self.cycle_counter >= self.CYCLE_CANDLES:
            self._recalculate_rankings()
            self.cycle_counter = 0
        elif not self.rankings:
            # 데이터 충분하면 초기 랭킹 계산
            self._recalculate_rankings()

    def get_request(self):
        """매수/매도 요청 리스트를 반환한다

        Returns: 요청 딕셔너리 리스트 or None
        각 요청에 "market" 필드 포함 (UpbitMultiTrader 라우팅용)
        """
        if not self.is_initialized or not self.rankings:
            return None

        requests = []

        pending_sell = {
            v["market"] for v in self.waiting_requests.values() if v["type"] == "sell"
        }
        pending_buy = {
            v["market"] for v in self.waiting_requests.values() if v["type"] == "buy"
        }

        # ── 1. 손절 체크: 보유 종목 중 조건 충족 시 매도 ─────────────────
        for currency in list(self.holdings.keys()):
            if currency in pending_sell:
                continue
            prices = self.price_history.get(currency, [])
            if not prices:
                continue
            current_price = prices[-1]
            reason = self._check_stop_loss(currency, current_price)
            if reason:
                req = self._create_sell_request(currency, current_price)
                if req:
                    requests.append(req)
                    self.logger.info(
                        f"[SELL/{reason}] {currency} @ {current_price}"
                    )

        # ── 2. 매수 체크: 랭킹 종목 중 조건 충족 시 매수 ─────────────────
        # 실제 보유 수 = 보유 종목(매도 대기 제외) + 매수 대기 종목
        active_count = (
            len([c for c in self.holdings if c not in pending_sell])
            + len(pending_buy)
        )

        for i, currency in enumerate(self.rankings):
            if active_count >= self.MAX_BUY_COUNT:
                break
            if currency in self.holdings or currency in pending_buy:
                continue

            streak = self.uptrend_streak.get(currency, 0)

            # 상위 3종목: TREND_CANDLES_MIN, 4~5위: TREND_CANDLES_MAX
            required_streak = (
                self.TREND_CANDLES_MAX if i >= self.MAX_BUY_COUNT
                else self.TREND_CANDLES_MIN
            )
            if streak < required_streak:
                continue

            prices = self.price_history.get(currency, [])
            if not prices:
                continue
            current_price = prices[-1]

            if not (self.MIN_PRICE <= current_price <= self.MAX_PRICE):
                continue

            buy_amount = min(self.MAX_BUY_AMOUNT, self.balance)
            if buy_amount < self.min_price:
                continue

            req = self._create_buy_request(currency, current_price, buy_amount)
            if req:
                requests.append(req)
                active_count += 1
                self.logger.info(
                    f"[BUY/rank={i+1}/streak={streak}] {currency} @ {current_price}"
                )

        return requests if requests else None

    def update_result(self, result):
        """체결 결과를 처리하여 잔고/보유량을 갱신한다"""
        if not isinstance(result, dict):
            return

        if result.get("state") == "requested":
            return

        if result.get("state") != "done":
            return

        request = result.get("request", {})
        req_id = request.get("id")
        if req_id in self.waiting_requests:
            del self.waiting_requests[req_id]

        currency = request.get("market")
        if not currency:
            return

        trade_type = result.get("type")
        price = float(result.get("price", 0))
        amount = float(result.get("amount", 0))

        if price <= 0 or amount <= 0:
            return

        total = price * amount
        fee = total * self.COMMISSION_RATIO

        if trade_type == "buy":
            self.balance -= round(total + fee)
            if currency not in self.holdings:
                self.holdings[currency] = {"amount": 0.0, "avg_price": 0.0}
            old = self.holdings[currency]
            old_value = old["avg_price"] * old["amount"]
            new_amount = old["amount"] + amount
            self.holdings[currency] = {
                "amount": round(new_amount, 6),
                "avg_price": round((old_value + total) / new_amount, 6),
            }
            self.logger.info(
                f"[BUY done] {currency} {amount}@{price}, balance={self.balance}"
            )

        elif trade_type == "sell":
            self.balance += round(total - fee)
            if currency in self.holdings:
                new_amount = round(self.holdings[currency]["amount"] - amount, 6)
                if new_amount <= 0:
                    del self.holdings[currency]
                else:
                    self.holdings[currency]["amount"] = new_amount
            self.logger.info(
                f"[SELL done] {currency} {amount}@{price}, balance={self.balance}"
            )

        self.result.append(copy.deepcopy(result))

    # ── Private 헬퍼 ─────────────────────────────────────────────────────

    def _has_enough_history(self, currency):
        needed = max(self.EMA_LONG, self.RSI_PERIOD + 1)
        return len(self.price_history.get(currency, [])) >= needed

    def _update_uptrend_streak(self, currency):
        """EMA + RSI 기반으로 해당 종목의 상승 연속 캔들 수를 갱신한다"""
        if not self._has_enough_history(currency):
            self.uptrend_streak[currency] = 0
            return

        prices = self.price_history[currency]
        ema_s = self._calc_ema(prices, self.EMA_SHORT)
        ema_l = self._calc_ema(prices, self.EMA_LONG)
        rsi = self._calc_rsi(prices, self.RSI_PERIOD)

        if ema_s is None or ema_l is None or rsi is None:
            self.uptrend_streak[currency] = 0
            return

        # 상승추세: 단기EMA > 장기EMA  AND  RSI > 50 (상승 모멘텀)
        if ema_s > ema_l and rsi > 50:
            self.uptrend_streak[currency] = self.uptrend_streak.get(currency, 0) + 1
        else:
            self.uptrend_streak[currency] = 0

    def _recalculate_rankings(self):
        """모든 종목의 추세 점수를 계산하고 상위 WATCH_COUNT 종목을 선정한다"""
        scores = {}
        for currency, prices in self.price_history.items():
            if not self._has_enough_history(currency):
                continue
            if not (self.MIN_PRICE <= prices[-1] <= self.MAX_PRICE):
                continue
            score = self._calc_trend_score(currency)
            if score > 0:
                scores[currency] = score

        ranked = sorted(scores, key=lambda c: scores[c], reverse=True)
        self.rankings = ranked[: self.WATCH_COUNT]
        self.logger.info(
            f"[Rankings] {[(c, round(scores[c], 4)) for c in self.rankings]}"
        )

    def _calc_trend_score(self, currency):
        """EMA 갭 + RSI 점수를 합산한 추세 강도를 반환한다 (0이면 하락 또는 중립)"""
        prices = self.price_history[currency]
        ema_s = self._calc_ema(prices, self.EMA_SHORT)
        ema_l = self._calc_ema(prices, self.EMA_LONG)
        rsi = self._calc_rsi(prices, self.RSI_PERIOD)

        if ema_s is None or ema_l is None or rsi is None:
            return 0
        if ema_s <= ema_l or rsi < 50:
            return 0

        ema_gap = (ema_s - ema_l) / ema_l  # 상대적 EMA 갭

        # RSI 점수: 50~70 구간을 이상적으로 보고, 70 초과는 과매수로 패널티
        if rsi <= 70:
            rsi_score = (rsi - 50) / 20.0
        else:
            rsi_score = max(0.0, 1.0 - (rsi - 70) / 30.0)

        return ema_gap + rsi_score * 0.5

    def _check_stop_loss(self, currency, current_price):
        """손절 조건 확인. 해당 이유 문자열 반환, 없으면 None"""
        holding = self.holdings.get(currency)
        if not holding:
            return None

        # 가격 손절: 매수 평균가 대비 STOP_LOSS_RATIO% 이상 하락
        if current_price < holding["avg_price"] * (1 - self.STOP_LOSS_RATIO):
            return "price_drop"

        # 추세 반전: 단기EMA < 장기EMA (데드크로스)
        if self._has_enough_history(currency):
            prices = self.price_history[currency]
            ema_s = self._calc_ema(prices, self.EMA_SHORT)
            ema_l = self._calc_ema(prices, self.EMA_LONG)
            if ema_s is not None and ema_l is not None and ema_s < ema_l:
                return "trend_reversal"

        return None

    def _create_buy_request(self, currency, price, budget):
        """매수 요청 딕셔너리를 생성하고 waiting_requests에 등록한다"""
        net_budget = budget * (1 - self.COMMISSION_RATIO)
        amount = math.floor(net_budget / price * 10000) / 10000
        if amount <= 0:
            return None

        req_id = DateConverter.timestamp_id()
        self.waiting_requests[req_id] = {"market": currency, "type": "buy"}
        return {
            "id": req_id,
            "type": "buy",
            "market": currency,
            "price": price,
            "amount": amount,
            "date_time": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        }

    def _create_sell_request(self, currency, price):
        """매도 요청 딕셔너리를 생성하고 waiting_requests에 등록한다"""
        holding = self.holdings.get(currency)
        if not holding:
            return None

        amount = math.floor(holding["amount"] * 10000) / 10000
        if amount <= 0:
            return None

        req_id = DateConverter.timestamp_id()
        self.waiting_requests[req_id] = {"market": currency, "type": "sell"}
        return {
            "id": req_id,
            "type": "sell",
            "market": currency,
            "price": price,
            "amount": amount,
            "date_time": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        }

    # ── 지표 계산 (정적 메서드) ───────────────────────────────────────────

    @staticmethod
    def _calc_ema(prices, period):
        """지수이동평균(EMA) 계산

        첫 period 값의 SMA를 시드로 사용하고 이후 값에 EMA 공식 적용.
        """
        if len(prices) < period:
            return None
        k = 2.0 / (period + 1)
        ema = sum(prices[:period]) / period  # SMA 시드
        for p in prices[period:]:
            ema = p * k + ema * (1 - k)
        return ema

    @staticmethod
    def _calc_rsi(prices, period):
        """RSI 계산 (단순 평균 방식)"""
        if len(prices) < period + 1:
            return None
        recent = prices[-(period + 1):]
        gains = [max(0.0, recent[i] - recent[i - 1]) for i in range(1, len(recent))]
        losses = [max(0.0, recent[i - 1] - recent[i]) for i in range(1, len(recent))]
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        if avg_loss == 0:
            return 100.0
        return 100.0 - (100.0 / (1 + avg_gain / avg_loss))
