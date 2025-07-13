# Kinbech


**Kinbech** is a lightweight marketplace built with FastAPI. Sellers can list their goods while buyers browse and order items. The application supports different user roles (buyer, seller and admin) and includes a small HTML frontend.

---

## Features

- JWT based login and registration
- Sellers can list products with name, price, images, delivery range and expiry
- Admin dashboard to validate or remove products and view all sellers
- Buyers can place orders and receive notifications when orders are fulfilled
- Optional shop name, address and phone number for each seller
- Order items now store the seller's shop name
- Background task removes products after their expiry date
- WhatsApp-based username and password recovery
- Clean HTML/CSS frontend
- Responsive pages optimized for mobile devices
---

## Technology Used

- Python 3.11 (FastAPI)
- HTML, CSS, JavaScript (frontend)
- SQLite (database)
- JWT Token for login
- Uvicorn to run the app

This project is tested with **Python 3.11**.

---

## How to Run the App

1. **Clone the project**
   ```bash
   git clone https://github.com/Safalsharma1991/Kinbech.git
   cd Kinbech
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate   # On Windows use "venv\\Scripts\\activate"
   ```

3. **Install required packages**
   ```bash
   pip install -r requirements.txt
   ```
   The requirements file installs `psycopg2-binary`, which works across
   Python versions including 3.13.
4. **Set `SECRET_KEY` environment variable**
   ```bash
   export SECRET_KEY="your-secret-key"
   ```
   Make sure this value is long and random when deploying to production.
   The fallback `"secretkey"` defined in `main.py` is intended for development
   only.

5. **Run the app**
   ```bash
   uvicorn main:app --reload
   ```

6. Open your browser and go to:
   [http://127.0.0.1:8000](http://127.0.0.1:8000)

Registration is handled directly on this page; there is no separate
`/register` form route.

---

## Inspecting the Database

The application stores its data in a SQLite file named `test.db`. You can
use the `sqlite3` command line tool to browse its tables and run queries.

### Installing the SQLite CLI

On Debian or Ubuntu systems:

```bash
sudo apt-get install sqlite3
```

On macOS with Homebrew:

```bash
brew install sqlite3
```

### Viewing `test.db`

Open the database and list the tables:

```bash
sqlite3 test.db
sqlite> .tables
sqlite> SELECT * FROM users LIMIT 5;
```

Use `.schema` to show the table definitions or any valid SQL commands to
inspect the stored data.

## Managing Shop Names

Sellers can set a unique `shop_name` for their account. Use the `/shop/name` endpoint to retrieve or update it:

```bash
# Get current shop name
curl -H "Authorization: Bearer <token>" http://127.0.0.1:8000/shop/name

# Update shop name
curl -X POST -H "Authorization: Bearer <token>" -F name=MyStore \
    http://127.0.0.1:8000/shop/name
```

When adding products, the seller page includes this shop name so buyers can see which store offers each item.

### Updating Seller Contact Details

Sellers can store an optional address and phone number using the `/seller/details` endpoints:

```bash
# View saved details
curl -H "Authorization: Bearer <token>" http://127.0.0.1:8000/seller/details

# Update address and phone
curl -X POST \
  -H "Authorization: Bearer <token>" \
  -F address="123 Market St" \
  -F phone_number="9876543210" \
  http://127.0.0.1:8000/seller/details
```

These values appear on the seller dashboard where they can be edited anytime.

---

## Admin Users

Create an admin account by sending a role of `"admin"` when registering.  Existing admins can also use the form at `/admin/register`, which is publicly accessible (no login required):

```bash
curl -X POST -H "Content-Type: application/json" \
     -d '{"username": "admin", "password": "secret", "role": ["admin"]}' \
     http://127.0.0.1:8000/register
```

Admins can list all sellers using:

```bash
curl -H "Authorization: Bearer <token>" \
     http://127.0.0.1:8000/admin/sellers
```

The response includes each seller's username, shop name, address and phone number.

Admins can retrieve each seller along with their listed products:

```bash
curl -H "Authorization: Bearer <token>" \
     http://127.0.0.1:8000/admin/sellers/details
```

Each seller object in the returned JSON also contains a `products` array listing all
their items.

Admins can mark any order as fulfilled, bypassing the seller ownership check:

```bash
curl -X POST -H "Authorization: Bearer <token>" \
     http://127.0.0.1:8000/orders/<order_id>/fulfill
```

This endpoint is also used by the admin dashboard to update pending orders.

---

## Folder Info

```
Kinbech/
│
├── main.py           # Main FastAPI backend
├── models.py         # Data models (User, Product, etc.)
├── static/           # Frontend files and HTML templates
├── database.py       # Database setup
├── requirements.txt  # Required packages
```

---

## About the Developer

This app is made by **Safal Sharma** to help local sellers and buyers connect easily.

GitHub: [https://github.com/Safalsharma1991](https://github.com/Safalsharma1991)

---

## License

This project is free to use under the [MIT License](LICENSE).
