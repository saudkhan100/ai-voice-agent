"""Database schema. Enum-like columns are stored as varchar so adding a value needs no migration."""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def str_enum(enum_cls: type[StrEnum]) -> SAEnum:
    return SAEnum(
        enum_cls, native_enum=False, length=40, values_callable=lambda e: [m.value for m in e]
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# --- Enums -----------------------------------------------------------------


class UserRole(StrEnum):
    ADMIN = "admin"
    SALES = "sales"
    MANAGER = "manager"


class VehicleStatus(StrEnum):
    AVAILABLE = "available"
    PENDING = "pending"
    SOLD = "sold"
    REMOVED = "removed"


class LeadSource(StrEnum):
    AUTOTRADER = "AutoTrader"
    CARGURUS = "CarGurus"
    AUTOBUNNY = "AutoBunny"
    OTHER = "Other"


class IntakeChannel(StrEnum):
    CSV = "csv"
    API = "api"
    EMAIL = "email"


class MatchMethod(StrEnum):
    VIN = "vin"
    STOCK = "stock"
    DESCRIPTION = "description"
    NONE = "none"


class LeadStatus(StrEnum):
    NEW = "new"
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    FOLLOW_UP = "follow_up"
    APPOINTMENT_BOOKED = "appointment_booked"
    CLOSED = "closed"
    FAILED = "failed"


class Outcome(StrEnum):
    APPOINTMENT_BOOKED = "Appointment booked"
    SERIOUS_BUYER = "Serious buyer"
    BUSY = "Busy"
    DIDNT_ANSWER = "Didn't answer"
    NOT_INTERESTED = "Not interested"
    PROBLEM = "Problem/issue"


class AppointmentType(StrEnum):
    TEST_DRIVE = "test_drive"
    VIEWING = "viewing"


class AppointmentStatus(StrEnum):
    BOOKED = "booked"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"
    COMPLETED = "completed"


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


# --- Tables ----------------------------------------------------------------


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True)
    phone: Mapped[str | None] = mapped_column(String(20))
    role: Mapped[UserRole] = mapped_column(str_enum(UserRole), default=UserRole.SALES)
    receives_alerts: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))


class DealershipSettings(TimestampMixin, Base):
    """Single-row table holding dealer facts and business rules editable from the dashboard."""

    __tablename__ = "dealership_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    address: Mapped[str | None] = mapped_column(Text)
    timezone: Mapped[str] = mapped_column(String(64), default="America/Toronto")
    business_hours: Mapped[dict] = mapped_column(
        JSONB, default=dict
    )  # {"mon": ["09:00","18:00"], ...}
    calling_hours: Mapped[dict] = mapped_column(JSONB, default=dict)
    slot_length_min: Mapped[int] = mapped_column(Integer, default=30)
    dedupe_window_days: Mapped[int] = mapped_column(Integer, default=14)
    max_call_attempts: Mapped[int] = mapped_column(Integer, default=3)
    voicemail_audio_url: Mapped[str | None] = mapped_column(String(500))
    agent_name: Mapped[str] = mapped_column(String(60), default="Alex")
    extra_facts: Mapped[str | None] = mapped_column(Text)  # policies, fees, etc. fed to the prompt


class Vehicle(TimestampMixin, Base):
    __tablename__ = "vehicles"

    id: Mapped[int] = mapped_column(primary_key=True)
    vin: Mapped[str | None] = mapped_column(String(17), unique=True)
    stock_number: Mapped[str | None] = mapped_column(String(40), unique=True)
    year: Mapped[int | None] = mapped_column(Integer)
    make: Mapped[str | None] = mapped_column(String(60))
    model: Mapped[str | None] = mapped_column(String(80))
    trim: Mapped[str | None] = mapped_column(String(120))
    condition: Mapped[str | None] = mapped_column(String(20))  # new / used / cpo
    body_style: Mapped[str | None] = mapped_column(String(60))
    ext_color: Mapped[str | None] = mapped_column(String(60))
    int_color: Mapped[str | None] = mapped_column(String(60))
    mileage: Mapped[int | None] = mapped_column(Integer)
    price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    status: Mapped[VehicleStatus] = mapped_column(
        str_enum(VehicleStatus), default=VehicleStatus.AVAILABLE
    )
    features: Mapped[list] = mapped_column(JSONB, default=list)
    description: Mapped[str | None] = mapped_column(Text)
    photo_urls: Mapped[list] = mapped_column(JSONB, default=list)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (Index("ix_vehicles_make_model_year", "make", "model", "year"),)


class InventorySync(Base):
    __tablename__ = "inventory_syncs"

    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[JobStatus] = mapped_column(str_enum(JobStatus), default=JobStatus.RUNNING)
    added: Mapped[int] = mapped_column(Integer, default=0)
    updated: Mapped[int] = mapped_column(Integer, default=0)
    removed: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[list] = mapped_column(JSONB, default=list)


