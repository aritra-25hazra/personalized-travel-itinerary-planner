"""
Personalized Travel Itinerary Planner
Skill Wallet Capstone Project 4 - Generative AI | Intelligent SaaS Trip Planning

Single-file Streamlit application.
- Epic 3: Preference capture + smart destination recommender
- Epic 4: Day-wise itinerary with geographic clustering + budget tracker + dynamic day swap
- Epic 5: SQLite trip persistence + offline PDF export (ReportLab)

Works with Gemini or Groq (bring your own key) and has a fully offline Demo mode,
so it deploys to Streamlit Community Cloud with zero external dependencies.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import random
import re
import sqlite3
from collections import Counter
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd
import requests
import streamlit as st
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

# =============================================================================
# Constants & configuration
# =============================================================================

APP_NAME = "Personalized Travel Itinerary Planner"
DB_PATH = "trips.db"

VIBES = ["Beach", "Mountains", "Cultural", "Urban"]
BUDGET_LEVELS = ["Budget", "Moderate", "Luxury"]
PARTIES = ["Solo", "Couple", "Family", "Friends"]
PACES = ["Relaxed", "Moderate", "Fast-Paced"]
INTERESTS = ["Food", "Adventure", "History", "Nightlife", "Nature", "Shopping", "Art & Museums", "Wellness"]
SLOTS = ["Morning Sightseeing", "Lunch Recommendation", "Afternoon Leisure", "Evening Dining & Entertainment"]

# Approximate conversion table (static, so the app has zero external API dependencies).
INR_PER_USD = 84.0
USD_PER_UNIT = {
    "USD": 1.0, "INR": 1 / INR_PER_USD, "EUR": 1.08, "GBP": 1.27, "JPY": 0.0067, "AED": 0.272,
    "SGD": 0.74, "THB": 0.029, "IDR": 0.000063, "CHF": 1.12, "TRY": 0.029, "AUD": 0.65,
    "CAD": 0.73, "MYR": 0.22, "VND": 0.00004, "LKR": 0.0033, "NPR": 0.0075, "MVR": 0.065,
    "KRW": 0.00072, "CNY": 0.14, "HKD": 0.128, "EGP": 0.02, "ZAR": 0.055, "MXN": 0.055,
    "BRL": 0.18, "NZD": 0.60, "SEK": 0.095, "NOK": 0.093, "DKK": 0.145, "CZK": 0.043,
    "PLN": 0.25, "HUF": 0.0027, "QAR": 0.275, "SAR": 0.267, "OMR": 2.6, "BHD": 2.65, "KES": 0.0077,
    "MAD": 0.10, "PHP": 0.0175, "TWD": 0.031, "ILS": 0.27, "ARS": 0.001, "CLP": 0.0011, "PEN": 0.27,
    "COP": 0.00024, "ISK": 0.0072, "BTN": 0.012, "FJD": 0.44, "MUR": 0.022, "SCR": 0.072,
}
CURRENCY_SYMBOLS = {
    "USD": "$", "INR": "₹", "EUR": "€", "GBP": "£", "JPY": "¥", "AED": "AED ", "SGD": "S$", "THB": "฿",
    "IDR": "Rp", "CHF": "CHF ", "TRY": "₺", "AUD": "A$", "CAD": "C$", "MYR": "RM", "VND": "₫",
    "LKR": "Rs ", "NPR": "Rs ", "KRW": "₩", "CNY": "¥", "HKD": "HK$", "EGP": "E£", "ZAR": "R",
    "MXN": "MX$", "BRL": "R$", "NZD": "NZ$", "PHP": "₱", "QAR": "QR ", "SAR": "SR ",
}
# Target daily spend per person by budget tier (USD) - used for the budget health meter.
DAILY_BUDGET_USD = {"Budget": 60, "Moderate": 150, "Luxury": 400}

GEMINI_MODELS = ["gemini-flash-latest", "gemini-3.6-flash", "gemini-2.5-flash", "gemini-flash-lite-latest"]
GROQ_MODELS = ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "llama-3.3-70b-versatile", "llama-3.1-8b-instant"]

QUICK_SWAPS = [  # (short button label, full instruction sent to the planner)
    ("Museum → market", "Swap the museum or indoor activity for an outdoor market"),
    ("Vegetarian lunch", "Find a vegetarian lunch spot"),
    ("More relaxed", "Make this day more relaxed with fewer, longer activities"),
    ("Add nightlife", "Add a nightlife option in the evening"),
    ("Cut costs", "Cut costs for this day - cheaper or free alternatives"),
    ("Add adventure", "Add an adventure activity in the afternoon"),
]

EMERGENCY_DEFAULTS = {
    "India": {"police": "100 / 112", "ambulance": "102 / 108", "fire": "101", "tourist_helpline": "1363 (24x7, multilingual)"},
    "Indonesia": {"police": "110", "ambulance": "118 / 119", "fire": "113", "tourist_helpline": "Bali Tourist Police +62 361 754 599"},
    "France": {"police": "17 / 112", "ambulance": "15 / 112", "fire": "18", "tourist_helpline": "112 (EU emergency)"},
    "Japan": {"police": "110", "ambulance": "119", "fire": "119", "tourist_helpline": "Japan Visitor Hotline 050-3816-2787"},
    "United Arab Emirates": {"police": "999", "ambulance": "998", "fire": "997", "tourist_helpline": "Dubai Tourist Police 800-4438"},
    "Thailand": {"police": "191", "ambulance": "1669", "fire": "199", "tourist_helpline": "Tourist Police 1155"},
    "Singapore": {"police": "999", "ambulance": "995", "fire": "995", "tourist_helpline": "1800-736-2000"},
    "Switzerland": {"police": "117 / 112", "ambulance": "144", "fire": "118", "tourist_helpline": "112"},
    "Portugal": {"police": "112", "ambulance": "112", "fire": "112", "tourist_helpline": "SOS Tourist +351 808 781 212"},
    "Turkey": {"police": "155 / 112", "ambulance": "112", "fire": "110", "tourist_helpline": "Tourist Police +90 212 527 4503"},
}
EMERGENCY_GENERIC = {"police": "112 (international) / local number", "ambulance": "112 / local number",
                     "fire": "112 / local number", "tourist_helpline": "Ask your hotel reception"}

PACKING_BY_VIBE = {
    "Beach": ["Sunscreen SPF 50+", "Swimwear & quick-dry towel", "Flip-flops / water shoes", "Sunglasses & hat", "Waterproof phone pouch"],
    "Mountains": ["Layered warm clothing", "Trekking shoes", "Rain jacket", "Power bank", "Motion-sickness tablets"],
    "Cultural": ["Modest clothing for temples/churches", "Comfortable walking shoes", "Scarf / shawl", "Small day-pack", "Printed hotel address in local language"],
    "Urban": ["Comfortable sneakers", "Metro card / transit app", "Universal travel adapter", "Compact umbrella", "Reusable water bottle"],
}

# =============================================================================
# Small helpers
# =============================================================================


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        if isinstance(value, str):
            value = re.sub(r"[^\d.\-]", "", value)
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_coord(value: Any):
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def fmt_money(amount: float, currency: str) -> str:
    sym = CURRENCY_SYMBOLS.get(currency, f"{currency} ")
    if currency in ("IDR", "VND", "KRW", "JPY", "INR", "LKR", "NPR", "HUF", "CLP", "COP", "ARS"):
        return f"{sym}{amount:,.0f}"
    return f"{sym}{amount:,.2f}"


def to_usd(amount: float, currency: str) -> float:
    return amount * USD_PER_UNIT.get(currency, 1.0)


def to_inr(amount: float, currency: str) -> float:
    return to_usd(amount, currency) * INR_PER_USD


def haversine_km(lat1, lng1, lat2, lng2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def extract_json(text: str) -> Any:
    """Robustly pull a JSON object/array out of an LLM response."""
    if not text or not text.strip():
        raise ValueError("The model returned an empty response.")
    t = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", t, re.S)
    if fence:
        t = fence.group(1).strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    starts = [i for i in (t.find("{"), t.find("[")) if i != -1]
    if not starts:
        raise ValueError("No JSON found in the model response.")
    s = min(starts)
    closer = "}" if t[s] == "{" else "]"
    e = t.rfind(closer)
    if e <= s:
        raise ValueError("Malformed JSON in the model response.")
    return json.loads(t[s:e + 1])


def prefs_seed(prefs: dict) -> int:
    """Stable seed across processes (Python's hash() is salted per run)."""
    digest = hashlib.md5(json.dumps(prefs, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


# =============================================================================
# LLM layer (Gemini / Groq via REST - no SDK pinning headaches)
# =============================================================================


class LLMError(Exception):
    pass


def call_gemini(api_key: str, model: str, prompt: str, temperature: float = 0.7, json_mode: bool = True) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}
    gen_cfg: dict[str, Any] = {"temperature": temperature, "maxOutputTokens": 24576}
    if json_mode:
        gen_cfg["responseMimeType"] = "application/json"
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}], "generationConfig": gen_cfg}
    try:
        resp = requests.post(url, headers=headers, json=body, timeout=120)
    except requests.RequestException as exc:
        raise LLMError(f"Network error while calling Gemini: {exc}") from exc
    if resp.status_code != 200:
        raise LLMError(f"Gemini API error {resp.status_code}: {resp.text[:400]}")
    data = resp.json()
    try:
        parts = data["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts)
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError(f"Unexpected Gemini response shape: {json.dumps(data)[:400]}") from exc


def call_groq(api_key: str, model: str, prompt: str, temperature: float = 0.7, json_mode: bool = True) -> str:
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    body: dict[str, Any] = {
        "model": model,
        "temperature": temperature,
        "max_tokens": 16384,
        "messages": [
            {"role": "system", "content": "You are a senior travel planner. Always respond with valid JSON only."},
            {"role": "user", "content": prompt},
        ],
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    try:
        resp = requests.post(url, headers=headers, json=body, timeout=120)
    except requests.RequestException as exc:
        raise LLMError(f"Network error while calling Groq: {exc}") from exc
    if resp.status_code != 200:
        raise LLMError(f"Groq API error {resp.status_code}: {resp.text[:400]}")
    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError(f"Unexpected Groq response shape: {json.dumps(data)[:400]}") from exc


def call_llm(prompt: str, temperature: float = 0.7, json_mode: bool = True) -> str:
    provider = st.session_state.get("provider", "Demo")
    api_key = st.session_state.get("api_key", "")
    model = st.session_state.get("model", "")
    if provider == "Gemini":
        return call_gemini(api_key, model, prompt, temperature, json_mode)
    if provider == "Groq":
        return call_groq(api_key, model, prompt, temperature, json_mode)
    raise LLMError("No live provider configured. Switch Demo mode off and add an API key.")


def is_demo() -> bool:
    return st.session_state.get("provider", "Demo") == "Demo" or not st.session_state.get("api_key")


# =============================================================================
# Prompt templates
# =============================================================================

ITINERARY_SCHEMA = """{
  "destination": "City",
  "country": "Country",
  "currency_code": "ISO 4217 code of the LOCAL currency, e.g. INR, EUR, JPY",
  "overview": "2-3 sentence summary of the trip personality",
  "days": [
    {
      "day": 1,
      "theme": "short theme for the day",
      "area": "the ONE neighbourhood / district this day stays in",
      "activities": [
        {"slot": "Morning Sightseeing", "name": "...", "area": "neighbourhood", "description": "1-2 sentences",
         "duration_hours": 2.5, "cost_local": 0, "category": "Sightseeing", "lat": 0.0, "lng": 0.0},
        {"slot": "Lunch Recommendation", "name": "restaurant / dish", "area": "...", "description": "...",
         "duration_hours": 1, "cost_local": 0, "category": "Food", "lat": 0.0, "lng": 0.0},
        {"slot": "Afternoon Leisure", "name": "...", "area": "...", "description": "...",
         "duration_hours": 3, "cost_local": 0, "category": "Leisure", "lat": 0.0, "lng": 0.0},
        {"slot": "Evening Dining & Entertainment", "name": "...", "area": "...", "description": "...",
         "duration_hours": 3, "cost_local": 0, "category": "Dining", "lat": 0.0, "lng": 0.0}
      ]
    }
  ],
  "emergency": {"police": "...", "ambulance": "...", "fire": "...", "tourist_helpline": "...",
                "embassy_note": "where Indian travellers can find their embassy/consulate"},
  "packing": ["item", "item"],
  "tips": ["local tip", "local tip"]
}"""

DAY_SCHEMA = """{
  "day": N,
  "theme": "...",
  "area": "...",
  "activities": [ four activities with slots in order: Morning Sightseeing, Lunch Recommendation,
                  Afternoon Leisure, Evening Dining & Entertainment - same fields as before
                  (slot, name, area, description, duration_hours, cost_local, category, lat, lng) ]
}"""


def prefs_summary(prefs: dict) -> str:
    return (
        f"Destination: {prefs.get('destination') or 'not fixed (open to suggestions)'}\n"
        f"Vibe: {prefs['vibe']}\nDuration: {prefs['days']} days starting {prefs['start_date']}\n"
        f"Budget level: {prefs['budget']} (~{DAILY_BUDGET_USD[prefs['budget']]} USD per person per day all-in)\n"
        f"Travel party: {prefs['party']}\nPace: {prefs['pace']}\n"
        f"Interests: {', '.join(prefs['interests']) or 'general'}\n"
        f"Travellers are from India (home currency INR)."
    )


def recommendation_prompt(prefs: dict) -> str:
    month = datetime.fromisoformat(prefs["start_date"]).strftime("%B")
    return f"""You are a senior travel consultant. The traveller has NOT fixed a destination.

Traveller profile:
{prefs_summary(prefs)}
Travel month: {month}

Recommend the TOP 3 destination cities worldwide (or in India if budget-friendly fits best) that best match the
vibe "{prefs['vibe']}", the budget level, the weather/season in {month}, and the interests.
Rank them by match quality. Give realistic, specific highlights.

Return ONLY valid JSON:
{{
  "recommendations": [
    {{"city": "...", "country": "...", "match_score": 92, "why": "2 sentences on why it matches",
      "weather_in_month": "short note", "best_season": "e.g. Nov-Feb",
      "estimated_daily_cost_usd": 80, "currency_code": "ISO code",
      "highlights": ["place 1", "place 2", "place 3", "place 4"],
      "tags": ["Beaches", "Nightlife", "Seafood"]}}
  ]
}}"""


def itinerary_prompt(prefs: dict) -> str:
    return f"""You are a senior travel planner building a production-quality itinerary.

Traveller profile:
{prefs_summary(prefs)}

STRICT RULES
1. Exactly {prefs['days']} days. Each day has exactly 4 activities, slots in this order:
   "Morning Sightseeing", "Lunch Recommendation", "Afternoon Leisure", "Evening Dining & Entertainment".
2. GEOGRAPHIC CLUSTERING: every day stays inside ONE neighbourhood/district. Group attractions that are close to
   each other on the same day. Never backtrack across the city, and never hop between cities on the same day.
   Set "area" on the day and on each activity to that neighbourhood.
3. Every activity needs: realistic cost in the LOCAL currency (0 if free), approximate latitude/longitude,
   duration in hours, a category (Sightseeing / Food / Leisure / Dining / Adventure / Shopping / Nature / Nightlife).
4. Keep daily spend near {DAILY_BUDGET_USD[prefs['budget']]} USD per person; match the "{prefs['pace']}" pace
   (Relaxed = fewer, longer activities; Fast-Paced = packed days).
5. Respect the interests and travel party ({prefs['party']}) when choosing food and evening options.
6. Fill emergency numbers for the destination country, a packing list for the vibe, and 4-5 local tips.

Return ONLY valid JSON matching this schema exactly:
{ITINERARY_SCHEMA}"""


def regenerate_day_prompt(prefs: dict, plan: dict, day_idx: int, instruction: str) -> str:
    day = plan["days"][day_idx]
    used = [a["name"] for i, d in enumerate(plan["days"]) if i != day_idx for a in d["activities"]]
    return f"""You are editing ONE day of an existing {len(plan['days'])}-day itinerary for {plan['destination']}, {plan['country']}.
Local currency: {plan['currency_code']}.

Traveller profile:
{prefs_summary(prefs)}

Current Day {day['day']} (area: {day['area']}):
{json.dumps(day, ensure_ascii=False)}

USER INSTRUCTION FOR THIS DAY: "{instruction}"

RULES
- Rewrite ONLY this day. Apply the instruction faithfully (e.g. swap a specific slot, change cuisine, change pace).
- Keep the geographic clustering: stay in "{day['area']}" unless the instruction clearly needs another area.
- Keep the 4 slots in order. Keep lat/lng realistic and costs in {plan['currency_code']}.
- Do NOT reuse these activities already used on other days: {json.dumps(used[:40], ensure_ascii=False)}

Return ONLY valid JSON for the single day:
{DAY_SCHEMA.replace('N', str(day['day']))}"""


# =============================================================================
# Demo-mode engine (offline, deterministic, geographically clustered)
# =============================================================================

DEMO_DESTINATIONS = [
    {"city": "Goa", "country": "India", "vibes": ["Beach"], "currency": "INR", "daily_usd": 45, "season": "Nov-Mar",
     "highlights": ["Palolem Beach", "Fontainhas Latin Quarter", "Dudhsagar Falls", "Anjuna Flea Market"],
     "tags": ["Beaches", "Nightlife", "Seafood", "Portuguese heritage"], "interests": ["Food", "Nightlife", "Adventure"]},
    {"city": "Phuket", "country": "Thailand", "vibes": ["Beach"], "currency": "THB", "daily_usd": 70, "season": "Nov-Apr",
     "highlights": ["Phi Phi Islands", "Old Phuket Town", "Big Buddha", "Bangla Road"],
     "tags": ["Island hopping", "Street food", "Nightlife"], "interests": ["Food", "Nightlife", "Adventure"]},
    {"city": "Bali", "country": "Indonesia", "vibes": ["Beach", "Cultural"], "currency": "IDR", "daily_usd": 65, "season": "Apr-Oct",
     "highlights": ["Ubud rice terraces", "Uluwatu Temple", "Seminyak sunsets", "Nusa Penida"],
     "tags": ["Surf", "Temples", "Wellness", "Cafes"], "interests": ["Nature", "Wellness", "Adventure", "Food"]},
    {"city": "Manali", "country": "India", "vibes": ["Mountains"], "currency": "INR", "daily_usd": 35, "season": "Mar-Jun, Oct-Feb",
     "highlights": ["Solang Valley", "Atal Tunnel to Sissu", "Old Manali cafes", "Hadimba Temple"],
     "tags": ["Snow", "Paragliding", "Cafes", "Trekking"], "interests": ["Adventure", "Nature"]},
    {"city": "Leh-Ladakh", "country": "India", "vibes": ["Mountains"], "currency": "INR", "daily_usd": 50, "season": "May-Sep",
     "highlights": ["Pangong Lake", "Nubra Valley", "Khardung La", "Thiksey Monastery"],
     "tags": ["High-altitude", "Road trip", "Monasteries"], "interests": ["Adventure", "Nature", "History"]},
    {"city": "Interlaken", "country": "Switzerland", "vibes": ["Mountains"], "currency": "CHF", "daily_usd": 260, "season": "Jun-Sep, Dec-Mar",
     "highlights": ["Jungfraujoch", "Harder Kulm", "Lauterbrunnen valley", "Lake Thun cruise"],
     "tags": ["Alps", "Scenic trains", "Luxury"], "interests": ["Nature", "Adventure"]},
    {"city": "Jaipur", "country": "India", "vibes": ["Cultural"], "currency": "INR", "daily_usd": 40, "season": "Oct-Mar",
     "highlights": ["Amber Fort", "Hawa Mahal", "City Palace", "Johari Bazaar"],
     "tags": ["Forts", "Royal heritage", "Shopping", "Rajasthani food"], "interests": ["History", "Shopping", "Food"]},
    {"city": "Kyoto", "country": "Japan", "vibes": ["Cultural"], "currency": "JPY", "daily_usd": 140, "season": "Mar-May, Oct-Nov",
     "highlights": ["Fushimi Inari", "Arashiyama bamboo grove", "Gion district", "Kinkaku-ji"],
     "tags": ["Temples", "Tea culture", "Autumn colours"], "interests": ["History", "Art & Museums", "Food"]},
    {"city": "Istanbul", "country": "Turkey", "vibes": ["Cultural", "Urban"], "currency": "TRY", "daily_usd": 90, "season": "Apr-Jun, Sep-Nov",
     "highlights": ["Hagia Sophia", "Grand Bazaar", "Bosphorus cruise", "Cappadocia add-on"],
     "tags": ["History", "Bazaars", "Kebabs"], "interests": ["History", "Food", "Shopping"]},
    {"city": "Dubai", "country": "United Arab Emirates", "vibes": ["Urban"], "currency": "AED", "daily_usd": 220, "season": "Nov-Mar",
     "highlights": ["Burj Khalifa", "Desert safari", "Dubai Mall", "Old Dubai souks"],
     "tags": ["Skyline", "Shopping", "Luxury", "Desert"], "interests": ["Shopping", "Adventure", "Nightlife"]},
    {"city": "Singapore", "country": "Singapore", "vibes": ["Urban"], "currency": "SGD", "daily_usd": 180, "season": "Feb-Apr",
     "highlights": ["Gardens by the Bay", "Marina Bay Sands", "Hawker centres", "Sentosa"],
     "tags": ["Food", "Family-friendly", "Clean & safe"], "interests": ["Food", "Shopping", "Nightlife"]},
    {"city": "Lisbon", "country": "Portugal", "vibes": ["Urban", "Beach", "Cultural"], "currency": "EUR", "daily_usd": 120, "season": "Mar-Jun, Sep-Oct",
     "highlights": ["Alfama & tram 28", "Belem Tower", "Sintra day trip", "Cascais beaches"],
     "tags": ["Pastel de nata", "Fado", "Viewpoints"], "interests": ["Food", "History", "Nightlife"]},
    {"city": "Paris", "country": "France", "vibes": ["Urban", "Cultural"], "currency": "EUR", "daily_usd": 200, "season": "Apr-Jun, Sep-Oct",
     "highlights": ["Eiffel Tower", "Louvre", "Montmartre", "Seine cruise"],
     "tags": ["Art", "Romance", "Cafes", "Fashion"], "interests": ["Art & Museums", "Food", "History", "Shopping"]},
    {"city": "Tokyo", "country": "Japan", "vibes": ["Urban"], "currency": "JPY", "daily_usd": 160, "season": "Mar-May, Oct-Nov",
     "highlights": ["Shibuya Crossing", "Senso-ji", "teamLab Planets", "Tsukiji market"],
     "tags": ["Neon", "Ramen & sushi", "Anime culture"], "interests": ["Food", "Shopping", "Art & Museums", "Nightlife"]},
]

# Each demo city: areas with lat/lng and two alternatives per slot so swaps feel real.
# Costs are in the local currency.
DEMO_CITY_DATA: dict[str, dict] = {
    "goa": {
        "country": "India", "currency": "INR",
        "overview": "Sun-soaked beaches, Portuguese lanes and seafood shacks - this plan keeps North, Panaji, Old Goa and South Goa on separate days so you never waste a day on the highway.",
        "tips": ["Rent a scooter (approx. INR 400/day) - taxis are expensive and unmetered", "Carry cash for beach shacks and flea markets", "Sunset shacks fill up by 6 pm in season - go early", "Avoid swimming at red-flag beaches during monsoon swells"],
        "areas": [
            {"name": "North Goa - Anjuna & Vagator", "lat": 15.573, "lng": 73.740, "theme": "Cliffs, shacks & flea markets", "slots": {
                "Morning Sightseeing": [("Chapora Fort sunrise walk", "Short climb for the classic Vagator coastline view.", 0, 1.5, "Sightseeing"), ("Vagator Beach cliff stroll", "Quiet early-morning walk along the red cliffs.", 0, 1.5, "Nature")],
                "Lunch Recommendation": [("Goan fish thali at an Anjuna beach shack", "Kingfish curry, rice, kokum - the local classic.", 600, 1, "Food"), ("Vegetarian Goan lunch at a sea-view cafe", "Mushroom xacuti, veg caldinho and poi bread.", 450, 1, "Food")],
                "Afternoon Leisure": [("Anjuna Flea Market browsing", "Jewellery, lamps, spices and live music (Wednesdays).", 500, 3, "Shopping"), ("Parasailing & jet-ski at Baga", "Classic water-sports strip, haggle for a combo.", 1200, 3, "Adventure")],
                "Evening Dining & Entertainment": [("Sunset & live music at a Vagator cliff shack", "Chill sundowners, then a seafood platter.", 1500, 3, "Nightlife"), ("Dinner at a Greek-style cliffside restaurant, Vagator", "Book a sunset table; mezze and grills.", 2500, 3, "Dining")],
            }},
            {"name": "Panaji & Fontainhas", "lat": 15.497, "lng": 73.828, "theme": "Latin Quarter heritage", "slots": {
                "Morning Sightseeing": [("Heritage walk through Fontainhas Latin Quarter", "Pastel Portuguese houses, azulejo tiles, tiny chapels.", 300, 2, "Sightseeing"), ("Our Lady of the Immaculate Conception Church", "Panaji's white landmark church and the Municipal Garden.", 0, 1.5, "Sightseeing")],
                "Lunch Recommendation": [("Goan lunch at a Fontainhas heritage restaurant", "Prawn balchao and bebinca to finish.", 700, 1, "Food"), ("Veg thali at an old Panaji cafe", "Local vegetarian thali, cheap and filling.", 300, 1, "Food")],
                "Afternoon Leisure": [("Reis Magos Fort", "Restored riverside fort with gallery and views.", 50, 2, "Sightseeing"), ("Mandovi river sunset cruise", "Hour-long cruise with live Goan music.", 500, 2, "Leisure")],
                "Evening Dining & Entertainment": [("Miramar beach walk + Panaji dinner", "Local seafood at a Campal bistro.", 1200, 3, "Dining"), ("Floating casino evening on the Mandovi", "Entry includes buffet; dress code applies.", 2500, 4, "Nightlife")],
            }},
            {"name": "Old Goa & the hinterland", "lat": 15.503, "lng": 73.912, "theme": "Churches & spice farms", "slots": {
                "Morning Sightseeing": [("Basilica of Bom Jesus & Se Cathedral", "UNESCO-listed churches of Old Goa.", 0, 2.5, "Sightseeing"), ("Church of St Cajetan & Viceroy's Arch", "Quieter corners of Old Goa.", 0, 2, "Sightseeing")],
                "Lunch Recommendation": [("Riverside Goan lunch on Divar Island", "Take the free ferry; try crab xec xec.", 600, 1.5, "Food"), ("Spice-farm Goan buffet", "Lunch served on banana leaves at the plantation.", 500, 1.5, "Food")],
                "Afternoon Leisure": [("Spice plantation tour near Ponda", "Guided walk, feni tasting, elephant-free ethical farm.", 800, 3, "Nature"), ("Dudhsagar Falls jeep safari", "Seasonal (Oct-May); 4x4 through the sanctuary.", 2000, 4, "Adventure")],
                "Evening Dining & Entertainment": [("Sunset at Dona Paula + dinner", "Jetty views, then Goan dinner nearby.", 1200, 3, "Dining"), ("Quiet dinner at a Panaji rooftop", "Early night before the South Goa day.", 1000, 2, "Dining")],
            }},
            {"name": "South Goa - Palolem & Agonda", "lat": 15.010, "lng": 74.023, "theme": "Slow beach day", "slots": {
                "Morning Sightseeing": [("Kayaking at Palolem", "Calm bay, rent a kayak at sunrise.", 700, 2, "Adventure"), ("Agonda Beach yoga & walk", "Quiet turtle-nesting beach.", 300, 2, "Wellness")],
                "Lunch Recommendation": [("Beach shack lunch at Palolem", "Grilled fish of the day with butter-garlic.", 500, 1, "Food"), ("Vegan cafe lunch in Palolem", "Buddha bowls and fresh juices.", 450, 1, "Food")],
                "Afternoon Leisure": [("Boat trip to Butterfly Beach", "Secluded cove, dolphins often spotted.", 900, 3, "Nature"), ("Cabo de Rama Fort", "Cliff-top fort with the best sea views in Goa.", 0, 3, "Sightseeing")],
                "Evening Dining & Entertainment": [("Silent-disco headphone party, Palolem", "Saturday special; otherwise beach bonfire dinner.", 1500, 4, "Nightlife"), ("Candle-lit seafood dinner on Agonda beach", "Tables on the sand, book ahead.", 1500, 3, "Dining")],
            }},
        ],
    },
    "jaipur": {
        "country": "India", "currency": "INR",
        "overview": "The Pink City done neighbourhood-by-neighbourhood: old-city palaces, the Amber fort circuit, the modern C-Scheme side, and a craft day in Sanganer.",
        "tips": ["Forts open 8 am - book a composite ticket (Amber, Nahargarh, Jantar Mantar, Hawa Mahal, Albert Hall)", "Bargain to ~50% in Johari and Bapu Bazaar", "Lassi at the famous old-city lassi shop before noon", "Auto drivers push 'shops' - say no politely and insist on the meter/fixed price"],
        "areas": [
            {"name": "Pink City (Old Walled City)", "lat": 26.924, "lng": 75.826, "theme": "Palaces & bazaars", "slots": {
                "Morning Sightseeing": [("Hawa Mahal & City Palace", "Start at the honeycomb facade, then the royal courtyards.", 700, 3, "Sightseeing"), ("Jantar Mantar observatory", "UNESCO astronomical instruments - go early for shade.", 200, 2, "Sightseeing")],
                "Lunch Recommendation": [("Rajasthani thali at an old-city sweet-shop restaurant", "Dal baati churma, ghewar for dessert.", 600, 1, "Food"), ("Street-food crawl at Bapu Bazaar", "Pyaaz kachori, mirchi vada, lassi.", 250, 1, "Food")],
                "Afternoon Leisure": [("Johari Bazaar shopping", "Gems, block prints, mojari shoes.", 1500, 3, "Shopping"), ("Heritage walk of the old city gates", "Guided walk through the nine squares of the planned city.", 500, 3, "History")],
                "Evening Dining & Entertainment": [("Rooftop dinner facing Hawa Mahal", "Lit facade view, Rajasthani and North Indian.", 1200, 3, "Dining"), ("Evening puppet show + dinner", "Traditional kathputli performance at a heritage haveli.", 1500, 3, "Nightlife")],
            }},
            {"name": "Amber & the fort circuit", "lat": 26.985, "lng": 75.851, "theme": "Forts & sunset", "slots": {
                "Morning Sightseeing": [("Amber Fort with jeep ride up", "Sheesh Mahal, Ganesh Pol - arrive by 8 am.", 1000, 3.5, "Sightseeing"), ("Panna Meena ka Kund stepwell", "Photogenic geometric stepwell beside Amber.", 0, 1, "Sightseeing")],
                "Lunch Recommendation": [("Lunch inside the fort complex", "Heritage dining room with royal recipes.", 1500, 1.5, "Food"), ("Simple dhaba lunch on the Amber road", "Local veg thali, quick and cheap.", 250, 1, "Food")],
                "Afternoon Leisure": [("Jaigarh Fort & the world's largest cannon", "Walk or taxi up from Amber.", 200, 2.5, "History"), ("Anokhi Museum of Hand Printing", "Block-print demos in a restored haveli near Amber.", 100, 2, "Art & Museums")],
                "Evening Dining & Entertainment": [("Nahargarh Fort sunset + dinner at the fort restaurant", "City lights from the ramparts.", 800, 3.5, "Dining"), ("Jal Mahal lakeside stroll + chaat", "Evening lights on the water palace.", 300, 2, "Leisure")],
            }},
            {"name": "C-Scheme & modern Jaipur", "lat": 26.910, "lng": 75.803, "theme": "Museums, cafes & gardens", "slots": {
                "Morning Sightseeing": [("Albert Hall Museum", "Indo-Saracenic museum, Egyptian mummy and miniatures.", 300, 2, "Art & Museums"), ("Birla Mandir & Moti Dungri", "White marble temple in the morning calm.", 0, 1.5, "Sightseeing")],
                "Lunch Recommendation": [("Organic vegetarian cafe lunch in C-Scheme", "Salads, thalis, cold-pressed juices.", 500, 1, "Food"), ("Modern Rajasthani tasting lunch", "Laal maas or safed maas done upscale.", 1200, 1.5, "Food")],
                "Afternoon Leisure": [("Patrika Gate & Jawahar Circle", "Painted gate, every arch a different Rajasthan region.", 0, 2, "Sightseeing"), ("Spa & wellness afternoon", "Ayurvedic massage at a heritage spa.", 2500, 3, "Wellness")],
                "Evening Dining & Entertainment": [("Chokhi Dhani village experience", "Folk dances, camel rides, unlimited thali.", 1200, 4, "Nightlife"), ("Craft-cocktail bar + dinner in C-Scheme", "Jaipur's modern bar scene.", 2000, 3, "Nightlife")],
            }},
            {"name": "Sanganer & the outskirts", "lat": 26.820, "lng": 75.800, "theme": "Crafts & temples", "slots": {
                "Morning Sightseeing": [("Block-printing workshop in Sanganer", "Print your own scarf with a master printer.", 800, 3, "Art & Museums"), ("Galtaji (Monkey Temple)", "Hillside temple complex with sacred tanks.", 0, 2.5, "Sightseeing")],
                "Lunch Recommendation": [("Dal baati at a highway dhaba", "The real deal, served on steel plates.", 300, 1, "Food"), ("Home-style lunch at a Sanganer family kitchen", "Pre-booked community dining experience.", 600, 1.5, "Food")],
                "Afternoon Leisure": [("Blue-pottery studio visit", "Watch and try the Jaipur blue-pottery craft.", 500, 2, "Art & Museums"), ("Sisodia Rani garden", "Tiered Mughal garden, quiet and green.", 50, 2, "Nature")],
                "Evening Dining & Entertainment": [("Street-food trail at Masala Chowk", "Open-air food court of Jaipur legends.", 400, 2.5, "Food"), ("Farewell dinner at a heritage haveli hotel", "Live classical music, royal thali.", 2500, 3, "Dining")],
            }},
        ],
    },
    "bali": {
        "country": "Indonesia", "currency": "IDR",
        "overview": "Rice terraces, cliff temples and beach clubs - each day sticks to one part of the island (Ubud, Canggu/Seminyak, Uluwatu, Nusa Penida) to avoid Bali's notorious traffic.",
        "tips": ["Hire a driver for the day (~IDR 600-700k) instead of hopping taxis", "Carry a sarong for temples", "Gojek/Grab for short hops; avoid Canggu at 5-7 pm", "ATMs: use ones attached to banks only"],
        "areas": [
            {"name": "Ubud", "lat": -8.509, "lng": 115.263, "theme": "Rice terraces & temples", "slots": {
                "Morning Sightseeing": [("Tegalalang Rice Terrace & jungle swing", "Go at 7 am before the crowds.", 150000, 3, "Nature"), ("Campuhan Ridge walk", "Easy 2 km ridge trail with valley views.", 0, 2, "Nature")],
                "Lunch Recommendation": [("Nasi campur at a classic Ubud warung", "Local mixed-rice plate, strong coffee.", 80000, 1, "Food"), ("Vegetarian lunch at a raw-food cafe", "Ubud's famous plant-based scene.", 120000, 1, "Food")],
                "Afternoon Leisure": [("Sacred Monkey Forest", "Temple complex in the jungle; hold your sunglasses.", 80000, 2, "Nature"), ("Balinese cooking class", "Market visit + 5-dish class.", 450000, 4, "Food")],
                "Evening Dining & Entertainment": [("Kecak fire dance at Ubud Palace + dinner", "7:30 pm show, dinner at a Jalan Raya restaurant.", 250000, 3, "Nightlife"), ("Dinner overlooking the rice fields", "Candle-lit paddy-side restaurant.", 350000, 2.5, "Dining")],
            }},
            {"name": "Canggu & Seminyak", "lat": -8.655, "lng": 115.140, "theme": "Surf & sunset clubs", "slots": {
                "Morning Sightseeing": [("Surf lesson at Batu Bolong beach", "Beginner-friendly waves, board included.", 350000, 2.5, "Adventure"), ("Sunrise walk on Berawa beach", "Then a smoothie bowl at a beach cafe.", 0, 2, "Nature")],
                "Lunch Recommendation": [("Smoothie bowls & eggs at a Canggu cafe", "The brunch capital of Bali.", 90000, 1, "Food"), ("Babi guling or ayam betutu lunch", "Traditional Balinese roast at a warung.", 70000, 1, "Food")],
                "Afternoon Leisure": [("Tanah Lot sea temple", "Offshore temple; best 1 hour before sunset.", 75000, 3, "Sightseeing"), ("Seminyak boutique shopping", "Jalan Kayu Aya designer lane.", 500000, 3, "Shopping")],
                "Evening Dining & Entertainment": [("Sunset at a Seminyak beach club", "Pool, DJ, cocktails - minimum spend applies.", 300000, 4, "Nightlife"), ("Seafood BBQ on Jimbaran-style grill in Canggu", "Fresh catch, feet in the sand.", 250000, 3, "Dining")],
            }},
            {"name": "Uluwatu & the Bukit", "lat": -8.829, "lng": 115.085, "theme": "Cliffs & hidden beaches", "slots": {
                "Morning Sightseeing": [("Padang Padang & Bingin beaches", "Cliff-stair beaches, calm in the morning.", 15000, 3, "Nature"), ("Melasti Beach", "White cliffs, clear water, Instagram-famous.", 10000, 3, "Nature")],
                "Lunch Recommendation": [("Cliff-top warung lunch at Bingin", "Nasi goreng with a surf view.", 70000, 1, "Food"), ("Healthy bowls at an Uluwatu cafe", "Acai, poke and cold brew.", 110000, 1, "Food")],
                "Afternoon Leisure": [("Uluwatu Temple cliff walk", "Temple on a 70 m cliff; sunset Kecak optional.", 50000, 2.5, "Sightseeing"), ("Cliff-side infinity pool day pass", "Lounge at a Bukit resort pool.", 400000, 4, "Wellness")],
                "Evening Dining & Entertainment": [("Jimbaran beach grilled-seafood dinner", "Tables on the sand, lobster by weight.", 350000, 3, "Dining"), ("Sunset cliff bar at Uluwatu", "Cocktails over the surf break.", 300000, 3, "Nightlife")],
            }},
            {"name": "Nusa Penida day trip", "lat": -8.735, "lng": 115.540, "theme": "Island adventure", "slots": {
                "Morning Sightseeing": [("Fast boat from Sanur + Kelingking viewpoint", "The T-rex cliff - go first thing.", 450000, 4, "Adventure"), ("Diamond Beach & Atuh Beach", "East-coast twin beaches, steep stairs.", 400000, 4, "Nature")],
                "Lunch Recommendation": [("Warung lunch at Crystal Bay", "Simple grilled fish and rice by the beach.", 70000, 1, "Food"), ("Lunch at a cliff-top cafe near Kelingking", "Fresh juices, nasi campur.", 80000, 1, "Food")],
                "Afternoon Leisure": [("Snorkelling at Manta Point", "Manta rays almost guaranteed.", 300000, 3, "Adventure"), ("Angel's Billabong & Broken Beach", "Natural infinity pool and rock arch.", 50000, 3, "Nature")],
                "Evening Dining & Entertainment": [("Return boat + sunset dinner in Sanur", "Relaxed beachfront end to a big day.", 200000, 3, "Dining"), ("Night market dinner in Sanur", "Satay and martabak at the pasar malam.", 80000, 2, "Food")],
            }},
        ],
    },
    "paris": {
        "country": "France", "currency": "EUR",
        "overview": "Paris by arrondissement: the island & Latin Quarter, Louvre & Tuileries, Eiffel & Orsay, then Montmartre - each day is walkable end-to-end.",
        "tips": ["Buy a Navigo Easy card for the metro", "Book Louvre/Orsay/Eiffel slots online 2+ weeks ahead", "Lunch 'formule' menus are far cheaper than dinner", "Pickpockets work the metro and Montmartre steps - front pockets only"],
        "areas": [
            {"name": "Ile de la Cite & Latin Quarter", "lat": 48.853, "lng": 2.347, "theme": "Medieval heart", "slots": {
                "Morning Sightseeing": [("Notre-Dame & Sainte-Chapelle", "Stained glass first, cathedral second.", 13, 2.5, "Sightseeing"), ("Pantheon & Rue Mouffetard market", "Great men's crypt, then the oldest market street.", 13, 2.5, "History")],
                "Lunch Recommendation": [("Galettes at a Breton creperie", "Buckwheat galette + cider.", 18, 1, "Food"), ("Falafel in the Marais", "Cross the river for the famous queue.", 10, 1, "Food")],
                "Afternoon Leisure": [("Shakespeare & Co + Luxembourg Gardens", "Bookshop, then chairs by the fountain.", 0, 3, "Leisure"), ("Musee de Cluny (medieval art)", "The Lady and the Unicorn tapestries.", 12, 2.5, "Art & Museums")],
                "Evening Dining & Entertainment": [("Seine evening cruise + dinner in Saint-Germain", "Lights on the bridges, then a bistro.", 60, 3.5, "Dining"), ("Jazz club in the Latin Quarter", "Cellar jazz, cheap drinks.", 25, 3, "Nightlife")],
            }},
            {"name": "Louvre & Tuileries", "lat": 48.861, "lng": 2.336, "theme": "Art & royal gardens", "slots": {
                "Morning Sightseeing": [("Louvre Museum (timed entry)", "Denon wing first: Mona Lisa, Winged Victory.", 22, 3.5, "Art & Museums"), ("Palais-Royal gardens & Galerie Vivienne", "Striped columns, covered passages.", 0, 2, "Sightseeing")],
                "Lunch Recommendation": [("Lunch under the Louvre arcades", "Classic brasserie plates, museum view.", 35, 1.5, "Food"), ("Bento or ramen on Rue Sainte-Anne", "Paris's Little Tokyo, 5 min from the Louvre.", 16, 1, "Food")],
                "Afternoon Leisure": [("Tuileries to Place de la Concorde stroll", "Then the Orangerie's Water Lilies.", 12, 3, "Art & Museums"), ("Shopping on Rue Saint-Honore", "Flagships and the Samaritaine rooftop.", 100, 3, "Shopping")],
                "Evening Dining & Entertainment": [("Dinner near Palais-Royal", "Modern French tasting menu.", 55, 2.5, "Dining"), ("Opera Garnier evening tour or show", "Chandelier, grand staircase, Chagall ceiling.", 15, 2.5, "Nightlife")],
            }},
            {"name": "Eiffel, Trocadero & Orsay", "lat": 48.858, "lng": 2.294, "theme": "Icons of the Left Bank", "slots": {
                "Morning Sightseeing": [("Eiffel Tower summit", "First slot of the day = shortest queue.", 36, 2.5, "Sightseeing"), ("Rue Cler market street", "Cheese, bread, fruit - picnic shopping.", 15, 1.5, "Food")],
                "Lunch Recommendation": [("Picnic on the Champ de Mars", "Baguette, brie, tarte from Rue Cler.", 15, 1, "Food"), ("Classic bistro steak-frites near Ecole Militaire", "Lunch formule with dessert.", 28, 1.5, "Food")],
                "Afternoon Leisure": [("Musee d'Orsay", "Impressionists in a converted railway station.", 16, 3, "Art & Museums"), ("Seine-side cycle to Pont Alexandre III", "Velib bikes along the river.", 5, 2.5, "Adventure")],
                "Evening Dining & Entertainment": [("Sunset at Trocadero + bistro dinner", "The hourly sparkle at the top of the hour.", 45, 3, "Dining"), ("Dinner cruise with the tower lit", "Three courses on the water.", 90, 3, "Dining")],
            }},
            {"name": "Montmartre", "lat": 48.886, "lng": 2.343, "theme": "Artists' hill", "slots": {
                "Morning Sightseeing": [("Sacre-Coeur & Place du Tertre", "Climb early; artists set up by 10.", 0, 2.5, "Sightseeing"), ("Montmartre vineyard & Wall of Love", "Hidden corners behind the basilica.", 0, 2, "Sightseeing")],
                "Lunch Recommendation": [("Classic bistro lunch on the hill", "Onion soup and coq au vin.", 25, 1.5, "Food"), ("Lebanese or veggie lunch on Rue des Abbesses", "Light and cheap after the climb.", 15, 1, "Food")],
                "Afternoon Leisure": [("Musee de Montmartre & Renoir gardens", "The studio-house of the Montmartre painters.", 15, 2.5, "Art & Museums"), ("Vintage shopping in Pigalle", "Thrift stores and record shops.", 40, 2.5, "Shopping")],
                "Evening Dining & Entertainment": [("Cabaret evening in Montmartre", "Book the show-only ticket to save.", 80, 3, "Nightlife"), ("Wine bar + fondue dinner", "Cosy Montmartre cellar.", 40, 3, "Dining")],
            }},
        ],
    },
    "tokyo": {
        "country": "Japan", "currency": "JPY",
        "overview": "Tokyo by rail line: Asakusa/Ueno, Shibuya/Harajuku, Shinjuku and the bay - each day sits on one or two adjacent stations so you ride, not zig-zag.",
        "tips": ["Get a Suica/Pasmo on your phone before landing", "Convenience-store breakfasts are excellent and cheap", "Many small restaurants are cash-only", "Reserve teamLab and Shibuya Sky online; same-day is rarely possible"],
        "areas": [
            {"name": "Asakusa & Ueno", "lat": 35.712, "lng": 139.797, "theme": "Old Tokyo", "slots": {
                "Morning Sightseeing": [("Senso-ji Temple & Nakamise street", "Go by 8 am for empty lanterns.", 0, 2.5, "Sightseeing"), ("Ueno Park & Tokyo National Museum", "Cherry blossoms in spring, samurai swords year-round.", 1000, 3, "Art & Museums")],
                "Lunch Recommendation": [("Tempura at a century-old Asakusa shop", "Tendon bowl, queue moves fast.", 2500, 1, "Food"), ("Vegetarian shojin-ryori lunch", "Buddhist temple cuisine near Ueno.", 3000, 1.5, "Food")],
                "Afternoon Leisure": [("Kappabashi kitchen street + Sumida river walk", "Knives, plastic food, ceramics.", 3000, 3, "Shopping"), ("Ameyoko market browsing", "Street snacks and bargains under the tracks.", 1500, 2.5, "Shopping")],
                "Evening Dining & Entertainment": [("Tokyo Skytree night view + Solamachi dinner", "Book the 6 pm slot for dusk-to-night.", 4000, 3.5, "Sightseeing"), ("Hoppy Street izakaya night", "Asakusa's retro drinking lane.", 3500, 3, "Nightlife")],
            }},
            {"name": "Shibuya & Harajuku", "lat": 35.660, "lng": 139.701, "theme": "Pop culture & shrines", "slots": {
                "Morning Sightseeing": [("Meiji Shrine & Yoyogi Park", "Forest shrine in the middle of the city.", 0, 2.5, "Sightseeing"), ("Nezu Museum garden", "Quiet Japanese garden behind Omotesando.", 1500, 2, "Art & Museums")],
                "Lunch Recommendation": [("Yuzu-shio ramen in Harajuku", "Light citrus broth, ticket machine ordering.", 1300, 1, "Food"), ("Okonomiyaki in Shibuya", "Cook-it-yourself savoury pancake.", 1800, 1.5, "Food")],
                "Afternoon Leisure": [("Takeshita Street + Shibuya Sky", "Kawaii shopping, then the open-air rooftop.", 2500, 3.5, "Sightseeing"), ("Shibuya Parco anime & game floors", "Nintendo, Pokemon and Capcom stores.", 5000, 3, "Shopping")],
                "Evening Dining & Entertainment": [("Izakaya hopping in Shibuya Yokocho", "Tiny stalls, yakitori and highballs.", 4500, 3, "Nightlife"), ("Sushi dinner in Shibuya", "Mid-range omakase counter.", 8000, 2, "Dining")],
            }},
            {"name": "Shinjuku", "lat": 35.690, "lng": 139.700, "theme": "Gardens by day, neon by night", "slots": {
                "Morning Sightseeing": [("Shinjuku Gyoen garden", "Three garden styles, perfect picnic lawns.", 500, 2.5, "Nature"), ("Tokyo Metropolitan Government observatory", "Free 45th-floor view, Fuji on clear days.", 0, 1.5, "Sightseeing")],
                "Lunch Recommendation": [("Conveyor-belt sushi near the station", "Fast, fun, cheap plates.", 2000, 1, "Food"), ("Tonkatsu set lunch", "Crisp pork cutlet, free cabbage refills.", 1800, 1, "Food")],
                "Afternoon Leisure": [("Department-store basement food halls (depachika)", "Isetan's basement is a museum of food.", 3000, 2.5, "Shopping"), ("Samurai or ninja experience class", "Katana basics in a dojo near Shinjuku.", 6000, 2, "Adventure")],
                "Evening Dining & Entertainment": [("Omoide Yokocho yakitori + Golden Gai bars", "Smoky alley skewers, then 6-seat bars.", 5000, 4, "Nightlife"), ("Kabukicho robot-style show + ramen", "Loud, neon, unforgettable.", 9000, 3.5, "Nightlife")],
            }},
            {"name": "Tsukiji, Toyosu & Odaiba (bay side)", "lat": 35.645, "lng": 139.775, "theme": "Markets & the bay", "slots": {
                "Morning Sightseeing": [("Tsukiji Outer Market brunch crawl", "Tamagoyaki, uni, tuna skewers.", 2000, 2.5, "Food"), ("Hamarikyu Gardens tea house", "Edo garden with skyscraper backdrop.", 300, 2, "Nature")],
                "Lunch Recommendation": [("Sushi lunch at Tsukiji", "Chef's set from the morning market.", 3500, 1, "Food"), ("Monjayaki in Tsukishima", "Tokyo's own gooey pancake street.", 1800, 1.5, "Food")],
                "Afternoon Leisure": [("teamLab Planets, Toyosu", "Barefoot digital-art museum; book ahead.", 3800, 2.5, "Art & Museums"), ("Odaiba waterfront & giant Gundam", "Rainbow Bridge views, DiverCity.", 0, 3, "Leisure")],
                "Evening Dining & Entertainment": [("Odaiba night view + Rainbow Bridge dinner", "Bayfront terrace restaurants.", 4000, 3, "Dining"), ("Yakatabune dinner boat on the bay", "Traditional lantern boat with tempura.", 12000, 2.5, "Dining")],
            }},
        ],
    },
    "dubai": {
        "country": "United Arab Emirates", "currency": "AED",
        "overview": "Downtown glitz, Old Dubai souks, the Marina and a desert evening - grouped so you take one long cab per day, not five.",
        "tips": ["Metro is cheap and air-conditioned; Nol card from any station", "Friday brunch is the city's big social event", "Dress modestly in Old Dubai and malls", "Book Burj Khalifa sunset slots 2-3 weeks ahead"],
        "areas": [
            {"name": "Downtown Dubai", "lat": 25.197, "lng": 55.274, "theme": "Skyline & fountains", "slots": {
                "Morning Sightseeing": [("Burj Khalifa - At the Top (124/125)", "Morning slot for clear desert haze-free views.", 170, 2, "Sightseeing"), ("Dubai Opera district walk", "Architecture stroll around the boulevard.", 0, 1.5, "Sightseeing")],
                "Lunch Recommendation": [("Dubai Mall food hall", "Everything from shawarma to ramen.", 60, 1, "Food"), ("Emirati lunch at a heritage restaurant", "Machboos and luqaimat.", 120, 1.5, "Food")],
                "Afternoon Leisure": [("Dubai Mall + Aquarium & Underwater Zoo", "Then the ice rink if you need a break from heat.", 150, 3.5, "Leisure"), ("Dubai Frame", "Old-vs-new city view from the golden frame.", 50, 2, "Sightseeing")],
                "Evening Dining & Entertainment": [("Dubai Fountain show + dinner at Souk Al Bahar", "Fountain view table; shows every 30 min.", 200, 3, "Dining"), ("Rooftop lounge with Burj view", "Sunset cocktails and mezze.", 300, 3, "Nightlife")],
            }},
            {"name": "Old Dubai - Deira & Bur Dubai", "lat": 25.263, "lng": 55.297, "theme": "Souks & the Creek", "slots": {
                "Morning Sightseeing": [("Al Fahidi Historical District", "Wind-tower houses, coffee museum, art galleries.", 10, 2.5, "History"), ("Dubai Museum (Al Fahidi Fort)", "The pearl-diving story of the city.", 5, 1.5, "History")],
                "Lunch Recommendation": [("Emirati lunch at an Al Fahidi courtyard cafe", "Shrimp machboos, karak tea.", 80, 1.5, "Food"), ("Pakistani/Indian lunch in Meena Bazaar", "Legendary cheap eats of Bur Dubai.", 35, 1, "Food")],
                "Afternoon Leisure": [("Abra ride + Gold & Spice Souks", "1 AED boat across the Creek, then bargain hard.", 5, 3, "Shopping"), ("Al Seef waterfront walk", "New-old promenade along the Creek.", 0, 2, "Leisure")],
                "Evening Dining & Entertainment": [("Dhow cruise dinner on the Creek", "Buffet and lights of Old Dubai.", 150, 3, "Dining"), ("Global Village evening (seasonal Oct-Apr)", "Country pavilions, street food and rides.", 100, 4, "Nightlife")],
            }},
            {"name": "Marina & JBR", "lat": 25.080, "lng": 55.140, "theme": "Beach & yachts", "slots": {
                "Morning Sightseeing": [("Dubai Marina walk & Ain Dubai photo stop", "Yachts, towers and the giant wheel.", 0, 2, "Sightseeing"), ("Kite Beach morning swim", "Public beach with Burj Al Arab backdrop.", 0, 2.5, "Nature")],
                "Lunch Recommendation": [("Beachfront lunch at JBR The Walk", "Lebanese grills with sea views.", 90, 1.5, "Food"), ("Seafood market lunch in the Marina", "Pick your fish, choose the style.", 150, 1.5, "Food")],
                "Afternoon Leisure": [("JBR beach + jet ski", "Rentals right on the sand.", 250, 3, "Adventure"), ("Palm Jumeirah monorail + The View", "Ride out to the Palm's observation deck.", 100, 3, "Sightseeing")],
                "Evening Dining & Entertainment": [("Marina yacht cruise at sunset", "Shared 2-hour cruise with snacks.", 300, 3, "Nightlife"), ("Dinner at Pier 7, Dubai Marina", "Seven restaurants, one tower, pick your cuisine.", 250, 3, "Dining")],
            }},
            {"name": "Desert day", "lat": 24.950, "lng": 55.550, "theme": "Dunes & stars", "slots": {
                "Morning Sightseeing": [("Lazy pool morning / hotel breakfast", "Rest before the desert heat.", 0, 2, "Wellness"), ("Al Qudra lakes sunrise", "Flamingos and cycling track in the desert.", 0, 3, "Nature")],
                "Lunch Recommendation": [("Light hotel lunch", "Keep it light before dune bashing.", 120, 1, "Food"), ("Camel-milk cafe & snacks", "Quirky Emirati desert pit stop.", 60, 1, "Food")],
                "Afternoon Leisure": [("Desert safari: dune bashing, sandboarding, camel ride", "Pick-up at 3 pm, conservation-reserve option available.", 250, 4, "Adventure"), ("Hot-air balloon over the desert (dawn alt.)", "Book as an early-morning alternative.", 1100, 4, "Adventure")],
                "Evening Dining & Entertainment": [("Bedouin camp BBQ dinner & show", "Included with most safaris; henna, falconry.", 100, 3, "Dining"), ("Stargazing dinner at a desert resort", "Private dune dinner, premium.", 600, 3, "Dining")],
            }},
        ],
    },
}

GENERIC_AREAS = [
    ("Old Town & Heritage Core", 0.000, 0.000, "Heritage & landmarks"),
    ("Waterfront / Scenic District", 0.035, 0.030, "Views & open air"),
    ("Market & Food Quarter", -0.030, 0.025, "Markets & local flavours"),
    ("Nature Escape (edge of town)", 0.060, -0.050, "A breath of nature"),
    ("Modern District & Nightlife", -0.045, -0.035, "Cafes, galleries & nightlife"),
]

GENERIC_SLOTS = {
    "Beach": {
        "Morning Sightseeing": [("Sunrise walk on {dest}'s main beach", "Soft light, empty sand, coffee from a beach kiosk.", 5, 2, "Nature"), ("Coastal viewpoint hike", "Short trail to the best sea view in {dest}.", 0, 2.5, "Adventure")],
        "Lunch Recommendation": [("Grilled catch-of-the-day at a beach shack", "Ask what came in this morning.", 15, 1, "Food"), ("Vegetarian lunch at a sea-view cafe", "Fresh salads, local bread, cold juice.", 12, 1, "Food")],
        "Afternoon Leisure": [("Snorkelling or kayaking session", "Rent gear on the beach; go before the wind picks up.", 25, 3, "Adventure"), ("Hammock afternoon + beach massage", "Do nothing, properly.", 20, 3, "Wellness")],
        "Evening Dining & Entertainment": [("Sunset dinner on the sand", "Tables on the beach, seafood platter.", 35, 3, "Dining"), ("Beach bonfire & live music", "Ask locals which shack has music tonight.", 25, 3, "Nightlife")],
    },
    "Mountains": {
        "Morning Sightseeing": [("Sunrise viewpoint drive/hike", "Peaks turn gold around 6:30 am.", 10, 3, "Nature"), ("Old village & monastery/temple walk", "Stone lanes, prayer flags, wood-smoke.", 0, 2.5, "Sightseeing")],
        "Lunch Recommendation": [("Mountain-cafe lunch with a valley view", "Local stew/thukpa and hot bread.", 12, 1, "Food"), ("Home-stay style vegetarian lunch", "Seasonal vegetables, mountain rice.", 10, 1, "Food")],
        "Afternoon Leisure": [("Waterfall or river-side trek", "Easy 2-3 hour trail, carry water.", 15, 3.5, "Adventure"), ("Paragliding / zipline (weather permitting)", "Book the morning before.", 45, 2, "Adventure")],
        "Evening Dining & Entertainment": [("Bonfire dinner at the stay", "Barbecue and local music.", 25, 3, "Dining"), ("Cafe-street evening in town", "Live acoustic sets and apple-pie.", 20, 3, "Nightlife")],
    },
    "Cultural": {
        "Morning Sightseeing": [("{dest}'s signature monument (book early slot)", "The must-see, before the tour buses.", 20, 3, "Sightseeing"), ("Guided heritage walk of the old quarter", "Stories you won't get from a plaque.", 15, 2.5, "History")],
        "Lunch Recommendation": [("Traditional lunch at a century-old eatery", "Order the house classic.", 15, 1, "Food"), ("Vegetarian thali / meze lunch near the old town", "Local vegetarian staples, fast service.", 10, 1, "Food")],
        "Afternoon Leisure": [("City museum / art gallery", "Air-conditioned afternoon with the collections.", 12, 2.5, "Art & Museums"), ("Craft workshop (pottery / weaving / printing)", "Make something to take home.", 30, 3, "Art & Museums")],
        "Evening Dining & Entertainment": [("Folk performance + dinner", "Music or dance show with a set menu.", 35, 3, "Nightlife"), ("Rooftop dinner facing the old town", "Lit-up monuments, slow dinner.", 30, 3, "Dining")],
    },
    "Urban": {
        "Morning Sightseeing": [("Skyline viewpoint / observation deck", "Clear mornings give the best photos.", 25, 2, "Sightseeing"), ("Architecture & street-art walk", "Self-guided loop through the design district.", 0, 2.5, "Sightseeing")],
        "Lunch Recommendation": [("Food-hall lunch", "Many counters, one table - everyone's happy.", 15, 1, "Food"), ("Plant-based cafe lunch", "Bowls, sourdough, specialty coffee.", 14, 1, "Food")],
        "Afternoon Leisure": [("Flagship shopping street + concept stores", "Window-shop or splurge.", 50, 3, "Shopping"), ("Contemporary art museum", "The city's modern collection.", 18, 2.5, "Art & Museums")],
        "Evening Dining & Entertainment": [("Night market / street-food crawl", "Eat small, eat often.", 20, 3, "Nightlife"), ("Cocktail bar + chef's-table dinner", "Reserve ahead for the counter seats.", 70, 3, "Dining")],
    },
}

CITY_COORDS = {  # for generic demo clustering
    "london": (51.507, -0.128, "GBP", "United Kingdom"), "rome": (41.903, 12.496, "EUR", "Italy"),
    "bangkok": (13.756, 100.502, "THB", "Thailand"), "new york": (40.713, -74.006, "USD", "United States"),
    "mumbai": (19.076, 72.878, "INR", "India"), "delhi": (28.614, 77.209, "INR", "India"),
    "udaipur": (24.586, 73.713, "INR", "India"), "kerala": (9.931, 76.267, "INR", "India"),
    "kochi": (9.931, 76.267, "INR", "India"), "rishikesh": (30.087, 78.268, "INR", "India"),
    "darjeeling": (27.036, 88.263, "INR", "India"), "shimla": (31.104, 77.173, "INR", "India"),
    "manali": (32.240, 77.189, "INR", "India"), "leh": (34.152, 77.577, "INR", "India"),
    "leh-ladakh": (34.152, 77.577, "INR", "India"), "andaman": (11.667, 92.736, "INR", "India"),
    "singapore": (1.352, 103.820, "SGD", "Singapore"), "kyoto": (35.011, 135.768, "JPY", "Japan"),
    "istanbul": (41.008, 28.978, "TRY", "Turkey"), "lisbon": (38.722, -9.139, "EUR", "Portugal"),
    "barcelona": (41.385, 2.173, "EUR", "Spain"), "amsterdam": (52.370, 4.895, "EUR", "Netherlands"),
    "phuket": (7.880, 98.392, "THB", "Thailand"), "interlaken": (46.686, 7.863, "CHF", "Switzerland"),
    "maldives": (4.175, 73.509, "MVR", "Maldives"), "kathmandu": (27.717, 85.324, "NPR", "Nepal"),
    "colombo": (6.927, 79.861, "LKR", "Sri Lanka"), "hong kong": (22.319, 114.169, "HKD", "Hong Kong"),
    "sydney": (-33.869, 151.209, "AUD", "Australia"), "seoul": (37.566, 126.978, "KRW", "South Korea"),
    "hampi": (15.335, 76.460, "INR", "India"), "varanasi": (25.318, 83.006, "INR", "India"),
    "agra": (27.177, 78.008, "INR", "India"), "amritsar": (31.634, 74.872, "INR", "India"),
    "munnar": (10.089, 77.060, "INR", "India"), "pondicherry": (11.934, 79.830, "INR", "India"),
    "coorg": (12.337, 75.806, "INR", "India"), "ooty": (11.413, 76.695, "INR", "India"),
    "gokarna": (14.550, 74.318, "INR", "India"), "mysore": (12.296, 76.639, "INR", "India"),
    "hyderabad": (17.385, 78.487, "INR", "India"), "bangalore": (12.972, 77.594, "INR", "India"),
    "kolkata": (22.573, 88.364, "INR", "India"), "chennai": (13.083, 80.270, "INR", "India"),
    "pune": (18.520, 73.857, "INR", "India"), "jaisalmer": (26.916, 70.916, "INR", "India"),
    "jodhpur": (26.292, 73.019, "INR", "India"), "kasol": (32.010, 77.315, "INR", "India"),
    "spiti": (32.246, 78.034, "INR", "India"), "dharamshala": (32.219, 76.323, "INR", "India"),
    "nainital": (29.392, 79.453, "INR", "India"), "mussoorie": (30.459, 78.066, "INR", "India"),
    "gangtok": (27.339, 88.607, "INR", "India"), "shillong": (25.579, 91.893, "INR", "India"),
    "bhopal": (23.260, 77.413, "INR", "India"), "indore": (22.720, 75.858, "INR", "India"),
    "khajuraho": (24.832, 79.920, "INR", "India"), "ujjain": (23.179, 75.785, "INR", "India"),
}


def _activity(name, desc, cost, hours, cat, slot, area, lat, lng, rng):
    return {
        "slot": slot, "name": name, "area": area, "description": desc, "duration_hours": float(hours),
        "cost_local": float(cost), "category": cat,
        "lat": round(lat + rng.uniform(-0.006, 0.006), 5), "lng": round(lng + rng.uniform(-0.006, 0.006), 5),
    }


def demo_recommendations(prefs: dict) -> dict:
    month = datetime.fromisoformat(prefs["start_date"]).month
    daily_cap = DAILY_BUDGET_USD[prefs["budget"]]
    scored = []
    for d in DEMO_DESTINATIONS:
        score = 55.0
        if prefs["vibe"] in d["vibes"]:
            score += 25
        ratio = d["daily_usd"] / daily_cap
        score += 12 if 0.4 <= ratio <= 1.1 else (6 if ratio < 0.4 else -10)
        overlap = len(set(prefs["interests"]) & set(d["interests"]))
        score += min(10, overlap * 4)
        in_season = _month_in_season(month, d["season"])
        score += 6 if in_season else -4
        scored.append((round(min(99, score)), d, in_season))
    scored.sort(key=lambda x: -x[0])
    recs = []
    for score, d, in_season in scored[:3]:
        recs.append({
            "city": d["city"], "country": d["country"], "match_score": score,
            "why": f"{d['city']} is a strong {prefs['vibe'].lower()} pick for a {prefs['party'].lower()} trip at a {prefs['budget'].lower()} budget, with {', '.join(d['tags'][:2]).lower()} front and centre.",
            "weather_in_month": "Peak season - great weather" if in_season else "Off-season - fewer crowds, check the forecast",
            "best_season": d["season"], "estimated_daily_cost_usd": d["daily_usd"], "currency_code": d["currency"],
            "highlights": d["highlights"], "tags": d["tags"],
        })
    return {"recommendations": recs}


def _month_in_season(month: int, season: str) -> bool:
    abbr = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
    for part in season.lower().replace(" ", "").split(","):
        if "-" not in part:
            continue
        a, b = part.split("-")
        if a[:3] not in abbr or b[:3] not in abbr:
            continue
        ia, ib = abbr.index(a[:3]) + 1, abbr.index(b[:3]) + 1
        if ia <= ib and ia <= month <= ib:
            return True
        if ia > ib and (month >= ia or month <= ib):
            return True
    return False


def _pick_slot(options, rng, avoid: set[str] | None = None):
    pool = [o for o in options if not avoid or o[0] not in avoid] or list(options)
    return rng.choice(pool)


def demo_itinerary(prefs: dict) -> dict:
    rng = random.Random(prefs_seed(prefs))
    dest = (prefs.get("destination") or "Goa").strip()
    key = dest.lower()
    n_days = int(prefs["days"])
    budget_mult = {"Budget": 0.7, "Moderate": 1.0, "Luxury": 1.6}[prefs["budget"]]
    city = DEMO_CITY_DATA.get(key)
    days = []
    if city:
        currency, country = city["currency"], city["country"]
        areas = city["areas"]
        used: set[str] = set()
        for i in range(n_days):
            area = areas[i % len(areas)]
            acts = []
            for slot in SLOTS:
                name, desc, cost, hours, cat = _pick_slot(area["slots"][slot], rng, used)
                used.add(name)
                acts.append(_activity(name, desc, cost * budget_mult, hours, cat, slot, area["name"], area["lat"], area["lng"], rng))
            days.append({"day": i + 1, "theme": area["theme"], "area": area["name"], "activities": acts})
        overview, tips = city["overview"], city["tips"]
    else:
        lat0, lng0, currency, country = CITY_COORDS.get(key, (20.0, 77.0, "USD", "your destination"))
        if currency == "USD" and key not in CITY_COORDS:
            country = "your destination"
        rate = 1 / USD_PER_UNIT.get(currency, 1.0)
        vibe_slots = GENERIC_SLOTS[prefs["vibe"]]
        used = set()
        for i in range(n_days):
            aname, dlat, dlng, theme = GENERIC_AREAS[i % len(GENERIC_AREAS)]
            acts = []
            for slot in SLOTS:
                name, desc, usd_cost, hours, cat = _pick_slot(vibe_slots[slot], rng, used)
                used.add(name)
                name = name.replace("{dest}", dest.title())
                acts.append(_activity(name, desc, round(usd_cost * rate * budget_mult, 2), hours, cat, slot, aname, lat0 + dlat, lng0 + dlng, rng))
            days.append({"day": i + 1, "theme": theme, "area": aname, "activities": acts})
        overview = (f"A {n_days}-day {prefs['vibe'].lower()} itinerary for {dest.title()} built in Demo mode: each day is anchored to one "
                    f"district so you spend time exploring, not commuting. Add a Gemini/Groq key for a fully bespoke plan.")
        tips = ["Keep a digital copy of your passport/ID", "Learn 5 local phrases - it changes how people treat you",
                "Carry small notes for markets and taxis", "Confirm opening days of museums; many close one weekday"]
    if prefs["pace"] == "Relaxed":
        for d in days:
            d["activities"][2]["duration_hours"] = max(1.5, d["activities"][2]["duration_hours"] - 1)
    emergency = dict(EMERGENCY_DEFAULTS.get(country, EMERGENCY_GENERIC))
    emergency["embassy_note"] = ("Not applicable - domestic travel. Keep the state tourism helpline handy."
                                 if country == "India" else f"Locate the Embassy/Consulate of India in {country} before departure (mea.gov.in).")
    return {
        "destination": dest.title() if not city else dest.title(), "country": country, "currency_code": currency,
        "overview": overview, "days": days, "emergency": emergency,
        "packing": PACKING_BY_VIBE[prefs["vibe"]], "tips": tips,
    }


SWAP_RULES = [
    (("vegetarian", "veg ", "vegan", "plant"), "Lunch Recommendation", ("Vegetarian / plant-based lunch spot in {area}", "Locally loved vegetarian kitchen - thalis, bowls and fresh juices.", "Food", 0.8)),
    (("market", "bazaar", "souk"), "Afternoon Leisure", ("Local market exploration in {area}", "Open-air market: crafts, produce, street snacks and people-watching.", "Shopping", 0.6)),
    (("outdoor", "park", "garden", "nature", "walk"), "Afternoon Leisure", ("Outdoor afternoon: park & scenic walk in {area}", "Trade the indoors for green space and a slow walk.", "Nature", 0.2)),
    (("museum", "gallery", "art"), "Afternoon Leisure", ("Museum / gallery visit in {area}", "The district's best collection - cool, calm and curated.", "Art & Museums", 0.9)),
    (("beach", "swim", "sea"), "Afternoon Leisure", ("Beach afternoon near {area}", "Swim, sunbathe, and a cold drink from the nearest kiosk.", "Nature", 0.3)),
    (("nightlife", "bar", "club", "party", "drinks"), "Evening Dining & Entertainment", ("Dinner + nightlife crawl in {area}", "Early dinner, then the district's best bars and live-music spots.", "Nightlife", 1.3)),
    (("adventure", "trek", "hike", "kayak", "surf", "zipline"), "Afternoon Leisure", ("Adventure activity near {area}", "Guided outdoor adventure - book the earliest slot for best conditions.", "Adventure", 1.4)),
    (("spa", "massage", "wellness", "yoga"), "Afternoon Leisure", ("Spa & wellness afternoon in {area}", "Massage, steam and a slow recovery hour.", "Wellness", 1.2)),
    (("shopping", "shop", "boutique"), "Afternoon Leisure", ("Boutique & design shopping in {area}", "Independent stores and local designers.", "Shopping", 1.0)),
    (("food", "street food", "foodie"), "Evening Dining & Entertainment", ("Street-food trail through {area}", "Five small stops, one great evening.", "Food", 0.7)),
]


def demo_regenerate_day(prefs: dict, plan: dict, day_idx: int, instruction: str) -> dict:
    """Keyword-driven offline rewrite of a single day that preserves the area cluster."""
    rng = random.Random(prefs_seed(prefs) + day_idx * 97 + len(instruction))
    day = json.loads(json.dumps(plan["days"][day_idx]))
    text = instruction.lower()
    area = day["area"]
    changed = False
    base_cost = max([a["cost_local"] for a in day["activities"]] + [1.0])
    for keywords, slot, (name_tpl, desc, cat, cost_factor) in SWAP_RULES:
        if any(k in text for k in keywords):
            idx = SLOTS.index(slot)
            old = day["activities"][idx]
            day["activities"][idx] = {
                **old, "name": name_tpl.format(area=area), "description": desc, "category": cat,
                "cost_local": round(base_cost * cost_factor, 2), "duration_hours": old["duration_hours"],
            }
            changed = True
    if any(k in text for k in ("relax", "slow", "chill", "easy", "rest")):
        for a in day["activities"]:
            a["duration_hours"] = round(max(1.0, a["duration_hours"] * 0.75), 1)
        day["theme"] = f"{day['theme']} (relaxed)"
        changed = True
    if any(k in text for k in ("cheap", "cost", "budget", "save", "affordable")):
        for a in day["activities"]:
            a["cost_local"] = round(a["cost_local"] * 0.6, 2)
        day["theme"] = f"{day['theme']} (budget-friendly)"
        changed = True
    if not changed:
        # Generic refresh: pull the alternative option for 2 random slots, if the city catalog exists.
        city = DEMO_CITY_DATA.get(plan["destination"].lower())
        swapped = 0
        if city:
            area_data = next((a for a in city["areas"] if a["name"] == area), None)
            if area_data:
                for slot in rng.sample(SLOTS, 2):
                    options = [o for o in area_data["slots"][slot] if o[0] != day["activities"][SLOTS.index(slot)]["name"]]
                    if options:
                        name, desc, cost, hours, cat = rng.choice(options)
                        day["activities"][SLOTS.index(slot)] = _activity(name, desc, cost, hours, cat, slot, area, area_data["lat"], area_data["lng"], rng)
                        swapped += 1
        if not swapped:
            for slot in rng.sample(SLOTS, 2):
                a = day["activities"][SLOTS.index(slot)]
                a["name"] = f"Alternative {slot.split()[0].lower()} pick in {area}"
                a["description"] = f"Regenerated per your note: '{instruction}'. A fresh option in the same neighbourhood."
    day["theme"] = day["theme"] if "(" in day["theme"] else f"{day['theme']} - updated"
    return day


# =============================================================================
# Plan normalisation, clustering and budget maths
# =============================================================================


def normalize_plan(raw: dict, prefs: dict) -> dict:
    currency = str(raw.get("currency_code") or "USD").upper().strip()[:3]
    if currency not in USD_PER_UNIT:
        currency = "USD"
    start = datetime.fromisoformat(prefs["start_date"]).date()
    days = []
    for i, d in enumerate(raw.get("days") or []):
        if not isinstance(d, dict):
            continue
        acts = []
        for j, a in enumerate(d.get("activities") or []):
            if not isinstance(a, dict):
                continue
            acts.append({
                "slot": str(a.get("slot") or SLOTS[min(j, 3)]),
                "name": str(a.get("name") or "Free time"),
                "area": str(a.get("area") or d.get("area") or "City centre"),
                "description": str(a.get("description") or ""),
                "duration_hours": safe_float(a.get("duration_hours"), 2.0),
                "cost_local": max(0.0, safe_float(a.get("cost_local"), 0.0)),
                "category": str(a.get("category") or "General"),
                "lat": safe_coord(a.get("lat")), "lng": safe_coord(a.get("lng")),
            })
        if not acts:
            continue
        areas = Counter(a["area"] for a in acts)
        days.append({
            "day": i + 1, "date": (start + timedelta(days=i)).isoformat(),
            "theme": str(d.get("theme") or f"Day {i + 1}"),
            "area": str(d.get("area") or areas.most_common(1)[0][0]),
            "activities": acts,
        })
    if not days:
        raise ValueError("The plan contained no usable days.")
    em = raw.get("emergency") if isinstance(raw.get("emergency"), dict) else {}
    emergency = {k: str(em.get(k) or EMERGENCY_GENERIC.get(k, "-")) for k in ("police", "ambulance", "fire", "tourist_helpline")}
    emergency["embassy_note"] = str(em.get("embassy_note") or "Locate the nearest Indian embassy/consulate before departure (mea.gov.in).")
    return {
        "destination": str(raw.get("destination") or prefs.get("destination") or "Destination"),
        "country": str(raw.get("country") or ""),
        "currency_code": currency,
        "overview": str(raw.get("overview") or ""),
        "days": days,
        "emergency": emergency,
        "packing": [str(x) for x in (raw.get("packing") or PACKING_BY_VIBE[prefs["vibe"]])][:12],
        "tips": [str(x) for x in (raw.get("tips") or [])][:8],
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "prefs": prefs,
    }


def _coords(day: dict):
    return [(a["lat"], a["lng"]) for a in day["activities"] if a.get("lat") is not None and a.get("lng") is not None]


def day_transit_km(day: dict):
    pts = _coords(day)
    if len(pts) < 2:
        return None
    return sum(haversine_km(*pts[i], *pts[i + 1]) for i in range(len(pts) - 1))


def _centroid(day: dict):
    pts = _coords(day)
    if not pts:
        return None
    return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)


def optimize_clusters(plan: dict) -> tuple[dict, float, float]:
    """Greedy same-slot swaps between days when it brings each activity closer to its day's centroid.
    Returns (plan, total_km_before, total_km_after)."""
    days = plan["days"]
    before = sum(day_transit_km(d) or 0.0 for d in days)
    improved = True
    passes = 0
    while improved and passes < 4:
        improved = False
        passes += 1
        for i in range(len(days)):
            for j in range(i + 1, len(days)):
                ci, cj = _centroid(days[i]), _centroid(days[j])
                if not ci or not cj:
                    continue
                for slot_idx in range(min(len(days[i]["activities"]), len(days[j]["activities"]))):
                    ai, aj = days[i]["activities"][slot_idx], days[j]["activities"][slot_idx]
                    if ai["slot"] != aj["slot"] or ai["lat"] is None or aj["lat"] is None:
                        continue
                    cur = haversine_km(ai["lat"], ai["lng"], *ci) + haversine_km(aj["lat"], aj["lng"], *cj)
                    alt = haversine_km(aj["lat"], aj["lng"], *ci) + haversine_km(ai["lat"], ai["lng"], *cj)
                    if alt + 0.5 < cur:  # only swap for a meaningful gain
                        days[i]["activities"][slot_idx], days[j]["activities"][slot_idx] = aj, ai
                        improved = True
                        ci, cj = _centroid(days[i]), _centroid(days[j])
    for d in days:
        areas = Counter(a["area"] for a in d["activities"])
        d["area"] = areas.most_common(1)[0][0]
    after = sum(day_transit_km(d) or 0.0 for d in days)
    return plan, before, after


def transit_badge(km):
    if km is None:
        return "No coordinates", "badge-warn"
    if km <= 8:
        return f"Low transit · {km:.1f} km", "badge-good"
    if km <= 20:
        return f"Moderate transit · {km:.1f} km", "badge-warn"
    return f"High transit · {km:.1f} km", "badge-bad"


def budget_frame(plan: dict) -> pd.DataFrame:
    cur = plan["currency_code"]
    rows = []
    cum_usd = cum_inr = cum_local = 0.0
    for d in plan["days"]:
        local = sum(a["cost_local"] for a in d["activities"])
        usd, inr = to_usd(local, cur), to_inr(local, cur)
        cum_local += local
        cum_usd += usd
        cum_inr += inr
        rows.append({"Day": d["day"], "Date": d["date"], "Area": d["area"], f"Local ({cur})": round(local, 2),
                     "Spend (USD)": round(usd, 2), "Spend (INR)": round(inr, 0),
                     "Cumulative (USD)": round(cum_usd, 2), "Cumulative (INR)": round(cum_inr, 0)})
    return pd.DataFrame(rows)


# =============================================================================
# SQLite persistence (simulated DB - zero external dependencies)
# =============================================================================


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS trips (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            destination TEXT,
            days INTEGER,
            budget TEXT,
            prefs_json TEXT NOT NULL,
            plan_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL)""")


def save_trip(name: str, prefs: dict, plan: dict, trip_id: int | None = None) -> int:
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        if trip_id:
            conn.execute("UPDATE trips SET name=?, destination=?, days=?, budget=?, prefs_json=?, plan_json=?, updated_at=? WHERE id=?",
                         (name, plan["destination"], len(plan["days"]), prefs["budget"], json.dumps(prefs), json.dumps(plan), now, trip_id))
            return trip_id
        cur = conn.execute("INSERT INTO trips (name, destination, days, budget, prefs_json, plan_json, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
                           (name, plan["destination"], len(plan["days"]), prefs["budget"], json.dumps(prefs), json.dumps(plan), now, now))
        return int(cur.lastrowid)


def list_trips() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT id, name, destination, days, budget, created_at, updated_at FROM trips ORDER BY updated_at DESC").fetchall()
    return [dict(r) for r in rows]


def load_trip(trip_id: int) -> tuple[dict, dict] | None:
    with get_conn() as conn:
        row = conn.execute("SELECT prefs_json, plan_json FROM trips WHERE id=?", (trip_id,)).fetchone()
    if not row:
        return None
    return json.loads(row["prefs_json"]), json.loads(row["plan_json"])


def delete_trip(trip_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM trips WHERE id=?", (trip_id,))


# =============================================================================
# PDF export (ReportLab)
# =============================================================================

TEAL = colors.HexColor("#0F5C5C")
CORAL = colors.HexColor("#FF6B5B")
SAND = colors.HexColor("#FBF5EC")
MIST = colors.HexColor("#E6F0F2")
INK = colors.HexColor("#1E2A32")


def pdf_safe(text: Any) -> str:
    """Standard PDF fonts only cover Latin-1; strip anything else and escape XML."""
    s = str(text if text is not None else "")
    s = s.replace("₹", "INR ").replace("–", "-").replace("—", "-").replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = "".join(ch for ch in s if ord(ch) < 256)
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_pdf(plan: dict, prefs: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
                            title=f"{plan['destination']} itinerary", author=APP_NAME)
    ss = getSampleStyleSheet()
    h_title = ParagraphStyle("t", parent=ss["Title"], fontName="Helvetica-Bold", fontSize=24, textColor=TEAL, alignment=TA_CENTER, spaceAfter=4)
    h_sub = ParagraphStyle("s", parent=ss["Normal"], fontSize=10.5, textColor=colors.HexColor("#5B6B74"), alignment=TA_CENTER, spaceAfter=14)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontName="Helvetica-Bold", fontSize=14, textColor=TEAL, spaceBefore=12, spaceAfter=6)
    h3 = ParagraphStyle("h3", parent=ss["Heading3"], fontName="Helvetica-Bold", fontSize=11.5, textColor=INK, spaceBefore=10, spaceAfter=4)
    body = ParagraphStyle("b", parent=ss["Normal"], fontSize=9.5, leading=13, textColor=INK)
    small = ParagraphStyle("sm", parent=body, fontSize=8.5, leading=11.5)
    cell = ParagraphStyle("c", parent=body, fontSize=8.5, leading=11)
    cur = plan["currency_code"]
    story = []

    start = datetime.fromisoformat(prefs["start_date"]).date()
    end = start + timedelta(days=len(plan["days"]) - 1)
    story.append(Paragraph(pdf_safe(f"{plan['destination']}{', ' + plan['country'] if plan['country'] else ''}"), h_title))
    story.append(Paragraph(pdf_safe(f"{len(plan['days'])}-day {prefs['vibe']} itinerary · {start.strftime('%d %b %Y')} - {end.strftime('%d %b %Y')} · "
                                    f"{prefs['party']} · {prefs['pace']} pace · {prefs['budget']} budget"), h_sub))
    if plan.get("overview"):
        story.append(Paragraph(pdf_safe(plan["overview"]), body))
    story.append(Spacer(1, 6))

    # Budget summary table
    bf = budget_frame(plan)
    total_local = float(bf[f"Local ({cur})"].sum())
    # second converted column: INR for foreign trips, USD when the trip is already in INR
    alt_label = "USD" if cur == "INR" else "INR"
    alt = (lambda v: to_usd(v, cur)) if cur == "INR" else (lambda v: to_inr(v, cur))
    data = [["Total estimated spend", f"{cur} {total_local:,.0f}", f"{alt_label} {alt(total_local):,.0f}",
             f"per day ~ {cur} {total_local / max(1, len(plan['days'])):,.0f}"]]
    t = Table(data, colWidths=[62 * mm, 36 * mm, 36 * mm, 40 * mm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), SAND), ("TEXTCOLOR", (0, 0), (-1, -1), INK),
                           ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 9.5),
                           ("BOX", (0, 0), (-1, -1), 0.6, TEAL), ("PADDING", (0, 0), (-1, -1), 6)]))
    story.append(t)
    story.append(Paragraph(pdf_safe(f"Costs are per person estimates in {cur}; USD/INR converted at approximate rates (1 USD = {INR_PER_USD:.0f} INR)."), small))

    # Days
    story.append(Paragraph("Day-by-day plan", h2))
    for d in plan["days"]:
        d_date = datetime.fromisoformat(d["date"]).strftime("%a, %d %b")
        km = day_transit_km(d)
        km_txt = f" · approx. {km:.1f} km of transit" if km is not None else ""
        block = [Paragraph(pdf_safe(f"Day {d['day']} · {d_date} · {d['theme']}"), h3),
                 Paragraph(pdf_safe(f"Area: {d['area']}{km_txt}"), small), Spacer(1, 3)]
        rows = [[Paragraph("<b>Slot</b>", cell), Paragraph("<b>Activity</b>", cell), Paragraph("<b>Hrs</b>", cell),
                 Paragraph(f"<b>Cost ({cur})</b>", cell), Paragraph(f"<b>{alt_label}</b>", cell)]]
        day_total = 0.0
        for a in d["activities"]:
            day_total += a["cost_local"]
            rows.append([Paragraph(pdf_safe(a["slot"]), cell),
                         Paragraph(f"<b>{pdf_safe(a['name'])}</b><br/>{pdf_safe(a['description'])}", cell),
                         Paragraph(f"{a['duration_hours']:g}", cell),
                         Paragraph(f"{a['cost_local']:,.0f}", cell),
                         Paragraph(f"{alt(a['cost_local']):,.0f}", cell)])
        rows.append(["", Paragraph("<b>Day total</b>", cell), "", Paragraph(f"<b>{day_total:,.0f}</b>", cell),
                     Paragraph(f"<b>{alt(day_total):,.0f}</b>", cell)])
        tbl = Table(rows, colWidths=[30 * mm, 92 * mm, 12 * mm, 22 * mm, 22 * mm], repeatRows=1)
        tbl.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), MIST), ("LINEBELOW", (0, 0), (-1, 0), 0.6, TEAL),
                                 ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#FAFCFC")]),
                                 ("BACKGROUND", (0, -1), (-1, -1), SAND), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                 ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D5E0E3")), ("PADDING", (0, 0), (-1, -1), 4)]))
        block.append(tbl)
        story.append(KeepTogether(block))

    # Emergency + checklists
    story.append(PageBreak())
    story.append(Paragraph("Emergency contact checklist", h2))
    em = plan["emergency"]
    checklist = [
        f"Police: {em.get('police', '-')}", f"Ambulance: {em.get('ambulance', '-')}", f"Fire: {em.get('fire', '-')}",
        f"Tourist helpline: {em.get('tourist_helpline', '-')}", f"Embassy / consulate: {em.get('embassy_note', '-')}",
        "Hotel name, address & phone: ____________________________________",
        "Travel insurance provider & policy no.: __________________________",
        "Emergency contact back home: ____________________________________",
        "Passport / ID photocopies packed (and a photo on your phone)",
        "Bank card hotline saved; cards enabled for international use",
        "Blood group & allergies noted for each traveller: ________________",
    ]
    for item in checklist:
        story.append(Paragraph(pdf_safe(f"[  ]  {item}"), body))
    story.append(Paragraph("Packing checklist", h2))
    for item in plan.get("packing", []):
        story.append(Paragraph(pdf_safe(f"[  ]  {item}"), body))
    if plan.get("tips"):
        story.append(Paragraph("Local tips", h2))
        for tip in plan["tips"]:
            story.append(Paragraph(pdf_safe(f"• {tip}"), body))
    story.append(Spacer(1, 14))
    story.append(Paragraph(pdf_safe(f"Generated by {APP_NAME} on {datetime.now().strftime('%d %b %Y, %H:%M')}. Verify opening hours and prices before you go."), small))

    def _footer(canvas, doc_):
        canvas.saveState()
        canvas.setStrokeColor(CORAL)
        canvas.setLineWidth(1.2)
        canvas.line(16 * mm, 11 * mm, A4[0] - 16 * mm, 11 * mm)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#5B6B74"))
        canvas.drawString(16 * mm, 7 * mm, pdf_safe(f"{plan['destination']} · offline travel guide"))
        canvas.drawRightString(A4[0] - 16 * mm, 7 * mm, f"Page {doc_.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()


# =============================================================================
# Generation orchestration (live vs demo)
# =============================================================================


def generate_recommendations(prefs: dict) -> list[dict]:
    if is_demo():
        raw = demo_recommendations(prefs)
    else:
        raw = llm_json(recommendation_prompt(prefs), temperature=0.8)
    recs = raw.get("recommendations") if isinstance(raw, dict) else raw
    if not isinstance(recs, list) or not recs:
        raise ValueError("No recommendations were returned.")
    cleaned = []
    for r in recs[:3]:
        cleaned.append({
            "city": str(r.get("city", "?")), "country": str(r.get("country", "")),
            "match_score": int(safe_float(r.get("match_score"), 80)), "why": str(r.get("why", "")),
            "weather_in_month": str(r.get("weather_in_month", "")), "best_season": str(r.get("best_season", "")),
            "estimated_daily_cost_usd": safe_float(r.get("estimated_daily_cost_usd"), 0),
            "currency_code": str(r.get("currency_code", "USD")).upper()[:3],
            "highlights": [str(h) for h in (r.get("highlights") or [])][:6],
            "tags": [str(t) for t in (r.get("tags") or [])][:6],
        })
    return cleaned


def llm_json(prompt: str, temperature: float) -> Any:
    """Call the live model and parse JSON, retrying once with a stricter nudge if the output was malformed."""
    try:
        return extract_json(call_llm(prompt, temperature=temperature))
    except (ValueError, json.JSONDecodeError):
        strict = prompt + "\n\nIMPORTANT: Your previous answer was not valid JSON. Keep descriptions short and return compact, complete, valid JSON only."
        return extract_json(call_llm(strict, temperature=max(0.2, temperature - 0.3)))


def generate_itinerary(prefs: dict) -> dict:
    if is_demo():
        raw = demo_itinerary(prefs)
    else:
        raw = llm_json(itinerary_prompt(prefs), temperature=0.7)
    plan = normalize_plan(raw, prefs)
    plan, before, after = optimize_clusters(plan)
    plan["cluster_report"] = {"km_before": round(before, 1), "km_after": round(after, 1)}
    return plan


def regenerate_day(prefs: dict, plan: dict, day_idx: int, instruction: str) -> dict:
    if is_demo():
        raw_day = demo_regenerate_day(prefs, plan, day_idx, instruction)
    else:
        raw_day = llm_json(regenerate_day_prompt(prefs, plan, day_idx, instruction), temperature=0.8)
        if isinstance(raw_day, dict) and "days" in raw_day and isinstance(raw_day["days"], list) and raw_day["days"]:
            raw_day = raw_day["days"][0]
    tmp = normalize_plan({**plan, "days": [raw_day]}, prefs)
    new_day = tmp["days"][0]
    old_day = plan["days"][day_idx]
    new_day["day"], new_day["date"] = old_day["day"], old_day["date"]
    new_plan = json.loads(json.dumps(plan))
    new_plan["days"][day_idx] = new_day
    new_plan["last_swap"] = {"day": old_day["day"], "instruction": instruction, "at": datetime.now().isoformat(timespec="seconds")}
    return new_plan


# =============================================================================
# UI
# =============================================================================

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600;700&family=Inter:wght@400;500;600&display=swap');
:root { --teal:#0F5C5C; --teal-2:#1D8A8A; --coral:#FF6B5B; --sand:#FBF5EC; --ink:#1E2A32; --mist:#E6F0F2; --muted:#5B6B74; }
.stApp, .stApp p, .stApp li, .stApp label, .stApp input, .stApp textarea, .stApp h1, .stApp h2, .stApp h3, .stApp .stMarkdown { font-family: 'Inter', -apple-system, sans-serif; }
/* keep Streamlit's icon ligature fonts intact */
.stApp [data-testid*="Icon"], .stApp [data-testid*="icon"], .stApp span[class*="material-symbols"] { font-family: 'Material Symbols Rounded' !important; }
.hero { background: linear-gradient(120deg, #0F5C5C 0%, #1D8A8A 55%, #FF8A70 100%); border-radius: 18px;
        padding: 26px 30px; color: #fff; margin-bottom: 14px; box-shadow: 0 12px 32px rgba(15,92,92,.22); }
.hero h1 { font-family: 'Playfair Display', serif; font-size: 2.05rem; margin: 0 0 4px 0; color:#fff; letter-spacing:.2px; }
.hero p { margin: 0; opacity: .94; font-size: .98rem; }
.chip { display:inline-block; padding: 4px 11px; border-radius: 999px; background: rgba(255,255,255,.18);
        margin: 8px 6px 0 0; font-size: .78rem; font-weight: 500; border: 1px solid rgba(255,255,255,.28); }
.card { background: #fff; border-radius: 14px; padding: 18px 20px; border: 1px solid #E8EEF0;
        box-shadow: 0 6px 18px rgba(30,42,50,.06); margin-bottom: 14px; }
.card h3 { font-family: 'Playfair Display', serif; color: var(--teal); margin: 0 0 4px 0; font-size: 1.25rem; }
.card .score { float:right; background: var(--teal); color:#fff; border-radius: 999px; padding: 3px 10px; font-size:.8rem; font-weight:600; }
.tag { display:inline-block; background: var(--mist); color: var(--teal); padding: 3px 10px; border-radius: 999px;
       font-size: .76rem; margin: 4px 4px 0 0; font-weight: 500; }
.badge { display:inline-block; padding: 3px 10px; border-radius: 999px; font-size:.74rem; font-weight:600; margin-left:6px; }
.badge-good { background:#E3F7EA; color:#1B7F3B; } .badge-warn { background:#FFF3DB; color:#9A6400; } .badge-bad { background:#FDE4E1; color:#B3261E; }
.slot { font-size:.72rem; letter-spacing:.07em; text-transform:uppercase; color: var(--muted); font-weight:600; }
.act-name { font-weight:600; color: var(--ink); font-size: 1.02rem; margin: 2px 0; }
.act-desc { color:#3E4C55; font-size:.9rem; }
.act-meta { color: var(--muted); font-size:.8rem; margin-top: 2px; }
.cost { color: var(--coral); font-weight:700; font-size:1.02rem; text-align:right; }
.cost-sub { color: var(--muted); font-size:.78rem; text-align:right; }
.muted { color: var(--muted); font-size:.86rem; }
.day-total { background: var(--sand); border-radius: 10px; padding: 8px 14px; font-weight: 600; color: var(--ink); margin-top: 6px; }
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button { border-radius: 10px; font-weight: 600; }
div[data-testid="stMetric"] { background: #fff; border: 1px solid #E8EEF0; border-radius: 12px; padding: 10px 14px; }
.footer { color: var(--muted); font-size:.8rem; text-align:center; margin-top: 28px; }
</style>
"""


def init_state() -> None:
    defaults = {
        "provider": "Demo", "api_key": "", "model": GEMINI_MODELS[0],
        "prefs": None, "recommendations": None, "plan": None, "current_trip_id": None,
        "swap_instruction": "", "pending_destination": None,
    }
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)


