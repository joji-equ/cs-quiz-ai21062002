# app.py
import streamlit as st
import pdfplumber
import google.generativeai as genai
import json
import random
import os
import hashlib
from datetime import datetime
from json_repair import repair_json

# ----------------------------
# MUST be the FIRST Streamlit command
# ----------------------------
st.set_page_config(page_title="CS Quiz Generator", layout="wide")

# ----------------------------
# Custom Styling (Glassmorphism + Gradients)
# ----------------------------
def add_custom_css():
    st.markdown("""
    <style>
    .stApp {
        background: linear-gradient(135deg, #6a11cb 0%, #2575fc 100%);
        color: white;
    }
    section[data-testid="stSidebar"] {
        background: rgba(255, 255, 255, 0.15) !important;
        backdrop-filter: blur(10px);
        border-radius: 16px;
        border: 1px solid rgba(255, 255, 255, 0.2);
        margin: 10px;
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
    genai.configure(api_key=GOOGLE_API_KEY)
    model = genai.GenerativeModel("gemini-2.5-flash")
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

# Initialize quiz history
if "quiz_history" not in st.session_state:
    st.session_state.quiz_history = []

# ----------------------------
# Helper Functions
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

def generate_quiz_from_text(text):
    prompt = f"""
You are a precise JSON generator for a quiz app.
Generate 8 high-quality Computer Science questions in STRICT, VALID JSON format ONLY.

❗ RULES:
- Output ONLY the JSON. No intro, no explanation.
- Use double quotes.
- 5 MCQ + 3 True/False
- Include "difficulty": "Easy", "Medium", or "Hard"
- Include "explanation"

Format:
{{
  "questions": [
    {{
      "type": "MCQ",
      "question": "...",
      "options": ["A) ...", "B) ...", "C) ...", "D) ..."],
      "answer": "A",
      "difficulty": "Medium",
      "explanation": "..."
    }},
    {{
      "type": "True/False",
      "question": "...",
      "options": ["True", "False"],
      "answer": "True",
      "difficulty": "Easy",
      "explanation": "..."
    }}
  ]
}}

Text:
{text}
"""
    try:
        response = model.generate_content(prompt, request_options={"timeout": 60})
        return parse_ai_response(response.text)
    except Exception as e:
        st.error(f"AI generation failed: {e}")
        return {"questions": []}

def generate_quiz_from_topic(topic):
    prompt = f"""
Generate 8 Computer Science questions on: "{topic}".
5 MCQ + 3 True/False.
STRICT JSON ONLY.
"""
    try:
        response = model.generate_content(prompt, request_options={"timeout": 60})
        return parse_ai_response(response.text)
    except Exception as e:
        st.error(f"Auto-quiz failed: {e}")
        return {"questions": []}

def display_interactive_quiz(quiz_data, key_prefix="quiz", topic="Unknown", quiz_type="Auto"):
    if not isinstance(quiz_data, dict):
        st.error("Quiz data error.")
        return

    questions = quiz_data.get("questions", [])
    if not questions:
        st.warning("No questions generated.")
        return

    if f"{key_prefix}_user_answers" not in st.session_state:
        st.session_state[f"{key_prefix}_user_answers"] = [None] * len(questions)
    user_answers = st.session_state[f"{key_prefix}_user_answers"]

    for i, q in enumerate(questions, 1):
        st.markdown(f"### Question {i} ({q.get('difficulty', 'N/A')})")
        st.write(f"**{q.get('question', 'N/A')}**")

        unique_key = f"{key_prefix}_q{i}"
        options = q.get("options", [])
        
        if q.get("type") == "MCQ" and len(options) == 4:
            index = None
            if user_answers[i-1] in options:
                index = options.index(user_answers[i-1])
            selected = st.radio("", options, key=unique_key, index=index if index is not None else 0, horizontal=True)
            user_answers[i-1] = selected

        elif q.get("type") == "True/False":
            current = user_answers[i-1] if user_answers[i-1] in ["True", "False"] else "True"
            selected = st.radio("", ["True", "False"], key=unique_key, index=0 if current == "True" else 1, horizontal=True)
            user_answers[i-1] = selected
        st.divider()

    if st.button("✅ Submit Answers", key=f"{key_prefix}_submit", use_container_width=True):
        st.session_state[f"{key_prefix}_submitted"] = True

        correct_count = 0
        for i, q in enumerate(questions, 1):
            user_ans = user_answers[i-1]
            correct_ans = q.get("answer", "")
            if user_ans == correct_ans:
                correct_count += 1

        score_str = f"{correct_count}/{len(questions)}"
        st.session_state.quiz_history.append({
            "type": quiz_type,
            "topic": topic,
            "score": score_str,
            "time": datetime.now().strftime("%H:%M")
        })

    if st.session_state.get(f"{key_prefix}_submitted", False):
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

# ----------------------------
# Sidebar: History
# ----------------------------
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/860/860792.png", width=40)
    st.subheader("📚 Quiz History")
    if st.session_state.quiz_history:
        for entry in reversed(st.session_state.quiz_history[-5:]):  # Last 5
            st.markdown(f"`{entry['score']}` • {entry['type']} • {entry['topic'][:30]}...")
        if st.button("🗑️ Clear", use_container_width=True):
            st.session_state.quiz_history = []
            st.rerun()
    else:
        st.info("No attempts yet.")

# ----------------------------
# Main App
# ----------------------------
st.title("🧠 AI-Powered CS Quiz Generator")
st.markdown("Upload a PDF or try a random CS topic quiz!")

# --- PDF Upload ---
st.header("📥 Upload CS PDF")
uploaded_file = st.file_uploader("Choose a text-based PDF", type="pdf")

if uploaded_file:
    file_hash = hashlib.md5(uploaded_file.read()).hexdigest()[:8]
    uploaded_file.seek(0)
    quiz_key = f"pdf_{file_hash}"

    with st.spinner("Extracting text..."):
        text = extract_text_from_pdf(uploaded_file)
    
    if text.strip():
        if quiz_key not in st.session_state:
            with st.spinner("AI generating quiz..."):
                quiz = generate_quiz_from_text(text)
            st.session_state[quiz_key] = quiz
        display_interactive_quiz(st.session_state[quiz_key], quiz_key, f"PDF ({file_hash})", "PDF")
    else:
        st.error("Could not extract text. Use a text-based PDF.")

# --- Auto Quiz ---
st.header("🎲 Daily CS Quiz")
if "auto_topic" not in st.session_state:
    st.session_state.auto_topic = random.choice(CS_TOPICS)

if st.button("🔄 New Topic", use_container_width=True):
    st.session_state.auto_topic = random.choice(CS_TOPICS)
    st.session_state.pop("auto_quiz", None)
    st.session_state.pop("auto_submitted", None)
    st.session_state.pop("auto_user_answers", None)
    st.rerun()

st.subheader(f"Topic: {st.session_state.auto_topic}")

if "auto_quiz" not in st.session_state:
    with st.spinner("Generating quiz..."):
        st.session_state.auto_quiz = generate_quiz_from_topic(st.session_state.auto_topic)

display_interactive_quiz(st.session_state.auto_quiz, "auto", st.session_state.auto_topic, "Auto")