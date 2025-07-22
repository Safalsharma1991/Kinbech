from fastapi import (
    FastAPI,
    HTTPException,
    Depends,
    Form,
    Request,
    Body,
    UploadFile,
    File,
)
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    RedirectResponse,
    JSONResponse,
)

from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
import logging
from pydantic import BaseModel
from typing import Optional, List, Dict
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
import os
import asyncio
from sqlalchemy.orm import Session
from models import (
    Admin,
    Base,
    Order,
    OrderItem,
    UserModel as DBUser,
    Product as DBProduct,
    ResetToken,
    Shop,
    AddedProduct,
    Like,
)
from database import engine, get_db, SessionLocal
from schemas import ProductOut
from fastapi.templating import Jinja2Templates
import uuid
from uuid import uuid4
import json
from pathlib import Path
import smtplib
from email.message import EmailMessage
from twilio.rest import Client
import cloudinary
import cloudinary.uploader

cloudinary.config(
    cloud_name="dt6nx4ud7",
    api_key="787959511856333",
    api_secret="H9zQpeMBKn_pJ-GeICgAgU3YjIs",
    secure=True,
)
app = FastAPI()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
Base.metadata.create_all(bind=engine)


async def cleanup_expired_products():
    """Periodically remove products past their expiry time."""
    while True:
        db = SessionLocal()
        now = datetime.utcnow()
        for product in db.query(DBProduct).all():
            try:
                expiry = datetime.fromisoformat(product.expiry_datetime)
            except Exception:
                continue
            if expiry < now:
                db.delete(product)
        db.commit()
        db.close()
        await asyncio.sleep(3600)


@app.on_event("startup")
async def start_background_tasks():
    asyncio.create_task(cleanup_expired_products())


# Serve static frontend files


@app.get("/")
async def root():
    return FileResponse("static/index.html")


# JWT settings
# Read secret key from environment variable for security
SECRET_KEY = os.getenv("SECRET_KEY", "secretkey")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# Email configuration for password reset
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_FROM = os.getenv("EMAIL_FROM", EMAIL_USER if EMAIL_USER else "")

# Twilio WhatsApp configuration
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM")
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://127.0.0.1:8000")

# Domain suffix for usernames
USERNAME_DOMAIN = "kinbech.shop"

# Flat service fee added to each order total
SERVICE_FEE = 2.0

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class UserCreate(BaseModel):
    username: str
    full_name: Optional[str] = None
    password: str
    role: list[str] = ["buyer", "seller"]
    address: Optional[str] = None
    phone: Optional[str] = None

class PhoneCheckRequest(BaseModel):
    phone_number: str

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
    price: str
    seller: str  # seller username
    delivery_range_km: int
    expiry_datetime: str  # ISO format


class CartItem(BaseModel):
    product_id: int
    quantity: int


class CheckoutRequest(BaseModel):
    address: str
    phone_number: str  # Add phone_number to the checkout request
    special_instructions: str | None = None
    sample_image_url: str | None = None
    items: List[CartItem]


class ResetRequest(BaseModel):
    number: str


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def create_access_token(data: Dict, expires_delta: timedelta = timedelta(hours=1)) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + expires_delta
    to_encode.update({"exp": expire})
    
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str) -> Dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

def get_password_hash(password):
    return pwd_context.hash(password)


def verify_password(plain, hashed):
    return pwd_context.verify(plain, hashed)


def price_to_float(price: str) -> float:
    """Convert a price range like '120-130' to a float (lower bound)."""
    try:
        price_str = str(price)  
        if '-' in price_str:
            return float(price_str.split('-')[0])
        return float(price_str)
    except (ValueError, TypeError):
        return 0.0


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_user(db: Session, username: str):
    return db.query(DBUser).filter(DBUser.username == username).first()


def authenticate_user(db: Session, username: str, password: str):
    user = get_user(db, username)
    if user and verify_password(password, user.hashed_password):
        return user
    return None

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
            "role": user.role.split(","),
        }
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

