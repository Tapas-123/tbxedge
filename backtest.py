import pandas as pd
from config import TF_SECS, HTF, get_cfg
from signals import build
W = 250

def metrics(tr):
    if not tr: return {"trades": 0}
    r = [t["r"] for t in tr]; w = [x for x in r if x > 0]; l = [x for x in r if x <= 0]
    eq = pd.Series(r).cumsum(); dd = (eq.cummax() - eq).max()
    return {"trades": len(r), "win_rate": round(len(w) / len(r) * 100, 1),
            "profit_factor": round(sum(w) / abs(sum(l)), 2) if l and sum(l) != 0 else None,
            "expectancy_R": round(sum(r) / len(r), 3), "max_drawdown_R": round(float(dd), 2),
            "avg_planned_RR": round(sum(t["plan_rr"] for t in tr) / len(tr), 2), "net_R": round(sum(r), 2)}

def run(sym, tf, df, hdf, spread, slip, comm, oos=0.3, target=1):
    cfg = get_cfg(sym, tf); hc = hdf.t + pd.Timedelta(seconds=TF_SECS[HTF[tf]])
    trades, theo, busy = [], 0, -1
    for i in range(W, len(df) - 1):
        t_close = df.t.iloc[i] + pd.Timedelta(seconds=TF_SECS[tf])
        idx = int(hc.searchsorted(t_close, side="right"))
        s = build(sym, tf, df.iloc[i - W + 1:i + 1], hdf.iloc[max(0, idx - 150):idx], backtest=True)
        if s["side"] == "NO TRADE": continue
        theo += 1
        if i <= busy: continue  # signal existed but no free capital/position: theoretical only
        sg = 1 if s["side"] == "BUY" else -1; cost = spread / 2 + slip
        entry = df.o.iloc[i + 1] + sg * cost        # next-bar open, never the signal bar
        sl, tp = s["stop_loss"], s["take_profit"][target]; risk = (entry - sl) * sg
        if risk <= 0 or (tp - entry) * sg <= 0: continue
        ex, why, j = None, "TIME", i + 1
        for j in range(i + 1, min(i + 1 + cfg["expiry_bars"], len(df))):
            b = df.iloc[j]
            if (b.l <= sl) if sg == 1 else (b.h >= sl): ex, why = sl, "SL"; break
            if (b.h >= tp) if sg == 1 else (b.l <= tp): ex, why = tp, "TP"; break
        if ex is None: ex = df.c.iloc[j]
        ex -= sg * cost
        r = (ex - entry) * sg / risk - comm * (entry + ex) / risk
        trades.append({"i": i, "time": df.t.iloc[i].isoformat(), "side": s["side"], "r": round(r, 3), "exit": why,
                       "plan_rr": cfg["rr"][target], "bars": j - i}); busy = j
    cut = W + int((1 - oos) * (len(df) - 1 - W))
    ins, out = [t for t in trades if t["i"] < cut], [t for t in trades if t["i"] >= cut]
    return {"bars_tested": len(df) - 1 - W, "theoretical_signals": theo, "executed_trades": len(trades),
            "in_sample": metrics(ins), "out_of_sample": metrics(out), "all": metrics(trades), "recent_trades": trades[-40:],
            "assumptions": f"Entry next-bar open; spread {spread}, slippage {slip}/side, commission {comm*100:.3f}%/side; SL checked before TP in the same bar; one position at a time; exit at TP{target+1}, SL or expiry. Parameters are NOT optimised on this data."}
