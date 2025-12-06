# ============================================================
# Gilmer CFB Betting Intelligence Model V4.0
# Engineered by Matthew Gilmer
# ============================================================

import streamlit as st
import requests
import os
import re
import time
import json
import base64
import altair as alt
import pandas as pd
from datetime import datetime
from fpdf import FPDF
from openai import OpenAI

# ============================================================
# STREAMLIT SESSION INITIALIZATION
# ============================================================
if "should_run_pipeline" not in st.session_state:
    st.session_state["should_run_pipeline"] = False

# ============================================================
# API CLIENTS & SECRETS
# ============================================================
# FIXED — correct SDK initialization
client = OpenAI()

ODDS_API_KEY = os.environ.get("ODDS_API_KEY")

# ============================================================
# EXTERNAL ENDPOINTS
# ============================================================
ESPN_SCOREBOARD_URL = (
    "https://site.web.api.espn.com/apis/site/v2/"
    "sports/football/college-football/scoreboard"
)

ODDS_API_URL = (
    "https://api.the-odds-api.com/v4/sports/americanfootball_ncaaf/odds"
    "?regions=us&markets=h2h,spreads,totals&oddsFormat=american"
)

AUTO_REFRESH_INTERVAL_MS = 15000  # Live mode refresh interval (15s)

# ============================================================
# CSS THEME INJECTION (Blue/Gold Elite Sportsbook Theme)
# ============================================================
def inject_css_theme():
    st.markdown("""
    <style>
    body, .main { background-color: #0a0f1f !important; color: #e6e6e6 !important; }
    .gilmer-card {
        background: linear-gradient(180deg, #111827, #0d1529);
        padding: 22px;
        border-radius: 14px;
        border: 1px solid #1A73E8;
        box-shadow: 0 0 18px #1A73E855;
        margin-top: 20px;
        transition: 0.25s;
    }
    .gilmer-card:hover {
        transform: scale(1.02);
        box-shadow: 0 0 26px #D4AF37AA;
        border-color: #D4AF37;
    }
    .gold-text { color: #D4AF37 !important; font-weight: 700; }
    .prob-bar {
        height: 18px; background: #1A73E833; border-radius: 10px;
        overflow: hidden; margin-top: 5px; margin-bottom: 12px;
        border: 1px solid #1A73E8;
    }
    .prob-fill {
        height: 100%;
        background: linear-gradient(90deg, #1A73E8, #D4AF37);
    }
    </style>
    """, unsafe_allow_html=True)

# ============================================================
# FUZZY MATCHING ENGINE
# ============================================================
def normalize_team_name(name):
    if not name: return ""
    name = name.lower().strip()
    return re.sub(r"[^a-z0-9 ]", "", name)

def fuzzy_match_team(user, names):
    u = normalize_team_name(user)
    for n in names:
        if normalize_team_name(n) == u:
            return n
    for n in names:
        if u in normalize_team_name(n):
            return n
    for n in names:
        abbr = "".join([w[0] for w in n.split()])
        if abbr.lower() == u:
            return n
    return None

def extract_game_from_espn(data, t1, t2):
    t1 = normalize_team_name(t1)
    t2 = normalize_team_name(t2)
    for event in data.get("events", []):
        try:
            comps = event["competitions"][0]["competitors"]
            names = [
                comps[0]["team"]["displayName"],
                comps[1]["team"]["displayName"],
                comps[0]["team"]["shortName"],
                comps[1]["team"]["shortName"],
            ]
            if fuzzy_match_team(t1, names) and fuzzy_match_team(t2, names):
                return event
        except:
            continue
    return None

# ============================================================
# ESPN LIVE DATA ENGINE
# ============================================================
def fetch_espn_scoreboard():
    try:
        return requests.get(ESPN_SCOREBOARD_URL, timeout=5).json()
    except Exception as e:
        return {"error": str(e)}

def parse_espn_game(event):
    try:
        comp = event["competitions"][0]
        teams = comp["competitors"]

        home = teams[0] if teams[0]["homeAway"] == "home" else teams[1]
        away = teams[1] if teams[0]["homeAway"] == "home" else teams[0]

        status = comp["status"]
        situation = comp.get("situation", {})

        return {
            "home_team": home["team"]["displayName"],
            "away_team": away["team"]["displayName"],
            "home_score": int(home.get("score", 0)),
            "away_score": int(away.get("score", 0)),
            "period": status.get("period"),
            "clock": status.get("displayClock"),
            "possession": situation.get("possession"),
        }
    except Exception as e:
        return {"error": f"ESPN parsing error: {e}"}

# ============================================================
# ODDS API ENGINE
# ============================================================
def fetch_live_odds():
    try:
        url = f"{ODDS_API_URL}&apiKey={ODDS_API_KEY}"
        return requests.get(url, timeout=10).json()
    except Exception as e:
        return {"error": str(e)}

def extract_live_odds_for_game(odds_data, t1, t2):
    t1 = t1.lower()
    t2 = t2.lower()

    for game in odds_data:
        home = game.get("home_team","").lower()
        away = game.get("away_team","").lower()

        if (t1 in home or t1 in away) and (t2 in home or t2 in away):
            best_spread, best_total, best_ml = None, None, None
            for book in game.get("bookmakers", []):
                for m in book.get("markets", []):
                    if m["key"] == "spreads":
                        try: best_spread = sorted(m["outcomes"], key=lambda x: abs(x["point"]))[0]
                        except: pass
                    if m["key"] == "totals":
                        try: best_total = m["outcomes"][0]
                        except: pass
                    if m["key"] == "h2h":
                        try: best_ml = sorted(m["outcomes"], key=lambda x: x["price"])[0]
                        except: pass

            return {"spread": best_spread, "total": best_total, "moneyline": best_ml}

    return None

# ============================================================
# V4 CORE MODEL (unchanged section)
# ============================================================
GILMER_SYSTEM_PROMPT_V4 = """ ... unchanged ... """

def run_gpt_v4(prompt):
    for _ in range(3):
        try:
            resp = client.chat.completions.create(
                model="gpt-4.1",
                messages=[
                    {"role": "system", "content": GILMER_SYSTEM_PROMPT_V4},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.4,
            )
            return json.loads(resp.choices[0].message.content)
        except:
            continue
    return {"error":"GPT failed to produce valid JSON"}

# ============================================================
# (Everything else remains exactly as you provided)
# ============================================================

# --- Entire rest of your script stays unchanged ---
# --- EPA Engine, Charts, UI, Pipeline, PDF, main() ---

# ============================================================
# MAIN()
# ============================================================
def main():
    ui_layout()
    if st.session_state.get("should_run_pipeline"):
        execute_pipeline(
            st.session_state["mode"],
            st.session_state["team1"],
            st.session_state["team2"],
        )

if __name__ == "__main__":
    main()
