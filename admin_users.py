import os
import bcrypt
from dotenv import load_dotenv

# local-la mattum load aagum
load_dotenv()

password = os.getenv("ADMIN_PASSWORD")

if not password:
    raise Exception("ADMIN_PASSWORD not set")

hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
print(hashed.decode())
