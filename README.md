# ADK Weather Agent — Challenge Labs 1–5

Google Agent Development Kit (ADK) challenge labs, built and run in **Vertex AI
Colab Enterprise (Agent Platform)**. Each notebook builds on the previous one, ending
with a weather agent deployed to and tested on Vertex AI Agent Engine.

All agents authenticate through **Application Default Credentials (ADC)** — there are
**no API keys** anywhere in these notebooks. Geocoding and weather data come from
keyless public APIs.

## Notebooks

| File | Challenge | What it demonstrates |
|------|-----------|----------------------|
| `adk_weather_agent_challenge1.ipynb` | 1 — Custom tools | An ADK agent with two custom tools (geocoding + National Weather Service forecast), tested across multiple US cities, on both a Gemini and a third-party (Claude Sonnet 5) model. |
| `adk_weather_agent_challenge2.ipynb` | 2 — Callbacks | Adds `before_model_callback` (logs prompts, validates input) and `after_model_callback` (logs responses). Validation blocks non-US locations and obvious prompt-injection input. |
| `adk_weather_agent_challenge3.ipynb` | 3 — Multi-agent | A root/coordinator agent delegating to a weather agent and a search agent (built-in Google Search), with event output showing each delegation. |
| `adk_weather_agent_challenge4.ipynb` | 4 — Agent workflow | A `SequentialAgent` answer team (Search → Critique → Refine) behind a Greeter root, verifying and refining answers before returning them. |
| `adk_weather_agent_challenge5.ipynb` | 5 — Deployment | A self-contained Gemini weather agent deployed to Vertex AI Agent Engine (`agent_engines.create`) and tested on its remote cloud endpoint. |

## Architecture at a glance

- **Tools** — `geocode_location` (place → latitude/longitude) and
  `get_weather_forecast` (coordinates → NWS forecast), both keyless.
- **Models** — Gemini 2.5 Flash as the primary model; **Claude Sonnet 5** on Vertex
  AI Model Garden (via LiteLLM, ADC-authenticated, global endpoint) as the
  third-party model in Challenges 1–3.
- **Callbacks** (Ch. 2) — prompt/response logging and pre-model input validation.
- **Multi-agent** (Ch. 3) — coordinator delegates via `AgentTool`.
- **Workflow** (Ch. 4) — `SequentialAgent` chains Search → Critique → Refine using
  `output_key` / `{key}` session-state hand-off.
- **Deployment** (Ch. 5) — `AdkApp` + `agent_engines.create`, tested via
  `stream_query` against the deployed engine.

## Running

Open each notebook in **Colab Enterprise**, connect a runtime attached to a Vertex
AI–enabled project, and run cells top to bottom. Notebooks depend on cells above
them, so always run from the first cell — running a later cell alone will raise
`NameError` for imports it hasn't loaded yet.

Challenge 5 additionally requires a GCS staging bucket (the notebook creates one) and
the Reasoning Engine Service Agent to hold the *Vertex AI User* role; deployment takes
several minutes. Delete the deployed engine when finished
(`remote_agent.delete(force=True)`) to avoid ongoing cost.

## Notes on environment-driven deviations

These labs were completed in a permission-limited Qwiklabs sandbox. Two lab
instructions could not be followed literally because the environment withheld the
required access; each notebook documents the deviation and includes the
lab-specified approach (commented) for any project without the restriction.

1. **Geocoding provider.** The lab names the *Google Maps Geocoding API*, which
   requires an API key. The sandbox did not have the Geocoding API enabled by default
   and did not permit creating a Maps API key (`gcloud services api-keys create`
   returned `PERMISSION_DENIED`). The notebooks use **Open-Meteo's keyless geocoder**
   instead, which returns the same coordinates; the Google Maps implementation is
   included, commented out, as a drop-in replacement.

2. **Search agent model.** ADK's built-in Google Search tool is Gemini-only, so the
   search agent (Ch. 3) and the answer team's search step (Ch. 4) run on Gemini rather
   than the Claude third-party model.

Claude Sonnet 5 *was* successfully enabled in Vertex AI Model Garden and is used as
the third-party weather model in Challenges 1–3. For deployment (Ch. 5), a single
Gemini agent is used because Agent Engine's serialized runtime does not reliably
resolve Vertex partner models.
