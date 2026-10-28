# 🧭 Personalized Travel Itinerary Planner

**Skill Wallet Capstone · Project 4** · Generative AI | Intelligent SaaS Trip Planning
Platform ID: `6ac33976fb8fc7965cd9236d`

A full-stack, AI-powered Streamlit app that turns a short preference form into a day-by-day vacation plan:
attractions are **clustered by neighbourhood** so you never backtrack across a city, every activity is costed in the
local currency with a **running USD/INR budget tracker**, single days can be **re-generated with plain-English
instructions** without touching the rest of the plan, and the whole trip exports as an **offline PDF guide** with an
emergency-contact checklist.

> 🔑 Works with **Gemini** or **Groq** (bring your own key) and ships with a fully offline **Demo mode**, so the hosted
> app runs with zero API keys and zero external databases.

---

## ✨ Features (mapped to the Kanban epics)

| Epic | Module | What it does |
|------|--------|--------------|
| **Epic 3** – Preference capture | Sidebar | Secure API key input (Gemini / Groq) with demo fallback; trip form: destination *or* open-ended vibe (Beach / Mountains / Cultural / Urban), duration, dates, budget level, travel party, pace, interests |
| **Epic 3** – Destination recommender | Tab 1 | Top-3 matching cities scored on vibe, budget, travel-month season and interests, with highlight tags and a one-click "Use this destination" |
| **Epic 4** – Itinerary generator | Tab 2 | Day-wise plan with four sequential slots (Morning Sightseeing → Lunch → Afternoon Leisure → Evening Dining & Entertainment) |
| **Epic 4** – Geographic clustering | Tab 2 | Each day is anchored to one neighbourhood; a haversine-based route optimiser swaps same-slot activities between days when it reduces intra-day transit, and every day shows a *Low / Moderate / High transit* badge with km |
| **Epic 4** – Budget tracker | Tab 2 | Itemised cost per activity in local currency + USD + INR, day totals, cumulative line chart and a budget-health meter against the chosen tier |
| **Epic 4** – Dynamic activity swap | Tab 3 | Quick-swap chips ("Vegetarian lunch", "Museum → outdoor market", "Cut costs"…) or free-text instructions regenerate **one day only**; other days stay locked |
| **Epic 5** – Trip persistence | Tab 4 | Save / update / load / delete multiple trips in a local SQLite store (`trips.db`) with a history viewer |
| **Epic 5** – Offline PDF export | Tab 4 | One-click ReportLab PDF: cover summary, budget table, day tables, emergency-contact checklist, packing list and local tips; JSON export too |

---

## 🛠 Tech stack

- **Python 3.9+**, **Streamlit** (UI + session state)
- **Gemini API** / **Groq API** via REST (`requests`) – no SDK pinning, JSON-mode responses
- **SQLite** (stdlib `sqlite3`) – zero external database dependencies
- **ReportLab** – PDF generation
- **pandas** – budget tables and charts
- Custom "wanderlust" CSS theme (teal / coral / sand)

---

## 🚀 Run locally

```bash
git clone https://github.com/<your-username>/personalized-travel-itinerary-planner.git
cd personalized-travel-itinerary-planner
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Open http://localhost:8501.

**Demo mode** needs nothing else. For live AI planning, pick *Gemini* or *Groq* in the sidebar and paste a key:

- Gemini key → https://aistudio.google.com/app/apikey
- Groq key → https://console.groq.com/keys

Optionally create `.streamlit/secrets.toml` (git-ignored) so the key is pre-filled:

```toml
GEMINI_API_KEY = "..."
GROQ_API_KEY = "..."
```

---

## ☁️ 1-click deployment to Streamlit Community Cloud

1. Push `app.py`, `requirements.txt`, `README.md` and `.streamlit/config.toml` to a **public GitHub repo**.
2. Go to https://share.streamlit.io → **New app**.
3. Select the repo, branch `main`, main file path `app.py` → **Deploy**.
4. (Optional) In *App settings → Secrets* add `GEMINI_API_KEY` / `GROQ_API_KEY` to pre-fill the key for visitors.
   Leaving secrets empty is fine – the app runs in Demo mode and visitors can paste their own key.

Your live URL will look like `https://<app-name>.streamlit.app`.

### Skill Wallet proof registration

- **Step 33 – GitHub Repository Submission:** paste the repository URL.
- **Step 34 – Live Hosted Demo URL Registration:** paste the `https://<app-name>.streamlit.app` URL.

---

## 📁 Project structure

```
.
├── app.py                 # entire application (UI, LLM layer, demo engine, clustering, SQLite, PDF)
├── requirements.txt
├── README.md
├── .streamlit/config.toml # theme + server config
└── .gitignore             # keeps trips.db and secrets out of git
```

`app.py` is organised top-to-bottom as: constants → helpers → LLM layer (Gemini/Groq REST) → prompt templates →
demo-mode engine → plan normalisation, clustering & budget maths → SQLite persistence → PDF builder →
generation orchestration → Streamlit UI (sidebar + 4 tabs).

---

## 🧪 How the clustering works

1. The planner (LLM or demo engine) assigns every activity an `area` and approximate `lat/lng` and is instructed to keep
   each day inside one neighbourhood.
2. `optimize_clusters()` then runs a greedy pass: for every pair of days and every matching slot, it swaps the two
   activities if that brings both closer to their day's centroid (haversine distance, ≥0.5 km gain).
3. Each day re-labels its dominant area and reports total intra-day transit; the UI shows how many km the optimiser saved.

Conversion rates to USD/INR are a static table (`USD_PER_UNIT`, `INR_PER_USD`) so the app has no external API
dependency – update them in `app.py` when needed.

---

## 📄 Licence

MIT – built as a capstone project; verify opening hours, prices and emergency numbers before travelling.
