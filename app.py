# ============================================================
# Gilmer CFB Betting Intelligence Model V3.0
# Hybrid Pregame + Live In-Game ATS & O/U Prediction Engine
# Engineered by Matthew Gilmer
# ============================================================

import streamlit as st
import requests
import os
import re
import time
import json
import base64
from datetime import datetime
from fpdf import FPDF
from openai import OpenAI

# -----------------------------
# API Clients & Secrets
# -----------------------------
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
ODDS_API_KEY = os.environ.get("ODDS_API_KEY")  # stored safely in Streamlit Secrets

# -----------------------------
# Constants
# -----------------------------
ESPN_SCOREBOARD_URL = "https://site.web.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard"
ODDS_API_URL = (
    "https://api.the-odds-api.com/v4/sports/americanfootball_ncaaf/odds"
    "?regions=us&markets=h2h,spreads,totals&oddsFormat=american"
)
AUTO_REFRESH_INTERVAL_MS = 15000  # 15-second refresh for live mode

# ============================================================
# Module 2 — Fuzzy Team Matching Engine
# ============================================================

def normalize_team_name(name):
    """
    Clean and normalize team names for fuzzy comparison.
    """
    if not name:
        return ""
    name = name.lower().strip()
    name = re.sub(r"[^a-z0-9 ]", "", name)  # remove punctuation
    return name


def fuzzy_match_team(user_input, espn_team_names):
    """
    Attempt to match user-entered team name with ESPN-provided names.
    Uses partial matches, abbreviations, and nickname matching.
    """
    user_clean = normalize_team_name(user_input)

    # Perfect match
    for t in espn_team_names:
        if normalize_team_name(t) == user_clean:
            return t

    # Strong partial match
    for t in espn_team_names:
        if user_clean in normalize_team_name(t):
            return t

    # Reverse partial (team name contains user input)
    for t in espn_team_names:
        if normalize_team_name(t) in user_clean:
            return t

    # Abbreviation/short name handling (UGA, LSU, FSU, BAMA)
    for t in espn_team_names:
        abbr = "".join([word[0] for word in t.split() if word[0].isalpha()])
        if user_clean == abbr.lower():
            return t

    # If nothing matches, return None (handled gracefully later)
    return None


def extract_game_from_espn(data, team1, team2):
    """
    Given ESPN scoreboard data and user-entered teams,
    attempt to find the matching live game.
    """
    team1_clean = normalize_team_name(team1)
    team2_clean = normalize_team_name(team2)

    for event in data.get("events", []):
        try:
            comps = event["competitions"][0]["competitors"]
            espn_names = [
                comps[0]["team"]["displayName"],
                comps[0]["team"]["shortName"],
                comps[1]["team"]["displayName"],
                comps[1]["team"]["shortName"],
            ]

            # Attempt fuzzy match for both teams
            match1 = fuzzy_match_team(team1_clean, espn_names)
            match2 = fuzzy_match_team(team2_clean, espn_names)

            if match1 and match2:
                return event

        except Exception:
            continue

    return None  # if no matching event found

# ============================================================
# Module 3 — ESPN Live Data Engine
# ============================================================

def fetch_espn_scoreboard():
    """
    Pull the full ESPN College Football scoreboard feed.
    """
    try:
        resp = requests.get(ESPN_SCOREBOARD_URL, timeout=5)
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


def parse_espn_game(event):
    """
    Given an ESPN event (single game), extract structured game information.
    """

    try:
        comp = event["competitions"][0]
        competitors = comp["competitors"]

        home = competitors[0] if competitors[0]["homeAway"] == "home" else competitors[1]
        away = competitors[1] if competitors[0]["homeAway"] == "home" else competitors[0]

        # Basic score info
        home_team = home["team"]["displayName"]
        away_team = away["team"]["displayName"]
        home_score = int(home.get("score", 0))
        away_score = int(away.get("score", 0))

        # Game status
        status = comp.get("status", {})
        period = status.get("period")
        clock = status.get("displayClock")
        game_status_text = status.get("type", {}).get("description", "Unknown")

        # Possession, down, distance, yard line
        situation = comp.get("situation", {})
        possession = situation.get("possession")
        down = situation.get("down")
        distance = situation.get("distance")
        yard_line = situation.get("yardLine")  # 50 = midfield

        # Drives (if available)
        drives = comp.get("drives", {})

        parsed = {
            "home_team": home_team,
            "away_team": away_team,
            "home_score": home_score,
            "away_score": away_score,
            "period": period,
            "clock": clock,
            "status_text": game_status_text,
            "possession": possession,
            "down": down,
            "distance": distance,
            "yard_line": yard_line,
            "drives": drives,
        }

        return parsed

    except Exception as e:
        return {"error": f"Failed to parse ESPN data: {e}"}

