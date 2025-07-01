from fastapi import FastAPI, HTTPException, Depends, status, Form, Request, Body, APIRouter
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from pydantic import BaseModel
from typing import Optional, Dict, List
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
import json
import os
from sqlalchemy.orm import Session
from models import Base, Order, OrderItem, UserModel as DBUser, Product as DBProduct
from database import Base, engine, SessionLocal
from sqlalchemy.exc import SQLAlchemyError
from fastapi import UploadFile, File, Form
from fastapi.responses import HTMLResponse
from models import Product, UserModel as User
from schemas import ProductOut
from database import get_db
from auth import get_current_user
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
import uuid

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
Base.metadata.create_all(bind=engine)

# Serve static frontend files


@app.get("/")
async def root():
    return FileResponse("static/index.html")

# JWT settings
SECRET_KEY = "secretkey"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Simulated in-memory user DB
users_db: Dict[str, dict] = {}

products = []
product_id_counter = 1

Base.metadata.create_all(bind=engine)


class UserCreate(BaseModel):
    username: str
    full_name: Optional[str] = None
    password: str
    role: list[str]


class Token(BaseModel):
    access_token: str
    token_type: str


class ResetPasswordRequest(BaseModel):
    username: str
    new_password: str


class Product(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    price: float
    seller: str  # seller username
    delivery_range_km: int
    expiry_datetime: str  # ISO format


class CartItem(BaseModel):
    product_id: int
    quantity: int


class CheckoutRequest(BaseModel):
    items: List[CartItem]
    address: str


class ResetRequest(BaseModel):
    number: str


PRODUCTS_FILE = "products.json"


def load_products():
    if os.path.exists(PRODUCTS_FILE):
        with open(PRODUCTS_FILE, "r") as f:
            return json.load(f)
    return []


def save_products(products):
    with open(PRODUCTS_FILE, "w") as f:
        json.dump(products, f, indent=2)


# Load on startup
products = load_products()
product_id_counter = max([p["id"] for p in products], default=0) + 1

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


def get_password_hash(password):
    return pwd_context.hash(password)


def verify_password(plain, hashed):
    return pwd_context.verify(plain, hashed)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_user(db: Session, username: str):
    return db.query(DBUser).filter(DBUser.username == username).first()


def authenticate_user(db: Session, username: str, password: str):
    user = get_user(db, username)
    if user and verify_password(password, user.hashed_password):
        return user
    return None


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user_from_token(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if not username:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        user = db.query(DBUser).filter(DBUser.username == username).first()
        if not user:
            raise HTTPException(status_code=401, detail="User not found")

        return {
            "username": user.username,
            "full_name": user.full_name,
            "role": user.role.split(",")
        }
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


@app.post("/register", status_code=201)
async def register(user: UserCreate, db: Session = Depends(get_db)):
    existing = db.query(DBUser).filter(
        DBUser.username == user.username).first()
    if existing:
        raise HTTPException(
            status_code=400, detail="Username already registered")

    hashed_password = get_password_hash(user.password)
    db_user = DBUser(
        username=user.username,
        full_name=user.full_name,
        hashed_password=hashed_password,
        role="buyer,seller"  # ✅ hardcoded
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return {"msg": "User registered successfully"}


@app.post("/token", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=400, detail="Incorrect username or password")
    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}


@app.post("/reset-password")
async def reset_password(data: ResetPasswordRequest):
    user = users_db.get(data.username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user["hashed_password"] = get_password_hash(data.new_password)
    return {"msg": "Password reset successful"}


@app.get("/profile")
async def read_profile(current_user: dict = Depends(get_current_user_from_token)):
    return {
        "username": current_user["username"],
        "full_name": current_user["full_name"],
        "role": current_user["role"]  # ✅ already a list
    }


@app.post("/products")
async def create_product(
    name: str = Form(...),
    description: str = Form(""),
    price: float = Form(...),
    delivery_range_km: int = Form(...),
    expiry_datetime: str = Form(...),
    images: List[UploadFile] = File(...),
    current_user: dict = Depends(get_current_user_from_token),
    db: Session = Depends(get_db)
):
    # ✅ Create directory if it doesn't exist
    os.makedirs("static/uploads", exist_ok=True)

    image_urls = []

    for image in images:
        image_path = f"static/uploads/{image.filename}"
        with open(image_path, "wb") as buffer:
            buffer.write(await image.read())
        image_urls.append(f"/{image_path}")  # store with /static path

    new_product = DBProduct(  # ✅ correct model (SQLAlchemy)
        name=name,
        description=description,
        price=price,
        seller=current_user["username"],
        image_url=",".join(image_urls),
        delivery_range_km=delivery_range_km,
        expiry_datetime=expiry_datetime,
    )

    db.add(new_product)
    db.commit()
    db.refresh(new_product)
    return {"msg": "Product added successfully"}


@app.get("/products")
async def get_products(current_user: dict = Depends(get_current_user_from_token), db: Session = Depends(get_db)):
    db_products = db.query(DBProduct).all()

    return [
        {
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "price": p.price,
            "seller": p.seller,
            "image_urls": p.image_url.split(","),
            "delivery_range_km": p.delivery_range_km,
            "expiry_datetime": p.expiry_datetime,
        }
        for p in db_products
    ]


@app.post("/buy/{product_id}")
async def buy_product(
    product_id: int,
    address: str = Body(...),
    current_user: dict = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    if "buyer" not in current_user["role"]:
        raise HTTPException(
            status_code=403, detail="Only buyers can purchase products")

    product = db.query(DBProduct).filter(DBProduct.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    order = Order(buyer=current_user["username"], address=address)
    db.add(order)
    db.flush()
    db.add(OrderItem(order_id=order.id, product_id=product_id, quantity=1))
    db.commit()

    return {
        "msg": f"You bought '{product.name}' for ₹{product.price}",
        "product": {
            "id": product.id,
            "name": product.name,
            "price": product.price,
        },
    }


@app.post("/checkout")
async def checkout(
    request: CheckoutRequest,
    current_user: dict = Depends(get_current_user_from_token),
    db: Session = Depends(get_db)
):
    order = Order(
        buyer=current_user["username"],
        address=request.address,
    )
    db.add(order)
    db.flush()  # Get order.id

    for item in request.items:
        db.add(OrderItem(order_id=order.id,
               product_id=item.product_id, quantity=item.quantity))

    db.commit()
    return {"msg": "Order placed successfully!"}


# This serves the HTML page
@app.get("/my-products", response_class=HTMLResponse)
async def serve_my_products_page():
    return FileResponse("static/my_products.html")

# This serves the product data securely


@app.get("/api/my-products")
async def get_my_products(current_user: dict = Depends(get_current_user_from_token), db: Session = Depends(get_db)):
    products = db.query(DBProduct).filter(
        DBProduct.seller == current_user["username"]).all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "price": p.price,
            "image_urls": p.image_url.split(","),
            "delivery_range_km": p.delivery_range_km,
            "expiry_datetime": p.expiry_datetime,
        }
        for p in products
    ]


@app.delete("/products/{product_id}")
async def delete_product(product_id: int, current_user: dict = Depends(get_current_user_from_token), db: Session = Depends(get_db)):
    product = db.query(DBProduct).filter(
        DBProduct.id == product_id, DBProduct.seller == current_user["username"]).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    db.delete(product)
    db.commit()
    return {"msg": "Product deleted"}


@app.put("/products/{product_id}")
async def update_product(
    product_id: int,
    data: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_from_token)
):
    product = db.query(DBProduct).filter(
        DBProduct.id == product_id, DBProduct.seller == current_user["username"]).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    for key in ["name", "description", "price", "delivery_range_km", "expiry_datetime"]:
        if key in data:
            setattr(product, key, data[key])
    db.commit()
    return {"msg": "Product updated"}


# ✅ Just serve the HTML (no auth needed)
@app.get("/my-products", include_in_schema=False)
async def my_products_page():
    return FileResponse("static/my_products.html")

# ✅ Actual product data requires auth


@app.get("/api/my-products")
async def get_my_products(current_user: dict = Depends(get_current_user_from_token), db: Session = Depends(get_db)):
    products = db.query(DBProduct).filter(
        DBProduct.seller == current_user["username"]).all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "price": p.price,
            "image_urls": p.image_url.split(","),
            "delivery_range_km": p.delivery_range_km,
            "expiry_datetime": p.expiry_datetime,
        }
        for p in products
    ]


