"""ReadyNow! — FEMA Emergency Preparedness Agent, packaged for `adk web`.

This module exposes a single `root_agent` that ADK's web/CLI runners discover.
It mirrors the multi-agent coordinator from the capstone notebook: a root agent
that logs + validates input via callbacks and delegates to weather, search,
routes, and safety-Q&A specialists (wrapped as AgentTools).

Run from the parent directory (the one that CONTAINS this package folder):

    adk web --allow_origins="regex:.*" .

or target this agent explicitly:

    adk web --allow_origins="regex:.*" readynow_agent

Then open the Web Preview (Cloud Shell) on the served port (default 8000).
"""

import os
import re
import datetime
from typing import Any, Optional

import requests

# --- Vertex AI / ADC config (no API keys) --------------------------------
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")
# GOOGLE_CLOUD_PROJECT / GOOGLE_CLOUD_LOCATION are picked up from the
# environment / ADC in Cloud Shell. Set them before launching if needed:
#   export GOOGLE_CLOUD_PROJECT=$(gcloud config get-value project)
#   export GOOGLE_CLOUD_LOCATION=us-central1


# =========================================================================
# Tools (keyless: Open-Meteo geocoding, NWS weather/alerts, OSRM/Maps routes)
# =========================================================================
def geocode_location(place_name: str) -> dict[str, Any]:
    """Convert a US place name into coordinates via Open-Meteo (keyless).

    Args:
        place_name: e.g. "Miami, FL".

    Returns:
        dict with status and latitude/longitude/resolved_name, or error_message.
    """
    name_part = place_name.split(",")[0].strip()
    try:
        r = requests.get("https://geocoding-api.open-meteo.com/v1/search",
                         params={"name": name_part, "count": 5, "country": "US"},
                         timeout=10)
        r.raise_for_status()
        results = r.json().get("results")
    except requests.RequestException as exc:
        return {"status": "error", "error_message": f"Geocoding failed: {exc}"}
    if not results:
        return {"status": "error", "error_message": f"No match for '{place_name}'."}
    state = place_name.split(",")[1].strip() if "," in place_name else None
    chosen = results[0]
    if state:
        for c in results:
            a1 = c.get("admin1", "")
            if state.lower() in a1.lower() or a1.lower().startswith(state.lower()):
                chosen = c
                break
    return {"status": "success", "latitude": chosen["latitude"],
            "longitude": chosen["longitude"],
            "resolved_name": f"{chosen.get('name')}, {chosen.get('admin1','')}".strip(", ")}


def get_weather_forecast(latitude: float, longitude: float) -> dict[str, Any]:
    """Current US forecast for coordinates via the NWS API (keyless).

    Args:
        latitude: Latitude in decimal degrees.
        longitude: Longitude in decimal degrees.

    Returns:
        dict with status and forecast fields, or error_message.
    """
    h = {"User-Agent": "ReadyNow-FEMA (poc)", "Accept": "application/geo+json"}
    try:
        pd = requests.get(f"https://api.weather.gov/points/{latitude},{longitude}",
                          headers=h, timeout=10).json()
        furl = pd.get("properties", {}).get("forecast")
        rel = pd.get("properties", {}).get("relativeLocation", {}).get("properties", {})
        loc = f"{rel.get('city','Unknown')}, {rel.get('state','')}".strip(", ")
        if not furl:
            return {"status": "error", "error_message": "No NWS forecast (US only)."}
        cur = requests.get(furl, headers=h, timeout=10).json()["properties"]["periods"][0]
    except (requests.RequestException, KeyError, IndexError) as exc:
        return {"status": "error", "error_message": f"NWS forecast failed: {exc}"}
    return {"status": "success", "location": loc,
            "short_forecast": cur.get("shortForecast", ""),
            "temperature": cur.get("temperature"),
            "temperature_unit": cur.get("temperatureUnit", "F"),
            "wind_speed": cur.get("windSpeed", ""),
            "detailed_forecast": cur.get("detailedForecast", "")}