# ============================================================
# Module 4 — Live Odds Engine (TheOddsAPI)
# ============================================================

def fetch_live_odds():
    """
    Pull live odds from TheOddsAPI for NCAAF.
    Returns list of games with multiple book odds.
    """
    url = f"{ODDS_API_URL}&apiKey={ODDS_API_KEY}"
    try:
        resp = requests.get(url, timeout=8)
        data = resp.json()
        return data
    except Exception as e:
        return {"error": f"Odds API request failed: {e}"}


def extract_live_odds_for_game(odds_data, team1, team2):
    """
    Attempts to match live odds with user-entered game.
    Returns best spread/total across available books.
    """

    team1 = team1.lower()
    team2 = team2.lower()

    for game in odds_data:
        home = game.get("home_team", "").lower()
        away = game.get("away_team", "").lower()

        # fuzzy-ish matching
        if (team1 in home or team1 in away) and (team2 in home or team2 in away):

            best_spread = None
            best_total = None
            best_ml = None

            for book in game.get("bookmakers", []):
                markets = book.get("markets", [])

                for m in markets:
                    if m["key"] == "spreads":
                        try:
                            o1 = m["outcomes"][0]
                            o2 = m["outcomes"][1]
                            # choose best spread based on lower absolute number
                            candidate = sorted([o1, o2], key=lambda x: abs(x["point"]))[0]
                            best_spread = candidate
                        except:
                            pass

                    if m["key"] == "totals":
                        try:
                            o1 = m["outcomes"][0]
                            # choose the total closest to 50 (neutral point)
                            candidate = o1
                            best_total = candidate
                        except:
                            pass

                    if m["key"] == "h2h":  # moneyline
                        try:
                            o1 = m["outcomes"][0]
                            o2 = m["outcomes"][1]
                            best_ml = sorted([o1, o2], key=lambda x: x["price"])[0]
                        except:
                            pass

            return {
                "best_spread": best_spread,
                "best_total": best_total,
                "best_ml": best_ml,
                "raw": game,
            }

    return None

# ============================================================
# Module 5 — Hybrid GPT Prediction Engine
# ============================================================

HYBRID_SYSTEM_PROMPT = """
You are the Gilmer CFB Hybrid Betting Intelligence Model V3.0.
You generate ATS and O/U recommendations using:

1. Pregame priors from historical tendencies.
2. Live ESPN game state (score, time, drives, possession, pace).
3. Real-time spreads, totals, and odds movement from TheOddsAPI.
4. Momentum analysis, drive quality, and pace-of-play projections.
5. Risk-adjusted recommendation logic.

Rules:
- ALWAYS output a clear ATS pick: team + spread direction.
- ALWAYS output a clear O/U pick: Over or Under.
- ALWAYS include a confidence score (0–100%).
- Keep explanations clean, direct, and analytic.
- Never complain about missing data; infer rationally when needed.
- If live data indicates a flipped projection, explicitly state the flip.
- If pregame and live disagree, prioritize LIVE DATA by 60%, pregame 40%.
- Provide a short actionable summary up top.
"""