def get_current_admin_from_token(
    request: Request, db: Session = Depends(get_db)
) -> Admin:
    token = request.headers.get("Authorization")
    if not token or not token.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")

    token = token.replace("Bearer ", "")
    payload = decode_token(token)  # This will decode the real JWT token
    phone_number = payload.get("phone_number")

    if not phone_number:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    
    # Query the admin based on the phone number from the token
    admin = db.query(Admin).filter(Admin.phone_number == phone_number).first()
    if not admin:
        raise HTTPException(status_code=404, detail="Admin not found")
    
    return admin




def _generate_unique_username(base: str, db: Session) -> str:
    """Generate a unique username using the configured domain."""
    while True:
        candidate = f"{base}{uuid4().hex[:5]}@{USERNAME_DOMAIN}"
        if not db.query(DBUser).filter(DBUser.username == candidate).first():
            return candidate


def _create_reset_token(user: DBUser, db: Session) -> str:
    """Generate and store a password reset token for the user."""
    token = str(uuid.uuid4())
    expires_at = datetime.utcnow() + timedelta(hours=1)
    db_token = ResetToken(user_id=user.id, token=token, expires_at=expires_at)
    db.add(db_token)
    db.commit()
    return token


def _send_email(to_email: str, subject: str, body: str):
    """Send an email if credentials are configured, else log the message."""
    if not (EMAIL_HOST and EMAIL_USER and EMAIL_PASSWORD):
        logger.info("Email not configured. Would send to %s: %s", to_email, body)
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = EMAIL_FROM
    msg["To"] = to_email
    msg.set_content(body)

    try:
        with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASSWORD)
            server.send_message(msg)
    except Exception as e:
        logger.error("Failed to send email: %s", e)


def _send_whatsapp(to_number: str, body: str):
    """Send a WhatsApp message using Twilio if configured."""
    if not (TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_WHATSAPP_FROM):
        logger.info("Twilio not configured. Would send to %s: %s", to_number, body)
        return

    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        from_number = TWILIO_WHATSAPP_FROM
        if not from_number.startswith("whatsapp:"):
            from_number = f"whatsapp:{from_number}"
        to = to_number if to_number.startswith("whatsapp:") else f"whatsapp:{to_number}"
        client.messages.create(body=body, from_=from_number, to=to)
    except Exception as e:
        logger.error("Failed to send WhatsApp message: %s", e)


@app.post("/register", status_code=201)
async def register(user: UserCreate, db: Session = Depends(get_db)):
    base_name = user.username.split("@")[0]
    username = f"{base_name}@{USERNAME_DOMAIN}"

    existing = db.query(DBUser).filter(DBUser.username == username).first()
    if existing:
        suggestion = _generate_unique_username(base_name, db)
        raise HTTPException(
            status_code=400,
            detail=f"Username already registered. Suggested username: {suggestion}",
        )

    hashed_password = get_password_hash(user.password)
    db_user = DBUser(
        username=username,
        full_name=user.full_name,
        hashed_password=hashed_password,
        role=",".join(user.role),
        address=user.address,
        phone_number=user.phone,
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return {"msg": "User registered successfully"}


@app.post("/token", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
):
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}


