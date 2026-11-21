import streamlit as st
import pandas as pd
from decimal import Decimal
from datetime import date, datetime, time, timedelta
from db import (
    query, execute, scalar, authenticate, create_sale, record_delivery,
    customer_balance, get_conn
)

st.set_page_config(page_title="TorreonTrack", page_icon="🛒", layout="wide")

st.markdown("""
<style>
    .block-container {padding-top: 1.5rem; padding-bottom: 2rem;}
    .main-title {font-size: 2rem; font-weight: 750; color: #17324d;}
    .subtle {color: #64748b;}
    div[data-testid="stMetric"] {background: #f7fafc; padding: 14px; border-radius: 12px;}
</style>
""", unsafe_allow_html=True)

def money(value):
    return f"PHP {float(value or 0):,.2f}"

def is_manager():
    return st.session_state.user["role"] in ("Owner", "Manager")

def load_df(sql, params=None):
    rows = query(sql, params)
    return pd.DataFrame(rows) if rows else pd.DataFrame()

def login_screen():
    left, center, right = st.columns([1, 1.2, 1])
    with center:
        st.markdown("<div class='main-title'>TorreonTrack</div>", unsafe_allow_html=True)
        st.subheader("Torreon Store")
        st.caption("Household sales, stock and customer tabs")
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Log in", use_container_width=True)
        if submitted:
            user = authenticate(username.strip(), password)
            if user:
                st.session_state.user = user
                st.rerun()
            else:
                st.error("Incorrect username or password.")
        st.caption("Your account determines what you can access.")

if "user" not in st.session_state:
    login_screen()
    st.stop()

user = st.session_state.user
with st.sidebar:
    st.markdown("## TorreonTrack")
    st.caption("Torreon Store")
    st.write(f"**{user['full_name']}**")
    st.caption(f"Role: {user['role']}")
    pages = ["Home", "New Sale", "Stock Lookup", "Customers & Tabs"]
    if is_manager():
        pages += ["Products & Stock", "Restocking", "Reports", "User Accounts"]
    page = st.radio("Navigation", pages, label_visibility="collapsed")
    if st.button("Log out", use_container_width=True):
        del st.session_state.user
        st.session_state.pop("cart", None)
        st.rerun()

st.markdown(f"<div class='main-title'>{page}</div>", unsafe_allow_html=True)
st.caption("Torreon Store | Sales, inventory and credit management")

# HOME
if page == "Home":
    today = date.today()
    sales = query("""
        SELECT
          COALESCE(SUM(si.quantity*si.unit_price),0) AS total,
          COALESCE(SUM(CASE WHEN s.payment_type='Cash' THEN si.quantity*si.unit_price ELSE 0 END),0) AS cash,
          COALESCE(SUM(CASE WHEN s.payment_type='Credit' THEN si.quantity*si.unit_price ELSE 0 END),0) AS credit
        FROM sale s JOIN sale_item si ON si.sale_id=s.sale_id
        WHERE s.sale_datetime::date=%s
    """, (today,))[0]
    collections = scalar("SELECT COALESCE(SUM(amount),0) FROM payment WHERE payment_date::date=%s", (today,))
    a,b,c = st.columns(3)
    a.metric("Merchandise sales today", money(sales["total"]))
    b.metric("Cash sales", money(sales["cash"]))
    c.metric("Tab sales", money(sales["credit"]))
    st.info(f"Tab payments received today: **{money(collections)}**  |  Cash collected (cash sales + tab payments): **{money(Decimal(sales['cash']) + Decimal(collections or 0))}**")
    st.subheader("Products to restock")
    low = load_df("""
        SELECT product_name AS "Product", stock AS "Stock", reorder_level AS "Reorder"
        FROM product WHERE is_active=TRUE AND stock<=reorder_level ORDER BY product_name
    """)
    st.dataframe(low, use_container_width=True, hide_index=True)
    st.subheader("Outstanding customer tabs")
    tabs = load_df("""
        SELECT c.display_name AS "Customer",
          COALESCE(x.balance,0) AS "Balance", c.tab_limit AS "Approved limit"
        FROM customer c
        LEFT JOIN (
          SELECT z.customer_id, SUM(z.amount) AS balance FROM (
            SELECT s.customer_id, SUM(si.quantity*si.unit_price) AS amount
            FROM sale s JOIN sale_item si ON si.sale_id=s.sale_id
            WHERE s.payment_type='Credit' GROUP BY s.customer_id
            UNION ALL
            SELECT customer_id, -SUM(amount) FROM payment GROUP BY customer_id
          ) z GROUP BY z.customer_id
        ) x ON x.customer_id=c.customer_id
        WHERE c.is_active=TRUE AND COALESCE(x.balance,0)>0
        ORDER BY "Balance" DESC
    """)
    st.dataframe(tabs, use_container_width=True, hide_index=True)

