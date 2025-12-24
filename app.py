from flask import Flask, request, jsonify
from flask_cors import CORS
import psycopg2
import os
import bcrypt
import jwt
from functools import wraps
from datetime import datetime, timedelta
from dotenv import load_dotenv
import resend

# =====================================================
# BASIC SETUP
# =====================================================
load_dotenv()
app = Flask(__name__)
CORS(app)

DATABASE_URL = os.getenv("DATABASE_URL")
JWT_SECRET = os.getenv("JWT_SECRET")
CLUB_EMAIL = os.getenv("CLUB_EMAIL")
resend.api_key = os.getenv("RESEND_API_KEY")

# =====================================================
# DATABASE
# =====================================================
def get_db():
    return psycopg2.connect(DATABASE_URL, sslmode="require")

# =====================================================
# ADMIN AUTH MIDDLEWARE
# =====================================================
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

# =====================================================
# HEALTH CHECK
# =====================================================
@app.route("/")
def home():
    return {"status": "ADAS Club API running"}

# =====================================================
# ADMIN LOGIN
# =====================================================
@app.route("/admin/login", methods=["POST"])
def admin_login():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON"}), 400

        if "username" not in data or "password" not in data:
            return jsonify({"error": "Username & password required"}), 400

        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "SELECT password_hash FROM admin_users WHERE username=%s",
            (data["username"],)
        )
        row = cur.fetchone()
        cur.close()
        conn.close()

        if not row:
            return jsonify({"error": "Invalid credentials"}), 401

        stored_hash = row[0]
        if isinstance(stored_hash, str):
            stored_hash = stored_hash.encode("utf-8")

        if not bcrypt.checkpw(data["password"].encode("utf-8"), stored_hash):
            return jsonify({"error": "Invalid credentials"}), 401

        token = jwt.encode(
            {
                "user": data["username"],
                "exp": datetime.utcnow() + timedelta(hours=6)
            },
            JWT_SECRET,
            algorithm="HS256"
        )

        return jsonify({"token": token}), 200

    except Exception as e:
        print("ADMIN LOGIN ERROR:", e)
        return jsonify({"error": str(e)}), 500

# =====================================================
# PRESIDENT CRUD
# =====================================================
@app.route("/president", methods=["GET"])
def get_presidents():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, name, year, photo_url FROM president1 ORDER BY year DESC"
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()

    return [
        {
            "id": r[0],
            "name": r[1],
            "year": r[2],
            "photo_url": r[3]
        } for r in rows
    ]

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
    conn.close()
    return {"message": "President updated"}

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

# =====================================================
# MEMBERS CRUD
# =====================================================
@app.route("/members", methods=["GET"])
def get_members():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT 
            cm.id, cm.name, cm.role, cm.photo_url,
            p.id, p.name, p.year
        FROM club_members1 cm
        JOIN president1 p ON cm.president_id = p.id
        ORDER BY p.year DESC
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    return [
        {
            "id": r[0],
            "name": r[1],
            "role": r[2],
            "photo_url": r[3],
            "president": {
                "id": r[4],
                "name": r[5],
                "year": r[6]
            }
        } for r in rows
    ]

@app.route("/admin/members", methods=["POST"])
@admin_required
def add_member():
    data = request.json
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO club_members1 (name, role, photo_url, president_id)
        VALUES (%s,%s,%s,%s)
    """, (
        data["name"],
        data["role"],
        data["photo_url"],
        data["president_id"]
    ))
    conn.commit()
    cur.close()
    conn.close()
    return {"message": "Member added"}

@app.route("/admin/members/<int:id>", methods=["PUT"])
@admin_required
def update_member(id):
    data = request.json
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE club_members1
        SET name=%s, role=%s, photo_url=%s, president_id=%s
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
    conn.close()
    return {"message": "Member updated"}

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

# =====================================================
# EVENTS CRUD
# =====================================================
@app.route("/events", methods=["GET"])
def get_events():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, title, categories, details, event_date, gform_link
        FROM events
        ORDER BY event_date DESC
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    return [
        {
            "id": r[0],
            "title": r[1],
            "categories": r[2],
            "details": r[3],
            "event_date": r[4],
            "gform_link": r[5]
        } for r in rows
    ]

@app.route("/admin/events", methods=["POST"])
@admin_required
def add_event():
    data = request.json
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO events (title, categories, details, event_date, gform_link)
        VALUES (%s,%s,%s,%s,%s)
    """, (
        data["title"],
        data["categories"],
        data["details"],
        data["event_date"],
        data["gform_link"]
    ))
    conn.commit()
    cur.close()
    conn.close()
    return {"message": "Event added"}

@app.route("/admin/events/<int:id>", methods=["PUT"])
@admin_required
def update_event(id):
    data = request.json
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE events
        SET title=%s, categories=%s, details=%s, event_date=%s, gform_link=%s
        WHERE id=%s
    """, (
        data["title"],
        data["categories"],
        data["details"],
        data["event_date"],
        data["gform_link"],
        id
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

# =====================================================
# CONTACT (NO AUTO REPLY)
# =====================================================
@app.route("/contact", methods=["POST"])
def contact():
    data = request.json

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO messages (name, email, message) VALUES (%s,%s,%s)",
        (data["name"], data["email"], data["message"])
    )
    conn.commit()
    cur.close()
    conn.close()

    resend.Emails.send({
        "from": "ADAS Club <onboarding@resend.dev>",
        "to": CLUB_EMAIL,
        "reply_to": data["email"],
        "subject": "New Contact Message - ADAS Club",
        "html": f"""
            <p><b>Name:</b> {data['name']}</p>
            <p><b>Email:</b> {data['email']}</p>
            <p><b>Message:</b><br>{data['message']}</p>
        """
    })

    return {"message": "Message sent successfully"}

# =====================================================
# RUN
# =====================================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
