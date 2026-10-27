import os
from dotenv import load_dotenv
load_dotenv()
API_KEY = os.getenv("TWELVEDATA_API_KEY", "")
DB_PATH = os.getenv("DB_PATH", "tbx_edge.db")
SYMBOLS = {"BTCUSD": "BTC/USD", "XAUUSD": "XAU/USD"}
TF_SECS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400}
TF_API = {"1m": "1min", "5m": "5min", "15m": "15min", "1h": "1h", "4h": "4h"}
HTF = {"1m": "15m", "5m": "1h", "15m": "1h", "1h": "4h", "4h": "4h"}
# One configurable strategy per timeframe (override per instrument via INSTRUMENT_OVERRIDES)
STRATEGY = {
    "1m":  dict(name="Scalping",  atr_sl=1.0, rr=(1.0, 1.5, 2.0), min_conf=70, adx_min=20, expiry_bars=10),
    "5m":  dict(name="Scalping",  atr_sl=1.2, rr=(1.0, 1.5, 2.5), min_conf=65, adx_min=20, expiry_bars=12),
    "15m": dict(name="Intraday",  atr_sl=1.3, rr=(1.0, 2.0, 3.0), min_conf=60, adx_min=20, expiry_bars=12),
    "1h":  dict(name="Intraday",  atr_sl=1.5, rr=(1.0, 2.0, 3.0), min_conf=60, adx_min=22, expiry_bars=10),
    "4h":  dict(name="Swing",     atr_sl=1.8, rr=(1.5, 2.5, 4.0), min_conf=60, adx_min=22, expiry_bars=8),
}
INSTRUMENT_OVERRIDES = {"BTCUSD": {}, "XAUUSD": {}}
CACHE_TTL = 30  # seconds; protects free-plan credit limits

import json, pathlib
SETTINGS_FILE = pathlib.Path("settings.json")
LIMITS = {"atr_sl": (0.3, 5), "min_conf": (0, 100), "adx_min": (0, 60), "expiry_bars": (1, 100)}
COSTS = {"BTCUSD": dict(spread=10.0, slip=5.0, comm=0.0002), "XAUUSD": dict(spread=0.30, slip=0.10, comm=0.0)}
def _load():
    try: return json.loads(SETTINGS_FILE.read_text())
    except Exception: return {}
def get_cfg(sym, tf):
    return {**STRATEGY[tf], **_load().get(sym, {}).get(tf, {})}
def set_cfg(sym, tf, v):
    out = {}
    for k, (lo, hi) in LIMITS.items():
        if k in v:
            x = float(v[k])
            if not lo <= x <= hi: raise ValueError(f"{k} must be {lo}-{hi}")
            out[k] = int(x) if k != "atr_sl" else x
    if "rr" in v:
        rr = [float(x) for x in v["rr"]]
        if len(rr) != 3 or not (0 < rr[0] < rr[1] < rr[2] <= 10): raise ValueError("rr must be 3 ascending values (0-10]")
        out["rr"] = rr
    d = _load(); d.setdefault(sym, {}).setdefault(tf, {}).update(out); SETTINGS_FILE.write_text(json.dumps(d, indent=1))
    return get_cfg(sym, tf)
