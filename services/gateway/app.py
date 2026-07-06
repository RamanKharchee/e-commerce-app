import os
import uuid

import requests
from flask import Flask, render_template, request, redirect, url_for, session, flash
from prometheus_flask_exporter import PrometheusMetrics

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-change-me')

# Exposes GET /metrics and auto-instruments every route with request
# count / latency (flask_http_request_*), scraped by Prometheus.
metrics = PrometheusMetrics(app)
metrics.info('app_info', 'Application info', service='gateway', version='1.0.0')

PRODUCT_SERVICE_URL = os.environ.get('PRODUCT_SERVICE_URL', 'http://localhost:8001')
CART_SERVICE_URL = os.environ.get('CART_SERVICE_URL', 'http://localhost:8003')
ORDER_SERVICE_URL = os.environ.get('ORDER_SERVICE_URL', 'http://localhost:8002')
HTTP_TIMEOUT = float(os.environ.get('HTTP_TIMEOUT', '5'))


def cart_id():
    """A stable per-browser cart id kept in the signed session cookie."""
    if 'cart_id' not in session:
        session['cart_id'] = uuid.uuid4().hex
    return session['cart_id']


# --- service clients ---------------------------------------------------------

def get_products():
    resp = requests.get(f'{PRODUCT_SERVICE_URL}/products', timeout=HTTP_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def get_product(product_id):
    resp = requests.get(f'{PRODUCT_SERVICE_URL}/products/{product_id}', timeout=HTTP_TIMEOUT)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


def get_cart_items():
    resp = requests.get(f'{CART_SERVICE_URL}/carts/{cart_id()}', timeout=HTTP_TIMEOUT)
    resp.raise_for_status()
    return resp.json().get('items', {})


def cart_items_and_total():
    """Join the cart (product_id -> qty) with live product details."""
    items = []
    total = 0.0
    for pid, qty in get_cart_items().items():
        product = get_product(pid)
        if product:
            subtotal = product['price'] * qty
            total += subtotal
            items.append({'product': product, 'quantity': qty, 'subtotal': subtotal})
    return items, total


# --- routes (mirror the original monolith) -----------------------------------

@app.route('/health')
def health():
    return {'status': 'ok', 'service': 'gateway'}


@app.route('/')
def index():
    products = get_products()
    return render_template('index.html', products=products)


@app.route('/product/<int:product_id>')
def product_detail(product_id):
    product = get_product(product_id)
    if product is None:
        flash('Product not found')
        return redirect(url_for('index'))
    return render_template('product.html', product=product)


@app.route('/cart/add/<int:product_id>', methods=['POST'])
def add_to_cart(product_id):
    qty = max(1, int(request.form.get('quantity', 1)))
    resp = requests.post(
        f'{CART_SERVICE_URL}/carts/{cart_id()}/items',
        json={'product_id': product_id, 'quantity': qty},
        timeout=HTTP_TIMEOUT,
    )
    resp.raise_for_status()
    flash('Added to cart')
    return redirect(url_for('view_cart'))


@app.route('/cart')
def view_cart():
    items, total = cart_items_and_total()
    return render_template('cart.html', items=items, total=total)


@app.route('/cart/remove/<int:product_id>', methods=['POST'])
def remove_from_cart(product_id):
    resp = requests.delete(
        f'{CART_SERVICE_URL}/carts/{cart_id()}/items/{product_id}',
        timeout=HTTP_TIMEOUT,
    )
    resp.raise_for_status()
    return redirect(url_for('view_cart'))


@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    items, total = cart_items_and_total()
    if not items:
        return redirect(url_for('index'))

    if request.method == 'POST':
        payload = {
            'customer_name': request.form['name'],
            'customer_email': request.form['email'],
            'address': request.form['address'],
            'items': [
                {'product_id': it['product']['id'], 'quantity': it['quantity']}
                for it in items
            ],
        }
        resp = requests.post(f'{ORDER_SERVICE_URL}/orders', json=payload, timeout=HTTP_TIMEOUT)
        resp.raise_for_status()
        order = resp.json()
        # Order placed -> clear the cart (best-effort).
        requests.delete(f'{CART_SERVICE_URL}/carts/{cart_id()}', timeout=HTTP_TIMEOUT)
        return redirect(url_for('order_success', order_id=order['id']))

    return render_template('checkout.html', items=items, total=total)


@app.route('/order/<int:order_id>')
def order_success(order_id):
    resp = requests.get(f'{ORDER_SERVICE_URL}/orders/{order_id}', timeout=HTTP_TIMEOUT)
    if resp.status_code == 404:
        flash('Order not found')
        return redirect(url_for('index'))
    resp.raise_for_status()
    return render_template('order_success.html', order=resp.json())


@app.route('/orders')
def list_orders():
    resp = requests.get(f'{ORDER_SERVICE_URL}/orders', timeout=HTTP_TIMEOUT)
    resp.raise_for_status()
    return render_template('orders.html', orders=resp.json())


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)
