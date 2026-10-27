import numpy as np, pandas as pd
def ema(s, n): return s.ewm(span=n, adjust=False).mean()
def rsi(c, n=14):
    d = c.diff(); up = d.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))
def atr(df, n=14):
    pc = df.c.shift()
    tr = pd.concat([df.h - df.l, (df.h - pc).abs(), (df.l - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1/n, adjust=False).mean()
def adx(df, n=14):
    up, dn = df.h.diff(), -df.l.diff()
    pdm = up.where((up > dn) & (up > 0), 0.0); mdm = dn.where((dn > up) & (dn > 0), 0.0)
    a = atr(df, n)
    pdi = 100 * pdm.ewm(alpha=1/n, adjust=False).mean() / a
    mdi = 100 * mdm.ewm(alpha=1/n, adjust=False).mean() / a
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return dx.ewm(alpha=1/n, adjust=False).mean()
def macd(c, f=12, s=26, sg=9):
    m = ema(c, f) - ema(c, s); sig = ema(m, sg); return m, sig, m - sig
def vwap(df):
    if df.v.sum() <= 0: return None  # forex/gold feeds often lack volume -> unsupported
    day = df.t.dt.date; tp = (df.h + df.l + df.c) / 3
    return (tp * df.v).groupby(day).cumsum() / df.v.groupby(day).cumsum()
def swings(df, k=3):
    """Fractal swings, confirmed only k bars later (no look-ahead / no repaint)."""
    hi = df.h == df.h.rolling(2*k+1, center=True).max()
    lo = df.l == df.l.rolling(2*k+1, center=True).min()
    hi.iloc[-k:] = False; lo.iloc[-k:] = False
    return df.h[hi], df.l[lo]
def enrich(df):
    d = df.copy()
    d["ema9"], d["ema21"], d["ema50"] = ema(d.c, 9), ema(d.c, 21), ema(d.c, 50)
    d["rsi"], d["atr"], d["adx"] = rsi(d.c), atr(d), adx(d)
    d["macd"], d["macd_sig"], d["macd_hist"] = macd(d.c)
    vw = vwap(d); d["vwap"] = vw if vw is not None else np.nan
    return d
