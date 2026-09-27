# AI Voice Agent

An AI voice agent that makes real phone calls. You give it a phone number and some context
through an API; it calls the person, holds a natural spoken conversation with a real-time AI
voice model, and saves the transcript plus a structured summary of the call to a database.

It can be used for any outbound calling task, for example:

- Following up on new leads (sales, real estate, insurance, education)
- Appointment booking, reminders and confirmations (clinics, salons, service centres)
- Customer feedback and satisfaction surveys
- Order, delivery or payment follow-ups
- Qualifying enquiries before handing them to a human

**Built-in example:** the project ships configured for a car dealership. The agent calls someone
who enquired about a car, answers questions about it, asks about budget, timeline, trade-in and
financing, and offers a test drive. See [Adapting it to your use case](#adapting-it-to-your-use-case)
to change the script for anything else.

## How it works

```
POST /api/calls ──► Twilio places the call ──► person answers
                                                   │
             Twilio streams audio over WebSocket (/ws/calls/{id})
                                                   │
                        Pipecat pipeline ◄──► Gemini Live / OpenAI Realtime
                                                   │ (speech-to-speech AI)
                            call ends ──► Gemini analyses the transcript
                                                   │
                            results saved in PostgreSQL ──► GET /api/calls/{id}
```

1. You send a phone number and context (who they are, what the call is about) to `POST /api/calls`.
2. The app saves the contact in the database and asks Twilio to dial the number.
3. When the person answers, Twilio streams the call audio to the app over a WebSocket.
4. Pipecat connects that audio to a real-time voice model (Gemini Live or OpenAI Realtime), which
   holds the conversation by following a system prompt built from your context.
5. The AI ends the call itself when the conversation is over. If an answering machine picks up,
   the call is hung up.
6. After the call, a Gemini text model reads the transcript and extracts structured results
   (outcome, key answers, callback time, summary).
7. You fetch everything with `GET /api/calls/{id}`.

## Tech stack

| Part | Tool | What it does here |
|---|---|---|
| Language | Python 3.12 | |
| Package manager | [uv](https://docs.astral.sh/uv/) | Installs Python 3.12 and the exact dependency versions from `uv.lock` |
| Web framework | FastAPI + Uvicorn | REST API, Twilio webhooks and the audio WebSocket |
| Voice pipeline | [Pipecat](https://github.com/pipecat-ai/pipecat) | Connects Twilio's audio stream to the AI voice model |
| Voice AI | Google Gemini Live (default) or OpenAI Realtime | Speech-to-speech conversation on the call |
| Call analysis | Google Gemini (`google-genai`) | Turns the transcript into structured JSON |
| Telephony | Twilio | Places the call, detects answering machines, records calls |
| Database | PostgreSQL + SQLAlchemy (async) + asyncpg | Stores contacts, calls, transcripts and results |
| Migrations | Alembic | Creates and updates the database tables |
| Validation | Pydantic, pydantic-settings, phonenumbers | Request validation, `.env` config, phone number checks |
| Logging | Loguru | |
| Tests / lint | pytest, pytest-asyncio, httpx, ruff | |
| Deployment | Docker Compose + Caddy | App, Postgres and automatic HTTPS on one server |

## Project structure

```
app/
  main.py              FastAPI app entry point
  config.py            Settings loaded from .env
  api/calls.py         Start a call, read results, Twilio webhooks, audio WebSocket
  api/health.py        GET /health (checks the database)
  db/                  SQLAlchemy models and database session
  telephony/           Twilio client (place call, hang up, verify signatures)
  voice/
    bot.py             Pipecat pipeline that runs one phone call
    engines.py         Picks Gemini Live or OpenAI Realtime
    prompt.py          The agent's script (system prompt)
    analysis.py        Post-call transcript analysis with Gemini
    outcome.py         Saves the call outcome to the database
alembic/               Database migrations
scripts/
  setup_local_db.sql   Creates the local database and user
  test_call.py         Places a test call and prints the result
  sample_call.json     Example phone number + call context
tests/                 pytest tests
```

## Prerequisites

- **Python** (any recent version; uv downloads Python 3.12 for the project automatically)
- **PostgreSQL** running locally
- **Twilio account** with a phone number (Account SID, Auth Token, From number)
- **Google AI API key** ([Google AI Studio](https://aistudio.google.com/apikey)). An OpenAI key is
  only needed if you use `VOICE_ENGINE=openai`.
- **A tunnel** such as [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/)
  or [ngrok](https://ngrok.com/), so Twilio can reach your computer over HTTPS

## Setup

The commands are for Windows PowerShell. On macOS/Linux use `python3` and `cp`, and replace
`.venv\Scripts\` with `.venv/bin/`.

**1. Clone and install the dependencies**

```powershell
git clone <your-repo-url>
cd ai_agent_voice
python -m pip install --user uv
python -m uv sync
```

`uv sync` creates a `.venv` folder with Python 3.12 and every package from `uv.lock`.

**2. Create the database**

```powershell
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -h localhost -f scripts/setup_local_db.sql
```

This creates a `dealer` user (password `dealer`) and a `dealer_ai` database. Change the version
number in the path to match your PostgreSQL install.

**3. Configure your keys**

```powershell
copy .env.example .env
```

Open `.env` and fill in at least:

| Variable | Value |
|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://dealer:dealer@localhost:5432/dealer_ai` |
| `LEAD_API_KEY` | Any secret string; clients send it in the `X-API-Key` header |
| `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER` | From your Twilio console |
| `GOOGLE_API_KEY` | Your Gemini API key |
| `DEALERSHIP_NAME` | The business the agent calls on behalf of |
| `AGENT_NAME` | The name the agent introduces itself with |

Never commit `.env`. It is already in `.gitignore`.

**4. Create the tables**

```powershell
python -m uv run alembic upgrade head
```

**5. Run the app**

```powershell
python -m uv run uvicorn app.main:app --reload --port 8000
```

- Health check: http://localhost:8000/health
- API docs: http://localhost:8000/docs (only when `ENV=dev`)

**6. Run the tests**

```powershell
python -m uv run pytest
```

## Making a test call

Twilio has to reach your app over HTTPS, so you need three terminals:

```powershell
# Terminal 1: open a tunnel and copy the https://....trycloudflare.com URL it prints
cloudflared tunnel --url http://localhost:8000

# Put that URL in .env as PUBLIC_BASE_URL, then:

# Terminal 2: start the app
python -m uv run uvicorn app.main:app --port 8000

# Terminal 3: place the call (use your own number in E.164 format)
python -m uv run python scripts\test_call.py scripts\sample_call.json --phone +1XXXXXXXXXX
```

Your phone rings and the agent runs the script using the details in `scripts/sample_call.json`.
When the call ends, the script prints the transcript and the analysed result.

> On a Twilio trial account you can only call numbers you have verified in the Twilio console.

## API

Every `/api/*` request needs the header `X-API-Key: <LEAD_API_KEY>`.

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/calls` | Start a call. Body: `phone`, `first_name`, optional `last_name` and `customer_message`, plus the call context (in the built-in example, a `vehicle` object; see `scripts/sample_call.json`) |
| `GET` | `/api/calls/{id}` | Call status, transcript, analysis and contact details |
| `GET` | `/health` | App and database health |

`/twilio/*` and `/ws/calls/*` are called by Twilio only and are protected by Twilio signature checks.

## Adapting it to your use case

The calling, audio streaming, voice AI, recording and storage work for any kind of call. What the
agent says and what it extracts afterwards are defined in a few files:

| To change... | Edit |
|---|---|
| What the agent says: its role, goal, call steps and rules | `app/voice/prompt.py` (`build_system_prompt`) |
| What gets extracted after the call (fields and outcome labels) | `app/voice/analysis.py` (`CallAnalysis`, `OutcomeLabel`, `INSTRUCTIONS`) |
| The context you send when starting a call | `app/api/calls.py` (`CallRequest`, `VehicleIn`) |
| How the results are stored | `app/db/models.py`, then create a migration with `python -m uv run alembic revision --autogenerate -m "..."` |
| Business and agent names | `DEALERSHIP_NAME`, `AGENT_NAME` in `.env` |

For example, to turn it into a clinic appointment-reminder agent, rewrite the prompt to confirm or
reschedule an appointment, replace the analysis fields with `confirmed` / `new_time` /
`reason_for_cancelling`, and send appointment details instead of a vehicle in the request.

Keep the `end_call` instruction in the prompt so the agent can hang up by itself.

## Switching the voice engine

Set `VOICE_ENGINE=gemini` or `VOICE_ENGINE=openai` in `.env` and restart. No code changes are
needed. OpenAI requires `OPENAI_API_KEY`. The voice can be changed with `GEMINI_VOICE`.

## Production (Docker)

On a server with Docker and a domain pointing at it:

```bash
cp .env.example .env   # set DOMAIN, POSTGRES_PASSWORD, PUBLIC_BASE_URL=https://<DOMAIN> and API keys
docker compose up -d --build
```

This starts PostgreSQL, the app (it runs the migrations first) and Caddy, which gets an HTTPS
certificate for `DOMAIN` automatically.

## Responsible use

Automated calls are regulated in many countries (for example the TCPA in the US and CASL in
Canada). Only call people who have agreed to be contacted, respect do-not-call requests, and
tell them they are speaking to an AI. The built-in prompt already discloses that it is an AI and
that the call is recorded.

## Current limitations

- One call per request; no automatic retries, SMS, calendar booking or human alerts yet.
- Voicemails are hung up on rather than getting a message left.
- The request format, database tables and analysis fields are still shaped around the built-in
  dealership example; other use cases need the edits listed above.
