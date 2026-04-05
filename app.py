import streamlit as st
import google.generativeai as genai
import PyPDF2
import os
import markdown

# --- Page Config ---
st.set_page_config(page_title="PaperBanao - AI Question Paper", page_icon="📝", layout="centered")

# --- INITIALIZE SESSION STATE (MEMORY FOR EDITING) ---
if "paper_content" not in st.session_state:
    st.session_state.paper_content = ""
if "file_name" not in st.session_state:
    st.session_state.file_name = "PaperBanao_Exam.html"

# --- App Header & App Logo ---
col_logo, col_title = st.columns([1, 5])
with col_logo:
    if os.path.exists("logo.png"):
        st.image("logo.png", width=80)
    else:
        st.markdown("<h1>📝</h1>", unsafe_allow_html=True) 
with col_title:
    st.title("PaperBanao")
    st.markdown("Generate precise, multi-format question papers in seconds using AI.")

# ==========================================
# --- SIDEBAR: SETTINGS & INSTITUTE DETAILS ---
# ==========================================
st.sidebar.header("⚙️ System Settings")
api_key = st.sidebar.text_input("Enter Google Gemini API Key:", type="password")

# --- AUTO-DETECT MODEL LOGIC ---
working_model_name = "gemini-1.5-flash" 
if api_key:
    genai.configure(api_key=api_key)
    try:
        valid_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        if valid_models:
            flash_models = [m for m in valid_models if '1.5-flash' in m]
            working_model_name = flash_models[0] if flash_models else valid_models[0]
        st.sidebar.success("✅ API Connected!")
    except Exception as e:
        st.sidebar.error("Invalid API Key or Network Issue.")
else:
    st.sidebar.warning("Please enter your API key to start.")

st.sidebar.markdown("---")
st.sidebar.header("🏫 Institute Details")

inst_logo = st.sidebar.file_uploader("Upload Institute Logo", type=["png", "jpg", "jpeg"])
inst_name = st.sidebar.text_input("Institute / School Name", value="My Success Academy")
exam_time = st.sidebar.text_input("Exam Time (Duration)", value="2 Hours")
max_marks = st.sidebar.number_input("Maximum Marks", min_value=1, value=50)

st.sidebar.markdown("---")
st.sidebar.header("📜 Exam Format & Language")
board_format = st.sidebar.selectbox(
    "Select Board Pattern", 
    ["Standard / Default", "BSEB (Bihar Board)", "CBSE", "ICSE"]
)

paper_language = st.sidebar.selectbox(
    "Paper Language", 
    ["English", "Hindi", "Bilingual (English + Hindi)"]
)

# === FEATURE 3: ANSWER KEY TOGGLE ===
st.sidebar.markdown("---")
st.sidebar.header("🔑 Output Settings")
include_answer_key = st.sidebar.toggle("Include Answer Key at the end", value=True)


# --- Helper Functions ---
def extract_text_from_pdf(uploaded_file, start_page, end_page):
    try:
        reader = PyPDF2.PdfReader(uploaded_file)
        total_pages = len(reader.pages)
        start_index = max(0, start_page - 1) 
        end_index = min(total_pages, end_page)
        extracted_text = ""
        for i in range(start_index, end_index):
            extracted_text += reader.pages[i].extract_text() + "\n"
        return extracted_text
    except Exception as e:
        return f"Error reading PDF: {e}"

# UPDATED: Added include_answers parameter
def build_question_prompt(mcq_c, mcq_d, fib_c, fib_d, tf_c, tf_d, short_c, short_d, long_c, long_d, include_answers):
    reqs = []
    if mcq_c > 0: reqs.append(f"- {mcq_c} Multiple Choice Questions (Diff: {mcq_d}). Provide 4 options.")
    if fib_c > 0: reqs.append(f"- {fib_c} Fill in the Blanks (Diff: {fib_d}).")
    if tf_c > 0:  reqs.append(f"- {tf_c} True/False Questions (Diff: {tf_d}).")
    if short_c > 0: reqs.append(f"- {short_c} Short Answer Questions (Diff: {short_d}).")
    if long_c > 0:  reqs.append(f"- {long_c} Long Answer Questions (Diff: {long_d}).")
    if not reqs: return "No questions requested."
    
    # Conditional AI Command based on Toggle
    if include_answers:
        return "\n".join(reqs) + "\n\n*CRITICAL: Put ALL the answers/solutions at the very end of the document. You MUST use the exact English heading '# Answer Key' for this section. Do NOT write answers immediately after the questions.*"
    else:
        return "\n".join(reqs) + "\n\n*CRITICAL: DO NOT provide any answers, solutions, or answer keys. Provide ONLY the questions. Stop generating after the last question.*"

def get_board_instructions(board):
