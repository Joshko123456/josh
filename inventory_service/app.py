from flask import Flask, request, Response
from flask_cors import CORS
import xml.etree.ElementTree as ET
from sqlalchemy import create_engine, Column, String, Integer, Float
from sqlalchemy.orm import declarative_base, sessionmaker

app = Flask(__name__)
CORS(app)

# ── Database Setup ──────────────────────────────────────────────────────────
import mysql.connector
import os

conn = mysql.connector.connect(
    host=os.environ.get("gateway01.ap-southeast-1.prod.alicloud.tidbcloud.com"),
    port=4000,
    user=os.environ.get("45dhqdYGrnFxjYF.root"),
    password=os.environ.get("mUrsVv2UppsEdhR6"),
    database=os.environ.get("techvault"),
    ssl_disabled=False
)
engine = create_engine(DATABASE_URL)
Base = declarative_base()

class InventoryItem(Base):
    __tablename__ = 'inventory'
    code     = Column(String(20), primary_key=True)
    name     = Column(String(100))
    category = Column(String(50))
    stock    = Column(Integer)
    price    = Column(Float)

Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

# ── Seed data (runs only if table is empty) ─────────────────────────────────
SEED_DATA = [
    InventoryItem(code="ACC-001", name="iPhone 15 Pro Case",    category="CASE",    stock=500, price=12.99),
    InventoryItem(code="ACC-002", name="Samsung Fast Charger",  category="CHARGER", stock=350, price=18.50),
    InventoryItem(code="ACC-003", name="USB-C Cable 2m",        category="CABLE",   stock=800, price=8.99),
    InventoryItem(code="ACC-004", name="Wireless Earbuds Pro",  category="EARBUDS", stock=200, price=45.00),
    InventoryItem(code="ACC-005", name="Screen Protector Glass",category="GLASS",   stock=600, price=6.50),
    InventoryItem(code="ACC-006", name="Power Bank 20000mAh",   category="POWER",   stock=150, price=32.00),
    InventoryItem(code="ACC-007", name="Car Phone Holder",      category="HOLDER",  stock=280, price=15.75),
    InventoryItem(code="ACC-008", name="Lightning Adapter",     category="ADAPTER", stock=420, price=9.99),
    InventoryItem(code="ACC-009", name="Wireless Charger Pad",  category="CHARGER", stock=180, price=22.00),
    InventoryItem(code="ACC-010", name="Phone Stand Desktop",   category="HOLDER",  stock=320, price=11.25),
]

with Session() as s:
    if s.query(InventoryItem).count() == 0:
        s.add_all(SEED_DATA)
        s.commit()

# ── Routes ───────────────────────────────────────────────────────────────────

@app.route('/inventory', methods=['GET'])
def get_inventory():
    """Return all inventory items as XML."""
    with Session() as s:
        items = s.query(InventoryItem).all()
        root = ET.Element('Inventory')
        for item in items:
            el = ET.SubElement(root, 'Item')
            ET.SubElement(el, 'Code').text     = item.code
            ET.SubElement(el, 'Name').text     = item.name
            ET.SubElement(el, 'Category').text = item.category
            ET.SubElement(el, 'Stock').text    = str(item.stock)
            ET.SubElement(el, 'Price').text    = str(item.price)
        return Response(ET.tostring(root, encoding='unicode'), mimetype='application/xml')


