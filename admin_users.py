import bcrypt

password = os.getenv("password")   # 👈 nee use panna password
hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
print(hashed.decode())
