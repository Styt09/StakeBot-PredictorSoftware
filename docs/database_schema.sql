-- Institutional Trading Platform v9.0 database schema foundation.
-- Designed for PostgreSQL-compatible engines.

CREATE TABLE instruments (
    instrument_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    venue TEXT NOT NULL,
    asset_class TEXT NOT NULL,
    currency CHAR(3) NOT NULL,
    lot_size INTEGER NOT NULL CHECK (lot_size > 0),
    tick_size NUMERIC NOT NULL CHECK (tick_size > 0),
    isin TEXT,
    expiry TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE market_bars (
    instrument_id TEXT NOT NULL REFERENCES instruments(instrument_id),
    ts TIMESTAMPTZ NOT NULL,
    open NUMERIC NOT NULL CHECK (open > 0),
    high NUMERIC NOT NULL CHECK (high > 0),
    low NUMERIC NOT NULL CHECK (low > 0),
    close NUMERIC NOT NULL CHECK (close > 0),
    volume NUMERIC NOT NULL CHECK (volume >= 0),
    source TEXT NOT NULL,
    received_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (instrument_id, ts, source)
);

CREATE TABLE data_contracts (
    contract_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    version TEXT NOT NULL,
    owner TEXT NOT NULL,
    description TEXT NOT NULL,
    schema JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE datasets (
    name TEXT PRIMARY KEY,
    contract_id TEXT NOT NULL REFERENCES data_contracts(contract_id),
    storage_uri TEXT NOT NULL,
    owner TEXT NOT NULL,
    tags TEXT[] NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE features (
    feature_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    version TEXT NOT NULL,
    entity TEXT NOT NULL,
    expression TEXT NOT NULL,
    owner TEXT NOT NULL,
    source_datasets TEXT[] NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE signal_decisions (
    decision_id BIGSERIAL PRIMARY KEY,
    instrument_id TEXT REFERENCES instruments(instrument_id),
    decision TEXT NOT NULL,
    confidence NUMERIC NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    payload JSONB NOT NULL,
    rejected_gates JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE order_intents (
    client_order_id TEXT PRIMARY KEY,
    instrument_id TEXT NOT NULL REFERENCES instruments(instrument_id),
    side TEXT NOT NULL,
    order_type TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    limit_price NUMERIC CHECK (limit_price > 0),
    status TEXT NOT NULL DEFAULT 'CREATED',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE audit_events (
    event_id BIGSERIAL PRIMARY KEY,
    occurred_at TIMESTAMPTZ NOT NULL,
    severity TEXT NOT NULL,
    event_type TEXT NOT NULL,
    actor TEXT NOT NULL,
    message TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX idx_market_bars_ts ON market_bars(ts);
CREATE INDEX idx_audit_events_type_time ON audit_events(event_type, occurred_at DESC);

CREATE TABLE research_artifacts (
    artifact_id TEXT PRIMARY KEY,
    artifact_type TEXT NOT NULL,
    owner TEXT NOT NULL,
    manifest_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE model_registry (
    model_id TEXT PRIMARY KEY,
    family TEXT NOT NULL,
    owner TEXT NOT NULL,
    version TEXT NOT NULL,
    feature_names TEXT[] NOT NULL,
    metrics JSONB NOT NULL,
    approved BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE regime_states (
    state_id BIGSERIAL PRIMARY KEY,
    label TEXT NOT NULL,
    probability NUMERIC NOT NULL CHECK (probability >= 0 AND probability <= 1),
    volatility_score NUMERIC NOT NULL,
    liquidity_score NUMERIC NOT NULL,
    crisis_score NUMERIC NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE tca_reports (
    report_id BIGSERIAL PRIMARY KEY,
    client_order_id TEXT REFERENCES order_intents(client_order_id),
    average_fill_price NUMERIC NOT NULL,
    implementation_shortfall_bps NUMERIC NOT NULL,
    vwap_slippage_bps NUMERIC NOT NULL,
    twap_slippage_bps NUMERIC NOT NULL,
    market_impact_bps NUMERIC NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