@app.get("/seller/orders")
def get_seller_orders(current_user: dict = Depends(get_current_user_from_token), db: Session = Depends(get_db)):
    username = current_user["username"]

    orders = db.query(Order).join(OrderItem).join(
        DBProduct).filter(DBProduct.seller == username).all()

    return [{
        "id": order.id,
        "buyer": order.buyer,
        "address": order.address,
        "items": [{
            "name": item.product.name,
            "price": item.product.price,
            "quantity": item.quantity,
        } for item in order.items],
        "total": sum(item.product.price * item.quantity for item in order.items),
        "timestamp": order.timestamp.isoformat(),
        "status": order.status
    } for order in orders]


@app.post("/seller/orders/{order_id}/fulfill")
def mark_order_fulfilled(order_id: int, current_user: dict = Depends(get_current_user_from_token), db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # Optional: Check if the seller is the owner of the order items
    for item in order.items:
        if item.product.seller != current_user["username"]:
            raise HTTPException(status_code=403, detail="Unauthorized")

    order.status = "Fulfilled"
    db.commit()
    return {"msg": "Order marked as fulfilled"}


@app.get("/buyer/notifications")
def get_notifications(current_user: dict = Depends(get_current_user_from_token), db: Session = Depends(get_db)):
    username = current_user["username"]

    orders = db.query(Order).filter(Order.buyer == username).order_by(
        Order.timestamp.desc()).all()

    return [{
        "id": o.id,
        "status": o.status,
        "timestamp": o.timestamp.isoformat(),
    } for o in orders]


@app.get("/products/{product_id}", response_model=ProductOut)
def get_product(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_from_token),
):
    product = db.query(DBProduct).filter(
        DBProduct.id == product_id,
        DBProduct.seller == current_user["username"],
    ).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return {
        "id": product.id,
        "name": product.name,
        "description": product.description,
        "price": product.price,
        "delivery_range_km": product.delivery_range_km,
        "expiry_datetime": product.expiry_datetime,
        "image_urls": product.image_url.split(","),
    }