def get_weather_alerts(latitude: float, longitude: float) -> dict[str, Any]:
    """Active NWS alerts/warnings for a US point (keyless).

    Args:
        latitude: Latitude in decimal degrees.
        longitude: Longitude in decimal degrees.

    Returns:
        dict with status, alert_count, and a list of alerts, or error_message.
    """
    h = {"User-Agent": "ReadyNow-FEMA (poc)", "Accept": "application/geo+json"}
    try:
        data = requests.get(
            f"https://api.weather.gov/alerts/active?point={latitude},{longitude}",
            headers=h, timeout=10).json()
    except requests.RequestException as exc:
        return {"status": "error", "error_message": f"NWS alerts failed: {exc}"}
    alerts = [{"event": p.get("properties", {}).get("event", ""),
               "severity": p.get("properties", {}).get("severity", ""),
               "headline": p.get("properties", {}).get("headline", "")}
              for p in data.get("features", [])]
    return {"status": "success", "alert_count": len(alerts), "alerts": alerts}


def get_route_to_safety(start_place: str, destination_place: str) -> dict[str, Any]:
    """Driving route between two US places (Google Maps if key set, else OSRM).

    Args:
        start_place: Start location, e.g. "Miami, FL".
        destination_place: Destination, e.g. "Orlando, FL".

    Returns:
        dict with status, provider, distance, duration, summary, or error_message.
    """
    s, d = geocode_location(start_place), geocode_location(destination_place)
    if s["status"] != "success":
        return {"status": "error", "error_message": f"Can't locate start: {start_place}"}
    if d["status"] != "success":
        return {"status": "error", "error_message": f"Can't locate dest: {destination_place}"}
    key = os.environ.get("GOOGLE_MAPS_API_KEY", "")
    if key:
        try:
            r = requests.get("https://maps.googleapis.com/maps/api/directions/json",
                params={"origin": f"{s['latitude']},{s['longitude']}",
                        "destination": f"{d['latitude']},{d['longitude']}", "key": key},
                timeout=15).json()
            if r.get("status") == "OK" and r.get("routes"):
                leg = r["routes"][0]["legs"][0]
                return {"status": "success", "provider": "google_maps",
                        "distance": leg["distance"]["text"], "duration": leg["duration"]["text"],
                        "summary": f"Drive {s['resolved_name']} to {d['resolved_name']}: "
                                   f"{leg['distance']['text']}, ~{leg['duration']['text']}."}
        except requests.RequestException:
            pass
    coords = f"{s['longitude']},{s['latitude']};{d['longitude']},{d['latitude']}"
    try:
        r = requests.get(
            f"https://router.project-osrm.org/route/v1/driving/{coords}?overview=false",
            timeout=15).json()
    except requests.RequestException as exc:
        return {"status": "error", "error_message": f"Routing failed: {exc}"}
    if r.get("code") != "Ok" or not r.get("routes"):
        return {"status": "error", "error_message": "No route found."}
    rt = r["routes"][0]
    mi, mn = rt["distance"] / 1609.34, rt["duration"] / 60
    return {"status": "success", "provider": "osrm",
            "distance": f"{mi:.1f} mi", "duration": f"{mn:.0f} min",
            "summary": f"Drive {s['resolved_name']} to {d['resolved_name']}: "
                       f"~{mi:.1f} miles, ~{mn:.0f} minutes."}


# =========================================================================
# Callbacks: log every interaction; validate + scope input
# =========================================================================
from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmRequest, LlmResponse
from google.genai import types as genai_types

INTERACTION_LOG: list[dict] = []

_MALICIOUS = [r"ignore (all |your |previous )?(instructions|prompts)",
              r"disregard (the |all |your )?(above|previous|prior|system)",
              r"reveal (your )?(system prompt|instructions)", r"you are now",
              r"pretend to be", r"jailbreak", r"do anything now",
              r"</?(script|system)>", r"drop table", r"rm -rf"]

# Clearly off-mission signals. We BLOCK only when one of these appears, rather
# than requiring a mission keyword to pass — that avoids over-blocking short,
# valid follow-ups like a bare location ("Miami, FL") in a multi-turn chat.
_OFF_MISSION_TERMS = [
    "poem", "poetry", "haiku", "song", "lyrics", "joke", "riddle", "story",
    "essay", "recipe", "cook", "bake", "movie", "sports score", "stock price",
    "cryptocurrency", "bitcoin", "dating", "horoscope", "write code", "python script",
    "homework", "translate this", "math problem",
]


def _latest_user_text(req: LlmRequest) -> str:
    if req.contents:
        for content in reversed(req.contents):
            if content.role == "user" and content.parts:
                for part in content.parts:
                    if getattr(part, "text", None):
                        return part.text
    return ""


