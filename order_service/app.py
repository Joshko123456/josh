from flask import Flask, request, Response
from flask_cors import CORS
import xml.etree.ElementTree as ET
import requests
from datetime import datetime
from sqlalchemy import create_engine, Column, String, Integer, Float
from sqlalchemy.orm import declarative_base, sessionmaker

app = Flask(__name__)
CORS(app)

# ── Database Setup ──────────────────────────────────────────────────────────
import mysql.connector
import os

DB_HOST = os.environ.get("DB_HOST")
DB_USER = os.environ.get("DB_USER")
DB_PASSWORD = os.environ.get("DB_PASSWORD")
DB_NAME = os.environ.get("DB_NAME")

DATABASE_URL = f"mysql+mysqlconnector://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:4000/{DB_NAME}"

from sqlalchemy import create_engine
engine = create_engine(DATABASE_URL)
Base = declarative_base()

class Order(Base):
    __tablename__ = 'orders'
    transaction_id  = Column(String(20),  primary_key=True)
    timestamp       = Column(String(30))
    product_code    = Column(String(20))
    product         = Column(String(100))
    category        = Column(String(50))
    quantity        = Column(Integer)
    price_per_unit  = Column(Float)
    total_amount    = Column(Float)
    status          = Column(String(20))

Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

INVENTORY_URL = 'http://127.0.0.1:5001/update_inventory'
PAYMENT_URL   = 'http://127.0.0.1:5002/process_payment'


# ── Routes ───────────────────────────────────────────────────────────────────

@app.route('/place_order', methods=['POST'])
def place_order():
    root = ET.fromstring(request.data)
    product_code = root.find('ProductCode').text
    quantity     = int(root.find('Quantity').text)

    # 1. Reserve inventory
    inv_resp = requests.post(INVENTORY_URL, data=request.data,
                             headers={'Content-Type': 'application/xml'})
    inv_root = ET.fromstring(inv_resp.content)

    if inv_root.find('Status').text != 'Success':
        return Response(inv_resp.content, mimetype='application/xml')

    product        = inv_root.find('Product').text
    category       = inv_root.find('Category').text
    price_per_unit = float(inv_root.find('Price').text)
    total_amount   = quantity * price_per_unit

    # 2. Process payment
    pay_xml = ET.Element('Payment')
    ET.SubElement(pay_xml, 'Amount').text   = str(total_amount)
    ET.SubElement(pay_xml, 'Product').text  = product
    ET.SubElement(pay_xml, 'Quantity').text = str(quantity)

    pay_resp = requests.post(PAYMENT_URL, data=ET.tostring(pay_xml),
                             headers={'Content-Type': 'application/xml'})
    pay_root = ET.fromstring(pay_resp.content)

    if pay_root.find('Status').text != 'Success':
        return Response(pay_resp.content, mimetype='application/xml')

    transaction_id = pay_root.find('TransactionID').text

    # 3. Save order to MySQL (ADD)
    with Session() as s:
        order = Order(
            transaction_id = transaction_id,
            timestamp      = datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            product_code   = product_code,
            product        = product,
            category       = category,
            quantity       = quantity,
            price_per_unit = price_per_unit,
            total_amount   = total_amount,
            status         = 'Completed'
        )
        s.add(order)
        s.commit()

    # 4. Return success response
    final = ET.Element('OrderResponse')
    ET.SubElement(final, 'Status').text         = 'Success'
    ET.SubElement(final, 'TransactionID').text  = transaction_id
    ET.SubElement(final, 'Product').text        = product
    ET.SubElement(final, 'Quantity').text       = str(quantity)
    ET.SubElement(final, 'PricePerUnit').text   = f"{price_per_unit:.2f}"
    ET.SubElement(final, 'TotalAmount').text    = f"{total_amount:.2f}"
    ET.SubElement(final, 'RemainingStock').text = inv_root.find('RemainingStock').text
    ET.SubElement(final, 'Message').text        = 'Order placed and payment processed successfully'

    return Response(ET.tostring(final, encoding='unicode'), mimetype='application/xml')


@app.route('/order_history', methods=['GET'])
def order_history():
    """Return all orders from MySQL as XML."""
    with Session() as s:
        orders = s.query(Order).all()
        root = ET.Element('Orders')
        for o in orders:
            el = ET.SubElement(root, 'Order')
            ET.SubElement(el, 'TransactionID').text = o.transaction_id
            ET.SubElement(el, 'Timestamp').text     = o.timestamp
            ET.SubElement(el, 'ProductCode').text   = o.product_code
            ET.SubElement(el, 'Product').text       = o.product
            ET.SubElement(el, 'Category').text      = o.category
            ET.SubElement(el, 'Quantity').text      = str(o.quantity)
            ET.SubElement(el, 'PricePerUnit').text  = f"{o.price_per_unit:.2f}"
            ET.SubElement(el, 'TotalAmount').text   = f"{o.total_amount:.2f}"
            ET.SubElement(el, 'Status').text        = o.status
        return Response(ET.tostring(root, encoding='unicode'), mimetype='application/xml')


@app.route('/update_order', methods=['POST'])
def update_order():
    """Update an order's status or quantity (UPDATE)."""
    root = ET.fromstring(request.data)
    txn_id = root.find('TransactionID').text

    response_el = ET.Element('OrderResponse')
    with Session() as s:
        order = s.query(Order).filter_by(transaction_id=txn_id).first()
        if not order:
            ET.SubElement(response_el, 'Status').text  = 'Failed'
            ET.SubElement(response_el, 'Message').text = 'Transaction not found'
        else:
            if root.find('Status')   is not None: order.status   = root.find('Status').text
            if root.find('Quantity') is not None:
                order.quantity     = int(root.find('Quantity').text)
                order.total_amount = order.quantity * order.price_per_unit
            s.commit()   # UPDATE
            ET.SubElement(response_el, 'Status').text        = 'Success'
            ET.SubElement(response_el, 'Message').text       = 'Order updated successfully'
            ET.SubElement(response_el, 'TransactionID').text = order.transaction_id
            ET.SubElement(response_el, 'NewStatus').text     = order.status
            ET.SubElement(response_el, 'Quantity').text      = str(order.quantity)
            ET.SubElement(response_el, 'TotalAmount').text   = f"{order.total_amount:.2f}"

    return Response(ET.tostring(response_el, encoding='unicode'), mimetype='application/xml')


@app.route('/delete_order', methods=['POST'])
def delete_order():
    """Delete an order by TransactionID (DELETE)."""
    root = ET.fromstring(request.data)
    txn_id = root.find('TransactionID').text

    response_el = ET.Element('OrderResponse')
    with Session() as s:
        order = s.query(Order).filter_by(transaction_id=txn_id).first()
        if not order:
            ET.SubElement(response_el, 'Status').text  = 'Failed'
            ET.SubElement(response_el, 'Message').text = 'Transaction not found'
        else:
            s.delete(order)   # DELETE
            s.commit()
            ET.SubElement(response_el, 'Status').text  = 'Success'
            ET.SubElement(response_el, 'Message').text = f"Order {txn_id} deleted successfully"

    return Response(ET.tostring(response_el, encoding='unicode'), mimetype='application/xml')


import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
