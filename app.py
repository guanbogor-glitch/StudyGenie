import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from google import genai
import os
import pandas as pd
from datetime import datetime
import random
import json
import io
import time
from pypdf import PdfReader

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

# --- DATABASE CONNECTION (SAFE) ---
@st.cache_resource
def get_db():
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        sheet_id = "1Lo-X7A7y0UTgCJqDTiDp87YHtohxOLJF3_qnkvGvXOA" 
        return client.open_by_key(sheet_id)
    except Exception:
        return None

db = get_db()
if db:
    try:
        progress_sheet = db.worksheet("Progress")
        mistakes_sheet = db.worksheet("Mistakes")
        richard_data = progress_sheet.row_values(2)
        xp = int(richard_data[1]) if len(richard_data) > 1 and richard_data[1] else 0
    except:
        xp = 0
        progress_sheet = None
        mistakes_sheet = None
else:
    xp = 0
    progress_sheet = None
    mistakes_sheet = None

if xp < 1000: level, badge = "Level 1: Novice 🌱", "🥉 Bronze Scout"
elif xp < 2500: level, badge = "Level 2: Apprentice 📖", "🥈 Silver Explorer"
else: level, badge = "Level 3: Scholar 🧠", "🥇 Gold Master"

def save_progress(new_xp, new_level, new_badge):
    if progress_sheet:
        try: progress_sheet.update('B2:D2', [[new_xp, new_level, new_badge]])
        except: pass

# --- SIDEBAR ---
with st.sidebar:
    st.header("🏆 Richard's Progress")
    st.subheader(level)
    st.write(f"**Badge:** {badge}")
    st.progress(min(xp / 1000.0, 1.0))
    st.write(f"**XP:** {xp} / 1000")
    
    if not db:
        st.warning("⚠️ Database offline.")
    
    st.divider()
    st.header("🔐 Login")
    if st.radio("Mode:", ["Student", "Developer"]) == "Developer":
        if st.text_input("Password:", type="password") == "parent123":
            st.session_state.is_dev = True
            st.success("Dev Access ✅")

api_key = st.secrets["GEMINI_API_KEY"]
client = genai.Client(api_key=api_key)

if "mode" not in st.session_state: st.session_state.mode = "home"
if "q_index" not in st.session_state: st.session_state.q_index = 0
if "answers" not in st.session_state: st.session_state.answers = {}

# --- DEVELOPER DASHBOARD ---
if st.session_state.get("is_dev"):
    st.header("👨‍💻 Parent Dashboard")
    
    tab1, tab2, tab3 = st.tabs(["📚 Question Bank Upload", "❌ Mistake Log", "⚙️ Settings"])
    
    with tab1:
        st.write("Upload the 18 exam papers here. The AI will extract the text and save it to the cloud server.")
        uploaded_papers = st.file_uploader("Upload Exam Papers (PDFs)", type=["pdf"], accept_multiple_files=True)
        
        if st.button("Process and Save to Question Bank"):
            if uploaded_papers:
                with st.spinner("Extracting text from PDFs... This may take a minute."):
                    all_text = ""
                    for paper in uploaded_papers:
                        try:
                            reader = PdfReader(io.BytesIO(paper.getvalue()))
                            for page in reader.pages[:4]: # Read first 4 pages of each paper
                                all_text += page.extract_text() + "\n"
                        except Exception as e:
                            st.warning(f"Could not read {paper.name}")
                    
                    # Save the text to a local file on the server
                    with open("bank_text.txt", "w", encoding="utf-8") as f:
                        f.write(all_text)
                    st.success(f"Saved text from {len(uploaded_papers)} papers to the Question Bank!")
                    st.rerun()
        
        st.write("### Current Question Bank Status:")
        if os.path.exists("bank_text.txt"):
            size = os.path.getsize("bank_text.txt")
            st.success(f"✅ Question Bank is loaded ({size} bytes of text).")
        else:
            st.info("No papers uploaded yet.")

    with tab2:
        if mistakes_sheet:
            try:
                all_mistakes = mistakes_sheet.get_all_records()
                for row in reversed(all_mistakes):
                    with st.expander(f"❌ {row['Question'][:50]}..."):
                        st.write(f"**Richard's Answer:** {row['Richard_Answer']}")
                        st.write(f"**Correct Answer:** {row['Correct_Answer']}")
            except: st.info("No data yet.")
        else:
            st.warning("Database offline.")

    with tab3:
        st.write("### Database Status")
        st.write(f"Database Connection: {'✅ Online' if db else '❌ Offline'}")
        st.write("### API Status")
        st.write(f"Gemini API Key: {'✅ Loaded' if api_key else '❌ Missing'}")