def _blocked(reason: str) -> LlmResponse:
    msg = (f"ReadyNow! can't help with that: {reason} I'm an emergency-preparedness "
           "assistant — I can help with weather, hazards, evacuation routes, and "
           "safety information for US locations.")
    return LlmResponse(content=genai_types.Content(
        role="model", parts=[genai_types.Part(text=msg)]))


def before_model_callback(
    callback_context: CallbackContext, llm_request: LlmRequest
) -> Optional[LlmResponse]:
    """Log the prompt, block unsafe input, refuse off-mission requests."""
    name = callback_context.agent_name
    text = _latest_user_text(llm_request)
    ts = datetime.datetime.now().isoformat(timespec="seconds")
    INTERACTION_LOG.append({"time": ts, "type": "prompt", "agent": name, "text": text})
    print(f"[LOG {ts}] PROMPT to {name!r}: {text!r}")
    low = text.lower()
    for pat in _MALICIOUS:
        if re.search(pat, low):
            print(f"[VALIDATION] blocked (malicious): {pat!r}")
            return _blocked("that request looked unsafe.")
    if name == "readynow_root" and text.strip():
        if any(t in low for t in _OFF_MISSION_TERMS):
            print("[VALIDATION] blocked (off-mission).")
            return _blocked("it doesn't appear related to emergencies or safety.")
    print(f"[VALIDATION] passed for {name!r}.")
    return None


def after_model_callback(
    callback_context: CallbackContext, llm_response: LlmResponse
) -> Optional[LlmResponse]:
    """Log the model response."""
    name = callback_context.agent_name
    text = ""
    if llm_response and llm_response.content and llm_response.content.parts:
        for part in llm_response.content.parts:
            if getattr(part, "text", None):
                text += part.text
    ts = datetime.datetime.now().isoformat(timespec="seconds")
    INTERACTION_LOG.append({"time": ts, "type": "response", "agent": name, "text": text})
    if text:
        print(f"[LOG {ts}] RESPONSE from {name!r}: {text[:120]!r}")
    return None


# =========================================================================
# Agents
# =========================================================================
from google.adk.agents import Agent
from google.adk.tools import google_search
from google.adk.tools.agent_tool import AgentTool

weather_agent = Agent(
    name="weather_agent", model="gemini-2.5-flash",
    description="US weather forecasts and active hazard alerts for a location.",
    instruction="Report weather and hazards for US locations. Call geocode_location, "
                "then get_weather_forecast and get_weather_alerts. Lead with any alert.",
    tools=[geocode_location, get_weather_forecast, get_weather_alerts],
)

search_agent = Agent(
    name="search_agent", model="gemini-2.5-flash",
    description="Searches the web for current news and disaster information.",
    instruction="Find current, credible emergency/weather/safety info with Google "
                "Search. Answer concisely and mention sources.",
    tools=[google_search],
)

routes_agent = Agent(
    name="routes_agent", model="gemini-2.5-flash",
    description="Provides driving/evacuation routes to safety.",
    instruction="Provide evacuation routing. Call get_route_to_safety with the user's "
                "start and a safer destination, then explain distance/time calmly.",
    tools=[get_route_to_safety],
)

safety_qa_agent = Agent(
    name="safety_qa_agent", model="gemini-2.5-flash",
    description="Answers general emergency-preparedness and safety questions.",
    instruction="Answer preparedness/safety questions in clear, calm, plain language.",
)

root_agent = Agent(
    name="readynow_root", model="gemini-2.5-flash",
    description="ReadyNow! emergency-preparedness coordinator.",
    instruction=(
        "You are ReadyNow!, a FEMA emergency-preparedness assistant. You help during "
        "disasters with weather and hazard alerts, news, evacuation routes, and safety "
        "guidance. Reassure the user, then use the right tool: weather_agent for "
        "weather/alerts, search_agent for news, routes_agent for evacuation routes, "
        "safety_qa_agent for preparedness questions. If asked what you can do, describe "
        "these. Stay strictly on the emergency-preparedness mission; politely decline "
        "unrelated requests. Keep answers clear, calm, and easy to understand."
    ),
    tools=[AgentTool(agent=weather_agent), AgentTool(agent=search_agent),
           AgentTool(agent=routes_agent), AgentTool(agent=safety_qa_agent)],
    before_model_callback=before_model_callback,
    after_model_callback=after_model_callback,
)
