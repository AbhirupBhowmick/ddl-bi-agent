from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    String,
    Float,
    Integer,
    DateTime,
    ForeignKey,
    Index
)
from sqlalchemy.orm import relationship
from backend.database import Base


class Customer(Base):
    __tablename__ = "customers"

    customer_id = Column(String(50), primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    email = Column(String(100), nullable=False, unique=True, index=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    segment = Column(String(50), nullable=False, default="Consumer", index=True)

    orders = relationship("Order", back_populates="customer", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Customer {self.customer_id} - {self.name}>"


class Product(Base):
    __tablename__ = "products"

    product_id = Column(String(50), primary_key=True, index=True)
    name = Column(String(150), nullable=False)
    category = Column(String(50), nullable=False, index=True)
    cost_price = Column(Float, nullable=False)
    retail_price = Column(Float, nullable=False)
    stock_level = Column(Integer, nullable=False, default=0)

    order_items = relationship("OrderItem", back_populates="product")

    def __repr__(self):
        return f"<Product {self.product_id} - {self.name}>"


class Order(Base):
    __tablename__ = "orders"

    order_id = Column(String(50), primary_key=True, index=True)
    customer_id = Column(String(50), ForeignKey("customers.customer_id"), nullable=False, index=True)
    order_date = Column(DateTime, nullable=False, index=True)
    status = Column(String(20), nullable=False, default="completed", index=True)  # completed, cancelled, refunded
    total_amount = Column(Float, nullable=False, default=0.0)

    customer = relationship("Customer", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_orders_status_date", "status", "order_date"),
    )

    def __repr__(self):
        return f"<Order {self.order_id} - ${self.total_amount:.2f} ({self.status})>"


class OrderItem(Base):
    __tablename__ = "order_items"

    order_item_id = Column(String(50), primary_key=True, index=True)
    order_id = Column(String(50), ForeignKey("orders.order_id"), nullable=False, index=True)
    product_id = Column(String(50), ForeignKey("products.product_id"), nullable=False, index=True)
    quantity = Column(Integer, nullable=False, default=1)
    unit_price = Column(Float, nullable=False)
    line_total = Column(Float, nullable=False)

    order = relationship("Order", back_populates="items")
    product = relationship("Product", back_populates="order_items")

    __table_args__ = (
        Index("idx_order_items_product", "product_id"),
        Index("idx_order_items_order", "order_id"),
    )

    def __repr__(self):
        return f"<OrderItem {self.order_item_id} - Order {self.order_id}>"
