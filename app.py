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
        
        # ⚠️ REPLACE THIS WITH YOUR ACTUAL BUCKET NAME ⚠️
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
        
        # ⚠️ YOUR GOOGLE SHEET ID ⚠️
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

# ==========================================
# 2. XP & HELPER FUNCTIONS
# ==========================================
xp = 0
if progress_sheet:
    try:
        richard_data = progress_sheet.row_values(2)
        xp = int(richard_data[1]) if len(richard_data) > 1 and richard_data[1] else 0
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
# 3. SIDEBAR (LOGIN & XP)
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
        st.write("Upload materials to Google Cloud. The AI will extract the text to generate tests.")
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
                    with st.spinner(f"Extracting text & uploading {file.name}..."):
                        try:
                            reader = PdfReader(io.BytesIO(file.getvalue()))
                            extracted_text = "".join([page.extract_text() + "\n" for page in reader.pages])
                        except:
                            extracted_text = "No text could be extracted."
                            
                        blob = bucket.blob(f"{subject}/{book_level}/{chapter}/{mat_type}/{file.name}")
                        blob.upload_from_string(file.getvalue(), content_type=file.type)
                        
                        doc_ref = db_fs.collection("materials").document()
                        doc_ref.set({
                            "subject": subject,
                            "book_level": book_level,
                            "chapter": chapter,
                            "type": mat_type,
                            "file_name": file.name,
                            "gcs_path": blob.name,
                            "extracted_text": extracted_text[:100000],
                            "timestamp": firestore.SERVER_TIMESTAMP
                        })
                st.success("Files and text saved to Cloud!")
                st.rerun()

    with tab2:
        st.subheader("☁️ Files in Cloud Database")
        if db_fs:
            docs = list(db_fs.collection("materials").order_by("timestamp", direction=firestore.Query.DESCENDING).stream())
            if not docs:
                st.info("No materials found.")
            else:
                for doc in docs:
                    data = doc.to_dict()
                    col1, col2 = st.columns([5, 1])
                    with col1:
                        text_len = len(data.get('extracted_text', ''))
                        st.write(f"**{data.get('subject')}** | {data.get('book_level')} | {data.get('chapter')} | {data.get('type')} | `{data.get('file_name')}` | Text: {text_len} chars")
                    with col2:
                        if st.button("🗑️", key=f"del_{doc.id}"):
                            try:
                                bucket.blob(data['gcs_path']).delete()
                                db_fs.collection("materials").document(doc.id).delete()
                                st.success("Deleted!")
                                st.rerun()
                            except: st.error("Error deleting.")

    with tab3:
        st.subheader("📈 XP Progress Chart")
        if progress_sheet:
            try:
                chart_data = pd.DataFrame({"Date": ["Start", "Week 1", "Week 2", "Today"], "XP": [0, int(xp*0.2), int(xp*0.6), xp]})
                fig = px.line(chart_data, x="Date", y="XP", markers=True)
                st.plotly_chart(fig, use_container_width=True)
            except: pass
            
        st.subheader("📝 Work Log (Recent Activities)")
        if work_log_sheet:
            try:
                logs = work_log_sheet.get_all_records()
                if logs:
                    df = pd.DataFrame(logs)
                    st.dataframe(df.iloc[::-1], use_container_width=True)
                else:
                    st.info("No work logged yet.")
            except: st.info("No data yet.")

    with tab4:
        st.subheader("❌ Mistake Log")
        if mistakes_sheet:
            try:
                all_mistakes = mistakes_sheet.get_all_records()
                for row in reversed(all_mistakes):
                    with st.expander(f"❌ {row['Question'][:50]}..."):
                        st.write(f"**Richard's Answer:** {row['Richard_Answer']}")
                        st.write(f"**Correct Answer:** {row['Correct_Answer']}")
            except: st.info("No mistakes logged yet.")

