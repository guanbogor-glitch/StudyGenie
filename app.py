import streamlit as st
from google import genai
import os
import plotly.express as px
import pandas as pd
from datetime import datetime
import random

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

# --- DATA & FOLDER SETUP ---
XP_FILE = "xp_points.txt"
MISTAKE_FILE = "mistake_log.csv"
TESTS_FILE = "tests_taken.txt"
HISTORY_FILE = "xp_history.csv"

for file in [XP_FILE, TESTS_FILE]:
    if not os.path.exists(file):
        with open(file, "w") as f: f.write("0")

if not os.path.exists(HISTORY_FILE):
    df = pd.DataFrame(columns=["Date", "XP"])
    df.to_csv(HISTORY_FILE, index=False)

if not os.path.exists(MISTAKE_FILE):
    df_mistakes = pd.DataFrame(columns=["Date", "Question", "Richard_Answer", "Correct_Answer", "Retries_To_Master"])
    df_mistakes.to_csv(MISTAKE_FILE, index=False)

with open(XP_FILE, "r") as f: xp = int(f.read().strip())
with open(TESTS_FILE, "r") as f: tests_taken = int(f.read().strip())

SYLLABUS = {
    "Mathematics (G3)": {
        "Sec 2A": ["Ch 1: Linear Equations & Simultaneous Equations", "Ch 2: Linear Inequalities", "Ch 3: Algebraic Expressions", "Ch 4: Expansion & Factorisation"],
        "Sec 1 Review": ["Algebra Basics", "Fractions & Decimals"]
    }
}

# --- HARDER XP SYSTEM ---
if xp < 1000: level, badge = "Level 1: Novice 🌱", "🥉 Bronze Scout"
elif xp < 2500: level, badge = "Level 2: Apprentice 📖", "🥈 Silver Explorer"
elif xp < 5000: level, badge = "Level 3: Scholar 🧠", "🥇 Gold Master"
elif xp < 10000: level, badge = "Level 4: Master 🧞‍♂️", "🏆 Platinum Genius"
else: level, badge = "Level 5: Grandmaster 🌟", "💎 Diamond Legend"

# --- LOGIN SYSTEM ---
st.sidebar.header("🔐 Login")
user_role = st.sidebar.radio("Select Mode:", ["Student (Richard)", "Developer (Parent)"])
is_dev = False

if user_role == "Developer (Parent)":
    password = st.sidebar.text_input("Enter Password:", type="password")
    if password == "parent123":
        is_dev = True
        st.sidebar.success("Developer Access Granted ✅")

# --- SIDEBAR ---
with st.sidebar:
    st.header("🏆 Richard's Progress")
    st.subheader(level)
    st.write(f"**Badge:** {badge}")
    next_level_xp = 1000 if xp < 1000 else 2500 if xp < 2500 else 5000 if xp < 5000 else 10000
    st.progress(min(xp / next_level_xp, 1.0))
    st.write(f"**XP:** {xp} / {next_level_xp}")
    
    st.divider()
    st.header("Settings")
    api_key = st.text_input("Gemini API Key", type="password")

if not api_key:
    st.info("👈 Please enter your API Key on the left to start.")
    st.stop()

# Using the smarter, free Gemini 2.5 Flash
client = genai.Client(api_key=api_key)

def ask_ai(prompt):
    response = client.models.generate_content(
        model="gemini-3.5-flash-lite",
        contents=prompt
    )
    return response.text

if "mode" not in st.session_state: st.session_state.mode = "home"
if "q_index" not in st.session_state: st.session_state.q_index = 0
if "answers" not in st.session_state: st.session_state.answers = {}

# --- DEVELOPER DASHBOARD ---
if is_dev:
    st.header("👨‍💻 Developer / Parent Dashboard")
    tab1, tab2 = st.tabs(["📈 Progress Chart", "🔍 Detailed Mistake Log"])
    
    with tab1:
        df_history = pd.read_csv(HISTORY_FILE)
        if not df_history.empty:
            fig = px.line(df_history, x="Date", y="XP", title="Richard's XP Growth", markers=True)
            st.plotly_chart(fig, use_container_width=True)
    
    with tab2:
        st.subheader("Detailed Mistake Log")
        df_mistakes = pd.read_csv(MISTAKE_FILE)
        if not df_mistakes.empty:
            for index, row in df_mistakes.iloc[::-1].iterrows():
                with st.expander(f"❌ {row['Question'][:50]}..."):
                    st.write(f"**Richard's Answer:** {row['Richard_Answer']}")
                    st.write(f"**Correct Answer:** {row['Correct_Answer']}")
        else:
            st.success("No mistakes logged yet!")

