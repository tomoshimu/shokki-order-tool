import os, secrets, requests, csv, io
from flask import Flask, request, redirect, session, render_template, jsonify, Response

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))

API_KEY    = os.environ.get("SHOPIFY_API_KEY", "")
API_SECRET = os.environ.get("SHOPIFY_API_SECRET", "")
SCOPES     = "read_orders"

# ---------- Shopifyæ¥ç¶ ----------

def get_token(shop):
    """ã·ã§ããã®ã¢ã¯ã»ã¹ãã¼ã¯ã³ãè¿ãï¼ç°å¢å¤æ°åªåï¼"""
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

# ---------- å®æ° ----------

ORDERS_GQL = """
{{
  orders(first: {count}, sortKey: CREATED_AT, reverse: true, query: "fulfillment_status:unfulfilled") {{
    edges {{
      node {{
        name
        createdAt
        shippingAddress {{ firstName lastName zip province city address1 address2 phone }}
        lineItems(first: 20) {{
          edges {{ node {{ title quantity customAttributes {{ key value }} }} }}
        }}
      }}
    }}
  }}
}}
"""

OPTION_KEYS = ["ãããã¹ï¼ã­ã³ãã¼ã¹","ã­ã´ã«ã©ã¼","ãµã¤ãº","ãµã¤ãºèª¿æ´","è¸å²","è¢ä¸","çä¸","çºéæ¹æ³","åèæ¬"]

PREF = {
    "Hokkaido":"åæµ·é","Aomori":"éæ£®ç","Iwate":"å²©æç","Miyagi":"å®®åç","Akita":"ç§ç°ç",
    "Yamagata":"å±±å½¢ç","Fukushima":"ç¦å³¶ç","Ibaraki":"è¨åç","Tochigi":"æ æ¨ç","Gunma":"ç¾¤é¦¬ç",
    "Saitama":"å¼çç","Chiba":"åèç","TÅkyÅ":"æ±äº¬é½","Tokyo":"æ±äº¬é½","Kanagawa":"ç¥å¥å·ç",
    "Niigata":"æ°æ½ç","Toyama":"å¯å±±ç","Ishikawa":"ç³å·ç","Fukui":"ç¦äºç","Yamanashi":"å±±æ¢¨ç",
    "Nagano":"é·éç","Gifu":"å²éç","Shizuoka":"éå²¡ç","Aichi":"æç¥ç","Mie":"ä¸éç",
    "Shiga":"æ»è³ç","KyÅto":"äº¬é½åº","Kyoto":"äº¬é½åº","Åsaka":"å¤§éªåº","Osaka":"å¤§éªåº",
    "HyÅgo":"åµåº«ç","Hyogo":"åµåº«ç","Nara":"å¥è¯ç","Wakayama":"åæ­å±±ç","Tottori":"é³¥åç",
    "Shimane":"å³¶æ ¹ç","Okayama":"å²¡å±±ç","Hiroshima":"åºå³¶ç","Yamaguchi":"å±±å£ç","Tokushima":"å¾³å³¶ç",
    "Kagawa":"é¦å·ç","Ehime":"æåªç","KÅchi":"é«ç¥ç","Kochi":"é«ç¥ç","Fukuoka":"ç¦å²¡ç",
    "Saga":"ä½è³ç","Nagasaki":"é·å´ç","Kumamoto":"çæ¬ç","Åita":"å¤§åç","Oita":"å¤§åç",
    "Miyazaki":"å®®å´ç","Kagoshima":"é¹¿åå³¶ç","Okinawa":"æ²ç¸ç",
}

def clean_zip(z):   return (z or "").replace("-", "")
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
    # åå¾ãããã¼ã¯ã³ãã­ã°ã«åºå â Renderã®ç°å¢å¤æ°ã«æåè¨­å®ãã
    print(f"\n{'='*60}")
    print(f"â ã¢ã¯ã»ã¹ãã¼ã¯ã³åå¾æåï¼")
    print(f"ã·ã§ãã: {shop}")
    print(f"SHOPIFY_ACCESS_TOKEN={token}")
    print(f"ð Renderã®Environment Variablesã«ãã®å¤ãè¨­å®ãã¦ãã ãã")
    print(f"{'='*60}\n")
    # ä»åã®ãªã¯ã¨ã¹ãã ãä½¿ããããã«ã»ãã·ã§ã³ã«ä¿å­
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
            rows.append({
                "order": o["name"],
                "date": o["createdAt"][:10],
                "title": item["title"],
                "qty": item["quantity"],
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
    data  = graphql(shop, token, ORDERS_GQL.format(count=count))
    rows  = []
    for edge in data["data"]["orders"]["edges"]:
        o = edge["node"]
        a = o.get("shippingAddress") or {}
        items = "ï¼".join(
            f"{li['node']['title']}Ã{li['node']['quantity']}"
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

# ---------- ãã¦ã³ã­ã¼ã ----------

@app.route("/download/orders")
def download_orders():
    shop  = request.args.get("shop", "")
    count = request.args.get("count", "50")
    token = get_token(shop) or session.get("token", "")
    rows, extra_keys = get_orders_data(shop, token, count)
    cols  = ["æ³¨æçªå·","æ³¨ææ¥","ååå","æ°é"] + OPTION_KEYS + extra_keys
    out   = io.StringIO()
    w     = csv.writer(out)
    w.writerow(cols)
    for r in rows:
        w.writerow([
            r["order"], r["date"], r["title"], r["qty"],
            *[r["attrs"].get(k, "") for k in OPTION_KEYS + extra_keys],
        ])
    from datetime import date
    filename = f"æªçºéæ³¨æ_{date.today()}.csv"
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
    data     = graphql(shop, token, ORDERS_GQL.format(count=count))
    filter_products = [p.strip() for p in products.split(",") if p.strip()] if products else []
    COLS  = ["ãå±ãåéµä¾¿çªå·","ãå±ãåæ°å","ãå±ãåä½æ1(é½éåºç)","ãå±ãåä½æ2(å¸åºçºæ)",
             "ãå±ãåä½æ3(çªå°)","ãå±ãåä½æ4(å»ºç©åç­)","ãå±ãåé»è©±çªå·","åå®¹å","éé(g)"]
    out   = io.StringIO()
    w     = csv.writer(out)
    w.writerow(COLS)
    for edge in data["data"]["orders"]["edges"]:
        o = edge["node"]
        a = o.get("shippingAddress") or {}
        items = "ï¼".join(
            f"{li['node']['title']}Ã{li['node']['quantity']}"
            for li in o["lineItems"]["edges"]
        )
        w.writerow([
            '="' + clean_zip(a.get("zip", "")) + '"',
            (a.get("lastName") or "") + (a.get("firstName") or ""),
            PREF.get(a.get("province", ""), a.get("province", "")),
            a.get("city", ""),
            a.get("address1", ""),
            a.get("address2") or "",
            clean_phone(a.get("phone", "")),
            items, "",
        ])
    from datetime import date
    filename = f"ã¯ãªãã¯ãã¹ã_{date.today()}.csv"
    return Response(
        out.getvalue().encode("utf-8-sig"),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{requests.utils.quote(filename)}"},
    )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