# --- STUDENT VIEW ---
else:
    if st.session_state.mode == "home":
        st.write("Welcome Richard! Choose your study mode:")
        
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("📚 Smart Exam Practice")
            st.write("The AI will generate a test based on real exam papers.")
            if st.button("Start AI Test"):
                st.session_state.mode = "textbook_test"
                st.session_state.current_test = None
                st.session_state.q_index = 0
                st.session_state.answers = {}
                st.session_state.test_results = None
                st.rerun()
                
        with col2:
            st.subheader("📸 Homework Helper")
            if st.button("Upload Homework (PDF/Photo)"):
                st.session_state.mode = "upload"
                st.rerun()

    elif st.session_state.mode == "upload":
        st.header("📸 Upload Homework")
        uploaded_file = st.file_uploader("Choose a file", type=["pdf", "jpg", "png", "jpeg"])
        
        if uploaded_file and st.button("Explain this to me"):
            with st.spinner("Teacher is reading the document..."):
                try:
                    if uploaded_file.type == "application/pdf":
                        reader = PdfReader(io.BytesIO(uploaded_file.getvalue()))
                        extracted_text = "".join([page.extract_text() + "\n" for page in reader.pages[:3]])
                        prompt = f"Explain step-by-step how to solve the problems in this text:\n{extracted_text}"
                        response = client.models.generate_content(model="gemini-2.5-pro", contents=prompt)
                        st.info(response.text)
                    else:
                        st.warning("Image processing is temporarily disabled. Please upload a PDF.")
                except Exception as e:
                    st.error("Error reading file.")
                    
        if st.button("⬅️ Back"):
            st.session_state.mode = "home"
            st.rerun()

    elif st.session_state.mode == "textbook_test":
        st.header("📝 Smart AI Test (Based on Real Exam Papers)")
        
        if st.session_state.get("test_results") is None:
            if st.session_state.get("current_test") is None:
                
                # Check if Bank exists
                if not os.path.exists("bank_text.txt"):
                    st.error("⚠️ No exam papers found in the Question Bank. Ask your Dad to upload them in Developer Mode!")
                    if st.button("⬅️ Back to Home"): 
                        st.session_state.mode = "home"
                        st.rerun()
                    st.stop()
                
                with st.spinner("Teacher is reading past papers and generating MOE questions..."):
                    # Read the text from the Question Bank
                    with open("bank_text.txt", "r", encoding="utf-8") as f:
                        context_text = f.read()
                    
                    # Limit context to avoid token limits (just grab a chunk)
                    context_text = context_text[:15000] 
                    
                    generated_test = {}
                    for i in range(1, 6):
                        success = False
                        for attempt in range(5):
                            try:
                                prompt = f"""Here are snippets of real MOE exam papers:
                                {context_text}
                                
                                Create ONE new multiple-choice question with the exact same style and difficulty. 
                                Output EXACTLY this text format, no markdown:
                                Question
                                A) opt1
                                B) opt2
                                C) opt3
                                D) opt4
                                Answer: A"""
                                
                                response = client.models.generate_content(model="gemini-2.5-pro", contents=prompt)
                                text = response.text.strip()
                                lines = [line.strip() for line in text.split('\n') if line.strip()]
                                
                                if len(lines) >= 6 and lines[-1].startswith("Answer:"):
                                    generated_test[f"Q{i}"] = {
                                        "question": lines[0],
                                        "options": lines[1:5],
                                        "answer": lines[5].split(":")[1].strip()
                                    }
                                    success = True
                                    break
                            except Exception:
                                time.sleep(1)
                                
                        if not success:
                            st.error("⚠️ AI is struggling to format the questions. Please try again.")
                            if st.button("Try Again 🔄"): st.rerun()
                            st.stop()
                            
                    st.session_state.current_test = generated_test
            st.rerun()

        # DISPLAY TEST
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
