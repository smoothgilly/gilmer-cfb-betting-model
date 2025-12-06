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
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
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

    /* Global Background */
    body, .main {
        background-color: #0a0f1f !important;
        color: #e6e6e6 !important;
    }

    /* Card Component */
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

    /* Gold Text */
    .gold-text {
        color: #D4AF37 !important;
        text-shadow: 0 0 12px #D4AF3755;
        font-weight: 700;
    }

    /* Animated Live Dot */
    .live-dot {
        height: 12px;
        width: 12px;
        background-color: #D4AF37;
        border-radius: 50%;
        display: inline-block;
        margin-right: 8px;
        animation: pulse 1.2s infinite;
    }
    @keyframes pulse {
        0%   { transform: scale(0.9); opacity: 0.7; }
        50%  { transform: scale(1.3); opacity: 1; }
        100% { transform: scale(0.9); opacity: 0.7; }
    }

    /* Probability Bar Container */
    .prob-bar {
        height: 18px;
        background: #1A73E833;
        border-radius: 10px;
        overflow: hidden;
        margin-top: 5px;
        margin-bottom: 12px;
        border: 1px solid #1A73E8;
    }

    /* Animated Probability Fill */
    .prob-fill {
        height: 100%;
        background: linear-gradient(90deg, #1A73E8, #D4AF37);
        width: 0%;
        animation: grow-bar 1.2s forwards;
    }
    @keyframes grow-bar {
        from { width: 0%; }
        to   { width: VAR_WIDTH%; }
    }

    </style>
    """, unsafe_allow_html=True)

# ============================================================
# FUZZY MATCHING ENGINE (Team Name Resolver)
# ============================================================
def normalize_team_name(name):
    if not name:
        return ""
    name = name.lower().strip()
    return re.sub(r"[^a-z0-9 ]", "", name)

def fuzzy_match_team(user, names):
    u = normalize_team_name(user)

    # Exact
    for n in names:
        if normalize_team_name(n) == u:
            return n

    # Partial
    for n in names:
        if u in normalize_team_name(n):
            return n

    # Abbreviation
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
        home = game.get("home_team", "").lower()
        away = game.get("away_team", "").lower()

        # fuzzy include
        if (t1 in home or t1 in away) and (t2 in home or t2 in away):
            best_spread, best_total, best_ml = None, None, None

            for book in game.get("bookmakers", []):
                for m in book.get("markets", []):

                    if m["key"] == "spreads":
                        try:
                            best_spread = sorted(m["outcomes"], key=lambda x: abs(x["point"]))[0]
                        except:
                            pass

                    if m["key"] == "totals":
                        try:
                            best_total = m["outcomes"][0]
                        except:
                            pass

                    if m["key"] == "h2h":
                        try:
                            best_ml = sorted(m["outcomes"], key=lambda x: x["price"])[0]
                        except:
                            pass

            return {
                "spread": best_spread,
                "total": best_total,
                "moneyline": best_ml,
            }

    return None

# ============================================================
# V4.0 CORE MODEL: SYSTEM PROMPT + JSON ENGINE + RETRY LOGIC
# ============================================================
GILMER_SYSTEM_PROMPT_V4 = """
You are the Gilmer CFB Betting Intelligence Model V4.0 — an elite 
dual-engine handicapping system engineered by Matthew Gilmer.

ARCHITECTURE:
1. Pregame Probabilistic Engine (PPE)
2. Live Momentum Engine (LME)
3. Market Drift Engine (MDE)
4. ATS/O-U Ensemble Decision Layer
5. Probability Distribution Generator
6. Gilmer Edge Score™ Calculator
7. JSON Strict Output Layer

RETURN ONLY VALID JSON IN THIS EXACT FORMAT:
{
  "ats_pick": "",
  "ats_probability": 0.00,
  "ou_pick": "",
  "ou_probability": 0.00,
  "score_projection": {
      "team1": {"low":0, "median":0, "high":0},
      "team2": {"low":0, "median":0, "high":0}
  },
  "gilmer_edge_score": 0,
  "momentum_trend": "",
  "market_drift": "",
  "confidence": 0,
  "summary": ""
}
"""

def run_gpt_v4(prompt):
    """Executes GPT with strict JSON retry layer."""
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
            text = resp.choices[0].message.content
            return json.loads(text)
        except:
            continue
    return {"error": "GPT failed to produce valid JSON output after retries."}

def build_v4_prompt(mode, game, pregame, live, odds):
    return f"""
Mode: {mode}
Game: {game}

Pregame Context:
{json.dumps(pregame, indent=2)}

Live Game Data:
{json.dumps(live, indent=2) if live else "None"}

Market Odds:
{json.dumps(odds, indent=2) if odds else "None"}

Return JSON using the required V4.0 schema.
"""
# ============================================================
# SEGMENT B — UI COMPONENTS, CARDS, CHARTS
# ============================================================

# ------------------------------------------------------------
# Probability Bar Component (Animated)
# ------------------------------------------------------------
def probability_bar(label, value):
    value_pct = int(value * 100)

    html = f"""
    <div class="gilmer-card">
        <h4 class="gold-text">{label}: {value_pct}%</h4>
        <div class="prob-bar">
            <div class="prob-fill" style="width:{value_pct}%;"></div>
        </div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


# ------------------------------------------------------------
# Gilmer Edge Score™ Radial Gauge
# ------------------------------------------------------------
def edge_gauge(edge_score):
    # Clamp range
    edge_score = max(0, min(100, edge_score))

    chart_data = pd.DataFrame({
        "category": ["edge", "rest"],
        "value": [edge_score, 100 - edge_score],
    })

    chart = (
        alt.Chart(chart_data)
        .mark_arc(innerRadius=40)
        .encode(
            theta="value",
            color=alt.Color(
                "category:N",
                scale=alt.Scale(
                    domain=["edge", "rest"],
                    range=["#D4AF37", "#1A73E822"],
                ),
                legend=None,
            )
        )
        .properties(width=200, height=200)
    )

    st.altair_chart(chart, use_container_width=False)


# ------------------------------------------------------------
# ATS / O-U Bar Charts
# ------------------------------------------------------------
def ats_ou_bar_charts(ats_prob, ou_prob):
    df = pd.DataFrame({
        "Bet": ["ATS", "O/U"],
        "Probability": [ats_prob * 100, ou_prob * 100],
    })

    chart = (
        alt.Chart(df)
        .mark_bar(cornerRadiusTopLeft=6, cornerRadiusTopRight=6)
        .encode(
            x=alt.X("Bet:N", title="Bet Type"),
            y=alt.Y("Probability:Q", title="Win Probability (%)"),
            color=alt.Color(
                "Bet:N",
                scale=alt.Scale(
                    domain=["ATS", "O/U"],
                    range=["#1A73E8", "#D4AF37"],
                ),
                legend=None,
            ),
        )
        .properties(height=220)
    )

    st.altair_chart(chart, use_container_width=True)


# ------------------------------------------------------------
# Score Projection Chart
# ------------------------------------------------------------
def score_projection_chart(score_projection):
    """
    score_projection = {
        "team1": {"low":X, "median":Y, "high":Z},
        "team2": {"low":A, "median":B, "high":C}
    }
    """

    df = pd.DataFrame([
        {
            "Team": "Team 1",
            "Low": score_projection["team1"]["low"],
            "Median": score_projection["team1"]["median"],
            "High": score_projection["team1"]["high"],
        },
        {
            "Team": "Team 2",
            "Low": score_projection["team2"]["low"],
            "Median": score_projection["team2"]["median"],
            "High": score_projection["team2"]["high"],
        },
    ])

    base = alt.Chart(df).encode(x="Team:N")

    band = base.mark_area(opacity=0.35).encode(
        y="Low:Q",
        y2="High:Q",
        color=alt.Color(
            "Team:N",
            scale=alt.Scale(range=["#1A73E8AA", "#D4AF37AA"]),
            legend=None,
        ),
    )

    median_line = base.mark_line(point=True, size=3).encode(
        y="Median:Q",
        color=alt.Color(
            "Team:N",
            scale=alt.Scale(range=["#1A73E8", "#D4AF37"]),
            legend=None,
        ),
    )

    chart = (band + median_line).properties(height=260)

    st.altair_chart(chart, use_container_width=True)


# ------------------------------------------------------------
# Momentum Trend Visualizer
# ------------------------------------------------------------
def momentum_trend_display(momentum_text):
    html = f"""
    <div class="gilmer-card">
        <h3 class="gold-text">Momentum Trend</h3>
        <p style="color:#EEE; font-size:16px;">{momentum_text}</p>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


# ------------------------------------------------------------
# Market Drift Display
# ------------------------------------------------------------
def market_drift_display(drift_text):
    html = f"""
    <div class="gilmer-card">
        <h3 class="gold-text">Market Drift</h3>
        <p style="color:#EEE; font-size:16px;">{drift_text}</p>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


# ------------------------------------------------------------
# Sportsbook Output Card
# ------------------------------------------------------------
def sportsbook_output_card(ats_pick, ou_pick, confidence, summary):
    html = f"""
    <div class="gilmer-card">
        <h2 class="gold-text">Gilmer Model V4.0 Pick Summary</h2>

        <p style="font-size:18px; color:#1A73E8;">
            <b>ATS:</b> {ats_pick}
        </p>

        <p style="font-size:18px; color:#D4AF37;">
            <b>O/U:</b> {ou_pick}
        </p>

        <p style="font-size:18px; color:#EEE;">
            <b>Confidence:</b> {confidence}%
        </p>

        <hr style="border-color:#1A73E855;">

        <p style="color:#EEE; font-size:15px;">
            {summary}
        </p>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)
# ============================================================
# SEGMENT C — PDF GENERATION ENGINE (WITH CHART EMBEDDING)
# ============================================================

# ----------------------------------------------
# Utility: Export Altair chart to PNG
# ----------------------------------------------
def export_chart_to_png(chart, filename):
    """
    Saves an Altair chart as a PNG file.
    """
    chart.save(filename, scale_factor=2)  # high resolution


# ----------------------------------------------
# Build PDF Report
# ----------------------------------------------
def generate_pdf_report(
    game_title,
    live_data,
    odds_data,
    gpt_output,
    score_chart,
    ats_ou_chart,
    edge_chart,
    logo_b64=None,
):
    """
    Creates a full PDF report with charts and logo.
    """
    pdf = FPDF()
    pdf.add_page()

    # -----------------------------
    # Fonts
    # -----------------------------
    pdf.add_font("DejaVu", "", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", uni=True)
    pdf.add_font("DejaVu", "B", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", uni=True)
    pdf.set_auto_page_break(auto=True, margin=12)

    # -----------------------------
    # Title Section
    # -----------------------------
    pdf.set_font("DejaVu", "B", 20)
    pdf.cell(0, 12, "Gilmer CFB Betting Intelligence Report", ln=True, align="C")

    if logo_b64:
        with open("temp_logo.png", "wb") as f:
            f.write(base64.b64decode(logo_b64))
        pdf.image("temp_logo.png", x=85, w=40)
        os.remove("temp_logo.png")

    pdf.ln(10)

    # -----------------------------
    # Game Title + Timestamp
    # -----------------------------
    pdf.set_font("DejaVu", "B", 14)
    pdf.cell(0, 10, f"Game: {game_title}", ln=True)

    pdf.set_font("DejaVu", "", 11)
    pdf.cell(0, 7, f"Generated: {datetime.now()}", ln=True)
    pdf.ln(5)

    # -----------------------------
    # Section: Live Data
    # -----------------------------
    pdf.set_font("DejaVu", "B", 13)
    pdf.cell(0, 8, "Live Game Data:", ln=True)

    pdf.set_font("DejaVu", "", 10)
    pdf.multi_cell(0, 6, json.dumps(live_data, indent=2) if live_data else "None")
    pdf.ln(5)

    # -----------------------------
    # Section: Odds Data
    # -----------------------------
    pdf.set_font("DejaVu", "B", 13)
    pdf.cell(0, 8, "Live Odds:", ln=True)

    pdf.set_font("DejaVu", "", 10)
    pdf.multi_cell(0, 6, json.dumps(odds_data, indent=2) if odds_data else "None")
    pdf.ln(5)

    # -----------------------------
    # Embed ATS/O-U Bar Chart
    # -----------------------------
    pdf.set_font("DejaVu", "B", 13)
    pdf.cell(0, 10, "ATS / O-U Probabilities:", ln=True)

    export_chart_to_png(ats_ou_chart, "temp_atsou.png")
    pdf.image("temp_atsou.png", x=15, w=180)
    os.remove("temp_atsou.png")
    pdf.ln(8)

    # -----------------------------
    # Embed Score Projection Chart
    # -----------------------------
    pdf.set_font("DejaVu", "B", 13)
    pdf.cell(0, 10, "Score Projections:", ln=True)

    export_chart_to_png(score_chart, "temp_score.png")
    pdf.image("temp_score.png", x=15, w=180)
    os.remove("temp_score.png")
    pdf.ln(8)

    # -----------------------------
    # Embed Gilmer Edge Score Gauge
    # -----------------------------
    pdf.set_font("DejaVu", "B", 13)
    pdf.cell(0, 10, "Gilmer Edge Score™:", ln=True)

    export_chart_to_png(edge_chart, "temp_edge.png")
    pdf.image("temp_edge.png", x=60, w=90)
    os.remove("temp_edge.png")
    pdf.ln(8)

    # -----------------------------
    # Model Output Section
    # -----------------------------
    pdf.set_font("DejaVu", "B", 13)
    pdf.cell(0, 10, "V4.0 Model Output:", ln=True)

    pdf.set_font("DejaVu", "", 10)
    pdf.multi_cell(0, 6, json.dumps(gpt_output, indent=2))
    pdf.ln(5)

    # -----------------------------
    # Save Output
    # -----------------------------
    out_path = "gilmer_v4_report.pdf"
    pdf.output(out_path)

    return out_path
# ============================================================
# SEGMENT D — DASHBOARD LAYOUT + PIPELINE EXECUTION + MAIN
# ============================================================

# ------------------------------------------------------------
# Live Scoreboard Renderer
# ------------------------------------------------------------
def render_live_scoreboard(live):
    if not live or "error" in live:
        st.error("No live game data available.")
        return

    home = live.get("home_team", "Home")
    away = live.get("away_team", "Away")
    hs = live.get("home_score", 0)
    as_ = live.get("away_score", 0)
    period = live.get("period", "?")
    clock = live.get("clock", "?")

    html = f"""
    <div class="gilmer-card">
        <h2 style="text-align:center; color:#1A73E8;">
            {away} {as_} — {home} {hs}
        </h2>
        <h4 style="text-align:center; color:#D4AF37;">
            Q{period} | {clock}
        </h4>
    </div>
    """

    st.markdown(html, unsafe_allow_html=True)


# ------------------------------------------------------------
# MAIN PIPELINE EXECUTION
# ------------------------------------------------------------
def execute_pipeline(mode, team1, team2):

    # -----------------------------------------
    # Pregame context
    # -----------------------------------------
    pregame_context = {
        "team1": team1,
        "team2": team2,
        "mode": mode,
        "timestamp": str(datetime.now()),
    }

    # -----------------------------------------
    # Fetch Live Game Data (if live mode)
    # -----------------------------------------
    live_game = None
    if mode == "Live In-Game":
        scoreboard = fetch_espn_scoreboard()
        evt = extract_game_from_espn(scoreboard, team1, team2)
        if evt:
            live_game = parse_espn_game(evt)

    # -----------------------------------------
    # Fetch Live Odds
    # -----------------------------------------
    odds_raw = fetch_live_odds()
    live_odds = extract_live_odds_for_game(odds_raw, team1, team2)

    # -----------------------------------------
    # Build Prompt + Call V4 Model
    # -----------------------------------------
    prompt = build_v4_prompt(
        mode,
        f"{team1} vs {team2}",
        pregame_context,
        live_game,
        live_odds
    )

    gpt = run_gpt_v4(prompt)

    if "error" in gpt:
        st.error(gpt["error"])
        return

    # Unpack results
    ats_pick = gpt["ats_pick"]
    ats_prob = gpt["ats_probability"]
    ou_pick = gpt["ou_pick"]
    ou_prob = gpt["ou_probability"]
    projection = gpt["score_projection"]
    edge_score = gpt["gilmer_edge_score"]
    momentum_text = gpt["momentum_trend"]
    drift_text = gpt["market_drift"]
    confidence = gpt["confidence"]
    summary = gpt["summary"]

    # -----------------------------------------
    # DASHBOARD LAYOUT (Option 3 Mixed Layout)
    # -----------------------------------------
    col1, col2 = st.columns([1.15, 1])

    with col1:
        sportsbook_output_card(ats_pick, ou_pick, confidence, summary)
        probability_bar("ATS Probability", ats_prob)
        probability_bar("O/U Probability", ou_prob)

    with col2:
        st.subheader("Gilmer Edge Score™")
        edge_chart = (
            alt.Chart(pd.DataFrame({
                "category": ["edge", "rest"],
                "value": [edge_score, 100 - edge_score],
            }))
            .mark_arc(innerRadius=50)
            .encode(
                theta="value:Q",
                color=alt.Color(
                    "category:N",
                    scale=alt.Scale(
                        domain=["edge", "rest"],
                        range=["#D4AF37", "#1A73E822"]
                    ),
                    legend=None
                )
            )
            .properties(width=260, height=260)
        )
        st.altair_chart(edge_chart, use_container_width=False)

        momentum_trend_display(momentum_text)
        market_drift_display(drift_text)

    # -----------------------------------------
    # Score Projection Chart
    # -----------------------------------------
    st.subheader("Score Projection Range")
    score_chart = (
        alt.Chart(pd.DataFrame([
            {
                "Team": team1,
                "Low": projection["team1"]["low"],
                "Median": projection["team1"]["median"],
                "High": projection["team1"]["high"],
            },
            {
                "Team": team2,
                "Low": projection["team2"]["low"],
                "Median": projection["team2"]["median"],
                "High": projection["team2"]["high"],
            },
        ]))
        .mark_area(opacity=0.30)
        .encode(
            x="Team:N",
            y="Low:Q",
            y2="High:Q",
            color=alt.Color(
                "Team:N",
                scale=alt.Scale(range=["#1A73E8AA", "#D4AF37AA"]),
                legend=None,
            ),
        )
        .properties(height=260)
        +
        alt.Chart(pd.DataFrame([
            {
                "Team": team1,
                "Median": projection["team1"]["median"],
            },
            {
                "Team": team2,
                "Median": projection["team2"]["median"],
            },
        ]))
        .mark_line(point=True, size=3)
        .encode(
            x="Team:N",
            y="Median:Q",
            color=alt.Color(
                "Team:N",
                scale=alt.Scale(range=["#1A73E8", "#D4AF37"]),
                legend=None,
            ),
        )
    )
    st.altair_chart(score_chart, use_container_width=True)

    # -----------------------------------------
    # ATS/O-U Bar Chart
    # -----------------------------------------
    st.subheader("ATS / O-U Probability Breakdown")
    ats_ou_chart = (
        alt.Chart(pd.DataFrame({
            "Bet": ["ATS", "O/U"],
            "Probability": [ats_prob * 100, ou_prob * 100],
        }))
        .mark_bar()
        .encode(
            x="Bet:N",
            y="Probability:Q",
            color=alt.Color(
                "Bet:N",
                scale=alt.Scale(
                    domain=["ATS", "O/U"],
                    range=["#1A73E8", "#D4AF37"],
                ),
                legend=None,
            )
        )
        .properties(height=240)
    )
    st.altair_chart(ats_ou_chart, use_container_width=True)

    # -----------------------------------------
    # LIVE SCOREBOARD (if live)
    # -----------------------------------------
    if live_game:
        st.subheader("Live Scoreboard")
        render_live_scoreboard(live_game)

    # -----------------------------------------
    # PDF GENERATION
    # -----------------------------------------
    logo_b64 = None
    if os.path.exists("logo.png"):
        with open("logo.png", "rb") as f:
            logo_b64 = base64.b64encode(f.read()).decode()

    pdf_file = generate_pdf_report(
        f"{team1} vs {team2}",
        live_game,
        live_odds,
        gpt,
        score_chart,
        ats_ou_chart,
        edge_chart,
        logo_b64,
    )

    with open(pdf_file, "rb") as f:
        st.download_button(
            "Download Full PDF Report",
            data=f,
            file_name="gilmer_v4_report.pdf",
            mime="application/pdf"
        )


# ------------------------------------------------------------
# UI INPUT LAYOUT
# ------------------------------------------------------------
def ui_layout():
    inject_css_theme()

    st.markdown("""
        <h1 style="text-align:center; color:#1A73E8;">
            Gilmer CFB Betting Intelligence Model V4.0
        </h1>
        <h3 style="text-align:center; color:#D4AF37;">
            Engineered by Matthew Gilmer
        </h3>
        <hr>
    """, unsafe_allow_html=True)

    mode = st.selectbox("Betting Mode:", ["Pregame", "Live In-Game"])
    game_input = st.text_input("Which game do you want evaluated? (Example: Alabama vs Georgia)")

    run_button = st.button("Run Analysis", use_container_width=True)

    if mode == "Live In-Game":
        st.autorefresh(interval=AUTO_REFRESH_INTERVAL_MS)

    if run_button:
        if "vs" not in game_input.lower():
            st.error("Game format must be: Team1 vs Team2")
            return

        team1, team2 = [x.strip() for x in game_input.split("vs")]

        st.session_state["should_run_pipeline"] = True
        st.session_state["mode"] = mode
        st.session_state["team1"] = team1
        st.session_state["team2"] = team2

        st.rerun()


# ------------------------------------------------------------
# MAIN()
# ------------------------------------------------------------
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