def sidebar() -> None:
    with st.sidebar:
        st.markdown("### ⚙️ Configuration")
        provider = st.selectbox("AI provider", ["Demo (no API key)", "Gemini", "Groq"],
                                help="Demo mode runs fully offline with curated data. Add a key for live AI planning.")
        provider = provider.split(" ")[0]
        st.session_state.provider = provider
        if provider != "Demo":
            default_key = ""
            try:
                default_key = st.secrets.get(f"{provider.upper()}_API_KEY", "")
            except Exception:
                default_key = ""
            key = st.text_input(f"{provider} API key", value=default_key, type="password",
                                help="Stored only in this browser session - never written to disk.")
            st.session_state.api_key = key.strip()
            models = GEMINI_MODELS if provider == "Gemini" else GROQ_MODELS
            choice = st.selectbox("Model", models + ["Custom..."])
            if choice == "Custom...":
                choice = st.text_input("Custom model id", value=models[0])
            st.session_state.model = choice.strip()
            if not key:
                st.info("No key yet - the app will stay in Demo mode until you add one.")
            elif st.button("Test connection"):
                try:
                    out = call_llm('Reply with the JSON {"status":"ok"}', temperature=0.0)
                    st.success(f"Connected · {out.strip()[:60]}")
                except Exception as exc:  # noqa: BLE001
                    st.error(str(exc))
        else:
            st.session_state.api_key = ""
            st.caption("Demo mode: curated, geographically clustered sample plans for Goa, Jaipur, Bali, Paris, Tokyo, Dubai and a smart template for any other city.")

        st.markdown("---")
        st.markdown("### 🧳 Trip preferences")
        with st.form("prefs_form"):
            destination = st.text_input("Destination (leave blank for recommendations)",
                                        value=st.session_state.pending_destination or (st.session_state.prefs or {}).get("destination", ""),
                                        placeholder="e.g. Goa, Bali, Paris")
            vibe = st.selectbox("Travel vibe", VIBES, index=VIBES.index((st.session_state.prefs or {}).get("vibe", "Beach")))
            days = st.slider("Trip duration (days)", 1, 14, int((st.session_state.prefs or {}).get("days", 4)))
            start_date = st.date_input("Start date", value=date.today() + timedelta(days=14))
            budget = st.select_slider("Budget level", BUDGET_LEVELS, value=(st.session_state.prefs or {}).get("budget", "Moderate"))
            party = st.selectbox("Travel party", PARTIES, index=PARTIES.index((st.session_state.prefs or {}).get("party", "Couple")))
            pace = st.select_slider("Pace", PACES, value=(st.session_state.prefs or {}).get("pace", "Moderate"))
            interests = st.multiselect("Interests", INTERESTS, default=(st.session_state.prefs or {}).get("interests", ["Food", "History"]))
            submitted = st.form_submit_button("Save preferences", type="primary")
        if submitted:
            st.session_state.prefs = {
                "destination": destination.strip(), "vibe": vibe, "days": int(days), "start_date": start_date.isoformat(),
                "budget": budget, "party": party, "pace": pace, "interests": interests,
            }
            st.session_state.pending_destination = None
            st.toast("Preferences saved ✅")
        st.markdown("---")
        st.caption("Skill Wallet Capstone · Project 4 · Streamlit + Gemini/Groq + SQLite + ReportLab")


