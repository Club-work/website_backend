from flask import Flask, request, jsonify
from flask_cors import CORS
from psycopg2 import pool
import os
import bcrypt
import jwt
from functools import wraps
from dotenv import load_dotenv
from datetime import datetime, timedelta
import resend

# ======================================================
# LOAD ENV
# ======================================================
load_dotenv()

app = Flask(__name__)

# ======================================================
# ✅ SIMPLE & SAFE CORS (THIS IS THE FIX)
# ======================================================
CORS(app)

# ======================================================
# ENV
# ======================================================
DATABASE_URL = os.getenv("DATABASE_URL")
JWT_SECRET = os.getenv("JWT_SECRET")
CLUB_EMAIL = os.getenv("CLUB_EMAIL")
PORT = int(os.getenv("PORT", 5000))
resend.api_key = os.getenv("RESEND_API_KEY")

# ======================================================
# DATABASE POOL
# ======================================================
db_pool = pool.SimpleConnectionPool(
    1,
    10,
    DATABASE_URL,
    sslmode="require"
)

def get_db():
    return db_pool.getconn()

def release_db(conn):
    db_pool.putconn(conn)

# ======================================================
# ADMIN AUTH
# ======================================================
def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        auth = request.headers.get("Authorization")
        if not auth or not auth.startswith("Bearer "):
            return jsonify({"error": "Token missing"}), 401

        try:
            token = auth.split(" ")[1]
            jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        except:
            return jsonify({"error": "Invalid token"}), 401

        return f(*args, **kwargs)
    return wrapper

# ======================================================
# HEALTH
# ======================================================
@app.route("/")
def home():
    return {"status": "ADAS Club API running"}

# ======================================================
# ADMIN LOGIN
# ======================================================
@app.route("/admin/login", methods=["POST"])
def admin_login():
    data = request.json

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT password_hash FROM admin_users WHERE username=%s",
        (data["username"],)
    )
    row = cur.fetchone()
    cur.close()
    release_db(conn)

    if not row:
        return jsonify({"error": "Invalid credentials"}), 401

    stored_hash = row[0].encode() if isinstance(row[0], str) else row[0]

    if not bcrypt.checkpw(data["password"].encode(), stored_hash):
        return jsonify({"error": "Invalid credentials"}), 401

    token = jwt.encode(
        {"user": data["username"], "exp": datetime.utcnow() + timedelta(hours=6)},
        JWT_SECRET,
        algorithm="HS256"
    )

    return jsonify({"token": token})

# ======================================================
# EVENTS (PUBLIC)
# ======================================================
@app.route("/events", methods=["GET"])
def get_events():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, title, categories, details, gform_link,
               registration_open, registration_end
        FROM events
        ORDER BY created_at DESC
    """)
    rows = cur.fetchall()
    cur.close()
    release_db(conn)

    now = datetime.now()

    return jsonify([{
        "id": r[0],
        "title": r[1],
        "categories": r[2],
        "details": r[3],
        "register": r[5] and (r[6] is None or r[6] > now),
        "gform_link": r[4] if r[5] else None
    } for r in rows])

# ======================================================
# PRESIDENT + MEMBERS (PUBLIC)
# ======================================================
@app.route("/president-members", methods=["GET"])
def president_members():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            p.id, p.name, p.year, p.photo_url,
            m.id, m.name, m.role, m.photo_url
        FROM president1 p
        LEFT JOIN club_members1 m
            ON m.president_id = p.id
        ORDER BY p.year DESC, m.id
    """)

    rows = cur.fetchall()
    cur.close()
    release_db(conn)

    data = {}
    for r in rows:
        pid = r[0]
        if pid not in data:
            data[pid] = {
                "id": r[0],
                "name": r[1],
                "year": r[2],
                "photo_url": r[3],
                "members": []
            }

        if r[4]:
            data[pid]["members"].append({
                "id": r[4],
                "name": r[5],
                "role": r[6],
                "photo_url": r[7]
            })

    return jsonify(list(data.values()))

# ======================================================
# CONTACT
# ======================================================
@app.route("/contact", methods=["POST"])
def contact():
    try:
        data = request.json

        # 1️⃣ Save message in DB (always)
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO messages (name, email, message, created_at)
            VALUES (%s, %s, %s, %s)
            """,
            (data["name"], data["email"], data["message"], datetime.now())
        )
        conn.commit()
        cur.close()
        release_db(conn)

        # 2️⃣ Try sending email (optional)
        try:
            resend.Emails.send({
                "from": "ADAS Club <onboarding@resend.dev>",
                "to": CLUB_EMAIL,
                "reply_to": data["email"],
                "subject": "New Contact Message",
                "html": f"""
                    <p><b>Name:</b> {data['name']}</p>
                    <p><b>Email:</b> {data['email']}</p>
                    <p>{data['message']}</p>
                """
            })
        except Exception as mail_error:
            print("❌ Email sending failed:", mail_error)

        # 3️⃣ Always success response to frontend
        return jsonify({"message": "Message sent successfully"}), 200

    except Exception as e:
        print("❌ Contact API error:", e)
        return jsonify({"error": "Failed to send message"}), 500

# ======================================================
# RUN
# ======================================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
