import os

import redis
from flask import Flask, jsonify, request

from models import db, Product, Order, OrderItem
from seed import seed_products

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///shop.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
CART_TTL = int(os.environ.get('CART_TTL_SECONDS', 60 * 60 * 24 * 7))  # 7 days
r = redis.from_url(REDIS_URL, decode_responses=True)

with app.app_context():
    db.create_all()
    seed_products()


@app.route('/health')
def health():
    try:
        r.ping()
        return jsonify(status='ok', service='api')
    except redis.RedisError:
        return jsonify(status='degraded', service='api'), 503


# --- products (MySQL) --------------------------------------------------------

@app.route('/products')
def list_products():
    return jsonify([p.to_dict() for p in Product.query.all()])


@app.route('/products/<int:product_id>')
def get_product(product_id):
    product = Product.query.get(product_id)
    if product is None:
        return jsonify(error='Product not found'), 404
    return jsonify(product.to_dict())


# --- cart (Redis) ------------------------------------------------------------

def _cart_key(cart_id):
    return f'cart:{cart_id}'


def _cart_items(cart_id):
    raw = r.hgetall(_cart_key(cart_id))
    return {pid: int(qty) for pid, qty in raw.items()}


@app.route('/carts/<cart_id>')
def get_cart(cart_id):
    return jsonify(cart_id=cart_id, items=_cart_items(cart_id))


@app.route('/carts/<cart_id>/items', methods=['POST'])
def add_cart_item(cart_id):
    data = request.get_json(force=True, silent=True) or {}
    product_id = data.get('product_id')
    quantity = int(data.get('quantity', 1))
    if product_id in (None, '') or quantity < 1:
        return jsonify(error='product_id and a positive quantity are required'), 400
    key = _cart_key(cart_id)
    r.hincrby(key, str(product_id), quantity)
    r.expire(key, CART_TTL)
    return jsonify(cart_id=cart_id, items=_cart_items(cart_id))


@app.route('/carts/<cart_id>/items/<product_id>', methods=['DELETE'])
def remove_cart_item(cart_id, product_id):
    r.hdel(_cart_key(cart_id), str(product_id))
    return jsonify(cart_id=cart_id, items=_cart_items(cart_id))


@app.route('/carts/<cart_id>', methods=['DELETE'])
def clear_cart(cart_id):
    r.delete(_cart_key(cart_id))
    return jsonify(cart_id=cart_id, items={})


# --- orders (MySQL) ----------------------------------------------------------

@app.route('/orders', methods=['POST'])
def create_order():
    data = request.get_json(force=True, silent=True) or {}
    if not all(data.get(f) for f in ('customer_name', 'customer_email', 'address')):
        return jsonify(error='customer_name, customer_email and address are required'), 400
    line_items = data.get('items') or []
    if not line_items:
        return jsonify(error='order must contain at least one item'), 400

    # Resolve each line item against the product catalog so price/name are
    # authoritative snapshots, never trusting whatever the caller sent for price.
    resolved = []
    total = 0.0
    try:
        for li in line_items:
            pid = int(li['product_id'])
            qty = int(li.get('quantity', 1))
            if qty < 1:
                return jsonify(error=f'invalid quantity for product {pid}'), 400
            product = Product.query.get(pid)
            if product is None:
                return jsonify(error=f'product {pid} not found'), 400
            price = float(product.price)
            total += price * qty
            resolved.append({
                'product_id': pid,
                'product_name': product.name,
                'quantity': qty,
                'price': price,
            })
    except (KeyError, ValueError, TypeError):
        return jsonify(error='each item needs a numeric product_id and quantity'), 400

    order = Order(
        customer_name=data['customer_name'],
        customer_email=data['customer_email'],
        address=data['address'],
        total=total,
    )
    db.session.add(order)
    db.session.flush()
    for item in resolved:
        db.session.add(OrderItem(order_id=order.id, **item))
    db.session.commit()
    return jsonify(order.to_dict()), 201


@app.route('/orders')
def list_orders():
    orders = Order.query.order_by(Order.created_at.desc()).all()
    return jsonify([o.to_dict() for o in orders])


@app.route('/orders/<int:order_id>')
def get_order(order_id):
    order = Order.query.get(order_id)
    if order is None:
        return jsonify(error='Order not found'), 404
    return jsonify(order.to_dict())


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8001, debug=True)
