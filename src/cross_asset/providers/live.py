"""Opt-in live probes and public Yahoo/FRED fetches. Secrets never enter reports."""
import json
import os
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime

from .base import Observation


def _request(url, timeout=8, retries=2):
    started=time.perf_counter(); last=None
    for attempt in range(retries + 1):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "cross-asset-engine/0.1"})
            with urllib.request.urlopen(request, timeout=timeout) as response: payload=response.read()
            return json.loads(payload), round((time.perf_counter()-started)*1000,2)
        except Exception as exc:  # noqa: BLE001 - network stack has heterogeneous failures
            last=exc
            if attempt < retries: time.sleep(0.2 * (attempt + 1))
    raise last

def probe_yahoo(timeout=8):
    try:
        data,lat=_request("https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC?range=5d&interval=1d",timeout)
        result=data["chart"]["result"][0]; ts=result.get("timestamp") or []
        return {"provider":"yahoo","authenticated":True,"reachable":True,"historical_query":bool(ts),"latest_query":bool(ts),"latency_ms":lat,"earliest_date":datetime.fromtimestamp(ts[0],UTC).date().isoformat() if ts else None,"latest_date":datetime.fromtimestamp(ts[-1],UTC).date().isoformat() if ts else None,"quota_info_if_available":None,"error_type":None,"safe_error":None,"verified_at":datetime.now(UTC).isoformat()}
    except Exception as exc: return _error("yahoo",exc)  # noqa: BLE001

def probe_fred(api_key, timeout=8):
    if not api_key: return _error("fred",None,"MISSING_CREDENTIALS")
    try:
        q=urllib.parse.urlencode({"series_id":"DGS10","api_key":api_key,"file_type":"json","limit":5})
        data,lat=_request("https://api.stlouisfed.org/fred/series/observations?"+q,timeout); rows=data.get("observations",[])
        return {"provider":"fred","authenticated":True,"reachable":True,"historical_query":bool(rows),"latest_query":bool(rows),"latency_ms":lat,"earliest_date":rows[0].get("date") if rows else None,"latest_date":rows[-1].get("date") if rows else None,"quota_info_if_available":None,"error_type":None,"safe_error":None,"verified_at":datetime.now(UTC).isoformat()}
    except Exception as exc: return _error("fred",exc)  # noqa: BLE001

def _error(provider, exc, error_type=None):
    message = str(exc) if exc else "Credential required"
    # Do not allow URLs, query strings, or credential-shaped values into artifacts.
    message = message.split("?")[0].replace(os.getenv("FRED_API_KEY", "__never__"), "<redacted>")
    return {"provider":provider,"authenticated":False,"reachable":False,"historical_query":False,"latest_query":False,"latency_ms":None,"earliest_date":None,"latest_date":None,"quota_info_if_available":None,"error_type":error_type or type(exc).__name__,"safe_error":message[:240],"verified_at":datetime.now(UTC).isoformat()}

def yahoo_fetch(request, timeout=10):
    symbols={"US_EQ":"^GSPC","HK_EQ":"^HSI","GOLD":"GC=F","COPPER":"HG=F","OIL":"CL=F","DXY":"DX-Y.NYB","USDCNH":"CNH=X","US_GOV_10Y":"^TNX"}; out=[]
    # Prefer yfinance's supported public client; retain chart endpoint fallback.
    try:
        import yfinance as yf
    except ImportError:
        yf = None
    batch_frames = {}
    # Large multi-ticker yfinance calls can block indefinitely on constrained
    # networks; use bounded chart requests for the 8-series live gate.
    if yf is not None and len(request.series_ids) <= 3:
        try:
            symbols_requested = [symbols[s] for s in request.series_ids if symbols.get(s)]
            batch = yf.download(symbols_requested, period="10y", auto_adjust=False,
                                group_by="ticker", threads=False, progress=False, timeout=timeout)
            for symbol in symbols_requested:
                try:
                    batch_frames[symbol] = batch[symbol]
                except (KeyError, TypeError):
                    batch_frames[symbol] = batch
        except Exception:  # noqa: BLE001 - chart endpoint remains a legal fallback
            batch_frames = {}
    for sid in request.series_ids:
        symbol=symbols.get(sid)
        if not symbol: continue
        if yf is not None and symbol in batch_frames:
            try:
                frame = batch_frames[symbol]
                for index, value in frame["Close"].dropna().items():
                    dt = index.date() if hasattr(index, "date") else index
                    out.append(Observation(series_id=sid, observation_date=dt, available_at=datetime.now(UTC), value=float(value), source="yahoo", source_series_id=symbol, frequency="daily", unit="percent" if sid == "US_GOV_10Y" else "price"))
                if out and out[-1].series_id == sid:
                    continue
            except Exception:  # noqa: BLE001 - fallback to the supported chart endpoint
                yf = None
        q=urllib.parse.urlencode({"range":"10y","interval":"1d"}); data,_=_request("https://query1.finance.yahoo.com/v8/finance/chart/"+urllib.parse.quote(symbol,safe="")+"?"+q,timeout)
        result=data["chart"]["result"][0]; timestamps=result.get("timestamp",[]); closes=result["indicators"]["quote"][0].get("close",[])
        for stamp,value in zip(timestamps,closes):
            if value is not None: out.append(Observation(series_id=sid,observation_date=datetime.fromtimestamp(stamp,UTC).date(),available_at=datetime.now(UTC),value=float(value),source="yahoo",source_series_id=symbol,frequency="daily",unit="price"))
    return out