@app.route('/update_inventory', methods=['POST'])
def update_inventory():
    """Deduct stock based on order quantity (called by order_service)."""
    root = ET.fromstring(request.data)
    code     = root.find('ProductCode').text
    quantity = int(root.find('Quantity').text)

    response_el = ET.Element('InventoryResponse')
    with Session() as s:
        item = s.query(InventoryItem).filter_by(code=code).first()
        if item:
            if item.stock >= quantity:
                item.stock -= quantity   # UPDATE
                s.commit()
                ET.SubElement(response_el, 'Status').text        = 'Success'
                ET.SubElement(response_el, 'RemainingStock').text = str(item.stock)
                ET.SubElement(response_el, 'Product').text       = item.name
                ET.SubElement(response_el, 'Category').text      = item.category
                ET.SubElement(response_el, 'Price').text         = str(item.price)
            else:
                ET.SubElement(response_el, 'Status').text  = 'Failed'
                ET.SubElement(response_el, 'Message').text = f"Insufficient stock. Available: {item.stock} units"
        else:
            ET.SubElement(response_el, 'Status').text  = 'Failed'
            ET.SubElement(response_el, 'Message').text = 'Product code not found in inventory'

    return Response(ET.tostring(response_el, encoding='unicode'), mimetype='application/xml')


@app.route('/add_item', methods=['POST'])
def add_item():
    """Add a new inventory item."""
    root = ET.fromstring(request.data)
    code     = root.find('Code').text
    name     = root.find('Name').text
    category = root.find('Category').text
    stock    = int(root.find('Stock').text)
    price    = float(root.find('Price').text)

    response_el = ET.Element('InventoryResponse')
    with Session() as s:
        existing = s.query(InventoryItem).filter_by(code=code).first()
        if existing:
            ET.SubElement(response_el, 'Status').text  = 'Failed'
            ET.SubElement(response_el, 'Message').text = 'Product code already exists'
        else:
            new_item = InventoryItem(code=code, name=name, category=category, stock=stock, price=price)
            s.add(new_item)   # ADD
            s.commit()
            ET.SubElement(response_el, 'Status').text  = 'Success'
            ET.SubElement(response_el, 'Message').text = f"Item '{name}' added successfully"

    return Response(ET.tostring(response_el, encoding='unicode'), mimetype='application/xml')


@app.route('/edit_item', methods=['POST'])
def edit_item():
    """Update an existing inventory item's name, price, or stock."""
    root = ET.fromstring(request.data)
    code = root.find('Code').text

    response_el = ET.Element('InventoryResponse')
    with Session() as s:
        item = s.query(InventoryItem).filter_by(code=code).first()
        if not item:
            ET.SubElement(response_el, 'Status').text  = 'Failed'
            ET.SubElement(response_el, 'Message').text = 'Product code not found'
        else:
            # Only update fields that are provided
            if root.find('Name')  is not None: item.name  = root.find('Name').text
            if root.find('Price') is not None: item.price = float(root.find('Price').text)
            if root.find('Stock') is not None: item.stock = int(root.find('Stock').text)
            s.commit()   # UPDATE
            ET.SubElement(response_el, 'Status').text   = 'Success'
            ET.SubElement(response_el, 'Message').text  = f"Item '{item.name}' updated successfully"
            ET.SubElement(response_el, 'Code').text     = item.code
            ET.SubElement(response_el, 'Name').text     = item.name
            ET.SubElement(response_el, 'Price').text    = str(item.price)
            ET.SubElement(response_el, 'Stock').text    = str(item.stock)
            ET.SubElement(response_el, 'Category').text = item.category

    return Response(ET.tostring(response_el, encoding='unicode'), mimetype='application/xml')


@app.route('/delete_item', methods=['POST'])
def delete_item():
    """Delete an inventory item by code."""
    root = ET.fromstring(request.data)
    code = root.find('Code').text

    response_el = ET.Element('InventoryResponse')
    with Session() as s:
        item = s.query(InventoryItem).filter_by(code=code).first()
        if not item:
            ET.SubElement(response_el, 'Status').text  = 'Failed'
            ET.SubElement(response_el, 'Message').text = 'Product code not found'
        else:
            name = item.name
            s.delete(item)   # DELETE
            s.commit()
            ET.SubElement(response_el, 'Status').text  = 'Success'
            ET.SubElement(response_el, 'Message').text = f"Item '{name}' deleted successfully"

    return Response(ET.tostring(response_el, encoding='unicode'), mimetype='application/xml')


import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)