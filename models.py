# models.py
from sqlalchemy import Column, Integer, String, Float, ForeignKey, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy import DateTime
from datetime import datetime
from pydantic import BaseModel
from typing import List

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
    seller = Column(String)
    shop_name = Column(String)
    image_url = Column(String)  # Add this line
    is_validated = Column(Boolean, default=False)
    delivery_range_km = Column(Integer)
    expiry_datetime = Column(String)


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
    product_id = Column(Integer)
    quantity = Column(Integer)
    order = relationship("Order", back_populates="items")
