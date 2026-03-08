from flask import Flask, jsonify, request, render_template_string
import json
import os
from datetime import datetime, timedelta

app = Flask(__name__)

STATE_FILE = "render_monitor_state.json"
MONITOR_TOKEN = os.getenv("MONITOR_TOKEN", "")


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_state(payload: dict):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def token_ok(req) -> bool:
    if not MONITOR_TOKEN:
        return True
    return req.headers.get("X-Monitor-Token", "") == MONITOR_TOKEN


HTML_TEMPLATE = """
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ALPHA MONITOR</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #ffffff;
      --panel: #ffffff;
      --panel-soft: #fafafa;
      --panel-2: #f6f7f9;
      --text: #1f2937;
      --muted: #6b7280;
      --good: #f59e0b;
      --bad: #ff00ff;
      --warn: #d946ef;
      --line: #e5e7eb;
      --head: #f3f4f6;
      --shadow: 0 10px 26px rgba(15, 23, 42, 0.06);
      --orange: #f59e0b;
      --orange-soft: rgba(245, 158, 11, 0.18);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: 'Inter', Arial, Helvetica, sans-serif;
      padding: 24px;
    }
    .wrap {
      max-width: 1380px;
      margin: 0 auto;
    }
    .topbar {
      display: flex;
      align-items: center;
      gap: 14px;
      margin-bottom: 6px;
    }
    .title {
      margin: 0;
      font-size: 28px;
      font-weight: 800;
      letter-spacing: -0.03em;
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .binance-mark {
      width: 32px;
      height: 32px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      border-radius: 9px;
      background: #fff7e6;
      border: 1px solid #fde68a;
      color: #f0b90b;
      flex: 0 0 auto;
    }
    .sub {
      color: var(--muted);
      margin-bottom: 18px;
      font-size: 14px;
    }
    .grid-primary,
    .grid-secondary,
    .grid-tertiary,
    .grid-quaternary {
      display: grid;
      gap: 14px;
      margin-bottom: 16px;
      align-items: stretch;
    }
    .grid-primary { grid-template-columns: repeat(4, minmax(0, 1fr)); }
    .grid-secondary { grid-template-columns: repeat(4, minmax(0, 1fr)); }
    .grid-tertiary { grid-template-columns: repeat(4, minmax(0, 1fr)); }
    .grid-quaternary { grid-template-columns: repeat(4, minmax(0, 1fr)); }
    .card {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 16px 18px;
      min-width: 0;
      box-shadow: var(--shadow);
    }
    .label {
      color: var(--muted);
      font-size: 13px;
      margin-bottom: 10px;
      font-weight: 500;
    }
    .value {
      font-size: 22px;
      font-weight: 800;
      line-height: 1.2;
      letter-spacing: -0.03em;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .mono {
      font-variant-numeric: tabular-nums;
      white-space: nowrap;
      text-align: right;
    }
    .good { color: var(--orange); }
    .bad, .warn { color: var(--bad); }
    .neutral { color: var(--text); }
    .magenta { color: var(--bad); }
    table {
      width: 100%;
      border-collapse: separate;
      border-spacing: 0;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 16px;
      overflow: hidden;
      box-shadow: var(--shadow);
      table-layout: fixed;
    }
    thead th {
      background: var(--head);
      color: #374151;
      font-weight: 700;
      font-size: 14px;
      letter-spacing: 0.01em;
      border-bottom: 1px solid var(--line);
    }
    th, td {
      padding: 12px 10px;
      text-align: left;
      font-size: 14px;
      vertical-align: top;
      border-bottom: 1px solid #edf2f7;
    }
    tbody tr:last-child td { border-bottom: 0; }
    tbody tr:hover td { background: #fffaf0; }
    .coin-cell {
      display: flex;
      align-items: center;
      gap: 10px;
      min-width: 0;
      font-weight: 800;
      letter-spacing: -0.02em;
    }
    .coin-logo {
      width: 22px;
      height: 22px;
      border-radius: 999px;
      object-fit: cover;
      flex: 0 0 auto;
      background: #fff7e6;
      border: 1px solid #fde68a;
    }
    .pill {
      display: inline-block;
      padding: 4px 8px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 700;
      border: 1px solid #d946ef;
      color: #d946ef;
      background: #fdf4ff;
    }
    .muted { color: var(--muted); }
    .panels-row {
      display: grid;
      gap: 14px;
      grid-template-columns: minmax(0, 1fr) minmax(300px, 360px);
      margin-top: 14px;
      margin-bottom: 14px;
      align-items: start;
    }
    .mini-panel, .chart-panel {
      background: var(--panel-soft);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 18px;
      box-shadow: var(--shadow);
    }
    .mini-title, .chart-title {
      font-size: 16px;
      font-weight: 700;
      margin-bottom: 14px;
    }
    .bar-row {
      display: grid;
      grid-template-columns: 84px 1fr 70px;
      gap: 10px;
    }
      align-items: center;
      margin-bottom: 10px;
      font-size: 14px;
    }
    .bar-track {
      width: 100%;
      height: 12px;
      border-radius: 999px;
      background: #f3f4f6;
      overflow: hidden;
      border: 1px solid #e5e7eb;
    }
    .bar-fill {
      height: 100%;
      border-radius: 999px;
      background: linear-gradient(90deg, #fbbf24, #f59e0b);
    }
    .chart-head {
      display: flex;
      align-items: baseline;
      gap: 12px;
      margin-bottom: 14px;
    }
    .chart-year {
      color: var(--muted);
      font-weight: 600;
      font-size: 14px;
    }
    .chart-wrap {
      height: 220px;
      position: relative;
    }
    .footer {
      margin-top: 12px;
      color: var(--muted);
      font-size: 12px;
    }
    @media (max-width: 1100px) {
      .grid-primary, .grid-secondary, .grid-tertiary, .grid-quaternary { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .panels-row { grid-template-columns: 1fr; }
    }
    @media (max-width: 860px) {
      body { padding: 14px; }
      .value { font-size: 20px; }
      table { display: block; overflow-x: auto; }
    }
    @media (max-width: 560px) {
      .grid-primary, .grid-secondary, .grid-tertiary, .grid-quaternary { grid-template-columns: 1fr; }
      .title { font-size: 24px; }
      .bar-row { grid-template-columns: 72px 1fr 78px; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="topbar">
      <div class="title">
        <span class="binance-mark" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
            <path d="M12 2.7 9.46 5.23 12 7.77l2.54-2.54L12 2.69Zm-5.23 5.23L4.23 10.46 6.77 13l2.54-2.54-2.54-2.53Zm10.46 0-2.54 2.53L17.23 13l2.54-2.54-2.54-2.53ZM12 13.15 9.46 15.69 12 18.23l2.54-2.54L12 13.15Zm0-7.84-5.15 5.15L12 15.61l5.15-5.15L12 5.31Zm0 3.59 1.56 1.56L12 12.02l-1.56-1.56L12 8.9Z"/>
          </svg>
        </span>
        ALPHA MONITOR
      </div>
    </div>
    <div class="sub">Última actualización: {{ updated_at or 'Sin datos' }}</div>

    <div class="grid-primary">
      <div class="card">
        <div class="label">Balance estimado</div>
        <div class="value mono neutral">{{ balance }}</div>
      </div>
      <div class="card">
        <div class="label">PnL 24h</div>
        <div class="value mono {{ pnl24_class }}">{{ pnl24 }}</div>
      </div>
      <div class="card">
        <div class="label">PnL 7d</div>
        <div class="value mono {{ pnl7_class }}">{{ pnl7 }}</div>
      </div>
      <div class="card">
        <div class="label">PnL 30d</div>
        <div class="value mono {{ pnl30_class }}">{{ pnl30 }}</div>
      </div>
    </div>

    <div class="grid-secondary">
      <div class="card">
        <div class="label">Closed Trades 24h</div>
        <div class="value mono neutral">{{ closed_trades_24h }}</div>
      </div>
      <div class="card">
        <div class="label">Win Rate 24h</div>
        <div class="value mono magenta">{{ win_rate_24h }}</div>
      </div>
      <div class="card">
        <div class="label">Profit Factor 24h</div>
        <div class="value mono magenta">{{ profit_factor_24h }}</div>
      </div>
      <div class="card">
        <div class="label">Fees 24h</div>
        <div class="value mono magenta">{{ fees_24h }}</div>
      </div>
    </div>

    <div class="grid-tertiary">
      <div class="card">
        <div class="label">Closed Trades 7d</div>
        <div class="value mono neutral">{{ closed_trades_7d }}</div>
      </div>
      <div class="card">
        <div class="label">Win Rate 7d</div>
        <div class="value mono magenta">{{ win_rate_7d }}</div>
      </div>
      <div class="card">
        <div class="label">Profit Factor 7d</div>
        <div class="value mono magenta">{{ profit_factor_7d }}</div>
      </div>
      <div class="card">
        <div class="label">Fees 7d</div>
        <div class="value mono magenta">{{ fees_7d }}</div>
      </div>
    </div>

    <div class="grid-quaternary">
      <div class="card">
        <div class="label">Closed Trades 30d</div>
        <div class="value mono neutral">{{ closed_trades_30d }}</div>
      </div>
      <div class="card">
        <div class="label">Win Rate 30d</div>
        <div class="value mono magenta">{{ win_rate_30d }}</div>
      </div>
      <div class="card">
        <div class="label">Profit Factor 30d</div>
        <div class="value mono magenta">{{ profit_factor_30d }}</div>
      </div>
      <div class="card">
        <div class="label">Fees 30d</div>
        <div class="value mono magenta">{{ fees_30d }}</div>
      </div>
    </div>

    <table>
      <thead>
        <tr>
          <th style="width:16%;">Moneda</th>
          <th style="width:12%;">Precio</th>
          <th style="width:10%;">Mercado</th>
          <th style="width:12%;">Posición</th>
          <th style="width:14%;">PnL 24h</th>
          <th style="width:9%;">Cerrado</th>
          <th style="width:10%;">Efectividad</th>
          <th style="width:17%;">Última operación</th>
        </tr>
      </thead>
      <tbody>
        {% for bot in bots %}
        <tr>
          <td>
            <div class="coin-cell">
              <img class="coin-logo" src="{{ bot.logo_url }}" alt="{{ bot.symbol }}">
              <strong>{{ bot.symbol }}</strong>
            </div>
          </td>
          <td class="mono">{{ bot.price_text }}</td>
          <td>{{ bot.market_text }}</td>
          <td>{{ bot.position_text }}</td>
          <td class="mono {{ bot.pnl_class }}">{{ bot.pnl_24h_text }}</td>
          <td class="mono">{{ bot.closed_trades_24h }}</td>
          <td class="mono {{ bot.win_rate_class }}">{{ bot.win_rate_text }}</td>
          <td>
            {% if bot.last_trade and bot.last_trade.side %}
              <span class="pill">{{ bot.last_trade.side }}</span><br>
              <span class="muted">{{ bot.last_trade.time }}</span><br>
              <span>Precio: {{ bot.last_trade.price }}</span><br>
              <span>Cant.: {{ bot.last_trade.qty }}</span>
            {% else %}
              <span class="muted">Sin operación reciente</span>
            {% endif %}
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>

    <div class="panels-row">
      <div class="mini-panel">
        <div class="mini-title">PnL 24h por moneda</div>
        {% for row in pnl_bars %}
        <div class="bar-row">
          <div>{{ row.symbol }}</div>
          <div class="bar-track"><div class="bar-fill" style="width: {{ row.width }}%;"></div></div>
          <div class="mono magenta">{{ row.text }}</div>
        </div>
        {% endfor %}
      </div>
      <div class="mini-panel">
        <div class="mini-title">Efectividad</div>
        <div class="bar-row">
          <div>Ganadas</div>
          <div class="bar-track"><div class="bar-fill" style="width: {{ wins_pct }}%;"></div></div>
          <div class="mono magenta">{{ wins_pct_text }}</div>
        </div>
        <div class="bar-row">
          <div>Perdidas</div>
          <div class="bar-track"><div class="bar-fill" style="width: {{ losses_pct }}%;"></div></div>
          <div class="mono magenta">{{ losses_pct_text }}</div>
        </div>
      </div>
    </div>

    <div class="chart-panel">
      <div class="chart-head">
        <div class="chart-title">Evolución estimada (USDT)</div>
        <div class="chart-year">{{ chart_year }}</div>
      </div>
      <div class="chart-wrap">
        <canvas id="equityChart"></canvas>
      </div>
    </div>

    <div class="footer">Auto refresh: 30 segundos</div>
  </div>

  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <script>
    const labels = {{ chart_labels|safe }};
    const values = {{ chart_values|safe }};
    const ctx = document.getElementById('equityChart');
    new Chart(ctx, {
      type: 'line',
      data: {
        labels: labels,
        datasets: [{
          label: 'USDT',
          data: values,
          borderColor: '#f59e0b',
          backgroundColor: 'rgba(245, 158, 11, 0.15)',
          fill: true,
          tension: 0.25,
          pointRadius: 3,
          pointHoverRadius: 4,
          pointBackgroundColor: '#f59e0b',
          pointBorderColor: '#f59e0b'
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false }
        },
        scales: {
          x: {
            grid: { color: '#eef2f7' },
            ticks: { color: '#6b7280' }
          },
          y: {
            grid: { color: '#eef2f7' },
            ticks: { color: '#6b7280' }
          }
        }
      }
    });
    setTimeout(() => window.location.reload(), 30000);
  </script>
</body>
</html>
"""