# NEW SALE
elif page == "New Sale":
    products = query("SELECT product_id, product_name, price, stock FROM product WHERE is_active=TRUE ORDER BY product_name")
    if not products:
        st.warning("No active products yet. Ask a manager to add products.")
        st.stop()
    product_map = {f"{p['product_name']} (stock: {p['stock']})": p for p in products}
    with st.form("add_cart"):
        selected = st.selectbox("Find merchandise", list(product_map))
        qty = st.number_input("Quantity", min_value=0.001, value=1.0, step=1.0)
        add = st.form_submit_button("Add item")
    if add:
        p = product_map[selected]
        cart = st.session_state.setdefault("cart", [])
        existing = next((x for x in cart if x["product_id"] == p["product_id"]), None)
        if existing:
            existing["quantity"] += qty
        else:
            cart.append({"product_id": p["product_id"], "name": p["product_name"],
                         "quantity": qty, "price": float(p["price"])})
        st.success("Item added.")
    cart = st.session_state.setdefault("cart", [])
    st.subheader("Current sale")
    if cart:
        for i, item in enumerate(cart):
            col1,col2,col3,col4 = st.columns([4,1,2,1])
            col1.write(item["name"])
            col2.write(item["quantity"])
            col3.write(money(item["quantity"] * item["price"]))
            if col4.button("Remove", key=f"remove_{i}"):
                cart.pop(i)
                st.rerun()
        total = sum(Decimal(str(x["quantity"])) * Decimal(str(x["price"])) for x in cart)
        st.markdown(f"### Total: {money(total)}")
        method = st.radio("Payment method", ["Cash", "Credit"], horizontal=True)
        customer_id = None
        if method == "Credit":
            customers = query("SELECT customer_id, display_name, tab_limit FROM customer WHERE is_active=TRUE ORDER BY display_name")
            if customers:
                cm = {f"{x['display_name']} (limit {money(x['tab_limit'])})": x for x in customers}
                chosen = st.selectbox("Customer (tab only)", list(cm))
                customer_id = cm[chosen]["customer_id"]
                bal = customer_balance(customer_id)
                st.caption(f"Current balance: {money(bal)} | Available: {money(Decimal(cm[chosen]['tab_limit'])-bal)}")
            else:
                st.warning("Register a customer before making a tab sale.")
        cash_received = None
        if method == "Cash":
            cash_received = st.number_input("Cash received", min_value=0.0, value=float(total), step=1.0)
            st.write(f"Change: **{money(max(Decimal('0'), Decimal(str(cash_received))-total))}**")
        col1,col2 = st.columns(2)
        with col1:
            if st.button("Complete sale", type="primary", use_container_width=True):
                if method == "Cash" and Decimal(str(cash_received)) < total:
                    st.error("Cash received is less than the total.")
                elif method == "Credit" and not customer_id:
                    st.error("Select a registered customer.")
                else:
                    try:
                        sale_id = create_sale(user["user_id"], method, customer_id, cart)
                        st.session_state.cart = []
                        st.success(f"Sale #{sale_id} saved successfully.")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))
        with col2:
            if st.button("Clear sale", use_container_width=True):
                st.session_state.cart = []
                st.rerun()
    else:
        st.info("No items in the sale yet. Find a product and add its quantity.")

# STOCK LOOKUP
elif page == "Stock Lookup":
    df = load_df("""
        SELECT p.product_name AS "Product", c.category_name AS "Category",
               p.price AS "Sell price", p.stock AS "Available stock",
               p.reorder_level AS "Reorder level"
        FROM product p JOIN category c ON c.category_id=p.category_id
        WHERE p.is_active=TRUE ORDER BY p.product_name
    """)
    st.dataframe(df, use_container_width=True, hide_index=True)