def hero() -> None:
    prefs = st.session_state.prefs
    mode = "Demo mode" if is_demo() else f"{st.session_state.provider} · {st.session_state.model}"
    chips = [mode]
    if prefs:
        chips += [prefs["destination"] or "Destination: open", f"{prefs['days']} days", prefs["vibe"], prefs["budget"], prefs["party"], prefs["pace"]]
    st.markdown(
        f"""<div class="hero"><h1>🧭 {APP_NAME}</h1>
        <p>AI-optimised day-by-day itineraries · geographic clustering to kill transit fatigue · vibe-based destination picks · offline PDF guides</p>
        {''.join(f'<span class="chip">{c}</span>' for c in chips)}</div>""", unsafe_allow_html=True)


def need_prefs() -> bool:
    if not st.session_state.prefs:
        st.info("👈 Start by filling in your trip preferences in the sidebar and clicking **Save preferences**.")
        return True
    return False


def tab_recommender() -> None:
    st.subheader("Smart Destination Recommender")
    st.markdown('<p class="muted">No fixed destination? Get the top 3 cities matching your vibe, budget, season and interests.</p>', unsafe_allow_html=True)
    if need_prefs():
        return
    prefs = st.session_state.prefs
    if prefs["destination"]:
        st.caption(f"You already chose **{prefs['destination']}** - recommendations are still available if you want to compare.")
    if st.button("✨ Recommend destinations", type="primary"):
        with st.spinner("Matching vibes, seasons and budgets..."):
            try:
                st.session_state.recommendations = generate_recommendations(prefs)
            except (LLMError, ValueError, json.JSONDecodeError) as exc:
                st.error(f"Could not get recommendations: {exc}")
    recs = st.session_state.recommendations
    if not recs:
        return
    cols = st.columns(len(recs))
    for col, r in zip(cols, recs):
        with col:
            daily_inr = r["estimated_daily_cost_usd"] * INR_PER_USD
            st.markdown(
                f"""<div class="card"><span class="score">{r['match_score']}% match</span>
                <h3>{r['city']}</h3><div class="muted">{r['country']}</div>
                <p style="margin:8px 0 6px 0">{r['why']}</p>
                <div class="muted">🌤️ {r['weather_in_month']} · best: {r['best_season']}</div>
                <div class="muted">💸 ~${r['estimated_daily_cost_usd']:.0f}/day (≈ ₹{daily_inr:,.0f})</div>
                <div style="margin-top:8px">{''.join(f'<span class="tag">{t}</span>' for t in r['tags'])}</div>
                <ul style="margin:10px 0 0 16px;padding:0;font-size:.88rem">{''.join(f'<li>{h}</li>' for h in r['highlights'])}</ul>
                </div>""", unsafe_allow_html=True)
            if st.button(f"Use {r['city']}", key=f"use_{r['city']}"):
                st.session_state.prefs = {**prefs, "destination": r["city"]}
                st.session_state.pending_destination = r["city"]
                st.session_state.plan = None
                st.toast(f"Destination set to {r['city']} - head to the Itinerary tab.")
                st.rerun()