def fmt_num(v, suffix=""):
    try:
        return f"{float(v):.6f}{suffix}"
    except Exception:
        return "-"


def fmt_signed_num(v, suffix=""):
    try:
        x = float(v)
        if x > 0:
            return f"▲ +{x:.6f}{suffix}"
        if x < 0:
            return f"▼ {x:.6f}{suffix}"
        return f"• {x:.6f}{suffix}"
    except Exception:
        return "-"


def fmt_pct(v):
    try:
        return f"{float(v) * 100:.1f}%"
    except Exception:
        return "-"


def css_class(v):
    try:
        x = float(v)
    except Exception:
        return "neutral"
    if x > 0:
        return "good"
    if x < 0:
        return "bad"
    return "neutral"


def position_text(position):
    if position == "LONG":
        return "Compró"
    if position == "SHORT":
        return "Vendió"
    return "Sin posición"


def market_text(regime):
    return regime if regime else "RANGE"


def coin_logo_url(symbol: str) -> str:
    base = (symbol or "").replace("USDT", "").replace("BUSD", "").replace("USDC", "").lower()
    mapping = {
        "btc": "https://raw.githubusercontent.com/spothq/cryptocurrency-icons/master/32/color/btc.png",
        "eth": "https://raw.githubusercontent.com/spothq/cryptocurrency-icons/master/32/color/eth.png",
        "bnb": "https://raw.githubusercontent.com/spothq/cryptocurrency-icons/master/32/color/bnb.png",
        "ada": "https://raw.githubusercontent.com/spothq/cryptocurrency-icons/master/32/color/ada.png",
        "xrp": "https://raw.githubusercontent.com/spothq/cryptocurrency-icons/master/32/color/xrp.png",
        "sol": "https://raw.githubusercontent.com/spothq/cryptocurrency-icons/master/32/color/sol.png",
        "dot": "https://raw.githubusercontent.com/spothq/cryptocurrency-icons/master/32/color/dot.png",
    }
    return mapping.get(base, f"https://cryptoicons.org/api/icon/{base}/32")


