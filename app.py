import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from google import genai
import os
import pandas as pd
from datetime import datetime
import random
import json
import time

# --- 2026 UI THEME ---
st.set_page_config(page_title="StudyGenie AI", page_icon="🚀", layout="wide")
st.markdown("""
<style>
    .stApp { background-color: #0E1117; }
    h1, h2, h3 { color: #4CAF50; font-family: 'Helvetica Neue', sans-serif; }
    .stButton>button { background-color: #2196F3; color: white; border-radius: 10px; }
    .stProgress > div > div > div > div { background-color: #FFD700; }
</style>
""", unsafe_allow_html=True)

st.title("🚀 Richard's StudyGenie AI")

# --- DATABASE CONNECTION ---
@st.cache_resource
def get_db():
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        sheet_id = "1Lo-X7A7y0UTgCJqDTiDp87YHtohxOLJF3_qnkvGvXOA" 
        return client.open_by_key(sheet_id)
    except Exception as e:
        st.error(f"Database connection error: {e}")
        st.stop()

db = get_db()
progress_sheet = db.worksheet("Progress")
mistakes_sheet = db.worksheet("Mistakes")

try:
    richard_data = progress_sheet.row_values(2)
    xp = int(richard_data[1]) if len(richard_data) > 1 and richard_data[1] else 0
except: xp = 0

if xp < 1000: level, badge = "Level 1: Novice 🌱", "🥉 Bronze Scout"
elif xp < 2500: level, badge = "Level 2: Apprentice 📖", "🥈 Silver Explorer"
else: level, badge = "Level 3: Scholar 🧠", "🥇 Gold Master"

def save_progress(new_xp, new_level, new_badge):
    try: progress_sheet.update('B2:D2', [[new_xp, new_level, new_badge]])
    except: pass

TEXTBOOK_CHAPTERS = {
    "Ch 1: Linear Graphs & Simultaneous Equations": "Graphs of linear equations, solving simultaneous equations by substitution and elimination.",
    "Ch 2: Linear Inequalities": "Solving simple linear inequalities, number lines.",
    "Ch 3: Algebraic Expressions": "Addition and subtraction of algebraic expressions.",
    "Ch 4: Expansion & Factorisation": "Expansion using identities, factorisation."
}

# --- SIDEBAR ---
with st.sidebar:
    st.header("🏆 Richard's Progress")
    st.subheader(level)
    st.write(f"**Badge:** {badge}")
    st.progress(min(xp / 1000.0, 1.0))
    st.write(f"**XP:** {xp} / 1000")
    
    st.divider()
    st.header("🔐 Login")
    if st.radio("Mode:", ["Student", "Developer"]) == "Developer":
        if st.text_input("Password:", type="password") == "parent123":
            st.session_state.is_dev = True
            st.success("Dev Access ✅")

api_key = st.secrets["GEMINI_API_KEY"]
client = genai.Client(api_key=api_key)

def ask_ai(prompt, use_pro=False):
    model = "gemini-2.5-pro" if use_pro else "gemini-3.5-flash-lite"
    response = client.models.generate_content(model=model, contents=prompt)
    return response.text

if "mode" not in st.session_state: st.session_state.mode = "home"
if "q_index" not in st.session_state: st.session_state.q_index = 0
if "answers" not in st.session_state: st.session_state.answers = {}

# --- DEVELOPER DASHBOARD ---
if st.session_state.get("is_dev"):
    st.header("👨‍💻 Parent Dashboard")
    try:
        all_mistakes = mistakes_sheet.get_all_records()
        for row in reversed(all_mistakes):
            with st.expander(f"❌ {row['Question'][:50]}..."):
                st.write(f"**Richard's Answer:** {row['Richard_Answer']}")
                st.write(f"**Correct Answer:** {row['Correct_Answer']}")
    except: st.info("No data yet.")

