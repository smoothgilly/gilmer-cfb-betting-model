# ============================================================
# Gilmer CFB Betting Intelligence Model V3.0
# Hybrid Pregame + Live ATS & O/U Prediction Engine
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

# ------------------------------------------------------------
# Initialize session state
# ------------------------------------------------------------
if "should_run_pipeline" not in st.session_state:
    st.session_state["should_run_pipeline"] = False

# ------------------------------------------------------------
# API Clients & Secrets
# ------------------------------------------------------------
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
ODDS_API_KEY = os.environ.get("ODDS_API_KEY")

# ------------------------------------------------------------
# Constants
# ------------------------------------------------------------
ESPN_SCOREBOARD_URL = "https://site.web.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard"
ODDS_API_URL = (
    "https://api.the-odds-api.com/v4/sports/americanfootball_ncaaf/odds"
    "?regions=us&markets=h2h,spreads,totals&oddsFormat=american"
)
AUTO_REFRESH_INTERVAL_MS = 15000  # 15 seconds refresh

# ============================================================
# Module 2 — Fuzzy Matching Engine
# ============================================================

def normalize_team_name(name):
    if not name:
        return ""
    name = name.lower().strip()
    name = re.sub(r"[^a-z0-9 ]", "", name)
    return name

def fuzzy_match_team(user_input, espn_team_names):
    user_clean = normalize_team_name(user_input)

    # Exact
    for t in espn_team_names:
        if normalize_team_name(t) == user_clean:
            return t

    # Partial
    for t in espn_team_names:
        if user_clean in normalize_team_name(t):
            return t

    # Reverse partial
    for t in espn_team_names:
        if normalize_team_name(t) in user_clean:
            return t

    # Abbreviations
    for t in espn_team_names:
        abbr = "".join([w[0] for w in t.split() if w])
        if user_clean == abbr.lower():
            return t

    return None

def extract_game_from_espn(data, team1, team2):
    t1 = normalize_team_name(team1)
    t2 = normalize_team_name(team2)

    for event in data.get("events", []):
        try:
            comps = event["competitions"][0]["competitors"]
            espn_names = [
                comps[0]["team"]["displayName"],
                comps[0]["team"]["shortName"],
                comps[1]["team"]["displayName"],
                comps[1]["team"]["shortName"],
            ]
            m1 = fuzzy_match_team(t1, espn_names)
            m2 = fuzzy_match_team(t2, espn_names)
            if m1 and m2:
                return event
        except:
            continue
    return None

# ============================================================
# Module 3 — ESPN Live Data Engine
# ============================================================

def fetch_espn_scoreboard():
    try:
        return requests.get(ESPN_SCOREBOARD_URL, timeout=5).json()
    except Exception as e:
        return {"error": str(e)}

def parse_espn_game(event):
    try:
        comp = event["competitions"][0]
        competitors = comp["competitors"]

        home = competitors[0] if competitors[0]["homeAway"] == "home" else competitors[1]
        away = competitors[1] if competitors[0]["homeAway"] == "home" else competitors[0]

        status = comp.get("status", {})
        situation = comp.get("situation", {})

        parsed = {
            "home_team": home["team"]["displayName"],
            "away_team": away["team"]["displayName"],
            "home_score": int(home.get("score", 0)),
            "away_score": int(away.get("score", 0)),
            "period": status.get("period"),
            "clock": status.get("displayClock"),
            "status_text": status.get("type", {}).get("description", "Unknown"),
            "possession": situation.get("possession"),
            "down": situation.get("down"),
            "distance": situation.get("distance"),
            "yard_line": situation.get("yardLine"),
            "drives": comp.get("drives", {}),
        }
        return parsed
    except Exception as e:
        return {"error": f"Failed to parse ESPN data: {e}"}

# ============================================================
# Module 4 — Odds API Engine
# ============================================================

def fetch_live_odds():
    try:
        url = f"{ODDS_API_URL}&apiKey={ODDS_API_KEY}"
        return requests.get(url, timeout=8).json()
    except Exception as e:
        return {"error": f"Odds API request failed: {e}"}