# ==========================================
# 5. STUDENT VIEW
# ==========================================
else:
    if "mode" not in st.session_state: st.session_state.mode = "home"
    
    if st.session_state.mode == "home":
        st.write("Welcome Richard! Choose your study mode:")
        
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("📚 Smart Practice")
            subj = st.selectbox("Subject:", ["Mathematics", "Science"])
            book = st.selectbox("Book:", ["Sec 2A", "Sec 2B"])
            chap = st.selectbox("Chapter:", ["Ch 1", "Ch 2", "Ch 3", "Ch 4"])
            
            c1, c2 = st.columns(2)
            if c1.button("Standard Practice"):
                st.session_state.mode = "test"
                st.session_state.test_type = "Knowledge Base (Textbook)"
                st.session_state.test_info = (subj, book, chap)
                st.session_state.q_idx = 0
                st.session_state.answers = {}
                st.session_state.current_test = None
                st.session_state.test_results = None
                st.rerun()
                
            if c2.button("🔥 Hard Mode"):
                st.session_state.mode = "test"
                st.session_state.test_type = "Question Bank (Exam Papers)"
                st.session_state.test_info = (subj, book, chap)
                st.session_state.q_idx = 0
                st.session_state.answers = {}
                st.session_state.current_test = None
                st.session_state.test_results = None
                st.rerun()
                
        with col2:
            st.subheader("📸 Homework Helper")
            st.write("Upload your homework for auto-grading.")
            if st.button("Upload Homework"):
                st.session_state.mode = "homework"
                st.rerun()

    elif st.session_state.mode == "homework":
        st.header("📸 Homework Auto-Grading")
        uploaded_file = st.file_uploader("Upload a photo or PDF of your work", type=["pdf", "jpg", "png", "jpeg"])
        
        if uploaded_file and st.button("Mark My Work"):
            with st.spinner("Teacher is reading your handwriting and grading..."):
                try:
                    prompt = """You are an MOE Teacher. Read this homework. 
                    Output ONLY a valid JSON array of objects with keys: 'question', 'student_answer', 'correct_answer', 'is_correct' (boolean), 'feedback' (1 short sentence).
                    Format: [{"question": "...", "student_answer": "...", "correct_answer": "...", "is_correct": true, "feedback": "..."}]"""
                    
                    if uploaded_file.type == "application/pdf":
                        reader = PdfReader(io.BytesIO(uploaded_file.getvalue()))
                        text = "".join([page.extract_text() for page in reader.pages])
                        response = client.models.generate_content(
                            model="gemini-2.5-pro",
                            contents=[prompt, f"Here is the text:\n{text}"],
                            config=types.GenerateContentConfig(response_mime_type="application/json")
                        )
                    else:
                        img = Image.open(io.BytesIO(uploaded_file.getvalue()))
                        response = client.models.generate_content(
                            model="gemini-2.5-pro",
                            contents=[prompt, img],
                            config=types.GenerateContentConfig(response_mime_type="application/json")
                        )
                        
                    results = json.loads(response.text)
                    
                    score = 0
                    for i, item in enumerate(results):
                        if item.get("is_correct"): score += 1
                        else:
                            if mistakes_sheet:
                                mistakes_sheet.append_row([str(datetime.now()), "Homework", item.get("question",""), item.get("correct_answer",""), item.get("student_answer","")])
                                
                        with st.expander(f"Q{i+1}: {item.get('question','')} - {'✅ Correct' if item.get('is_correct') else '❌ Wrong'}"):
                            st.write(f"**Your Answer:** {item.get('student_answer','')}")
                            st.write(f"**Correct Answer:** {item.get('correct_answer','')}")
                            st.info(f"**Teacher:** {item.get('feedback','')}")
                    
                    earned_xp = score * 5
                    new_xp = xp + earned_xp
                    save_progress(new_xp)
                    log_work("Homework", "Mixed", "-", f"{score}/{len(results)}", "Graded", earned_xp, "Auto-graded by AI")
                    
                    st.success(f"Grading Complete! You earned {earned_xp} XP.")
                    st.balloons()
                    
                except Exception as e:
                    st.error(f"Could not read the file clearly. Error: {e}")
                    
        if st.button("⬅️ Back"):
            st.session_state.mode = "home"
            st.rerun()

    elif st.session_state.mode == "test":
        subj, book, chap = st.session_state.test_info
        t_type = st.session_state.test_type
        
        if st.session_state.get("test_results") is None:
            if st.session_state.get("current_test") is None:
                st.header(f"📝 Generating {t_type}: {subj} {book} {chap}")
                if not db_fs:
                    st.error("Database offline.")
                    if st.button("Back"): st.session_state.mode = "home"; st.rerun()
                    st.stop()
                    
                with st.spinner("Teacher is reading your textbook and generating a smart test..."):
                    context_text = ""
                    docs_ch = db_fs.collection("materials").where("subject", "==", subj).where("book_level", "==", book).where("chapter", "==", chap).where("type", "==", t_type).stream()
                    for doc in docs_ch:
                        context_text += doc.to_dict().get("extracted_text", "") + "\n"
                        
                    docs_all = db_fs.collection("materials").where("subject", "==", subj).where("book_level", "==", book).where("chapter", "==", "All Chapters").stream()
                    for doc in docs_all:
                        context_text += doc.to_dict().get("extracted_text", "") + "\n"
                    
                    # If no text found, use fallback
                    if len(context_text) < 100:
                        context_text = f"Standard MOE Secondary 2 Mathematics questions for {chap}."
                    
                    context_text = context_text[:10000] # Limit to avoid token overflow
                    
                    # Use JSON Mode for 5 questions at once (Much more reliable)
                    prompt = f"""Here is material from Richard's textbook/exam paper for {chap}:
                    {context_text}
                    
                    Generate exactly 5 multiple-choice questions based on this material. They should be MOE Sec 2 difficulty.
                    Output ONLY a valid JSON array of objects with keys: 'question', 'options' (array of 4 strings like 'A) ...'), 'answer' (e.g., 'A').
                    """
                    
                    try:
                        response = client.models.generate_content(
                            model="gemini-2.5-pro",
                            contents=prompt,
                            config=types.GenerateContentConfig(response_mime_type="application/json")
                        )
                        raw_json = response.text
                        # Sometimes AI wraps in markdown, clean it
                        if raw_json.startswith("```json"):
                            raw_json = raw_json[7:-3]
                        
                        questions_list = json.loads(raw_json)
                        
                        generated_test = {}
                        for i, q in enumerate(questions_list, 1):
                            generated_test[f"Q{i}"] = {
                                "question": q['question'],
                                "options": q['options'],
                                "answer": q['answer']
                            }
                        st.session_state.current_test = generated_test
                        st.rerun()
                        
                    except Exception as e:
                        st.error(f"AI formatting error. Please try again. Details: {e}")
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
                        with st.spinner("Thinking..."):
                            hint_prompt = f"Give a Socratic hint for this question without revealing the answer: {q_data['question']}"
                            hint_res = client.models.generate_content(model="gemini-2.5-pro", contents=hint_prompt)
                            st.info(f"**Hint:** {hint_res.text}")
                            
                if st.button("Next Question ➡️" if curr_idx < total_q - 1 else "Submit Test 🚀"):
                    if "--- Select ---" in st.session_state.answers.values():
                        st.warning("Answer all questions first!")
                    elif curr_idx < total_q - 1:
                        st.session_state.q_idx += 1
                        st.rerun()
                    else:
                        st.session_state.test_results = {"user_answers": st.session_state.answers}
                        st.rerun()

        # --- RESULTS VIEW ---
        else:
            st.header(f"📊 Results: {subj} {book} {chap}")
            test_data = st.session_state.current_test
            user_answers = st.session_state.test_results["user_answers"]
            
            total_q = len(test_data) # <--- THIS FIXES THE ERROR
            score = 0
            for q_key, q_data in test_data.items():
                if user_answers[q_key].startswith(q_data['answer']): score += 1
                    
            st.subheader(f"Score: {score}/{total_q}")
            
            base_xp = score * 2
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
                
            if "Question Bank" in t_type:
                base_xp += 20
                st.warning("🔥 HARD MODE BONUS: +20 XP awarded!")
                
            current_xp = xp + base_xp
            save_progress(current_xp)
            log_work("Test", subj, chap, f"{score}/{total_q}", result_msg, base_xp, f"Completed {t_type}")
            
            st.write(f"🏆 You earned **{base_xp} XP**!")
            
            if score < total_q and mistakes_sheet:
                for q_key, q_data in test_data.items():
                    if not user_answers[q_key].startswith(q_data['answer']):
                        correct_opt = next((opt for opt in q_data['options'] if opt.startswith(q_data['answer'])), q_data['answer'])
                        try: mistakes_sheet.append_row([str(datetime.now()), subj, q_data['question'], correct_opt, user_answers[q_key]])
                        except: pass
            
            if st.button("Return Home 🏠"):
                st.session_state.mode = "home"
                st.session_state.test_results = None
                st.rerun()