# PRODUCTS & STOCK
elif page == "Products & Stock":
    st.subheader("Add merchandise")
    categories = query("SELECT category_id, category_name FROM category ORDER BY category_name")
    with st.form("add_product"):
        name = st.text_input("Product name")
        if categories:
            cat_map = {x["category_name"]: x["category_id"] for x in categories}
            cat_name = st.selectbox("Category", list(cat_map))
        else:
            cat_map, cat_name = {}, None
            st.warning("Add a category first.")
        price = st.number_input("Selling price (PHP)", min_value=0.01, value=1.0)
        opening_stock = st.number_input("Opening stock", min_value=0.0, value=0.0)
        reorder = st.number_input("Reorder level", min_value=0.0, value=0.0)
        cost = st.number_input("Opening unit cost (PHP)", min_value=0.0, value=0.0)
        submitted = st.form_submit_button("Save product")
    if submitted:
        if not name.strip() or not categories:
            st.error("Enter a product name and make sure a category exists.")
        else:
            execute("""INSERT INTO product(product_name,category_id,price,stock,reorder_level,average_cost)
                       VALUES (%s,%s,%s,%s,%s,%s)""",
                    (name.strip(), cat_map[cat_name], price, opening_stock, reorder, cost))
            st.success("Product added.")
            st.rerun()

    st.subheader("Product list")
    df = load_df("""
        SELECT p.product_id AS "ID", p.product_name AS "Product",
               c.category_name AS "Category", p.price AS "Sell price",
               p.stock AS "Stock", p.reorder_level AS "Reorder", p.average_cost AS "Average cost"
        FROM product p JOIN category c ON c.category_id=p.category_id
        WHERE p.is_active=TRUE ORDER BY p.product_name
    """)
    st.dataframe(df, use_container_width=True, hide_index=True)
    if not df.empty:
        ids = dict(zip(df["Product"] + " (#" + df["ID"].astype(str) + ")", df["ID"]))
        chosen = st.selectbox("Select product to edit or deactivate", list(ids))
        selected_id = int(ids[chosen])
        with st.form("edit_product"):
            new_price = st.number_input("New selling price", min_value=0.01, value=float(df.loc[df["ID"]==selected_id, "Sell price"].iloc[0]))
            new_reorder = st.number_input("New reorder level", min_value=0.0, value=float(df.loc[df["ID"]==selected_id, "Reorder"].iloc[0]))
            save_edit = st.form_submit_button("Update price / reorder level")
        if save_edit:
            execute("UPDATE product SET price=%s,reorder_level=%s WHERE product_id=%s", (new_price,new_reorder,selected_id))
            st.success("Product updated.")
            st.rerun()
        if st.button("Deactivate selected product"):
            execute("UPDATE product SET is_active=FALSE WHERE product_id=%s", (selected_id,))
            st.success("Product deactivated; transaction history retained.")
            st.rerun()

    st.divider()
    st.subheader("Manage categories")
    with st.form("add_category"):
        category_name = st.text_input("New category name")
        cat_submit = st.form_submit_button("Add category")
    if cat_submit and category_name.strip():
        execute("INSERT INTO category(category_name) VALUES (%s) ON CONFLICT DO NOTHING", (category_name.strip(),))
        st.success("Category saved.")
        st.rerun()