# --- STUDENT VIEW ---
else:
    if st.session_state.mode == "home":
        st.write("Welcome Richard! Choose your study mode:")
        
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("📚 Textbook Practice")
            selected_chapter = st.selectbox("Select Chapter:", list(TEXTBOOK_CHAPTERS.keys()))
            difficulty = st.radio("Difficulty:", ["Standard", "Hard"])
            if st.button("Start Textbook Test"):
                st.session_state.mode = "textbook_test"
                st.session_state.current_topic = selected_chapter
                st.session_state.current_difficulty = difficulty
                st.session_state.current_test = None
                st.session_state.q_index = 0
                st.session_state.answers = {}
                st.session_state.test_results = None
                st.rerun()
                
        with col2:
            st.subheader("📸 Homework / Test Paper")
            if st.button("Upload File"):
                st.session_state.mode = "upload"
                st.rerun()

    elif st.session_state.mode == "upload":
        st.header("📸 Upload Homework (PDF or Image)")
        uploaded_file = st.file_uploader("Choose a file", type=["pdf", "jpg", "png", "jpeg"])
        
        if uploaded_file and st.button("Convert to Quiz"):
            with st.spinner("Teacher is reading the document..."):
                prompt = """Extract the math questions from this document. Output ONLY a valid JSON dictionary. Format: {"Q1": {"question": "...", "options": ["A) ...", "B) ...", "C) ...", "D) ..."], "answer": "A"}}"""
                try:
                    text = ask_ai(prompt, use_pro=True).replace("```json", "").replace("```", "").strip()
                    st.session_state.current_test = json.loads(text)
                    st.session_state.mode = "test_display"
                    st.rerun()
                except:
                    st.error("Could not read the file. Try another photo/PDF.")
                    
        if st.button("⬅️ Back"):
            st.session_state.mode = "home"
            st.rerun()

    elif st.session_state.mode == "textbook_test":
        topic = st.session_state.current_topic
        is_hard = st.session_state.current_difficulty == "Hard"
        st.header(f"📝 Test: {topic} ({st.session_state.current_difficulty})")
        
        if st.session_state.get("test_results") is None:
            if st.session_state.get("current_test") is None:
                with st.spinner("MOE Teacher is preparing your test..."):
                    generated_test = {}
                    topic_desc = TEXTBOOK_CHAPTERS[topic]
                    
                    # 1. GENERATE 4 STABLE PYTHON QUESTIONS
                    for i in range(1, 5):
                        a = random.randint(2, 5); b = random.randint(1, 5); x = random.randint(2, 10)
                        eq = f"Solve the linear equation:\n\n{a}(x + {b}) = {a*(x+b)}"
                        ans = f"x = {x}"
                        options = [ans]
                        while len(options) < 4:
                            wx = x + random.choice([-2, -1, 1, 2])
                            wrong_ans = f"x = {wx}"
                            if wrong_ans not in options: options.append(wrong_ans)
                        random.shuffle(options)
                        letters = ["A", "B", "C", "D"]
                        generated_test[f"Q{i}"] = {"question": eq, "options": [f"{letters[j]}) {options[j]}" for j in range(4)], "answer": letters[options.index(ans)]}

                    # 2. GENERATE 1 SMART AI QUESTION (THE MOE PROBLEM SUM)
                    success = False
                    for attempt in range(3):
                        try:
                            # We only ask for ONE question to prevent formatting crashes
                            prompt = f"Create ONE math multiple-choice question for a Sec 2 student on the topic: '{topic_desc}'. Difficulty: {'Hard exam-style' if is_hard else 'Standard'}. Output EXACTLY this text format, no markdown:\nQuestion\nA) opt1\nB) opt2\nC) opt3\nD) opt4\nAnswer: A"
                            text = ask_ai(prompt, use_pro=True).strip()
                            lines = [line.strip() for line in text.split('\n') if line.strip()]
                            
                            if len(lines) >= 6 and lines[-1].startswith("Answer:"):
                                generated_test["Q5"] = {"question": lines[0], "options": lines[1:5], "answer": lines[5].split(":")[1].strip()}
                                success = True
                                break
                        except Exception:
                            time.sleep(2)
                    
                    if not success:
                        # If AI fails, fallback to Python so the test doesn't crash
                        generated_test["Q5"] = {"question": "Solve: 3x + 5 = 20", "options": ["A) x = 5", "B) x = 4", "C) x = 6", "D) x = 7"], "answer": "A"}
                            
                    st.session_state.current_test = generated_test
            st.rerun()

        test_data = st.session_state.current_test
        q_keys = list(test_data.keys())
        total_q = len(q_keys)
        curr_idx = st.session_state.q_index
        
        if curr_idx < total_q:
            st.progress((curr_idx + 1) / total_q)
            q_data = test_data[q_keys[curr_idx]]
            
            st.markdown(f"### Q{curr_idx + 1}: {q_data['question']}")
            ans = st.radio("Select an answer:", ["--- Select ---"] + q_data['options'], key=f"radio_{curr_idx}")
            st.session_state.answers[q_keys[curr_idx]] = ans
            
            if st.button("Next Question ➡️" if curr_idx < total_q - 1 else "Submit Test 🚀"):
                if "--- Select ---" in st.session_state.answers.values():
                    st.warning("Answer all questions first!")
                elif curr_idx < total_q - 1:
                    st.session_state.q_index += 1
                    st.rerun()
                else:
                    st.session_state.test_results = {"user_answers": st.session_state.answers}
                    st.rerun()

    elif st.session_state.mode == "test_display":
        test_data = st.session_state.current_test
        q_keys = list(test_data.keys())
        total_q = len(q_keys)
        curr_idx = st.session_state.q_index
        
        if curr_idx < total_q:
            st.progress((curr_idx + 1) / total_q)
            q_data = test_data[q_keys[curr_idx]]
            
            st.markdown(f"### Q{curr_idx + 1}: {q_data['question']}")
            ans = st.radio("Select an answer:", ["--- Select ---"] + q_data['options'], key=f"radio_p_{curr_idx}")
            st.session_state.answers[q_keys[curr_idx]] = ans
            
            if st.button("Next Question ➡️" if curr_idx < total_q - 1 else "Submit Test 🚀"):
                if "--- Select ---" in st.session_state.answers.values():
                    st.warning("Answer all questions first!")
                elif curr_idx < total_q - 1:
                    st.session_state.q_index += 1
                    st.rerun()
                else:
                    st.session_state.test_results = {"user_answers": st.session_state.answers}
                    st.rerun()

    # --- RESULTS VIEW ---
    if st.session_state.get("test_results") is not None:
        test_data = st.session_state.current_test
        user_answers = st.session_state.test_results["user_answers"]
        
        score = 0
        for q_key, q_data in test_data.items():
            if user_answers[q_key].startswith(q_data['answer']):
                score += 1
                
        st.subheader(f"📊 Score: {score}/{total_q}")
        
        base_xp = score * 2
        current_xp = xp + base_xp
        save_progress(current_xp, level, badge)
        st.write(f"🏆 You earned **{base_xp} XP**!")
        
        if st.button("Return Home 🏠"):
            st.session_state.mode = "home"
            st.session_state.current_test = None
            st.session_state.test_results = None
            st.session_state.q_index = 0
            st.session_state.answers = {}
            st.rerun()
