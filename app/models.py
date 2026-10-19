from datetime import date, datetime, time

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, LargeBinary, String, Text, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Service(Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(Text, default="")
    price: Mapped[float] = mapped_column(Float)
    duration_minutes: Mapped[int] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    image_data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True, deferred=True)
    image_revision: Mapped[str] = mapped_column(String(64), default="", server_default="")

    appointments: Mapped[list["Appointment"]] = relationship(back_populates="service")


class BusinessHours(Base):
    __tablename__ = "business_hours"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    weekday: Mapped[int] = mapped_column(Integer, unique=True)
    is_open: Mapped[bool] = mapped_column(Boolean, default=True)
    open_time: Mapped[time] = mapped_column(Time)
    close_time: Mapped[time] = mapped_column(Time)
    break_start: Mapped[time | None] = mapped_column(Time, nullable=True)
    break_end: Mapped[time | None] = mapped_column(Time, nullable=True)


class ClosedDate(Base):
    __tablename__ = "closed_dates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    day: Mapped[date] = mapped_column(Date, unique=True)
    reason: Mapped[str] = mapped_column(String(120), default="Folga")


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    phone: Mapped[str] = mapped_column(String(30))
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    verification_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    verification_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    appointments: Mapped[list["Appointment"]] = relationship(back_populates="customer")


class Appointment(Base):
    __tablename__ = "appointments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"))
    client_name: Mapped[str] = mapped_column(String(120))
    client_phone: Mapped[str] = mapped_column(String(30))
    notes: Mapped[str] = mapped_column(Text, default="")
    day: Mapped[date] = mapped_column(Date)
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
    status: Mapped[str] = mapped_column(String(20), default="confirmado")
    created_at: Mapped[datetime] = mapped_column(DateTime)
    whatsapp_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    whatsapp_error: Mapped[str] = mapped_column(Text, default="")
    amount_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payment_method: Mapped[str] = mapped_column(String(20), default="no_local", server_default="no_local")
    payment_status: Mapped[str] = mapped_column(String(20), default="pendente", server_default="pendente")
    payment_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    pix_key: Mapped[str] = mapped_column(String(254), default="", server_default="")
    pix_recipient: Mapped[str] = mapped_column(String(120), default="", server_default="")
    mercadopago_preference_id: Mapped[str] = mapped_column(String(100), default="", server_default="")
    mercadopago_payment_id: Mapped[str] = mapped_column(String(100), default="", server_default="")
    payment_provider_status: Mapped[str] = mapped_column(String(40), default="", server_default="")

    service: Mapped[Service] = relationship(back_populates="appointments")
    customer: Mapped[Customer | None] = relationship(back_populates="appointments")
