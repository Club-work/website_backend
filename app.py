from flask import Flask, request, jsonify
from flask_cors import CORS
import psycopg2
import os
import bcrypt
import jwt
from functools import wraps
from dotenv import load_dotenv
from email.message import EmailMessage
from datetime import datetime, timedelta
import resend


# ---------------- LOAD ENV ----------------
load_dotenv()
app = Flask(__name__)
CORS(app)

# ---------------- ENV ----------------
DATABASE_URL = os.getenv("DATABASE_URL")
CLUB_EMAIL = os.getenv("CLUB_EMAIL")
resend.api_key = os.getenv("RESEND_API_KEY")
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
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON"}), 400

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

        # IMPORTANT FIX HERE 👇
        if not bcrypt.checkpw(
            data["password"].encode("utf-8"),
            row[0].encode("utf-8") if isinstance(row[0], str) else row[0]
        ):
            return jsonify({"error": "Invalid credentials"}), 401

        token = jwt.encode(
            {"user": data["username"], "exp": datetime.utcnow() + timedelta(hours=6)},
            JWT_SECRET,
            algorithm="HS256"
        )

        return jsonify({"token": token}), 200

    except Exception as e:
        print("ADMIN LOGIN ERROR:", e)
        return jsonify({"error": "Something went wrong"}), 500

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
        "categories": r[2],
        "event_date": r[3],
        "gform_link": r[4],
        "details": r[5]
    } for r in rows]

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

# ======================================================
# ✉️ CONTACT
# ======================================================
@app.route("/contact", methods=["POST"])
def contact():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON"}), 400

        # Save to DB
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO messages (name, email, message, created_at) VALUES (%s,%s,%s,%s)",
            (data["name"], data["email"], data["message"], datetime.now())
        )
        conn.commit()
        cur.close()
        conn.close()

        # Send email
        response = resend.Emails.send({
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

        print("RESEND RESPONSE:", response)

        return jsonify({"message": "Contact message sent successfully"}), 200

    except Exception as e:
        print("CONTACT ERROR:", e)
        return jsonify({"error": "Something went wrong"}), 500

# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=True)
