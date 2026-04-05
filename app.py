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

# === FEATURE 4: CONTACT DETAILS FOR FOOTER ===
st.sidebar.markdown("---")
st.sidebar.header("🏢 Contact Details (Footer)")
inst_address = st.sidebar.text_input("Institute Address", value="123 Education Lane, City")
inst_contact = st.sidebar.text_input("Contact Number", value="+91 9876543210")

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

def build_question_prompt(mcq_c, mcq_d, fib_c, fib_d, tf_c, tf_d, short_c, short_d, long_c, long_d, include_answers):
    reqs = []
    if mcq_c > 0: reqs.append(f"- {mcq_c} Multiple Choice Questions (Diff: {mcq_d}). Provide 4 options.")
    if fib_c > 0: reqs.append(f"- {fib_c} Fill in the Blanks (Diff: {fib_d}).")
    if tf_c > 0:  reqs.append(f"- {tf_c} True/False Questions (Diff: {tf_d}).")
    if short_c > 0: reqs.append(f"- {short_c} Short Answer Questions (Diff: {short_d}).")
    if long_c > 0:  reqs.append(f"- {long_c} Long Answer Questions (Diff: {long_d}).")
    if not reqs: return "No questions requested."
    
    if include_answers:
        return "\n".join(reqs) + "\n\n*CRITICAL: Put ALL the answers/solutions at the very end of the document. You MUST use the exact English heading '# Answer Key' for this section. Do NOT write answers immediately after the questions.*"
    else:
        return "\n".join(reqs) + "\n\n*CRITICAL: DO NOT provide any answers, solutions, or answer keys. Provide ONLY the questions. Stop generating after the last question.*"

def get_board_instructions(board):
    if board == "CBSE": return "CRITICAL BOARD FORMAT: Structure the paper strictly matching CBSE board exam patterns. Group questions logically into Sections. Add standard CBSE General Instructions at the top."
    elif board == "ICSE": return "CRITICAL BOARD FORMAT: Structure the paper strictly matching ICSE board exam patterns. Add standard ICSE General Instructions."
    elif board == "BSEB (Bihar Board)": return "CRITICAL BOARD FORMAT: Structure the paper strictly matching BSEB (Bihar School Examination Board) patterns. Divide into 'Section-A: Objective Type' and 'Section-B: Subjective Type'. Add standard BSEB General Instructions."
    else: return "Format the paper beautifully as a standard ready-to-print exam paper with clear sections."

def get_language_instructions(lang):
    if lang == "Hindi": return "CRITICAL LANGUAGE FORMAT: Generate the ENTIRE exam paper strictly in Hindi language."
    elif lang == "Bilingual (English + Hindi)": return "CRITICAL LANGUAGE FORMAT: Generate the exam paper in a BILINGUAL format. For every instruction and every question, write it first in English, immediately followed by its exact translation in Hindi below it."
    else: return "CRITICAL LANGUAGE FORMAT: Generate the paper in English."

# UPDATED: Passing Branding details to HTML
def create_a4_html(md_content, i_name, i_address, i_contact):
    md_content = md_content.replace("# Answer Key", "<div style='page-break-before: always;'></div>\n# Answer Key")
    md_content = md_content.replace("# ANSWER KEY", "<div style='page-break-before: always;'></div>\n# ANSWER KEY")
    md_content = md_content.replace("## Answer Key", "<div style='page-break-before: always;'></div>\n## Answer Key")

    html_body = markdown.markdown(md_content)
    
    # Custom Footer HTML
    footer_html = f"""
    <div class="footer">
        <p><strong>{i_name}</strong> | 📍 {i_address} | 📞 {i_contact}</p>
        <p style="font-size: 12px; color: #888; margin-top: 5px;"><em>Generated securely by PaperBanao AI</em></p>
    </div>
    """
    
    html_template = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>Question Paper</title>
        <script>
          MathJax = {{ tex: {{ inlineMath: [['$', '$'], ['\\\\(', '\\\\)']], displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']] }} }};
        </script>
        <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
        <style>
            body {{ background-color: #f0f0f0; font-family: 'Times New Roman', Times, serif; margin: 0; padding: 20px; display: flex; justify-content: center; }}
            .a4-page {{ background-color: white; width: 210mm; min-height: 297mm; padding: 20mm; box-sizing: border-box; box-shadow: 0 0 10px rgba(0,0,0,0.2); position: relative; }}
            @media print {{ body {{ background-color: white; padding: 0; display: block; }} .a4-page {{ box-shadow: none; width: 100%; padding: 0; margin: 0; min-height: auto; }} @page {{ size: A4; margin: 20mm; }} }}
            h1, h2, h3 {{ text-align: center; color: #111; }} p, li {{ font-size: 16px; line-height: 1.5; color: #000; }} hr {{ border: 1px solid #ccc; margin: 20px 0; }}
            mjx-container {{ max-width: 100%; overflow-x: auto; overflow-y: hidden; }}
            
            /* Footer Styling */
            .footer {{ margin-top: 50px; padding-top: 15px; border-top: 2px dashed #bbb; text-align: center; font-size: 14px; color: #444; page-break-inside: avoid; }}
            .footer p {{ margin: 2px 0; font-size: 14px; color: #444; }}
        </style>
    </head>
    <body>
        <div class="a4-page">
            {html_body}
            {footer_html}
        </div>
    </body>
    </html>
    """
    return html_template

# ==========================================
# --- 1. CHOOSE PAPER SOURCE (TOP) ---
# ==========================================
st.markdown("### 1. Choose Paper Source")
source_choice = st.radio("Select Method:", ["⚡ Quick Generate (By Syllabus)", "📄 Deep Extract (From PDF Book)"], horizontal=True, label_visibility="collapsed")

sub1, grade1, syl1 = "", "", ""
up_pdf, start_p, end_p, sub2, top2 = None, 1, 5, "", ""

if "Syllabus" in source_choice:
    st.info("Best for general tests without strict textbook boundaries.")
    col1, col2 = st.columns(2)
    with col1: sub1 = st.text_input("Subject (e.g., Science)")
    with col2: grade1 = st.text_input("Class / Grade")
    syl1 = st.text_area("Paste Syllabus or Topics to Cover", placeholder="e.g., Light reflection, Newton's laws...")
else:
    st.info("Best when you want questions extracted ONLY from the provided text.")
    up_pdf = st.file_uploader("Upload Book/Chapter (PDF)", type="pdf")
    col4, col5 = st.columns(2)
    with col4: start_p = st.number_input("Start Page", min_value=1, value=1)
    with col5: end_p = st.
