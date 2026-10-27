import time, logging, httpx, pandas as pd
from config import API_KEY, SYMBOLS, TF_API, TF_SECS
log = logging.getLogger("provider")
URL = "https://api.twelvedata.com/time_series"

class ProviderError(Exception): pass

class TwelveData:
    name = "Twelve Data"
    def candles(self, symbol: str, tf: str, n: int = 300) -> pd.DataFrame:
        if not API_KEY: raise ProviderError("TWELVEDATA_API_KEY not set")
        p = dict(symbol=SYMBOLS[symbol], interval=TF_API[tf], outputsize=n,
                 timezone="UTC", order="DESC", apikey=API_KEY)
        last = None
        for i in range(4):
            try:
                r = httpx.get(URL, params=p, timeout=15); d = r.json()
            except (httpx.HTTPError, ValueError) as e:
                last = str(e); time.sleep(2 ** i); continue
            if d.get("status") == "error":
                code = d.get("code")
                if code == 429:
                    log.warning("rate limited, backing off"); time.sleep(10 * (i + 1)); last = "429"; continue
                raise ProviderError(f"{code}: {d.get('message')}")
            return self._parse(d, tf)
        raise ProviderError(f"provider unreachable: {last}")

    def _parse(self, d, tf) -> pd.DataFrame:
        vals = d.get("values") or []
        if not vals: raise ProviderError("empty candle response")
        df = pd.DataFrame(vals)
        df["t"] = pd.to_datetime(df["datetime"], utc=True)
        for c in ("open", "high", "low", "close", "volume"):
            df[c] = pd.to_numeric(df.get(c), errors="coerce") if c in df else 0.0
        df = df.rename(columns={"open": "o", "high": "h", "low": "l", "close": "c", "volume": "v"})
        df = df[["t", "o", "h", "l", "c", "v"]].dropna(subset=["o", "h", "l", "c"])
        df = df.drop_duplicates("t").sort_values("t").reset_index(drop=True)
        if (df.h < df.l).any(): raise ProviderError("invalid OHLC data (high < low)")
        # drop unfinished candle: never treat a forming bar as confirmed
        close_t = df["t"] + pd.Timedelta(seconds=TF_SECS[tf])
        return df[close_t <= pd.Timestamp.now(tz="UTC")].reset_index(drop=True)
