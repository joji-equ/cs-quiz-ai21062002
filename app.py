# app.py
import streamlit as st
import pdfplumber
import google.generativeai as genai
import json
import random
import os
import hashlib
from datetime import datetime, timedelta
from json_repair import repair_json
from pymongo import MongoClient
from typing import List, Dict

# ----------------------------
# MUST be the FIRST Streamlit command
# ----------------------------
st.set_page_config(page_title="CS Quiz Generator", layout="wide")

# ----------------------------
# MongoDB Setup (using Streamlit Secrets)
# ----------------------------
@st.cache_resource
def get_db_client():
    try:
        # Get connection string from secrets
        connection_string = st.secrets["MONGODB_URI"]
        client = MongoClient(connection_string)
        # Test connection
        client.admin.command('ping')
        return client
    except Exception as e:
        st.error(f"⚠️ MongoDB connection failed: {e}")
        return None

# Get database and collection
client = get_db_client()
db = client.csquiz if client else None
history_collection = db.history if db else None

# ----------------------------
# Custom Styling
# ----------------------------
def add_custom_css():
    st.markdown("""
    <style>
    .stApp {
        background: linear-gradient(135deg, #42275a 0%, #734b6d 100%);
        color: white;
    }
    section[data-testid="stSidebar"] {
        background: rgba(255, 255, 255, 0.15) !important;
        backdrop-filter: blur(10px);
        border-radius: 16px;
        border: 1px solid rgba(255, 255, 255, 0.2);
        margin: 10px;
        padding: 20px;
    }
    .stMarkdown, .stRadio, div[data-testid="stHorizontalBlock"] {
        background: rgba(255, 255, 255, 0.15) !important;
        backdrop-filter: blur(10px);
        border-radius: 16px;
        border: 1px solid rgba(255, 255, 255, 0.2);
        padding: 16px;
        margin-bottom: 16px;
    }
    .stButton > button {
        background: linear-gradient(90deg, #ff416c, #ff4b2b) !important;
        color: white !important;
        border: none !important;
        border-radius: 12px !important;
        padding: 12px 24px !important;
        font-weight: bold !important;
        transition: transform 0.2s, box-shadow 0.2s;
    }
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(255, 75, 43, 0.4) !important;
    }
    .stFileUploader > div > div {
        background: rgba(255, 255, 255, 0.2) !important;
        border-radius: 12px !important;
    }
    button[data-baseweb="tab"] {
        background: rgba(255, 255, 255, 0.2) !important;
        color: white !important;
        border-radius: 10px !important;
        margin: 0 5px !important;
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        background: linear-gradient(90deg, #ff416c, #ff4b2b) !important;
    }
    .timer {
        font-size: 1.2em;
        font-weight: bold;
        color: #ffcc00;
        text-align: center;
        margin: 10px 0;
    }
    </style>
    """, unsafe_allow_html=True)

add_custom_css()

# ----------------------------
# Configuration
# ----------------------------
GOOGLE_API_KEY = os.getenv("GEMINI_API_KEY") or st.secrets.get("GEMINI_API_KEY")

if not GOOGLE_API_KEY:
    st.error("❌ Missing GEMINI_API_KEY. Set it in Streamlit Cloud secrets.")
    st.stop()

try:
    model = genai.GenerativeModel("gemini-2.5-flash")
    genai.configure(api_key=GOOGLE_API_KEY)
except Exception as e:
    st.error(f"Failed to initialize Gemini: {e}")
    st.stop()

# ----------------------------
# Constants
# ----------------------------
CS_TOPICS = [
    "Object-Oriented Programming (OOP) in Java",
    "Data Structures and Algorithms",
    "Fundamentals of Computer Networking",
    "SQL and Relational Database Design",
    "Introduction to Cloud Computing",
    "Responsive Web Applications",
    "Software Engineering and Project Management",
    "Automata Theory"
]

DIFFICULTY_OPTIONS = ["Random", "Easy", "Medium", "Hard"]