def render_day(d: dict, cur: str, expanded: bool = False) -> None:
    km = day_transit_km(d)
    label, cls = transit_badge(km)
    d_date = datetime.fromisoformat(d["date"]).strftime("%a, %d %b")
    day_total = sum(a["cost_local"] for a in d["activities"])
    with st.expander(f"Day {d['day']} · {d_date} · {d['theme']}", expanded=expanded):
        st.markdown(f'<span class="muted">📍 Cluster: <b>{d["area"]}</b></span><span class="badge {cls}">{label}</span>', unsafe_allow_html=True)
        for a in d["activities"]:
            c1, c2 = st.columns([5, 1.3])
            with c1:
                st.markdown(
                    f"""<div class="slot">{a['slot']}</div><div class="act-name">{a['name']}</div>
                    <div class="act-desc">{a['description']}</div>
                    <div class="act-meta">📍 {a['area']} · ⏱ {a['duration_hours']:g} h · {a['category']}</div>""", unsafe_allow_html=True)
            with c2:
                st.markdown(f"""<div class="cost">{fmt_money(a['cost_local'], cur)}</div>
                            <div class="cost-sub">≈ {conv_text(a['cost_local'], cur)}</div>""", unsafe_allow_html=True)
            st.markdown("<hr style='margin:6px 0;border:none;border-top:1px solid #EEF2F4'>", unsafe_allow_html=True)
        st.markdown(f'<div class="day-total">Day total: {fmt_money(day_total, cur)} · ≈ {conv_text(day_total, cur)}</div>', unsafe_allow_html=True)


