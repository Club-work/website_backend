from flask import Flask, request, jsonify
from flask_cors import CORS
import psycopg2
from psycopg2 import pool
import os
import bcrypt
import jwt
from functools import wraps
from dotenv import load_dotenv
from datetime import datetime, timedelta
import resend

# ---------------- LOAD ENV ----------------
load_dotenv()
app = Flask(__name__)

# CORS optimised
CORS(app, resources={r"/*": {"origins": "*"}})

# ---------------- ENV ----------------
DATABASE_URL = os.getenv("DATABASE_URL")
CLUB_EMAIL = os.getenv("CLUB_EMAIL")
JWT_SECRET = os.getenv("JWT_SECRET")
PORT = int(os.getenv("PORT", 5000))
resend.api_key = os.getenv("RESEND_API_KEY")

# ---------------- DB CONNECTION POOL ----------------
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

# ---------------- ADMIN AUTH ----------------
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

@app.route("/health")
def health():
    return {"status": "ok"}

# ======================================================
# 🔐 ADMIN LOGIN
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

    stored_hash = row[0]
    if isinstance(stored_hash, str):
        stored_hash = stored_hash.encode()   # safety fallback

    if not bcrypt.checkpw(data["password"].encode(), stored_hash):
        return jsonify({"error": "Invalid credentials"}), 401

    token = jwt.encode(
        {"user": data["username"], "exp": datetime.utcnow() + timedelta(hours=6)},
        JWT_SECRET,
        algorithm="HS256"
    )

    return jsonify({"token": token})

# ======================================================
# 👑 PRESIDENT (ADMIN CRUD)
# ======================================================
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
    release_db(conn)

    return {"message": "President added"}

@app.route("/admin/president/<int:id>", methods=["PUT"])
@admin_required
def update_president(id):
    data = request.json
    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "UPDATE president1 SET name=%s, year=%s, photo_url=%s WHERE id=%s",
        (data["name"], data["year"], data["photo_url"], id)
    )
    conn.commit()

    cur.close()
    release_db(conn)

    return {"message": "President updated"}

@app.route("/admin/president/<int:id>", methods=["DELETE"])
@admin_required
def delete_president(id):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("DELETE FROM president1 WHERE id=%s", (id,))
    conn.commit()

    cur.close()
    release_db(conn)

    return {"message": "President deleted"}

# ======================================================
# 👥 MEMBERS (ADMIN CRUD)
# ======================================================
@app.route("/admin/members", methods=["POST"])
@admin_required
def add_member():
    data = request.json
    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        """INSERT INTO club_members1
        (name, role, photo_url, president_id)
        VALUES (%s,%s,%s,%s)""",
        (data["name"], data["role"], data["photo_url"], data["president_id"])
    )
    conn.commit()

    cur.close()
    release_db(conn)

    return {"message": "Member added"}

@app.route("/admin/members/<int:id>", methods=["PUT"])
@admin_required
def update_member(id):
    data = request.json
    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        """UPDATE club_members1
        SET name=%s, role=%s, photo_url=%s, president_id=%s
        WHERE id=%s""",
        (data["name"], data["role"], data["photo_url"], data["president_id"], id)
    )
    conn.commit()

    cur.close()
    release_db(conn)

    return {"message": "Member updated"}

@app.route("/admin/members/<int:id>", methods=["DELETE"])
@admin_required
def delete_member(id):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("DELETE FROM club_members1 WHERE id=%s", (id,))
    conn.commit()

    cur.close()
    release_db(conn)

    return {"message": "Member deleted"}

# ======================================================
# ⭐ PRESIDENT + MEMBERS (PUBLIC GET)
# ======================================================
@app.route("/president-members", methods=["GET"])
def president_members():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, name, photo_url, year
        FROM president1
        ORDER BY year DESC
    """)
    presidents = cur.fetchall()

    result = []

    for p in presidents:
        cur.execute("""
            SELECT id, name, role, photo_url
            FROM club_members1
            WHERE president_id=%s
        """, (p[0],))
        members = cur.fetchall()

        result.append({
            "id": p[0],
            "name": p[1],
            "photo_url": p[2],
            "year": p[3],
            "members": [
                {"id": m[0], "name": m[1], "role": m[2], "photo_url": m[3]}
                for m in members
            ]
        })

    cur.close()
    release_db(conn)

    return jsonify(result)

# ======================================================
# 📅 EVENTS
# ======================================================
@app.route("/events", methods=["GET"])
def get_events():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT title, categories, details, gform_link,
               registration_open, registration_end
        FROM events
        ORDER BY created_at DESC
    """)
    rows = cur.fetchall()

    cur.close()
    release_db(conn)

    now = datetime.now()

    return [{
        "title": r[0],
        "categories": r[1],
        "details": r[2],
        "register": r[4] and (r[5] is None or r[5] > now),
        "gform_link": r[3] if r[4] else None
    } for r in rows]

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
    release_db(conn)

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

    return {"message": "Message sent"}
