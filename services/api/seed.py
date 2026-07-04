from sqlalchemy.exc import IntegrityError

from models import db, Product

PRODUCTS = [
    {'name': 'Wireless Headphones', 'description': 'Noise-cancelling over-ear headphones with 30hr battery.', 'price': 2499.00, 'image_url': 'https://placehold.co/300x300?text=Headphones', 'stock': 15},
    {'name': 'Smart Watch', 'description': 'Fitness tracking, heart rate monitor, GPS.', 'price': 3999.00, 'image_url': 'https://placehold.co/300x300?text=Watch', 'stock': 20},
    {'name': 'Bluetooth Speaker', 'description': 'Portable, water-resistant, 12hr playback.', 'price': 1799.00, 'image_url': 'https://placehold.co/300x300?text=Speaker', 'stock': 25},
    {'name': 'Laptop Backpack', 'description': 'Fits 15.6 inch laptops, USB charging port.', 'price': 1299.00, 'image_url': 'https://placehold.co/300x300?text=Backpack', 'stock': 30},
    {'name': 'Mechanical Keyboard', 'description': 'RGB backlit, blue switches, USB-C.', 'price': 4499.00, 'image_url': 'https://placehold.co/300x300?text=Keyboard', 'stock': 10},
    {'name': 'Wireless Mouse', 'description': 'Ergonomic, 6 programmable buttons.', 'price': 899.00, 'image_url': 'https://placehold.co/300x300?text=Mouse', 'stock': 40},
    {'name': 'Digital Camera', 'description': '24MP mirrorless camera, 4K video, Wi-Fi, 18-55mm lens kit.', 'price': 34999.00, 'image_url': 'https://placehold.co/300x300?text=Camera', 'stock': 12},
    {'name': 'Cleaning Bot', 'description': 'Robot vacuum with smart mapping, app control, auto-empty dock.', 'price': 18999.00, 'image_url': 'https://placehold.co/300x300?text=Cleaning+Bot', 'stock': 18},
    {'name': 'Washing Machine', 'description': '7kg fully-automatic front-load washer, 1400 RPM, inverter motor.', 'price': 27999.00, 'image_url': 'https://placehold.co/300x300?text=Washing+Machine', 'stock': 10},
]


def seed_products():
    """Idempotently seed the catalog. Safe to call on every startup."""
    added = 0
    for p in PRODUCTS:
        if not Product.query.filter_by(name=p['name']).first():
            db.session.add(Product(**p))
            added += 1
    if not added:
        print('Catalog already seeded, nothing to do')
        return
    try:
        db.session.commit()
        print(f'Seeded {added} new product(s)')
    except IntegrityError:
        # Another worker/instance seeded concurrently; the unique name guard tripped.
        db.session.rollback()
        print('Catalog seeded concurrently by another worker')


if __name__ == '__main__':
    from app import app
    with app.app_context():
        db.create_all()
        seed_products()
