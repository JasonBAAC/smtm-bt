# SMTM (Show Me The Money) 프로젝트 상세 분석

`smtm` 프로젝트는 파이썬 기반의 암호화폐 자동 매매 시스템으로, 데이터 수집부터 전략 실행, 실제 거래 및 결과 분석까지의 전 과정을 자동화합니다. 이 프로젝트는 확장성과 유연성을 극대화하기 위해 각 기능을 모듈화한 **계층형 아키텍처(Layered Architecture)**를 채택하고 있습니다.

## 1. 전체 구조 및 워크플로우
시스템은 설정된 주기(기본 10초)마다 다음 과정을 반복합니다.
1. **데이터 수집**: `DataProvider`가 시장 데이터를 가져옴
2. **전략 판단**: `Strategy`가 데이터를 분석하여 매수/매도/관망 결정
3. **거래 실행**: `Trader`가 결정된 요청을 거래소(또는 가상 시장)에 전달
4. **결과 기록 및 분석**: `Analyzer`가 모든 과정을 기록하고 수익률 및 그래프 생성
5. **반복**: `Operator`가 이 전체 과정을 제어하며 주기적으로 실행

---

## 2. 주요 구성 요소 (Core Modules)

### 1) Operator (`smtm/operator.py`)
시스템의 **심장** 역할을 하며, 모든 모듈을 연결하고 실행 흐름을 제어합니다.
- `initialize()`: 사용할 데이터 제공자, 전략, 트레이더, 분석기를 설정합니다.
- `_execute_trading()`: 핵심 매매 루프입니다. 데이터를 가져와 전략에 전달하고, 생성된 요청을 트레이더에게 보내 실행합니다.
- `start() / stop()`: 백그라운드 스레드(`Worker`)를 통해 자동 매매를 시작하거나 중지합니다.

### 2) Data Provider (`smtm/data/`)
다양한 소스로부터 시장 데이터를 공급하는 인터페이스입니다.
- `UpbitDataProvider`, `BithumbDataProvider`, `BinanceDataProvider`: 실시간 거래소 API를 통해 OHLCV(시가, 고가, 저가, 종가, 거래량) 데이터를 가져옵니다.
- `SimulationDataProvider`: 과거의 대량 데이터를 로드하여 시뮬레이션(백테스팅)용 데이터를 공급합니다.

### 3) Strategy (`smtm/strategy/`)
매매 로직이 담긴 **두뇌** 부분입니다.
- `update_trading_info()`: 새로운 시장 데이터를 받아 지표를 계산합니다.
- `get_request()`: 현재 상태를 바탕으로 매수/매도 요청 리스트를 생성합니다.
- `StrategyBuyAndHold`: 단순히 사서 보유하는 전략.
- `StrategySmaMl`: 이동평균선(SMA)과 머신러닝 모델을 결합한 고도화된 전략.

### 4) Trader (`smtm/trader/`)
실제 거래소 API와 통신하거나 가상 시장을 관리합니다.
- `send_request()`: 매매 요청을 실행하고 결과를 콜백으로 전달합니다.
- `UpbitTrader`, `BithumbTrader`: 실제 API Key를 사용하여 실제 자산을 운용합니다.
- `SimulationTrader`: 과거 데이터를 바탕으로 `VirtualMarket`에서 가상의 체결을 수행합니다.

### 5) Analyzer (`smtm/analyzer.py`)
투자의 성과를 정밀하게 추적합니다.
- `put_result()`: 체결 결과를 받아 자산 상태를 업데이트합니다.
- `create_report()`: 누적 수익률, 자산 변동 등을 텍스트 리포트와 캔들차트 그래프(`mplfinance` 활용)로 생성합니다.

---

## 3. 제어 레이어 (Controllers)
사용자가 시스템을 조작하는 인터페이스입니다.
- **Controller (`smtm/controller/controller.py`)**: 일반적인 CLI 기반 실거래 제어기.
- **Simulator (`smtm/controller/simulator.py`)**: 과거 데이터를 이용한 백테스팅 전용 제어기.
- **TelegramController**: 텔레그램 봇을 통해 원격으로 매매를 시작/중지하고 수익률을 확인합니다.
- **JptController**: 주피터 노트북 환경에서 대화형으로 매매를 제어합니다.

## 4. 핵심 유틸리티
- **Worker (`smtm/worker.py`)**: 메인 스레드가 멈추지 않도록 별도의 스레드에서 작업을 순차적으로 처리하는 큐 기반 워커입니다.
- **LogManager (`smtm/log_manager.py`)**: 시스템 전체의 로그를 관리하며 파일 및 콘솔 출력을 제어합니다.

## 요약
이 프로젝트는 **`Operator`**가 중심이 되어 **`DataProvider`**로부터 받은 데이터를 **`Strategy`**에 전달하고, 결정된 내용을 **`Trader`**를 통해 실행하며, 그 결과를 **`Analyzer`**가 기록하는 구조입니다. 이러한 모듈화 덕분에 새로운 거래소나 새로운 전략을 추가할 때 기존 코드를 거의 수정하지 않고도 쉽게 확장할 수 있는 강점을 가지고 있습니다.