# --- STUDENT VIEW ---
else:
    with st.sidebar:
        st.divider()
        st.header("🎯 Choose Topic")
        
        if st.session_state.mode in ["home", "test", "learn"]:
            subject = st.selectbox("Subject:", list(SYLLABUS.keys()))
            book = st.selectbox("Book / Level:", list(SYLLABUS[subject].keys()))
            topic = st.selectbox("Chapter:", SYLLABUS[subject][book])
            final_topic_name = f"{subject} - {book} - {topic}"
            
            difficulty = st.radio("Select Difficulty:", ["Standard (Normal)", "Hard Mode (Extra XP)"])
                    
            if st.button("📖 1. Learn this Topic"):
                st.session_state.mode = "learn"
                st.session_state.lesson_text = None 
                st.session_state.current_topic = final_topic_name
                st.session_state.test_results = None
                st.rerun()
            
            if st.button("📝 2. Take the Test"):
                st.session_state.mode = "test"
                st.session_state.current_test = None 
                st.session_state.current_topic = final_topic_name
                st.session_state.current_difficulty = difficulty
                st.session_state.test_results = None
                st.session_state.q_index = 0
                st.session_state.answers = {}
                st.rerun()

    if st.session_state.mode == "home":
        st.write("Welcome Richard! Select a Subject, Book, and Chapter on the left to begin.")

    elif st.session_state.mode == "learn":
        topic = st.session_state.current_topic
        st.header(f"📖 Lesson: {topic}")
        if st.session_state.get("lesson_text") is None:
            with st.spinner("Preparing your visual lesson..."):
                try:
                    prompt = f"Explain {topic} for a Singapore Sec 2 (G3) student named Richard. Use simple language. DO NOT use LaTeX formatting. Instead, write math plainly (e.g. 3x + 5 = 15). Include a text-based diagram using emojis."
                    st.session_state.lesson_text = ask_ai(prompt)
                except Exception:
                    st.error("⚠️ Google is busy. Try again.")
                    if st.button("Try Again 🔄"): st.rerun()
                    st.stop()
        st.markdown(st.session_state.lesson_text, unsafe_allow_html=True)

    elif st.session_state.mode == "test":
        topic = st.session_state.current_topic
        is_hard = st.session_state.get("current_difficulty") == "Hard Mode (Extra XP)"
        st.header(f"📝 Test: {topic} ({'Hard Mode' if is_hard else 'Standard'})")
        
        if st.session_state.get("test_results") is None:
            if st.session_state.get("current_test") is None:
                # --- PURE PYTHON GENERATION ---
                generated_test = {}
                for i in range(1, 11):
                    if not is_hard:
                        q_type = random.choice(["brackets", "both_sides"])
                    else:
                        q_type = random.choice(["both_sides", "simultaneous"])
                    
                    if q_type == "brackets":
                        a = random.randint(2, 5)
                        b = random.randint(1, 5)
                        x = random.randint(2, 10)
                        eq = f"Solve the linear equation:\n\n{a}(x + {b}) = {a*(x+b)}"
                        ans = f"x = {x}"
                        
                    elif q_type == "both_sides":
                        a = random.randint(3, 6)
                        c = random.randint(1, 2) 
                        b = random.randint(1, 10)
                        x = random.randint(2, 10)
                        d = (a*x + b) - (c*x)
                        eq = f"Solve the linear equation:\n\n{a}x + {b} = {c}x + {d}"
                        ans = f"x = {x}"
                        
                    else: # simultaneous
                        x = random.randint(1, 5)
                        y = random.randint(1, 5)
                        a, b = random.randint(1, 3), random.randint(1, 3)
                        c, d = random.randint(1, 3), random.randint(1, 3)
                        while a == c and b == d:
                            c, d = random.randint(1, 3), random.randint(1, 3)
                        eq1 = f"{a}x + {b}y = {a*x + b*y}"
                        eq2 = f"{c}x + {d}y = {c*x + d*y}"
                        eq = f"Solve the simultaneous equations:\n\n{eq1}\n\nand\n\n{eq2}"
                        ans = f"x = {x}, y = {y}"
                    
                    options = [ans]
                    while len(options) < 4:
                        if "," in ans:
                            wx = x + random.choice([-2, -1, 1, 2])
                            wy = y + random.choice([-2, -1, 1, 2])
                            wrong_ans = f"x = {wx}, y = {wy}"
                        else:
                            wx = x + random.choice([-2, -1, 1, 2])
                            wrong_ans = f"x = {wx}"
                        if wrong_ans not in options and wrong_ans != ans:
                            options.append(wrong_ans)
                    
                    random.shuffle(options)
                    letters = ["A", "B", "C", "D"]
                    correct_letter = letters[options.index(ans)]
                    formatted_options = [f"{letters[j]}) {options[j]}" for j in range(4)]
                    
                    generated_test[f"Q{i}"] = {
                        "question": eq,
                        "options": formatted_options,
                        "answer": correct_letter
                    }
                
                st.session_state.current_test = generated_test

            test_data = st.session_state.current_test
            q_keys = list(test_data.keys())
            total_q = len(q_keys)
            curr_idx = st.session_state.q_index
            
            st.progress((curr_idx + 1) / total_q)
            st.write(f"**Question {curr_idx + 1} of {total_q}**")
            
            q_key = q_keys[curr_idx]
            q_data = test_data[q_key]
            
            st.markdown(f"### {q_key}: {q_data['question']}")
            
            current_ans = st.radio("Select an answer:", ["--- Select ---"] + q_data['options'], key=f"radio_{curr_idx}")
            st.session_state.answers[q_key] = current_ans
            
            with st.popover(f"🆘 Need a hint for {q_key}?"):
                if st.button(f"Get Hint for {q_key}", key=f"btn_hint_{curr_idx}"):
                    with st.spinner("Thinking..."):
                        hint_prompt = f"Give a small hint for this math question without revealing the exact answer: {q_data['question']}"
                        hint_text = ask_ai(hint_prompt)
                        st.info(f"**Hint:** {hint_text}")

            st.write("---")
            
            col1, col2, col3 = st.columns([1, 1, 1])
            with col1:
                if curr_idx > 0:
                    if st.button("⬅️ Previous Question"):
                        st.session_state.q_index -= 1
                        st.rerun()
            with col3:
                if curr_idx < total_q - 1:
                    if st.button("Next Question ➡️"):
                        st.session_state.q_index += 1
                        st.rerun()
                else:
                    if st.button("Submit Test 🚀"):
                        if "--- Select ---" in st.session_state.answers.values():
                            st.warning("⚠️ Please answer all questions before submitting!")
                        else:
                            tests_taken += 1
                            with open(TESTS_FILE, "w") as f: f.write(str(tests_taken))
                            st.session_state.test_results = {"user_answers": st.session_state.answers}
                            st.rerun()

        else:
            test_data = st.session_state.current_test
            user_answers = st.session_state.test_results["user_answers"]
            
            score, wrong_questions = 0, []
            for q_key, q_data in test_data.items():
                if user_answers[q_key].startswith(q_data['answer']):
                    score += 1
                else:
                    wrong_questions.append({"q_key": q_key, "question": q_data['question'], "correct": q_data['answer'], "options": q_data['options'], "user_ans": user_answers[q_key]})
            
            percentage = (score / len(test_data)) * 100
            st.subheader(f"📊 Score: {score}/10 ({percentage:.0f}%)")
            base_xp = score * 2
            
            if score == 10:
                st.balloons()
                st.success("🌟 FLAWLESS VICTORY! 🌟 +30 Bonus XP awarded!")
                base_xp += 30
                
            if is_hard:
                base_xp += 20
                st.info("🔥 HARD MODE BONUS: +20 XP awarded!")
            
            current_xp = xp + base_xp
            with open(XP_FILE, "w") as f: f.write(str(current_xp))
            
            df_new = pd.DataFrame([{"Date": datetime.now().strftime("%Y-%m-%d %H:%M"), "XP": current_xp}])
            df_new.to_csv(HISTORY_FILE, mode='a', header=False, index=False)
            
            st.write(f"🏆 You earned **{base_xp} XP**!")
            
            if len(wrong_questions) > 0:
                st.divider()
                st.subheader("🔍 Review Mistakes")
                for wq in wrong_questions:
                    with st.expander(f"❌ {wq['q_key']}: {wq['question']}"):
                        st.write(f"**Richard's Answer:** {wq['user_ans']}")
                        correct_option = next((opt for opt in wq['options'] if opt.startswith(wq['correct'])), wq['correct'])
                        st.write(f"**Correct Answer:** {correct_option}")
                        
                        st.write("---")
                        try:
                            explain_prompt = f"Richard answered: {wq['user_ans']}. The correct answer is {correct_option}. Explain step-by-step why."
                            explanation = ask_ai(explain_prompt)
                            st.info(explanation)
                        except: st.write("Could not load explanation.")
            
            if st.button("Return Home 🏠"):
                st.session_state.mode = "home"
                st.session_state.current_test = None
                st.session_state.test_results = None
                st.session_state.q_index = 0
                st.session_state.answers = {}
                st.rerun()