templates = Jinja2Templates(directory="templates")  # Update path if needed


@app.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(request: Request):
    return templates.TemplateResponse("forgot_password.html", {"request": request})


@app.post("/forgot-password")
async def forgot_password_submit(username: str = Form(...)):
    # TODO: Implement actual reset logic or email link
    print(f"Password reset requested for user: {username}")
    # For now, just redirect back to login with a dummy message
    return RedirectResponse("/", status_code=302)


@app.get("/forgot-password", response_class=HTMLResponse)
def forgot_password_form(request: Request):
    return templates.TemplateResponse("forgot_password.html", {"request": request})


@app.post("/forgot-password")
def process_forgot_password(email: str = Form(...)):
    # Here, add logic to:
    # 1. Verify email exists
    # 2. Create a reset token (we’ll do this in step 5)
    # 3. Send a reset email (or just show a message for now)

    print(f"Password reset link requested for: {email}")
    return RedirectResponse(url="/login", status_code=303)


@app.get("/register", response_class=HTMLResponse)
def register_form(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})


@app.post("/register")
def register_user(username: str = Form(...), password: str = Form(...), full_name: str = Form(...)):
    # TODO: Add logic to save the user to your database
    print(f"Registered: {username}, {full_name}")
    return RedirectResponse(url="/login", status_code=303)


@app.post("/send-reset-link")
async def send_reset_link(payload: ResetRequest):
    # Generate unique token
    reset_token = str(uuid.uuid4())

    # Save token and associate with user in DB (or mock store)
    reset_link = f"http://127.0.0.1:8000/reset-password/{reset_token}"

    # TODO: Replace this with actual WhatsApp API integration
    print(f"Send this link via WhatsApp: {reset_link} to {payload.number}")

    return {"msg": "Reset link sent to your WhatsApp!"}
