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
    try: xp = int(progress_sheet.row_values(2)[1])
    except: pass

if xp < 1000: level, badge = "Level 1: Novice 🌱", "🥉 Bronze Scout"
elif xp < 2500: level, badge = "Level 2: Apprentice 📖", "🥈 Silver Explorer"
else: level, badge = "Level 3: Scholar 🧠", "🥇 Gold Master"

def save_progress(new_xp):
    if progress_sheet and not st.session_state.get('test_mode'):
        try: progress_sheet.update('B2', [[new_xp]])
        except: pass

def log_work(activity, subject, chapter, score, result, xp_earned, note):
    if work_log_sheet and not st.session_state.get('test_mode'):
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
    
    if "is_dev" not in st.session_state: st.session_state.is_dev = False
    if "test_mode" not in st.session_state: st.session_state.test_mode = False

    if user_mode == "Developer (Parent)":
        if st.text_input("Password:", type="password") == "parent123":
            st.session_state.is_dev = True
            st.success("Dev Access ✅")
            st.session_state.test_mode = st.checkbox("🧪 Test as Student (No Progress Saved)")
            if st.session_state.test_mode:
                st.info("⚠️ TEST MODE ACTIVE: XP and mistakes will NOT be saved.")
        else:
            st.session_state.is_dev = False
            st.session_state.test_mode = False
    else:
        st.session_state.is_dev = False
        st.session_state.test_mode = False

# ==========================================
# 4. DEVELOPER DASHBOARD
# ==========================================
if st.session_state.get("is_dev") and not st.session_state.get("test_mode"):
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
            try:
                logs = work_log_sheet.get_all_records()
                if logs:
                    df = pd.DataFrame(logs)
                    st.dataframe(df.iloc[::-1], use_container_width=True)
                else:
                    st.info("Work log is currently empty.")
            except Exception as e:
                st.warning("Could not read Work Log.")
                
    with tab4:
        if mistakes_sheet:
            try:
                all_mistakes = mistakes_sheet.get_all_records()
                for row in reversed(all_mistakes):
                    with st.expander(f"❌ {row['Question'][:50]}..."):
                        st.write(f"**Richard's Answer:** {row['Richard_Answer']}")
                        st.write(f"**Correct Answer:** {row['Correct_Answer']}")
            except: st.info("No mistakes logged yet.")

# ==========================================
# 5. STUDENT VIEW (Also used for Test Mode)
# ==========================================
else:
    if st.session_state.get("test_mode"):
        st.warning("🧪 **YOU ARE IN TEST MODE.** Progress will not be saved.")
        
    if "mode" not in st.session_state: st.session_state.mode = "home"
    
    if st.session_state.mode == "home":
        st.write("Welcome Richard! Choose your study mode:")
        
        subj = st.selectbox("Subject:", ["Mathematics", "Science"])
        book = st.selectbox("Book:", ["Sec 2A", "Sec 2B"])
        chap = st.selectbox("Chapter:", ["Ch 1", "Ch 2", "Ch 3", "Ch 4"])
        
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("🧑‍🏫 1-on-1 Teaching"):
                st.session_state.mode = "study_chat"
                st.session_state.study_info = (subj, book, chap)
                st.session_state.chat_history = []
                st.session_state.study_started = False
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
        if st.button("Upload Homework"):
            st.session_state.mode = "homework"
            st.rerun()

    # --- INTERACTIVE 1-ON-1 STUDY MODE ---
    elif st.session_state.mode == "study_chat":
        subj, book, chap = st.session_state.study_info
        st.header(f"🧑‍🏫 1-on-1 Lesson: {subj} {book} {chap}")
        
        # INITIATE THE FIRST LESSON
        if not st.session_state.study_started:
            with st.spinner("Teacher is reading the textbook and preparing the first concept..."):
                context_text = ""
                docs = db_fs.collection("materials").where("subject", "==", subj).where("book_level", "==", book).where("chapter", "==", chap).stream()
                for doc in docs:
                    context_text += doc.to_dict().get("extracted_text", "")
                
                if len(context_text) < 100:
                    st.error("No textbook material found.")
                else:
                    st.session_state.textbook_text = context_text[:8000]
                    
                    # ASK AI TO GENERATE THE FIRST EXPLANATION
                    initial_prompt = f"""You are a patient, fun 1-on-1 MOE tutor for Richard. 
                    Textbook Context: {st.session_state.textbook_text}
                    
                    TASK:
                    1. Read the textbook context.
                    2. Explain the VERY FIRST concept of this chapter in simple terms. Use an analogy if possible. 
                    3. Keep it under 4 sentences.
                    4. End by asking Richard ONE simple question to test his understanding.
                    
                    DO NOT say "Here is the first concept". Just start explaining it directly.
                    """
                    
                    try:
                        first_response = ask_ai(initial_prompt)
                        st.session_state.chat_history.append({"role": "assistant", "content": first_response})
                    except Exception as e:
                        st.error(f"Failed to load lesson. Error: {e}")
                        
                    st.session_state.study_started = True
                    st.rerun()

        # Display Chat History
        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        # Chat Input
        if prompt := st.chat_input("Type your answer here..."):
            st.session_state.chat_history.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    history_str = "\n".join([f"{m['role']}: {m['content']}" for m in st.session_state.chat_history])
                    
                    chat_prompt = f"""You are a patient, fun 1-on-1 MOE tutor for Richard. 
                    Textbook Context: {st.session_state.textbook_text}
                    
                    Conversation so far:
                    {history_str}
                    
                    RULES:
                    1. Do NOT give a huge wall of text.
                    2. If Richard answered your last question correctly, praise him and explain the NEXT small concept. Then ask a slightly harder question.
                    3. If he answered wrong, gently correct him and ask a simpler question.
                    4. Continue this loop for 5 successful steps. At the 5th step, tell him "Great job! You are ready for the test now. Click Back to Home to start the test."
                    """
                    
                    response = ask_ai(chat_prompt)
                    st.session_state.chat_history.append({"role": "assistant", "content": response})
                    st.markdown(response)

        if st.button("⬅️ Back to Home"):
            st.session_state.mode = "home"
            st.rerun()

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
                            if mistakes_sheet and not st.session_state.get('test_mode'):
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
                    
                    STRUCTURE:
                    - Q1 to Q3: Very basic warm-up.
                    - Q4 to Q7: Standard Sec 2 questions.
                    - Q8 to Q10: Challenging word problems.
                    
                    CRITICAL FORMATTING RULE: 
                    If a question has multiple equations, you MUST format them with the word 'AND' on a new line. 
                    Example: 
                    2x + y = 10
                    AND
                    x - y = 2
                    DO NOT put them on the same line.
                    
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
                
                with st.popover("🆘 I'm Stuck (Need a Hint)"):
                    if st.button("Reveal Hint", key=f"btn_hint_{curr_idx}"):
                        with st.spinner("Thinking of a hint..."):
                            hint_prompt = f"""Richard is stuck on this math question: {q_data['question']}.
                            The correct answer is {q_data['answer']}.
                            RULES:
                            1. Do not use fluffy words like "Don't worry" or "You can do it".
                            2. Give him the FIRST mathematical step. 
                            3. For example, say "Look at the first equation. Substitute x = 4 into it."
                            """
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
                    
            base_xp = (score * 2) + 10
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
                        if mistakes_sheet and not st.session_state.get('test_mode'):
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
