"""Runs one live phone conversation: Twilio Media Stream <-> Pipecat <-> realtime LLM."""

from datetime import UTC, datetime

from fastapi import WebSocket
from loguru import logger
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.frames.frames import EndWorkerFrame, LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    AssistantTurnStoppedMessage,
    LLMContextAggregatorPair,
    UserTurnMessageAddedMessage,
)
from pipecat.runner.utils import parse_telephony_websocket
from pipecat.serializers.twilio import TwilioFrameSerializer
from pipecat.services.llm_service import FunctionCallParams
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams, FastAPIWebsocketTransport
from pipecat.workers.runner import WorkerRunner
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.db.models import Call, Lead, LeadStatus
from app.db.session import SessionLocal
from app.voice.engines import create_llm
from app.voice.outcome import finish_call
from app.voice.prompt import build_system_prompt

END_CALL = FunctionSchema(
    name="end_call",
    description="Hang up the phone. Call this only after you have said goodbye.",
    properties={},
    required=[],
)


async def run_call(websocket: WebSocket, call_id: int) -> None:
    settings = get_settings()
    _, call_data = await parse_telephony_websocket(websocket)

    async with SessionLocal() as session:
        call = await session.scalar(
            select(Call)
            .where(Call.id == call_id)
            .options(selectinload(Call.lead).selectinload(Lead.vehicle))
        )
        if call is None or (call.twilio_call_sid and call.twilio_call_sid != call_data.call_id):
            logger.warning(
                f"Rejecting media stream for call {call_id}: unknown call or SID mismatch"
            )
            await websocket.close()
            return
        call.twilio_call_sid = call.twilio_call_sid or call_data.call_id
        call.answered_at = datetime.now(UTC)
        call.lead.status = LeadStatus.IN_PROGRESS
        llm, call.model = create_llm(settings, build_system_prompt(settings, call.lead))
        first_name = call.lead.first_name
        await session.commit()

    transcript: list[dict] = []
    error: str | None = None

    transport = FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            session_timeout=settings.max_call_seconds,
            serializer=TwilioFrameSerializer(
                stream_sid=call_data.stream_id,
                call_sid=call_data.call_id,
                account_sid=settings.twilio_account_sid,
                auth_token=settings.twilio_auth_token,
            ),
        ),
    )

    context = LLMContext(tools=ToolsSchema(standard_tools=[END_CALL]))
    user_agg, assistant_agg = LLMContextAggregatorPair(context)

    pipeline = Pipeline([transport.input(), user_agg, llm, transport.output(), assistant_agg])
    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(enable_metrics=True, enable_usage_metrics=True),
        enable_rtvi=False,
    )

    async def end_call(params: FunctionCallParams) -> None:
        logger.info(f"Call {call_id}: agent ended the call")
        await params.result_callback({"status": "ending call"})
        # Flushes queued audio (the goodbye) before the pipeline ends; the serializer then hangs up.
        await params.llm.push_frame(EndWorkerFrame(reason="agent ended call"))

    llm.register_function("end_call", end_call)

    @user_agg.event_handler("on_user_turn_message_added")
    async def on_user_text(_aggregator, message: UserTurnMessageAddedMessage) -> None:
        transcript.append({"role": "user", "text": message.content, "t": message.timestamp})

    @assistant_agg.event_handler("on_assistant_turn_stopped")
    async def on_assistant_text(_aggregator, message: AssistantTurnStoppedMessage) -> None:
        if message.content:
            transcript.append(
                {
                    "role": "assistant",
                    "text": message.content,
                    "t": message.timestamp,
                    "interrupted": message.interrupted,
                }
            )

    @transport.event_handler("on_client_connected")
    async def on_connected(_transport, _client) -> None:
        context.add_message(
            {"role": "developer", "content": f"The call has connected. Greet {first_name} now."}
        )
        await worker.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_disconnected(_transport, _client) -> None:
        await worker.cancel(reason="caller hung up")

    @transport.event_handler("on_session_timeout")
    async def on_timeout(_transport, _client) -> None:
        logger.warning(f"Call {call_id}: max duration reached")
        await worker.cancel(reason="max call duration")

    try:
        runner = WorkerRunner(handle_sigint=False)
        await runner.add_workers(worker)
        await runner.run()
    except Exception as exc:  # noqa: BLE001 - the call must still be saved and analysed
        logger.exception(f"Call {call_id}: pipeline error")
        error = repr(exc)
    finally:
        await finish_call(call_id, transcript, error)
