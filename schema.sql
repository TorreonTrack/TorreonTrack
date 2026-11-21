CREATE TABLE IF NOT EXISTS app_user (
    user_id SERIAL PRIMARY KEY,
    full_name VARCHAR(80) NOT NULL,
    username VARCHAR(30) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role VARCHAR(10) NOT NULL CHECK (role IN ('Owner','Manager','Cashier')),
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS category (
    category_id SERIAL PRIMARY KEY,
    category_name VARCHAR(40) UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS supplier (
    supplier_id SERIAL PRIMARY KEY,
    supplier_name VARCHAR(80) NOT NULL,
    contact_no VARCHAR(30)
);

CREATE TABLE IF NOT EXISTS product (
    product_id SERIAL PRIMARY KEY,
    product_name VARCHAR(80) NOT NULL,
    category_id INTEGER NOT NULL REFERENCES category(category_id),
    price NUMERIC(12,2) NOT NULL CHECK (price > 0),
    stock NUMERIC(12,3) NOT NULL DEFAULT 0 CHECK (stock >= 0),
    reorder_level NUMERIC(12,3) NOT NULL DEFAULT 0 CHECK (reorder_level >= 0),
    average_cost NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (average_cost >= 0),
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS customer (
    customer_id SERIAL PRIMARY KEY,
    display_name VARCHAR(80) NOT NULL,
    contact_no VARCHAR(30),
    tab_limit NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (tab_limit >= 0),
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS delivery (
    delivery_id SERIAL PRIMARY KEY,
    supplier_id INTEGER NOT NULL REFERENCES supplier(supplier_id),
    delivery_date TIMESTAMP NOT NULL DEFAULT NOW(),
    user_id INTEGER NOT NULL REFERENCES app_user(user_id)
);

CREATE TABLE IF NOT EXISTS delivery_item (
    delivery_id INTEGER NOT NULL REFERENCES delivery(delivery_id),
    product_id INTEGER NOT NULL REFERENCES product(product_id),
    quantity NUMERIC(12,3) NOT NULL CHECK (quantity > 0),
    unit_cost NUMERIC(12,2) NOT NULL CHECK (unit_cost > 0),
    PRIMARY KEY (delivery_id, product_id)
);

CREATE TABLE IF NOT EXISTS sale (
    sale_id SERIAL PRIMARY KEY,
    sale_datetime TIMESTAMP NOT NULL DEFAULT NOW(),
    user_id INTEGER NOT NULL REFERENCES app_user(user_id),
    customer_id INTEGER REFERENCES customer(customer_id),
    payment_type VARCHAR(6) NOT NULL CHECK (payment_type IN ('Cash','Credit'))
);

CREATE TABLE IF NOT EXISTS sale_item (
    sale_id INTEGER NOT NULL REFERENCES sale(sale_id),
    product_id INTEGER NOT NULL REFERENCES product(product_id),
    quantity NUMERIC(12,3) NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12,2) NOT NULL CHECK (unit_price > 0),
    unit_cost_at_sale NUMERIC(12,2) NOT NULL CHECK (unit_cost_at_sale >= 0),
    PRIMARY KEY (sale_id, product_id)
);

CREATE TABLE IF NOT EXISTS payment (
    payment_id SERIAL PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customer(customer_id),
    user_id INTEGER NOT NULL REFERENCES app_user(user_id),
    payment_date TIMESTAMP NOT NULL DEFAULT NOW(),
    amount NUMERIC(12,2) NOT NULL CHECK (amount > 0)
);

CREATE INDEX IF NOT EXISTS idx_sale_datetime ON sale(sale_datetime);
CREATE INDEX IF NOT EXISTS idx_sale_customer ON sale(customer_id);
CREATE INDEX IF NOT EXISTS idx_payment_customer ON payment(customer_id);
