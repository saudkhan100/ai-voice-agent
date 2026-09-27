"""Start a test call with a phone number + car details, read back the result, Twilio webhooks."""

import secrets
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

import phonenumbers
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, WebSocket
from loguru import logger
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from twilio.base.exceptions import TwilioRestException

from app.config import Settings, get_settings
from app.db.models import Call, Lead, LeadSource, LeadStatus, Vehicle
from app.db.session import get_session
from app.telephony import twilio_client
from app.voice.bot import run_call
from app.voice.outcome import mark_not_connected

router = APIRouter()

Session = Annotated[AsyncSession, Depends(get_session)]
Config = Annotated[Settings, Depends(get_settings)]


def require_api_key(config: Config, x_api_key: Annotated[str, Header()] = "") -> None:
    if not secrets.compare_digest(x_api_key, config.lead_api_key):
        raise HTTPException(401, "Invalid API key")


# --- Start a call ------------------------------------------------------------


class VehicleIn(BaseModel):
    year: int | None = None
    make: str
    model: str
    trim: str | None = None
    condition: str | None = None
    price: Decimal | None = None
    mileage: int | None = None
    ext_color: str | None = None
    int_color: str | None = None
    body_style: str | None = None
    stock_number: str | None = None
    vin: str | None = None
    features: list[str] = []
    description: str | None = None


class CallRequest(BaseModel):
    phone: str
    first_name: str
    last_name: str | None = None
    customer_message: str | None = None
    vehicle: VehicleIn

    @field_validator("phone")
    @classmethod
    def e164(cls, v: str) -> str:
        try:
            number = phonenumbers.parse(v, None)
        except phonenumbers.NumberParseException as exc:
            raise ValueError("phone must be in E.164 format, e.g. +14165550123") from exc
        if not phonenumbers.is_valid_number(number):
            raise ValueError("phone is not a valid number")
        return phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)


@router.post("/api/calls", status_code=201, dependencies=[Depends(require_api_key)])
async def start_call(body: CallRequest, session: Session, config: Config) -> dict:
    if not config.twilio_enabled:
        raise HTTPException(503, "Twilio is disabled (TWILIO_ENABLED=false)")
    if not (config.twilio_account_sid and config.twilio_auth_token and config.twilio_from_number):
        raise HTTPException(503, "Twilio credentials are not configured")
    if not config.public_base_url.startswith("https://"):
        raise HTTPException(503, "PUBLIC_BASE_URL must be an https tunnel/domain Twilio can reach")

    # Vehicles supplied by hand are not inventory rows; keep VIN/stock off them to avoid clashes.
    vehicle = Vehicle(**body.vehicle.model_dump(exclude={"vin", "stock_number"}))
    lead = Lead(
        external_lead_id=f"manual-{uuid.uuid4().hex[:12]}",
        source=LeadSource.OTHER,
        first_name=body.first_name,
        last_name=body.last_name,
        phone=body.phone,
        vin=body.vehicle.vin,
        stock_number=body.vehicle.stock_number,
        customer_message=body.customer_message,
        inquiry_time=datetime.now(UTC),
        vehicle=vehicle,
        status=LeadStatus.QUEUED,
    )
    call = Call(
        lead=lead,
        attempt_no=1,
        engine=config.voice_engine,
        model="pending",
        started_at=datetime.now(UTC),
    )
    session.add_all([vehicle, lead, call])
    await session.commit()

    try:
        call.twilio_call_sid = await twilio_client.place_call(config, body.phone, call.id)
    except TwilioRestException as exc:
        message = f"Twilio error {exc.code}: {exc.msg}"
        logger.error(f"Call {call.id}: {message}")
        call.error = message
        lead.status = LeadStatus.FAILED
        await session.commit()
        raise HTTPException(502, message) from exc
    await session.commit()
    return {"call_id": call.id, "lead_id": str(lead.id), "twilio_call_sid": call.twilio_call_sid}


# --- Read the result -----------------------------------------------------------


@router.get("/api/calls/{call_id}", dependencies=[Depends(require_api_key)])
async def get_call(call_id: int, session: Session) -> dict:
    call = await session.get(Call, call_id, options=[selectinload(Call.lead)])
    if call is None:
        raise HTTPException(404, "Call not found")
    lead = call.lead
    return {
        "call_id": call.id,
        "engine": call.engine,
        "model": call.model,
        "telephony_status": call.telephony_status,
        "answered_by": call.answered_by,
        "duration_s": call.duration_s,
        "outcome": call.outcome,
        "error": call.error,
        "recording_url": call.recording_url,
        "lead": {
            "id": str(lead.id),
            "name": f"{lead.first_name} {lead.last_name or ''}".strip(),
            "phone": lead.phone,
            "status": lead.status,
            "budget": lead.budget,
            "timeline": lead.timeline,
            "trade_in": lead.trade_in,
            "trade_in_details": lead.trade_in_details,
            "financing_needed": lead.financing_needed,
            "callback_at": lead.callback_at,
            "summary": lead.summary,
        },
        "analysis": call.analysis,
        "transcript": call.transcript,
    }


# --- Twilio webhooks & media stream ----------------------------------------------


async def twilio_form(request: Request, config: Config) -> dict:
    form = dict(await request.form())
    # Twilio signs the public URL it called, not the internal one behind the tunnel/proxy.
    url = config.public_base_url.rstrip("/") + request.url.path
    if request.url.query:
        url += "?" + request.url.query
    signature = request.headers.get("X-Twilio-Signature", "")
    if not twilio_client.is_valid_signature(config, url, form, signature):
        raise HTTPException(403, "Invalid Twilio signature")
    return form


TwilioForm = Annotated[dict, Depends(twilio_form)]
NOT_CONNECTED = {"no-answer", "busy", "failed", "canceled", "completed"}


@router.post("/twilio/status/{call_id}")
async def twilio_status(call_id: int, form: TwilioForm, session: Session) -> Response:
    call = await session.get(Call, call_id)
    if call is None:
        return Response(status_code=204)
    status = form.get("CallStatus")
    call.telephony_status = status
    if form.get("CallDuration"):
        call.duration_s = int(form["CallDuration"])
    await session.commit()
    if status in NOT_CONNECTED:
        await mark_not_connected(call_id, status)
    return Response(status_code=204)


@router.post("/twilio/amd/{call_id}")
async def twilio_amd(call_id: int, form: TwilioForm, session: Session, config: Config) -> Response:
    call = await session.get(Call, call_id)
    if call is None:
        return Response(status_code=204)
    call.answered_by = form.get("AnsweredBy")
    await session.commit()
    if (
        call.answered_by
        and call.answered_by.startswith(("machine", "fax"))
        and call.twilio_call_sid
    ):
        # Voicemail: hang up now (prerecorded voicemail + SMS come in a later phase).
        logger.info(f"Call {call_id}: answered by {call.answered_by}, hanging up")
        await twilio_client.hang_up(config, call.twilio_call_sid)
    return Response(status_code=204)


@router.post("/twilio/recording/{call_id}")
async def twilio_recording(call_id: int, form: TwilioForm, session: Session) -> Response:
    call = await session.get(Call, call_id)
    if call is not None and form.get("RecordingStatus") == "completed":
        call.recording_sid = form.get("RecordingSid")
        call.recording_url = form.get("RecordingUrl")
        await session.commit()
    return Response(status_code=204)


@router.websocket("/ws/calls/{call_id}")
async def media_stream(websocket: WebSocket, call_id: int) -> None:
    await websocket.accept()
    await run_call(websocket, call_id)
