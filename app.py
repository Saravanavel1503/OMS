# app.py - The Python Flask backend for the Bike Accessories Management System
# This file handles all data logic and API endpoints, including database management and PDF generation.

from flask import Flask, jsonify, request, send_from_directory, Response
from flask_cors import CORS
import sqlite3
from datetime import datetime
import json
from fpdf import FPDF
import sys, os

app = Flask(__name__)
# Enable CORS to allow the frontend to access the API
CORS(app)

GST_RATE = 0.05  # Default GST rate as a decimal


def _bundle_dir():
    # Folder where PyInstaller unpacks files at runtime
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

def _app_data_dir():
    # %LOCALAPPDATA%\OMSApp  (no admin needed)
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    target = os.path.join(base, "OMSApp")
    os.makedirs(target, exist_ok=True)
    return target

# Use a per-user DB path
DATABASE = os.path.join(_app_data_dir(), "simple.db")

# (Optional) Seed from bundled simple.db on first run
# if not os.path.exists(DATABASE):
#     bundled_db = os.path.join(_bundle_dir(), "simple.db")
#     if os.path.exists(bundled_db):
#         shutil.copyfile(bundled_db, DATABASE)


# --- Database Initialization and Management ---

def ensure_orders_has_gst_rate_column():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    try:
        cursor.execute("PRAGMA table_info(orders)")
        cols = {row[1] for row in cursor.fetchall()}  # set of column names
        if 'gst_rate' not in cols:
            # Add with a default equal to your app-level GST_RATE
            cursor.execute("ALTER TABLE orders ADD COLUMN gst_rate REAL DEFAULT ?", (float(GST_RATE),))
            conn.commit()
    finally:
        conn.close()

