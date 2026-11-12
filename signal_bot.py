import os, json, urllib.request, urllib.parse
from datetime import datetime, timezone

BASE = "https://api.bybit.com"
TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

def api(path, params=None):
    url = BASE + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={"User-Agent": "futures-signal-alert/1.0"})
    with urllib.request.urlopen(req, timeout=20) as response:
        payload = json.loads(response.read().decode())
    if payload.get("retCode") != 0:
        raise RuntimeError(f"Bybit API error: {payload.get('retMsg', 'unknown')}")
    return payload["result"]

def ema(values, period):
    alpha = 2 / (period + 1)
    result = values[0]
    for value in values[1:]:
        result = alpha * value + (1 - alpha) * result
    return result

def klines(symbol, interval):
    result = api("/v5/market/kline", {"category":"linear","symbol":symbol,"interval":interval,"limit":60})
    return list(reversed(result["list"]))

def send(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = urllib.parse.urlencode({"chat_id":CHAT_ID,"text":message}).encode()
    req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req, timeout=20) as response:
        response.read()

def main():
    try:
        btc = klines("BTCUSDT", "15")
        btc_close = [float(c[4]) for c in btc[:-1]]
        if len(btc_close) < 50:
            raise RuntimeError("BTC candle data incomplete")
        btc_side = "LONG" if ema(btc_close[-50:],9) > ema(btc_close[-50:],21) else "SHORT"

        tickers = api("/v5/market/tickers", {"category":"linear"})["list"]
        liquid = [t for t in tickers if t["symbol"].endswith("USDT")
                  and "USDC" not in t["symbol"] and float(t.get("turnover24h",0)) >= 20000000]
        liquid.sort(key=lambda t: float(t.get("turnover24h",0)), reverse=True)

        signals = []
        for ticker in liquid[:25]:
            symbol = ticker["symbol"]
            try:
                a, b = klines(symbol,"15"), klines(symbol,"5")
                c15 = [float(c[4]) for c in a[:-1]]
                c5 = [float(c[4]) for c in b[:-1]]
                h5 = [float(c[2]) for c in b[:-1]]
                l5 = [float(c[3]) for c in b[:-1]]
                v5 = [float(c[5]) for c in b[:-1]]
                if min(len(c15),len(c5),len(h5),len(l5),len(v5)) < 22:
                    continue
                side = "LONG" if ema(c15[-50:],9) > ema(c15[-50:],21) else "SHORT"
                if side != btc_side:
                    continue
                avg_volume = sum(v5[-21:-1]) / 20
                breakout = c5[-1] > max(h5[-21:-1]) if side == "LONG" else c5[-1] < min(l5[-21:-1])
                if not breakout or v5[-1] <= 1.5 * avg_volume:
                    continue
                entry = c5[-1]
                stop = min(l5[-6:]) if side == "LONG" else max(h5[-6:])
                risk = abs(entry-stop)
                if risk <= 0 or risk/entry > 0.015:
                    continue
                tp1 = entry + (2*risk if side == "LONG" else -2*risk)
                tp2 = entry + (3*risk if side == "LONG" else -3*risk)
                signals.append((symbol,side,entry,stop,tp1,tp2,float(ticker.get("turnover24h",0))))
            except Exception as error:
                print(f"Skip {symbol}: {error}")

        if not signals:
            print("NO ENTRY: no confirmed candidate.")
            return
        signals.sort(key=lambda x:x[6], reverse=True)
        message = [
            "FUTURES SCALPING ALERT — DATA BYBIT LINEAR",
            "PENTING: harga/level dari Bybit, BUKAN Binance. Cocokkan harga dan pastikan kontrak tersedia di Binance sebelum entry.",
            f"BTC filter: {btc_side}",
            f"UTC: {datetime.now(timezone.utc):%Y-%m-%d %H:%M}", ""
        ]
        for symbol,side,entry,stop,tp1,tp2,_ in signals[:2]:
            message += [f"{symbol} — {side}",f"Entry acuan: {entry:.8g}",f"SL acuan: {stop:.8g}",
                        f"TP1 (2R): {tp1:.8g}",f"TP2 (3R): {tp2:.8g}",
                        "Filter: EMA 9/21 15m searah BTC + breakout 5m + volume > 1.5x",""]
        send("\n".join(message))
    except Exception as error:
        print(f"SCANNER ERROR: {error}")
        try:
            send(f"SCANNER ERROR — data market tidak berhasil diambil.\nDetail: {error}")
        except Exception as telegram_error:
            print(f"Telegram error: {telegram_error}")
        raise

if __name__ == "__main__":
    main()
