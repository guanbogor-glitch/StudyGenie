import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from google import genai
from google.genai import types
import os
import pandas as pd
from datetime import datetime
import json
import io
import time
from pypdf import PdfReader
from google.cloud import firestore, storage
from google.oauth2 import service_account
import plotly.express as px
from PIL import Image

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

# ==========================================
# 1. CLOUD & DATABASE CONNECTIONS
# ==========================================
@st.cache_resource
def get_cloud_clients():
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = service_account.Credentials.from_service_account_info(creds_dict)
        db_fs = firestore.Client(credentials=creds, project=creds_dict["project_id"])
        storage_client = storage.Client(credentials=creds, project=creds_dict["project_id"])
        bucket_name = "studygenie-materials-guan" 
        bucket = storage_client.bucket(bucket_name)
        return db_fs, bucket
    except Exception as e:
        return None, None

db_fs, bucket = get_cloud_clients()

@st.cache_resource
def get_sheets():
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        sheet_id = "1Lo-X7A7y0UTgCJqDTiDp87YHtohxOLJF3_qnkvGvXOA" 
        spreadsheet = client.open_by_key(sheet_id)
        progress = spreadsheet.worksheet("Progress")
        mistakes = spreadsheet.worksheet("Mistakes")
        try:
            work_log = spreadsheet.worksheet("Work_Log")
        except:
            work_log = spreadsheet.add_worksheet(title="Work_Log", rows="1000", cols="8")
            work_log.append_row(["Date", "Activity", "Subject", "Chapter", "Score", "Result", "XP Earned", "Teacher Note"])
        return progress, mistakes, work_log
    except: return None, None, None

progress_sheet, mistakes_sheet, work_log_sheet = get_sheets()
api_key = st.secrets["GEMINI_API_KEY"]
client = genai.Client(api_key=api_key)

# --- SMART AI CALL (Using your verified models) ---
def ask_ai(prompt, config=None):
    models_to_try = ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-3.5-flash"]
    for model_name in models_to_try:
        try:
            response = client.models.generate_content(model=model_name, contents=prompt, config=config)
            return response.text
        except Exception:
            continue
    raise Exception("All AI models failed.")

# ==========================================
# 2. XP & HELPER FUNCTIONS
# ==========================================
xp = 0
if progress_sheet:
    try:
        xp = int(progress_sheet.row_values(2)[1])
    except: pass

if xp < 1000: level, badge = "Level 1: Novice 🌱", "🥉 Bronze Scout"
elif xp < 2500: level, badge = "Level 2: Apprentice 📖", "🥈 Silver Explorer"
else: level, badge = "Level 3: Scholar 🧠", "🥇 Gold Master"

def save_progress(new_xp):
    if progress_sheet:
        try: progress_sheet.update('B2', [[new_xp]])
        except: pass

def log_work(activity, subject, chapter, score, result, xp_earned, note):
    if work_log_sheet:
        try:
            date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
            work_log_sheet.append_row([date_str, activity, subject, chapter, score, result, xp_earned, note])
        except: pass

# ==========================================
# 3. SIDEBAR
# ==========================================
with st.sidebar:
    st.header("🏆 Richard's Progress")
    st.subheader(level)
    st.write(f"**Badge:** {badge}")
    st.progress(min(xp / 2500.0, 1.0))
    st.write(f"**XP:** {xp} points")
    
    st.divider()
    st.header("🔐 Login")
    user_mode = st.radio("Mode:", ["Student (Richard)", "Developer (Parent)"])
    is_dev = (user_mode == "Developer (Parent)")
    
    if is_dev:
        if st.text_input("Password:", type="password") == "parent123":
            st.success("Dev Access ✅")
        else:
            is_dev = False

