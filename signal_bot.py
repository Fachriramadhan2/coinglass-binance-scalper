import os, json, urllib.request, urllib.parse
from datetime import datetime, timezone

BASE = "https://fapi.binance.com"
TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

def api(path, params=None):
    url = BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "futures-alert"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())

def ema(values, period):
    alpha = 2 / (period + 1)
    out = values[0]
    for x in values[1:]:
        out = alpha * x + (1 - alpha) * out
    return out

def klines(symbol, interval):
    return api("/fapi/v1/klines", {"symbol": symbol, "interval": interval, "limit": 60})

def send(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": text}).encode()
    req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req, timeout=15) as r:
        r.read()

def main():
    btc = klines("BTCUSDT", "15m")
    btc_close = [float(k[4]) for k in btc[:-1]]
    btc_side = "LONG" if ema(btc_close[-50:], 9) > ema(btc_close[-50:], 21) else "SHORT"

    tickers = api("/fapi/v1/ticker/24hr")
    liquid = [t for t in tickers if t["symbol"].endswith("USDT")
              and not any(q in t["symbol"] for q in ("USDC","BUSD","FDUSD","TUSD"))
              and float(t["quoteVolume"]) >= 20000000]
    liquid.sort(key=lambda t: float(t["quoteVolume"]), reverse=True)

    signals = []
    for t in liquid[:25]:
        symbol = t["symbol"]
        try:
            a, b = klines(symbol, "15m"), klines(symbol, "5m")
            c15 = [float(k[4]) for k in a[:-1]]
            c5 = [float(k[4]) for k in b[:-1]]
            h5 = [float(k[2]) for k in b[:-1]]
            l5 = [float(k[3]) for k in b[:-1]]
            v5 = [float(k[5]) for k in b[:-1]]
            side = "LONG" if ema(c15[-50:], 9) > ema(c15[-50:], 21) else "SHORT"
            if side != btc_side:
                continue
            avgv = sum(v5[-21:-1]) / 20
            broke = c5[-1] > max(h5[-21:-1]) if side == "LONG" else c5[-1] < min(l5[-21:-1])
            if not broke or v5[-1] <= 1.5 * avgv:
                continue
            entry = c5[-1]
            swing = min(l5[-6:]) if side == "LONG" else max(h5[-6:])
            risk = abs(entry - swing)
            if risk <= 0 or risk / entry > 0.015:
                continue
            tp1 = entry + (2*risk if side == "LONG" else -2*risk)
            tp2 = entry + (3*risk if side == "LONG" else -3*risk)
            signals.append((symbol, side, entry, swing, tp1, tp2, float(t["quoteVolume"])))
        except Exception:
            continue

    if not signals:
        print("NO ENTRY: no confirmed candidate.")
        return
    signals.sort(key=lambda x: x[6], reverse=True)
    msg = ["BINANCE USDT-M FUTURES ALERT (bukan auto-trading)",
           f"BTC filter: {btc_side}",
           f"UTC: {datetime.now(timezone.utc):%Y-%m-%d %H:%M}", ""]
    for s, side, entry, sl, tp1, tp2, _ in signals[:2]:
        msg += [f"{s} — {side}", f"Entry: {entry:.8g}", f"SL: {sl:.8g}",
                f"TP1 (2R): {tp1:.8g}", f"TP2 (3R): {tp2:.8g}",
                "Syarat: EMA 15m searah BTC + breakout 5m + volume > 1.5x", ""]
    send("\n".join(msg))

if __name__ == "__main__":
    main()
