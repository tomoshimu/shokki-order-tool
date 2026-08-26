import os, secrets, requests, csv, io
from flask import Flask, request, redirect, session, render_template, jsonify, Response

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))

API_KEY    = os.environ.get("SHOPIFY_API_KEY", "")
API_SECRET = os.environ.get("SHOPIFY_API_SECRET", "")
SCOPES     = "read_orders"

# ---------- Shopify接続 ----------

def get_token(shop):
    """ショップのアクセストークンを返す（環境変数優先）"""
    return os.environ.get("SHOPIFY_ACCESS_TOKEN", "")

def graphql(shop, token, query):
    r = requests.post(
        f"https://{shop}/admin/api/2024-01/graphql.json",
        json={"query": query},
        headers={"X-Shopify-Access-Token": token, "Content-Type": "application/json"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()

# ---------- 定数 ----------

ORDERS_GQL = """
{{
  orders(first: {count}, sortKey: CREATED_AT, reverse: true, query: "fulfillment_status:unfulfilled status:open") {{
    edges {{
      node {{
        name
        createdAt
        shippingAddress {{ firstName lastName zip province city address1 address2 phone }}
        lineItems(first: 20) {{
          edges {{ node {{ title quantity currentQuantity customAttributes {{ key value }} }} }}
        }}
      }}
    }}
  }}
}}
"""

CLICKPOST_GQL = """
{{
  orders(first: {count}, sortKey: CREATED_AT, reverse: true, query: "status:open") {{
    edges {{
      node {{
        name
        createdAt
        shippingAddress {{ firstName lastName zip province city address1 address2 phone }}
        lineItems(first: 20) {{
          edges {{ node {{ title quantity currentQuantity customAttributes {{ key value }} }} }}
        }}
      }}
    }}
  }}
}}
"""

CLICKPOST_GQL = """
{{
  orders(first: {{count}}, sortKey: CREATED_AT, reverse: true, query: "fulfillment_status:unshipped status:open") {{
    edges {{
      node {{
        name
        createdAt
        shippingAddress {{ firstName lastName zip province city address1 address2 phone }}
        lineItems(first: 20) {{
          edges {{ node {{ title quantity currentQuantity customAttributes {{ key value }} }} }}
        }}
      }}
    }}
  }}
}}
"""

OPTION_KEYS = ["トップス／ロンパース","ロゴカラー","サイズ","サイズ調整","胸囲","袖丈","着丈","発送方法","備考欄"]

PREF = {
    "Hokkaido":"北海道","Hokkaidō":"北海道","Aomori":"青森県","Iwate":"岩手県","Miyagi":"宮城県","Akita":"秋田県",
    "Yamagata":"山形県","Fukushima":"福島県","Ibaraki":"茨城県","Tochigi":"栃木県","Gunma":"群馬県",
    "Saitama":"埼玉県","Chiba":"千葉県","Tōkyō":"東京都","Tokyo":"東京都","Kanagawa":"神奈川県",
    "Niigata":"新潟県","Toyama":"富山県","Ishikawa":"石川県","Fukui":"福井県","Yamanashi":"山梨県",
    "Nagano":"長野県","Gifu":"岐阜県","Shizuoka":"静岡県","Aichi":"愛知県","Mie":"三重県",
    "Shiga":"滋賀県","Kyōto":"京都府","Kyoto":"京都府","Ōsaka":"大阪府","Osaka":"大阪府",
    "Hyōgo":"兵庫県","Hyogo":"兵庫県","Nara":"奈良県","Wakayama":"和歌山県","Tottori":"鳥取県",
    "Shimane":"島根県","Okayama":"岡山県","Hiroshima":"広島県","Yamaguchi":"山口県","Tokushima":"徳島県",
    "Kagawa":"香川県","Ehime":"愛媛県","Kōchi":"高知県","Kochi":"高知県","Fukuoka":"福岡県",
    "Saga":"佐賀県","Nagasaki":"長崎県","Kumamoto":"熊本県","Ōita":"大分県","Oita":"大分県",
    "Miyazaki":"宮崎県","Kagoshima":"鹿児島県","Okinawa":"沖縄県",
}

def clean_zip(z):   return (z or "").replace("-", "").zfill(7)
def clean_phone(p):
    p = (p or "").replace("+81", "0").replace("-", "").replace(" ", "")
    return p

# ---------- OAuth ----------

@app.route("/")
def index():
    shop = request.args.get("shop", "")
    host = request.args.get("host", "")
    if not shop:
        return "Missing shop parameter", 400
    token = get_token(shop)
    if not token:
        return redirect(f"/install?shop={shop}")
    return render_template("index.html", api_key=API_KEY, host=host, shop=shop)

@app.route("/install")
def install():
    shop = request.args.get("shop", "")
    if not shop:
        return "Missing shop", 400
    state = secrets.token_hex(16)
    session["oauth_state"] = state
    session["oauth_shop"] = shop
    app_url = os.environ.get("APP_URL", request.host_url.rstrip("/"))
    redirect_uri = f"{app_url}/auth/callback"
    return redirect(
        f"https://{shop}/admin/oauth/authorize"
        f"?client_id={API_KEY}&scope={SCOPES}"
        f"&redirect_uri={redirect_uri}&state={state}"
    )

@app.route("/auth/callback")
def auth_callback():
    shop = request.args.get("shop", "")
    code = request.args.get("code", "")
    if not shop or not code:
        return "Invalid callback", 400
    r = requests.post(f"https://{shop}/admin/oauth/access_token", json={
        "client_id": API_KEY, "client_secret": API_SECRET, "code": code,
    })
    token = r.json().get("access_token", "")
    print(f"\n{'='*60}")
    print(f"✅ アクセストークン取得成功！")
    print(f"ショップ: {shop}")
    print(f"SHOPIFY_ACCESS_TOKEN={token}")
    print(f"👆 RenderのEnvironment Variablesにこの値を設定してください")
    print(f"{'='*60}\n")
    session["token"] = token
    session["shop"] = shop
    return render_template("token_saved.html", token=token, shop=shop, api_key=API_KEY)

# ---------- API ----------

def get_orders_data(shop, token, count):
    data = graphql(shop, token, ORDERS_GQL.format(count=count))
    rows = []
    extra_keys = []
    seen_keys = set(OPTION_KEYS)
    for edge in data["data"]["orders"]["edges"]:
        o = edge["node"]
        for li in o["lineItems"]["edges"]:
            item = li["node"]
            attrs = {a["key"].strip(): a["value"] for a in item["customAttributes"]}
            for k in attrs:
                if k not in seen_keys:
                    seen_keys.add(k)
                    extra_keys.append(k)
            for _ in range(item["currentQuantity"]):
                rows.append({
                    "order": o["name"],
                    "date": o["createdAt"][:10],
                    "title": item["title"],
                    "attrs": attrs,
                })
    return rows, extra_keys

@app.route("/api/orders")
def api_orders():
    shop  = request.args.get("shop", "")
    count = request.args.get("count", "50")
    token = get_token(shop) or session.get("token", "")
    rows, extra_keys = get_orders_data(shop, token, count)
    return jsonify({"rows": rows, "extra_keys": extra_keys})

@app.route("/api/clickpost")
def api_clickpost():
    shop  = request.args.get("shop", "")
    count = request.args.get("count", "50")
    token = get_token(shop) or session.get("token", "")
    data  = graphql(shop, token, CLICKPOST_GQL.format(count=count))
    rows  = []
    for edge in data["data"]["orders"]["edges"]:
        o = edge["node"]
        a = o.get("shippingAddress") or {}
        items = "／".join(
            f"{li['node']['title']}×{li['node']['quantity']}"
            for li in o["lineItems"]["edges"]
        )
        rows.append({
            "zip":   clean_zip(a.get("zip", "")),
            "name":  (a.get("lastName") or "") + (a.get("firstName") or ""),
            "pref":  PREF.get(a.get("province", ""), a.get("province", "")),
            "city":  a.get("city", ""),
            "addr1": a.get("address1", ""),
            "addr2": a.get("address2") or "",
            "phone": clean_phone(a.get("phone", "")),
            "items": items,
        })
    return jsonify(rows)

# ---------- ダウンロード ----------

@app.route("/download/orders")
def download_orders():
    shop  = request.args.get("shop", "")
    count = request.args.get("count", "50")
    token = get_token(shop) or session.get("token", "")
    rows, extra_keys = get_orders_data(shop, token, count)
    cols  = ["注文番号","注文日","商品名"] + OPTION_KEYS + extra_keys
    out   = io.StringIO()
    w     = csv.writer(out)
    w.writerow(cols)
    for r in rows:
        w.writerow([
            r["order"], r["date"], r["title"],
            *[r["attrs"].get(k, "") for k in OPTION_KEYS + extra_keys],
        ])
    from datetime import date
    filename = f"未発送注文_{date.today()}.csv"
    return Response(
        out.getvalue().encode("utf-8-sig"),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{requests.utils.quote(filename)}"},
    )

@app.route("/download/clickpost")
def download_clickpost():
    shop     = request.args.get("shop", "")
    count    = request.args.get("count", "50")
    products = request.args.get("products", "")
    token    = get_token(shop) or session.get("token", "")
    data     = graphql(shop, token, CLICKPOST_GQL.format(count=count))
    filter_products = [p.strip() for p in products.split(",") if p.strip()] if products else []
    COLS  = ["お届け先郵便番号","お届け先氏名","お届け先住所1(都道府県)","お届け先住所2(市区町村)",
             "お届け先住所3(番地)","お届け先住所4(建物名等)","お届け先電話番号","内容品","重量(g)"]
    out   = io.StringIO()
    w     = csv.writer(out)
    w.writerow(COLS)
    for edge in data["data"]["orders"]["edges"]:
        o = edge["node"]
        a = o.get("shippingAddress") or {}
        line_titles = [li["node"]["title"] for li in o["lineItems"]["edges"]]
        if filter_products and not any(t in filter_products for t in line_titles):
            continue
        items = "／".join(
            f"{li['node']['title']}×{li['node']['quantity']}"
            for li in o["lineItems"]["edges"]
        )
        w.writerow([
            clean_zip(a.get("zip", "")),
            (a.get("lastName") or "") + (a.get("firstName") or ""),
            PREF.get(a.get("province", ""), a.get("province", "")),
            a.get("city", ""),
            a.get("address1", ""),
            a.get("address2") or "",
            clean_phone(a.get("phone", "")),
            items, "",
        ])
    from datetime import date
    filename = f"クリックポスト_{date.today()}.csv"
    return Response(
        out.getvalue().encode("utf-8-sig"),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{requests.utils.quote(filename)}"},
    )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
