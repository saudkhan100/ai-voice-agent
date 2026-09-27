"""Speech-to-speech engine factory. The rest of the pipeline never imports a specific engine."""

from pipecat.services.llm_service import LLMService

from app.config import Settings


def create_llm(settings: Settings, system_instruction: str) -> tuple[LLMService, str]:
    """Return the configured realtime LLM service and the model name it will use."""
    if settings.voice_engine == "gemini":
        from pipecat.services.google.gemini_live.llm import GeminiLiveLLMService

        overrides = {"model": settings.gemini_live_model} if settings.gemini_live_model else {}
        llm = GeminiLiveLLMService(
            api_key=settings.google_api_key,
            settings=GeminiLiveLLMService.Settings(
                system_instruction=system_instruction, voice=settings.gemini_voice, **overrides
            ),
        )
    elif settings.voice_engine == "openai":
        from pipecat.services.openai.realtime.events import (
            AudioConfiguration,
            AudioInput,
            InputAudioNoiseReduction,
            InputAudioTranscription,
            SemanticTurnDetection,
            SessionProperties,
        )
        from pipecat.services.openai.realtime.llm import OpenAIRealtimeLLMService

        overrides = (
            {"model": settings.openai_realtime_model} if settings.openai_realtime_model else {}
        )
        llm = OpenAIRealtimeLLMService(
            api_key=settings.openai_api_key,
            settings=OpenAIRealtimeLLMService.Settings(
                system_instruction=system_instruction,
                session_properties=SessionProperties(
                    audio=AudioConfiguration(
                        input=AudioInput(
                            transcription=InputAudioTranscription(),
                            turn_detection=SemanticTurnDetection(),
                            noise_reduction=InputAudioNoiseReduction(type="far_field"),
                        )
                    )
                ),
                **overrides,
            ),
        )
    else:
        raise ValueError(f"Unknown VOICE_ENGINE: {settings.voice_engine}")

    # Pipecat exposes no public accessor for the resolved model; it is only used for call logging.
    model = str(getattr(getattr(llm, "_settings", None), "model", "") or "unknown")
    return llm, model.removeprefix("models/")
