import streamlit as st
import google.generativeai as genai
import PyPDF2
import os
import markdown

# --- Page Config ---
st.set_page_config(page_title="PaperBanao - AI Question Paper", page_icon="📝", layout="centered")

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
st.sidebar.header("📜 Exam Format")
board_format = st.sidebar.selectbox(
    "Select Board Pattern", 
    ["Standard / Default", "BSEB (Bihar Board)", "CBSE", "ICSE"]
)

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

def build_question_prompt(mcq_c, mcq_d, fib_c, fib_d, tf_c, tf_d, short_c, short_d, long_c, long_d):
    reqs = []
    if mcq_c > 0: reqs.append(f"- {mcq_c} Multiple Choice Questions (Diff: {mcq_d}). Provide 4 options.")
    if fib_c > 0: reqs.append(f"- {fib_c} Fill in the Blanks (Diff: {fib_d}).")
    if tf_c > 0:  reqs.append(f"- {tf_c} True/False Questions (Diff: {tf_d}).")
    if short_c > 0: reqs.append(f"- {short_c} Short Answer Questions (Diff: {short_d}).")
    if long_c > 0:  reqs.append(f"- {long_c} Long Answer Questions (Diff: {long_d}).")
    
    if not reqs: return "No questions requested."
    return "\n".join(reqs) + "\n\n*CRITICAL: Put ALL the answers/solutions at the very end of the document. You MUST use the exact heading '# Answer Key' for this section. Do NOT write answers immediately after the questions.*"

def get_board_instructions(board):
    if board == "CBSE":
        return "CRITICAL BOARD FORMAT: Structure the paper strictly matching CBSE board exam patterns. Group questions logically into Sections. Add standard CBSE General Instructions at the top."
    elif board == "ICSE":
        return "CRITICAL BOARD FORMAT: Structure the paper strictly matching ICSE board exam patterns. Add standard ICSE General Instructions."
    elif board == "BSEB (Bihar Board)":
        return "CRITICAL BOARD FORMAT: Structure the paper strictly matching BSEB (Bihar School Examination Board) patterns. Divide into 'Section-A: Objective Type' and 'Section-B: Subjective Type'. Add standard BSEB General Instructions."
    else:
        return "Format the paper beautifully as a standard ready-to-print exam paper with clear sections."

