import sqlite3, pandas as pd
from config import DB_PATH
def _c():
    c = sqlite3.connect(DB_PATH)
    c.execute("""CREATE TABLE IF NOT EXISTS candles(sym TEXT, tf TEXT, t TEXT, o REAL, h REAL, l REAL, c REAL, v REAL,
                 PRIMARY KEY(sym, tf, t))""")
    return c
def save(sym, tf, df):
    with _c() as c:
        c.executemany("INSERT OR REPLACE INTO candles VALUES(?,?,?,?,?,?,?,?)",
            [(sym, tf, r.t.isoformat(), r.o, r.h, r.l, r.c, r.v) for r in df.itertuples()])
def load(sym, tf):
    with _c() as c:
        return pd.read_sql("SELECT * FROM candles WHERE sym=? AND tf=? ORDER BY t", c, params=(sym, tf), parse_dates=["t"])

import json
def _init():
    with _c() as c:
        c.execute("CREATE TABLE IF NOT EXISTS signals(key TEXT PRIMARY KEY, sym TEXT, tf TEXT, created TEXT, payload TEXT, outcome TEXT)")
_init()
def log_signal(key, sym, tf, s):
    with _c() as c:
        c.execute("INSERT OR IGNORE INTO signals VALUES(?,?,?,?,?,NULL)", (key, sym, tf, s["created_at"], json.dumps(s)))
def _outcome(s, df):
    up = s["side"] == "BUY"; k = 0; exp = pd.Timestamp(s["expires_at"])
    for r in df[df.t >= pd.Timestamp(s["created_at"])].itertuples():
        if (r.l <= s["stop_loss"]) if up else (r.h >= s["stop_loss"]):  # SL first if same bar (conservative)
            return f"TP{k}->SL" if k else "SL"
        for n, tp in enumerate(s["take_profit"], 1):
            if (r.h >= tp) if up else (r.l <= tp): k = max(k, n)
        if k == 3: return "TP3"
        if r.t >= exp: return f"TP{k} (expired)" if k else "EXPIRED"
    return None
def history(limit=100):
    with _c() as c:
        pend = c.execute("SELECT key,sym,tf,payload FROM signals WHERE outcome IS NULL").fetchall()
        for key, sym, tf, p in pend:
            o = _outcome(json.loads(p), load(sym, tf))
            if o: c.execute("UPDATE signals SET outcome=? WHERE key=?", (o, key))
        rows = c.execute("SELECT sym,tf,created,payload,outcome FROM signals ORDER BY created DESC LIMIT ?", (limit,)).fetchall()
    return [{"sym": a, "tf": b, "created": cr, **{k: json.loads(p).get(k) for k in ("side", "entry", "stop_loss", "take_profit", "confidence", "strategy")},
             "outcome": o or "PENDING"} for a, b, cr, p, o in rows]
