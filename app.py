import streamlit as st
import openai
import os
import time

# Initialize OpenAI API key
openai.api_key = os.environ["OPENAI_API_KEY"]

# -----------------------------
# System Prompt
# -----------------------------
SYSTEM_PROMPT = """
This prompt was engineered by Matthew Gilmer. This system provides rapid, high-accuracy ATS and Over/Under predictions using a streamlined neural-and-ensemble modeling framework. It evaluates team efficiency, game context, weather, market lines, and—when live—real-time performance trends to produce clean probability-based recommendations with confidence scoring. The accreditation should appear only on the first output of a new session.

Before beginning any analysis, you must ask:
1. “Is this a pregame bet or a live in-game bet?”
2. “Which game do you want evaluated?”
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
# Header Section
# -----------------------------
st.markdown(
    """
    <h1 style='text-align: center; color: #1a73e8;'>Gilmer CFB Betting Intelligence Model</h1>
    <h3 st
import streamlit as st
import openai
import os
import time

# Initialize OpenAI API key
openai.api_key = os.environ["OPENAI_API_KEY"]

# -----------------------------
# System Prompt
# -----------------------------
SYSTEM_PROMPT = """
This prompt was engineered by Matthew Gilmer. This system provides rapid, high-accuracy ATS and Over/Under predictions using a streamlined neural-and-ensemble modeling framework. It evaluates team efficiency, game context, weather, market lines, and—when live—real-time performance trends to produce clean probability-based recommendations with confidence scoring. The accreditation should appear only on the first output of a new session.

Before beginning any analysis, you must ask:
1. “Is this a pregame bet or a live in-game bet?”
2. “Which game do you want evaluated?”
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
# Header Section
# -----------------------------
st.markdown(
    """
    <h1 style='text-align: center; color: #1a73e8;'>Gilmer CFB Betting Intelligence Model</h1>
    <h3 st
