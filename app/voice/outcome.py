"""Save the call result: transcript, AI analysis, outcome. No follow-up actions yet."""

from datetime import UTC, datetime

from loguru import logger
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.db.models import Call, Lead, LeadEvent, LeadStatus, Outcome
from app.db.session import SessionLocal
from app.voice.analysis import analyse_transcript

LEAD_STATUS_FOR = {
    Outcome.APPOINTMENT_BOOKED: LeadStatus.APPOINTMENT_BOOKED,
    Outcome.NOT_INTERESTED: LeadStatus.CLOSED,
}


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _apply_outcome(call: Call, lead: Lead, outcome: Outcome) -> None:
    call.outcome = outcome
    lead.outcome = outcome
    lead.status = LEAD_STATUS_FOR.get(outcome, LeadStatus.FOLLOW_UP)


async def finish_call(call_id: int, transcript: list[dict], error: str | None) -> None:
    settings = get_settings()
    async with SessionLocal() as session:
        call = await session.get(Call, call_id, options=[selectinload(Call.lead)])
        if call is None:
            return
        lead = call.lead
        call.transcript = transcript
        call.ended_at = datetime.now(UTC)
        call.error = error
        lead.attempt_count += 1
        await session.commit()  # the transcript is safe even if analysis fails below

        machine = (call.answered_by or "").startswith(("machine", "fax"))
        customer_spoke = any(t["role"] == "user" and t["text"].strip() for t in transcript)
        if machine or not customer_spoke:
            _apply_outcome(call, lead, Outcome.DIDNT_ANSWER)
            lead.summary = "Voicemail or no response from the customer."
            await session.commit()
            return

        try:
            result = await analyse_transcript(settings, transcript, call.answered_at)
        except Exception as exc:  # noqa: BLE001 - keep the transcript, flag for follow-up
            logger.exception(f"Call {call_id}: analysis failed")
            call.error = f"{error or ''} analysis failed: {exc!r}".strip()
            lead.status = LeadStatus.FOLLOW_UP
            await session.commit()
            return

        call.analysis = result.model_dump()
        _apply_outcome(call, lead, Outcome(result.outcome))
        lead.budget = result.budget
        lead.timeline = result.timeline
        lead.trade_in = result.trade_in
        lead.trade_in_details = result.trade_in_details
        lead.financing_needed = result.financing_needed
        lead.summary = result.summary
        lead.callback_at = _parse_dt(result.callback_time)
        session.add(LeadEvent(lead_id=lead.id, type="call_analysed", data=call.analysis))
        await session.commit()
        logger.info(f"Call {call_id}: outcome {result.outcome}")


async def mark_not_connected(call_id: int, telephony_status: str) -> None:
    """Call ended without ever reaching the media stream (no-answer, busy, failed, ...)."""
    async with SessionLocal() as session:
        call = await session.get(Call, call_id, options=[selectinload(Call.lead)])
        if call is None or call.answered_at is not None:
            return
        call.ended_at = datetime.now(UTC)
        call.lead.attempt_count += 1
        if telephony_status in ("failed", "completed"):
            call.error = call.error or (
                "Twilio reported the call as failed"
                if telephony_status == "failed"
                else "Call was answered but the media stream never connected (check the tunnel)"
            )
            call.lead.status = LeadStatus.FAILED
        else:
            _apply_outcome(call, call.lead, Outcome.DIDNT_ANSWER)
        await session.commit()
