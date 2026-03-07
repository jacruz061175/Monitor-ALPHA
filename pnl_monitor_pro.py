#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import time
import os
import csv
import math
import json
import hmac
import hashlib
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from collections import defaultdict, deque
from typing import Dict, List, Tuple, Optional
from colorama import init
from colorama import Fore, Style

import requests
import config


def print_box(lines, width=110, title_color="", reset=""):
    """
    Dibuja un marco estilo 'menu' con box-drawing.
    lines: lista de strings (ya formateados/coloreados si querés)
    width: ancho total del box
    """
    # recorto por si te pasás
    inner = width - 4  # "│ " + " │"
    top = "┌" + "─" * (width - 2) + "┐"
    bot = "└" + "─" * (width - 2) + "┘"
    print(top)
    for s in lines:
        s_plain = s  # (si usás colores, el padding visual puede variar, pero queda bien)
        if len(s_plain) > inner:
            s_plain = s_plain[:inner]
        pad = " " * max(0, inner - len(s_plain))
        print(f"│ {s_plain}{pad} │")
    print(bot)

# =========================
# CONFIG
# =========================
API_KEY = getattr(config, "API_KEY", "").strip()
API_SECRET = getattr(config, "API_SECRET", "").strip()

SYMBOLS = getattr(config, "PNL_SYMBOLS", [])
REFRESH_MINUTES = int(getattr(config, "PNL_REFRESH_MINUTES", 5))

BASE_URL = "https://api.binance.com"
QUOTE = "USDT"
STATE_JSON = "pnl_dashboard_state.json"

RENDER_UPDATE_URL = getattr(config, "RENDER_UPDATE_URL", "").strip()
RENDER_UPDATE_TOKEN = getattr(config, "RENDER_UPDATE_TOKEN", "").strip()
# tu zona horaria de trabajo (Chile/Argentina)
LOCAL_TZ = timezone(timedelta(hours=-3))

REPORT_DIR = "reports"
DAILY_SNAPSHOT = os.path.join(REPORT_DIR, "daily_pnl_snapshot.csv")
MONTHLY_SNAPSHOT = os.path.join(REPORT_DIR, "monthly_pnl_snapshot.csv")

session = requests.Session()
session.headers.update({"X-MBX-APIKEY": API_KEY})


# =========================
# BINANCE REST helpers
# =========================
def _sign(params: dict) -> str:
    qs = urllib.parse.urlencode(params, doseq=True)
    sig = hmac.new(API_SECRET.encode(), qs.encode(), hashlib.sha256).hexdigest()
    return qs + "&signature=" + sig


def _get(path: str, params: dict):
    url = BASE_URL + path
    qs = _sign(params)
    r = session.get(url + "?" + qs, timeout=30)
    if r.status_code != 200:
        print("ERROR STATUS:", r.status_code)
        print("ERROR BODY:", r.text)
    r.raise_for_status()
    return r.json()


