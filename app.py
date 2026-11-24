import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from google import genai
from google.genai import types
import os
import pandas as pd
from datetime import datetime
import random
import json
import io
import time
from pypdf import PdfReader
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

# --- DATABASE CONNECTION (SAFE & PERSISTENT) ---
@st.cache_resource
def get_db():
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        sheet_id = "1Lo-X7A7y0UTgCJqDTiDp87YHtohxOLJF3_qnkvGvXOA" 
        spreadsheet = client.open_by_key(sheet_id)
        
        # Auto-create tabs if they don't exist
        try: progress_sheet = spreadsheet.worksheet("Progress")
        except: progress_sheet = spreadsheet.add_worksheet(title="Progress", rows="10", cols="6")
        
        try: mistakes_sheet = spreadsheet.worksheet("Mistakes")
        except: mistakes_sheet = spreadsheet.add_worksheet(title="Mistakes", rows="1000", cols="5")
            
        return spreadsheet, progress_sheet, mistakes_sheet
    except Exception as e:
        return None, None, None

db, progress_sheet, mistakes_sheet = get_db()

if db and progress_sheet:
    try:
        richard_data = progress_sheet.row_values(2)
        xp = int(richard_data[1]) if len(richard_data) > 1 and richard_data[1] else 0
    except:
        xp = 0
else:
    xp = 0

if xp < 1000: level, badge = "Level 1: Novice 🌱", "🥉 Bronze Scout"
elif xp < 2500: level, badge = "Level 2: Apprentice 📖", "🥈 Silver Explorer"
else: level, badge = "Level 3: Scholar 🧠", "🥇 Gold Master"

def save_progress(new_xp, new_level, new_badge):
    if progress_sheet:
        try: progress_sheet.update('B2:D2', [[new_xp, new_level, new_badge]])
        except: pass

# --- LOGIN SYSTEM ---
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

api_key = st.secrets["GEMINI_API_KEY"]
client = genai.Client(api_key=api_key)

# --- JSON EXTRACTION & GRADING FUNCTION ---
def process_uploaded_file(uploaded_file, is_grading=False):
    """Uses Gemini Pro to extract structured JSON from an image or PDF."""
    
    # 1. Prepare the file data
    file_bytes = uploaded_file.getvalue()
    mime_type = uploaded_file.type
    
    if mime_type == "application/pdf":
        reader = PdfReader(io.BytesIO(file_bytes))
        # Extract text from first 3 pages for prompt context
        text_content = "".join([page.extract_text() + "\n" for page in reader.pages[:3]])
        prompt = f"Extract all questions, options, and the correct answers from this text:\n{text_content}"
        contents = [prompt]
    else:
        # It's an image (JPG, PNG)
        img = Image.open(io.BytesIO(file_bytes))
        prompt = "Read the handwritten or printed math questions in this image."
        contents = [prompt, img]
        
    if is_grading:
        prompt += """
        You are an MOE teacher grading a student's work. 
        For each question, identify the student's handwritten answer, the correct answer, and provide a brief, encouraging feedback.
        """
    else:
        prompt += """
        Extract the questions, options (if any), and the correct answer.
        """
        
    prompt += """
    Output ONLY a valid JSON array matching this structure:
    [
        {
            "question": "...",
            "student_answer": "...", // Leave blank if not grading
            "correct_answer": "...",
            "is_correct": true/false, // Only if grading
            "feedback": "..." // Only if grading
        }
    ]
    """

    # 2. Call Gemini Pro with JSON schema enforcement
    try:
        response = client.models.generate_content(
            model='gemini-2.5-pro',
            contents=contents,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1
            )
        )
        return json.loads(response.text)
    except Exception as e:
        return {"error": str(e)}

if "mode" not in st.session_state: st.session_state.mode = "home"

# --- DEVELOPER DASHBOARD ---
if st.session_state.get("is_dev"):
    st.header("👨‍💻 Parent Dashboard")
    
    tab1, tab2 = st.tabs(["📚 Upload Question Bank", "❌ Mistake Log"])
    
    with tab1:
        st.write("Upload exam papers or textbook pages. The AI will extract the questions into JSON format for the bank.")
        uploaded_papers = st.file_uploader("Upload PDFs/Images", type=["pdf", "jpg", "png", "jpeg"], accept_multiple_files=True)
        
        if st.button("Extract & Save"):
            if uploaded_papers:
                with st.spinner("AI is extracting questions..."):
                    all_extracted = []
                    for paper in uploaded_papers:
                        result = process_uploaded_file(paper, is_grading=False)
                        if isinstance(result, list):
                            all_extracted.extend(result)
                    
                    # Save to a local file for now (or could push to Google Sheets)
                    with open("bank_json.json", "w") as f:
                        json.dump(all_extracted, f)
                    
                    st.success(f"Successfully extracted {len(all_extracted)} questions!")
                    st.json(all_extracted[:2]) # Preview first 2

    with tab2:
        if mistakes_sheet:
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
            st.subheader("📸 Submit Homework for Grading")
            st.write("Take a photo of your completed homework, and I will mark it and explain your mistakes!")
            if st.button("Upload Homework"):
                st.session_state.mode = "upload_hw"
                st.rerun()
                
        with col2:
            st.subheader("📚 Practice Test")
            st.write("Test your knowledge based on the Question Bank.")
            if st.button("Start AI Test"):
                st.session_state.mode = "practice"
                st.rerun()

    elif st.session_state.mode == "upload_hw":
        st.header("📸 Homework Auto-Grading")
        uploaded_file = st.file_uploader("Upload a photo of your work (JPG/PNG) or PDF", type=["pdf", "jpg", "png", "jpeg"])
        
        if uploaded_file and st.button("Grade My Work"):
            with st.spinner("Teacher is reading your handwriting and grading..."):
                result = process_uploaded_file(uploaded_file, is_grading=True)
                
                if isinstance(result, dict) and "error" in result:
                    st.error(f"Could not read the file. Error: {result['error']}")
                else:
                    st.success("Grading complete!")
                    score = 0
                    total = len(result)
                    
                    for i, item in enumerate(result):
                        is_correct = item.get("is_correct", False)
                        if is_correct: score += 1
                        
                        # Log mistakes to Google Sheets
                        if not is_correct and mistakes_sheet:
                            try:
                                mistakes_sheet.append_row([str(datetime.now()), "Homework", item.get("question", ""), item.get("correct_answer", ""), item.get("student_answer", "")])
                            except: pass
                            
                        with st.expander(f"Q{i+1}: {item.get('question', '')} - {'✅ Correct' if is_correct else '❌ Incorrect'}"):
                            st.write(f"**Your Answer:** {item.get('student_answer', '')}")
                            st.write(f"**Correct Answer:** {item.get('correct_answer', '')}")
                            st.info(f"**Teacher's Feedback:** {item.get('feedback', '')}")
                    
                    # Award XP
                    xp_earned = score * 5
                    current_xp = xp + xp_earned
                    save_progress(current_xp, level, badge)
                    st.write(f"### 🏆 You earned **{xp_earned} XP**! (Score: {score}/{total})")
                    
        if st.button("⬅️ Back"):
            st.session_state.mode = "home"
            st.rerun()

    elif st.session_state.mode == "practice":
        st.header("📚 Practice Test")
        st.write("Coming soon: This will pull questions from the extracted Question Bank JSON.")
        if st.button("⬅️ Back"):
            st.session_state.mode = "home"
            st.rerun()
