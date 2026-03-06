import config
from binance.client import Client
from binance.enums import *
import time
import json
import os
import math
#from colorama import init
from colorama import init, Fore, Style

init(autoreset=True)

# ==============================
# CONFIGURACION (solo tocá esto)
# ==============================
SIMBOLO = "BTCUSDT"         # ej: "BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT"
SIMBOLO_BALANCE = "BTC"    # ej: "BTC", "ETH", "BNB", "ADA"

#USDT_POR_TRADE = 10.0       # USDT aprox a invertir en la compra

# ------------------------------
# Modo autofinanciable (compounding en QUOTE)
# - El bot mantiene un "capital del bot" en la moneda QUOTE (ej: USDT).
# - Arranca en BOT_CAPITAL_START (20 por defecto).
# - Cada vez que cierra un trade (TP o SL) actualiza ese capital con el PnL.
# - El próximo trade usa BOT_USE_PCT * ese capital (y respeta el balance real disponible).
# ------------------------------
BOT_STATE_FILE = f"{SIMBOLO}_bot_state.json"
# Capital inicial por símbolo (en QUOTE, ej USDT).
# Regla pedida: ADA/BNB/ETH = 10 USDT, BTC = 20 USDT.
CAP_INICIAL_POR_BASE = {
    "ADA": 12.0,
    "BNB": 12.0,
    "ETH": 12.0,
    "BTC": 22.0,
}

# Colores por símbolo (default WHITE)
SYMBOL_COLORS = {
    "ADAUSDT": Fore.MAGENTA,
    "BNBUSDT": Fore.CYAN,
    "ETHUSDT": Fore.GREEN,
    "BTCUSDT": Fore.YELLOW,
}
# Colores por símbolo (marco)
SYMBOL_BORDER_COLOR = {
    "BTCUSDT": Fore.YELLOW,
    "ETHUSDT": Fore.GREEN,
    "ADAUSDT": Fore.MAGENTA,
    "BNBUSDT": Fore.CYAN,
}

def border_color(sym: str) -> str:
    return SYMBOL_BORDER_COLOR.get(sym, Fore.WHITE)

def _fmt(x, n=2):
    try:
        return f"{float(x):,.{n}f}"
    except Exception:
        return "—"

def _yn(v) -> str:
    return "✓" if bool(v) else "✗"

def _pad(s: str, width: int) -> str:
    # recorta y rellena exacto
    s = s[:width]
    return s + (" " * (width - len(s)))

def _center(s: str, width: int) -> str:
    if len(s) >= width:
        return s[:width]
    left = (width - len(s)) // 2
    right = width - len(s) - left
    return (" " * left) + s + (" " * right)

import re

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

def _vlen(s: str) -> int:
    return len(_ANSI_RE.sub("", s))

def _vpad(s: str, width: int) -> str:
    pad = max(0, width - _vlen(s))
    return s + (" " * pad)

def _vcenter(s: str, width: int) -> str:
    vis = _vlen(s)
    if vis >= width:
        return _vtrunc(s, width)
    left = (width - vis) // 2
    right = width - vis - left
    return (" " * left) + s + (" " * right)

def _vtrunc(s: str, width: int) -> str:
    if _vlen(s) <= width:
        return s

    out = []
    vis = 0
    i = 0
    while i < len(s) and vis < width:
        if s[i] == "\x1b":
            m = _ANSI_RE.match(s, i)
            if m:
                out.append(m.group(0))
                i = m.end()
                continue
        out.append(s[i])
        vis += 1
        i += 1

    out.append(Style.RESET_ALL)
    return "".join(out)

