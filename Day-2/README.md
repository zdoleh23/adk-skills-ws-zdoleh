# Day 2 — ReadyNow! FEMA Emergency Preparedness Agent (Capstone)

A multi-agent emergency-preparedness assistant built on the Google Agent Development
Kit (ADK), combining every technique from the Day 1 challenges into one system and
deploying it to Vertex AI Agent Engine.

## Files

- `readynow_fema_agent.ipynb` — the full case-study notebook (build, local test, deploy, cloud test).
- `readynow_architecture.svg` — the system architecture diagram.

## What it does (FEMA requirements → implementation)

| FEMA capability | Implementation |
|---|---|
| Real-time weather & alerts | Weather agent: Open-Meteo geocoding + National Weather Service forecast and active-alerts tools |
| News / general search | Search agent: ADK built-in Google Search tool |
| Routes to safety | Routes agent: Google Maps Directions API, with keyless OSRM fallback |
| Answer questions / safety info | Safety Q&A agent |
| Coordinate tasks & sub-agents | Root coordinator agent (delegates via `AgentTool`) |
| Validate + refine responses | `SequentialAgent`: Validate → Refine |
| Log all interactions | `before_model_callback` / `after_model_callback` → `INTERACTION_LOG` |
| Validate & scope user input | `before_model_callback`: blocks unsafe input, refuses off-mission requests |
| Deploy to Agent Platform | `AdkApp` + `agent_engines.create` on Vertex AI Agent Engine |
| Test working deployment | Remote `stream_query` against the deployed endpoint |

## Architecture

The user talks only to the **Root Coordinator**, which logs and validates every turn
via callbacks and delegates to four specialists (Weather, Search, Routes, Safety
Q&A) plus a Validate → Refine sequential workflow. See `readynow_architecture.svg`.

## Running

Open in Colab Enterprise on a Vertex AI-enabled project and run top to bottom.
Sections: setup (1-2), tools (3), callbacks (4), specialists (5), workflow (6), root
(7), local test with event streaming (8), interaction log (9), deploy (10),
cloud test (11), cleanup (12), notes (13).

## Design decisions / environment notes

- **No API keys hardcoded** — models use ADC; weather, geocoding, and the fallback
  router are keyless. Google Maps routing reads `GOOGLE_MAPS_API_KEY` if set.
- **Routing** prefers the Google Maps Directions API (the case-study requirement) and
  falls back to keyless OSRM so the notebook always runs — the Day 1 sandbox blocked
  Maps API-key creation, and OSRM keeps routing functional regardless.
- **Search is Gemini-only** (ADK built-in tool constraint), so all agents run on Gemini.
- **Deployment** uses a self-contained single Gemini agent (weather + alerts +
  routes), because Agent Engine's serialized runtime does not reliably handle partner
  models or complex multi-agent tool graphs. The full multi-agent system is the local
  solution; the deployed agent is its serializable core.
- Delete the deployed engine when finished (`remote_agent.delete(force=True)`).

## Screenshots

Demonstration screenshots of ReadyNow! running (captured from Colab Enterprise after
a top-to-bottom run). Images live in `Day-2/screenshots/`.

### 1. Architecture diagram
![Architecture](./readynow_architecture.svg)

### 2. Tools sanity check (section 3)
Confirms the shared data tools work: geocoding (Open-Meteo), active weather alerts
(NWS), and routing (OSRM fallback) all return valid results for Miami, FL.

![Tools sanity check](./screenshots/00_tools_sanity.png)

### 3. Local multi-agent run — root delegating to sub-agents
Section 8 runs six scenarios through the root coordinator. Because the full output is
long, it is captured across several screenshots — each shows the `[EVENT]`
delegation lines (root calling a specialist), plus `[LOG]` and `[VALIDATION]` lines.

**3a. Weather scenario** — root delegates to `weather_agent` (geocode + NWS + alerts).

![Weather delegation](./screenshots/01a_weather.png)

**3b. Route scenario** — root delegates to `routes_agent` (evacuation route).

![Route delegation](./screenshots/01b_route.png)

**3c. News scenario** — root delegates to `search_agent` (built-in Google Search).

![Search delegation](./screenshots/01c_search.png)

**3d. Preparedness scenario** — root delegates to `safety_qa_agent`.

![Safety Q&A delegation](./screenshots/01d_safety.png)

### 4. Input validation
Shows off-mission and malicious requests being refused by `before_model_callback`
(`[VALIDATION] blocked (off-mission)` and `[VALIDATION] blocked (malicious)`),
section 8.

![Validation](./screenshots/02_validation_logging.png)

### 4b. Interaction log
The `INTERACTION_LOG` captured by the callbacks — every prompt and response, with
timestamps (section 9). Evidence that all user-agent interactions are logged.

![Interaction log](./screenshots/02b_interaction_log.png)

### 5. Successful deployment to Agent Platform
Shows `agent_engines.create(...)` completing with a `reasoningEngines/...` resource
name (section 10).

![Deployment](./screenshots/03_deployment.png)

### 6. Cloud test — deployed agent responding
Shows `stream_query` results from the deployed endpoint answering a weather/alert
query and an evacuation-route query (section 11).

![Cloud test](./screenshots/04_cloud_test.png)

### 7. Cleanup cell (best practice)
Section 12 provides a cleanup cell to delete the deployed Agent Engine when finished,
avoiding ongoing cost. (Left commented so the deployment persists for grading; run it
after grading to tear the engine down.)

![Cleanup cell](./screenshots/05_cleanup.png)

### 8. Live `adk web` UI demo
The ReadyNow! coordinator running in ADK's web chat UI (launched with `adk web` in
Cloud Shell — see `readynow_web/RUN_ADK_WEB.md`). Shows the agent tree
(root → weather / search / routes / safety), a safety answer, and both validation
guardrails firing: an off-mission request ("write me a poem") and a malicious request
("ignore all previous instructions") are refused.

![adk web UI demo](./screenshots/06_adk_web_demo.png)
