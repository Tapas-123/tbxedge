import pandas as pd
from datetime import datetime, timezone, timedelta
from config import HTF, TF_SECS, get_cfg
from indicators import enrich, swings

def freshness(df, tf):
    age = (datetime.now(timezone.utc) - (df.t.iloc[-1] + pd.Timedelta(seconds=TF_SECS[tf]))).total_seconds()
    return age, age <= 2 * TF_SECS[tf] + 120  # last closed bar should be recent (weekend/closed market -> stale)

def htf_bias(h, adx_min):
    r = h.iloc[-1]
    if r.ema21 > r.ema50 and r.c > r.ema50 and r.adx >= adx_min: return "BULLISH"
    if r.ema21 < r.ema50 and r.c < r.ema50 and r.adx >= adx_min: return "BEARISH"
    return "NEUTRAL"

def levels(d, price, k=3):
    hs, ls = swings(d, k)
    res = hs[hs > price].tail(8); sup = ls[ls < price].tail(8)
    return (float(res.min()) if len(res) else None), (float(sup.max()) if len(sup) else None), hs, ls

def candle_ok(d, side):
    a, b = d.iloc[-1], d.iloc[-2]
    if side == "BUY": return a.c > a.o and (a.c > b.h or (a.c > b.o and a.o < b.c))
    return a.c < a.o and (a.c < b.l or (a.c < b.o and a.o > b.c))

def build(symbol, tf, df, hdf, backtest=False):
    cfg = get_cfg(symbol, tf)
    now = (df.t.iloc[-1] + pd.Timedelta(seconds=TF_SECS[tf])).to_pydatetime() if backtest else datetime.now(timezone.utc)
    age, fresh = (0, True) if backtest else freshness(df, tf)
    base = dict(instrument=symbol, timeframe=tf, strategy=cfg["name"], created_at=now.isoformat(),
                data_age_seconds=int(age), side="NO TRADE", reasons=[], htf=HTF[tf])
    if not fresh:
        return {**base, "warning": "Data stale/unavailable - signals disabled"}
    if len(df) < 120 or len(hdf) < 60:
        return {**base, "warning": "Not enough candles for indicators"}
    d, h = enrich(df), enrich(hdf)
    bias = htf_bias(h, cfg["adx_min"]); base["htf_trend"] = bias
    r = d.iloc[-1]; price = float(r.c); atr = float(r.atr)
    if bias == "NEUTRAL":
        return {**base, "reasons": ["Higher-timeframe bias is neutral/weak - no trade"]}
    side = "BUY" if bias == "BULLISH" else "SELL"; up = side == "BUY"
    res, sup, hs, ls = levels(d, price)
    # confidence = transparent weighted checklist
    chk = {
        "HTF bias aligned": (25, True),
        f"ADX >= {cfg['adx_min']}": (15, r.adx >= cfg["adx_min"]),
        "EMA 9/21/50 stacked": (15, (r.ema9 > r.ema21 > r.ema50) if up else (r.ema9 < r.ema21 < r.ema50)),
        "MACD histogram with trend": (15, (r.macd_hist > 0) if up else (r.macd_hist < 0)),
        "RSI in healthy zone": (10, (45 <= r.rsi <= 70) if up else (30 <= r.rsi <= 55)),
        "Candlestick confirmation": (10, candle_ok(d, side)),
        "Room to S/R >= 1R": (10, True),
    }
    swing = (float(ls.iloc[-1]) if len(ls) else None) if up else (float(hs.iloc[-1]) if len(hs) else None)
    if swing is None: return {**base, "reasons": ["No confirmed swing structure for stop placement"]}
    risk_atr = cfg["atr_sl"] * atr
    sl = min(swing - 0.25 * atr, price - risk_atr) if up else max(swing + 0.25 * atr, price + risk_atr)
    risk = abs(price - sl)
    if risk > 3.5 * atr: return {**base, "reasons": ["Structure stop too wide vs ATR - skipped"]}
    sign = 1 if up else -1
    tps = [price + sign * risk * m for m in cfg["rr"]]
    target = res if up else sup
    if target is not None and abs(target - price) < risk:
        chk["Room to S/R >= 1R"] = (10, False)
    score = sum(w for w, ok in chk.values() if ok)
    breakdown = [{"factor": k, "weight": w, "met": bool(ok)} for k, (w, ok) in chk.items()]
    ok_order = (sl < price < tps[0] < tps[1] < tps[2]) if up else (sl > price > tps[0] > tps[1] > tps[2])
    must = chk["EMA 9/21/50 stacked"][1] and chk["MACD histogram with trend"][1] and chk["Candlestick confirmation"][1]
    if not (ok_order and must and score >= cfg["min_conf"]):
        return {**base, "confidence": score, "breakdown": breakdown,
                "reasons": [f"Setup incomplete (score {score}/{cfg['min_conf']} needed; EMA, MACD and candle must all agree)"]}
    reasons = [k for k, (w, ok) in chk.items() if ok]
    return {**base, "side": side, "entry": round(price, 2), "stop_loss": round(sl, 2),
            "take_profit": [round(t, 2) for t in tps], "risk_reward": list(cfg["rr"]),
            "confidence": score, "breakdown": breakdown, "reasons": reasons,
            "nearest_resistance": res, "nearest_support": sup,
            "indicators": {k: round(float(r[k]), 4) for k in ("ema9", "ema21", "ema50", "rsi", "atr", "adx", "macd_hist")},
            "invalidation": [f"Candle closes beyond SL {round(sl,2)}", f"{HTF[tf]} bias flips from {bias}",
                             "Signal expires after " + str(cfg["expiry_bars"]) + f" {tf} bars"],
            "expires_at": (now + timedelta(seconds=cfg["expiry_bars"] * TF_SECS[tf])).isoformat()}