def init_db():
    """
    Initializes the SQLite database with products, categories, orders, and order_items tables.
    This function now dynamically checks and updates the schema for both 'orders' and 'order_items'
    to ensure all necessary columns are present, including gst_rate in orders.
    """
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")
    # Create the categories table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            name TEXT PRIMARY KEY
        )
    ''')

    # Products (inventory) table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            sku TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT,
            quantity INTEGER NOT NULL,
            price REAL NOT NULL,
            FOREIGN KEY(category) REFERENCES categories(name) ON DELETE SET NULL
        )
    ''')

    # Ensure order_id_sequence exists
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS order_id_sequence (
            id INTEGER PRIMARY KEY,
            last_number INTEGER NOT NULL
        )
    ''')
    cursor.execute("SELECT * FROM order_id_sequence WHERE id = 1")
    if cursor.fetchone() is None:
        cursor.execute("INSERT INTO order_id_sequence (id, last_number) VALUES (1, 0)")
        conn.commit()

    # Orders table (force recreate if missing essential columns)
    cursor.execute("PRAGMA table_info(orders)")
    orders_columns = [info[1] for info in cursor.fetchall()]
    if ('orders' not in [row[0] for row in cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='orders'")] or
        'email_address' not in orders_columns or
        'planned_delivery_date' not in orders_columns or
        'gst_rate' not in orders_columns):
        print("Recreating 'orders' table with gst_rate...")
        cursor.execute("DROP TABLE IF EXISTS orders")
        cursor.execute(f'''
            CREATE TABLE orders (
                id TEXT PRIMARY KEY,
                customer_name TEXT NOT NULL,
                mobile_number TEXT NOT NULL,
                email_address TEXT,
                order_date TEXT NOT NULL,
                planned_delivery_date TEXT,
                payment_method TEXT,
                advance_received REAL,
                personalization_required INTEGER DEFAULT 0,
                personalization_details TEXT,
                total_cost REAL NOT NULL,
                gst_rate REAL NOT NULL DEFAULT {float(GST_RATE)}
            )
        ''')

    # Order items table (force recreate if missing product_sku)
    cursor.execute("PRAGMA table_info(order_items)")
    order_items_columns = [info[1] for info in cursor.fetchall()]
    if ('order_items' not in [row[0] for row in cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='order_items'")] or
        'product_sku' not in order_items_columns):
        print("Recreating 'order_items' table...")
        cursor.execute("DROP TABLE IF EXISTS order_items")
        cursor.execute('''
            CREATE TABLE order_items (
                order_id TEXT,
                product_sku TEXT,
                quantity INTEGER NOT NULL,
                price REAL NOT NULL,
                product_name TEXT NOT NULL,
                FOREIGN KEY(order_id) REFERENCES orders(id) ON DELETE CASCADE,
                FOREIGN KEY(product_sku) REFERENCES products(sku) ON DELETE SET NULL
            )
        ''')

    conn.commit()
    conn.close()


# --- API Endpoints ---
@app.route('/api/products', methods=['POST'])
def add_product():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    product = request.json
    try:
        cursor.execute("INSERT INTO products (sku, name, category, quantity, price) VALUES (?, ?, ?, ?, ?)",
                       (product['sku'], product['name'], product['category'], product['quantity'], product['price']))
        conn.commit()
        return jsonify({"message": "Product added successfully"}), 201
    except sqlite3.IntegrityError:
        return jsonify({"message": "Product with this SKU already exists"}), 409
    finally:
        conn.close()

@app.route('/api/products', methods=['GET'])
def get_products():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("SELECT sku, name, category, quantity, price FROM products")
    products = [{"sku": row[0], "name": row[1], "category": row[2], "quantity": row[3], "price": row[4]} for row in cursor.fetchall()]
    conn.close()
    return jsonify(products)

@app.route('/api/products/<sku>', methods=['PUT'])
def update_product(sku):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    product = request.json
    try:
        cursor.execute("UPDATE products SET name=?, category=?, quantity=?, price=? WHERE sku=?",
                       (product['name'], product['category'], product['quantity'], product['price'], sku))
        conn.commit()
        if cursor.rowcount == 0:
            return jsonify({"message": "Product not found"}), 404
        return jsonify({"message": "Product updated successfully"})
    finally:
        conn.close()

@app.route('/api/products/<sku>', methods=['DELETE'])
def delete_product(sku):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM products WHERE sku=?", (sku,))
        conn.commit()
        if cursor.rowcount == 0:
            return jsonify({"message": "Product not found"}), 404
        return jsonify({"message": "Product deleted successfully"})
    finally:
        conn.close()

@app.route('/api/categories', methods=['POST'])
def add_category():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    category = request.json
    try:
        cursor.execute("INSERT INTO categories (name) VALUES (?)", (category['name'],))
        conn.commit()
        return jsonify({"message": "Category added successfully"}), 201
    except sqlite3.IntegrityError:
        return jsonify({"message": "Category already exists"}), 409
    finally:
        conn.close()

@app.route('/api/categories', methods=['GET'])
def get_categories():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM categories")
    categories = [row[0] for row in cursor.fetchall()]
    conn.close()
    return jsonify(categories)

@app.route('/api/categories/<name>', methods=['DELETE'])
def delete_category(name):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM categories WHERE name=?", (name,))
        conn.commit()
        if cursor.rowcount == 0:
            return jsonify({"message": "Category not found"}), 404
        return jsonify({"message": "Category deleted successfully"})
    finally:
        conn.close()

# NOTE: All /api/bike_models endpoints removed intentionally

@app.route('/api/orders', methods=['POST'])
def handle_create_order():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN IMMEDIATE")

        order_data = request.json
        customer_name = order_data['customerName']
        mobile_number = order_data['mobileNumber']
        email_address = order_data.get('emailAddress')
        order_date = order_data['orderDate']
        planned_delivery_date = order_data.get('plannedDeliveryDate')
        payment_method = order_data.get('paymentMethod')
        advance_received = float(order_data.get('advanceReceived', 0.0))
        personalization_required = 1 if order_data.get('personalizationRequired') else 0
        personalization_details = order_data.get('personalizationDetails', '')
        items = order_data['items']  # [{sku, product_name, quantity, price}, ...]

        # NEW: gstRate (decimal). Fall back to constant if not provided.
        gst_rate = float(order_data.get('gstRate', GST_RATE))

        # Validate all stock first
        for item in items:
            sku = item['sku']
            qty_needed = int(item['quantity'])
            cursor.execute("SELECT quantity, name FROM products WHERE sku=?", (sku,))
            row = cursor.fetchone()
            if row is None:
                raise Exception(f"Product with SKU '{sku}' not found.")
            current_qty, product_name = int(row[0]), row[1]
            if current_qty < qty_needed:
                raise Exception(f"Insufficient stock for {product_name} (SKU: {sku}). "
                                f"Available: {current_qty}, requested: {qty_needed}.")

        # Allocate order id
        cursor.execute("SELECT last_number FROM order_id_sequence WHERE id = 1")
        last_number = cursor.fetchone()[0]
        new_number = last_number + 1
        new_order_id = f"ORD{new_number:04d}"
        cursor.execute("UPDATE order_id_sequence SET last_number = ? WHERE id = 1", (new_number,))

        # 3) Totals
        subtotal = sum(float(item['price']) * int(item['quantity']) for item in items)
        total_cost = subtotal + (subtotal * gst_rate)

        # Insert order header (NOTICE: gst_rate column)
        cursor.execute("""
            INSERT INTO orders (
                id, customer_name, mobile_number, email_address, order_date,
                planned_delivery_date, payment_method, advance_received,
                personalization_required, personalization_details, total_cost, gst_rate
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            new_order_id, customer_name, mobile_number, email_address, order_date,
            planned_delivery_date, payment_method, advance_received,
            personalization_required, personalization_details, total_cost, gst_rate
        ))

        for item in items:
            cursor.execute("""
                INSERT INTO order_items (order_id, product_sku, quantity, price, product_name)
                VALUES (?, ?, ?, ?, ?)
            """, (new_order_id, item['sku'], int(item['quantity']), float(item['price']), item['product_name']))

        # 5) Subtract stock (after successful inserts)
        for item in items:
            cursor.execute("""
                UPDATE products SET quantity = quantity - ?
                WHERE sku = ?
            """, (int(item['quantity']), item['sku']))
            if cursor.rowcount == 0:
                raise Exception(f"Failed to update inventory for SKU '{item['sku']}'.")

        conn.commit()
        return jsonify({"message": "Order placed successfully", "order_id": new_order_id}), 201

    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 400
    finally:
        conn.close()



@app.route('/api/orders', methods=['GET'])
def get_orders():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, customer_name, mobile_number, order_date, planned_delivery_date, total_cost FROM orders ORDER BY id DESC")
    orders = [{"id": row[0], "customerName": row[1], "mobileNumber": row[2], "orderDate": row[3], "plannedDeliveryDate": row[4], "totalCost": row[5]} for row in cursor.fetchall()]
    conn.close()
    return jsonify(orders)

@app.route('/api/orders/<order_id>', methods=['GET'])
def get_order(order_id):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT id, customer_name, mobile_number, email_address, order_date,
                   planned_delivery_date, payment_method, advance_received,
                   personalization_required, personalization_details, total_cost, gst_rate
            FROM orders WHERE id=?
        """, (order_id,))
        row = cursor.fetchone()
        if not row:
            return jsonify({"error": "Order not found"}), 404

        (oid, cname, mobile, email, odate, pdd, pmethod, adv, pers_req, pers_det, total, gst_rate) = row

        cursor.execute("""
            SELECT product_sku, product_name, quantity, price
              FROM order_items
             WHERE order_id=?
        """, (order_id,))
        items = []
        for sku, pname, qty, price in cursor.fetchall():
            items.append({
                "sku": sku,
                "product_name": pname,
                "quantity": int(qty),
                "price": float(price)
            })

        return jsonify({
            "id": oid,
            "customerName": cname,
            "mobileNumber": mobile,
            "emailAddress": email,
            "orderDate": odate,
            "plannedDeliveryDate": pdd,
            "paymentMethod": pmethod,
            "advanceReceived": float(adv or 0.0),
            "personalizationRequired": bool(pers_req),
            "personalizationDetails": pers_det or "",
            "totalCost": float(total or 0.0),
            "gstRate": float(gst_rate if gst_rate is not None else GST_RATE),
            "items": items
        })
    finally:
        conn.close()


@app.route('/api/orders/<order_id>', methods=['PUT'])
def update_order(order_id):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN IMMEDIATE")

        order_data = request.json
        customer_name = order_data['customerName']
        mobile_number = order_data['mobileNumber']
        email_address = order_data.get('emailAddress')
        order_date = order_data['orderDate']
        planned_delivery_date = order_data.get('plannedDeliveryDate')
        payment_method = order_data.get('paymentMethod') or None
        advance_received = float(order_data.get('advanceReceived', 0.0))
        personalization_required = 1 if order_data.get('personalizationRequired') else 0
        personalization_details = order_data.get('personalizationDetails', '')

        new_items = order_data['items']  # [{sku, product_name, quantity, price}, ...]
        # NEW: gstRate (decimal). Fall back to stored value if not provided.
        incoming_gst_rate = order_data.get('gstRate', None)

        # Load previous items -> old map
        cursor.execute("SELECT product_sku, quantity FROM order_items WHERE order_id=?", (order_id,))
        old_items = {}
        for sku, qty in cursor.fetchall():
            old_items[sku] = old_items.get(sku, 0) + int(qty)

        # Build new map
        new_map = {}
        for it in new_items:
            new_map[it['sku']] = new_map.get(it['sku'], 0) + int(it['quantity'])

        # Deltas
        deltas = {}
        for sku in set(old_items.keys()) | set(new_map.keys()):
            deltas[sku] = new_map.get(sku, 0) - old_items.get(sku, 0)

        # Validate positive deltas against stock
        for sku, delta in deltas.items():
            if delta > 0:
                cursor.execute("SELECT quantity, name FROM products WHERE sku=?", (sku,))
                row = cursor.fetchone()
                if row is None:
                    raise Exception(f"Product with SKU '{sku}' not found.")
                current_qty, product_name = int(row[0]), row[1]
                if current_qty < delta:
                    raise Exception(f"Insufficient stock for {product_name} (SKU: {sku}). "
                                    f"Available: {current_qty}, additional needed: {delta}.")

        # If gstRate not in payload, use the existing stored one
        if incoming_gst_rate is None:
            cursor.execute("SELECT gst_rate FROM orders WHERE id=?", (order_id,))
            row = cursor.fetchone()
            stored_gst = float(row[0]) if row and row[0] is not None else float(GST_RATE)
            gst_rate = stored_gst
        else:
            gst_rate = float(incoming_gst_rate)

        # Recompute totals with gst_rate
        subtotal = sum(float(it['price']) * int(it['quantity']) for it in new_items)
        total_cost = subtotal + (subtotal * gst_rate)

        # Update order header (+ gst_rate)
        cursor.execute("""
            UPDATE orders
               SET customer_name=?, mobile_number=?, email_address=?, order_date=?,
                   planned_delivery_date=?, payment_method=?, advance_received=?,
                   personalization_required=?, personalization_details=?, total_cost=?, gst_rate=?
             WHERE id=?
        """, (
            customer_name, mobile_number, email_address, order_date,
            planned_delivery_date, payment_method, advance_received,
            personalization_required, personalization_details, total_cost, gst_rate, order_id
        ))
        if cursor.rowcount == 0:
            raise Exception("Order not found")

        # Replace items
        cursor.execute("DELETE FROM order_items WHERE order_id=?", (order_id,))
        for it in new_items:
            cursor.execute("""
                INSERT INTO order_items (order_id, product_sku, quantity, price, product_name)
                VALUES (?, ?, ?, ?, ?)
            """, (order_id, it['sku'], int(it['quantity']), float(it['price']), it['product_name']))

        # Apply stock deltas
        for sku, delta in deltas.items():
            if delta != 0:
                cursor.execute("""
                    UPDATE products SET quantity = quantity - ?
                    WHERE sku = ?
                """, (int(delta), sku))

        conn.commit()
        return jsonify({"message": "Order updated successfully", "order_id": order_id}), 200

    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 400
    finally:
        conn.close()



@app.route('/api/orders/<order_id>', methods=['DELETE'])
def delete_order(order_id):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    try:
        # Atomic section: return stock then delete
        cursor.execute("BEGIN IMMEDIATE")

        # Fetch items to restore inventory
        cursor.execute("SELECT product_sku, quantity FROM order_items WHERE order_id=?", (order_id,))
        rows = cursor.fetchall()
        if not rows:
            # If there are no items, still attempt to delete the order (may be already gone)
            cursor.execute("DELETE FROM orders WHERE id=?", (order_id,))
            conn.commit()
            if cursor.rowcount == 0:
                return jsonify({"message": "Order not found"}), 404
            return jsonify({"message": "Order deleted successfully"}), 200

        # Return stock for each line
        for sku, qty in rows:
            cursor.execute("""
                UPDATE products SET quantity = quantity + ?
                WHERE sku = ?
            """, (int(qty), sku))
            # If product row missing, we still proceed; inventory can't be restored for a deleted product.

        # Delete order rows
        cursor.execute("DELETE FROM order_items WHERE order_id=?", (order_id,))
        cursor.execute("DELETE FROM orders WHERE id=?", (order_id,))

        conn.commit()
        if cursor.rowcount == 0:
            return jsonify({"message": "Order not found"}), 404
        return jsonify({"message": "Order deleted successfully"}), 200

    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 400
    finally:
        conn.close()


@app.route('/api/invoice_pdf/<order_id>', methods=['GET'])
def generate_invoice_pdf(order_id):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    try:
        # Load header (includes gst_rate)
        cursor.execute("""
            SELECT customer_name, mobile_number, email_address, order_date,
                   planned_delivery_date, payment_method, advance_received, gst_rate
              FROM orders WHERE id=?
        """, (order_id,))
        hdr = cursor.fetchone()
        if not hdr:
            return jsonify({"error": "Order not found"}), 404

        (customer_name, mobile_number, email_address, order_date,
         planned_delivery_date, payment_method, advance_received, gst_rate) = hdr

        if gst_rate is None:
            gst_rate = float(GST_RATE)
        else:
            gst_rate = float(gst_rate)

        # Items
        cursor.execute("""
            SELECT product_name, product_sku, quantity, price
              FROM order_items WHERE order_id=?
        """, (order_id,))
        items = cursor.fetchall()
        #print(items)
        # Totals using gst_rate
        subtotal = sum(float(price) * int(qty) for (_, _, qty, price) in items)
        gst_amount = subtotal * gst_rate
        total_cost = subtotal + gst_amount
        advance = float(advance_received or 0.0)
        balance_due = max(total_cost - advance, 0.0)

        # --- PDF ---
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=16)
        pdf.cell(0, 10, "INVOICE", ln=True, align='C')

        pdf.set_font("Arial", size=12)
        pdf.cell(0, 8, f"Invoice ID: {order_id}", ln=True)
        pdf.cell(0, 8, f"Order Date: {order_date}", ln=True)
        pdf.cell(0, 8, f"Planned Delivery: {planned_delivery_date or 'N/A'}", ln=True)
        pdf.ln(2)
        pdf.cell(0, 8, f"Customer: {customer_name}", ln=True)
        pdf.cell(0, 8, f"Mobile: {mobile_number}", ln=True)
        if email_address:
            pdf.cell(0, 8, f"Email: {email_address}", ln=True)
        if payment_method:
            pdf.cell(0, 8, f"Payment Method: {payment_method}", ln=True)

        pdf.ln(6)
        # Table header
        pdf.set_font("Arial", 'B', 11)
        pdf.cell(80, 8, "Product", 1)
        pdf.cell(25, 8, "SKU", 1)
        pdf.cell(25, 8, "Qty", 1, align='R')
        pdf.cell(30, 8, "Unit Price", 1, align='R')
        pdf.cell(30, 8, "Subtotal", 1, ln=True, align='R')

        pdf.set_font("Arial", size=11)
        for (pname, sku, qty, price) in items:
            line_sub = float(price) * int(qty)
            pdf.cell(80, 8, str(pname), 1)
            pdf.cell(25, 8, str(sku), 1)
            pdf.cell(25, 8, f"{int(qty)}", 1, align='R')
            pdf.cell(30, 8, f"INR {float(price):.2f}", 1, align='R')
            pdf.cell(30, 8, f"INR {line_sub:.2f}", 1, ln=True, align='R')

        pdf.ln(4)
        # Totals
        pdf.cell(140, 8, "Subtotal", 1)
        pdf.cell(40, 8, f"INR {subtotal:.2f}", 1, ln=True, align='R')

        pdf.cell(140, 8, f"GST ({gst_rate*100:.2f}%)", 1)
        pdf.cell(40, 8, f"INR {gst_amount:.2f}", 1, ln=True, align='R')

        pdf.cell(140, 8, "Total Cost", 1)
        pdf.cell(40, 8, f"INR {total_cost:.2f}", 1, ln=True, align='R')

        if advance > 0:
            pdf.cell(140, 8, "Advance Received", 1)
            pdf.cell(40, 8, f"INR {advance:.2f}", 1, ln=True, align='R')

        pdf.cell(140, 8, "Balance Due", 1)
        pdf.cell(40, 8, f"INR {balance_due:.2f}", 1, ln=True, align='R')

        # Return PDF
        return Response(pdf.output(dest='S').encode('latin1'),
                        mimetype='application/pdf',
                        headers={'Content-Disposition': f'attachment; filename=invoice_{order_id}.pdf'})

    except Exception as e:
        return jsonify({"error": str(e)}), 400
    finally:
        conn.close()


@app.route('/api/invoice_pdf/<order_id>', methods=['GET'])
def get_invoice_pdf(order_id):
    pdf, error = generate_invoice_pdf(order_id)
    if error:
        return jsonify({"error": error}), 404

    return Response(pdf.output(dest='S').encode('latin1'), mimetype='application/pdf',
                    headers={'Content-Disposition': f'attachment; filename=invoice_{order_id}.pdf'})


# Serve static files for the frontend
@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000)