# RESTOCKING
elif page == "Restocking":
    suppliers = query("SELECT supplier_id,supplier_name FROM supplier ORDER BY supplier_name")
    with st.expander("Add supplier"):
        with st.form("add_supplier"):
            supplier_name = st.text_input("Supplier name")
            contact = st.text_input("Contact number (optional)")
            ok = st.form_submit_button("Save supplier")
        if ok and supplier_name.strip():
            execute("INSERT INTO supplier(supplier_name,contact_no) VALUES (%s,%s)", (supplier_name.strip(),contact.strip() or None))
            st.success("Supplier added.")
            st.rerun()
    products = query("SELECT product_id,product_name FROM product WHERE is_active=TRUE ORDER BY product_name")
    if suppliers and products:
        sm = {x["supplier_name"]: x["supplier_id"] for x in suppliers}
        pm = {x["product_name"]: x["product_id"] for x in products}
        with st.form("delivery_form"):
            supplier = st.selectbox("Supplier", list(sm))
            product_name = st.selectbox("Product", list(pm))
            qty = st.number_input("Received quantity", min_value=0.001, value=1.0)
            unit_cost = st.number_input("Unit cost (PHP)", min_value=0.01, value=1.0)
            save = st.form_submit_button("Confirm delivery")
        if save:
            try:
                record_delivery(user["user_id"], sm[supplier],
                    [{"product_id":pm[product_name],"quantity":qty,"unit_cost":unit_cost}])
                st.success("Delivery recorded and stock updated.")
                st.rerun()
            except Exception as e:
                st.error(str(e))
    else:
        st.info("Add at least one supplier and one active product.")
    st.subheader("Recent deliveries")
    df = load_df("""
        SELECT d.delivery_id AS "Delivery #", d.delivery_date AS "Date",
               s.supplier_name AS "Supplier", p.product_name AS "Product",
               di.quantity AS "Qty", di.unit_cost AS "Unit cost"
        FROM delivery d JOIN supplier s ON s.supplier_id=d.supplier_id
        JOIN delivery_item di ON di.delivery_id=d.delivery_id
        JOIN product p ON p.product_id=di.product_id
        ORDER BY d.delivery_date DESC LIMIT 50
    """)
    st.dataframe(df, use_container_width=True, hide_index=True)

# CUSTOMERS & TABS
elif page == "Customers & Tabs":
    st.subheader("Register customer")
    with st.form("new_customer"):
        display_name = st.text_input("Customer name or nickname")
        contact_no = st.text_input("Contact number (optional)")
        tab_limit = st.number_input("Approved tab limit (PHP)", min_value=0.0, value=0.0)
        add_customer = st.form_submit_button("Register customer")
    if add_customer:
        if display_name.strip():
            execute("INSERT INTO customer(display_name,contact_no,tab_limit) VALUES (%s,%s,%s)",
                    (display_name.strip(), contact_no.strip() or None, tab_limit))
            st.success("Customer registered.")
            st.rerun()
        else:
            st.error("Customer name is required.")

    customers = query("SELECT customer_id,display_name,tab_limit FROM customer WHERE is_active=TRUE ORDER BY display_name")
    if customers:
        cmap = {f"{c['display_name']} (#{c['customer_id']})": c for c in customers}
        selected = st.selectbox("Find customer / nickname", list(cmap))
        customer = cmap[selected]
        balance = customer_balance(customer["customer_id"])
        available = Decimal(customer["tab_limit"]) - balance
        a,b,c = st.columns(3)
        a.metric("Current balance", money(balance))
        b.metric("Approved limit", money(customer["tab_limit"]))
        c.metric("Available tab", money(available))
        if is_manager():
            with st.form("edit_limit"):
                limit = st.number_input("Edit approved limit (PHP)", min_value=0.0, value=float(customer["tab_limit"]))
                update_limit = st.form_submit_button("Update approved limit")
            if update_limit:
                execute("UPDATE customer SET tab_limit=%s WHERE customer_id=%s", (limit,customer["customer_id"]))
                st.success("Approved limit updated.")
                st.rerun()
        st.subheader("Purchases and payments")
        history = load_df("""
            SELECT s.sale_datetime AS "Date", 'Tab purchase' AS "Transaction",
                   SUM(si.quantity*si.unit_price) AS "Amount", u.full_name AS "Recorded by"
            FROM sale s JOIN sale_item si ON si.sale_id=s.sale_id
            JOIN app_user u ON u.user_id=s.user_id
            WHERE s.customer_id=%s AND s.payment_type='Credit'
            GROUP BY s.sale_id,s.sale_datetime,u.full_name
            UNION ALL
            SELECT p.payment_date, 'Payment', -p.amount, u.full_name
            FROM payment p JOIN app_user u ON u.user_id=p.user_id
            WHERE p.customer_id=%s
            ORDER BY "Date" DESC
        """, (customer["customer_id"],customer["customer_id"]))
        st.dataframe(history, use_container_width=True, hide_index=True)
        st.subheader("Payment received")
        with st.form("record_payment"):
            amount = st.number_input("Payment amount (PHP)", min_value=0.01, value=1.0)
            save_payment = st.form_submit_button("Record payment")
        if save_payment:
            try:
                if Decimal(str(amount)) > balance:
                    st.error("Payment cannot be greater than the outstanding balance.")
                else:
                    execute("INSERT INTO payment(customer_id,user_id,amount) VALUES (%s,%s,%s)",
                            (customer["customer_id"],user["user_id"],amount))
                    st.success("Payment recorded.")
                    st.rerun()
            except Exception as e:
                st.error(str(e))
    else:
        st.info("No customers registered yet.")

