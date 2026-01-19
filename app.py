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

# ======================================================
# LOAD ENV
# ======================================================
load_dotenv()

app = Flask(__name__)

# ======================================================
# CORS (FIXED FOR REACT + AUTH HEADER)
# ======================================================
CORS(
    app,
    supports_credentials=True,
    resources={
        r"/*": {
            "origins": ["https://adas-club.onrender.com"],
            "allow_headers": ["Content-Type", "Authorization"],
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
        }
    }
)

@app.before_request
def handle_preflight():
    if request.method == "OPTIONS":
        response = jsonify({"status": "ok"})
        response.headers.add("Access-Control-Allow-Origin", "https://adas-club.onrender.com")
        response.headers.add("Access-Control-Allow-Headers", "Authorization, Content-Type")
        response.headers.add("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        return response, 200

# ======================================================
# ENV VARIABLES
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
# ADMIN AUTH DECORATOR
# ======================================================
def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if request.method == "OPTIONS":
            return jsonify({"status": "ok"}), 200

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
# HEALTH CHECK
# ======================================================
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
        stored_hash = stored_hash.encode()

    if not bcrypt.checkpw(data["password"].encode(), stored_hash):
        return jsonify({"error": "Invalid credentials"}), 401

    token = jwt.encode(
        {"user": data["username"], "exp": datetime.utcnow() + timedelta(hours=6)},
        JWT_SECRET,
        algorithm="HS256"
    )

    return jsonify({
        "message": "Token generated successfully",
        "token": token
    })

# ======================================================
# 📅 EVENTS (PUBLIC GET)
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
# 📅 EVENTS (ADMIN CRUD)
# ======================================================
@app.route("/admin/events", methods=["POST"])
@admin_required
def add_event():
    data = request.json
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO events
        (title, categories, details, gform_link, registration_open, registration_end)
        VALUES (%s,%s,%s,%s,%s,%s)
    """, (
        data["title"],
        data["categories"],
        data["details"],
        data["gform_link"],
        data["registration_open"],
        data.get("registration_end")
    ))

    conn.commit()
    cur.close()
    release_db(conn)

    return {"message": "Event added"}

@app.route("/admin/events/<int:id>", methods=["PUT"])
@admin_required
def update_event(id):
    data = request.json
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        UPDATE events SET
        title=%s,
        categories=%s,
        details=%s,
        gform_link=%s,
        registration_open=%s,
        registration_end=%s
        WHERE id=%s
    """, (
        data["title"],
        data["categories"],
        data["details"],
        data["gform_link"],
        data["registration_open"],
        data.get("registration_end"),
        id
    ))

    conn.commit()
    cur.close()
    release_db(conn)

    return {"message": "Event updated"}

@app.route("/admin/events/<int:id>", methods=["DELETE"])
@admin_required
def delete_event(id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM events WHERE id=%s", (id,))
    conn.commit()
    cur.close()
    release_db(conn)
    return {"message": "Event deleted"}

# ======================================================
# 👑 PRESIDENT (ADMIN CRUD)
# ======================================================
# ======================================================
# 👥 PRESIDENT + MEMBERS (PUBLIC VIEW ONLY)
# ======================================================
@app.route("/president-members", methods=["GET"])
def president_members_public():
    conn = get_db()
    cur = conn.cursor()

    # 🔹 Single JOIN query (FAST & SAFE)
    cur.execute("""
        SELECT
            p.id            AS president_id,
            p.name          AS president_name,
            p.year          AS president_year,
            p.photo_url     AS president_photo,

            m.id            AS member_id,
            m.name          AS member_name,
            m.role          AS member_role,
            m.photo_url     AS member_photo

        FROM president1 p
        LEFT JOIN club_members1 m
            ON m.president_id = p.id

        ORDER BY p.year DESC, m.id
    """)

    rows = cur.fetchall()
    cur.close()
    conn.close()

    # 🔹 Group members under their president
    result = {}
    for r in rows:
        pid = r[0]

        if pid not in result:
            result[pid] = {
                "id": r[0],
                "name": r[1],
                "year": r[2],
                "photo_url": r[3],
                "members": []
            }

        # If member exists, attach to that president
        if r[4] is not None:
            result[pid]["members"].append({
                "id": r[4],
                "name": r[5],
                "role": r[6],
                "photo_url": r[7]
            })

    # Convert dict → list
    return jsonify(list(result.values()))

@app.route("/admin/presidents", methods=["GET"])
@admin_required
def get_presidents_admin():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, name, year, photo_url
        FROM president1
        ORDER BY year DESC
    """)
    rows = cur.fetchall()

    cur.close()
    release_db(conn)

    return jsonify([
        {
            "id": r[0],
            "name": r[1],
            "year": r[2],
            "photo_url": r[3]
        } for r in rows
    ])

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
@app.route("/admin/members", methods=["GET"])
@admin_required
def get_members_admin():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, name, role, photo_url, president_id
        FROM club_members1
        ORDER BY id DESC
    """)
    rows = cur.fetchall()

    cur.close()
    release_db(conn)

    return jsonify([
        {
            "id": r[0],
            "name": r[1],
            "role": r[2],
            "photo_url": r[3],
            "president_id": r[4]
        } for r in rows
    ])
@app.route("/admin/members", methods=["POST"])
@admin_required
def add_member():
    data = request.json
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO club_members1
        (name, role, photo_url, president_id)
        VALUES (%s,%s,%s,%s)
    """, (
        data["name"],
        data["role"],
        data["photo_url"],
        data["president_id"]
    ))
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
    cur.execute("""
        UPDATE club_members1 SET
        name=%s,
        role=%s,
        photo_url=%s,
        president_id=%s
        WHERE id=%s
    """, (
        data["name"],
        data["role"],
        data["photo_url"],
        data["president_id"],
        id
    ))
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

# ======================================================
# RUN
# ======================================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
