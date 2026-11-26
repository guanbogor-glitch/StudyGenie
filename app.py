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
from pypdf import PdfReader
from google.cloud import firestore, storage
from google.oauth2 import service_account

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

# --- CLOUD CONNECTIONS (STORAGE & FIRESTORE) ---
@st.cache_resource
def get_cloud_clients():
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = service_account.Credentials.from_service_account_info(creds_dict)
        
        # 1. Firestore Database
        db_fs = firestore.Client(credentials=creds, project=creds_dict["project_id"])
        
        # 2. Cloud Storage
        storage_client = storage.Client(credentials=creds, project=creds_dict["project_id"])
        
        # ⚠️ REPLACE THIS WITH YOUR ACTUAL BUCKET NAME ⚠️
        bucket_name = "studygenie-materials-guan" 
        bucket = storage_client.bucket(bucket_name)
        
        return db_fs, bucket
    except Exception as e:
        st.error(f"Cloud connection error: {e}")
        return None, None

db_fs, bucket = get_cloud_clients()

# --- GOOGLE SHEETS (For XP & Mistakes) ---
@st.cache_resource
def get_sheet():
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        sheet_id = "1Lo-X7A7y0UTgCJqDTiDp87YHtohxOLJF3_qnkvGvXOA" 
        spreadsheet = client.open_by_key(sheet_id)
        return spreadsheet.worksheet("Progress"), spreadsheet.worksheet("Mistakes")
    except: return None, None

progress_sheet, mistakes_sheet = get_sheet()
xp = 0
if progress_sheet:
    try:
        richard_data = progress_sheet.row_values(2)
        xp = int(richard_data[1]) if len(richard_data) > 1 and richard_data[1] else 0
    except: pass

if xp < 1000: level, badge = "Level 1: Novice 🌱", "🥉 Bronze Scout"
elif xp < 2500: level, badge = "Level 2: Apprentice 📖", "🥈 Silver Explorer"
else: level, badge = "Level 3: Scholar 🧠", "🥇 Gold Master"

def save_progress(new_xp, new_level, new_badge):
    if progress_sheet:
        try: progress_sheet.update('B2:D2', [[new_xp, new_level, new_badge]])
        except: pass

api_key = st.secrets["GEMINI_API_KEY"]
client = genai.Client(api_key=api_key)

# --- SIDEBAR ---
with st.sidebar:
    st.header("🏆 Richard's Progress")
    st.subheader(level)
    st.write(f"**Badge:** {badge}")
    st.progress(min(xp / 1000.0, 1.0))
    st.write(f"**XP:** {xp} / 1000")
    
    st.divider()
    st.header("🔐 Login")
    user_mode = st.radio("Mode:", ["Student", "Developer"])
    if user_mode == "Developer":
        if st.text_input("Password:", type="password") == "parent123":
            st.session_state.is_dev = True
            st.success("Dev Access ✅")
        else:
            st.session_state.is_dev = False
    else:
        st.session_state.is_dev = False

# --- DEVELOPER DASHBOARD ---
if st.session_state.get("is_dev"):
    st.header("👨‍💻 Parent Dashboard")
    
    tab1, tab2, tab3 = st.tabs(["📚 Upload Materials", "📂 Cloud Database", "❌ Mistake Log"])
    
    with tab1:
        st.write("Upload scanned PDFs. They will be saved permanently in the Google Cloud.")
        
        col1, col2 = st.columns(2)
        with col1:
            subject = st.selectbox("Subject:", ["Mathematics", "Science", "English"])
            chapter = st.text_input("Chapter (e.g., Ch 1):")
        with col2:
            material_type = st.radio("Type:", ["Knowledge Base (Textbook)", "Question Bank (Exam Papers)"])
            
        uploaded_files = st.file_uploader("Upload PDFs", type=["pdf"], accept_multiple_files=True)
        
        if st.button("Upload to Cloud"):
            if uploaded_files and db_fs and bucket:
                for file in uploaded_files:
                    with st.spinner(f"Uploading {file.name}..."):
                        # 1. Upload actual file to Cloud Storage
                        blob = bucket.blob(f"{subject}/{material_type}/{file.name}")
                        blob.upload_from_string(file.getvalue(), content_type=file.type)
                        
                        # 2. Save metadata to Firestore Database
                        doc_ref = db_fs.collection("materials").document()
                        doc_ref.set({
                            "subject": subject,
                            "chapter": chapter,
                            "type": material_type,
                            "file_name": file.name,
                            "gcs_path": blob.name,
                            "timestamp": firestore.SERVER_TIMESTAMP
                        })
                st.success("All files uploaded permanently to the Cloud!")
                st.rerun()

    with tab2:
        st.subheader("☁️ Files in Cloud Database")
        if db_fs:
            docs = db_fs.collection("materials").stream()
            for doc in docs:
                data = doc.to_dict()
                st.write(f"- **{data['subject']}** | {data['chapter']} | {data['type']} | `{data['file_name']}`")
        else:
            st.info("No materials found.")
            
    with tab3:
        if mistakes_sheet:
            try:
                all_mistakes = mistakes_sheet.get_all_records()
                for row in reversed(all_mistakes):
                    with st.expander(f"❌ {row['Question'][:50]}..."):
                        st.write(f"**Richard's Answer:** {row['Richard_Answer']}")
                        st.write(f"**Correct Answer:** {row['Correct_Answer']}")
            except: st.info("No mistakes logged yet.")

# --- STUDENT VIEW ---
else:
    if st.session_state.get("mode") is None:
        st.session_state.mode = "home"
        
    if st.session_state.mode == "home":
        st.write("Welcome Richard! Choose your study mode:")
        
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("📚 Smart Practice")
            st.write("Test yourself using the materials uploaded by your Dad.")
            if st.button("Start AI Test"):
                st.session_state.mode = "practice"
                st.rerun()
                
        with col2:
            st.subheader("📸 Homework Helper")
            if st.button("Upload Homework"):
                st.info("Auto-grading feature coming in the next update!")
                
    elif st.session_state.mode == "practice":
        st.header("📚 Smart Practice Test")
        st.info("The AI is now reading your cloud PDFs to generate tests. Code integration coming next!")
        if st.button("⬅️ Back"):
            st.session_state.mode = "home"
            st.rerun()
