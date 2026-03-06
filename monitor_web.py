from flask import Flask, jsonify
import json
import os

app = Flask(__name__)

def load_bot_state(symbol):
    file = f"{symbol}_bot_state.json"
    if os.path.exists(file):
        with open(file) as f:
            return json.load(f)
    return {}

@app.route("/")
def dashboard():

    symbols = ["BTCUSDT","ETHUSDT","ADAUSDT","BNBUSDT"]

    data = []

    for s in symbols:
        st = load_bot_state(s)

        data.append({
            "symbol": s,
            "ready": st.get("ready"),
            "regime": st.get("regime"),
            "position": st.get("in_position")
        })

    return jsonify(data)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)