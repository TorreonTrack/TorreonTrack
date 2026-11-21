import os
import hashlib
import hmac
from decimal import Decimal
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor

load_dotenv()

def get_conn():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "torreontrack"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", ""),
    )

def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return salt.hex() + "$" + digest.hex()

def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split("$", 1)
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), 200_000
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except Exception:
        return False

def query(sql, params=None, fetch=True):
    conn = get_conn()
    try:
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, params or ())
                if fetch and cur.description:
                    return cur.fetchall()
                return cur.rowcount
    finally:
        conn.close()

def execute(sql, params=None):
    return query(sql, params, fetch=False)

def scalar(sql, params=None):
    rows = query(sql, params)
    if not rows:
        return None
    return next(iter(rows[0].values()))

def authenticate(username, password):
    rows = query(
        "SELECT user_id, full_name, username, password_hash, role "
        "FROM app_user WHERE username=%s AND is_active=TRUE",
        (username,)
    )
    if rows and verify_password(password, rows[0]["password_hash"]):
        user = rows[0].copy()
        user.pop("password_hash", None)
        return user
    return None

def customer_balance(customer_id, cursor=None):
    sql = """
        SELECT
          COALESCE((SELECT SUM(si.quantity * si.unit_price)
                    FROM sale s JOIN sale_item si ON si.sale_id=s.sale_id
                    WHERE s.customer_id=%s AND s.payment_type='Credit'),0)
          -
          COALESCE((SELECT SUM(amount) FROM payment WHERE customer_id=%s),0)
          AS balance
    """
    if cursor:
        cursor.execute(sql, (customer_id, customer_id))
        return Decimal(cursor.fetchone()[0] or 0)
    return Decimal(scalar(sql, (customer_id, customer_id)) or 0)

def create_sale(user_id, payment_type, customer_id, cart):
    """Save sale, sale lines, and stock changes in one database transaction."""
    conn = get_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                if payment_type == "Credit":
                    if not customer_id:
                        raise ValueError("Select a registered customer for a tab sale.")
                    cur.execute(
                        "SELECT tab_limit FROM customer WHERE customer_id=%s AND is_active=TRUE FOR UPDATE",
                        (customer_id,)
                    )
                    customer = cur.fetchone()
                    if not customer:
                        raise ValueError("Customer not found.")
                    current = customer_balance(customer_id, cur)
                    new_total = sum(Decimal(str(x["quantity"])) * Decimal(str(x["price"])) for x in cart)
                    if current + new_total > Decimal(customer[0]):
                        raise ValueError("This sale exceeds the customer's approved tab limit.")

                for item in cart:
                    cur.execute(
                        "SELECT stock FROM product WHERE product_id=%s AND is_active=TRUE FOR UPDATE",
                        (item["product_id"],)
                    )
                    row = cur.fetchone()
                    if not row:
                        raise ValueError(f'{item["name"]} is no longer available.')
                    if Decimal(str(row[0])) < Decimal(str(item["quantity"])):
                        raise ValueError(f'Insufficient stock for {item["name"]}.')

                cur.execute(
                    """INSERT INTO sale(user_id, customer_id, payment_type)
                       VALUES (%s,%s,%s) RETURNING sale_id""",
                    (user_id, customer_id if payment_type == "Credit" else None, payment_type)
                )
                sale_id = cur.fetchone()[0]

                for item in cart:
                    cur.execute(
                        "SELECT average_cost FROM product WHERE product_id=%s",
                        (item["product_id"],)
                    )
                    cost = cur.fetchone()[0]
                    cur.execute(
                        """INSERT INTO sale_item
                           (sale_id, product_id, quantity, unit_price, unit_cost_at_sale)
                           VALUES (%s,%s,%s,%s,%s)""",
                        (sale_id, item["product_id"], item["quantity"], item["price"], cost)
                    )
                    cur.execute(
                        "UPDATE product SET stock=stock-%s WHERE product_id=%s",
                        (item["quantity"], item["product_id"])
                    )
        return sale_id
    finally:
        conn.close()

def record_delivery(user_id, supplier_id, items):
    conn = get_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO delivery(supplier_id,user_id) VALUES (%s,%s) RETURNING delivery_id",
                    (supplier_id, user_id)
                )
                delivery_id = cur.fetchone()[0]
                for item in items:
                    cur.execute(
                        "SELECT stock, average_cost FROM product WHERE product_id=%s FOR UPDATE",
                        (item["product_id"],)
                    )
                    old_stock, old_cost = cur.fetchone()
                    qty = Decimal(str(item["quantity"]))
                    unit_cost = Decimal(str(item["unit_cost"]))
                    new_stock = Decimal(old_stock) + qty
                    if new_stock > 0:
                        avg = ((Decimal(old_stock) * Decimal(old_cost)) + (qty * unit_cost)) / new_stock
                    else:
                        avg = unit_cost
                    cur.execute(
                        """INSERT INTO delivery_item(delivery_id,product_id,quantity,unit_cost)
                           VALUES (%s,%s,%s,%s)""",
                        (delivery_id, item["product_id"], qty, unit_cost)
                    )
                    cur.execute(
                        "UPDATE product SET stock=%s, average_cost=%s WHERE product_id=%s",
                        (new_stock, avg, item["product_id"])
                    )
        return delivery_id
    finally:
        conn.close()
