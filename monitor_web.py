from flask import Flask, jsonify, request, render_template_string
import json
import os
from datetime import datetime, timedelta

app = Flask(__name__)

HISTORY_FILE = "balance_history.json"
STATE_FILE = "render_monitor_state.json"
HISTORY_FILE = "balance_history.json"
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

def save_balance_history(balance, timestamp):

    if not timestamp:
        return

    today = timestamp[:10]  # YYYY-MM-DD
    history = []

    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
        except:
            history = []

    # solo guardar un punto por día
    for h in history:
        if h.get("time", "")[:10] == today:
            return

    history.append({
        "time": timestamp,
        "balance": balance
    })

    # máximo 365 días de histórico
    history = history[-365:]

    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
        
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
    }
    .good { color: #16a34a; }
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
      margin-bottom: 10px;
    }
    .coin-meta {
      display: grid;
      gap: 4px;
      line-height: 1.25;
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

    .col-compact {
      text-align: center;
    }
    .col-metric {
      padding-left: 8px;
      padding-right: 8px;
    }
    .last-op {
      line-height: 1.3;
    }
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
      grid-template-columns: 90px 1fr 140px;
      gap: 12px;
      align-items: center;
      margin-bottom: 14px;
      font-size: 14px;
    }
    .bar-row > div:last-child {
      justify-self: end;
      min-width: 0;
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

    .bar-fill-positive {
      background: linear-gradient(90deg, #22c55e, #16a34a);
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
    .chart-year-bottom {
      font-weight: 700;
      font-size: 12px;
      color: #374151;
      margin-top: 4px;
    }
    .chart-wrap {
      height: 220px;
      position: relative;
    }

    .results-summary-table {
      width: 100%;
      border-collapse: collapse;
      table-layout: fixed;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 12px;
      overflow: hidden;
      box-shadow: none;
    }
    .results-summary-table thead th {
      background: #f3f4f6;
      color: #374151;
      font-weight: 700;
      font-size: 13px;
      text-align: center;
      border: 1px solid var(--line);
      padding: 10px 8px;
    }
    .results-summary-table td {
      padding: 12px 10px;
      text-align: center;
      font-size: 14px;
      border-top: 1px solid var(--line);
      border-left: none;
      border-right: none;
      border-bottom: none;
      background: var(--panel);
    }
    .results-summary-table tbody tr:hover td {
      background: var(--panel-2);
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
    /* tabla resultados por moneda */

    .results-table-bottom{
      width:100%;
      margin-top:18px;
      border-collapse:separate;
      border-spacing:0;
      border-radius:14px;
      overflow:hidden;
      background:var(--panel);
    }

    .results-table-bottom thead th{
      background:var(--head);
      color:var(--text);
      font-weight:600;
      font-size:13px;
      padding:10px 12px;
      text-align:center;
      border:none;
    }

    .results-table-bottom tbody td{
      padding:12px;
      text-align:center;
      border-top:1px solid var(--line);
      border-left:none;
      border-right:none;
      border-bottom:none;
    }

    .results-table-bottom tbody tr:hover td{
      background:var(--panel-2);
    }

    .coin-cell{
      display:flex;
      align-items:center;
      gap:8px;
    }

    .coin-icon{
      width:18px;
      height:18px;
    }

    .results-table-bottom .mono{
      font-family:monospace;
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
        <div class="label">Balance Estimado</div>
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
        <div class="value mono {{ win_rate_24h_class }}">{{ win_rate_24h }}</div>
      </div>
      <div class="card">
        <div class="label">Profit Factor 24h</div>
        <div class="value mono {{ profit_factor_24h_class }}">{{ profit_factor_24h }}</div>
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
        <div class="value mono {{ win_rate_7d_class }}">{{ win_rate_7d }}</div>
      </div>
      <div class="card">
        <div class="label">Profit Factor 7d</div>
        <div class="value mono {{ profit_factor_7d_class }}">{{ profit_factor_7d }}</div>
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
        <div class="value mono {{ win_rate_30d_class }}">{{ win_rate_30d }}</div>        
      </div>
      <div class="card">
        <div class="label">Profit Factor 30d</div>
        <div class="value mono {{ profit_factor_30d_class }}">{{ profit_factor_30d }}</div>
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
          <th class="col-metric" style="width:14%;">PnL 24h</th>
          <th class="col-metric" style="width:12%;">FEE24h</th>
          <th class="col-compact" style="width:6%;">CT</th>
          <th class="col-compact" style="width:6%;">WR</th>
          <th class="col-compact" style="width:6%;">PF</th>
          <th class="col-metric" style="width:10%;">AVG</th>
          <th class="col-metric" style="width:12%;">Expectancy</th>
          <th style="width:18%;">Ultima Operación</th>
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
            <div class="coin-meta">
              <div class="mono muted">{{ bot.price_text }}</div>
              <div class="muted">{{ bot.market_text }}</div>
              <div>{{ bot.position_text }}</div>
            </div>
          </td>
          <td class="mono col-metric {{ bot.pnl_class }}">{{ bot.pnl_24h_text }}</td>
          <td class="mono col-metric magenta">{{ bot.fees_24h_text }}</td>
          <td class="mono col-compact">{{ bot.closed_trades_24h }}</td>
          <td class="mono col-compact {{ bot.win_rate_class }}">{{ bot.win_rate_text }}</td>
          <td class="mono col-compact {{ bot.profit_factor_class }}">{{ bot.profit_factor_text }}</td>
          <td class="mono col-metric {{ bot.avg_trade_class }}">{{ bot.avg_trade_text }}</td>
          <td class="mono col-metric {{ bot.expectancy_class }}">{{ bot.expectancy_text }}</td>
          <td class="last-op">
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
</table>

    <div class="table-block">

    <table class="main-table results-table-bottom">

    <thead>
    <tr>
    <th rowspan="2">Moneda</th>
    <th colspan="3">Ganadas</th>
    <th colspan="3">Perdidas</th>
    </tr>

    <tr>
    <th>24h</th>
    <th>7d</th>
    <th>30d</th>
    <th>24h</th>
    <th>7d</th>
    <th>30d</th>
    </tr>

    </thead>

    <tbody>

    {% for bot in bots %}
    <tr>

    <td>
      <div class="coin-cell">
        <img
          src="https://cryptoicons.org/api/icon/{{ bot.symbol[:-4]|lower }}/32"
          alt="{{ bot.symbol }}"
          class="coin-icon"
          onerror="this.style.display='none'; this.nextElementSibling.style.marginLeft='0';"
        >
        <strong>{{ bot.symbol }}</strong>
      </div>
    </td>

    <td class="mono">{{ bot.wins_24h }}</td>
    <td class="mono">{{ bot.wins_7d }}</td>
    <td class="mono">{{ bot.wins_30d }}</td>

    <td class="mono">{{ bot.losses_24h }}</td>
    <td class="mono">{{ bot.losses_7d }}</td>
    <td class="mono">{{ bot.losses_30d }}</td>

    </tr>
    {% endfor %}

    </tbody>
    </table>

    </div>
    <div class="panels-row">
      <div class="mini-panel">
        <div class="mini-title">Efectividad 24h</div>
        <div class="bar-row">
          <div>Ganadas ({{ wins_count }})</div>
          <div class="bar-track"><div class="bar-fill" style="width: {{ wins_pct }}%;"></div></div>
          <div class="mono {{ wins_pct_class }}">{{ wins_pct_text }}</div>
        </div>
        <div class="bar-row">
          <div>Perdidas ({{ losses_count }})</div>
          <div class="bar-track"><div class="bar-fill" style="width: {{ losses_pct }}%;"></div></div>
          <div class="mono {{ losses_pct_class }}">{{ losses_pct_text }}</div>
        </div>
      </div>
    </div>

    <div class="chart-panel">
      <div class="chart-head">
        <div class="chart-title">Evolución Estimada (USDT)</div>
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
            ticks: {
              color: '#6b7280',
              maxRotation: 0,
              minRotation: 0,
              autoSkip: true,
              maxTicksLimit: 6,
              callback: function(value, index) {
                const label = this.getLabelForValue(value);
                if (index === 0) {
                  return "{{ chart_year }}   " + label;
                }
                return label;
              }
            }
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

def metric_threshold_class(v, threshold):
    try:
        x = float(v)
    except Exception:
        return "magenta"
    return "good" if x >= threshold else "magenta"

def position_text(position):
    if position == "LONG":
        return "Posición Abierta"
    if position == "SHORT":
        return "Posición Corta"
    return "Sin Posición"


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

    save_balance_history(
        payload.get("balance_estimated", 0),
        payload.get("timestamp")
    )

    return jsonify({
    "ok": True,
    "saved": True,
    "bots": len(payload.get("bots", []))
    })
@app.route("/")
def dashboard():
    state = load_state()
    summary = state.get("summary", {}) if isinstance(state, dict) else {}
    bots = state.get("bots", []) if isinstance(state, dict) else []
    quote = state.get("quote", "USDT") if isinstance(state, dict) else "USDT"

    bots_sorted = sorted(bots, key=lambda x: (x or {}).get("symbol", ""))
    safe_bots = []
    pnl_values = []

    for bot in bots_sorted:
        bot = bot or {}
        last_trade = bot.get("last_trade") or {}
        pnl_24h = float(bot.get("pnl_24h", 0) or 0)
        win_rate_24h = float(bot.get("win_rate_24h", 0) or 0)
        closed_24h = bot.get("closed_trades_24h", 0) or 0
        last_price = last_trade.get("price")

        pnl_values.append((bot.get("symbol", "-"), pnl_24h))

        pnl_7d = float(bot.get("pnl_7d", 0) or 0)
        pnl_30d = float(bot.get("pnl_30d", 0) or 0)
        fees_24h = float(bot.get("fees_24h", 0) or 0)
        profit_factor_24h = float(bot.get("profit_factor_24h", 0) or 0)
        avg_trade_24h = float(bot.get("avg_trade_24h", bot.get("avg_trade", 0)) or 0)
        expectancy_24h = float(bot.get("expectancy_24h", bot.get("expectancy", 0)) or 0)

        closed_7d = int(bot.get("closed_trades_7d", 0) or 0)
        closed_30d = int(bot.get("closed_trades_30d", 0) or 0)
        win_rate_7d = float(bot.get("win_rate_7d", 0) or 0)
        win_rate_30d = float(bot.get("win_rate_30d", 0) or 0)

        wins_24h = round(closed_24h * win_rate_24h)
        losses_24h = max(0, closed_24h - wins_24h)
        wins_7d = round(closed_7d * win_rate_7d)
        losses_7d = max(0, closed_7d - wins_7d)
        wins_30d = round(closed_30d * win_rate_30d)
        losses_30d = max(0, closed_30d - wins_30d)

        safe_bots.append({
            "symbol": bot.get("symbol", "-"),
            "wins_24h": wins_24h,
            "wins_7d": wins_7d,
            "wins_30d": wins_30d,
            "losses_24h": losses_24h,
            "losses_7d": losses_7d,
            "losses_30d": losses_30d,
            "logo_url": coin_logo_url(bot.get("symbol", "-")),
            "price_text": fmt_num(last_price) if last_price not in (None, "") else "-",
            "market_text": market_text(bot.get("regime")),
            "position_text": position_text(bot.get("position")),
            "pnl_24h_text": fmt_signed_num(pnl_24h, f" {quote}"),
            "pnl_class": css_class(pnl_24h),
            "pnl_7d_text": fmt_signed_num(pnl_7d, f" {quote}"),
            "pnl_7d_class": css_class(pnl_7d),
            "pnl_30d_text": fmt_signed_num(pnl_30d, f" {quote}"),
            "pnl_30d_class": css_class(pnl_30d),
            "fees_24h_text": fmt_signed_num(-fees_24h, f" {quote}"),
            "closed_trades_24h": closed_24h,
            "win_rate_text": fmt_pct(win_rate_24h),
            "win_rate_class": metric_threshold_class(win_rate_24h * 100, 60),
            "profit_factor_text": fmt_num(profit_factor_24h),
            "profit_factor_class": metric_threshold_class(profit_factor_24h, 1.5),
            "avg_trade_text": fmt_signed_num(avg_trade_24h, f" {quote}"),
            "avg_trade_class": css_class(avg_trade_24h),
            "expectancy_text": fmt_signed_num(expectancy_24h, f" {quote}"),
            "expectancy_class": css_class(expectancy_24h),
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
            "bar_class": "bar-fill-positive" if value > 0 else "",
        })

    closed_total = int(summary.get("closed_trades_24h", 0) or 0)
    win_rate = float(summary.get("win_rate_24h", 0) or 0)

    wins_count = round(closed_total * win_rate)
    losses_count = max(0, closed_total - wins_count)

    wins_pct = round((wins_count / closed_total) * 100, 1) if closed_total else 0.0
    losses_pct = round((losses_count / closed_total) * 100, 1) if closed_total else 0.0

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

    chart_values = []
    chart_dates = []

    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE) as f:
                history = json.load(f)

            for h in history[-120:]:  # últimos 120 puntos
                chart_values.append(h["balance"])
                try:
                    dt = datetime.strptime(h["time"][:10], "%Y-%m-%d")
                    chart_dates.append(dt.strftime("%m/%d"))
                except Exception:
                    dt = datetime.strptime(h["time"][:10], "%Y-%m-%d")
                    chart_dates.append(dt.strftime("%m/%d"))

        except:
            chart_values = [bal]  
            chart_dates = [now_dt.strftime("%m/%d")]
    else:
        chart_values = [bal]
        chart_dates = [now_dt.strftime("%d/%m")]

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
        wins_count=wins_count,
        losses_count=losses_count,
        win_rate_24h=fmt_pct(summary.get("win_rate_24h", 0)),
        win_rate_24h_class=metric_threshold_class((float(summary.get("win_rate_24h", 0) or 0) * 100), 45),
        profit_factor_24h=fmt_num(summary.get("profit_factor_24h", 0)),
        profit_factor_24h_class=metric_threshold_class(summary.get("profit_factor_24h", 0), 1.5),
        fees_24h=fmt_signed_num(-(float(summary.get("fees_24h", 0) or 0)), f" {quote}"),
        closed_trades_7d=summary.get("closed_trades_7d", "-"),
        win_rate_7d=fmt_pct(summary.get("win_rate_7d")) if summary.get("win_rate_7d") is not None else "-",
        win_rate_7d_class=metric_threshold_class((float(summary.get("win_rate_7d", 0) or 0) * 100), 45) if summary.get("win_rate_7d") is not None else "magenta",
        profit_factor_7d=fmt_num(summary.get("profit_factor_7d")) if summary.get("profit_factor_7d") is not None else "-",
        profit_factor_7d_class=metric_threshold_class(summary.get("profit_factor_7d", 0), 1.5) if summary.get("profit_factor_7d") is not None else "magenta",
        fees_7d=fmt_signed_num(-(float(summary.get("fees_7d", 0) or 0)), f" {quote}") if summary.get("fees_7d") is not None else "-",
        closed_trades_30d=summary.get("closed_trades_30d", "-"),
        win_rate_30d=fmt_pct(summary.get("win_rate_30d")) if summary.get("win_rate_30d") is not None else "-",
        win_rate_30d_class=metric_threshold_class((float(summary.get("win_rate_30d", 0) or 0) * 100), 45) if summary.get("win_rate_30d") is not None else "magenta",
        profit_factor_30d=fmt_num(summary.get("profit_factor_30d")) if summary.get("profit_factor_30d") is not None else "-",
        profit_factor_30d_class=metric_threshold_class(summary.get("profit_factor_30d", 0), 1.5) if summary.get("profit_factor_30d") is not None else "magenta",
        fees_30d=fmt_signed_num(-(float(summary.get("fees_30d", 0) or 0)), f" {quote}") if summary.get("fees_30d") is not None else "-",
        bots=safe_bots,
        pnl_bars=pnl_bars,
        wins_pct=wins_pct,
        wins_pct_text=f"{wins_pct:.1f}%",
        wins_pct_class=metric_threshold_class(wins_pct, 60),
        losses_pct=losses_pct,
        losses_pct_text=f"{losses_pct:.1f}%",
        losses_pct_class="good" if losses_pct < 40 else "magenta",
        chart_labels=json.dumps(chart_dates),
        chart_values=json.dumps(chart_values),
        chart_year=now_dt.strftime("%Y"),
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
