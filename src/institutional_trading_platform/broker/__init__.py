"""Broker integration placeholders and Phase 6 safety services."""

from .approval_mode import ApprovalModeService, ApprovalStatus, TradeApprovalDecision, TradeApprovalRequest
from .order_preview import RealOrderResult, RealOrderSafetyStatus, ZerodhaOrderPreview, ZerodhaOrderSafetyWrapper
from .reconciliation import BrokerOrderSnapshot, BrokerPositionSnapshot, BrokerReconciliationService, BrokerStateSnapshot, BrokerTradeSnapshot, LocalApprovalState, ReconciliationResult
from .sl_target_monitor import ApprovedTradePlan, ExitReason, ExitSuggestion, SLTargetMonitor
from . import zerodha_auth as _zerodha_auth
from .zerodha_instrument_manager import InstrumentResolution, InstrumentResolutionStatus, ZerodhaInstrument, ZerodhaInstrumentManager
from .zerodha_instruments import InstrumentMappingError, ZerodhaInstrumentMapper, ZerodhaInstrumentRecord
from . import zerodha_market_data as _zerodha_market_data

ZerodhaAuthConfig = _zerodha_auth.ZerodhaAuthConfig
ZerodhaAuthService = _zerodha_auth.ZerodhaAuthService
ZerodhaAuthState = _zerodha_auth.ZerodhaAuthState
ZerodhaConnectionStatus = _zerodha_auth.ZerodhaConnectionStatus
RealZerodhaProfileClient = getattr(_zerodha_auth, "RealZerodhaProfileClient", None)
ZerodhaProfileClient = getattr(_zerodha_auth, "ZerodhaProfileClient", None)
ZerodhaProfileClientError = getattr(_zerodha_auth, "ZerodhaProfileClientError", RuntimeError)
ZerodhaShadowFeedRunner = _zerodha_market_data.ZerodhaShadowFeedRunner
ZerodhaShadowFeedStatus = _zerodha_market_data.ZerodhaShadowFeedStatus
ZerodhaTickMappingResult = _zerodha_market_data.ZerodhaTickMappingResult
ZerodhaWebSocketMarketDataAdapter = _zerodha_market_data.ZerodhaWebSocketMarketDataAdapter
ReadOnlyKiteTickerStatus = getattr(_zerodha_market_data, "ReadOnlyKiteTickerStatus", None)
ReadOnlyKiteTickerWrapper = getattr(_zerodha_market_data, "ReadOnlyKiteTickerWrapper", None)

__all__ = [
    "ApprovalModeService",
    "ApprovalStatus",
    "ApprovedTradePlan",
    "BrokerOrderSnapshot",
    "BrokerPositionSnapshot",
    "BrokerReconciliationService",
    "BrokerStateSnapshot",
    "BrokerTradeSnapshot",
    "ExitReason",
    "ExitSuggestion",
    "InstrumentMappingError",
    "InstrumentResolution",
    "InstrumentResolutionStatus",
    "LocalApprovalState",
    "RealOrderResult",
    "RealOrderSafetyStatus",
    "RealZerodhaProfileClient",
    "ReadOnlyKiteTickerStatus",
    "ReadOnlyKiteTickerWrapper",
    "ReconciliationResult",
    "SLTargetMonitor",
    "TradeApprovalDecision",
    "TradeApprovalRequest",
    "ZerodhaAuthConfig",
    "ZerodhaAuthService",
    "ZerodhaAuthState",
    "ZerodhaConnectionStatus",
    "ZerodhaProfileClient",
    "ZerodhaProfileClientError",
    "ZerodhaInstrument",
    "ZerodhaInstrumentManager",
    "ZerodhaInstrumentMapper",
    "ZerodhaInstrumentRecord",
    "ZerodhaOrderPreview",
    "ZerodhaOrderSafetyWrapper",
    "ZerodhaShadowFeedRunner",
    "ZerodhaShadowFeedStatus",
    "ZerodhaTickMappingResult",
    "ZerodhaWebSocketMarketDataAdapter",
]
