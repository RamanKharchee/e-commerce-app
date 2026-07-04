# Dummy Shop — Two Services

This is the **two-service** edition of Dummy Shop. The user-facing behaviour (the
pages, the routes, the checkout flow) is unchanged — the three business back-end
concerns (products, cart, orders) are now consolidated behind a single `api` service,
while the `gateway` remains the public Backend-for-Frontend that renders the UI.

## Architecture

```
                        ┌────────────────────────────┐
        browser  ─────► │  gateway  (Flask + Jinja)   │  :8000   public entrypoint / BFF
                        └──────────────┬─────────────┘
                                       ▼
                        ┌────────────────────────────┐
                        │  api  (Flask)               │  :8001   products + cart + orders
                        └───────────┬────────┬────────┘
                                    ▼        ▼
                            shop-db (MySQL)   cart-redis (Redis)
                        products + orders      ephemeral carts

   Orders resolve product price/name in-process against the product tables
   (same DB), so there is no back-end service-to-service HTTP hop.
```

| Service   | Port | Datastore                       | Responsibility                                                |
| --------- | ---- | ------------------------------- | ------------------------------------------------------------- |
| `gateway` | 8000 | session cookie only             | Serves all HTML, orchestrates `api`                           |
| `api`     | 8001 | `shop-db` MySQL + `cart-redis`  | Product catalog, per-browser cart, orders + line items        |

### Why these boundaries?

- **Frontend / back-end split.** The `gateway` is a Backend-for-Frontend: it keeps the
  original Jinja templates and routes, so the UI is byte-for-byte the same, but every
  data access is an HTTP call to `api`.
- **One back-end, mixed stores.** `api` keeps products and orders in MySQL and the
  ephemeral cart in Redis (7-day TTL). The cart id lives in the gateway's signed
  session cookie.
- **Order price snapshots stay.** When an order is placed, `api` reads the product row
  in-process and **snapshots** `product_id`, `name`, and `price` into `OrderItem`, so
  historical orders stay correct even if a product's price later changes.

## Service APIs

All routes below are served by `api` on port 8001 (the `gateway` proxies to them).

**products**
- `GET /products` → list of products
- `GET /products/<id>` → one product (404 if missing)

**cart** (`<cart_id>` comes from the gateway session)
- `GET /carts/<cart_id>` → `{ items: { product_id: qty } }`
- `POST /carts/<cart_id>/items` body `{ product_id, quantity }`
- `DELETE /carts/<cart_id>/items/<product_id>`
- `DELETE /carts/<cart_id>` → clear

**orders**
- `POST /orders` body `{ customer_name, customer_email, address, items:[{product_id, quantity}] }`
- `GET /orders` → all orders (newest first)
- `GET /orders/<id>` → one order

**health**
- `GET /health` (on both `gateway` and `api`)

## Run it

```bash
docker compose up --build
```

Then open http://localhost:8000. The catalog is auto-seeded by `api` on first start.
`api` is also exposed on 8001 for debugging.

To run `api` locally without Docker it falls back to SQLite + localhost Redis defaults —
e.g. `cd services/api && pip install -r requirements.txt && python app.py`.

## Layout

```
docker-compose.yml          # orchestrates 4 containers (gateway, api, shop-db, cart-redis)
Jenkinsfile                 # CI: builds every service image
services/
  api/                      # Flask + SQLAlchemy + MySQL + Redis (products, cart, orders)
  gateway/                  # Flask + Jinja templates + static + requests
```
