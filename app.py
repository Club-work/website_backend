from flask import Flask, request, jsonify
from flask_cors import CORS
import psycopg2
import os, bcrypt, jwt
from functools import wraps
from dotenv import load_dotenv
from datetime import datetime, timedelta
import resend

# ================= LOAD ENV =================
load_dotenv()
app = Flask(__name__)

# ================= CORS =================
CORS(app)

# ================= ENV =================
DATABASE_URL = os.getenv("DATABASE_URL")
JWT_SECRET = os.getenv("JWT_SECRET")
CLUB_EMAIL = os.getenv("CLUB_EMAIL")
PORT = int(os.getenv("PORT", 10000))
resend.api_key = os.getenv("RESEND_API_KEY")

# ================= DB (LAZY CONNECTION) =================
def get_db():
    return psycopg2.connect(DATABASE_URL, sslmode="require")

# ================= ADMIN AUTH =================
def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):

        # 🔥 Allow preflight
        if request.method == "OPTIONS":
            return jsonify({"ok": True}), 200

        auth = request.headers.get("Authorization")
        if not auth or not auth.startswith("Bearer "):
            return jsonify({"error": "Token missing"}), 401

        try:
            jwt.decode(auth.split(" ")[1], JWT_SECRET, algorithms=["HS256"])
        except:
            return jsonify({"error": "Invalid token"}), 401

        return f(*args, **kwargs)
    return wrapper

# ================= HEALTH =================
@app.route("/")
def home():
    return {"status": "ADAS Club API running"}

# ================= ADMIN LOGIN =================
@app.route("/admin/login", methods=["POST"])
def admin_login():
    d = request.json
    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "SELECT password_hash FROM admin_users WHERE username=%s",
        (d["username"],)
    )
    row = cur.fetchone()

    cur.close()
    conn.close()

    if not row:
        return jsonify({"error": "Invalid credentials"}), 401

    stored = row[0].encode() if isinstance(row[0], str) else row[0]
    if not bcrypt.checkpw(d["password"].encode(), stored):
        return jsonify({"error": "Invalid credentials"}), 401

    token = jwt.encode(
        {"user": d["username"], "exp": datetime.utcnow() + timedelta(hours=6)},
        JWT_SECRET,
        algorithm="HS256"
    )

    return jsonify({"token": token})

# ================= EVENTS =================
@app.route("/events", methods=["GET"])
def get_events():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT id,title,categories,details,gform_link,
               registration_open,registration_end
        FROM events
        ORDER BY created_at DESC
    """)
    rows = cur.fetchall()

    cur.close()
    conn.close()

    now = datetime.now()
    return jsonify([{
        "id": r[0],
        "title": r[1],
        "categories": r[2],
        "details": r[3],
        "register": r[5] and (r[6] is None or r[6] > now),
        "gform_link": r[4] if r[5] else None
    } for r in rows])

# ================= EVENTS ADMIN =================
@app.route("/admin/events", methods=["POST"])
@admin_required
def add_event():
    d = request.json
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO events
        (title,categories,details,gform_link,registration_open,registration_end)
        VALUES (%s,%s,%s,%s,%s,%s)
    """, (
        d["title"], d["categories"], d["details"],
        d["gform_link"], d["registration_open"], d.get("registration_end")
    ))

    conn.commit()
    cur.close()
    conn.close()
    return {"message": "Event added"}

@app.route("/admin/events/<int:id>", methods=["PUT"])
@admin_required
def update_event(id):
    d = request.json
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        UPDATE events SET
        title=%s,categories=%s,details=%s,
        gform_link=%s,registration_open=%s,registration_end=%s
        WHERE id=%s
    """, (
        d["title"], d["categories"], d["details"],
        d["gform_link"], d["registration_open"], d.get("registration_end"), id
    ))

    conn.commit()
    cur.close()
    conn.close()
    return {"message": "Event updated"}

@app.route("/admin/events/<int:id>", methods=["DELETE"])
@admin_required
def delete_event(id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM events WHERE id=%s", (id,))
    conn.commit()
    cur.close()
    conn.close()
    return {"message": "Event deleted"}

# ================= PRESIDENT =================
@app.route("/admin/president", methods=["POST"])
@admin_required
def add_president():
    d = request.json
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO president1 (name,year,photo_url) VALUES (%s,%s,%s)",
        (d["name"], d["year"], d["photo_url"])
    )
    conn.commit()
    cur.close()
    conn.close()
    return {"message": "President added"}

@app.route("/admin/president/<int:id>", methods=["DELETE"])
@admin_required
def delete_president(id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM president1 WHERE id=%s", (id,))
    conn.commit()
    cur.close()
    conn.close()
    return {"message": "President deleted"}

# ================= MEMBERS =================
@app.route("/admin/members", methods=["GET"])
@admin_required
def get_members():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, name, role, photo_url, president_id
        FROM club_members1
        ORDER BY id DESC
    """)
    rows = cur.fetchall()

    cur.close()
    conn.close()

    return jsonify([
        {
            "id": r[0],
            "name": r[1],
            "role": r[2],
            "photo_url": r[3],
            "president_id": r[4]
        }
        for r in rows
    ])

@app.route("/admin/members", methods=["POST"])
@admin_required
def add_member():
    d = request.json
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO club_members1 (name,role,photo_url,president_id)
        VALUES (%s,%s,%s,%s)
    """, (d["name"], d["role"], d["photo_url"], d["president_id"]))
    conn.commit()
    cur.close()
    conn.close()
    return {"message": "Member added"}

@app.route("/admin/members/<int:id>", methods=["PUT"])
@admin_required
def update_member(id):
    d = request.json
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        UPDATE club_members1 SET
            name=%s,
            role=%s,
            photo_url=%s,
            president_id=%s
        WHERE id=%s
    """, (
        d["name"],
        d["role"],
        d["photo_url"],
        d["president_id"],
        id
    ))

    conn.commit()
    cur.close()
    conn.close()

    return jsonify({"message": "Member updated successfully"})

@app.route("/admin/members/<int:id>", methods=["DELETE"])
@admin_required
def delete_member(id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM club_members1 WHERE id=%s", (id,))
    conn.commit()
    cur.close()
    conn.close()
    return {"message": "Member deleted"}

# ================= CONTACT =================
@app.route("/contact", methods=["POST"])
def contact():
    d = request.json
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO messages (name,email,message,created_at)
        VALUES (%s,%s,%s,%s)
    """, (d["name"], d["email"], d["message"], datetime.now()))
    conn.commit()

    cur.close()
    conn.close()

    try:
        resend.Emails.send({
            "from": "ADAS Club <onboarding@resend.dev>",
            "to": CLUB_EMAIL,
            "reply_to": d["email"],
            "subject": "New Contact Message",
            "html": f"<p>{d['message']}</p>"
        })
    except:
        pass

    return {"message": "Message sent"}

# ================= RUN =================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
