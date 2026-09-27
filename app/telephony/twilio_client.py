"""Thin wrapper over the Twilio REST client: place calls, hang up, validate webhooks."""

import asyncio
from xml.sax.saxutils import quoteattr

from twilio.request_validator import RequestValidator
from twilio.rest import Client

from app.config import Settings


def _client(settings: Settings) -> Client:
    return Client(settings.twilio_account_sid, settings.twilio_auth_token)


def stream_twiml(settings: Settings, call_id: int) -> str:
    url = f"{settings.ws_base_url}/ws/calls/{call_id}"
    return f"<Response><Connect><Stream url={quoteattr(url)} /></Connect></Response>"


async def place_call(settings: Settings, to: str, call_id: int) -> str:
    """Dial `to`; when answered, Twilio streams audio to our websocket. Returns the Call SID."""
    base = settings.public_base_url
    kwargs = {
        "to": to,
        "from_": settings.twilio_from_number,
        "twiml": stream_twiml(settings, call_id),
        "status_callback": f"{base}/twilio/status/{call_id}",
        "status_callback_event": ["initiated", "ringing", "answered", "completed"],
        # Async AMD: the call connects immediately; Twilio tells us later if a machine answered.
        "machine_detection": "Enable",
        "async_amd": "true",
        "async_amd_status_callback": f"{base}/twilio/amd/{call_id}",
        "timeout": 30,
    }
    if settings.twilio_record_calls:
        kwargs |= {
            "record": True,
            "recording_channels": "dual",
            "recording_status_callback": f"{base}/twilio/recording/{call_id}",
        }
    call = await asyncio.to_thread(_client(settings).calls.create, **kwargs)
    return call.sid


async def hang_up(settings: Settings, call_sid: str) -> None:
    await asyncio.to_thread(_client(settings).calls(call_sid).update, status="completed")


def is_valid_signature(settings: Settings, url: str, params: dict, signature: str) -> bool:
    if not settings.twilio_validate_signatures:
        return True
    return RequestValidator(settings.twilio_auth_token).validate(url, params, signature)