# REPORTS
elif page == "Reports":
    col1,col2 = st.columns(2)
    start = col1.date_input("From", value=date.today()-timedelta(days=6))
    end = col2.date_input("To", value=date.today())
    if start > end:
        st.error("The start date must not be after the end date.")
        st.stop()
    totals = query("""
        SELECT
          COALESCE(SUM(si.quantity*si.unit_price),0) AS sales,
          COALESCE(SUM(si.quantity*si.unit_cost_at_sale),0) AS costs,
          COALESCE(SUM(CASE WHEN s.payment_type='Cash' THEN si.quantity*si.unit_price ELSE 0 END),0) AS cash,
          COALESCE(SUM(CASE WHEN s.payment_type='Credit' THEN si.quantity*si.unit_price ELSE 0 END),0) AS credit
        FROM sale s JOIN sale_item si ON si.sale_id=s.sale_id
        WHERE s.sale_datetime::date BETWEEN %s AND %s
    """, (start,end))[0]
    profit = Decimal(totals["sales"]) - Decimal(totals["costs"])
    a,b,c = st.columns(3)
    a.metric("Sales", money(totals["sales"]))
    b.metric("Assigned costs", money(totals["costs"]))
    c.metric("Estimated gross profit", money(profit))
    st.caption(f"Cash sales: {money(totals['cash'])} | Tab sales: {money(totals['credit'])}")
    st.subheader("Daily merchandise sales")
    daily = load_df("""
        SELECT s.sale_datetime::date AS "Date",
               SUM(si.quantity*si.unit_price) AS "Sales"
        FROM sale s JOIN sale_item si ON si.sale_id=s.sale_id
        WHERE s.sale_datetime::date BETWEEN %s AND %s
        GROUP BY s.sale_datetime::date ORDER BY "Date"
    """, (start,end))
    if not daily.empty:
        st.bar_chart(daily.set_index("Date"))
    else:
        st.info("No sales in this date range.")
    st.subheader("Best-selling merchandise by quantity")
    best = load_df("""
        SELECT p.product_name AS "Product", SUM(si.quantity) AS "Qty sold",
               SUM(si.quantity*si.unit_price) AS "Revenue"
        FROM sale s JOIN sale_item si ON si.sale_id=s.sale_id
        JOIN product p ON p.product_id=si.product_id
        WHERE s.sale_datetime::date BETWEEN %s AND %s
        GROUP BY p.product_id,p.product_name
        ORDER BY "Qty sold" DESC LIMIT 10
    """, (start,end))
    st.dataframe(best, use_container_width=True, hide_index=True)
    st.caption("Gross profit is sales revenue minus recorded merchandise costs. It is not net profit; operating expenses are excluded.")

# USER ACCOUNTS
elif page == "User Accounts":
    st.subheader("Create household user account")
    with st.form("create_user"):
        full_name = st.text_input("Full name")
        username = st.text_input("Username")
        password = st.text_input("Temporary password", type="password")
        role = st.selectbox("Role", ["Manager", "Cashier"])
        save_user = st.form_submit_button("Create account")
    if save_user:
        if not full_name.strip() or not username.strip() or not password:
            st.error("Complete all required fields.")
        else:
            from db import hash_password
            try:
                execute("""INSERT INTO app_user(full_name,username,password_hash,role)
                           VALUES (%s,%s,%s,%s)""",
                        (full_name.strip(),username.strip(),hash_password(password),role))
                st.success("User account created.")
            except Exception as e:
                st.error(f"Could not create account: {e}")
    st.subheader("Existing accounts")
    users = load_df("SELECT full_name AS \"Name\", username AS \"Username\", role AS \"Role\", is_active AS \"Active\" FROM app_user ORDER BY full_name")
    st.dataframe(users, use_container_width=True, hide_index=True)

st.divider()
st.caption("TorreonTrack | Proposed local store application")