def _strip_ansi(s: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", s)


def print_panel(
    simbol: str,
    price_5m: float,
    rsi_5m: float,
    ma1h: float,
    cond_price_above_ma20: bool,
    cond_rsi: bool,
    cond_macro: bool,
    buy_signal: bool,
    extra_lines: list[str] | None = None,
):
    """Panel estilo 'menu' para cada símbolo (sin desfasajes)."""

    status_txt = "BUY" if buy_signal else "BLOC"
    status_col = (Fore.GREEN if buy_signal else Fore.MAGENTA) + status_txt + Style.RESET_ALL

    title = f"● {Fore.CYAN}{simbol}{Style.RESET_ALL} | MICRO-ALPHA ENGINE | {status_col}"

    ok = lambda x: "✓" if x else "×"

    # columnas
    yn = lambda x: "✓" if x else "✗"
    status_line = f"READY: {yn(buy_signal)}"

    # ancho interno (3 columnas)
    col_w = 24
    sep = " │ "
    inner_table = col_w * 3 + len(sep) * 2

    # extra lines (ej: balance)
    extras = extra_lines or []
    max_extra = 0
    for e in extras:
        max_extra = max(max_extra, len(_strip_ansi(e)))

    inner = max(inner_table, len(_strip_ansi(title)), max_extra) + 2  # padding lateral

    # helpers box
    def top_line():
        return "┌" + "─" * inner + "┐"

    def mid_line():
        return "├" + "─" * inner + "┤"

    def bot_line():
        return "└" + "─" * inner + "┘"

    def put(line: str):
        plain = _strip_ansi(line)
        if len(plain) > inner - 2:
            # recorte suave
            keep = inner - 5
            line = line[:keep] + "..."
            plain = _strip_ansi(line)
        pad = " " * max(0, (inner - 2) - len(plain))
        print(f"│ {line}{pad} │")

    cbox = border_color(SIMBOLO)
    # Render
    print(cbox + top_line() + Style.RESET_ALL)
    put(title)

    for e in extras:
        put(e)

    print(cbox + mid_line() + Style.RESET_ALL)
    
    put(status_line)
    
    print(cbox + bot_line() + Style.RESET_ALL)


def capital_inicial_para(base_asset: str) -> float:
    base = base_asset.upper()

    if base not in CAP_INICIAL_POR_BASE:
        raise ValueError(f"Moneda {base} no definida en CAP_INICIAL_POR_BASE")

    return float(CAP_INICIAL_POR_BASE[base])

BOT_CAPITAL_START = capital_inicial_para(SIMBOLO_BALANCE)  # default dinámico por moneda
#BOT_CAPITAL_START = 12.0
#BOT_USE_PCT = 0.95               # usa 95% del capital del bot por trade
# --- Position sizing escalonado (agresivo para cuentas pequeñas) ---
USE_PCT_SMALL = 0.95   # capital chico
USE_PCT_MID   = 0.70   # capital medio
USE_PCT_LARGE = 0.50   # capital grande

CAP_TIER_SMALL = 50.0
CAP_TIER_MID   = 200.0

def bot_use_pct(bot_cap: float) -> float:
    if bot_cap < CAP_TIER_SMALL:
        return USE_PCT_SMALL
    if bot_cap < CAP_TIER_MID:
        return USE_PCT_MID
    return USE_PCT_LARGE

BOT_MIN_TRADE_QUOTE = 10.0        # mínimo para intentar comprar (por debajo, no opera)
# --- Fees / Profit mínimo (pro) ---
FEE_RATE = 0.001            # 0.10% por lado (conservador)
FEE_MULT = 2.2              # 2 lados + buffer (slippage/redondeo)
MIN_NET_PROFIT_PCT = 0.0015 # 0.15% neto mínimo por trade
# --- PREMIUM MODE (más agresivo cuando hay momentum) ---
PREMIUM_MODE = True

# Momentum = RSI más alto + MA20 subiendo + volatilidad suficiente
PREMIUM_RSI_MIN = 56.0          # arriba de esto ya hay intención (agresivo pero razonable)
PREMIUM_RSI_MAX = 78.0          # evitás compra en euforia/fake pump
PREMIUM_VOL_MIN = 0.0030        # 0.30% velas 5m (si es menos, no hay jugo)

# Tendencia corta: MA20 subiendo (en 5m)
PREMIUM_MA20_SLOPE_MIN = 0.0003 # 0.03% (muy leve, solo para evitar mercado plano)

# Boosts cuando hay premium
PREMIUM_TP_MULT = 1.25          # +25% TP en momentum
PREMIUM_SL_MULT = 1.10          # SL un poco más amplio para no salir por ruido
PREMIUM_SIZE_MULT = 1.10        # +10% size SOLO cuando hay momentum (opcional)

# --- GUARD ANTI "CAPITAL INSUFICIENTE" ---
_min_start = BOT_MIN_TRADE_QUOTE / USE_PCT_SMALL
if BOT_CAPITAL_START < _min_start:
    print(f"[CFG] BOT_CAPITAL_START muy bajo ({BOT_CAPITAL_START:.2f}). "
          f"Subiendo a {_min_start:.2f}")
    BOT_CAPITAL_START = _min_start
MIN_POSITION_QUOTE_TO_BLOCK = 5.0
# ------------------------------
# Multi-bot en la MISMA cuenta (sin subcuentas):
# Reserva lógica de QUOTE (USDT) para que 4 bots no se pisen.
# - Si corrés 1 solo bot, podés apagarlo.
# - Si corrés varios bots en paralelo, dejalo en True.
# ------------------------------
USE_GLOBAL_RESERVATION = True
RESERVATION_FILE = "quote_reservations.json"
RESERVATION_LOCK = "quote_reservations.lock"
RESERVATION_LOCK_TIMEOUT_SEC = 3.0
TP_PCT = 0.02               # 0.02=2% take profit
SL_PCT = 0.01               # 0.01=1% stop loss (virtual si no hay OCO)
# --- SMART LOSS PROTECTION ---
SMART_SL_ENABLED = True

SMART_SL_BE_TRIGGER = 0.004      # +0.4% → mover SL a break even
SMART_SL_TRAIL_TRIGGER = 0.012   # +1.2% → activar trailing
SMART_SL_TRAIL_PCT = 0.005       # trailing 0.5%
# --- Smart SL: buffer dinámico por ATR% (anti-whipsaw) ---
SMART_SL_TRAIL_BUFFER_ATR_K = 0.35     # buffer = K * ATR% (ATR% = LAST_VOL_5M)
SMART_SL_TRAIL_BUFFER_MIN = 0.0006     # 0.06% mínimo
SMART_SL_TRAIL_BUFFER_MAX = 0.0020     # 0.20% máximo

SL_LIMIT_EXTRA = 0.005      # 0.5% debajo del stop (solo si hay STOP_LOSS_LIMIT real)
ALLOW_REBUY = True          # True: cuando se vende, vuelve a buscar compra (ciclo infinito)
STATE_FILE = f"{SIMBOLO}_state.json"   # estado de TP/SL (se crea solo)

LAST_VOL_5M = None
VOL_5M_DEFAULT = 0.003  # 0.3% (default si recién arranca y no hay 50 velas cerradas)
# --- Spread guard (para compras MARKET) ---
SPREAD_MAX_PCT = 0.0015          # 0.15% tope duro
SPREAD_TP_FRACTION = 0.35        # spread permitido como % del TP estimado
# --- Filtro mercado muerto ---
VOL_5M_MIN_PCT = 0.0010   # 0.20% mínimo para operar
VOL_5M_MAX_PCT = 0.0250   # 2% máximo (evita mercado loco)

# ==============================
# MARKET REGIME FILTER
# ==============================
USE_MARKET_REGIME_FILTER = True

REGIME_VOL_DEAD_MAX = VOL_5M_MIN_PCT
REGIME_VOL_CHAOTIC_MIN = VOL_5M_MAX_PCT
REGIME_MA20_SLOPE_MIN_PCT = 0.0005   # 0.05%

# --- Micro Breakout Entry (agresivo con control) ---
BREAKOUT_MODE = True
BREAKOUT_LOOKBACK = 12          # 12 velas 5m = 1h de resistencia
BREAKOUT_BUFFER_PCT = 0.0005    # 0.05% arriba del high reciente
BREAKOUT_VOL_MIN_PCT = 0.0020   # vol mínima (0.20%) para evitar mercado muerto
BREAKOUT_RSI_MIN = 52.0         # momentum mínimo
BREAKOUT_REQUIRE_MACRO = True   # respeta filtro macro (MA50 1H)


# Aliases (para mantener compatibilidad con versiones anteriores del script)
simbolo = SIMBOLO
simboloBalance = SIMBOLO_BALANCE


# Sleeps (ajustados para evitar rate-limit; no hace falta 20s)
SLEEP_BALANCE_SEC = 60      # refresco de balance/cuenta (pesado)
SLEEP_MAIN_SEC = 5         # loop principal
SLEEP_AFTER_BUY_SEC = 5    # pausa tras enviar market buy
SLEEP_MONITOR_SEC = 10       # polling del monitor TP/SL virtual

# Protecciones anti-recompra
BUY_COOLDOWN_SEC = 90     # 5 minutos sin volver a comprar tras una compra
ONE_BUY_PER_CANDLE = True   # si True, compra como máximo 1 vez por vela cerrada de 5m
# --- Pullback Entry a MA20 (agresivo, micro-scalping) ---
PULLBACK_MODE = True

# Banda alrededor de MA20 para "comprar el retroceso"
# Ejemplo: si MA20=1.0000, compra si el precio está entre 0.9960 y 1.0020
PULLBACK_ABOVE_MA20_PCT = 0.0020   # +0.20% arriba de MA20
PULLBACK_BELOW_MA20_PCT = 0.0040   # -0.40% debajo de MA20

# Exigir que MA20 no esté cayendo (evita comprar pullbacks en bajada)
PULLBACK_REQUIRE_MA20_UP = True

import random
from binance.exceptions import BinanceAPIException, BinanceRequestException
import requests

def api_call(fn, *, retries=8, base_sleep=1.0, max_sleep=30.0, tag="api"):
    """
    Reintenta errores transitorios (rate limit / timeouts / network) con backoff exponencial.
    Maneja desincronización de reloj (Binance error -1021) sincronizando hora.
    """
    backoff = base_sleep
    for attempt in range(1, retries + 1):
        try:
            return fn()
        except BinanceAPIException as e:
            msg = str(e)
            code = getattr(e, "code", None)

            # Desincronización de reloj (timestamp)
            if code == -1021 or "timestamp" in msg.lower():
                print(Fore.YELLOW + f"[{tag}] timestamp desincronizado, sincronizando reloj... (attempt {attempt}/{retries})")
                try:
                    sync_time()
                except Exception as e2:
                    print(Fore.YELLOW + f"[{tag}] sync_time falló: {e2}")
                time.sleep(base_sleep)
                continue

            # Rate limit / bans
            if code in (-1003, -1015) or "too many requests" in msg.lower():
                print(Fore.YELLOW + f"[{tag}] rate limit, espero {backoff:.1f}s (attempt {attempt}/{retries})")
                time.sleep(backoff)
                backoff = min(backoff * 2, max_sleep)
                continue

            # Otros errores API: no reintento por defecto
            raise

        except (requests.exceptions.RequestException, ConnectionError, TimeoutError) as e:
            print(Fore.YELLOW + f"[{tag}] error red: {e}. Espero {backoff:.1f}s (attempt {attempt}/{retries})")
            time.sleep(backoff)
            backoff = min(backoff * 2, max_sleep)
            continue

    raise Exception(f"[{tag}] API falló tras {retries} intentos")



cliente = Client(config.API_KEY, config.API_SECRET, tld='com')
def get_spread_pct(symbol: str) -> tuple[float, float, float]:
    """
    Retorna (spread_pct, bid, ask).
    spread_pct = (ask - bid) / ask
    """
    t = api_call(lambda: cliente.get_orderbook_ticker(symbol=symbol), tag="get_orderbook_ticker")
    bid = float(t["bidPrice"])
    ask = float(t["askPrice"])
    if ask <= 0:
        return 1.0, bid, ask
    spread_pct = (ask - bid) / ask
    return spread_pct, bid, ask

# =========================
# Snapshot de cuenta (1 llamada por iteración)
# =========================
ACCOUNT_SNAPSHOT = None
ACCOUNT_SNAPSHOT_TS_MS = 0

def refresh_account_snapshot(force: bool = False, max_age_s: float = 1.5) -> dict:
    """Snapshot de cuenta con cache corta (evita llamadas repetidas a Binance en el mismo loop).

    Devuelve un dict asset -> {"free": float, "locked": float, "total": float}.
    """
    global ACCOUNT_SNAPSHOT, ACCOUNT_SNAPSHOT_TS_MS

    now_ms = int(time.time() * 1000)
    if (not force) and ACCOUNT_SNAPSHOT and (now_ms - ACCOUNT_SNAPSHOT_TS_MS) <= int(max_age_s * 1000):
        return ACCOUNT_SNAPSHOT

    acc = api_call(cliente.get_account, tag="get_account")

    balmap: dict[str, dict[str, float]] = {}
    for b in acc.get("balances", []):
        asset = b.get("asset")
        if not asset:
            continue
        free = float(b.get("free", 0) or 0)
        locked = float(b.get("locked", 0) or 0)
        total = free + locked
        balmap[asset] = {"free": free, "locked": locked, "total": total}

    ACCOUNT_SNAPSHOT = balmap
    ACCOUNT_SNAPSHOT_TS_MS = now_ms
    return balmap

def sync_time():
    """Sincroniza reloj local con server Binance para evitar error -1021."""
    global cliente
    try:
        server = cliente.get_server_time()
        offset = int(server['serverTime']) - int(time.time() * 1000)
        # python-binance usa timestamp_offset internamente
        try:
            cliente.timestamp_offset = offset
        except Exception:
            pass
        return offset
    except Exception:
        return None


# ------------------------------
sync_time()  # intento inicial (si falla, api_call reintenta)

# Helpers
# ------------------------------

def _decimals_from_step(step: float) -> int:
    s = ('%.16f' % step).rstrip('0').rstrip('.')
    return len(s.split('.')[-1]) if '.' in s else 0


def quantize_down(value: float, step: float) -> float:
    if step <= 0:
        return value
    d = _decimals_from_step(step)
    return math.floor(value / step) * step if step < 1 else math.floor(value)


def format_by_step(value: float, step: float) -> str:
    q = quantize_down(value, step)
    d = _decimals_from_step(step)
    return f"{q:.{d}f}"


def load_state() -> dict | None:
    if not os.path.exists(STATE_FILE):
        return None
    try:
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def save_state(st: dict) -> None:
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(st, f, indent=2)


def clear_state() -> None:
    try:
        if os.path.exists(STATE_FILE):
            os.remove(STATE_FILE)
    except Exception:
        pass



def infer_quote_asset(symbol: str) -> str:
    """Infiero el QUOTE (USDT/USDC/etc) desde el símbolo. Default: USDT."""
    common_quotes = ["USDT","USDC","BUSD","FDUSD","TUSD","BTC","ETH","BNB","EUR","TRY"]
    for q in common_quotes:
        if symbol.endswith(q):
            return q
    return "USDT"

def get_free_balance(asset: str) -> float:
    asset = asset.upper()

    if ACCOUNT_SNAPSHOT is not None and asset in ACCOUNT_SNAPSHOT:
        return float(ACCOUNT_SNAPSHOT.get(asset, {}).get("free", 0.0))

    bal = api_call(lambda: cliente.get_asset_balance(asset=asset), tag="get_asset_balance")
    return float(bal["free"]) if bal else 0.0

def get_total_balance(asset: str) -> float:
    asset = asset.upper()

    if ACCOUNT_SNAPSHOT is not None and asset in ACCOUNT_SNAPSHOT:
        return float(ACCOUNT_SNAPSHOT.get(asset, {}).get("total", 0.0))

    bal = api_call(lambda: cliente.get_asset_balance(asset=asset), tag="get_asset_balance")
    if not bal:
        return 0.0
    return float(bal["free"]) + float(bal["locked"])

def print_spot_balance(print_it: bool = True) -> str:
    """Devuelve (y opcionalmente imprime) el balance SPOT base/quote para el símbolo actual."""
    quote = infer_quote_asset(SIMBOLO)

    base_total = get_total_balance(SIMBOLO_BALANCE)
    quote_total = get_total_balance(quote)

    line = (
        Fore.MAGENTA
        + f"[{SIMBOLO}] Balance SPOT => "
        + f"{SIMBOLO_BALANCE} {base_total:.8f} == {quote} {quote_total:.8f}"
        + Style.RESET_ALL
    )

    if print_it:
        print(line)
    return line

def get_last_buy_meta() -> tuple[int | None, int | None]:
    """Devuelve (last_buy_ts, last_buy_candle_open_time_ms) desde BOT_STATE_FILE."""
    st = load_bot_state()
    ts = st.get("last_buy_ts")
    candle = st.get("last_buy_candle")
    try:
        ts = int(ts) if ts is not None else None
    except Exception:
        ts = None
    try:
        candle = int(candle) if candle is not None else None
    except Exception:
        candle = None
    return ts, candle

def set_last_buy_meta(ts: int, candle_open_time_ms: int | None) -> None:
    st = load_bot_state()
    st["last_buy_ts"] = int(ts)
    if candle_open_time_ms is not None:
        st["last_buy_candle"] = int(candle_open_time_ms)
    save_bot_state(st)

def has_exit_state_or_orders(symbol: str) -> bool:
    """True si ya hay una salida armada (STATE_FILE) o hay ordenes abiertas."""
    try:
        if list_open_orders(symbol):
            return True
    except Exception:
        pass
    st = load_state()
    return bool(st and st.get("symbol") == symbol)

def should_block_buy(symbol: str, base_asset: str, quote_asset: str, current_candle_open_ms: int | None) -> tuple[bool, str]:
    """
    Bloquea compras repetidas:
    - si ya hay posición (balance base > 0)
    - si hay ordenes abiertas o state de salida
    - si estamos dentro de cooldown tras la última compra
    - si ya compró en esta misma vela cerrada (anti doble disparo)
    """
    
    # 1) Posición existente (ignoramos "dust")
    base_total = get_total_balance(base_asset)
    if base_total > 0:
        try:
            last_price = float(api_call(
                lambda: cliente.get_symbol_ticker(symbol=symbol),
                tag="get_symbol_ticker"
            )["price"])
            base_value_quote = base_total * last_price
        except Exception:
            base_value_quote = 999999.0  # si falla el precio, bloqueamos por seguridad

        print("DEBUG POS:", base_total, base_value_quote, MIN_POSITION_QUOTE_TO_BLOCK)

        if base_value_quote >= MIN_POSITION_QUOTE_TO_BLOCK:
            return True, (
                f"Ya hay posición: {base_asset} total={base_total:.8f} "
                f"(~{base_value_quote:.2f} {quote_asset})"
            )
    # Si es menor al umbral, se considera polvo y NO bloquea

    # 2) Salidas/órdenes activas
    if has_exit_state_or_orders(symbol):
        return True, "Ya hay órdenes/estado de salida activo"

    # 3) Cooldown
    last_ts, last_candle = get_last_buy_meta()
    now = int(time.time())
    if last_ts is not None and (now - last_ts) < BUY_COOLDOWN_SEC:
        return True, f"Cooldown activo ({now - last_ts}s < {BUY_COOLDOWN_SEC}s)"

    # 4) Una compra por vela
    if ONE_BUY_PER_CANDLE and current_candle_open_ms is not None and last_candle is not None:
        if int(current_candle_open_ms) == int(last_candle):
            return True, "Ya compraste en esta misma vela (ONE_BUY_PER_CANDLE)"

    return False, ""

def load_bot_state() -> dict:
    try:
        if os.path.exists(BOT_STATE_FILE):
            with open(BOT_STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def save_bot_state(st: dict) -> None:
    try:
        with open(BOT_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(st, f, indent=2)
    except Exception:
        pass

# ------------------------------
# Reserva lógica de QUOTE (anti pisadas entre bots)
# ------------------------------
def _lock_acquire(path: str, timeout_sec: float) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout_sec:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            return True
        except FileExistsError:
            time.sleep(0.05)
    return False

def _lock_release(path: str) -> None:
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass

def _load_reservations() -> dict:
    if not os.path.exists(RESERVATION_FILE):
        return {}
    try:
        with open(RESERVATION_FILE, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}

def _save_reservations(d: dict) -> None:
    tmp = RESERVATION_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2)
    os.replace(tmp, RESERVATION_FILE)

def get_reserved_total(exclude_symbol: str | None = None) -> float:
    d = _load_reservations()
    total = 0.0
    for sym, amt in d.items():
        if exclude_symbol and sym == exclude_symbol:
            continue
        try:
            total += float(amt)
        except Exception:
            pass
    return float(total)

def reserve_quote(symbol: str, quote_asset: str, amount: float) -> tuple[bool, str]:
    """Reserva amount de QUOTE para este bot. Evita que otros bots lo usen en paralelo."""
    if not USE_GLOBAL_RESERVATION:
        return True, ""
    if amount <= 0:
        return False, "amount<=0"
    if not _lock_acquire(RESERVATION_LOCK, RESERVATION_LOCK_TIMEOUT_SEC):
        return False, "No pude tomar lock de reservas (otro bot escribiendo)."

    try:
        d = _load_reservations()
        reserved_other = 0.0
        for sym, amt in d.items():
            if sym != symbol:
                try:
                    reserved_other += float(amt)
                except Exception:
                    pass

        free_quote = get_free_balance(quote_asset)
        available = max(0.0, free_quote - reserved_other)

        if available + 1e-9 < amount:
            return False, f"Disponible {available:.6f} {quote_asset} < reserva {amount:.6f} (otros bots reservan {reserved_other:.6f})."

        d[symbol] = float(amount)
        _save_reservations(d)
        return True, ""
    finally:
        _lock_release(RESERVATION_LOCK)

def release_quote(symbol: str) -> None:
    if not USE_GLOBAL_RESERVATION:
        return
    if not _lock_acquire(RESERVATION_LOCK, RESERVATION_LOCK_TIMEOUT_SEC):
        return
    try:
        d = _load_reservations()
        if symbol in d:
            d.pop(symbol, None)
            _save_reservations(d)
    finally:
        _lock_release(RESERVATION_LOCK)


def get_bot_capital() -> float:
    st = load_bot_state()
    cap = st.get("bot_capital_quote")
    if cap is None:
        cap = BOT_CAPITAL_START
        st["bot_capital_quote"] = cap
        st["quote_asset"] = infer_quote_asset(SIMBOLO)
        save_bot_state(st)
    return float(cap)

def set_bot_capital(new_cap: float) -> None:
    st = load_bot_state()
    st["bot_capital_quote"] = float(max(0.0, new_cap))
    st["quote_asset"] = st.get("quote_asset") or infer_quote_asset(SIMBOLO)
    save_bot_state(st)

def add_bot_pnl(pnl_quote: float) -> None:
    """Suma/resta PnL al capital del bot (en QUOTE)."""
    cap = get_bot_capital()
    set_bot_capital(cap + float(pnl_quote))
def get_filters(simbolo: str):
    info = api_call(lambda: cliente.get_symbol_info(simbolo), tag="get_symbol_info")
    if not info:
        raise Exception(f"No pude obtener info del símbolo {simbolo}")

    lot_filter = next((f for f in info.get('filters', []) if f.get('filterType') in ('LOT_SIZE', 'MARKET_LOT_SIZE')), None)
    price_filter = next((f for f in info.get('filters', []) if f.get('filterType') == 'PRICE_FILTER'), None)
    min_notional_filter = next((f for f in info.get('filters', []) if f.get('filterType') in ('MIN_NOTIONAL', 'NOTIONAL')), None)

    stepSize = float((lot_filter or {}).get('stepSize', '1') or 1)
    tickSize = float((price_filter or {}).get('tickSize', '0.00000001') or 0.00000001)

    minNotional = None
    if min_notional_filter:
        v = min_notional_filter.get('minNotional') or min_notional_filter.get('notional')
        try:
            minNotional = float(v)
        except Exception:
            minNotional = None

    oco_allowed = bool(info.get('ocoAllowed', False))
    return stepSize, tickSize, minNotional, oco_allowed


def get_symbol_filters(simbolo: str):
    """Alias para compatibilidad (antes se llamaba get_symbol_filters)."""
    return get_filters(simbolo)


def get_last_buy_avg_price(simbolo: str) -> float | None:
    """Promedio del último BUY (si existe) para usar como entry real."""
    try:
        trades = api_call(lambda: cliente.get_my_trades(symbol=simbolo, limit=50), tag="get_my_trades")
        # buscar último BUY
        for t in reversed(trades):
            if t.get('isBuyer'):
                try:
                    return float(t.get('price'))
                except Exception:
                    return None
        return None
    except Exception:
        return None


def list_open_orders(simbolo: str) -> list:
    try:
        return api_call(lambda: cliente.get_open_orders(symbol=simbolo), tag="get_open_orders")
    except Exception:
        return []

def safe_sell_qty(asset: str, stepSize: float) -> float:
    free = get_free_balance(asset)   # <-- debe usar snapshot
    return quantize_down(free, stepSize)

def cancel_order_safe(simbolo: str, order_id: int):
    try:
        api_call(lambda: cliente.cancel_order(symbol=simbolo, orderId=int(order_id)), tag="cancel_order")
        return True
    except Exception:
        return False

def market_sell_safe(simbolo: str, asset: str, stepSize: float):
    """Vende TODO el asset en market. Devuelve el dict de la orden o None."""
    refresh_account_snapshot()
    qty = safe_sell_qty(asset, stepSize)
    if qty <= 0:
        print(Fore.MAGENTA + f"❌ No hay {asset} FREE para vender MARKET.")
        return None
    try:
        order = api_call(lambda: cliente.order_market_sell(symbol=simbolo, quantity=format_by_step(qty, stepSize)), tag="order_market_sell")
        print(Fore.MAGENTA + f"✅ Vendí MARKET {qty} {asset}.")
        return order
    except Exception as e:
        # Si sigue dando insuficiente balance, bajo 1 step e intento 1 vez
        try:
            qty2 = quantize_down(max(qty - stepSize, 0), stepSize)
            if qty2 > 0:
                order = api_call(lambda: cliente.order_market_sell(symbol=simbolo, quantity=format_by_step(qty2, stepSize)), tag="order_market_sell")
                print(Fore.MAGENTA + f"✅ Vendí MARKET {qty2} {asset} (ajustado por balance).")
                return order
        except Exception:
            pass
        print(Fore.MAGENTA + f"❌ Error vendiendo MARKET: {e}")
        return None
def ensure_exit_for_existing_position(simbolo: str, asset: str, stepSize: float, tickSize: float, minNotional: float | None, curr_close: float, tp_pct: float | None = None, sl_pct: float | None = None) -> bool:
    """Si hay {asset} en SPOT y NO hay estado/ordenes, crea TP LIMIT y activa SL virtual."""

# si no me pasan tp/sl, los calculo dinámicos con la última volatilidad conocida
    global LAST_VOL_5M, VOL_5M_DEFAULT
    if tp_pct is None or sl_pct is None:
        vol_usar = LAST_VOL_5M if LAST_VOL_5M is not None else VOL_5M_DEFAULT
        tp_pct = max(0.004, min(vol_usar * 3.0, 0.015))  # 0.4% a 1.5%
        sl_pct = max(0.003, min(vol_usar * 2.0, 0.012))  # 0.3% a 1.2%

    if list_open_orders(simbolo):
        return False

    st = load_state()
    if st and st.get('symbol') == simbolo:
        return False

    qty = safe_sell_qty(asset, stepSize)
    if qty <= 0:
        return False

    entry = get_last_buy_avg_price(simbolo) or float(curr_close)

    # --- TP mínimo para cubrir fees + margen ---
    if tp_pct is None:
        tp_pct = 0.002

    min_tp_pct = (FEE_RATE * FEE_MULT) + MIN_NET_PROFIT_PCT
    tp_pct_eff = max(float(tp_pct), float(min_tp_pct))

    # precios crudos
    tp_price = entry * (1 + tp_pct_eff)
    sl_stop = entry * (1 - sl_pct)
    sl_limit = sl_stop * (1 - SL_LIMIT_EXTRA)

    # formateo/quantize (lo que vas a mandar a Binance)
    tp_s = format_by_step(tp_price, tickSize)
    qty_s = format_by_step(qty, stepSize)
    sl_s = format_by_step(sl_stop, tickSize)
    sll_s = format_by_step(sl_limit, tickSize)

    print(Fore.YELLOW + f"📌 Tenés {asset} en SPOT y no hay salida. Creo TP LIMIT + SL virtual.")
    print(Fore.YELLOW + f"   qty={qty_s} entry~{entry:.8f} TP={tp_s} SL(stop)={format_by_step(sl_stop, tickSize)}")

    try:
        tp_order = api_call(lambda: cliente.order_limit_sell(symbol=simbolo, quantity=qty_s, price=tp_s), tag="order_limit_sell")
        tp_id = tp_order.get('orderId')
        if not tp_id:
            return False

        save_state({
            'mode': 'TP_LIMIT_SL_VIRTUAL',
            'symbol': simbolo,
            'asset': asset,
            'entry_price': float(entry),
            'qty': float(qty),
            'tp_id': int(tp_id),
            'tp_price': float(tp_price),
            'sl_stop_price': float(sl_stop),
            'sl_limit_price': float(sl_limit),
            'created_at': int(time.time())
        })
        print(Fore.GREEN + f"✅ TP LIMIT creado (id={tp_id}). SL virtual activo.")
        return True
    except Exception as e:
        # Si falla por balance (fee/rounding), bajo 1 step y reintento una vez
        try:
            qty2 = quantize_down(max(qty - stepSize, 0), stepSize)
            if qty2 > 0:
                qty2_s = format_by_step(qty2, stepSize)
                tp_order = api_call(lambda: cliente.order_limit_sell(symbol=simbolo, quantity=qty2_s, price=tp_s), tag="order_limit_sell_retry")



                tp_id = tp_order.get('orderId')
                if tp_id:
                    save_state({
                        'mode': 'TP_LIMIT_SL_VIRTUAL',
                        'symbol': simbolo,
                        'asset': asset,
                        'entry_price': float(entry),
                        'qty': float(qty2),
                        'tp_id': int(tp_id),
                        'tp_price': float(tp_price),
                        'sl_stop_price': float(sl_stop),
                        'sl_limit_price': float(sl_limit),
                        'created_at': int(time.time())
                    })
                    print(Fore.GREEN + f"✅ TP LIMIT creado (id={tp_id}) con qty ajustada={qty2}.")
                    return True
        except Exception:
            pass

        print(Fore.MAGENTA + f"❌ No pude crear TP LIMIT: {e}")
        return False


def monitor_existing_exit_once(simbolo: str, asset: str, stepSize: float) -> bool:
    """Monitorea 1 vez la salida virtual: si toca SL -> cancela TP y vende MARKET."""
    st = load_state()
    if not st or st.get('symbol') != simbolo:
        return False

    if st.get('mode') != 'TP_LIMIT_SL_VIRTUAL':
        return False

    tp_id = int(st.get('tp_id', 0) or 0)
    sl_stop = float(st.get('sl_stop_price', 0) or 0)
    if tp_id <= 0 or sl_stop <= 0:
        return False

    # si TP se llenó/canceló, limpio estado
    try:
        o = api_call(lambda: cliente.get_order(symbol=simbolo, orderId=tp_id), tag="get_order")
        status = o.get('status')
        if status in ('FILLED', 'CANCELED', 'REJECTED', 'EXPIRED'):
            print(Fore.CYAN + f"Estado TP {tp_id} => {status}. Limpio estado.")
            if status == "FILLED":
                # ---- Autofinanciable: actualizo capital del bot con PnL del TP ----
                try:
                    executed = float(o.get("executedQty", st.get("qty", 0.0)) or 0.0)
                    proceeds = float(o.get("cummulativeQuoteQty", 0.0) or 0.0)
                    entry_price = float(st.get("entry_price", 0.0) or 0.0)
                    cost = executed * entry_price
                    pnl = proceeds - cost
                    add_bot_pnl(pnl)
                    quote = infer_quote_asset(simbolo)
                    print(Fore.CYAN + f"[BOT] PnL TP={pnl:.6f} {quote}. Nuevo capital={get_bot_capital():.6f} {quote}")
                except Exception:
                    pass
            clear_state()
            return True
    except Exception:
        pass

    try:
        last = float(api_call(lambda: cliente.get_symbol_ticker(symbol=simbolo), tag="get_symbol_ticker")['price'])
    except Exception:
        return False

    # =========================
    # SMART LOSS PROTECTION
    # =========================
    if SMART_SL_ENABLED:
        entry_price = float(st.get("entry_price", 0.0))

        if entry_price > 0:

            profit_pct = (last - entry_price) / entry_price

            # Break Even automático
            if profit_pct >= SMART_SL_BE_TRIGGER:
                new_sl = entry_price

                if new_sl > sl_stop:
                    print(Fore.GREEN + "🛡 Smart SL → Break Even activado")
                    st["sl_stop_price"] = new_sl
                    save_state(st)
                    sl_stop = new_sl

            # Trailing dinámico
            if profit_pct >= SMART_SL_TRAIL_TRIGGER:

                atr_pct = LAST_VOL_5M if LAST_VOL_5M is not None else VOL_5M_DEFAULT

                buffer_pct = atr_pct * SMART_SL_TRAIL_BUFFER_ATR_K

                if buffer_pct < SMART_SL_TRAIL_BUFFER_MIN:
                    buffer_pct = SMART_SL_TRAIL_BUFFER_MIN
                elif buffer_pct > SMART_SL_TRAIL_BUFFER_MAX:
                    buffer_pct = SMART_SL_TRAIL_BUFFER_MAX

                trailing_sl = last * (1 - (SMART_SL_TRAIL_PCT + buffer_pct))

                if trailing_sl > sl_stop:
                    print(Fore.GREEN + f"🛡 Smart SL → Trailing actualizado: {trailing_sl:.8f}")
                    st["sl_stop_price"] = trailing_sl
                    save_state(st)
                    sl_stop = trailing_sl
    # si precio <= SL -> cancelo TP y vendo MARKET

    if last <= sl_stop:
        print(Fore.MAGENTA + f"🚨 SL virtual gatillado: last={last:.8f} <= SL={sl_stop:.8f}. Cancelo TP y vendo MARKET!")
        cancel_order_safe(simbolo, tp_id)

        qty_needed = safe_sell_qty(asset, stepSize)  # cuánto podrías vender si ya estuviera libre (cuantizado)

        for _ in range(10):  # ~4s
            refresh_account_snapshot()
            free_now = get_free_balance(asset)
            if free_now >= qty_needed and qty_needed > 0:
                break
            time.sleep(0.4)

        order = market_sell_safe(simbolo, asset, stepSize)
        refresh_account_snapshot(force=True)
        # ---- Autofinanciable: actualizo capital del bot con PnL del SL ----
        try:
            if order:
                executed = float(order.get("executedQty", st.get("qty", 0.0)) or 0.0)
                proceeds = float(order.get("cummulativeQuoteQty", 0.0) or 0.0)
                entry_price = float(st.get("entry_price", 0.0) or 0.0)
                cost = executed * entry_price
                pnl = proceeds - cost
                add_bot_pnl(pnl)
                quote = infer_quote_asset(simbolo)
                print(Fore.CYAN + f"[BOT] PnL SL={pnl:.6f} {quote}. Nuevo capital={get_bot_capital():.6f} {quote}")
        except Exception:
            pass
        clear_state()
        return True

    return True


# ------------------------------
# Loop principal
# ------------------------------

def _sma(arr, n):
    if arr is None or len(arr) < n:
        return None
    return sum(arr[-n:]) / n


def _rsi_wilder(arr, period=14):
    if arr is None or len(arr) < period + 1:
        return None
    deltas = [arr[i] - arr[i - 1] for i in range(1, len(arr))]
    seed = deltas[:period]
    avg_gain = sum(d for d in seed if d > 0) / period
    avg_loss = -sum(d for d in seed if d < 0) / period
    for d in deltas[period:]:
        gain = max(d, 0.0)
        loss = max(-d, 0.0)
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))

