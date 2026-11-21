"""Run once after creating the database and schema: python setup_admin.py"""
from getpass import getpass
from db import get_conn, hash_password

username = input("New manager username: ").strip()
full_name = input("Full name: ").strip()
password = getpass("Password: ")
confirm = getpass("Confirm password: ")

if not username or not full_name or not password:
    raise SystemExit("All fields are required.")
if password != confirm:
    raise SystemExit("Passwords do not match.")

conn = get_conn()
try:
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO app_user(full_name, username, password_hash, role)
                   VALUES (%s,%s,%s,'Owner')""",
                (full_name, username, hash_password(password))
            )
    print("Owner account created successfully.")
except Exception as e:
    print("Could not create account:", e)
finally:
    conn.close()