def create_a4_html(md_content):
    md_content = md_content.replace("# Answer Key", "<div style='page-break-before: always;'></div>\n# Answer Key")
    md_content = md_content.replace("# ANSWER KEY", "<div style='page-break-before: always;'></div>\n# ANSWER KEY")
    md_content = md_content.replace("## Answer Key", "<div style='page-break-before: always;'></div>\n## Answer Key")

    html_body = markdown.markdown(md_content)
    
    html_template = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>Question Paper</title>
        <script>
          MathJax = {{
            tex: {{
              inlineMath: [['$', '$'], ['\\\\(', '\\\\)']],
              displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']]
            }}
          }};
        </script>
        <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
        <style>
            body {{ background-color: #f0f0f0; font-family: 'Times New Roman', Times, serif; margin: 0; padding: 20px; display: flex; justify-content: center; }}
            .a4-page {{ background-color: white; width: 210mm; min-height: 297mm; padding: 20mm; box-sizing: border-box; box-shadow: 0 0 10px rgba(0,0,0,0.2); }}
            @media print {{ body {{ background-color: white; padding: 0; display: block; }} .a4-page {{ box-shadow: none; width: 100%; padding: 0; margin: 0; }} @page {{ size: A4; margin: 20mm; }} }}
            h1, h2, h3 {{ text-align: center; color: #111; }} p, li {{ font-size: 16px; line-height: 1.5; color: #000; }} hr {{ border: 1px solid #ccc; margin: 20px 0; }}
            mjx-container {{ max-width: 100%; overflow-x: auto; overflow-y: hidden; }}
        </style>
    </head>
    <body>
        <div class="a4-page">
            {html_body}
        </div>
    </body>
    </html>
    """
    return html_template

# ==========================================
# --- 1. GLOBAL QUESTION SETUP (PERFECT ALIGNMENT) ---
# ==========================================
st.markdown("### 1. Set Questions & Difficulty")
diff_options = ["Easy", "Medium", "Hard", "Mixed"]

# Headers
h1, h2, h3 = st.columns([2, 1, 2])
h1.markdown("**Question Type**")
h2.markdown("**Count**")
h3.markdown("**Difficulty**")

# Row 1: MCQs
c1, c2, c3 = st.columns([2, 1, 2])
with c1: st.markdown("<div style='padding-top: 10px;'>Multiple Choice (MCQs)</div>", unsafe_allow_html=True)
with c2: mcq_c = st.number_input("MCQ count", min_value=0, value=5, label_visibility="collapsed", key="m_c")
with c3: mcq_d = st.selectbox("MCQ Diff", diff_options, label_visibility="collapsed", key="m_d")

# Row 2: Fill in the Blanks
c1, c2, c3 = st.columns([2, 1, 2])
with c1: st.markdown("<div style='padding-top: 10px;'>Fill in the Blanks</div>", unsafe_allow_html=True)
with c2: fib_c = st.number_input("FIB count", min_value=0, value=3, label_visibility="collapsed", key="f_c")
with c3: fib_d = st.selectbox("FIB Diff", diff_options, label_visibility="collapsed", key="f_d")

# Row 3: True / False
c1, c2, c3 = st.columns([2, 1, 2])
with c1: st.markdown("<div style='padding-top: 10px;'>True / False</div>", unsafe_allow_html=True)
with c2: tf_c = st.number_input("TF count", min_value=0, value=3, label_visibility="collapsed", key="t_c")
with c3: tf_d = st.selectbox("TF Diff", diff_options, label_visibility="collapsed", key="t_d")

# Row 4: Short Answer
c1, c2, c3 = st.columns([2, 1, 2])
with c1: st.markdown("<div style='padding-top: 10px;'>Short Answer (2-3 Lines)</div>", unsafe_allow_html=True)
with c2: short_c = st.number_input("Short count", min_value=0, value=3, label_visibility="collapsed", key="s_c")
with c3: short_d = st.selectbox("Short Diff", diff_options, label_visibility="collapsed", key="s_d")

# Row 5: Long Answer
c1, c2, c3 = st.columns([2, 1, 2])
with c1: st.markdown("<div style='padding-top: 10px;'>Long Answer (Detailed)</div>", unsafe_allow_html=True)
with c2: long_c = st.number_input("Long count", min_value=0, value=2, label_visibility="collapsed", key="l_c")
with c3: long_d = st.selectbox("Long Diff", diff_options, label_visibility="collapsed", key="l_d")

st.markdown("---")

# ==========================================
# --- 2. CHOOSE GENERATION METHOD ---
# ==========================================
st.markdown("### 2. Choose Paper Source")
tab1, tab2 = st.tabs(["⚡ Quick Generate (By Syllabus)", "📄 Deep Extract (From PDF Book)"])

# ------------------------------------------
# TAB 1: SYLLABUS BASED
# ------------------------------------------
with tab1:
    with st.form("quick_gen_form"):
        col1, col2 = st.columns(2)
        with col1:
            subject_t1 = st.text_input("Subject (e.g., Science)")
        with col2:
            grade_t1 = st.text_input("Class / Grade")
            
        syllabus_t1 = st.text_area("Paste Syllabus or Topics to Cover", placeholder="e.g., Light reflection, Newton's laws...")
        submit_t1 = st.form_submit_button("🚀 Generate Paper from Syllabus")

    if submit_t1:
        if not api_key: st.error("API Key is missing!")
        elif not subject_t1 or not syllabus_t1: st.error("Please fill in the Subject and Syllabus.")
        else:
            with st.spinner(f"Generating {board_format} Paper... Please wait."):
                total_q = mcq_c + fib_c + tf_c + short_c + long_c
                q_reqs = build_question_prompt(mcq_c, mcq_d, fib_c, fib_d, tf_c, tf_d, short_c, short_d, long_c, long_d)
                board_rules = get_board_instructions(board_format)
                
                header1 = f"""
# {inst_name}
**Class:** {grade_t1} | **Subject:** {subject_t1} | **Pattern:** {board_format}  
**Time Allowed:** {exam_time} | **Maximum Marks:** {max_marks} | **Total Questions:** {total_q}
***
                """
                prompt1 = f"""You are an expert educator. Create an exam paper covering strictly: {syllabus_t1}\n{board_rules}\nYou MUST start your response EXACTLY with this formatting header:\n{header1}\nGenerate exactly the following questions:\n{q_reqs}"""
                
                try:
                    model = genai.GenerativeModel(working_model_name)
                    response = model.generate_content(prompt1)
                    st.success("Success! Your paper is ready.")
                    
                    st.markdown("---")
                    if inst_logo is not None:
                        col_space1, col_img, col_space2 = st.columns([2, 1, 2])
                        with col_img: st.image(inst_logo, width=150)
                    st.markdown(response.text)
                    st.markdown("---")
                    
                    final_html = create_a4_html(response.text)
                    st.download_button(label="🖨️ Download A4 Paper (HTML/PDF)", data=final_html, file_name=f"{subject_t1}_Paper.html", mime="text/html")
                except Exception as e:
                    st.error(f"API Error: {e}")

# ------------------------------------------
# TAB 2: PDF BASED
# ------------------------------------------
with tab2:
    with st.form("pdf_gen_form"):
        uploaded_pdf = st.file_uploader("Upload Book/Chapter (PDF)", type="pdf")
        
        col4, col5 = st.columns(2)
        with col4: start_p = st.number_input("Start Page", min_value=1, value=1)
        with col5: end_p = st.number_input("End Page", min_value=1, value=5)
            
        col6, col7 = st.columns(2)
        with col6: subject_t2 = st.text_input("Subject")
        with col7: topic_t2 = st.text_input("Specific Topic")
            
        submit_t2 = st.form_submit_button("📑 Extract & Generate from PDF")

    if submit_t2:
        if not api_key: st.error("API Key is missing!")
        elif not uploaded_pdf: st.error("Please upload a PDF document.")
        elif not subject_t2 or not topic_t2: st.error("Please fill in the Subject and Topic.")
        else:
            with st.spinner(f"Reading PDF & Generating {board_format} Paper... Please wait."):
                document_text = extract_text_from_pdf(uploaded_pdf, start_p, end_p)
                total_q = mcq_c + fib_c + tf_c + short_c + long_c
                q_reqs = build_question_prompt(mcq_c, mcq_d, fib_c, fib_d, tf_c, tf_d, short_c, short_d, long_c, long_d)
                board_rules = get_board_instructions(board_format)
                
                header2 = f"""
# {inst_name}
**Subject:** {subject_t2} | **Topic:** {topic_t2} | **Pattern:** {board_format}  
**Time Allowed:** {exam_time} | **Maximum Marks:** {max_marks} | **Total Questions:** {total_q}
***
                """
                prompt2 = f"""You are an expert exam creator. Generate an exam ONLY for the topic requested below using the provided text.\n- Subject: {subject_t2}\n- Target Topic: {topic_t2}\nCRITICAL INSTRUCTIONS:\n1. Ignore any text NOT related to '{topic_t2}'.\n2. Extract questions STRICTLY from the text provided below.\n{board_rules}\nYou MUST start your response EXACTLY with this formatting header:\n{header2}\nGenerate exactly the following questions:\n{q_reqs}\nTextbook text:\n---\n{document_text}\n---"""
                
                try:
                    model = genai.GenerativeModel(working_model_name)
                    response = model.generate_content(prompt2)
                    st.success("Success! Your paper is ready.")
                    
                    st.markdown("---")
                    if inst_logo is not None:
                        col_space3, col_img2, col_space4 = st.columns([2, 1, 2])
                        with col_img2: st.image(inst_logo, width=150)
                    st.markdown(response.text)
                    st.markdown("---")
                    
                    final_html = create_a4_html(response.text)
                    st.download_button(label="🖨️ Download A4 Paper (HTML/PDF)", data=final_html, file_name=f"{topic_t2}_Paper.html", mime="text/html")
                except Exception as e:
                    st.error(f"API Error: {e}")
