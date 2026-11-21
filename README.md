# TorreonTrack – Sales, Inventory and Credit Management System

This is a starter implementation of the system described in the Torreon Store project document.

## Included modules

- Login with individual accounts and roles (Owner, Manager, Cashier)
- Store overview: daily cash sales, tab sales, collections, low stock and outstanding tabs
- New Sale: cash or customer tab, stock validation, cash change calculation
- Stock Lookup
- Products & Stock: categories, add/edit/deactivate products
- Restocking: suppliers, deliveries and weighted-average inventory cost
- Customers & Tabs: customer registration, approved limits, balance/history and payments
- Reports: date range, daily sales, best-selling products and estimated merchandise gross profit
- User Accounts: manager can create household accounts

The app intentionally does **not** process device charging, e-load or GCash transactions, online orders, payroll, delivery or barcode scanning, matching the stated initial project scope.

## Requirements

1. Install Python 3.10 or newer.
2. Install PostgreSQL and create a database named `torreontrack`.
3. Copy `.env.example` to `.env` and enter your PostgreSQL username and password.
4. Open a terminal in this project folder.

## Database setup

Run the schema against your database:

```bash
psql -U postgres -d torreontrack -f schema.sql
```

If your database name is `torreontrack`, use:

```bash
psql -U postgres -d torreontrack -f schema.sql
```

On Windows, you can also open pgAdmin, select the `torreontrack` database, open Query Tool, and execute the contents of `schema.sql`.

## Install and create the first account

```bash
python -m venv venv
```

Windows:

```bash
venv\Scripts\activate
```

macOS/Linux:

```bash
source venv/bin/activate
```

Install packages:

```bash
pip install -r requirements.txt
```

Create the first Owner account:

```bash
python setup_admin.py
```

The script asks for the owner's name, username and password. No default password is built into the project.

## Run the system

```bash
streamlit run app.py
```

Streamlit will show a local address, usually `http://localhost:8501`.