def extract_live_odds_for_game(odds_data, t1, t2):
    t1 = t1.lower()
    t2 = t2.lower()

    for game in odds_data:
        home = game.get("home_team", "").lower()
        away = game.get("away_team", "").lower()

        if (t1 in home or t1 in away) and (t2 in home or t2 in away):
            best_spread = None
            best_total = None
            best_ml = None

            for book in game.get("bookmakers", []):
                for m in book.get("markets", []):
                    key = m["key"]

                    # Spread
                    if key == "spreads":
                        try:
                            o = sorted(m["outcomes"], key=lambda x: abs(x["point"]))[0]
                            best_spread = o
                        except:
                            pass

                    # Total
                    if key == "totals":
                        try:
                            best_total = m["outcomes"][0]
                        except:
                            pass

                    # ML
                    if key == "h2h":
                        try:
                            best_ml = sorted(
                                m["outcomes"], key=lambda x: x["price"]
                            )[0]
                        except:
                            pass

            return {
                "best_spread": best_spread,
                "best_total": best_total,
                "best_ml": best_ml,
            }
    return None

# ============================================================
# Module 5 — Hybrid GPT Model
# ============================================================

HYBRID_SYSTEM_PROMPT = """
You are the Gilmer CFB Hybrid Betting Intelligence Model V3.0.
Blend:
- Pregame priors
- Live ESPN game state
- Live betting lines
- Momentum, pace
- ATS + O/U recommendations
- Confidence (0–100%)

Prioritize live data 60%, pregame 40%.
"""

def run_hybrid_gpt_model(mode, game, pregame_context, live_game_data, live_odds):
    live_data_json = json.dumps(live_game_data, indent=2) if live_game_data else "None"
    live_odds_json = json.dumps(live_odds, indent=2) if live_odds else "None"

    user_prompt = f"""
Mode: {mode}
Game: {game}

Pregame:
{pregame_context}

Live Data:
{live_data_json}

Live Odds:
{live_odds_json}

Return:
1. ATS pick
2. O/U pick
3. Confidence %
4. 1–3 paragraph reasoning
5. A top-action summary
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
        return f"GPT Error: {e}"

# ============================================================
# Module 6 — Scoreboard Renderer
# ============================================================

def render_live_scoreboard(live):
    if not live or "error" in live:
        st.error("No live game data available.")
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
    yard = live.get("yard_line")

    poss = ""
    if possession:
        if possession.lower() in home.lower():
            poss = f"🏈 {home} ball"
        elif possession.lower() in away.lower():
            poss = f"🏈 {away} ball"

    dd = ""
    if down and dist:
        ord_map = {1:"1st",2:"2nd",3:"3rd",4:"4th"}
        dd = f"{ord_map.get(down, str(down)+'th')} & {dist}"

    field = ""
    if yard is not None:
        field = "Midfield (50)" if yard == 50 else f"Ball on {yard}"

    html = f"""
    <div style='background:#111; padding:20px; border-radius:10px;'>
        <h2 style='color:#1A73E8; text-align:center;'>{away} {as_} — {home} {hs}</h2>
        <h4 style='color:#D4AF37; text-align:center;'>Q{period} | {clock}</h4>
        <p style='color:#AAA; text-align:center;'>{poss}</p>
        <p style='color:#AAA; text-align:center;'>{dd}</p>
        <p style='color:#AAA; text-align:center;'>{field}</p>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

# ============================================================
# Module 8 — PDF Generator
# ============================================================