@app.route("/health")
def health():
    return jsonify({"ok": True, "time": datetime.utcnow().isoformat() + "Z"})


@app.route("/api/monitor-state")
def api_monitor_state():
    return jsonify(load_state())


@app.route("/update", methods=["POST"])
def update_monitor():
    if not token_ok(request):
        return jsonify({"ok": False, "error": "unauthorized"}), 401

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"ok": False, "error": "invalid json"}), 400

    save_state(payload)
    return jsonify({"ok": True, "saved": True, "bots": len(payload.get("bots", []))})


@app.route("/")
def dashboard():
    state = load_state()
    summary = state.get("summary", {}) if isinstance(state, dict) else {}
    bots = state.get("bots", []) if isinstance(state, dict) else []
    quote = state.get("quote", "USDT") if isinstance(state, dict) else "USDT"

    bots_sorted = sorted(bots, key=lambda x: (x or {}).get("symbol", ""))
    safe_bots = []
    pnl_values = []
    wins_positive = 0
    losses_positive = 0

    for bot in bots_sorted:
        bot = bot or {}
        last_trade = bot.get("last_trade") or {}
        pnl_24h = float(bot.get("pnl_24h", 0) or 0)
        win_rate_24h = float(bot.get("win_rate_24h", 0) or 0)
        closed_24h = bot.get("closed_trades_24h", 0) or 0
        last_price = last_trade.get("price")

        if pnl_24h > 0:
            wins_positive += 1
        elif pnl_24h < 0:
            losses_positive += 1
        pnl_values.append((bot.get("symbol", "-"), pnl_24h))

        safe_bots.append({
            "symbol": bot.get("symbol", "-"),
            "logo_url": coin_logo_url(bot.get("symbol", "-")),
            "price_text": fmt_num(last_price) if last_price not in (None, "") else "-",
            "market_text": market_text(bot.get("regime")),
            "position_text": position_text(bot.get("position")),
            "pnl_24h_text": fmt_signed_num(pnl_24h, f" {quote}"),
            "pnl_class": css_class(pnl_24h),
            "closed_trades_24h": closed_24h,
            "win_rate_text": fmt_pct(win_rate_24h),
            "win_rate_class": 'magenta',
            "last_trade": {
                "side": last_trade.get("side"),
                "time": last_trade.get("time", "-"),
                "price": fmt_num(last_trade.get("price")),
                "qty": fmt_num(last_trade.get("qty")),
            } if last_trade else None,
        })

    max_abs = max([abs(v) for _, v in pnl_values], default=0)
    pnl_bars = []
    for symbol, value in pnl_values:
        width = 8 if max_abs == 0 else max(8, round(abs(value) / max_abs * 100, 1))
        pnl_bars.append({
            "symbol": symbol,
            "width": width,
            "text": fmt_signed_num(value, f" {quote}"),
        })

    total_scored = wins_positive + losses_positive
    wins_pct = round((wins_positive / total_scored) * 100, 1) if total_scored else 0.0
    losses_pct = round(100 - wins_pct, 1) if total_scored else 0.0

    bal = float(state.get("balance_estimated", 0) or 0) if isinstance(state, dict) else 0.0
    p24 = float(summary.get("pnl_24h", 0) or 0)
    p7 = float(summary.get("pnl_7d", 0) or 0)
    p30 = float(summary.get("pnl_30d", 0) or 0)

    now_dt = None
    ts = state.get("timestamp") if isinstance(state, dict) else None
    if ts:
        try:
            now_dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
        except Exception:
            now_dt = datetime.now()
    else:
        now_dt = datetime.now()

    chart_values = [round(bal - p30, 6), round(bal - p7, 6), round(bal - p24, 6), round(bal, 6)]
    chart_dates = [
        (now_dt - timedelta(days=3)).strftime("%d/%m"),
        (now_dt - timedelta(days=2)).strftime("%d/%m"),
        (now_dt - timedelta(days=1)).strftime("%d/%m"),
        now_dt.strftime("%d/%m"),
    ]

    return render_template_string(
        HTML_TEMPLATE,
        updated_at=state.get("timestamp") if isinstance(state, dict) else None,
        balance=f"{fmt_num(state.get('balance_estimated', 0))} {quote}" if isinstance(state, dict) else f"0.000000 {quote}",
        pnl24=fmt_signed_num(summary.get("pnl_24h", 0), f" {quote}"),
        pnl24_class=css_class(summary.get("pnl_24h", 0)),
        pnl7=fmt_signed_num(summary.get("pnl_7d", 0), f" {quote}"),
        pnl7_class=css_class(summary.get("pnl_7d", 0)),
        pnl30=fmt_signed_num(summary.get("pnl_30d", 0), f" {quote}"),
        pnl30_class=css_class(summary.get("pnl_30d", 0)),
        closed_trades_24h=summary.get("closed_trades_24h", 0),
        win_rate_24h=fmt_pct(summary.get("win_rate_24h", 0)),
        profit_factor_24h=fmt_num(summary.get("profit_factor_24h", 0)),
        fees_24h=fmt_signed_num(-(float(summary.get("fees_24h", 0) or 0)), f" {quote}"),
        closed_trades_7d=summary.get("closed_trades_7d", "-"),
        win_rate_7d=fmt_pct(summary.get("win_rate_7d")) if summary.get("win_rate_7d") is not None else "-",
        profit_factor_7d=fmt_num(summary.get("profit_factor_7d")) if summary.get("profit_factor_7d") is not None else "-",
        fees_7d=fmt_signed_num(-(float(summary.get("fees_7d", 0) or 0)), f" {quote}") if summary.get("fees_7d") is not None else "-",
        closed_trades_30d=summary.get("closed_trades_30d", "-"),
        win_rate_30d=fmt_pct(summary.get("win_rate_30d")) if summary.get("win_rate_30d") is not None else "-",
        profit_factor_30d=fmt_num(summary.get("profit_factor_30d")) if summary.get("profit_factor_30d") is not None else "-",
        fees_30d=fmt_signed_num(-(float(summary.get("fees_30d", 0) or 0)), f" {quote}") if summary.get("fees_30d") is not None else "-",
        bots=safe_bots,
        pnl_bars=pnl_bars,
        wins_pct=wins_pct,
        wins_pct_text=f"{wins_pct:.1f}%",
        losses_pct=losses_pct,
        losses_pct_text=f"{losses_pct:.1f}%",
        chart_labels=json.dumps(chart_dates),
        chart_values=json.dumps(chart_values),
        chart_year=now_dt.strftime("%Y"),
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