# ----------------------------
# Sidebar: Instructions
# ----------------------------
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/860/860792.png", width=40)
    st.subheader("ℹ️ How to Use This App")
    st.markdown("""
    ### 📎 **Upload PDF Quiz**
    1. Upload a **text-based PDF**
    2. Choose: questions, difficulty, timer
    3. Submit → results saved to cloud!
    
    ### 🎲 **Daily CS Quiz**
    1. Pick topic, questions, difficulty
    2. Set timer (optional)
    3. Submit → history persists!

    > 💾 **All quiz history is saved permanently** in the cloud!
    """)

    # Show persistent history
    st.subheader("📚 Your Quiz History")
    if history_collection:
        try:
            history = list(history_collection.find().sort("_id", -1).limit(5))
            if history:
                for entry in history:
                    st.markdown(f"`{entry['score']}` • {entry['type']} • {entry['topic'][:30]}...")
            else:
                st.info("No history yet.")
        except Exception as e:
            st.error("Failed to load history.")
    else:
        st.warning("History unavailable (DB not connected).")

# ----------------------------
# Helper: Save to MongoDB
# ----------------------------
def save_history_to_db(entry: Dict):
    if history_collection:
        try:
            history_collection.insert_one(entry)
        except Exception as e:
            st.error(f"Failed to save history: {e}")

# ----------------------------
# [All existing helper functions remain unchanged]
# ----------------------------
def extract_text_from_pdf(pdf_file):
    text = ""
    try:
        with pdfplumber.open(pdf_file) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        return text[:8000]
    except Exception as e:
        st.error(f"Error reading PDF: {e}")
        return ""

def parse_ai_response(response_text):
    try:
        json_str = response_text.strip()
        if "```json" in response_text:
            start = response_text.find("```json") + 7
            end = response_text.find("```", start)
            if end == -1:
                end = len(response_text)
            json_str = response_text[start:end].strip()
        elif "```" in response_text:
            start = response_text.find("```") + 3
            end = response_text.find("```", start)
            if end == -1:
                end = len(response_text)
            json_str = response_text[start:end].strip()

        try:
            parsed = json.loads(json_str)
        except json.JSONDecodeError:
            parsed = repair_json(json_str, return_objects=True)

        if isinstance(parsed, list):
            return {"questions": parsed}
        elif isinstance(parsed, dict):
            return parsed if "questions" in parsed else {"questions": list(parsed.values()) if parsed else []}
        else:
            return {"questions": []}
    except Exception:
        return {"questions": []}

def filter_questions_by_difficulty(questions, difficulty):
    if difficulty == "Random":
        return questions
    return [q for q in questions if q.get("difficulty") == difficulty]

def generate_quiz_from_text(text, num_questions=8, difficulty="Random"):
    prompt = f"""
You are a precise JSON generator for a quiz app.
Generate {num_questions} high-quality Computer Science questions in STRICT, VALID JSON format ONLY.

❗ RULES:
- Output ONLY the JSON. No intro, no explanation.
- Use double quotes.
- Mix of MCQ and True/False
- For EVERY question, include:
    - "type": "MCQ" or "True/False"
    - "question": full text
    - "options": list of 4 for MCQ, ["True","False"] for T/F
    - "answer": correct choice
    - "difficulty": one of "Easy", "Medium", "Hard"
    - "explanation": 1-sentence justification

Format:
{{
  "questions": [ ... ]
}}

Text:
{text}
"""
    try:
        response = model.generate_content(prompt, request_options={"timeout": 60})
        quiz = parse_ai_response(response.text)
        filtered = filter_questions_by_difficulty(quiz["questions"], difficulty)
        if len(filtered) < num_questions:
            extra = [q for q in quiz["questions"] if q not in filtered]
            random.shuffle(extra)
            filtered.extend(extra[:num_questions - len(filtered)])
        return {"questions": filtered[:num_questions]}
    except Exception as e:
        st.error(f"AI generation failed: {e}")
        return {"questions": []}

