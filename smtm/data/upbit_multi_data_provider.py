import requests
from .data_provider import DataProvider
from ..log_manager import LogManager


class UpbitMultiDataProvider(DataProvider):
    """
    여러 가상화폐 종목의 분봉 데이터를 동시에 제공하는 클래스

    get_info() 호출 시 설정된 모든 종목의 현재 분봉 캔들을 리스트로 반환한다.
    각 캔들은 type="primary_candle" 형식이며 market 필드로 종목을 구분한다.
    """

    AVAILABLE_CURRENCY = {
        "BTC": "KRW-BTC",
        "ETH": "KRW-ETH",
        "XRP": "KRW-XRP",
        "DOGE": "KRW-DOGE",
        "ADA": "KRW-ADA",
        "SOL": "KRW-SOL",
        "AVAX": "KRW-AVAX",
        "MATIC": "KRW-MATIC",
        "DOT": "KRW-DOT",
        "TRX": "KRW-TRX",
        "LINK": "KRW-LINK",
        "ATOM": "KRW-ATOM",
    }

    INTERVAL_TO_MINUTES = {60: 1, 180: 3, 300: 5, 600: 10}
    CODE = "UPMUL"
    NAME = "UPBIT Multi DP"

    def __init__(self, currency_list=None, interval=60):
        if interval not in self.INTERVAL_TO_MINUTES:
            raise UserWarning(f"not supported interval: {interval}")

        self.logger = LogManager.get_logger(__class__.__name__)
        minutes = self.INTERVAL_TO_MINUTES[interval]
        self.base_url = f"https://api.upbit.com/v1/candles/minutes/{minutes}"
        self.interval = interval

        if currency_list is None:
            currency_list = list(self.AVAILABLE_CURRENCY.keys())

        self.currency_list = [c for c in currency_list if c in self.AVAILABLE_CURRENCY]
        if not self.currency_list:
            raise UserWarning("no valid currencies provided")

        self.logger.info(f"UpbitMultiDataProvider initialized: {self.currency_list}")

    def get_info(self):
        """설정된 모든 종목의 현재 분봉 캔들을 반환

        Returns: 캔들 딕셔너리 리스트 (type="primary_candle")
        """
        result = []
        for currency in self.currency_list:
            market = self.AVAILABLE_CURRENCY[currency]
            candle = self._fetch_candle(currency, market)
            if candle is not None:
                result.append(candle)
        return result

    def _fetch_candle(self, currency, market):
        params = {"market": market, "count": 1}
        try:
            response = requests.get(self.base_url, params=params)
            response.raise_for_status()
            data = response.json()
            if not data:
                return None
            return self._create_candle_info(currency, data[0])
        except ValueError as error:
            self.logger.error(f"Invalid data from server for {currency}: {error}")
            return None
        except requests.exceptions.HTTPError as error:
            self.logger.error(f"HTTP error for {currency}: {error}")
            return None
        except requests.exceptions.RequestException as error:
            self.logger.error(f"Request error for {currency}: {error}")
            return None

    def _create_candle_info(self, currency, data):
        try:
            return {
                "type": "primary_candle",
                "market": currency,
                "date_time": data["candle_date_time_kst"],
                "opening_price": float(data["opening_price"]),
                "high_price": float(data["high_price"]),
                "low_price": float(data["low_price"]),
                "closing_price": float(data["trade_price"]),
                "acc_price": float(data["candle_acc_trade_price"]),
                "acc_volume": float(data["candle_acc_trade_volume"]),
            }
        except KeyError as err:
            self.logger.warning(f"invalid candle data for {currency}: {err}")
            return None