def _get_public(path: str, params: dict) -> dict:
    url = BASE_URL + path
    r = session.get(url, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def fetch_my_trades(symbol: str, start_ms: int, end_ms: int) -> list:
    trades = []
    DAY = 24 * 60 * 60 * 1000

    current = start_ms
    while current < end_ms:
        chunk_end = min(current + DAY - 1, end_ms)

        from_id = None
        while True:
            params = {
                "symbol": symbol,
                "startTime": current,
                "endTime": chunk_end,
                "limit": 1000,
                "timestamp": int(time.time() * 1000),
                "recvWindow": 5000,
            }
            if from_id is not None:
                params["fromId"] = from_id

            data = _get("/api/v3/myTrades", params)
            if not data:
                break

            trades.extend(data)

            if len(data) < 1000:
                break

            from_id = int(data[-1]["id"]) + 1
            time.sleep(0.15)  # suave con rate limits

        current = chunk_end + 1

    return trades

_price_cache: Dict[str, Tuple[float, float]] = {}  # sym -> (price, ts)


def get_price(symbol: str) -> Optional[float]:
    """
    Precio actual ticker/price (cache 30s).
    """
    now = time.time()
    if symbol in _price_cache and (now - _price_cache[symbol][1]) < 30:
        return _price_cache[symbol][0]

    try:
        data = _get_public("/api/v3/ticker/price", {"symbol": symbol})
        p = float(data["price"])
        _price_cache[symbol] = (p, now)
        return p
    except Exception:
        return None


def fee_to_usdt(fee_asset: str, fee_amount: float) -> float:
    """
    Convierte fee_asset -> USDT usando precio actual.
    Si fee_asset ya es USDT, devuelve directo.
    Si no hay par directo, devuelve 0 y lo reportamos aparte.
    """
    fee_asset = (fee_asset or "").upper().strip()
    if fee_amount <= 0:
        return 0.0
    if fee_asset == QUOTE:
        return fee_amount

    # Intento directo: ASSETUSDT
    pair = f"{fee_asset}{QUOTE}"
    p = get_price(pair)
    if p is not None:
        return fee_amount * p

    # Intento inverso: USDTASSET (raro)
    inv = f"{QUOTE}{fee_asset}"
    p2 = get_price(inv)
    if p2 is not None and p2 > 0:
        return fee_amount / p2

    return 0.0


# =========================
# PnL FIFO (realizado)
# =========================
@dataclass
class Lot:
    qty: float
    price: float  # en USDT


@dataclass
class ClosedTrade:
    pnl: float  # en USDT
    fee_usdt: float


def compute_realized_fifo(trades: list) -> Tuple[float, float, List[ClosedTrade], Dict[str, float]]:
    """
    FIFO por símbolo:
    - BUY crea lotes (qty, price)
    - SELL consume lotes y crea trades cerrados con PnL realizado

    Fees:
    - convierte comisión a USDT si puede
    - fee sin conversión se acumula aparte

    Returns:
      realized_pnl_usdt, fee_usdt_total, closed_trades, fee_unconverted_by_asset
    """
    lots = deque()  # FIFO lots
    realized = 0.0
    fee_usdt_total = 0.0
    closed: List[ClosedTrade] = []
    fee_unconverted = defaultdict(float)

    # trades vienen con time ascendente normalmente, pero lo garantizamos
    trades_sorted = sorted(trades, key=lambda x: int(x["time"]))

    for t in trades_sorted:
        price = float(t["price"])
        qty = float(t["qty"])
        is_buy = bool(t["isBuyer"])

        comm = float(t.get("commission", 0.0))
        comm_asset = (t.get("commissionAsset") or "").upper().strip()

        # convertir fee
        fee_u = fee_to_usdt(comm_asset, comm)
        fee_usdt_total += fee_u
        if comm > 0 and fee_u == 0.0 and comm_asset and comm_asset != QUOTE:
            fee_unconverted[comm_asset] += comm

        if qty <= 0 or price <= 0:
            continue

        if is_buy:
            lots.append(Lot(qty=qty, price=price))
        else:
            # SELL: consumir FIFO
            remaining = qty
            sell_price = price
            trade_pnl = 0.0

            while remaining > 0 and lots:
                lot = lots[0]
                take = min(remaining, lot.qty)
                # pnl = (sell - buy) * qty
                trade_pnl += (sell_price - lot.price) * take

                lot.qty -= take
                remaining -= take

                if lot.qty <= 1e-12:
                    lots.popleft()

            # Si vendiste más de lo que hay en lotes (raro), ignoramos excedente
            realized += trade_pnl
            # le asignamos el fee (USDT) de este fill a ese trade cerrado (aprox)
            closed.append(ClosedTrade(pnl=trade_pnl, fee_usdt=fee_u))

    return realized, fee_usdt_total, closed, dict(fee_unconverted)


def stats_from_closed(closed: List[ClosedTrade]) -> Tuple[int, int, float, float]:
    """
    trades_closed, wins, profit_factor, avg_pnl
    """
    if not closed:
        return 0, 0, 0.0, 0.0

    wins = 0
    gross_profit = 0.0
    gross_loss = 0.0
    pnl_sum = 0.0

    for ct in closed:
        pnl_net = ct.pnl - ct.fee_usdt  # net por trade cerrado (aprox)
        pnl_sum += pnl_net
        if pnl_net > 0:
            wins += 1
            gross_profit += pnl_net
        else:
            gross_loss += abs(pnl_net)

    trades_closed = len(closed)
    profit_factor = (gross_profit / gross_loss) if gross_loss > 1e-12 else (999.0 if gross_profit > 0 else 0.0)
    avg_pnl = pnl_sum / trades_closed
    return trades_closed, wins, profit_factor, avg_pnl


# =========================
# Cashflow PnL (control rápido)
# =========================
def compute_cashflow(trades: list) -> Tuple[float, float, Dict[str, float]]:
    """
    BUY -> -quoteQty
    SELL -> +quoteQty
    fee en USDT se resta; fee en otros assets se intenta convertir.
    """
    net = 0.0
    fee_usdt_total = 0.0
    fee_unconverted = defaultdict(float)

    for t in trades:
        price = float(t["price"])
        qty = float(t["qty"])
        is_buy = bool(t["isBuyer"])
        quote_amt = price * qty

        net += (-quote_amt if is_buy else +quote_amt)

        comm = float(t.get("commission", 0.0))
        comm_asset = (t.get("commissionAsset") or "").upper().strip()
        fee_u = fee_to_usdt(comm_asset, comm)
        fee_usdt_total += fee_u
        if comm > 0 and fee_u == 0.0 and comm_asset and comm_asset != QUOTE:
            fee_unconverted[comm_asset] += comm

    net_after_fee = net - fee_usdt_total
    return net_after_fee, fee_usdt_total, dict(fee_unconverted)


# =========================
# Reporting persistence
# =========================
def ensure_reports():
    os.makedirs(REPORT_DIR, exist_ok=True)


def append_daily_snapshot(date_key: str, total_24h: float, total_7d: float, total_30d: float, fee_24h: float, trades_24h_closed: int):
    ensure_reports()
    new_file = not os.path.exists(DAILY_SNAPSHOT)
    with open(DAILY_SNAPSHOT, "a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["date", "quote", "pnl_24h", "pnl_7d", "pnl_30d", "fee_24h_usdt", "closed_trades_24h"])
        w.writerow([date_key, QUOTE, f"{total_24h:.8f}", f"{total_7d:.8f}", f"{total_30d:.8f}", f"{fee_24h:.8f}", trades_24h_closed])


def rebuild_monthly_snapshot():
    if not os.path.exists(DAILY_SNAPSHOT):
        return
    agg = defaultdict(lambda: {"pnl_24h": 0.0, "fee_24h": 0.0, "days": 0})
    with open(DAILY_SNAPSHOT, "r", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            date_s = row["date"]
            month = date_s[:7]
            agg[month]["pnl_24h"] += float(row["pnl_24h"])
            agg[month]["fee_24h"] += float(row["fee_24h_usdt"])
            agg[month]["days"] += 1

    ensure_reports()
    with open(MONTHLY_SNAPSHOT, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["month", "quote", "sum_pnl_24h", "sum_fee_24h_usdt", "days"])
        for m in sorted(agg.keys()):
            w.writerow([m, QUOTE, f"{agg[m]['pnl_24h']:.8f}", f"{agg[m]['fee_24h']:.8f}", agg[m]["days"]])


# =========================
# Terminal UI
# =========================
def clear():
    os.system("cls" if os.name == "nt" else "clear")


def pct(x: float) -> str:
    return f"{x*100:.1f}%"


def fmt(x: float) -> str:
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return "ERR"
    return f"{x: .6f}"


def fmt_fee_other(d: Dict[str, float]) -> str:
    if not d:
        return "-"
    parts = [f"{k}:{v:.6g}" for k, v in sorted(d.items())]
    s = " ".join(parts)
    return s[:70] + ("…" if len(s) > 70 else "")

# ===========================
# Balance estimado (en USDT)
# ===========================
_BAL_CACHE = None
_BAL_CACHE_TS = 0

def get_estimated_usdt_balance(quote: str = "USDT", max_age_s: float = 15.0) -> float:
    """Balance estimado en QUOTE sumando FREE+LOCKED y convirtiendo activos a QUOTE cuando existe par directo."""
    global _BAL_CACHE, _BAL_CACHE_TS
    now = time.time()
    if _BAL_CACHE is not None and (now - _BAL_CACHE_TS) <= max_age_s:
        return float(_BAL_CACHE)

    try:
        acc = _get("/api/v3/account", {"recvWindow": 5000, "timestamp": int(now * 1000)})
        bals = acc.get("balances", []) if isinstance(acc, dict) else []
    except Exception:
        _BAL_CACHE, _BAL_CACHE_TS = 0.0, now
        return 0.0

    total = 0.0
    for b in bals:
        asset = (b.get("asset") or "").upper()
        if not asset:
            continue
        try:
            free = float(b.get("free") or 0.0)
            locked = float(b.get("locked") or 0.0)
        except Exception:
            continue
        qty = free + locked
        if qty <= 0:
            continue

        if asset == quote.upper():
            total += qty
            continue

        # convertir a QUOTE si hay par directo ASSETQUOTE
        symbol = f"{asset}{quote.upper()}"
        try:
            px = _get_public("/api/v3/ticker/price", {"symbol": symbol})
            price = float(px.get("price"))
            total += qty * price
        except Exception:
            # si no hay par directo, lo ignoramos (no frenar el monitor)
            continue

    _BAL_CACHE, _BAL_CACHE_TS = float(total), now
    return float(total)



def ms_to_local_str(ms: Optional[int]) -> Optional[str]:
    if not ms:
        return None
    dt = datetime.fromtimestamp(ms / 1000, tz=LOCAL_TZ)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def last_trade_summary(trades: list) -> dict:
    """
    Devuelve un resumen simple de la última operación:
    COMPRA / VENTA, precio, cantidad, hora.
    """
    if not trades:
        return {
            "side": None,
            "price": None,
            "qty": None,
            "quote_qty": None,
            "time": None,
            "time_ms": None,
        }

    t = max(trades, key=lambda x: int(x["time"]))
    price = float(t["price"])
    qty = float(t["qty"])
    side = "COMPRA" if bool(t["isBuyer"]) else "VENTA"

    return {
        "side": side,
        "price": price,
        "qty": qty,
        "quote_qty": price * qty,
        "time": ms_to_local_str(int(t["time"])),
        "time_ms": int(t["time"]),
    }


def load_bot_state(symbol: str) -> dict:
    """
    Lee el archivo <SYMBOL>_bot_state.json si existe.
    """
    path = f"{symbol}_bot_state.json"
    if not os.path.exists(path):
        return {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def build_dashboard_payload(now_dt, balance_est_usdt, total_24h_real, total_7d_real, total_30d_real,
                            total_24h_fee, total_24h_closed, global_wr, global_pf, rows):
    """
    Arma el JSON completo para guardar localmente y enviar a Render.
    """
    bots = []

    for r in sorted(rows, key=lambda x: (1, 0) if "err" in x else (0, -x["net24"])):
        sym = r["sym"]
        bot_state = load_bot_state(sym)

        if "err" in r:
            bots.append({
                "symbol": sym,
                "status": "ERROR",
                "error": r["err"],
                "position": bot_state.get("position"),
                "ready": bot_state.get("ready"),
                "regime": bot_state.get("regime"),
                "last_trade": None,
            })
            continue

        wr = (r["wins"] / r["closed"]) if r["closed"] else 0.0

        bots.append({
            "symbol": sym,
            "status": "OK",
            "position": bot_state.get("position"),
            "ready": bot_state.get("ready"),
            "regime": bot_state.get("regime"),
            "pnl_24h": round(r["net24"], 6),
            "pnl_7d": round(r["net7"], 6),
            "pnl_30d": round(r["net30"], 6),
            "fee_24h": round(r["fee24"], 6),
            "closed_trades_24h": r["closed"],
            "win_rate_24h": round(wr, 4),
            "profit_factor_24h": round(r["pf"], 4),
            "avg_pnl_24h": round(r["avg"], 6),
            "cashflow_24h": round(r["cf24"], 6),
            "other_fees": r["fee_other"],
            "last_trade": r.get("last_trade"),
        })

    payload = {
        "timestamp": now_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "timestamp_epoch": int(now_dt.timestamp()),
        "quote": QUOTE,
        "balance_estimated": round(balance_est_usdt, 6),
        "summary": {
            "pnl_24h": round(total_24h_real, 6),
            "pnl_7d": round(total_7d_real, 6),
            "pnl_30d": round(total_30d_real, 6),
            "fees_24h": round(total_24h_fee, 6),
            "closed_trades_24h": total_24h_closed,
            "win_rate_24h": round(global_wr, 4),
            "profit_factor_24h": round(global_pf, 4),
        },
        "bots": bots
    }

    return payload


def save_dashboard_json(payload: dict):
    with open(STATE_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def send_to_render(payload: dict):
    """
    Envía el JSON a Render si RENDER_UPDATE_URL está definido.
    """
    if not RENDER_UPDATE_URL:
        return False, "RENDER_UPDATE_URL vacío"

    headers = {"Content-Type": "application/json"}
    if RENDER_UPDATE_TOKEN:
        headers["X-Monitor-Token"] = RENDER_UPDATE_TOKEN

    try:
        r = requests.post(RENDER_UPDATE_URL, json=payload, headers=headers, timeout=20)
        return r.ok, f"{r.status_code} {r.text[:150]}"
    except Exception as e:
        return False, str(e)


# =========================
# Main dashboard loop
# =========================
def window_ms(hours: int = 0, days: int = 0) -> int:
    return int((timedelta(hours=hours, days=days).total_seconds()) * 1000)


def slice_trades(trades: list, start_ms: int) -> list:
    return [t for t in trades if int(t["time"]) >= start_ms]


def main():
    if not API_KEY or not API_SECRET:
        print("Faltan API_KEY / API_SECRET en config.py")
        return
    if not SYMBOLS:
        print("Falta config.PNL_SYMBOLS (ej: ['ADAUSDT','BNBUSDT'])")
        return
    if not isinstance(SYMBOLS, list) or not all(isinstance(s, str) for s in SYMBOLS):
        print("config.PNL_SYMBOLS debe ser list[str]")
        return

    last_saved_date = None

    while True:
        now = datetime.now(tz=LOCAL_TZ)
        end_ms = int(now.timestamp() * 1000)

        start_30d = end_ms - window_ms(days=30)
        start_7d = end_ms - window_ms(days=7)
        start_24h = end_ms - window_ms(hours=24)

        total_24h_real = 0.0
        total_7d_real = 0.0
        total_30d_real = 0.0
        total_24h_fee = 0.0

        total_24h_closed = 0
        total_24h_wins = 0
        total_24h_pf_num = 0.0
        total_24h_pf_den = 0.0

        fee_other_all = defaultdict(float)

        rows = []

        for sym in SYMBOLS:
            try:
                all_trades_30d = fetch_my_trades(sym, start_30d, end_ms)

                t24 = slice_trades(all_trades_30d, start_24h)
                t7 = slice_trades(all_trades_30d, start_7d)
                t30 = all_trades_30d

                # Realized FIFO
                r24, fee24, closed24, fee_other24 = compute_realized_fifo(t24)
                r7, fee7, _, _ = compute_realized_fifo(t7)
                r30, fee30, _, _ = compute_realized_fifo(t30)

                # Net realized (restamos fee USDT convertida)
                net24 = r24 - fee24
                net7 = r7 - fee7
                net30 = r30 - fee30

                # Stats
                closed_n, wins, pf, avg_pnl = stats_from_closed(closed24)

                # Profit factor totals (sum wins / sum losses) agregado de forma aproximada:
                # recomputamos a partir de closed24 net
                gp = 0.0
                gl = 0.0
                for ct in closed24:
                    p = ct.pnl - ct.fee_usdt
                    if p > 0:
                        gp += p
                    else:
                        gl += abs(p)

                # Cashflow (control rápido)
                cf24, cf_fee24, cf_fee_other = compute_cashflow(t24)
                last_trade = last_trade_summary(all_trades_30d)

                # Acumular globales
                total_24h_real += net24
                total_7d_real += net7
                total_30d_real += net30
                total_24h_fee += fee24

                total_24h_closed += closed_n
                total_24h_wins += wins
                total_24h_pf_num += gp
                total_24h_pf_den += gl

                for a, v in fee_other24.items():
                    fee_other_all[a] += v

                rows.append({
                    "sym": sym,
                    "net24": net24,
                    "net7": net7,
                    "net30": net30,
                    "fee24": fee24,
                    "closed": closed_n,
                    "wins": wins,
                    "pf": pf,
                    "avg": avg_pnl,
                    "cf24": cf24,
                    "fee_other": fee_other24,
                    "last_trade": last_trade,
                })

            except Exception as e:
                rows.append({"sym": sym, "err": str(e)})

        # Global PF
        global_pf = (total_24h_pf_num / total_24h_pf_den) if total_24h_pf_den > 1e-12 else (999.0 if total_24h_pf_num > 0 else 0.0)
        global_wr = (total_24h_wins / total_24h_closed) if total_24h_closed > 0 else 0.0

        # UI
        clear()
        balance_est_usdt = get_estimated_usdt_balance(QUOTE)
        print("📊 RESUMEN PnL REAL")
        print(f"Balance Binance: {Fore.MAGENTA}{balance_est_usdt:.2f} {QUOTE}{Style.RESET_ALL}")
        print(Fore.MAGENTA + f"PnL 24h: {total_24h_real:.6f} {QUOTE} | 7d: {total_7d_real:.6f} {QUOTE} | 30d: {total_30d_real:.6f} {QUOTE}" + Style.RESET_ALL)
        print(f"  24h closed trades: {total_24h_closed} | win rate: {global_wr*100: .1f}% | profit factor: {global_pf: .2f} | fees 24h: {total_24h_fee: .6f} {QUOTE}")
        if fee_other_all:
            print("  Fees no convertidas (sin par directo): " + fmt_fee_other(dict(fee_other_all)))
    
        table_header = (
            f"{'SYMBOL':10s} {'PnL24h':>12s} {'PnL7d':>12s} {'PnL30d':>12s} "
            f"{'FEE24h':>12s} {'CL':>4s} {'WR':>6s} {'PF':>6s} "
            f"{'AVG':>10s} {'CF24h':>12s} OTHER_FEES"
        )
                # ===== Tabla PRO =====

        COLS = [
            ("SYMBOL", 10, "<"),
            ("PnL24h", 12, ">"),
            ("PnL7d", 12, ">"),
            ("PnL30d", 12, ">"),
            ("FEE24h", 12, ">"),
            ("CL", 4, ">"),
            ("WR", 6, ">"),
            ("PF", 6, ">"),
            ("AVG", 10, ">"),
            ("CF24h", 12, ">"),
            ("OTHER_FEES", 12, "<"),
        ]

        def fmt_cell(val, w, align):
            s = str(val)
            if len(s) > w:
                s = s[:w]
            return f"{s:{align}{w}}"

        def make_row(values):
            cells = []
            for (name, w, align), v in zip(COLS, values):
                cells.append(fmt_cell(v, w, align))
            return "│ " + " │ ".join(cells) + " │"

        inner_w = len(make_row([""] * len(COLS))) - 2

        TOP = "┌" + "─" * inner_w + "┐"
        MID = "├" + "─" * inner_w + "┤"
        BOT = "└" + "─" * inner_w + "┘"

        print(TOP)
        print(make_row([c[0] for c in COLS]))
        print(MID)

        def key_row(r):
            if "err" in r:
                return (1, 0)
            return (0, -r["net24"])


        for r in sorted(rows, key=key_row):

            if "err" in r:
                vals = [r["sym"], "ERR", "", "", "", "", "", "", "", "", r["err"]]
                print(make_row(vals))
                continue

            wr = (r["wins"] / r["closed"] * 100) if r["closed"] else 0

            vals = [
                r["sym"],
                f"{r['net24']:.6f}",
                f"{r['net7']:.6f}",
                f"{r['net30']:.6f}",
                f"{r['fee24']:.6f}",
                str(r["closed"]),
                f"{wr:.1f}%",
                f"{r['pf']:.2f}",
                f"{r['avg']:.6f}",
                f"{r['cf24']:.6f}",
                fmt_fee_other(r["fee_other"])
            ]

            print(make_row(vals))

        print(BOT)

        payload = build_dashboard_payload(
            now_dt=now,
            balance_est_usdt=balance_est_usdt,
            total_24h_real=total_24h_real,
            total_7d_real=total_7d_real,
            total_30d_real=total_30d_real,
            total_24h_fee=total_24h_fee,
            total_24h_closed=total_24h_closed,
            global_wr=global_wr,
            global_pf=global_pf,
            rows=rows,
        )

        save_dashboard_json(payload)
        ok_send, send_msg = send_to_render(payload)

        print(f"[json] {STATE_JSON}")
        if RENDER_UPDATE_URL:
            print(f"[render] {'OK' if ok_send else 'ERROR'} -> {send_msg}")
        else:
            print("[render] RENDER_UPDATE_URL no configurado, solo guardado local")

        # Persistencia (1 vez por día)
        date_key = now.strftime("%Y-%m-%d")
        if last_saved_date != date_key:
            append_daily_snapshot(date_key, total_24h_real, total_7d_real, total_30d_real, total_24h_fee, total_24h_closed)
            rebuild_monthly_snapshot()
            last_saved_date = date_key
            print(f"[saved] {DAILY_SNAPSHOT} | [monthly] {MONTHLY_SNAPSHOT}")

        # Sleep
        time.sleep(max(60, REFRESH_MINUTES * 60))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nMonitor detenido por usuario.")