# ==========================================
# 4. DEVELOPER DASHBOARD
# ==========================================
if is_dev:
    st.header("👨‍💻 Parent Dashboard")
    tab1, tab2, tab3, tab4 = st.tabs(["📚 Upload Materials", "☁️ Cloud Library", "📈 Progress & Work Log", "❌ Mistake Log"])
    
    with tab1:
        col1, col2 = st.columns(2)
        with col1:
            subject = st.selectbox("Subject:", ["Mathematics", "Science", "English"])
            book_level = st.selectbox("Book / Level:", ["Sec 2A", "Sec 2B", "Sec 1 Review"])
        with col2:
            chapter = st.selectbox("Chapter:", ["Ch 1", "Ch 2", "Ch 3", "Ch 4", "Ch 5", "Ch 6", "Ch 7", "All Chapters"])
            mat_type = st.radio("Type:", ["Knowledge Base (Textbook)", "Question Bank (Exam Papers)"])
            
        uploaded_files = st.file_uploader("Upload PDFs", type=["pdf"], accept_multiple_files=True)
        
        if st.button("Process & Upload to Cloud"):
            if uploaded_files and db_fs and bucket:
                for file in uploaded_files:
                    with st.spinner(f"Extracting & uploading {file.name}..."):
                        try:
                            reader = PdfReader(io.BytesIO(file.getvalue()))
                            extracted_text = "".join([page.extract_text() + "\n" for page in reader.pages])
                        except:
                            extracted_text = "No text could be extracted."
                        blob = bucket.blob(f"{subject}/{book_level}/{chapter}/{mat_type}/{file.name}")
                        blob.upload_from_string(file.getvalue(), content_type=file.type)
                        db_fs.collection("materials").document().set({
                            "subject": subject, "book_level": book_level, "chapter": chapter,
                            "type": mat_type, "file_name": file.name, "gcs_path": blob.name,
                            "extracted_text": extracted_text[:100000], "timestamp": firestore.SERVER_TIMESTAMP
                        })
                st.success("Saved to Cloud!")
                st.rerun()

    with tab2:
        if db_fs:
            docs = list(db_fs.collection("materials").order_by("timestamp", direction=firestore.Query.DESCENDING).stream())
            for doc in docs:
                data = doc.to_dict()
                col1, col2 = st.columns([5, 1])
                with col1:
                    st.write(f"**{data.get('subject')}** | {data.get('book_level')} | {data.get('chapter')} | {data.get('type')} | `{data.get('file_name')}`")
                with col2:
                    if st.button("🗑️", key=f"del_{doc.id}"):
                        bucket.blob(data['gcs_path']).delete()
                        db_fs.collection("materials").document(doc.id).delete()
                        st.rerun()

    with tab3:
        if work_log_sheet:
            logs = work_log_sheet.get_all_records()
            if logs:
                st.dataframe(pd.DataFrame(logs).iloc[::-1], use_container_width=True)
                
    with tab4:
        if mistakes_sheet:
            try:
                all_mistakes = mistakes_sheet.get_all_records()
                for row in reversed(all_mistakes):
                    with st.expander(f"❌ {row['Question'][:50]}..."):
                        st.write(f"**Richard's Answer:** {row['Richard_Answer']}")
                        st.write(f"**Correct Answer:** {row['Correct_Answer']}")
            except: pass

