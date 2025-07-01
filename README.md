# RangeCart

**RangeCart** is a simple web app where sellers can add their products and buyers can view and order them. The app has login, register, forgot password, and user roles like buyer and seller.

---

## Features

- User Login and Register
- Add products with name, price, image, expiry time, and delivery range
- Edit or delete products (seller only)
- Place orders (buyer only)
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

---

## Folder Info

```
RangeCart/
│
├── main.py           # Main FastAPI backend
├── models.py         # Data models (User, Product, etc.)
├── templates/        # HTML files (Jinja2)
├── static/           # Frontend files
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
