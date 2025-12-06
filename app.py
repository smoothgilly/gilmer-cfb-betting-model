import streamlit as st
from openai import OpenAI
import os
import time
import base64
from fpdf import FPDF
from datetime import datetime


# ---------------------------------------------------------
# Initialize OpenAI client (will use your Streamlit secret)
# ---------------------------------------------------------
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])


# ---------------------------------------------------------
# DARK MODE THEME (DM1 Matte Black)
# ---------------------------------------------------------
st.markdown(
    """
    <style>
        body, .stApp {
            background-color: #0D0D0D !important;
            color: #EAEAEA !important;
        }

        .stTextInput>div>div>input,
        .stSelectbox>div>div>div {
            background-color: #1C1C1C !important;
            color: #EAEAEA !important;
            border: 1px solid #333333 !important;
        }

        .stButton>button {
            background-color: #1A73E8 !important;
            color: white !important;
            border-radius: 8px !important;
            padding: 0.5rem 1rem !important;
            border: none !important;
        }

        h1, h2, h3, h4 {
            color: #EAEAEA !important;
        }

        hr {
            border: 1px solid #333333 !important;
        }
    </style>
    """,
    unsafe_allow_html=True
)


# ---------------------------------------------------------
# Load Logo (Base64)
# ---------------------------------------------------------
def load_logo():
    try:
        with open("logo.png", "rb") as f:
            return base64.b64encode(f.read()).decode()
    except Exception:
        return None

logo_base64 = load_logo()


# ---------------------------------------------------------
# System Prompt
# ---------------------------------------------------------
SYSTEM_PROMPT = """
This prompt was engineered by Matthew Gilmer. This system provides rapid, high-accuracy ATS and Over/Under predictions using a streamlined neural-and-ensemble modeling framework. It evaluates team efficiency, game context, weather, market lines, and when live, real-time performance trends to produce clean probability-based recommendations with confidence scoring. The accreditation should appear only on the first output of a new session.

Before beginning any analysis, you must ask:
1. "Is this a pregame bet or a live in-game bet?"
2. "Which game do you want evaluated?"
"""


# ---------------------------------------------------------
# Streamlit Page Setup
# ---------------------------------------------------------
st.set_page_config(
    page_title="Gilmer CFB Betting Model",
    layout="centered",
    page_icon="🏈",
)


# ---------------------------------------------------------
# Display Centered Logo
# ---------------------------------------------------------
if logo_base64:
    st.markdown(
        f"""
        <div style='display:flex; justify-content:center; margin-top:15px; margin-bottom:5px;'>
            <img src="data:image/png;base64,{logo_base64}" width="160">
        </div>
        """,
        unsafe_allow_html=True
    )


# ---------------------------------------------------------
# Header Section
# ---------------------------------------------------------
st.markdown(
    """
    <h1 style='text-align:center;'>Gilmer CFB Betting Intelligence Model</h1>
    <h3 style='text-align:center;'>Engineered by Matthew Gilmer</h3>
    <p style='text-align:center; font-size:16px;'>
        A real-time ATS and Over/Under prediction system using a custom neural and ensemble prompt-engineered framework.
    </p>
    <hr>
    """,
    unsafe_allow_html=True
)


# ---------------------------------------------------------
# User Inputs
# ---------------------------------------------------------
mode = st.selectbox("Select bet type:", ["Pregame", "Live In-Game"])
game = st.text_input("Enter the game (e.g., 'Alabama vs LSU'):")

summary_box = st.empty()
result_box = st.empty()
pdf_box = st.empty()


# ---------------------------------------------------------
# Extract Top Play Summary
# ---------------------------------------------------------
def extract_top_play(model_output):
    lines = model_output.split("\n")
    ats = next((l for l in lines if "ATS" in l or "spread" in l.lower()), "ATS pick: Not detected")
    ou = next((l for l in lines if "Over" in l or "Under" in l), "O/U pick: Not detected")
    conf = next((l for l in lines if "confidence" in l.lower()), "Confidence: Not detected")
    return ats.strip(), ou.strip(), conf.strip()


