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
        except:
            return {}
    return {}


def save_state(payload):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def token_ok(req):
    if not MONITOR_TOKEN:
        return True
    return req.headers.get("X-Monitor-Token", "") == MONITOR_TOKEN


HTML = """
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>ALPHA MONITOR</title>
<style>

body{
font-family:Arial;
background:#ffffff;
margin:30px;
}

h1{
margin-bottom:10px;
}

table{
border-collapse:collapse;
width:100%;
margin-top:20px;
}

th,td{
border:2px solid #000;
padding:8px;
text-align:center;
}

thead{
background:#eeeeee;
}

.sub{
font-size:12px;
color:#666;
}

</style>
</head>

<body>

<h1>ALPHA MONITOR</h1>
<div class="sub">Actualizado: {{updated_at}}</div>


<table>

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

{% for r in rows %}

<tr>

<td>{{r.symbol}}</td>

<td>{{r.win24}}</td>
<td>{{r.win7}}</td>
<td>{{r.win30}}</td>

<td>{{r.loss24}}</td>
<td>{{r.loss7}}</td>
<td>{{r.loss30}}</td>

</tr>

{% endfor %}

</tbody>

</table>


</body>
</html>
"""


@app.route("/update", methods=["POST"])
def update():

    if not token_ok(request):
        return {"ok": False}

    payload = request.get_json()
    save_state(payload)

    return {"ok": True}


@app.route("/")
def dashboard():

    state = load_state()

    bots = state.get("bots", [])
    rows = []

    for b in bots:

        symbol = b.get("symbol","-")

        ct24 = b.get("closed_trades_24h",0)
        wr24 = b.get("win_rate_24h",0)

        ct7 = b.get("closed_trades_7d",0)
        wr7 = b.get("win_rate_7d",0)

        ct30 = b.get("closed_trades_30d",0)
        wr30 = b.get("win_rate_30d",0)

        win24 = round(ct24*wr24)
        loss24 = ct24-win24

        win7 = round(ct7*wr7)
        loss7 = ct7-win7

        win30 = round(ct30*wr30)
        loss30 = ct30-win30

        rows.append({

        "symbol":symbol,

        "win24":win24,
        "win7":win7,
        "win30":win30,

        "loss24":loss24,
        "loss7":loss7,
        "loss30":loss30

        })


    return render_template_string(
        HTML,
        rows=rows,
        updated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0",port=10000)
