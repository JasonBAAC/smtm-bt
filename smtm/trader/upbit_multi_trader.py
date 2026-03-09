from datetime import datetime
from ..log_manager import LogManager
from .trader import Trader
from .upbit_trader import UpbitTrader


class UpbitMultiTrader(Trader):
    """
    여러 가상화폐 종목을 동시에 거래할 수 있는 멀티 트레이더

    종목별 UpbitTrader 인스턴스를 관리하고, 요청의 market 필드를 기준으로
    적절한 sub-trader에 주문을 라우팅한다.
    """

    AVAILABLE_CURRENCY = {
        "BTC": ("KRW-BTC", "BTC"),
        "ETH": ("KRW-ETH", "ETH"),
        "XRP": ("KRW-XRP", "XRP"),
        "DOGE": ("KRW-DOGE", "DOGE"),
        "ADA": ("KRW-ADA", "ADA"),
        "SOL": ("KRW-SOL", "SOL"),
        "AVAX": ("KRW-AVAX", "AVAX"),
        "MATIC": ("KRW-MATIC", "MATIC"),
        "DOT": ("KRW-DOT", "DOT"),
        "TRX": ("KRW-TRX", "TRX"),
        "LINK": ("KRW-LINK", "LINK"),
        "ATOM": ("KRW-ATOM", "ATOM"),
    }
    NAME = "Upbit Multi"

    def __init__(self, budget_per_currency=50000, currency_list=None, commission_ratio=0.0005):
        """
        budget_per_currency: 종목당 최대 매수 예산 (기본 50,000원)
        currency_list: 거래할 종목 코드 리스트 (None이면 전체)
        commission_ratio: 수수료율
        """
        self.logger = LogManager.get_logger(__class__.__name__)
        self.commission_ratio = commission_ratio

        if currency_list is None:
            currency_list = list(self.AVAILABLE_CURRENCY.keys())

        # UpbitTrader의 AVAILABLE_CURRENCY를 임시 확장하여 sub-trader 생성
        _orig = dict(UpbitTrader.AVAILABLE_CURRENCY)
        UpbitTrader.AVAILABLE_CURRENCY.update(self.AVAILABLE_CURRENCY)

        self.traders = {}
        for currency in currency_list:
            if currency in self.AVAILABLE_CURRENCY:
                self.traders[currency] = UpbitTrader(
                    budget=budget_per_currency,
                    currency=currency,
                    commission_ratio=commission_ratio,
                )

        # UpbitTrader AVAILABLE_CURRENCY 원복
        UpbitTrader.AVAILABLE_CURRENCY.clear()
        UpbitTrader.AVAILABLE_CURRENCY.update(_orig)

        if not self.traders:
            raise UserWarning("no valid currencies for trader")

        self.logger.info(f"UpbitMultiTrader initialized: {list(self.traders.keys())}")

    def send_request(self, request_list, callback):
        """거래 요청을 market 필드에 따라 해당 종목의 sub-trader로 전달

        request에 "market" 필드(예: "ETH")가 필요하다.
        """
        for request in request_list:
            market = request.get("market")
            if market is None or market not in self.traders:
                self.logger.warning(f"unknown or missing market in request: {market}")
                continue
            self.traders[market].send_request([request], callback)

    def cancel_request(self, request_id):
        """모든 sub-trader에서 해당 request_id 취소 시도"""
        for trader in self.traders.values():
            trader.cancel_request(request_id)

    def cancel_all_requests(self):
        """모든 sub-trader의 대기 중인 요청을 취소"""
        for trader in self.traders.values():
            trader.cancel_all_requests()

    def get_account_info(self):
        """모든 종목의 내부 상태를 통합하여 반환 (API 호출 없음)"""
        total_balance = sum(t.balance for t in self.traders.values())
        total_asset = {
            currency: t.asset
            for currency, t in self.traders.items()
            if t.asset[1] > 0
        }
        return {
            "balance": total_balance,
            "asset": total_asset,
            "quote": {},
            "date_time": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        }
