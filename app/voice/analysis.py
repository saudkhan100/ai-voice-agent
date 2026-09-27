"""Post-call analysis: transcript -> structured outcome via Gemini Flash (text mode)."""

from datetime import datetime
from typing import Literal

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from app.config import Settings

OutcomeLabel = Literal[
    "Appointment booked",
    "Serious buyer",
    "Busy",
    "Didn't answer",
    "Not interested",
    "Problem/issue",
]


class CallAnalysis(BaseModel):
    outcome: OutcomeLabel
    budget: str | None = Field(None, description="Customer's budget in their words, if stated")
    timeline: str | None = Field(None, description="When they plan to buy, if stated")
    trade_in: bool | None = Field(None, description="Whether they have a trade-in")
    trade_in_details: str | None = Field(None, description="Year/make/model/condition of trade-in")
    financing_needed: bool | None = None
    appointment_requested: str | None = Field(
        None, description="Day/time the customer asked for a test drive or viewing, as said"
    )
    callback_time: str | None = Field(
        None,
        description="When the customer asked to be called back, as an ISO 8601 datetime if "
        "it can be resolved from the call time, otherwise as said",
    )
    wants_human: bool = Field(
        False, description="Customer asked for a person or a question was left unanswered"
    )
    summary: str = Field(description="Two or three sentences for the salesperson")


INSTRUCTIONS = """You analyse transcripts of phone calls between an AI assistant for a car
dealership and a customer who enquired about a vehicle online. Return JSON only.

Outcome rules (pick exactly one):
- "Appointment booked": the customer agreed to a specific day/time for a test drive or viewing.
- "Serious buyer": interested and engaged (budget/timeline discussed) but no appointment agreed.
- "Busy": the customer could not talk now and asked to be called back.
- "Didn't answer": no real conversation with the customer (voicemail, silence, hung up at once).
- "Not interested": the customer declined, already bought elsewhere, or asked not to be called.
- "Problem/issue": complaint, angry customer, wrong person, or anything a manager should see.

Only record facts the customer actually said. Use null for anything not mentioned."""


def format_transcript(transcript: list[dict]) -> str:
    speaker = {"assistant": "AI", "user": "Customer"}
    return "\n".join(f"{speaker.get(t['role'], t['role'])}: {t['text']}" for t in transcript)


async def analyse_transcript(
    settings: Settings, transcript: list[dict], call_started: datetime | None
) -> CallAnalysis:
    client = genai.Client(api_key=settings.google_api_key)
    when = call_started.isoformat() if call_started else "unknown"
    response = await client.aio.models.generate_content(
        model=settings.gemini_analysis_model,
        contents=f"Call started at: {when}\n\nTranscript:\n{format_transcript(transcript)}",
        config=types.GenerateContentConfig(
            system_instruction=INSTRUCTIONS,
            response_mime_type="application/json",
            response_schema=CallAnalysis,
            temperature=0,
        ),
    )
    if isinstance(response.parsed, CallAnalysis):
        return response.parsed
    return CallAnalysis.model_validate_json(response.text or "{}")
