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

## Observability

`docker compose up` also brings up a monitoring stack that scrapes and collects from
the two app services:

| Component      | Port | Role                                                                    |
| -------------- | ---- | ----------------------------------------------------------------------- |
| `prometheus`   | 9090 | Scrapes `api` + `gateway` `/metrics`; evaluates alert rules             |
| `alertmanager` | 9093 | Receives alerts fired by Prometheus (no-op receiver by default)         |
| `loki`         | 3100 | Stores logs                                                             |
| `promtail`     | 9080 | Ships every container's stdout/stderr into Loki (via the Docker socket) |
| `grafana`      | 3000 | Dashboards over Prometheus + Loki (`admin` / `admin`)                   |

- **App metrics.** `api` and `gateway` are instrumented with
  [`prometheus-flask-exporter`](https://pypi.org/project/prometheus-flask-exporter/),
  exposing `GET /metrics` with per-route request counts and latency
  (`flask_http_request_total`, `flask_http_request_duration_seconds`). Prometheus
  scrapes both every 15s (see [`monitoring/prometheus/prometheus.yml`](monitoring/prometheus/prometheus.yml)).
- **Alerts.** [`monitoring/prometheus/alert.rules.yml`](monitoring/prometheus/alert.rules.yml)
  ships two sample rules: `TargetDown` and `HighHttpErrorRate` (>5% 5xx).
- **Logs.** Promtail discovers containers via the Docker socket and labels each log
  stream by `container` (`shop-api`, `shop-gateway`, …), queryable in Grafana as
  `{container=~"shop-.*"}`.
- **Grafana** auto-provisions both datasources and an **E-commerce App Overview**
  dashboard (request rate, p95 latency, 5xx rate, live logs) on first boot — open
  http://localhost:3000.

> Note: the app images run gunicorn with 2 workers, so each `/metrics` scrape reflects
> one worker. For a demo this is fine; for exact counters switch to
> `prometheus-flask-exporter`'s multiprocess mode.

## Layout

```
docker-compose.yml          # orchestrates 9 containers (app + datastores + observability)
Jenkinsfile                 # CI: builds every service image
services/
  api/                      # Flask + SQLAlchemy + MySQL + Redis (products, cart, orders)
  gateway/                  # Flask + Jinja templates + static + requests
monitoring/
  prometheus/               # prometheus.yml + alert.rules.yml
  alertmanager/             # alertmanager.yml
  loki/                     # loki-config.yml
  promtail/                 # promtail-config.yml (Docker log discovery -> Loki)
  grafana/                  # provisioned datasources + dashboards
```