def atr_pct_from_klines(klines, period=14):
    if len(klines) < period + 1:
        return None

    highs = [float(k[2]) for k in klines]
    lows = [float(k[3]) for k in klines]
    closes = [float(k[4]) for k in klines]

    trs = []
    for i in range(1, len(klines)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i-1]),
            abs(lows[i] - closes[i-1])
        )
        trs.append(tr)

    atr = sum(trs[-period:]) / period
    return atr / closes[-1]

def main():
    # filtros del símbolo (stepSize, tickSize, minNotional)
    global LAST_VOL_5M
    stepSize, tickSize, minNotional, _ = get_symbol_filters(SIMBOLO)

    while True:


        # --- Inicializaciones para evitar warnings de Pylance (runtime-safe) ---

        bot_cap: float | None = None

        quote_asset: str | None = None

        free_quote: float | None = None

        budget: float | None = None

        last_price: float | None = None
        last_closed_open_time_ms: int | None = None

        VOL_5M: float | None = None

        try:
            refresh_account_snapshot()
            bal_line = print_spot_balance(print_it=False)
            # 1) SIEMPRE primero manejo salidas (SL virtual + limpieza)
            monitor_existing_exit_once(SIMBOLO, SIMBOLO_BALANCE, stepSize)

            # 2) Indicadores 5m + volatilidad 5m (últimas velas cerradas)
            try:
                kl = api_call(
                    lambda: cliente.get_klines(
                        symbol=SIMBOLO,
                        interval=Client.KLINE_INTERVAL_5MINUTE,
                        limit=100
                    ),
                    tag="get_klines_5m"
                )

                # Excluir vela en formación
                kl_closed = kl[:-1]
                if len(kl_closed) < 50:
                    raise Exception("No hay suficientes velas cerradas 5m.")

                closes = [float(k[4]) for k in kl_closed]
                highs = [float(k[2]) for k in kl_closed]
                lows = [float(k[3]) for k in kl_closed]
                curr_close = closes[-1]
                last_closed_open_time_ms = int(kl_closed[-1][0])

                #Volatilidad 5m (ATR% aprox)
                #VOL_5M = _atr_pct_from_klines(kl_closed, period=14)
                VOL_5M = atr_pct_from_klines(kl_closed, period=14)
                if VOL_5M is not None:
                    LAST_VOL_5M = VOL_5M

                if VOL_5M < VOL_5M_MIN_PCT:
                    print(Fore.CYAN + f"[SKIP] Mercado muerto VOL_5M(ATR)={VOL_5M:.4%}")
                    time.sleep(SLEEP_MAIN_SEC)
                    continue

                if VOL_5M > VOL_5M_MAX_PCT:
                    print(Fore.CYAN + f"[SKIP] Mercado demasiado volátil VOL_5M(ATR)={VOL_5M:.4%}")
                    time.sleep(SLEEP_MAIN_SEC)
                    continue

            # 3) Filtro macro: MA50 en 1H
                kl_1h = api_call(
                    lambda: cliente.get_klines(
                        symbol=SIMBOLO,
                        interval=Client.KLINE_INTERVAL_1HOUR,
                        limit=60
                    ),
                    tag="get_klines_1h"
                )

                kl_1h_closed = kl_1h[:-1]
                if len(kl_1h_closed) < 50:
                    raise Exception("No hay suficientes velas 1H para MA50.")

                closes_1h = [float(k[4]) for k in kl_1h_closed]
                ma50_1h = _sma(closes_1h, 50)
                cond_macro = (ma50_1h is not None and curr_close > ma50_1h)

            # 4) MAs y RSI en 5m
                ma20 = _sma(closes, 20)
                ma20_prev = _sma(closes[:-1], 20)

                rsi14 = _rsi_wilder(closes, period=14)

            # 5) Señal de compra
                cond_price_above_ma20 = (ma20 is not None and curr_close >= ma20 * 0.998)

                pullback_ok = (
                    ma20 is not None and
                    ma20_prev is not None and
                    curr_close <= ma20 * 1.002 and
                    curr_close >= ma20 * 0.996 and
                    ma20 >= ma20_prev
                )

                cond_rsi = (rsi14 is not None and rsi14 > 48.0 and rsi14 < 80.0)


                pullback_signal = cond_macro and pullback_ok and cond_rsi
                buy_signal = pullback_signal

                # --- Micro Breakout Entry ---
                breakout_ok = False

                if BREAKOUT_MODE and len(highs) >= (BREAKOUT_LOOKBACK + 1):
                    recent_high = max(highs[-(BREAKOUT_LOOKBACK + 1):-1])
                    vol_entry = VOL_5M if VOL_5M is not None else (
                        LAST_VOL_5M if LAST_VOL_5M is not None else VOL_5M_DEFAULT
                    )

                    breakout_price = float(curr_close) >= float(recent_high) * (1.0 + float(BREAKOUT_BUFFER_PCT))
                    breakout_vol = float(vol_entry) >= float(BREAKOUT_VOL_MIN_PCT)
                    breakout_rsi = (rsi14 is not None) and (float(rsi14) >= float(BREAKOUT_RSI_MIN))
                    breakout_macro = cond_macro if BREAKOUT_REQUIRE_MACRO else True

                    breakout_ok = breakout_price and breakout_vol and breakout_rsi and breakout_macro

                    if breakout_ok:
                        print(
                            Fore.CYAN
                            + f"[BREAKOUT] high={recent_high:.8f} close={float(curr_close):.8f} "
                            f"VOL={vol_entry*100:.3f}% RSI={float(rsi14):.2f}"
                        )

                buy_signal = bool(buy_signal or breakout_ok)

                print_panel(
                    SIMBOLO,
                    curr_close,
                    rsi14,
                    ma50_1h,
                    cond_price_above_ma20,
                    cond_rsi,
                    cond_macro,
                    buy_signal,
                    extra_lines=[bal_line]
                )

                # =========================
                # BOT STATUS PARA MONITOR
                # =========================

                try:

                    st_monitor = load_bot_state()

                    st_monitor["symbol"] = SIMBOLO
                    st_monitor["price"] = float(curr_close)

                    st_monitor["ready"] = bool(buy_signal)
                    st_monitor["regime"] = locals().get("market_regime", "UNKNOWN")

                    st_monitor["rsi_5m"] = float(rsi14) if rsi14 else None
                    st_monitor["ma20_5m"] = float(ma20) if ma20 else None
                    st_monitor["ma50_1h"] = float(ma50_1h) if ma50_1h else None

                    st_monitor["vol_5m"] = float(VOL_5M) if VOL_5M else None

                    st_monitor["position_open"] = bool(load_state())

                    st_monitor["bot_capital"] = float(get_bot_capital())

                    st_monitor["last_update"] = int(time.time())

                    save_bot_state(st_monitor)

                except Exception as e:
                    print(Fore.YELLOW + f"[MONITOR] error guardando estado: {e}")

            # 6) MARKET REGIME FILTER
                market_regime = "UNKNOWN"

                if USE_MARKET_REGIME_FILTER:
                    if VOL_5M < REGIME_VOL_DEAD_MAX:
                        market_regime = "DEAD"
                    elif VOL_5M > REGIME_VOL_CHAOTIC_MIN:
                        market_regime = "CHAOTIC"
                    else:
                        ma20_slope = 0.0
                        if ma20 is not None and ma20_prev not in (None, 0):
                            ma20_slope = (ma20 - ma20_prev) / ma20_prev

                        if (
                            ma20 is not None
                            and cond_macro
                            and curr_close > ma20
                            and ma20_slope > REGIME_MA20_SLOPE_MIN_PCT
                        ):
                            market_regime = "TREND"
                        else:
                            market_regime = "RANGE"

                    print(Fore.BLUE + f"[REGIME] {SIMBOLO}: {market_regime}")

                    if market_regime != "TREND":
                        print(Fore.BLUE + f"[SKIP] Mercado no tendencial: {market_regime}")
                        time.sleep(SLEEP_MAIN_SEC)
                        continue

            except Exception as e:
                print(Fore.MAGENTA + f"Error obteniendo velas/indicadores 5m: {e}")
                time.sleep(SLEEP_MAIN_SEC)
                continue
                
            if not cond_macro:
                print("Filtro macro MA50 1H: NO compro (tendencia bajista).")
                time.sleep(SLEEP_MAIN_SEC)
                continue

            if not buy_signal:
                print(Fore.MAGENTA + "No se cumplen las condiciones de compra (5m).")
                time.sleep(SLEEP_MAIN_SEC)
                continue

            # 7) Comprar (market)
            # --- Bloqueo anti-recompra / anti-múltiples compras ---
            block, reason = should_block_buy(SIMBOLO, SIMBOLO_BALANCE, infer_quote_asset(SIMBOLO), last_closed_open_time_ms)
            if block:
                print(Fore.YELLOW + f"[BOT] No compro: {reason}")
                time.sleep(SLEEP_MAIN_SEC)
                continue

            last_price = curr_close
            # --- Spread guard (evita entrar cuando spread + fees te matan) ---
            VOL_USAR_PRE = (
                VOL_5M if VOL_5M is not None
                else (LAST_VOL_5M if LAST_VOL_5M is not None else VOL_5M_DEFAULT)
            )
            tp_est = max(0.006, min(VOL_USAR_PRE * 3.0, 0.015))  # misma lógica que después usás para TP dinámico

            spread_pct, bid, ask = get_spread_pct(SIMBOLO)
            spread_allowed = min(SPREAD_MAX_PCT, tp_est * SPREAD_TP_FRACTION)

            if spread_pct > spread_allowed:
                print(
                    Fore.CYAN
                    + f"[SKIP] Spread alto: {spread_pct*100:.3f}% (bid={bid:.8f} ask={ask:.8f}) "
                    f"> permitido {spread_allowed*100:.3f}% (TP_est={tp_est*100:.2f}%)"
                )
                time.sleep(SLEEP_MAIN_SEC)
                continue
            # --- Modo autofinanciable (QUOTE): el tamaño del trade sale del capital del bot ---
            quote_asset = infer_quote_asset(SIMBOLO)
            bot_cap = get_bot_capital()
            free_quote = get_free_balance(quote_asset)

            # Si hay varios bots, descuento reservas de los otros para evitar pisadas
            reserved_other = get_reserved_total(exclude_symbol=SIMBOLO) if USE_GLOBAL_RESERVATION else 0.0
            free_quote_effective = max(0.0, free_quote - reserved_other)

            # --- Premium conditions (solo si hay momentum real) ---
            premium = False
            premium_tp_mult = 1.0
            premium_sl_mult = 1.0

            if PREMIUM_MODE and (rsi14 is not None) and (ma20 is not None) and (ma20_prev is not None) and (VOL_USAR_PRE is not None):
                ma20_up = (ma20 >= ma20_prev * (1.0 + PREMIUM_MA20_SLOPE_MIN))
                vol_ok = (VOL_USAR_PRE >= PREMIUM_VOL_MIN)
                rsi_ok = (PREMIUM_RSI_MIN <= rsi14 <= PREMIUM_RSI_MAX)

                premium = cond_macro and ma20_up and vol_ok and rsi_ok

                if premium:
                    premium_tp_mult = PREMIUM_TP_MULT
                    premium_sl_mult = PREMIUM_SL_MULT
                    print(Fore.CYAN + f"[PREMIUM] Momentum ON: RSI={rsi14:.2f} VOL={VOL_USAR_PRE*100:.3f}% MA20_up={ma20_up}")

            #budget_quote = min(free_quote_effective, bot_cap) * BOT_USE_PCT
            use_pct = bot_use_pct(bot_cap)
            if premium:
                use_pct = min(1.0, use_pct * PREMIUM_SIZE_MULT)  # boost controlado
            budget_quote = min(free_quote_effective, bot_cap) * use_pct

            if budget_quote < BOT_MIN_TRADE_QUOTE:
                print(Fore.YELLOW + f"[BOT] Capital insuficiente. free_{quote_asset}={free_quote:.6f} bot_cap={bot_cap:.6f} budget={budget_quote:.6f}")
                time.sleep(SLEEP_MAIN_SEC)
                continue
                     
            qty_buy_raw = budget_quote / last_price
            qty_buy = quantize_down(qty_buy_raw, stepSize)
            qty_buy_s = format_by_step(qty_buy, stepSize)   # ← lo convierte al formato exacto permitido

            if qty_buy <= 0:
                print("qty_buy quedó en 0. Revisar USDT_POR_TRADE / stepSize.")
                time.sleep(SLEEP_MAIN_SEC)
                continue

            # --- MIN_NOTIONAL genérico (ajusta qty si entra en budget) ---
            notional = qty_buy * last_price
            if minNotional:
                minN = float(minNotional)
                if notional + 1e-12 < minN:
                    # qty mínima para cumplir minNotional (CEIL a stepSize)
                    min_qty_needed = math.ceil((minN / last_price) / stepSize) * stepSize
                    min_notional_needed = min_qty_needed * last_price
                    if min_notional_needed <= budget_quote + 1e-9:
                        qty_buy = min_qty_needed
                        qty_buy_s = format_by_step(qty_buy, stepSize)
                        notional = min_notional_needed
                    else:
                        print(f"Notional {notional:.4f} < minNotional {minN} y budget={budget_quote} no alcanza. No compro.")
                        time.sleep(SLEEP_MAIN_SEC)
                        continue
            # Reserva lógica antes de enviar la orden (evita que otro bot gaste el mismo USDT en paralelo)
            ok_res, msg_res = reserve_quote(SIMBOLO, quote_asset, budget_quote)
            if not ok_res:
                print(Fore.YELLOW + f"[BOT] No compro (reserva falló): {msg_res}")
                time.sleep(SLEEP_MAIN_SEC)
                continue

            try:
                api_call(lambda: cliente.order_market_buy(symbol=SIMBOLO, quantity=qty_buy_s), tag="order_market_buy")
                
            finally:
                release_quote(SIMBOLO)


            # registro anti-recompra
            set_last_buy_meta(int(time.time()), last_closed_open_time_ms)
            time.sleep(SLEEP_AFTER_BUY_SEC)

            # 7) Precio promedio real (fills)
            entry_price = get_last_buy_avg_price(SIMBOLO)
            if entry_price is None:
                entry_price = last_price
            print(Fore.CYAN + f"Entrada promedio (avg fill): {entry_price}")

            # 8) TP/SL dinámicos según volatilidad (SIEMPRE)
            VOL_USAR = (
                VOL_5M if VOL_5M is not None
                else (LAST_VOL_5M if LAST_VOL_5M is not None else VOL_5M_DEFAULT)
            )
            
            # --- TP/SL adaptativo real (agresivo, micro-scalping) ---
            # VOL_USAR está en "pct" (ej 0.003 = 0.30%)
            TP_MIN = 0.0045     # 0.45%  (más trades en mercado lento)
            TP_MAX = 0.0180     # 1.80%  (más ganancia cuando hay movimiento)
            SL_MIN = 0.0040     # 0.40%
            SL_MAX = 0.0140     # 1.40%

            TP_VOL_MULT = 2.8   # cuánto escala TP con volatilidad
            SL_VOL_MULT = 2.2   # SL un poco menor que TP para micro ganancias

            TP_PCT_DYN = max(TP_MIN, min(VOL_USAR * TP_VOL_MULT, TP_MAX))
            SL_PCT_DYN = max(SL_MIN, min(VOL_USAR * SL_VOL_MULT, SL_MAX))
            # --- Premium boost sobre TP/SL (más ganancia cuando hay momentum) ---
            if premium:
                TP_PCT_DYN = min(TP_MAX, TP_PCT_DYN * premium_tp_mult)
                SL_PCT_DYN = min(SL_MAX, SL_PCT_DYN * premium_sl_mult)

            print(
                Fore.YELLOW
                + f"TP dinámico={TP_PCT_DYN*100:.2f}%  SL dinámico={SL_PCT_DYN*100:.2f}%  (VOL_USAR={VOL_USAR*100:.3f}%)"
            )
            print(f"[VOL] VOL_5M={VOL_5M} LAST_VOL_5M={LAST_VOL_5M} VOL_USAR={VOL_USAR}")

            # 9) Crear salida (TP LIMIT + SL virtual)
            ensure_exit_for_existing_position(
                SIMBOLO, SIMBOLO_BALANCE, stepSize, tickSize, minNotional,
                entry_price,
                tp_pct=TP_PCT_DYN, sl_pct=SL_PCT_DYN
            )

            time.sleep(SLEEP_MONITOR_SEC)


        except KeyboardInterrupt:
            print(Fore.YELLOW + "\nDetenido por usuario.")
            break

        except Exception as e:
            # por si quedó una reserva colgada
            try:
                release_quote(SIMBOLO)
            except Exception:
                pass
            print(Fore.MAGENTA + f"⚠️ Error: {e}")
            time.sleep(5)



if __name__ == '__main__':
    main()