def conv_text(amount: float, cur: str) -> str:
    """'₹1,200 · $14' for foreign currencies, just '$14' when the local currency is already INR."""
    usd = f"${to_usd(amount, cur):,.0f}"
    return usd if cur == "INR" else f"₹{to_inr(amount, cur):,.0f} · {usd}"


def tab_itinerary() -> None:
    st.subheader("Day-by-Day Optimized Itinerary")
    st.markdown('<p class="muted">Sequential time slots per day, attractions grouped by neighbourhood, itemised costs with a live USD/INR budget tracker.</p>', unsafe_allow_html=True)
    if need_prefs():
        return
    prefs = st.session_state.prefs
    if not prefs["destination"]:
        st.warning("No destination set. Pick one in the sidebar or use the **Destination Recommender** tab first.")
        return
    c1, c2 = st.columns([1, 3])
    with c1:
        if st.button("🗺️ Generate itinerary", type="primary"):
            with st.spinner(f"Planning {prefs['days']} days in {prefs['destination']}..."):
                try:
                    st.session_state.plan = generate_itinerary(prefs)
                    st.session_state.current_trip_id = None
                except (LLMError, ValueError, json.JSONDecodeError) as exc:
                    st.error(f"Generation failed: {exc}")
    with c2:
        if st.session_state.plan:
            st.caption(f"Plan for **{st.session_state.plan['destination']}** generated {st.session_state.plan.get('generated_at', '')}. "
                       f"Change preferences and regenerate any time.")
    plan = st.session_state.plan
    if not plan:
        return
    cur = plan["currency_code"]
    if plan.get("overview"):
        st.markdown(f'<div class="card">{plan["overview"]}</div>', unsafe_allow_html=True)

    # Budget tracker
    bf = budget_frame(plan)
    total_local = float(bf[f"Local ({cur})"].sum())
    total_usd, total_inr = to_usd(total_local, cur), to_inr(total_local, cur)
    cap_usd = DAILY_BUDGET_USD[prefs["budget"]] * len(plan["days"])
    ratio = total_usd / cap_usd if cap_usd else 0
    m1, m2, m3, m4 = st.columns(4)
    if cur == "INR":
        m1.metric("Total (INR)", f"₹{total_inr:,.0f}")
        m2.metric("Total (USD)", f"${total_usd:,.0f}")
        m3.metric("Avg per day", f"₹{total_inr / len(plan['days']):,.0f}")
    else:
        m1.metric(f"Total ({cur})", fmt_money(total_local, cur))
        m2.metric("Total (USD)", f"${total_usd:,.0f}")
        m3.metric("Total (INR)", f"₹{total_inr:,.0f}")
    m4.metric(f"vs {prefs['budget']} budget", f"{ratio * 100:.0f}%", delta=f"{'under' if ratio <= 1 else 'over'} by ${abs(cap_usd - total_usd):,.0f}",
              delta_color="normal" if ratio <= 1 else "inverse")
    # '\$' keeps Streamlit's markdown from reading "$a ... $b" as LaTeX
    st.progress(min(1.0, ratio), text=f"Budget used: \\${total_usd:,.0f} of \\${cap_usd:,.0f} target ({prefs['budget']} tier, activities only - excludes flights & stay)")
    cr = plan.get("cluster_report") or {}
    if cr:
        saved = max(0.0, cr.get("km_before", 0) - cr.get("km_after", 0))
        st.caption(f"🧲 Clustering engine: {cr.get('km_after', 0):.1f} km total intra-day transit across the trip"
                   + (f" (route optimiser saved {saved:.1f} km by regrouping nearby activities)" if saved > 0.1 else " - already well grouped."))

    left, right = st.columns([3, 2])
    with left:
        for i, d in enumerate(plan["days"]):
            render_day(d, cur, expanded=(i == 0))
    with right:
        st.markdown("**Running budget tracker**")
        chart = bf.set_index("Day")[["Cumulative (INR)"]]
        st.line_chart(chart, height=220)
        cols = ["Day", "Area", "Spend (INR)", "Spend (USD)", "Cumulative (INR)"] if cur == "INR" else ["Day", "Area", f"Local ({cur})", "Spend (INR)", "Cumulative (INR)"]
        st.dataframe(bf[cols], hide_index=True, height=min(400, 60 + 36 * len(bf)))
        st.markdown("**Local tips**")
        for t in plan.get("tips", [])[:5]:
            st.markdown(f"- {t}")


