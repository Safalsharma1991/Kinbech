# models.py
from sqlalchemy import Column, Integer, String, Float, ForeignKey, Boolean, create_engine, UniqueConstraint
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy import DateTime
from datetime import datetime
from pydantic import BaseModel
from typing import List
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class UserModel(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    full_name = Column(String)
    hashed_password = Column(String)
    role = Column(String)  # Make sure it's a plain string field
    shop_name = Column(String, unique=True)

    address = Column(String, nullable=True)
    phone_number = Column(String, nullable=True)


class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    description = Column(String)
    price = Column(Float)
    image_url = Column(String)  # Add this line
    is_validated = Column(Boolean, default=False)
    delivery_range_km = Column(Integer)
    phone_number = Column(String, unique=True, nullable=False)


class Seller(Base):
    __tablename__ = "sellers"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    # Add any other fields you need for the seller (like phone_number, email, etc.)




class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    buyer = Column(String)
    address = Column(String)
    status = Column(String, default="Pending")
    timestamp = Column(DateTime, default=datetime.utcnow)
    items = relationship("OrderItem", back_populates="order")


class OrderItem(Base):
    __tablename__ = "order_items"
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"))
    product_id = Column(Integer, ForeignKey("products.id"))
    shop_name = Column(String)
    quantity = Column(Integer)
    order = relationship("Order", back_populates="items")
    product = relationship("Product")


class ResetToken(Base):
    """Password reset tokens associated with a user."""

    __tablename__ = "reset_tokens"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    token = Column(String, unique=True, index=True)
    expires_at = Column(DateTime)

    user = relationship("UserModel")


class Shop(Base):
    __tablename__ = 'shop'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    address = Column(String, nullable=False)
    phone_number = Column(String, unique=True, nullable=False)

    __table_args__ = (
        UniqueConstraint('phone_number', name='uix_phone_number'),
    )

class Admin(Base):
    __tablename__ = 'admin'
    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String, unique=True, nullable=False)
    role = Column(String)
    __table_args__ = (
        UniqueConstraint('phone_number', name='uix_phone_number'),
    )

class AddedProduct(Base):
    """Log of all added products with minimal details."""

    __tablename__ = "added_products"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    product_name = Column(String, nullable=False)
    details = Column(String, nullable=True)

    user = relationship("UserModel")


class CheckoutItem(BaseModel):
    product_id: int
    quantity: int

class CheckoutRequest(BaseModel):
    address: str
    phone_number: str
    items: List[CheckoutItem]