@app.post("/reset-password")
async def reset_password(data: ResetPasswordRequest, db: Session = Depends(get_db)):
    # 1. Query DBUser for the specified username
    user = db.query(DBUser).filter(DBUser.username == data.username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # 2. Update its hashed_password with the new password hash
    user.hashed_password = get_password_hash(data.new_password)

    # 3. Commit the change to the database
    db.commit()

    return {"msg": "Password reset successful"}


@app.get("/reset-password/{token}", response_class=HTMLResponse)
async def reset_password_form(token: str, request: Request, db: Session = Depends(get_db)):
    record = (
        db.query(ResetToken)
        .filter(ResetToken.token == token, ResetToken.expires_at > datetime.utcnow())
        .first()
    )
    if not record:
        return HTMLResponse("Invalid or expired token", status_code=400)
    return templates.TemplateResponse("reset_password.html", {"request": request, "token": token})


@app.post("/reset-password/{token}")
async def reset_password_token(token: str, new_password: str = Form(...), db: Session = Depends(get_db)):
    record = (
        db.query(ResetToken)
        .filter(ResetToken.token == token, ResetToken.expires_at > datetime.utcnow())
        .first()
    )
    if not record:
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    user = db.query(DBUser).filter(DBUser.id == record.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.hashed_password = get_password_hash(new_password)
    db.delete(record)
    db.commit()

    return RedirectResponse(url="/login", status_code=303)


@app.get("/profile")
async def read_profile(current_user: dict = Depends(get_current_user_from_token)):
    return {
        "username": current_user["username"],
        "full_name": current_user["full_name"],
        "role": current_user["role"],  # ✅ already a list
    }


@app.get("/shop/name")
def get_shop_name(
    current_user: dict = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    user = db.query(DBUser).filter(DBUser.username == current_user["username"]).first()
    return {"shop_name": user.shop_name if user and user.shop_name else ""}


@app.post("/shop/name")
def set_shop_name(
    name: str = Form(...),
    current_user: dict = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    user = db.query(DBUser).filter(DBUser.username == current_user["username"]).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    existing = db.query(DBUser).filter(DBUser.shop_name == name).first()
    if existing and existing.id != user.id:
        raise HTTPException(status_code=400, detail="Shop name already taken")
    user.shop_name = name
    db.commit()
    return {"shop_name": user.shop_name}


@app.get("/seller/details")
def get_seller_details(
    current_user: dict = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    user = db.query(DBUser).filter(DBUser.username == current_user["username"]).first()
    return {
        "address": user.address if user and user.address else "",
        "phone_number": user.phone_number if user and user.phone_number else "",
    }


@app.post("/seller/details")
def update_seller_details(
    address: str = Form(None),
    phone_number: str = Form(None),
    current_user: dict = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    user = db.query(DBUser).filter(DBUser.username == current_user["username"]).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.address = address
    user.phone_number = phone_number
    db.commit()
    return {"address": user.address, "phone_number": user.phone_number}

@app.post("/shops")
def create_or_update_shop(
    shop_name: str = Form(...),
    address: str = Form(...),
    phone_number: str = Form(...),
    db: Session = Depends(get_db)
):
    existing_shop = db.query(Shop).filter(Shop.phone_number == phone_number).first()
    
    if existing_shop:
        # Update existing shop
        existing_shop.name = shop_name
        existing_shop.address = address
        db.commit()
        db.refresh(existing_shop)
        return {"msg": "Shop updated successfully"}
    else:
        # Create new shop
        new_shop = Shop(name=shop_name, address=address, phone_number=phone_number)
        db.add(new_shop)
        db.commit()
        db.refresh(new_shop)
        return {"msg": "Shop registered successfully"}


@app.get("/shop/phone")
def get_shop_phone(
    current_user: dict = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """Fetch the phone number for the logged in user's shop from the Shop table."""
    user = db.query(DBUser).filter(DBUser.username == current_user["username"]).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    phone = user.phone_number
    if not phone:
        return {"phone_number": ""}

    shop = db.query(Shop).filter(Shop.phone_number == phone).first()
    return {"phone_number": shop.phone_number if shop else ""}


@app.post("/products")
async def create_product(
    name: str = Form(...),
    description: str = Form(""),
    price: str = Form(...),
    delivery_range_km: int = Form(...),
    phone_number: str = Form(...),
    images: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    shop = db.query(Shop).filter(Shop.phone_number == phone_number).first()
    if not shop:
        raise HTTPException(status_code=403, detail="Phone number not authorized")
        
    # Create upload dir if it doesn't exist
    upload_dir = Path("static/uploads")
    upload_dir.mkdir(parents=True, exist_ok=True)

    shop = db.query(Shop).filter(Shop.phone_number == phone_number).first()
    if not shop or shop.phone_number != phone_number:
        raise HTTPException(status_code=400, detail="Phone number does not match registered user")


    image_urls = []

    for image in images:
        try:
            result = cloudinary.uploader.upload(
                await image.read(),
                folder="kinbech_uploads",  # Optional: Organize images
                public_id=f"{uuid4().hex}",  # Unique filename
                resource_type="image"
            )
            image_urls.append(result["secure_url"])
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Cloudinary upload failed: {e}")

    new_product = DBProduct(  # ✅ correct model (SQLAlchemy)
        name=name,
        description=description,
        price=price,
        image_url=",".join(image_urls),
        is_validated=False,
        delivery_range_km=delivery_range_km,
        phone_number=phone_number,
    )


    db.add(new_product)
    db.commit()
    db.refresh(new_product)
    return {"msg": "Product added successfully"}


@app.get("/products")
async def get_products(
    current_user: dict = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """Return all validated products for the marketplace."""

    db_products = db.query(DBProduct).filter(DBProduct.is_validated == True).all()

    products = []
    for p in db_products:
        item = {
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "price": p.price,
            "seller": p.seller,
            "shop_name": p.shop_name,
            "image_urls": p.image_url.split(","),
            "delivery_range_km": p.delivery_range_km,
            "expiry_datetime": p.expiry_datetime,
        }

        if "admin" in current_user["role"]:
            item["shop_name"] = p.shop_name
        products.append(item)

    return products

@app.get("/public-products")
async def get_public_products(db: Session = Depends(get_db)):
    """Return validated products without requiring authentication."""
    db_products = db.query(DBProduct).filter(DBProduct.is_validated == True).all()
    products = []
    for p in db_products:
        like_row = db.query(Like).filter(Like.product_id == p.id).first()
        products.append({
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "price": p.price,
            "image_urls": p.image_url.split(","),
            "delivery_range_km": p.delivery_range_km,
            "likes": like_row.like if like_row else 0,
        })
    return products


@app.post("/products/{product_id}/like")
def like_product(product_id: int, db: Session = Depends(get_db)):
    """Increment like count for a product."""
    like_row = db.query(Like).filter(Like.product_id == product_id).first()
    if not like_row:
        like_row = Like(product_id=product_id, like=1)
        db.add(like_row)
    else:
        like_row.like += 1
    db.commit()
    db.refresh(like_row)
    return {"likes": like_row.like}

@app.post("/buy/{product_id}")
async def buy_product(
    product_id: int,
    address: str = Body(...),
    current_user: dict = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    if "buyer" not in current_user["role"]:
        raise HTTPException(status_code=403, detail="Only buyers can purchase products")

    product = db.query(DBProduct).filter(DBProduct.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    if not product.is_validated:
        raise HTTPException(status_code=403, detail="Product not validated")
    order = Order(buyer=current_user["username"], address=address)
    db.add(order)
    db.flush()
    db.add(
        OrderItem(
            order_id=order.id,
            product_id=product_id,
            quantity=1,
            shop_name=product.shop_name,
        )
    )
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
    items: str = Form(...),
    address: str = Form(...),
    phone_number: str = Form(...),
    special_instructions: str | None = Form(None),
    sample_image: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    try:
        items_data = json.loads(items)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid items data")

    sample_url = None
    if sample_image is not None:
        try:
            result = cloudinary.uploader.upload(
                await sample_image.read(),
                folder="kinbech_uploads",
                public_id=f"{uuid4().hex}",
                resource_type="image",
            )
            sample_url = result["secure_url"]
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Image upload failed: {e}")

    order = Order(
        buyer=items_data[0]["product_id"],
        phone_number=phone_number,
        status="Pending",
        timestamp=datetime.utcnow(),
        address=address,
        special_instructions=special_instructions,
        sample_image_url=sample_url,
    )
    db.add(order)
    db.flush()

    for item in items_data:
        product = db.query(DBProduct).filter(DBProduct.id == item["product_id"]).first()
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
        if not product.is_validated:
            raise HTTPException(status_code=403, detail="Product not validated")

        db.add(
            OrderItem(
                order_id=order.id,
                product_id=item["product_id"],
                quantity=item.get("quantity", 1),

            )
        )

    db.commit()
    return {"msg": "Order placed successfully!"}



@app.delete("/products/{product_id}")
def delete_product(
    product_id: int,
    db: Session = Depends(get_db)
):
    product = db.query(DBProduct).filter(DBProduct.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    db.delete(product)
    db.commit()
    return {"message": "Deleted successfully"}


class ProductIn(BaseModel):
    name: str
    description: Optional[str] = None
    price: str
    delivery_range_km: int


@app.put("/products/{product_id}")
def update_product(
    product_id: int,
    updated: ProductIn,
    db: Session = Depends(get_db)
):
    product = db.query(DBProduct).filter(DBProduct.id == product_id).first()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    product.name = updated.name
    product.description = updated.description
    product.price = updated.price
    product.delivery_range_km = updated.delivery_range_km

    db.commit()
    db.refresh(product)

    return {"message": "Product updated successfully"}


def update_product(
    product_id: int,
    updated: ProductIn,  # your input schema
    db: Session = Depends(get_db),
):
    product = db.query(DBProduct).filter(DBProduct.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    product.name = updated.name
    product.description = updated.description
    product.price = updated.price
    product.delivery_range_km = updated.delivery_range_km
    db.commit()
    db.refresh(product)
    return {"message": "Product updated"}



# Serve the seller products page only if the user's phone number exists in the
# Shop table
@app.get("/my-products", include_in_schema=False)
@app.get("/static/my_products.html", include_in_schema=False)
async def my_products_page():
    """Serve the seller product management page."""
    return FileResponse("static/my_products.html")


# ✅ Actual product data requires auth


@app.get("/api/my-products")
async def get_my_products(
    current_user: dict = Depends(get_current_admin_from_token),
    db: Session = Depends(get_db),
):

    products = (
        db.query(DBProduct).filter(DBProduct.seller == current_user["username"]).all()
    )
    out = []
    for p in products:
        item = {
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "price": p.price,
            "image_urls": p.image_url.split(","),
            "delivery_range_km": p.delivery_range_km,
        }
        if "admin" in current_user["role"]:
            item["shop_name"] = p.shop_name
        out.append(item)
    return out


@app.get("/api/products/by-phone/{phone_number}")
def get_products_by_phone(
    phone_number: str,
    db: Session = Depends(get_db),
):
    """Return all products for a shop identified by phone number."""
    products = db.query(DBProduct).filter(DBProduct.phone_number == phone_number).all()
    out = []
    for p in products:
        item = {
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "price": p.price,
            "image_urls": p.image_url.split(","),
            "delivery_range_km": p.delivery_range_km,
        }
        # Optional fields if they exist on the model
        if hasattr(p, "expiry_datetime"):
            item["expiry_datetime"] = p.expiry_datetime
        if hasattr(p, "shop_name"):
            item["shop_name"] = p.shop_name
        out.append(item)
    return out


@app.get("/seller/orders")
def get_seller_orders(
    current_user: dict = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    username = current_user["username"]

    orders = (
        db.query(Order)
        .join(OrderItem)
        .join(DBProduct)
        .filter(DBProduct.seller == username)
        .all()
    )

    return [
        {
            "id": order.id,
            "buyer": order.buyer,
            "address": order.address,
            "items": [
                {
                    "name": item.product.name,
                    "price": item.product.price,
                    "quantity": item.quantity,
                    "shop_name": item.shop_name or (item.product.shop_name if item.product else None),
                }
                for item in order.items
            ],
            "total": sum(price_to_float(item.product.price) * item.quantity for item in order.items)
            + SERVICE_FEE,
            "timestamp": order.timestamp.isoformat(),
            "status": order.status,
        }
        for order in orders
    ]


def _fulfill_order_logic(order_id: int, current_user: dict, db: Session):
    """Shared logic for marking an order as fulfilled."""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # Check ownership unless user is an admin
    if "admin" not in current_user["role"]:
        for item in order.items:
            if item.product.seller != current_user["username"]:
                raise HTTPException(status_code=403, detail="Unauthorized")

    order.status = "Fulfilled"
    db.commit()
    return {"msg": "Order marked as fulfilled"}


@app.post("/seller/orders/{order_id}/fulfill")
def mark_order_fulfilled(
    order_id: int,
    current_user: dict = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    return _fulfill_order_logic(order_id, current_user, db)


@app.post("/orders/{order_id}/fulfill")
def mark_order_fulfilled_general(
    order_id: int,
    current_user: dict = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """Endpoint for admins or sellers to mark an order as fulfilled."""
    return _fulfill_order_logic(order_id, current_user, db)


@app.post("/orders/{order_id}/complete")
def complete_order(
    order_id: int,
    current_user: dict = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """Allow admin or the buying user to mark an order as completed."""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if "admin" not in current_user["role"] and not (
        "buyer" in current_user["role"] and order.buyer == current_user["username"]
    ):
        raise HTTPException(status_code=403, detail="Unauthorized")

    if order.status != "Fulfilled":
        raise HTTPException(status_code=400, detail="Order not yet fulfilled")

    order.status = "Completed"
    db.commit()
    return {"msg": "Order marked as completed"}


@app.get("/buyer/notifications")
def get_notifications(
    current_user: dict = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    username = current_user["username"]

    orders = (
        db.query(Order)
        .filter(Order.buyer == username)
        .order_by(Order.timestamp.desc())
        .all()
    )

    return [
        {
            "id": o.id,
            "status": o.status,
            "timestamp": o.timestamp.isoformat(),
        }
        for o in orders
    ]


@app.get("/buyer/orders")
def get_buyer_orders(
    current_user: dict = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """Return all orders for the logged in buyer."""
    username = current_user["username"]

    orders = (
        db.query(Order)
        .filter(Order.buyer == username)
        .order_by(Order.timestamp.desc())
        .all()
    )

    return [
        {
            "id": o.id,
            "address": o.address,
            "items": [
                {
                    "name": item.product.name,
                    "price": item.product.price,
                    "quantity": item.quantity,
                    "shop_name": item.shop_name or None,

                }
                for item in o.items
            ],
            "total": sum(price_to_float(item.product.price) * item.quantity for item in o.items)
            + SERVICE_FEE,
            "status": o.status,
            "timestamp": o.timestamp.isoformat(),
        }
        for o in orders
    ]


@app.get("/api/orders/by-phone/{phone_number}")
def get_orders_by_phone(phone_number: str, db: Session = Depends(get_db)):
    """Return orders matching the provided phone number."""
    orders = (
        db.query(Order)
        .filter(Order.phone_number == phone_number)
        .order_by(Order.timestamp.desc())
        .all()
    )

    output = []
    for o in orders:
        output.append(
            {
                "id": o.id,
                "address": o.address,
                "items": [
                    {
                        "name": item.product.name if item.product else "[deleted]",
                        "price": item.product.price if item.product else "0",
                        "quantity": item.quantity,
                        
                    }
                    for item in o.items
                ],
                "total": sum(
                    price_to_float(item.product.price if item.product else "0")
                    * item.quantity
                    for item in o.items
                )
                + SERVICE_FEE,
                "status": o.status,
                "timestamp": o.timestamp.isoformat(),
            }
        )
    return output


@app.get("/admin/sellers")
def list_sellers(
    current_user: dict = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    if "admin" not in current_user["role"]:
        raise HTTPException(status_code=403, detail="Admins only")

    sellers = db.query(DBUser).filter(DBUser.role.like("%seller%")).all()
    return [
        {
            "username": s.username,
            "shop_name": s.shop_name,
            "address": s.address,
            "phone_number": s.phone_number,
        }
        for s in sellers
    ]

@app.get("/admin/sellers/details")
def list_seller_details(db: Session = Depends(get_db)):
    sellers = db.query(DBUser).all()  # start with all users
    output = []

    for s in sellers:
        # Check if the user is a seller by checking for a matching shop
        shop = db.query(Shop).filter(Shop.phone_number == s.phone_number).first()
        if not shop:
            continue  # skip non-sellers

        products = db.query(DBProduct).filter(DBProduct.phone_number == s.phone_number).all()

        output.append({
            "shop_name": shop.name,  # assuming `shop.name` exists
            "address": shop.address,
            "phone_number": s.phone_number,
            "products": [
                {
                    "id": p.id,
                    "name": p.name,
                    "description": p.description,
                    "price": p.price,
                    "delivery_range_km": p.delivery_range_km,
                    "image_urls": p.image_url.split(","),
                    "is_validated": p.is_validated,
                }
                for p in products
            ],
        })

    return output



@app.get("/products/{product_id}", response_model=ProductOut)
def get_product_public(product_id: int, db: Session = Depends(get_db)):
    product = db.query(DBProduct).filter(DBProduct.id == product_id).first()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    return {
        "id": product.id,
        "name": product.name,
        "description": product.description,
        "price": product.price,
        
        "delivery_range_km": product.delivery_range_km,
        
        "image_urls": product.image_url.split(","),
    }

# Load HTML templates from the same directory as other static files
templates = Jinja2Templates(directory="static")


@app.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(request: Request):
    return templates.TemplateResponse("forgot_password.html", {"request": request})


@app.post("/forgot-password")
async def process_forgot_password(email: str = Form(...), db: Session = Depends(get_db)):
    """Generate a reset token and email a link to the user."""
    user = db.query(DBUser).filter(DBUser.username == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="Email not found")

    token = _create_reset_token(user, db)
    reset_link = f"{APP_BASE_URL}/reset-password/{token}"
    _send_email(
        email,
        "Password Reset",
        f"Click the link to reset your password: {reset_link}",
    )

    logger.info("Password reset link sent to: %s", email)
    return RedirectResponse(url="/login", status_code=303)


# Registration is handled on the main page. The old form route is no longer used.
# @app.get("/register", response_class=HTMLResponse)
# def register_form(request: Request):
#     return templates.TemplateResponse("register.html", {"request": request})


@app.post("/send-reset-link")
async def send_reset_link(payload: ResetRequest, db: Session = Depends(get_db)):
    """Send a password reset link to the user's WhatsApp number."""
    user = db.query(DBUser).filter(DBUser.phone_number == payload.number).first()
    if not user:
        raise HTTPException(status_code=404, detail="Number not found")

    token = _create_reset_token(user, db)
    reset_link = f"{APP_BASE_URL}/reset-password/{token}"
    _send_whatsapp(payload.number, f"Reset your password here: {reset_link}")

    logger.info("Reset link sent via WhatsApp to %s", payload.number)
    return {"msg": "Reset link sent to your WhatsApp!"}


@app.post("/send-username")
async def send_username(payload: ResetRequest, db: Session = Depends(get_db)):
    """Send the user's username to their WhatsApp number."""
    user = db.query(DBUser).filter(DBUser.phone_number == payload.number).first()
    if not user:
        raise HTTPException(status_code=404, detail="Number not found")

    _send_whatsapp(payload.number, f"Your username is: {user.username}")
    logger.info("Username sent via WhatsApp to %s", payload.number)

    return {"msg": "Username sent to your WhatsApp!"}


# --- Admin Product Validation Endpoints ---


#def require_admin(current_user):
    # Directly access the 'role' attribute of the Admin object
 #   if current_user.role != "admin":
  #      raise HTTPException(status_code=403, detail="Admin privileges required")



@app.get("/admin/products/pending")
def list_pending_products(db: Session = Depends(get_db)):
    """Return all products awaiting validation."""
    products = db.query(DBProduct).filter(DBProduct.is_validated == False).all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "price": p.price,
            "phone_number": p.phone_number,
            "image_urls": p.image_url.split(",") if p.image_url else [],
            "delivery_range_km": p.delivery_range_km,
            
        }
        for p in products
    ]


@app.post("/admin/products/{product_id}/validate")
def validate_product(
    product_id: int,
    #current_user: dict = Depends(get_current_admin_from_token),
    db: Session = Depends(get_db),
):
    #require_admin(current_user)
    product = db.query(DBProduct).filter(DBProduct.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    product.is_validated = True
    db.commit()
    return {"msg": "Product validated"}


@app.delete("/admin/products/{product_id}")
def admin_delete_product(
    product_id: int,
    #current_user: dict = Depends(get_current_admin_from_token),
    db: Session = Depends(get_db),
):
    #require_admin(current_user)
    product = db.query(DBProduct).filter(DBProduct.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    db.delete(product)
    db.commit()
    return {"msg": "Product deleted"}


@app.get("/admin/shop/{phone_number}")
def admin_get_shop(
    phone_number: str,
    #current_user: dict = Depends(get_current_admin_from_token),
    db: Session = Depends(get_db),
):
    """Return shop details for the given phone number."""
    #require_admin(current_user)
    shop = db.query(Shop).filter(Shop.phone_number == phone_number).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    return {
        "name": shop.name,
        "address": shop.address,
        "phone_number": shop.phone_number,
    }

@app.post("/verify-shop")
def verify_shop(request: PhoneCheckRequest, db: Session = Depends(get_db)):
    shop = db.query(Shop).filter(Shop.phone_number == request.phone_number).first()
    return {"exists": bool(shop)}

@app.get("/admin/orders")
def get_all_orders(
    #current_user: dict = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """Return all orders for admin view."""
    #require_admin(current_user)
    orders = db.query(Order).all()
    out = []
    for order in orders:
        buyer = db.query(DBUser).filter(DBUser.username == order.buyer).first()
        out.append(
            {
                "id": order.id,
                "buyer": order.buyer,
                "phone_number": buyer.phone_number if buyer else None,
                "address": order.address,
                "items": [
                     {
                        "name": item.product.name if item.product else "[deleted]",
                        "price": item.product.price if item.product else "0",
                        "quantity": item.quantity,
                        "shop_name": item.shop_name or (item.product.shop_name if item.product else None),
                     }
                    for item in order.items
                ],
                "total": sum(
                    price_to_float(item.product.price if item.product else "0")
                    * item.quantity
                    for item in order.items
                )
                + SERVICE_FEE,
                "timestamp": order.timestamp.isoformat(),
                "status": order.status,
            }
        )
    return out


# ------- Admin Frontend Pages -------


@app.get("/admin", include_in_schema=False)
async def admin_dashboard_page():
    """Serve the admin dashboard page.

    Token validation happens client side via ``/admin/check`` so the HTML
    itself should be accessible without authentication.
    """
    return FileResponse("static/admin_dashboard.html")


@app.get("/static/admin_dashboard.html", include_in_schema=False)
async def admin_dashboard_static():
    """Serve the admin dashboard from the static path.

    The JavaScript on this page checks the stored token and redirects to the
    login page when missing or invalid.
    """
    return FileResponse("static/admin_dashboard.html")


@app.get("/admin/sellers/page", include_in_schema=False)
async def admin_sellers_page():
    """Serve the seller list HTML for admins."""
    return FileResponse("static/admin_sellers.html")


@app.get("/admin/register", include_in_schema=False)
async def admin_register_page():
    """Serve the admin registration form."""
    return FileResponse("static/admin_register.html")


# One-time admin phone registration page
@app.get("/admin/phone-register", include_in_schema=False)
async def admin_phone_register_page():
    """Serve the phone based admin registration page."""
    return FileResponse("static/admin_phone_register.html")


@app.post("/admin/phone-register", include_in_schema=False)
async def admin_phone_register(
    phone_number: str = Body(..., embed=True), db: Session = Depends(get_db)

):
    """Register a new admin using only a phone number once."""
    # If any admin already exists, block new registrations
    existing_admin = db.query(DBUser).filter(DBUser.role.like("%admin%"))
    if existing_admin.first():
        raise HTTPException(status_code=400, detail="Admin already registered")

    username = f"{phone_number}@{USERNAME_DOMAIN}"
    if db.query(DBUser).filter(DBUser.username == username).first():
        raise HTTPException(status_code=400, detail="Phone already registered")

    random_password = uuid4().hex
    db_user = DBUser(
        username=username,
        full_name="Admin",
        hashed_password=get_password_hash(random_password),
        role="admin",
        phone_number=phone_number,
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    token = create_access_token(data={"sub": db_user.username})
    return {"access_token": token}


# Expose all files in the ./static directory after custom routes so that
# /static/my_products.html can be overridden above.
app.mount("/static", StaticFiles(directory="static"), name="static")


# Admin login by phone number
@app.get("/admin/login", include_in_schema=False)
async def admin_login_page():
    """Serve the admin login page."""
    return FileResponse("static/admin_login.html")

@app.post("/admin/login", include_in_schema=False)
async def admin_login(
    phone_number: str = Body(..., embed=True), db: Session = Depends(get_db)
):
    """Login an existing admin using phone number only."""
    admin = db.query(Admin).filter(Admin.phone_number == phone_number).first()
    if not admin:
        raise HTTPException(status_code=400, detail="Invalid phone number")

    # Return a dummy access token for now
    access_token = create_access_token({"phone_number": phone_number})

    return JSONResponse(content={"access_token": access_token})


# Endpoint to verify admin token validity
@app.get("/admin/check", include_in_schema=False)
def admin_check():
    """Endpoint kept for compatibility but no longer performs auth."""
    return {"status": "ok"}
