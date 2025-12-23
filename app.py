from flask import Flask, request, jsonify
from flask_cors import CORS
import psycopg2
import os
import bcrypt
import jwt
from functools import wraps
from dotenv import load_dotenv
from email.message import EmailMessage
import smtplib
from datetime import datetime, timedelta

# ---------------- LOAD ENV ----------------
load_dotenv()
app = Flask(__name__)
CORS(app)

# ---------------- ENV ----------------
DATABASE_URL = os.getenv("DATABASE_URL")
CLUB_EMAIL = os.getenv("CLUB_EMAIL")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
JWT_SECRET = os.getenv("JWT_SECRET")
PORT = int(os.getenv("PORT", 5000))

# ---------------- DB ----------------
def get_db():
    return psycopg2.connect(DATABASE_URL, sslmode="require")

# ---------------- ADMIN AUTH MIDDLEWARE ----------------
def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        auth = request.headers.get("Authorization")
        if not auth:
            return jsonify({"error": "Token missing"}), 401
        try:
            token = auth.split(" ")[1]
            jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        except:
            return jsonify({"error": "Invalid token"}), 401
        return f(*args, **kwargs)
    return wrapper

# ---------------- HEALTH ----------------
@app.route("/")
def home():
    return {"status": "ADAS Club API running"}

# ---------------- TEST DB ----------------
@app.route("/test-db")
def test_db():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM president1")
        count = cur.fetchone()[0]
        cur.close()
        conn.close()
        return {"status": "success", "president_count": count}
    except Exception as e:
        return {"error": str(e)}, 500

# ======================================================
# 🔐 ADMIN AUTH
# ======================================================
@app.route("/admin/login", methods=["POST"])
def admin_login():
    data = request.json
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT password_hash FROM admin_users WHERE username=%s", (data["username"],))
    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row or not bcrypt.checkpw(data["password"].encode(), row[0].encode()):
        return {"error": "Invalid credentials"}, 401

    token = jwt.encode(
        {"user": data["username"], "exp": datetime.utcnow() + timedelta(hours=6)},
        JWT_SECRET,
        algorithm="HS256"
    )
    return {"token": token}

def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        auth = request.headers.get("Authorization")
        if not auth:
            return jsonify({"error": "Token missing"}), 401
        try:
            token = auth.split(" ")[1]
            jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        except Exception as e:
            return jsonify({"error": str(e)}), 401
        return f(*args, **kwargs)
    return wrapper


# ======================================================
# 👑 PRESIDENT
# ======================================================
@app.route("/president", methods=["GET"])
def get_president():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, name, year, photo_url FROM president1 ORDER BY id DESC LIMIT 1")
    row = cur.fetchone()
    cur.close()
    conn.close()
    return {} if not row else {
        "id": row[0],
        "name": row[1],
        "year": row[2],
        "photo_url": row[3]
    }

@app.route("/admin/president", methods=["POST"])
@admin_required
def add_president():
    data = request.json
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO president1 (name, year, photo_url) VALUES (%s,%s,%s)",
        (data["name"], data["year"], data["photo_url"])
    )
    conn.commit()
    cur.close()
    conn.close()
    return {"message": "President added"}

# ======================================================
# 👥 MEMBERS
# ======================================================
@app.route("/members", methods=["GET"])
def get_members():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT cm.id, cm.name, cm.role, cm.photo_url, p.name
        FROM club_members1 cm
        LEFT JOIN president1 p ON cm.president_id = p.id
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [{
        "id": r[0],
        "name": r[1],
        "role": r[2],
        "photo_url": r[3],
        "president": r[4]
    } for r in rows]

@app.route("/admin/members", methods=["POST"])
@admin_required
def add_member():
    data = request.json
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO club_members1 (name, role, photo_url, president_id) VALUES (%s,%s,%s,%s)",
        (data["name"], data["role"], data["photo_url"], data["president_id"])
    )
    conn.commit()
    cur.close()
    conn.close()
    return {"message": "Member added"}

# ======================================================
# 📅 EVENTS
# ======================================================
@app.route("/events", methods=["GET"])
def get_events():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, title, categories , event_date, gform_link FROM events ORDER BY event_date DESC")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [{
        "id": r[0],
        "title": r[1],
        "description": r[2],
        "event_date": r[3],
        "gform_link": r[4]
    } for r in rows]

@app.route("/admin/events", methods=["POST"])
@admin_required
def add_event():
    data = request.json
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO events (title, categories, event_date, gform_link) VALUES (%s,%s,%s,%s)",
        (data["title"], data["categories"], data["event_date"], data["gform_link"])
    )
    conn.commit()
    cur.close()
    conn.close()
    return {"message": "Event added"}

# ======================================================
# ✉️ CONTACT
# ======================================================
@app.route("/contact", methods=["POST"])
def contact():
    data = request.json
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO messages (name, email, message, created_at) VALUES (%s,%s,%s,%s)",
        (data["name"], data["email"], data["message"], datetime.now())
    )
    conn.commit()
    cur.close()
    conn.close()

    msg = EmailMessage()
    msg["Subject"] = "New Contact Message - ADAS Club"
    msg["From"] = CLUB_EMAIL
    msg["To"] = CLUB_EMAIL
    msg["Reply-To"] = data["email"]
    msg.set_content(f"""
Name: {data['name']}
Email: {data['email']}
Message:
{data['message']}
""")

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(CLUB_EMAIL, EMAIL_PASSWORD)
        server.send_message(msg)

    return {"message": "Message sent"}

# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=True)
