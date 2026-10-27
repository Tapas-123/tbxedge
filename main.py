import time, asyncio, logging, math, os, base64, secrets
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from fastapi import Request
from config import SYMBOLS, TF_SECS, CACHE_TTL, HTF, API_KEY, get_cfg, set_cfg, COSTS
from provider import TwelveData, ProviderError
import store, signals, backtest
logging.basicConfig(level=logging.INFO)
app = FastAPI(title="TBX EDGE AI"); prov = TwelveData(); _cache = {}
PW = os.getenv("APP_PASSWORD", "")
def _ok(h):
    try: return secrets.compare_digest(base64.b64decode(h.split(" ", 1)[1]).decode().split(":", 1)[1], PW)
    except Exception: return False
@app.middleware("http")
async def auth(req: Request, nxt):
    if PW and not _ok(req.headers.get("authorization", "")):
        return Response("Login required", 401, headers={"WWW-Authenticate": 'Basic realm="TBX EDGE"'})
    return await nxt(req)

def get_df(sym, tf):
    k = (sym, tf)
    if k in _cache and time.time() - _cache[k][0] < CACHE_TTL: return _cache[k][1]
    df = prov.candles(sym, tf); store.save(sym, tf, df); _cache[k] = (time.time(), df); return df

def chk(sym, tf):
    if sym not in SYMBOLS or tf not in TF_SECS: raise HTTPException(404, "unknown symbol/timeframe")

def candles_payload(sym, tf):
    chk(sym, tf)
    try: df = get_df(sym, tf)
    except ProviderError as e: raise HTTPException(502, str(e))
    age, fresh = signals.freshness(df, tf)
    return {"provider": prov.name, "last_closed_candle": df.t.iloc[-1].isoformat(), "age_seconds": int(age), "stale": not fresh,
            "candles": [{"time": int(r.t.timestamp()), "open": r.o, "high": r.h, "low": r.l, "close": r.c} for r in df.tail(300).itertuples()]}

def signal_payload(sym, tf):
    chk(sym, tf)
    try:
        df = get_df(sym, tf); s = signals.build(sym, tf, df, get_df(sym, HTF[tf]))
    except ProviderError as e: raise HTTPException(502, str(e))
    if s["side"] != "NO TRADE": store.log_signal(f"{sym}|{tf}|{df.t.iloc[-1].isoformat()}", sym, tf, s)
    return s

@app.get("/api/health")
def health():
    return {"provider": prov.name, "api_key_configured": bool(API_KEY), "read_only": True}
@app.get("/api/candles/{sym}/{tf}")
def candles(sym: str, tf: str): return candles_payload(sym, tf)
@app.get("/api/signal/{sym}/{tf}")
def signal(sym: str, tf: str): return signal_payload(sym, tf)
@app.get("/api/history")
def history(): return store.history()

@app.get("/api/settings/{sym}/{tf}")
def settings(sym: str, tf: str):
    chk(sym, tf); return {**get_cfg(sym, tf), "costs": COSTS[sym]}
@app.put("/api/settings/{sym}/{tf}")
def save_settings(sym: str, tf: str, body: dict):
    chk(sym, tf)
    try: return set_cfg(sym, tf, body)
    except (ValueError, TypeError) as e: raise HTTPException(400, str(e))

@app.get("/api/backtest/{sym}/{tf}")
def run_bt(sym: str, tf: str, spread: float = None, slip: float = None, comm: float = None, oos: float = 0.3, target: int = 1, bars: int = 2500):
    chk(sym, tf); c = COSTS[sym]; bars = min(max(bars, 500), 4000)
    try:
        nh = min(5000, math.ceil(bars * TF_SECS[tf] / TF_SECS[HTF[tf]]) + 220)
        df, hdf = prov.candles(sym, tf, bars), prov.candles(sym, HTF[tf], nh)
    except ProviderError as e: raise HTTPException(502, str(e))
    store.save(sym, tf, df)
    return backtest.run(sym, tf, df, hdf, c["spread"] if spread is None else spread, c["slip"] if slip is None else slip,
                        c["comm"] if comm is None else comm, min(max(oos, 0.1), 0.5), min(max(target, 0), 2))

@app.websocket("/ws/{sym}/{tf}")
async def ws(w: WebSocket, sym: str, tf: str):
    if PW and not _ok(w.headers.get("authorization", "")):
        await w.close(code=1008); return
    await w.accept()
    try:
        while True:
            try: data = await asyncio.to_thread(lambda: {"candles": candles_payload(sym, tf), "signal": signal_payload(sym, tf)})
            except HTTPException as e: data = {"error": e.detail}
            await w.send_json(data); await asyncio.sleep(20)
    except (WebSocketDisconnect, RuntimeError): pass

@app.get("/")
def index(): return FileResponse("index.html")