class LeadBatch(Base):
    __tablename__ = "lead_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    channel: Mapped[IntakeChannel] = mapped_column(str_enum(IntakeChannel))
    filename: Mapped[str | None] = mapped_column(String(255))
    uploaded_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    total: Mapped[int] = mapped_column(Integer, default=0)
    accepted: Mapped[int] = mapped_column(Integer, default=0)
    rejected: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[list] = mapped_column(
        JSONB, default=list
    )  # [{"row": 3, "field": "phone", "message": ...}]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Lead(TimestampMixin, Base):
    __tablename__ = "leads"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    external_lead_id: Mapped[str] = mapped_column(String(100))
    source: Mapped[LeadSource] = mapped_column(str_enum(LeadSource))
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("lead_batches.id"))

    first_name: Mapped[str] = mapped_column(String(80))
    last_name: Mapped[str | None] = mapped_column(String(80))
    phone: Mapped[str] = mapped_column(String(20))  # E.164
    email: Mapped[str | None] = mapped_column(String(255))

    vin: Mapped[str | None] = mapped_column(String(17))
    stock_number: Mapped[str | None] = mapped_column(String(40))
    vehicle_description: Mapped[str | None] = mapped_column(String(255))
    customer_message: Mapped[str | None] = mapped_column(Text)
    inquiry_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    vehicle_id: Mapped[int | None] = mapped_column(ForeignKey("vehicles.id"))
    match_method: Mapped[MatchMethod] = mapped_column(
        str_enum(MatchMethod), default=MatchMethod.NONE
    )

    status: Mapped[LeadStatus] = mapped_column(str_enum(LeadStatus), default=LeadStatus.NEW)
    outcome: Mapped[Outcome | None] = mapped_column(str_enum(Outcome))
    budget: Mapped[str | None] = mapped_column(String(120))
    timeline: Mapped[str | None] = mapped_column(String(120))
    trade_in: Mapped[bool | None] = mapped_column(Boolean)
    trade_in_details: Mapped[str | None] = mapped_column(Text)
    financing_needed: Mapped[bool | None] = mapped_column(Boolean)
    summary: Mapped[str | None] = mapped_column(Text)
    callback_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    assigned_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    do_not_contact: Mapped[bool] = mapped_column(Boolean, default=False)

    vehicle: Mapped[Vehicle | None] = relationship()
    calls: Mapped[list["Call"]] = relationship(back_populates="lead", order_by="Call.attempt_no")

    __table_args__ = (
        UniqueConstraint("source", "external_lead_id", name="uq_leads_source_external_id"),
        Index("ix_leads_phone_created", "phone", "created_at"),
        Index("ix_leads_status", "status"),
    )


class Call(TimestampMixin, Base):
    __tablename__ = "calls"

    id: Mapped[int] = mapped_column(primary_key=True)
    lead_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"), index=True
    )
    attempt_no: Mapped[int] = mapped_column(Integer, default=1)
    twilio_call_sid: Mapped[str | None] = mapped_column(String(64), unique=True)
    engine: Mapped[str] = mapped_column(String(20))
    model: Mapped[str] = mapped_column(String(100))
    telephony_status: Mapped[str | None] = mapped_column(String(20))  # Twilio CallStatus
    answered_by: Mapped[str | None] = mapped_column(String(30))  # Twilio AMD AnsweredBy
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_s: Mapped[int | None] = mapped_column(Integer)
    recording_sid: Mapped[str | None] = mapped_column(String(64))
    recording_url: Mapped[str | None] = mapped_column(String(500))
    transcript: Mapped[list] = mapped_column(JSONB, default=list)  # [{"role","text","t"}]
    analysis: Mapped[dict | None] = mapped_column(JSONB)
    outcome: Mapped[Outcome | None] = mapped_column(str_enum(Outcome))
    latency_ms: Mapped[dict | None] = mapped_column(JSONB)  # {"p50":..,"p95":..}
    usage: Mapped[dict | None] = mapped_column(JSONB)  # tokens / cost estimates
    error: Mapped[str | None] = mapped_column(Text)

    lead: Mapped[Lead] = relationship(back_populates="calls")


class Appointment(TimestampMixin, Base):
    __tablename__ = "appointments"

    id: Mapped[int] = mapped_column(primary_key=True)
    lead_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"), index=True
    )
    vehicle_id: Mapped[int | None] = mapped_column(ForeignKey("vehicles.id"))
    call_id: Mapped[int | None] = mapped_column(ForeignKey("calls.id"))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    type: Mapped[AppointmentType] = mapped_column(str_enum(AppointmentType))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[AppointmentStatus] = mapped_column(
        str_enum(AppointmentStatus), default=AppointmentStatus.BOOKED
    )
    calendar_provider: Mapped[str | None] = mapped_column(String(30))
    external_event_id: Mapped[str | None] = mapped_column(String(255))


class Message(Base):
    """Every SMS/email sent or received, for audit and the lead timeline."""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("leads.id", ondelete="SET NULL"), index=True
    )
    channel: Mapped[str] = mapped_column(String(10))  # sms / email
    direction: Mapped[str] = mapped_column(String(10))  # out / in
    to_addr: Mapped[str] = mapped_column(String(255))
    from_addr: Mapped[str | None] = mapped_column(String(255))
    template: Mapped[str | None] = mapped_column(String(60))
    body: Mapped[str] = mapped_column(Text)
    provider_id: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Job(Base):
    """Durable job queue; workers claim rows with SELECT ... FOR UPDATE SKIP LOCKED."""

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    status: Mapped[JobStatus] = mapped_column(str_enum(JobStatus), default=JobStatus.PENDING)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    last_error: Mapped[str | None] = mapped_column(Text)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lead_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_jobs_pending_run_at", "status", "run_at"),)


class LeadEvent(Base):
    __tablename__ = "lead_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    lead_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[str] = mapped_column(String(40))
    data: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DncNumber(Base):
    __tablename__ = "dnc_numbers"

    phone: Mapped[str] = mapped_column(String(20), primary_key=True)
    reason: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