def tab_customize() -> None:
    st.subheader("Vibe Customization & Dynamic Activity Swap")
    st.markdown('<p class="muted">Tweak one day without touching the rest of your plan. Describe the change in plain English.</p>', unsafe_allow_html=True)
    plan = st.session_state.plan
    if need_prefs():
        return
    if not plan:
        st.info("Generate an itinerary first (Itinerary tab).")
        return
    prefs = st.session_state.prefs
    cur = plan["currency_code"]
    labels = [f"Day {d['day']} · {d['theme']} · {d['area']}" for d in plan["days"]]
    day_idx = st.selectbox("Which day do you want to change?", range(len(labels)), format_func=lambda i: labels[i])
    day = plan["days"][day_idx]
    c1, c2 = st.columns([3, 2])
    with c1:
        render_day(day, cur, expanded=True)
    with c2:
        st.markdown("**Quick swaps**")
        qcols = st.columns(2)
        for i, (label, full) in enumerate(QUICK_SWAPS):
            if qcols[i % 2].button(label, key=f"quick_{i}", help=full):
                st.session_state.swap_instruction = full
        instruction = st.text_area("Your instruction", value=st.session_state.swap_instruction,
                                   placeholder='e.g. "Swap the museum for an outdoor market" or "Find a vegetarian lunch spot"', height=90)
        st.session_state.swap_instruction = instruction
        if st.button(f"🔁 Regenerate Day {day['day']} only", type="primary", disabled=not instruction.strip()):
            with st.spinner(f"Rewriting Day {day['day']}... other {len(plan['days']) - 1} day(s) stay locked."):
                try:
                    st.session_state.plan = regenerate_day(prefs, plan, day_idx, instruction.strip())
                    st.session_state.swap_instruction = ""
                    st.toast(f"Day {day['day']} updated - rest of the plan untouched ✅")
                    st.rerun()
                except (LLMError, ValueError, json.JSONDecodeError) as exc:
                    st.error(f"Could not regenerate the day: {exc}")
        last = plan.get("last_swap")
        if last:
            st.caption(f"Last change: Day {last['day']} · \"{last['instruction']}\" · {last['at']}")
        locked = ", ".join(f"Day {d['day']}" for i, d in enumerate(plan["days"]) if i != day_idx) or "none"
        st.markdown(f'<div class="muted">🔒 Locked: {locked}</div>', unsafe_allow_html=True)