# ==========================================
# 5. STUDENT VIEW
# ==========================================
else:
    if "mode" not in st.session_state: st.session_state.mode = "home"
    
    if st.session_state.mode == "home":
        st.write("Welcome Richard! Choose your study mode:")
        
        subj = st.selectbox("Subject:", ["Mathematics", "Science"])
        book = st.selectbox("Book:", ["Sec 2A", "Sec 2B"])
        chap = st.selectbox("Chapter:", ["Ch 1", "Ch 2", "Ch 3", "Ch 4"])
        
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("📖 Let's Learn First"):
                st.session_state.mode = "study"
                st.session_state.study_info = (subj, book, chap)
                st.rerun()
        with col2:
            if st.button("📝 Standard Practice"):
                st.session_state.mode = "test"
                st.session_state.test_type = "Knowledge Base (Textbook)"
                st.session_state.test_info = (subj, book, chap)
                st.session_state.q_idx = 0
                st.session_state.answers = {}
                st.session_state.current_test = None
                st.session_state.test_results = None
                st.rerun()
        with col3:
            if st.button("🔥 Hard Mode"):
                st.session_state.mode = "test"
                st.session_state.test_type = "Question Bank (Exam Papers)"
                st.session_state.test_info = (subj, book, chap)
                st.session_state.q_idx = 0
                st.session_state.answers = {}
                st.session_state.current_test = None
                st.session_state.test_results = None
                st.rerun()
                
        st.divider()
        st.subheader("📸 Homework Helper")
        st.write("Upload your homework for auto-grading.")
        if st.button("Upload Homework"):
            st.session_state.mode = "homework"
            st.rerun()

    # --- STUDY MODE ---
    elif st.session_state.mode == "study":
        subj, book, chap = st.session_state.study_info
        st.header(f"📖 Studying: {subj} {book} {chap}")
        
        if st.button("⬅️ Back to Home"):
            st.session_state.mode = "home"
            st.rerun()
            
        with st.spinner("Teacher is reading the textbook and preparing a fun summary..."):
            context_text = ""
            docs = db_fs.collection("materials").where("subject", "==", subj).where("book_level", "==", book).where("chapter", "==", chap).stream()
            for doc in docs:
                context_text += doc.to_dict().get("extracted_text", "")
                
            if len(context_text) < 100:
                st.error("No textbook material found for this chapter.")
            else:
                prompt = f"""You are a fun, encouraging tutor for a 14-year-old student. 
                Read this textbook chapter: {context_text[:8000]}
                
                Explain the key concepts in simple terms. Use a real-world analogy (like money, games, or food) to make it easy to understand. 
                Keep it under 200 words. End with an encouraging message."""
                
                try:
                    summary = ask_ai(prompt)
                    st.info(summary)
                except:
                    st.error("Could not generate summary.")

    # --- HOMEWORK MODE ---
    elif st.session_state.mode == "homework":
        st.header("📸 Homework Auto-Grading")
        uploaded_file = st.file_uploader("Upload a photo or PDF of your work", type=["pdf", "jpg", "png", "jpeg"])
        
        if uploaded_file and st.button("Mark My Work"):
            with st.spinner("Teacher is reading your work..."):
                try:
                    prompt = """You are an MOE Teacher. Read this homework. 
                    Output ONLY a valid JSON array of objects with keys: 'question', 'student_answer', 'correct_answer', 'is_correct' (boolean), 'feedback' (1 short sentence).
                    Format: [{"question": "...", "student_answer": "...", "correct_answer": "...", "is_correct": true, "feedback": "..."}]"""
                    
                    config = types.GenerateContentConfig(response_mime_type="application/json")
                    
                    if uploaded_file.type == "application/pdf":
                        reader = PdfReader(io.BytesIO(uploaded_file.getvalue()))
                        text = "".join([page.extract_text() for page in reader.pages])
                        raw_json = ask_ai(f"{prompt}\n\nText:\n{text}", config=config)
                    else:
                        img = Image.open(io.BytesIO(uploaded_file.getvalue()))
                        response = client.models.generate_content(model="gemini-2.5-flash", contents=[prompt, img], config=config)
                        raw_json = response.text
                        
                    results = json.loads(raw_json)
                    score = 0
                    for i, item in enumerate(results):
                        if item.get("is_correct"): score += 1
                        else:
                            if mistakes_sheet:
                                mistakes_sheet.append_row([str(datetime.now()), "Homework", item.get("question",""), item.get("correct_answer",""), item.get("student_answer","")])
                        with st.expander(f"Q{i+1}: {'✅ Correct' if item.get('is_correct') else '❌ Wrong'}"):
                            st.write(f"**Question:** {item.get('question','')}")
                            st.write(f"**Your Answer:** {item.get('student_answer','')}")
                            st.info(f"**Teacher:** {item.get('feedback','')}")
                    
                    earned_xp = score * 5
                    save_progress(xp + earned_xp)
                    log_work("Homework", "Mixed", "-", f"{score}/{len(results)}", "Graded", earned_xp, "Auto-graded")
                    st.success(f"Grading Complete! You earned {earned_xp} XP.")
                    st.balloons()
                except Exception as e:
                    st.error(f"Could not read the file. Error: {e}")
                    
        if st.button("⬅️ Back"):
            st.session_state.mode = "home"
            st.rerun()

    # --- TEST MODE ---
    elif st.session_state.mode == "test":
        subj, book, chap = st.session_state.test_info
        t_type = st.session_state.test_type
        
        if st.session_state.get("test_results") is None:
            if st.session_state.get("current_test") is None:
                st.header(f"📝 Generating {t_type}...")
                with st.spinner("Teacher is preparing a balanced test (Warm-up to Challenge)..."):
                    context_text = ""
                    docs = db_fs.collection("materials").where("subject", "==", subj).where("book_level", "==", book).where("chapter", "==", chap).where("type", "==", t_type).stream()
                    for doc in docs:
                        context_text += doc.to_dict().get("extracted_text", "") + "\n"
                    
                    context_text = context_text[:10000]
                    
                    prompt = f"""Here is material from Richard's textbook/exam paper:
                    {context_text}
                    
                    Generate exactly 10 multiple-choice questions.
                    
                    IMPORTANT STRUCTURE:
                    - Q1 to Q3: Very basic warm-up questions (to build confidence).
                    - Q4 to Q7: Standard Sec 2 questions.
                    - Q8 to Q10: Challenging word problems.
                    
                    VERY IMPORTANT FORMATTING: If an equation has multiple parts, separate them with a newline (\n) or the word "and".
                    
                    Output ONLY a valid JSON array: [{{"question": "...", "options": ["A) ...", "B) ...", "C) ...", "D) ..."], "answer": "A"}}]
                    """
                    
                    try:
                        config = types.GenerateContentConfig(response_mime_type="application/json")
                        raw_json = ask_ai(prompt, config=config)
                        if raw_json.startswith("```json"): raw_json = raw_json[7:-3]
                        
                        questions_list = json.loads(raw_json)
                        generated_test = {f"Q{i}": {"question": q['question'], "options": q['options'], "answer": q['answer']} for i, q in enumerate(questions_list, 1)}
                        st.session_state.current_test = generated_test
                        st.rerun()
                    except Exception as e:
                        st.error(f"Formatting error. Please try again. Details: {e}")
                        if st.button("Try Again 🔄"): st.rerun()
                        st.stop()

            # DISPLAY TEST
            test_data = st.session_state.current_test
            q_keys = list(test_data.keys())
            total_q = len(q_keys)
            curr_idx = st.session_state.q_idx
            
            if curr_idx < total_q:
                st.header(f"📝 {t_type}: {subj} {book} {chap}")
                st.progress((curr_idx + 1) / total_q)
                q_data = test_data[q_keys[curr_idx]]
                
                st.markdown(f"### Q{curr_idx + 1}: {q_data['question']}")
                ans = st.radio("Select an answer:", ["--- Select ---"] + q_data['options'], key=f"radio_{curr_idx}")
                st.session_state.answers[q_keys[curr_idx]] = ans
                
                # THE ANALOGY HINT
                with st.popover("🆘 I'm Stuck (Need a Hint)"):
                    if st.button("Reveal Hint", key=f"btn_hint_{curr_idx}"):
                        with st.spinner("Thinking of a hint..."):
                            hint_prompt = f"""You are a patient tutor. Richard is stuck on this question: {q_data['question']}.
                            DO NOT give the answer. Give him a hint using a real-world analogy (like money, food, or age).
                            Then ask him a simpler question to help him find the first step."""
                            st.info(f"**Hint:** {ask_ai(hint_prompt)}")
                            
                if st.button("Next Question ➡️" if curr_idx < total_q - 1 else "Submit Test 🚀"):
                    if "--- Select ---" in st.session_state.answers.values():
                        st.warning("Answer all questions first!")
                    elif curr_idx < total_q - 1:
                        st.session_state.q_idx += 1
                        st.rerun()
                    else:
                        st.session_state.test_results = {"user_answers": st.session_state.answers}
                        st.rerun()

        # --- RESULTS & NO-SHAME REVIEW ---
        else:
            st.header(f"📊 Results: {subj} {book} {chap}")
            test_data = st.session_state.current_test
            user_answers = st.session_state.test_results["user_answers"]
            
            total_q = len(test_data)
            score = 0
            for q_key, q_data in test_data.items():
                if user_answers[q_key].startswith(q_data['answer']): score += 1
                    
            # Effort-based XP
            base_xp = (score * 2) + 10 # 10 XP for just finishing!
            result_msg = "Needs Practice"
            if score == total_q:
                st.balloons()
                st.success("🌟 FLAWLESS VICTORY! 🌟 +30 Bonus XP awarded!")
                base_xp += 30
                result_msg = "Perfect"
            elif score >= total_q * 0.8:
                st.balloons()
                st.info("🎉 Great job! You are mastering this!")
                base_xp += 10
                result_msg = "Passed"
            else:
                st.warning("💪 Good effort! Let's review the mistakes below so we can crush it next time.")

            if "Question Bank" in t_type:
                base_xp += 20
                st.info("🔥 HARD MODE BONUS: +20 XP awarded!")
                
            save_progress(xp + base_xp)
            log_work("Test", subj, chap, f"{score}/{total_q}", result_msg, base_xp, f"Completed {t_type}")
            
            st.write(f"🏆 You earned **{base_xp} XP**! (Score: {score}/{total_q})")
            
            st.divider()
            st.subheader("🔍 Review Your Answers")
            
            for i, (q_key, q_data) in enumerate(test_data.items(), 1):
                is_correct = user_answers[q_key].startswith(q_data['answer'])
                correct_opt = next((opt for opt in q_data['options'] if opt.startswith(q_data['answer'])), q_data['answer'])
                
                with st.expander(f"{'✅' if is_correct else '❌'} Q{i}: {q_data['question'][:50]}..."):
                    st.write(f"**Question:** {q_data['question']}")
                    st.write(f"**Your Answer:** {user_answers[q_key]}")
                    st.write(f"**Correct Answer:** {correct_opt}")
                    
                    if not is_correct:
                        if mistakes_sheet:
                            try: mistakes_sheet.append_row([str(datetime.now()), subj, q_data['question'], correct_opt, user_answers[q_key]])
                            except: pass
                            
                        with st.spinner("Teacher is explaining the mistake..."):
                            review_prompt = f"""Richard answered a math question incorrectly. 
                            Question: {q_data['question']}
                            His answer: {user_answers[q_key]}
                            Correct answer: {correct_opt}
                            Explain step-by-step why his answer is wrong and how to get the correct answer. Use a supportive, encouraging tone."""
                            st.info(f"**Teacher:** {ask_ai(review_prompt)}")
            
            if st.button("Return Home 🏠"):
                st.session_state.mode = "home"
                st.session_state.test_results = None
                st.rerun()