def generate_quiz_from_topic(topic, num_questions=8, difficulty="Random"):
    prompt = f"""
Generate {num_questions} Computer Science questions on: "{topic}".
Mix of MCQ and True/False.
STRICT JSON ONLY.
Include "difficulty": "Easy", "Medium", or "Hard" for every question.
"""
    try:
        response = model.generate_content(prompt, request_options={"timeout": 60})
        quiz = parse_ai_response(response.text)
        filtered = filter_questions_by_difficulty(quiz["questions"], difficulty)
        if len(filtered) < num_questions:
            extra = [q for q in quiz["questions"] if q not in filtered]
            random.shuffle(extra)
            filtered.extend(extra[:num_questions - len(filtered)])
        return {"questions": filtered[:num_questions]}
    except Exception as e:
        st.error(f"Auto-quiz failed: {e}")
        return {"questions": []}

def display_interactive_quiz(quiz_data, key_prefix="quiz", topic="Unknown", quiz_type="Auto", duration_minutes=0):
    if not isinstance(quiz_data, dict):
        st.error("Quiz data error.")
        return

    questions = quiz_data.get("questions", [])
    if not questions:
        st.warning("No questions generated.")
        return

    if f"{key_prefix}_user_answers" not in st.session_state:
        st.session_state[f"{key_prefix}_user_answers"] = [None] * len(questions)
    if f"{key_prefix}_start_time" not in st.session_state and duration_minutes > 0:
        st.session_state[f"{key_prefix}_start_time"] = datetime.now()
        st.session_state[f"{key_prefix}_end_time"] = datetime.now() + timedelta(minutes=duration_minutes)

    user_answers = st.session_state[f"{key_prefix}_user_answers"]
    timer_expired = False

    if duration_minutes > 0 and f"{key_prefix}_end_time" in st.session_state:
        end_time = st.session_state[f"{key_prefix}_end_time"]
        now = datetime.now()
        if now >= end_time:
            timer_expired = True
            if not st.session_state.get(f"{key_prefix}_submitted", False):
                st.session_state[f"{key_prefix}_submitted"] = True
        else:
            remaining = end_time - now
            mins, secs = divmod(int(remaining.total_seconds()), 60)
            st.markdown(f'<div class="timer">⏳ Time left: {mins:02d}:{secs:02d}</div>', unsafe_allow_html=True)

    for i, q in enumerate(questions, 1):
        disabled = st.session_state.get(f"{key_prefix}_submitted", False) or timer_expired
        difficulty = q.get("difficulty", "Medium")
        if difficulty not in ["Easy", "Medium", "Hard"]:
            difficulty = "Medium"
        color = "#4CAF50" if difficulty == "Easy" else "#FF9800" if difficulty == "Medium" else "#F44336"
        st.markdown(f"### Question {i} • <span style='color:{color}; font-weight:bold;'>{difficulty}</span>", unsafe_allow_html=True)
        st.write(f"**{q.get('question', 'N/A')}**")

        unique_key = f"{key_prefix}_q{i}"
        options = q.get("options", [])
        
        if q.get("type") == "MCQ" and len(options) == 4:
            index = None
            if user_answers[i-1] in options:
                index = options.index(user_answers[i-1])
            selected = st.radio("", options, key=unique_key, index=index if index is not None else 0, horizontal=True, disabled=disabled)
            if not disabled:
                user_answers[i-1] = selected

        elif q.get("type") == "True/False":
            current = user_answers[i-1] if user_answers[i-1] in ["True", "False"] else "True"
            selected = st.radio("", ["True", "False"], key=unique_key, index=0 if current == "True" else 1, horizontal=True, disabled=disabled)
            if not disabled:
                user_answers[i-1] = selected
        st.divider()

    if not st.session_state.get(f"{key_prefix}_submitted", False) and not timer_expired:
        if st.button("✅ Submit Answers", key=f"{key_prefix}_submit", use_container_width=True):
            st.session_state[f"{key_prefix}_submitted"] = True

    if st.session_state.get(f"{key_prefix}_submitted", False) or timer_expired:
        correct_count = 0
        for i, q in enumerate(questions, 1):
            user_ans = user_answers[i-1]
            correct_ans = q.get("answer", "")
            is_correct = (user_ans == correct_ans)
            if is_correct:
                st.success(f"✅ Q{i}: Correct!")
                correct_count += 1
            else:
                st.error(f"❌ Q{i}: Incorrect. Correct: **{correct_ans}**")
            st.info(f"**Explanation:** {q.get('explanation', 'N/A')}")
            st.divider()

        st.subheader(f"🎉 Score: {correct_count}/{len(questions)}")
        if correct_count == len(questions):
            st.balloons()

        # Save to MongoDB
        score_str = f"{correct_count}/{len(questions)}"
        history_entry = {
            "type": quiz_type,
            "topic": topic,
            "score": score_str,
            "time": datetime.utcnow().isoformat(),
            "timestamp": datetime.utcnow()
        }
        save_history_to_db(history_entry)

        if st.button("🗑️ Clear Quiz", key=f"{key_prefix}_clear", use_container_width=True):
            keys_to_clear = [
                f"{key_prefix}_user_answers",
                f"{key_prefix}_submitted",
                f"{key_prefix}_start_time",
                f"{key_prefix}_end_time"
            ]
            for k in keys_to_clear:
                if k in st.session_state:
                    del st.session_state[k]
            st.rerun()