def tab_trips() -> None:
    st.subheader("Trip Management & Offline PDF Export")
    st.markdown('<p class="muted">Save multiple trips to the local SQLite store, reload them later, and export a clean offline PDF guide with an emergency checklist.</p>', unsafe_allow_html=True)
    plan = st.session_state.plan
    prefs = st.session_state.prefs
    c1, c2 = st.columns([1.2, 1])
    with c1:
        st.markdown("**Save current plan**")
        if plan and prefs:
            default_name = f"{plan['destination']} · {len(plan['days'])}-day {prefs['vibe']} trip"
            name = st.text_input("Trip name", value=default_name)
            b1, b2 = st.columns(2)
            if b1.button("💾 Save as new trip", type="primary"):
                tid = save_trip(name.strip() or default_name, prefs, plan)
                st.session_state.current_trip_id = tid
                st.success(f"Saved as trip #{tid}.")
            if st.session_state.current_trip_id and b2.button(f"Update trip #{st.session_state.current_trip_id}"):
                save_trip(name.strip() or default_name, prefs, plan, st.session_state.current_trip_id)
                st.success("Trip updated.")
        else:
            st.info("Generate an itinerary to save it.")
    with c2:
        st.markdown("**Export**")
        if plan and prefs:
            try:
                pdf_bytes = build_pdf(plan, prefs)
                fname = re.sub(r"[^A-Za-z0-9]+", "-", plan["destination"]).strip("-").lower() or "trip"
                st.download_button("📄 Download offline PDF guide", data=pdf_bytes, file_name=f"{fname}-itinerary.pdf", mime="application/pdf", type="primary")
            except Exception as exc:  # noqa: BLE001
                st.error(f"PDF export failed: {exc}")
            st.download_button("🧾 Download plan as JSON", data=json.dumps(plan, indent=2, ensure_ascii=False),
                               file_name=f"{re.sub(r'[^A-Za-z0-9]+', '-', plan['destination']).lower()}-itinerary.json", mime="application/json")
        else:
            st.caption("PDF and JSON export appear once a plan exists.")

    st.markdown("---")
    st.markdown("**Trip history**")
    trips = list_trips()
    if not trips:
        st.caption("No saved trips yet.")
        return
    df = pd.DataFrame(trips)[["id", "name", "destination", "days", "budget", "updated_at"]]
    st.dataframe(df, hide_index=True)
    sel = st.selectbox("Select a trip", trips, format_func=lambda t: f"#{t['id']} · {t['name']} ({t['updated_at'][:16]})")
    a1, a2, _ = st.columns([1, 1, 3])
    if a1.button("📂 Load trip"):
        loaded = load_trip(sel["id"])
        if loaded:
            st.session_state.prefs, st.session_state.plan = loaded
            st.session_state.current_trip_id = sel["id"]
            st.session_state.pending_destination = loaded[0].get("destination")
            st.toast(f"Loaded trip #{sel['id']} ✅")
            st.rerun()
    if a2.button("🗑️ Delete trip"):
        delete_trip(sel["id"])
        if st.session_state.current_trip_id == sel["id"]:
            st.session_state.current_trip_id = None
        st.toast(f"Deleted trip #{sel['id']}")
        st.rerun()


def main() -> None:
    st.set_page_config(page_title=APP_NAME, page_icon="🧭", layout="wide", initial_sidebar_state="expanded")
    st.markdown(CSS, unsafe_allow_html=True)
    init_state()
    init_db()
    sidebar()
    hero()
    t1, t2, t3, t4 = st.tabs(["🌍 Destination Recommender", "🗓️ Itinerary", "🎛️ Customize & Swap", "💾 Trips & PDF Export"])
    with t1:
        tab_recommender()
    with t2:
        tab_itinerary()
    with t3:
        tab_customize()
    with t4:
        tab_trips()
    st.markdown('<div class="footer">Built with Streamlit · Gemini / Groq · SQLite · ReportLab — Skill Wallet Capstone Project 4</div>', unsafe_allow_html=True)


if __name__ == "__main__":
    main()
