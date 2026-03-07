from flask import Flask, jsonify, request, render_template_string
import json
import os
from datetime import datetime

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
  <title>Monitor de Bots</title>
  <style>
    :root {
      --bg: #0b0f14;
      --panel: #111821;
      --panel-2: #17212b;
      --text: #e8eef5;
      --muted: #99a7b5;
      --good: #27c93f;
      --bad: #ff5f56;
      --warn: #f7c948;
      --line: #253240;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: Arial, Helvetica, sans-serif;
      padding: 24px;
    }
    .wrap {
      max-width: 1200px;
      margin: 0 auto;
    }
    h1 {
      margin: 0 0 8px;
      font-size: 30px;
    }
    .sub {
      color: var(--muted);
      margin-bottom: 20px;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
      margin-bottom: 18px;
    }
    .card {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 14px;
    }
    .label {
      color: var(--muted);
      font-size: 13px;
      margin-bottom: 8px;
    }
    .value {
      font-size: 24px;
      font-weight: 700;
    }
    .good { color: var(--good); }
    .bad { color: var(--bad); }
    .neutral { color: var(--text); }
    table {
      width: 100%;
      border-collapse: collapse;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 14px;
      overflow: hidden;
    }
    th, td {
      padding: 12px 10px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      font-size: 14px;
      vertical-align: top;
    }
    th {
      background: var(--panel-2);
      color: var(--muted);
      font-weight: 700;
    }
    tr:hover td {
      background: #131c25;
    }
    .pill {
      display: inline-block;
      padding: 4px 8px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 700;
      border: 1px solid var(--line);
    }
    .pill-buy { color: var(--good); }
    .pill-sell { color: var(--bad); }
    .muted { color: var(--muted); }
    .footer {
      margin-top: 12px;
      color: var(--muted);
      font-size: 12px;
    }
    @media (max-width: 800px) {
      body { padding: 14px; }
      th, td { font-size: 12px; padding: 10px 8px; }
      .value { font-size: 20px; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <h1>Monitor de Bots</h1>
    <div class="sub">Última actualización: {{ updated_at or 'Sin datos' }}</div>

    <div class="grid">
      <div class="card">
        <div class="label">Balance estimado</div>
        <div class="value">{{ balance }}</div>
      </div>
      <div class="card">
        <div class="label">PnL 24h</div>
        <div class="value {{ pnl24_class }}">{{ pnl24 }}</div>
      </div>
      <div class="card">
        <div class="label">PnL 7d</div>
        <div class="value {{ pnl7_class }}">{{ pnl7 }}</div>
      </div>
      <div class="card">
        <div class="label">PnL 30d</div>
        <div class="value {{ pnl30_class }}">{{ pnl30 }}</div>
      </div>
      <div class="card">
        <div class="label">Closed trades 24h</div>
        <div class="value">{{ closed_trades }}</div>
      </div>
      <div class="card">
        <div class="label">Win rate 24h</div>
        <div class="value">{{ win_rate }}</div>
      </div>
      <div class="card">
        <div class="label">Profit factor 24h</div>
        <div class="value">{{ profit_factor }}</div>
      </div>
      <div class="card">
        <div class="label">Fees 24h</div>
        <div class="value">{{ fees_24h }}</div>
      </div>
    </div>

    <table>
      <thead>
        <tr>
          <th>Moneda</th>
          <th>Ready</th>
          <th>Regime</th>
          <th>Posición</th>
          <th>PnL 24h</th>
          <th>Closed</th>
          <th>Win Rate</th>
          <th>Última operación</th>
        </tr>
      </thead>
      <tbody>
        {% for bot in bots %}
        <tr>
          <td><strong>{{ bot.symbol }}</strong></td>
          <td>{{ bot.ready }}</td>
          <td>{{ bot.regime }}</td>
          <td>{{ bot.position }}</td>
          <td class="{{ 'good' if (bot.pnl_24h or 0) > 0 else 'bad' if (bot.pnl_24h or 0) < 0 else 'neutral' }}">{{ bot.pnl_24h_text }}</td>
          <td>{{ bot.closed_trades_24h }}</td>
          <td>{{ bot.win_rate_text }}</td>
          <td>
            {% if bot.last_trade and bot.last_trade.side %}
              <span class="pill {{ 'pill-buy' if bot.last_trade.side == 'COMPRA' else 'pill-sell' }}">{{ bot.last_trade.side }}</span><br>
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

    <div class="footer">Auto refresh: 30 segundos</div>
  </div>
  <script>
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

    safe_bots = []
    for bot in bots:
        bot = bot or {}
        last_trade = bot.get("last_trade") or {}
        safe_bots.append({
            "symbol": bot.get("symbol", "-"),
            "ready": bot.get("ready", "-"),
            "regime": bot.get("regime", "-"),
            "position": bot.get("position", "-"),
            "pnl_24h": bot.get("pnl_24h", 0),
            "pnl_24h_text": fmt_num(bot.get("pnl_24h", 0), f" {quote}"),
            "closed_trades_24h": bot.get("closed_trades_24h", 0),
            "win_rate_text": fmt_pct(bot.get("win_rate_24h", 0)),
            "last_trade": {
                "side": last_trade.get("side"),
                "time": last_trade.get("time", "-"),
                "price": fmt_num(last_trade.get("price")),
                "qty": fmt_num(last_trade.get("qty")),
            } if last_trade else None,
        })

    return render_template_string(
        HTML_TEMPLATE,
        updated_at=state.get("timestamp") if isinstance(state, dict) else None,
        balance=f"{fmt_num(state.get('balance_estimated', 0))} {quote}" if isinstance(state, dict) else f"0.000000 {quote}",
        pnl24=fmt_num(summary.get("pnl_24h", 0), f" {quote}"),
        pnl24_class=css_class(summary.get("pnl_24h", 0)),
        pnl7=fmt_num(summary.get("pnl_7d", 0), f" {quote}"),
        pnl7_class=css_class(summary.get("pnl_7d", 0)),
        pnl30=fmt_num(summary.get("pnl_30d", 0), f" {quote}"),
        pnl30_class=css_class(summary.get("pnl_30d", 0)),
        closed_trades=summary.get("closed_trades_24h", 0),
        win_rate=fmt_pct(summary.get("win_rate_24h", 0)),
        profit_factor=fmt_num(summary.get("profit_factor_24h", 0)),
        fees_24h=fmt_num(summary.get("fees_24h", 0), f" {quote}"),
        bots=safe_bots,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