def generate_pdf(game_title, scoreboard_html, odds_data, model_output, logo_base64=None):
    pdf = FPDF()
    pdf.add_page()

    pdf.add_font("DejaVu", "", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", uni=True)
    pdf.add_font("DejaVu", "B", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", uni=True)

    pdf.set_font("DejaVu", "B", 18)
    pdf.cell(0, 10, "Gilmer CFB Betting Intelligence Report", ln=True, align="C")
    pdf.ln(5)

    if logo_base64:
        with open("temp_logo.png", "wb") as f:
            f.write(base64.b64decode(logo_base64))
        pdf.image("temp_logo.png", x=80, w=40)
        pdf.ln(10)

    pdf.set_font("DejaVu", "B", 14)
    pdf.cell(0, 8, f"Game: {game_title}", ln=True)
    pdf.ln(2)

    pdf.set_font("DejaVu", "", 10)
    pdf.cell(0, 6, f"Generated: {datetime.now()}", ln=True)
    pdf.ln(8)

    pdf.set_font("DejaVu", "B", 12)
    pdf.cell(0, 8, "Live Scoreboard:", ln=True)
    pdf.set_font("DejaVu", "", 10)
    pdf.multi_cell(0, 5, scoreboard_html)
    pdf.ln(5)

    pdf.set_font("DejaVu", "B", 12)
    pdf.cell(0, 8, "Live Odds:", ln=True)
    pdf.set_font("DejaVu", "", 10)
    pdf.multi_cell(0, 5, json.dumps(odds_data, indent=2))
    pdf.ln(5)

    pdf.set_font("DejaVu", "B", 12)
    pdf.cell(0, 8, "Model Output:", ln=True)
    pdf.set_font("DejaVu", "", 10)
    pdf.multi_cell(0, 5, model_output)

    out_path = "gilmer_v3_report.pdf"
    pdf.output(out_path)
    return out_path

# ============================================================
# Module 9 — Streamlit UI Controller
# ============================================================

def load_logo_base64():
    if not os.path.exists("logo.png"):
        return None
    with open("logo.png", "rb") as f:
        return base64.b64encode(f.read()).decode()

def display_header():
    logo_b64 = load_logo_base64()
    if logo_b64:
        st.markdown(
            f"<div style='text-align:center;'><img src='data:image/png;base64,{logo_b64}' width='140'></div>",
            unsafe_allow_html=True,
        )

    st.markdown(
        """
        <h1 style='text-align:center; color:#1a73e8;'>Gilmer CFB Betting Intelligence Model V3.0</h1>
        <h4 style='text-align:center;'>Engineered by Matthew Gilmer</h4>
        <hr>
        """,
        unsafe_allow_html=True,
    )

def run_ui():
    display_header()

    mode = st.selectbox("Betting Mode:", ["Pregame", "Live In-Game"])
    game_input = st.text_input("Which game do you want evaluated? (Example: Alabama vs Georgia)")
    run_button = st.button("Run Analysis", use_container_width=True)

    if mode == "Live In-Game":
        st.autorefresh(interval=AUTO_REFRESH_INTERVAL_MS)

    if run_button:
        if "vs" not in game_input.lower():
            st.error("Format must be: Team1 vs Team2")
            return

        t1, t2 = [x.strip() for x in game_input.split("vs")]

        st.session_state["should_run_pipeline"] = True
        st.session_state["team1"] = t1
        st.session_state["team2"] = t2
        st.session_state["mode"] = mode

        st.experimental_rerun()

# ============================================================
# Module 10 — Main Execution Engine
# ============================================================

def execute_full_pipeline(mode, team1, team2):
    pregame_context = f"Evaluating {team1} vs {team2} in {mode} mode."

    live_game_data = None
    live_odds = None

    if mode == "Live In-Game":
        scoreboard = fetch_espn_scoreboard()
        evt = extract_game_from_espn(scoreboard, team1, team2)

        if evt:
            live_game_data = parse_espn_game(evt)

        odds_raw = fetch_live_odds()
        live_odds = extract_live_odds_for_game(odds_raw, team1, team2)

    result = run_hybrid_gpt_model(
        mode,
        f"{team1} vs {team2}",
        pregame_context,
        live_game_data,
        live_odds,
    )

    if live_game_data:
        render_live_scoreboard(live_game_data)

    st.subheader("Model Output")
    st.write(result)

    logo_b64 = load_logo_base64()
    pdf = generate_pdf(
        f"{team1} vs {team2}",
        json.dumps(live_game_data, indent=2) if live_game_data else "No live data",
        live_odds,
        result,
        logo_b64,
    )

    with open(pdf, "rb") as f:
        st.download_button("Download PDF Report", f, "gilmer_v3_report.pdf")

def main():
    run_ui()

    if st.session_state.get("should_run_pipeline"):
        execute_full_pipeline(
            st.session_state["mode"],
            st.session_state["team1"],
            st.session_state["team2"],
        )

if __name__ == "__main__":
    main()
