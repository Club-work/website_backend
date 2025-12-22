from flask import Flask, request, jsonify
from flask_cors import CORS
import mysql.connector
from email.message import EmailMessage
import smtplib
import os
from dotenv import load_dotenv

# load .env variables
load_dotenv()

app = Flask(__name__)
CORS(app)

# ================= DATABASE CONFIG =================
db = mysql.connector.connect(
    host=os.environ.get("DB_HOST"),
    user=os.environ.get("DB_USER"),
    password=os.environ.get("DB_PASSWORD"),
    database=os.environ.get("DB_NAME")
)
cursor = db.cursor(dictionary=True)

# ================= EMAIL CONFIG =================
CLUB_EMAIL = os.environ.get("CLUB_EMAIL")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")

# ================= TEST =================
@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "ADAS Club API running"})

# ================= PRESIDENT =================
@app.route("/president", methods=["GET"])
def get_president():
    cursor.execute("""
        SELECT id, name, year, photo_url
        FROM president1
        WHERE active = true
    """)
    return jsonify(cursor.fetchone())

@app.route("/president", methods=["POST"])
def add_president():
    data = request.json
    cursor.execute("""
        INSERT INTO president1 (name, year, photo_url, active)
        VALUES (%s, %s, %s, true)
    """, (data["name"], data["year"], data["photo_url"]))
    db.commit()
    return jsonify({"message": "President added"}), 201

# ================= MEMBERS =================
@app.route("/members", methods=["GET"])
def get_members():
    cursor.execute("""
        SELECT cm.id, cm.name, cm.role, cm.photo_url,
               p.name AS president_name
        FROM club_members1 cm
        LEFT JOIN president1 p ON cm.president_id = p.id
    """)
    return jsonify(cursor.fetchall())

@app.route("/members", methods=["POST"])
def add_member():
    try:
        data = request.json
        print("DATA RECEIVED:", data)   # 👈 DEBUG

        cursor.execute("""
            INSERT INTO club_members1 (name, role, photo_url, president_id)
            VALUES (%s, %s, %s, %s)
        """, (
            data["name"],
            data["role"],
            data["photo_url"],
            data.get("president1_id")
        ))

        db.commit()
        return jsonify({"message": "Member added"}), 201

    except Exception as e:
        print("ERROR:", e)   # 👈 REAL ERROR
        return jsonify({"error": str(e)}), 500

# ================= EVENTS =================
@app.route("/events", methods=["GET"])
def get_events():
    cursor.execute("""
        SELECT id, title, description, event_date, gform_link
        FROM events_new
        ORDER BY event_date DESC
    """)
    return jsonify(cursor.fetchall())

@app.route("/events", methods=["POST"])
def add_event():
    data = request.json
    cursor.execute("""
        INSERT INTO events_new (title, description, event_date, gform_link)
        VALUES (%s, %s, %s, %s)
    """, (
        data["title"],
        data["description"],
        data["event_date"],
        data["gform_link"]
    ))
    db.commit()
    return jsonify({"message": "Event added"}), 201

# ================= CONTACT =================
@app.route("/contact", methods=["POST"])
def contact():
    data = request.json

    msg = EmailMessage()
    msg["Subject"] = "New Contact Message - ADAS Club"
    msg["From"] = CLUB_EMAIL
    msg["To"] = CLUB_EMAIL
    msg["Reply-To"] = data["email"]
    msg.set_content(f"""
Name: {data["name"]}
Email: {data["email"]}

Message:
{data["message"]}
""")

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(CLUB_EMAIL, EMAIL_PASSWORD)
        server.send_message(msg)

    return jsonify({"message": "Message sent"}), 200

# ================= RUN =================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