# ----------------------------
# Main App with Tabs
# ----------------------------
st.title("🧠 AI-Powered CS Quiz Generator")
st.markdown("Choose a quiz mode below!")

tab1, tab2 = st.tabs(["📎 Upload PDF Quiz", "🎲 Daily CS Quiz"])

# --- TAB 1: PDF Upload ---
with tab1:
    st.markdown("### 📎 Upload a CS/Programming PDF")
    st.caption("Supports text-based PDFs (not scanned images)")
    uploaded_file = st.file_uploader("Choose a PDF file", type="pdf", key="pdf_uploader")

    if uploaded_file:
        col1, col2, col3 = st.columns(3)
        with col1:
            num_q_pdf = st.slider("Number of Questions", 1, 10, 5, key="num_q_pdf")
        with col2:
            diff_pdf = st.selectbox("Difficulty", DIFFICULTY_OPTIONS, key="diff_pdf")
        with col3:
            timer_pdf = st.number_input("Timer (minutes, 0 = no timer)", 0, 30, 0, key="timer_pdf")

        file_hash = hashlib.md5(uploaded_file.read()).hexdigest()[:8]
        uploaded_file.seek(0)
        quiz_key = f"pdf_{file_hash}"

        with st.spinner("Extracting text from PDF..."):
            text = extract_text_from_pdf(uploaded_file)
        
        if text.strip():
            if quiz_key not in st.session_state:
                with st.spinner("AI is generating your custom quiz..."):
                    quiz = generate_quiz_from_text(text, num_q_pdf, diff_pdf)
                st.session_state[quiz_key] = quiz
            display_interactive_quiz(st.session_state[quiz_key], quiz_key, f"PDF ({file_hash})", "PDF", timer_pdf)
        else:
            st.error("❌ Could not extract text. Please use a text-based PDF.")

# --- TAB 2: Auto Quiz ---
with tab2:
    st.markdown("### 🎲 Try a Random CS Topic Quiz")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        selected_topic = st.selectbox("Select Topic", CS_TOPICS, key="topic_selector")
    with col2:
        num_q_auto = st.slider("Questions", 1, 10, 5, key="num_q_auto")
    with col3:
        diff_auto = st.selectbox("Difficulty", DIFFICULTY_OPTIONS, key="diff_auto")
    with col4:
        timer_auto = st.number_input("Timer (minutes)", 0, 30, 0, key="timer_auto")

    if st.button("🔄 Generate Quiz", use_container_width=True, key="gen_auto"):
        st.session_state.auto_quiz = generate_quiz_from_topic(selected_topic, num_q_auto, diff_auto)
        st.session_state.auto_quiz_generated = True

    if "auto_quiz_generated" in st.session_state and st.session_state.auto_quiz_generated:
        display_interactive_quiz(st.session_state.auto_quiz, "auto", selected_topic, "Auto", timer_auto)