# ---------------------------------------------------------
# Generate UTF-8 Safe PDF (FPDF2 + Bold font fix)
# ---------------------------------------------------------
def generate_pdf(game_title, summary_tuple, full_analysis, logo_base64):
    pdf = FPDF()
    pdf.add_page()

    # Register UTF-8 fonts: regular + bold
    pdf.add_font("DejaVu", "", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", uni=True)
    pdf.add_font("DejaVu", "B", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", uni=True)

    # Title
    pdf.set_font("DejaVu", "B", 18)
    pdf.cell(0, 10, "Gilmer CFB Betting Intelligence Report", ln=True, align="C")
    pdf.ln(5)

    # Logo
    if logo_base64:
        temp_logo_path = "temp_logo.png"
        with open(temp_logo_path, "wb") as f:
            f.write(base64.b64decode(logo_base64))
        pdf.image(temp_logo_path, x=75, w=50)

    pdf.ln(10)

    # Game Title
    pdf.set_font("DejaVu", "B", 14)
    pdf.cell(0, 10, game_title, ln=True)

    # Summary box border
    ats, ou, conf = summary_tuple
    pdf.set_draw_color(180, 180, 180)
    pdf.rect(10, pdf.get_y(), 190, 28)

    pdf.ln(4)
    pdf.set_font("DejaVu", "", 12)
    pdf.cell(0, 8, f"Top ATS Pick: {ats}", ln=True)
    pdf.cell(0, 8, f"Top O/U Pick: {ou}", ln=True)
    pdf.cell(0, 8, f"Confidence: {conf}", ln=True)
    pdf.ln(5)

    # Full analysis
    pdf.set_font("DejaVu", "", 11)
    pdf.multi_cell(0, 6, full_analysis)

    # Footer tagline
    pdf.ln(6)
    pdf.set_font("DejaVu", "I", 10)
    pdf.cell(0, 8, "If you can outperform this model, you should be selling your own.", ln=True, align="C")

    pdf_path = "report.pdf"
    pdf.output(pdf_path)
    return pdf_path


# ---------------------------------------------------------
# RUN ANALYSIS BUTTON
# ---------------------------------------------------------
if st.button("Run Analysis", use_container_width=True):

    if not game:
        st.error("Please enter a game.")
    else:
        with st.spinner("Running Gilmer Model Analysis..."):
            time.sleep(0.6)

            user_prompt = f"Mode Selected: {mode}\nGame: {game}\nRun full analysis."

            response = client.chat.completions.create(
                model="gpt-4.1",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
            )

            full_output = response.choices[0].message.content

            # Summary extraction
            ats, ou, conf = extract_top_play(full_output)

            # SUMMARY BOX
            summary_box.markdown(
                f"""
                <div style='padding:15px; background-color:#1A1A1A; border:1px solid #333; border-radius:10px;'>
                    <h3 style='color:#D4AF37;'>Top Play Summary</h3>
                    <p>{ats}</p>
                    <p>{ou}</p>
                    <p>{conf}</p>
                </div>
                """,
                unsafe_allow_html=True
            )

            # FULL ANALYSIS BOX
            result_box.markdown(
                f"""
                <div style='padding:20px; background-color:#1A1A1A; border:1px solid #333; border-radius:10px; margin-top:15px;'>
                    <h3 style='color:#1A73E8;'>Full Model Output</h3>
                    <pre style='white-space: pre-wrap; font-size:15px;'>{full_output}</pre>
                </div>
                """,
                unsafe_allow_html=True
            )

            # PDF EXPORT
            pdf_file = generate_pdf(game, (ats, ou, conf), full_output, logo_base64)
            with open(pdf_file, "rb") as f:
                pdf_box.download_button(
                    label="Download PDF Report",
                    data=f,
                    file_name=f"{game.replace(' ', '_')}_report.pdf",
                    mime="application/pdf"
                )
