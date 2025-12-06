import streamlit as st
from openai import OpenAI
import os
import time
import base64

# Initialize OpenAI client (correct for new SDK)
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

# -----------------------------
# Load Logo as Base64 (Always Displays)
# -----------------------------
def load_logo():
    try:
        with open("logo.png", "rb") as f:
            return base64.b64encode(f.read()).decode()
    except Exception:
        return None

logo_base64 = load_logo()

# -----------------------------
# System Prompt (ASCII ONLY)
# -----------------------------
SYSTEM_PROMPT = """
This prompt was engineered by Matthew Gilmer. This system provides rapid, high-accuracy ATS and Over/Under predictions using a streamlined neural-and-ensemble modeling framework. It evaluates team efficiency, game context, weather, market lines, and when live, real-time performance trends to produce clean probability-based recommendations with confidence scoring. The accreditation should appear only on the first output of a new session.

Before beginning any analysis, you must ask:
1. "Is this a pregame bet or a live in-game bet?"
2. "Which game do you want evaluated?"
"""

# -----------------------------
# Streamlit Page Config
# -----------------------------
st.set_page_config(
    page_title="Gilmer CFB Betting Model",
    layout="centered",
    page_icon="🏈",
)

# -----------------------------
# Display Centered Logo (Base64)
# -----------------------------
if logo_base64:
    st.markdown(
        f"""
        <div style='display: flex; justify-content: center; margin-top: 15px; margin-bottom: 5px;'>
            <img src="data:image/png;base64,{logo_base64}" width="180">
        </div>
        """,
        unsafe_allow_html=True
    )
else:
    st.warning("Logo file not found. Ensure 'logo.png' is in repository root.")

# -----------------------------
# Header Section
# -----------------------------
st.markdown(
    """
    <h1 style='text-align: center; color: #1a73e8;'>Gilmer CFB Betting Intelligence Model</h1>
    <h3 style='text-align: center;'>Engineered by Matthew Gilmer</h3>
    <p style='text-align: center; font-size: 16px;'>
    A real-time ATS and Over/Under prediction system using a custom neural and ensemble prompt-engineered framework.
    </p>
    <hr>
    """,
    unsafe_allow_html=True
)

# -----------------------------
# User Inputs
# -----------------------------
mode = st.selectbox("Select bet type:", ["Pregame", "Live In-Game"])
game = st.text_input("Enter the game (e.g., 'Alabama vs LSU'):")

# Container for output
result_box = st.empty()

# -----------------------------
# Run Button
# -----------------------------
if st.button("Run Analysis", use_container_width=True):

    if not game:
        st.error("Please enter a game.")
    else:
        with st.spinner("Running Gilmer Model Analysis..."):
            time.sleep(0.6)

            user_prompt = f"""
            Mode Selected: {mode}
            Game: {game}
            Run the full analysis according to the system instructions.
            """

            # -----------------------------
            # CORRECT OPENAI CALL FOR NEW SDK
            # -----------------------------
            response = client.chat.completions.create(
                model="gpt-4.1",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
            )

            output = response.choices[0].message.content

            # -----------------------------
            # Output box
            # -----------------------------
            result_box.markdown(
                f"""
                <div style='padding: 20px; border-radius: 10px; background-color: #f7f9fc; border: 1px solid #dfe3e8; margin-top: 10px;'>
                    <h3 style='color: #1a73e8;'>Model Output</h3>
                    <pre style='white-space: pre-wrap; font-size: 15px;'>{output}</pre>
                </div>
                """,
                unsafe_allow_html=True
            )

            # Copyable code block
            st.code(output, language='text')

            st.success("Analysis complete. You can copy the model output above using the copy button.")
