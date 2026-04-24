from flask import Flask, request, Response
from flask_cors import CORS
import xml.etree.ElementTree as ET

app = Flask(__name__)
CORS(app)

@app.route('/process_payment', methods=['POST'])
def process_payment():
    xml_data = request.data
    root = ET.fromstring(xml_data)

    amount = float(root.find('Amount').text)
    product = root.find('Product').text
    quantity = int(root.find('Quantity').text)

    response_el = ET.Element('PaymentResponse')

    if amount > 0 and quantity > 0:
        ET.SubElement(response_el, 'Status').text = 'Success'
        ET.SubElement(response_el, 'TransactionID').text = f"TXN-{abs(hash(f'{product}{amount}')) % 1000000:06d}"
        ET.SubElement(response_el, 'Amount').text = f"{amount:.2f}"
        ET.SubElement(response_el, 'Product').text = product
        ET.SubElement(response_el, 'Quantity').text = str(quantity)
        ET.SubElement(response_el, 'Message').text = 'Payment processed successfully'
    else:
        ET.SubElement(response_el, 'Status').text = 'Failed'
        ET.SubElement(response_el, 'Message').text = 'Invalid payment amount or quantity'

    return Response(ET.tostring(response_el, encoding='unicode'), mimetype='application/xml')

@app.route('/ping', methods=['GET'])
def ping():
    return Response('<status>ok</status>', mimetype='application/xml')

import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

