# RangeCart

**RangeCart** is a simple web app where sellers can add their products and buyers can view and order them. The app has login, register, forgot password, and user roles like buyer and seller.

---

## Features

- User Login and Register
- Add products with name, price, image, expiry time, and delivery range
- Edit or delete products (seller only)
- Place orders (buyer only)
- Unique shop names for sellers
- Forgot password feature (sends reset link to WhatsApp)
- Clean and simple design

---

## Technology Used

- Python (FastAPI)
- HTML, CSS, JavaScript (frontend)
- SQLite (database)
- JWT Token for login
- Uvicorn to run the app

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
   venv\Scripts\activate   # For Windows
   ```

3. **Install required packages**
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the app**
   ```bash
   uvicorn main:app --reload
   ```

5. Open your browser and go to:
   [http://127.0.0.1:8000](http://127.0.0.1:8000)

   Registration is handled directly on this page; there is no separate
   `/register` form route.

---

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

Create an admin account by sending a role of `"admin"` when registering:

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

---

## Folder Info

```
RangeCart/
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

This project is free to use under the MIT License.