def run_hybrid_gpt_model(
    mode,
    game,
    pregame_context,
    live_game_data=None,
    live_odds=None
):
    """
    Main GPT engine for hybrid modeling.
    """

    live_data_json = json.dumps(live_game_data, indent=2) if live_game_data else "None"
    live_odds_json = json.dumps(live_odds, indent=2) if live_odds else "None"

    user_prompt = f"""
Mode: {mode}
Game: {game}

Pregame Analysis:
{pregame_context}

Live Game State:
{live_data_json}

Live Market Odds:
{live_odds_json}

Provide:
1. ATS Prediction
2. O/U Prediction
3. Confidence percentage
4. Reasoning (1–3 tight paragraphs)
5. A top-summary at the beginning
"""

    try:
        resp = client.chat.completions.create(
            model="gpt-4.1",
            messages=[
                {"role": "system", "content": HYBRID_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.4,
        )
        return resp.choices[0].message["content"]

    except Exception as e:
        return f"GPT model error: {e}"

# ============================================================
# Module 6 — Live Scoreboard Renderer
# ============================================================

def render_live_scoreboard(live):
    """
    Renders a clean, readable scoreboard for live games.
    Accepts parsed ESPN game data from Module 3.
    """

    if not live or "error" in live:
        st.markdown(
            "<div style='padding:10px; background:#330000; color:#FF7777; border:1px solid #660000; border-radius:8px;'>"
            "Live game data unavailable or game not found."
            "</div>",
            unsafe_allow_html=True
        )
        return

    home = live["home_team"]
    away = live["away_team"]
    hs = live["home_score"]
    as_ = live["away_score"]
    period = live["period"]
    clock = live["clock"]
    possession = live.get("possession")
    down = live.get("down")
    dist = live.get("distance")
    yardline = live.get("yard_line")

    # Possession marker
    poss_text = ""
    if possession:
        if possession.lower() in home.lower():
            poss_text = f"🏈 {home} ball"
        elif possession.lower() in away.lower():
            poss_text = f"🏈 {away} ball"
    
    # Field position display
    field_pos = ""
    if yardline is not None:
        if yardline == 50:
            field_pos = "Midfield (50)"
        else:
            # simple display: yard line toward offense
            field_pos = f"Ball on {yardline}"

    # Down & distance
    dd_text = ""
    if down and dist:
        ordinal = {1:"1st",2:"2nd",3:"3rd",4:"4th"}.get(down, f"{down}th")
        dd_text = f"{ordinal} & {dist}"

    # Compose scoreboard block
    html = f"""
    <div style='
        background-color:#1A1A1A;
        padding:18px;
        border:1px solid #333;
        border-radius:10px;
        margin-top:10px;
        font-family:Arial, sans-serif;
    '>

        <h2 style='text-align:center; color:#1A73E8; margin-bottom:8px;'>
            {away} {as_} — {home} {hs}
        </h2>

        <h4 style='text-align:center; color:#D4AF37; margin-top:0;'>
            Q{period} | {clock}
        </h4>

        <p style='text-align:center; color:#AAAAAA; margin:6px 0;'>
            {poss_text}
        </p>

        <p style='text-align:center; color:#AAAAAA; margin:4px 0;'>
            {dd_text}
        </p>

        <p style='text-align:center; color:#AAAAAA; margin:4px 0;'>
            {field_pos}
        </p>
    </div>
    """

    st.markdown(html, unsafe_allow_html=True)

# ============================================================
# Module 7 — Auto-Refresh Engine (Live Mode)
# ============================================================

def auto_refresh_if_live(mode):
    """
    Automatically triggers a refresh on the Streamlit app
    if the user selects Live mode.
    """
    if mode.lower() == "live in-game" or mode.lower() == "live":
        st_autorefresh = st.experimental_rerun  # fallback if needed
        st_autorefresh_rate = st.autorefresh(interval=AUTO_REFRESH_INTERVAL_MS)


# ============================================================
# Module 8 — PDF Generator (V3.0: Pregame + Live Hybrid)
# ============================================================

def generate_pdf(game_title, scoreboard_html, odds_data, model_output, logo_base64=None):
    """
    Creates a polished PDF report summarizing the hybrid model's output.
    """

    pdf = FPDF()
    pdf.add_page()

    # Register fonts (DejaVu supports UTF-8)
    pdf.add_font("DejaVu", "", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", uni=True)
    pdf.add_font("DejaVu", "B", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", uni=True)

    # Header Title
    pdf.set_font("DejaVu", "B", 18)
    pdf.cell(0, 10, "Gilmer CFB Betting Intelligence Report", ln=True, align="C")
    pdf.ln(5)

    # Logo (optional)
    if logo_base64:
        temp_logo_path = "temp_logo_v3.png"
        with open(temp_logo_path, "wb") as f:
            f.write(base64.b64decode(logo_base64))
        pdf.image(temp_logo_path, x=80, w=40)
        pdf.ln(10)

    # Game Title
    pdf.set_font("DejaVu", "B", 14)
    pdf.cell(0, 8, f"Game: {game_title}", ln=True)
    pdf.ln(2)

    # Timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    pdf.set_font("DejaVu", "", 10)
    pdf.cell(0, 6, f"Generated: {timestamp}", ln=True)
    pdf.ln(8)

    # Live Scoreboard Block
    pdf.set_font("DejaVu", "B", 12)
    pdf.cell(0, 8, "Live Scoreboard Snapshot:", ln=True)
    pdf.set_font("DejaVu", "", 10)
    pdf.multi_cell(0, 5, scoreboard_html)
    pdf.ln(4)

    # Live Odds
    pdf.set_font("DejaVu", "B", 12)
    pdf.cell(0, 8, "Live Odds:", ln=True)
    pdf.set_font("DejaVu", "", 10)
    pdf.multi_cell(0, 5, json.dumps(odds_data, indent=2))
    pdf.ln(5)

    # Model Output
    pdf.set_font("DejaVu", "B", 12)
    pdf.cell(0, 8, "Model Output:", ln=True)
    pdf.set_font("DejaVu", "", 10)
    pdf.multi_cell(0, 5, model_output)
    pdf.ln(5)

    # Footer
    pdf.set_font("DejaVu", "", 9)
    pdf.ln(8)
    pdf.cell(
        0,
        5,
        "If you can outperform this model, you should be selling your own.",
        ln=True,
        align="C",
    )

    out_path = f"gilmer_v3_report.pdf"
    pdf.output(out_path)
    return out_path

# ============================================================
# Module 9 — Streamlit UI Controller
# ============================================================

def load_logo_base64():
    """Load logo.png as Base64 string if it exists."""
    if not os.path.exists("logo.png"):
        return None
    with open("logo.png", "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def display_header():
    """Top branding header."""
    logo_b64 = load_logo_base64()

    if logo_b64:
        st.markdown(
            f"""
            <div style='text-align:center; margin-top:-20px;'>
                <img src='data:image/png;base64,{logo_b64}' width='140'>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown(
        """
        <h1 style='text-align:center; color:#1a73e8;'>Gilmer CFB Betting Intelligence Model V3.0</h1>
        <h4 style='text-align:center; margin-top:-10px;'>Engineered by Matthew Gilmer</h4>
        <p style='text-align:center; color:#999; margin-top:-8px;'>
            Hybrid Pregame + Live ATS & O/U Prediction Engine
        </p>
        <hr>
        """,
        unsafe_allow_html=True,
    )


def run_ui():
    """Main UI controller for streamlit."""

    display_header()

    # Mode selection
    mode = st.selectbox("Betting Mode:", ["Pregame", "Live In-Game"])

    # Game input
    game_input = st.text_input(
        "Which game do you want evaluated? (Example: Alabama vs Georgia)"
    )

    run_button = st.button("Run Analysis", use_container_width=True)

    # Live auto-refresh (Module 7 usage)
    if mode == "Live In-Game":
        st.autorefresh(interval=AUTO_REFRESH_INTERVAL_MS)

    if not run_button:
        return  # do nothing until user clicks

    if "vs" not in game_input.lower():
        st.error("Please enter game format: Team1 vs Team2")
        return

    team1, team2 = [x.strip() for x in game_input.split("vs")]

# ============================================================
# Module 10 — Main Execution Engine
# ============================================================

def execute_full_pipeline(mode, team1, team2):
    """
    Orchestrates the full Pregame + Live hybrid pipeline.
    """

    # --------------------------------------------------------
    # PREGAME CONTEXT (light placeholder — can be expanded)
    # --------------------------------------------------------
    pregame_context = f"User requested analysis for {team1} vs {team2}. Mode: {mode}."

    # --------------------------------------------------------
    # LIVE MODE: pull ESPN + odds + scoreboard
    # --------------------------------------------------------
    live_game_data = None
    live_odds_data = None
    matched_event = None

    if mode == "Live In-Game":
        # 1. ESPN scoreboard
        scoreboard = fetch_espn_scoreboard()

        matched_event = extract_game_from_espn(scoreboard, team1, team2)
        if matched_event:
            live_game_data = parse_espn_game(matched_event)

        # 2. Odds
        odds_raw = fetch_live_odds()
        live_odds_data = extract_live_odds_for_game(odds_raw, team1, team2)

    # --------------------------------------------------------
    # Run Hybrid Model
    # --------------------------------------------------------
    model_output = run_hybrid_gpt_model(
        mode=mode,
        game=f"{team1} vs {team2}",
        pregame_context=pregame_context,
        live_game_data=live_game_data,
        live_odds=live_odds_data,
    )

    # --------------------------------------------------------
    # Display Scoreboard (if live)
    # --------------------------------------------------------
    scoreboard_text = "No live data."
    if live_game_data:
        render_live_scoreboard(live_game_data)
        scoreboard_text = json.dumps(live_game_data, indent=2)

    # --------------------------------------------------------
    # Display Odds (if present)
    # --------------------------------------------------------
    if live_odds_data:
        st.subheader("Live Market Odds")
        st.json(live_odds_data)

    # --------------------------------------------------------
    # Display Model Output
    # --------------------------------------------------------
    st.subheader("Model Output")
    st.write(model_output)

    # --------------------------------------------------------
    # PDF Generation
    # --------------------------------------------------------
    logo_b64 = load_logo_base64()
    pdf_path = generate_pdf(
        game_title=f"{team1} vs {team2}",
        scoreboard_html=scoreboard_text,
        odds_data=live_odds_data,
        model_output=model_output,
        logo_base64=logo_b64,
    )

    with open(pdf_path, "rb") as f:
        st.download_button(
            label="Download PDF Report",
            data=f,
            file_name="gilmer_v3_report.pdf",
            mime="application/pdf",
        )


# ============================================================
# MAIN ENTRYPOINT — RUN UI & PIPELINE
# ============================================================

def main():
    run_ui()

    # After UI input triggers "Run Analysis", execution resumes here
    if st.session_state.get("should_run_pipeline"):
        mode = st.session_state["mode"]
        team1 = st.session_state["team1"]
        team2 = st.session_state["team2"]
        execute_full_pipeline(mode, team1, team2)


# Required for Streamlit execution
if __name__ == "__main__":
    main()
