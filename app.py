import streamlit as st
import google.generativeai as genai
import PyPDF2
import os
import markdown
import sqlite3
from datetime import datetime
import re
import uuid
from docx import Document
from io import BytesIO

# --- Page Config ---
st.set_page_config(page_title="PaperBanao - AI Question Paper", page_icon="📝", layout="centered")

# ==========================================
# --- DATABASE INITIALIZATION (SQLITE) ---
# ==========================================
def init_db():
    conn = sqlite3.connect('paperbanao.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS papers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            subject TEXT,
            board TEXT,
            content TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def delete_paper(paper_id):
    conn = sqlite3.connect('paperbanao.db')
    c = conn.cursor()
    c.execute("DELETE FROM papers WHERE id=?", (paper_id,))
    conn.commit()
    conn.close()

# --- INITIALIZE SESSION STATE (MEMORY) ---
if "blocks" not in st.session_state:
    st.session_state.blocks = [] 
if "file_name" not in st.session_state:
    st.session_state.file_name = "PaperBanao_Exam"
if "current_subject" not in st.session_state:
    st.session_state.current_subject = "Unknown Subject"

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
st.sidebar.header("🏢 Contact Details (Footer)")
inst_address = st.sidebar.text_input("Institute Address", value="123 Education Lane, City")
inst_contact = st.sidebar.text_input("Contact Number", value="+91 9876543210")

st.sidebar.markdown("---")
st.sidebar.header("📜 Exam Format & Language")
board_format = st.sidebar.selectbox("Select Board Pattern", ["Standard / Default", "BSEB (Bihar Board)", "CBSE", "ICSE"])
paper_language = st.sidebar.selectbox("Paper Language", ["English", "Hindi", "Bilingual (English + Hindi)"])

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
    except Exception:
        return ""

def build_question_prompt(mcq_c, mcq_d, fib_c, fib_d, tf_c, tf_d, short_c, short_d, long_c, long_d, include_answers):
    reqs = []
    if mcq_c > 0: reqs.append(f"- {mcq_c} Multiple Choice Questions (Diff: {mcq_d}). Provide 4 options.")
    if fib_c > 0: reqs.append(f"- {fib_c} Fill in the Blanks (Diff: {fib_d}).")
    if tf_c > 0:  reqs.append(f"- {tf_c} True/False Questions (Diff: {tf_d}).")
    if short_c > 0: reqs.append(f"- {short_c} Short Answer Questions (Diff: {short_d}).")
    if long_c > 0:  reqs.append(f"- {long_c} Long Answer Questions (Diff: {long_d}).")
    if not reqs: return "No questions requested."
    
    base_prompt = "\n".join(reqs) + "\n\nCRITICAL FORMATTING RULE: You MUST separate the Main Header, EVERY SINGLE Question (with its options), and the Answer Key using exactly this delimiter: `|||` on a new line."
    
    if include_answers:
        return base_prompt + "\nPut ALL the answers at the very end. You MUST use the exact English heading '# Answer Key' for this section. Separate the answer key block with `|||` as well."
    else:
        return base_prompt + "\nDO NOT provide any answers or answer keys. Provide ONLY the questions."

def get_board_instructions(board):
    return f"Structure the paper matching {board} patterns. Group questions logically."

def get_language_instructions(lang):
    if lang == "Hindi": return "Generate the ENTIRE exam paper strictly in Hindi language."
    elif lang == "Bilingual (English + Hindi)": return "Generate in a BILINGUAL format (English first, followed by exact Hindi translation below it)."
    else: return "Generate the paper in English."

def regenerate_single_question(old_text):
    prompt = f"You are an expert exam creator. Please generate a NEW, completely different question to replace this old one. Keep the same difficulty, language, and format (e.g. if it was an MCQ, give a new MCQ with 4 options).\n\nOLD QUESTION:\n{old_text}\n\nProvide ONLY the new question text without any introductory conversation."
    model = genai.GenerativeModel(working_model_name)
    return model.generate_content(prompt).text.strip()

def create_a4_html(md_content, i_name, i_address, i_contact):
    md_content = md_content.replace("# Answer Key", "<div style='page-break-before: always;'></div>\n# Answer Key")
    md_content = md_content.replace("# ANSWER KEY", "<div style='page-break-before: always;'></div>\n# ANSWER KEY")
    md_content = md_content.replace("## Answer Key", "<div style='page-break-before: always;'></div>\n## Answer Key")
    html_body = markdown.markdown(md_content)
    footer_html = f"""<div class="footer"><p><strong>{i_name}</strong> | 📍 {i_address} | 📞 {i_contact}</p></div>"""
    html_template = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8"><title>Question Paper</title>
        <script>MathJax = {{ tex: {{ inlineMath: [['$', '$'], ['\\\\(', '\\\\)']], displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']] }} }};</script>
        <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
        <style>
            body {{ background-color: #f0f0f0; font-family: 'Times New Roman', Times, serif; margin: 0; padding: 20px; display: flex; justify-content: center; }}
            .a4-page {{ background-color: white; width: 210mm; min-height: 297mm; padding: 20mm; box-sizing: border-box; box-shadow: 0 0 10px rgba(0,0,0,0.2); }}
            @media print {{ body {{ background-color: white; padding: 0; display: block; }} .a4-page {{ box-shadow: none; width: 100%; padding: 0; margin: 0; min-height: auto; }} @page {{ size: A4; margin: 20mm; }} }}
            h1, h2, h3 {{ text-align: center; color: #111; }} p, li {{ font-size: 16px; line-height: 1.5; color: #000; }} hr {{ border: 1px solid #ccc; margin: 20px 0; }}
            .footer {{ margin-top: 50px; padding-top: 15px; border-top: 2px dashed #bbb; text-align: center; font-size: 14px; color: #444; page-break-inside: avoid; }}
        </style>
    </head>
    <body><div class="a4-page">{html_body}{footer_html}</div></body>
    </html>
    """
    return html_template

def create_word_docx(md_content, i_name, i_address, i_contact):
    doc = Document()
    header = doc.add_heading(i_name, level=0)
    header.alignment = 1 
    lines = md_content.split('\n')
    for line in lines:
        if line.strip() == "": continue
        if "# Answer Key" in line or "# ANSWER KEY" in line or "## Answer Key" in line:
            doc.add_page_break()
            doc.add_heading("Answer Key", level=1)
            continue
        if line.startswith('# '): doc.add_heading(line.replace('# ', ''), level=1)
        elif line.startswith('## '): doc.add_heading(line.replace('## ', ''), level=2)
        elif line.startswith('### '): doc.add_heading(line.replace('### ', ''), level=3)
        else:
            p = doc.add_paragraph()
            parts = re.split(r'\*\*(.*?)\*\*', line)
            for i, part in enumerate(parts):
                if i % 2 == 1: p.add_run(part).bold = True
                else: p.add_run(part)
    doc.add_paragraph("\n")
    footer = doc.add_paragraph(f"📍 {i_address} | 📞 {i_contact}\nGenerated securely by PaperBanao AI")
    footer.alignment = 1
    bio = BytesIO()
    doc.save(bio)
    return bio.getvalue()


# ==========================================
# --- MAIN LAYOUT ---
# ==========================================
tab_create, tab_history = st.tabs(["🏠 Create New Paper", "🗂️ Past Papers History"])

with tab_create:
    st.markdown("### 1. Choose Paper Source")
    source_choice = st.radio("Select Method:", ["⚡ Quick Generate (By Syllabus)", "📄 Deep Extract (From PDF Book)"], horizontal=True, label_visibility="collapsed")

    sub1, grade1, syl1 = "", "", ""
    up_pdf, start_p, end_p, sub2, top2 = None, 1, 5, "", ""

    if "Syllabus" in source_choice:
        col1, col2 = st.columns(2)
        with col1: sub1 = st.text_input("Subject (e.g., Science)")
        with col2: grade1 = st.text_input("Class / Grade")
        syl1 = st.text_area("Paste Syllabus or Topics to Cover", placeholder="e.g., Light reflection, Newton's laws...")
    else:
        up_pdf = st.file_uploader("Upload Book/Chapter (PDF)", type="pdf")
        col4, col5 = st.columns(2)
        with col4: start_p = st.number_input("Start Page", min_value=1, value=1)
        with col5: end_p = st.number_input("End Page", min_value=1, value=5)
        col6, col7 = st.columns(2)
        with col6: sub2 = st.text_input("Subject")
        with col7: top2 = st.text_input("Specific Topic (e.g., Basic Electricity)")

    st.markdown("---")
    st.markdown("### 2. Set Questions & Difficulty")
    diff_options = ["Easy", "Medium", "Hard", "Mixed"]

    c1, c2, c3 = st.columns([2, 1, 2])
    with c1: st.markdown("<div style='padding-top: 10px;'>Multiple Choice (MCQs)</div>", unsafe_allow_html=True)
    with c2: mcq_c = st.number_input("MCQ count", min_value=0, value=5, label_visibility="collapsed", key="m_c")
    with c3: mcq_d = st.selectbox("MCQ Diff", diff_options, label_visibility="collapsed", key="m_d")

    c1, c2, c3 = st.columns([2, 1, 2])
    with c1: st.markdown("<div style='padding-top: 10px;'>Fill in the Blanks</div>", unsafe_allow_html=True)
    with c2: fib_c = st.number_input("FIB count", min_value=0, value=3, label_visibility="collapsed", key="f_c")
    with c3: fib_d = st.selectbox("FIB Diff", diff_options, label_visibility="collapsed", key="f_d")

    c1, c2, c3 = st.columns([2, 1, 2])
    with c1: st.markdown("<div style='padding-top: 10px;'>True / False</div>", unsafe_allow_html=True)
    with c2: tf_c = st.number_input("TF count", min_value=0, value=3, label_visibility="collapsed", key="t_c")
    with c3: tf_d = st.selectbox("TF Diff", diff_options, label_visibility="collapsed", key="t_d")

    c1, c2, c3 = st.columns([2, 1, 2])
    with c1: st.markdown("<div style='padding-top: 10px;'>Short Answer (2-3 Lines)</div>", unsafe_allow_html=True)
    with c2: short_c = st.number_input("Short count", min_value=0, value=3, label_visibility="collapsed", key="s_c")
    with c3: short_d = st.selectbox("Short Diff", diff_options, label_visibility="collapsed", key="s_d")

    c1, c2, c3 = st.columns([2, 1, 2])
    with c1: st.markdown("<div style='padding-top: 10px;'>Long Answer (Detailed)</div>", unsafe_allow_html=True)
    with c2: long_c = st.number_input("Long count", min_value=0, value=2, label_visibility="collapsed", key="l_c")
    with c3: long_d = st.selectbox("Long Diff", diff_options, label_visibility="collapsed", key="l_d")

    st.markdown("---")
    generate_btn = st.button("🚀 Generate Exam Paper", use_container_width=True)

    if generate_btn:
        if not api_key:
            st.error("API Key is missing! Please add it in the sidebar.")
        else:
            total_q = mcq_c + fib_c + tf_c + short_c + long_c
            q_reqs = build_question_prompt(mcq_c, mcq_d, fib_c, fib_d, tf_c, tf_d, short_c, short_d, long_c, long_d, include_answer_key)
            board_rules = get_board_instructions(board_format)
            lang_rules = get_language_instructions(paper_language)
            
            prompt = ""
            if "Syllabus" in source_choice and sub1 and syl1:
                header = f"# {inst_name}\n**Class:** {grade1} | **Subject:** {sub1} | **Pattern:** {board_format}\n**Time Allowed:** {exam_time} | **Maximum Marks:** {max_marks} | **Total Questions:** {total_q}\n***"
                prompt = f"You are an expert educator. Create an exam paper covering strictly: {syl1}\n{board_rules}\n{lang_rules}\nYou MUST start your response EXACTLY with this formatting header:\n{header}\nGenerate exactly the following questions:\n{q_reqs}"
                st.session_state.file_name = f"{sub1}_Paper"
                st.session_state.current_subject = f"{sub1} (Class: {grade1})"
            elif "Deep Extract" in source_choice and up_pdf and sub2 and top2:
                document_text = extract_text_from_pdf(up_pdf, start_p, end_p)
                header = f"# {inst_name}\n**Subject:** {sub2} | **Topic:** {top2} | **Pattern:** {board_format}\n**Time Allowed:** {exam_time} | **Maximum Marks:** {max_marks} | **Total Questions:** {total_q}\n***"
                prompt = f"You are an expert exam creator. Generate an exam ONLY for the topic requested below using the provided text.\n- Subject: {sub2}\n- Target Topic: {top2}\nCRITICAL INSTRUCTIONS:\n1. Ignore any text NOT related to '{top2}'.\n2. Extract questions STRICTLY from the text provided below.\n{board_rules}\n{lang_rules}\nYou MUST start your response EXACTLY with this formatting header:\n{header}\nGenerate exactly the following questions:\n{q_reqs}\nTextbook text:\n---\n{document_text}\n---"
                st.session_state.file_name = f"{top2}_Paper"
                st.session_state.current_subject = f"{sub2} - {top2}"

            if prompt:
                with st.spinner(f"Generating {board_format} Paper in {paper_language}..."):
                    try:
                        model = genai.GenerativeModel(working_model_name)
                        response = model.generate_content(prompt)
                        raw_blocks = response.text.split("|||")
                        st.session_state.blocks = [{'id': str(uuid.uuid4()), 'text': b.strip()} for b in raw_blocks if b.strip()]
                    except Exception as e: st.error(f"API Error: {e}")

    # ==========================================
    # --- 4. QUESTION BANK UI (CARDS) ---
    # ==========================================
    if st.session_state.blocks:
        st.markdown("---")
        st.markdown("### 🧩 Question Bank Manager")
        st.success("💡 **Pro Tip:** You can edit the text inside any box below. Don't like a question? Click **Regenerate** to get a new one, or **Delete** to remove it completely!")
        
        for i, block in enumerate(st.session_state.blocks):
            with st.container(border=True):
                # Text Area
                st.session_state.blocks[i]['text'] = st.text_area(f"Block {i}", value=block['text'], key=f"edit_{block['id']}", height=120, label_visibility="collapsed")
                
                col1, col2, col3 = st.columns([1, 1, 4])
                with col1:
                    if st.button("🗑️ Delete", key=f"del_{block['id']}", use_container_width=True):
                        # ✅ THE FIX FOR DELETE: Box की याददाश्त डिलीट करें
                        if f"edit_{block['id']}" in st.session_state:
                            del st.session_state[f"edit_{block['id']}"]
                        st.session_state.blocks.pop(i)
                        st.rerun()
                with col2:
                    if st.button("🔄 Regenerate", key=f"reg_{block['id']}", use_container_width=True):
                        with st.spinner("Generating new question..."):
                            new_text = regenerate_single_question(block['text'])
                            st.session_state.blocks[i]['text'] = new_text
                            
                            # ✅ THE FIX FOR REGENERATE: Box की पुरानी याददाश्त डिलीट करें
                            if f"edit_{block['id']}" in st.session_state:
                                del st.session_state[f"edit_{block['id']}"]
                            
                            st.rerun()

        final_markdown_paper = "\n\n".join([b['text'] for b in st.session_state.blocks])
        
        st.markdown("---")
        st.markdown("### 🖨️ Finalize & Download")
        
        with st.expander("👁️ Preview Final Paper Layout", expanded=False):
            if inst_logo is not None:
                col_img = st.columns([2, 1, 2])[1]
                col_img.image(inst_logo, width=150)
            st.markdown(final_markdown_paper)
        
        final_html = create_a4_html(final_markdown_paper, inst_name, inst_address, inst_contact)
        final_word = create_word_docx(final_markdown_paper, inst_name, inst_address, inst_contact)
        
        col_dl_h, col_dl_w, col_save = st.columns(3)
        with col_dl_h:
            st.download_button("🖨️ Download HTML (A4 Print)", data=final_html, file_name=st.session_state.file_name + ".html", mime="text/html", use_container_width=True)
        with col_dl_w:
            st.download_button("📄 Download MS Word", data=final_word, file_name=st.session_state.file_name + ".docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document", use_container_width=True)
        with col_save:
            if st.button("💾 Save to Past Papers", use_container_width=True):
                conn = sqlite3.connect('paperbanao.db')
                c = conn.cursor()
                current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
                c.execute("INSERT INTO papers (date, subject, board, content) VALUES (?, ?, ?, ?)", (current_time, st.session_state.current_subject, board_format, final_markdown_paper))
                conn.commit()
                conn.close()
                st.success("✅ Paper saved! Check the 'Past Papers History' tab.")

# ------------------------------------------
# TAB 2: PAST PAPERS HISTORY
# ------------------------------------------
with tab_history:
    st.markdown("### 🗂️ Your Saved Past Papers")
    conn = sqlite3.connect('paperbanao.db')
    c = conn.cursor()
    c.execute("SELECT * FROM papers ORDER BY id DESC")
    saved_papers = c.fetchall()
    conn.close()
    
    if not saved_papers:
        st.warning("No papers saved yet. Generate a paper and click 'Save to Past Papers' to see it here!")
    else:
        for paper in saved_papers:
            p_id, p_date, p_sub, p_board, p_content = paper
            with st.expander(f"📄 {p_sub} | {p_board} | 🕒 {p_date}"):
                if "<!DOCTYPE html>" in p_content:
                    st.warning("Older paper saved in HTML format. Word Download unavailable.")
                    st.download_button("📥 Download HTML Paper", data=p_content, file_name=f"Saved_{p_id}.html", mime="text/html", key=f"dl_old_{p_id}")
                    if st.button("🗑️ Delete Paper", key=f"del_old_{p_id}", on_click=delete_paper, args=(p_id,)): st.rerun()
                else:
                    hist_html = create_a4_html(p_content, inst_name, inst_address, inst_contact)
                    hist_word = create_word_docx(p_content, inst_name, inst_address, inst_contact)
                    c1, c2, c3 = st.columns(3)
                    with c1: st.download_button("🖨️ Download HTML", data=hist_html, file_name=f"History_{p_id}.html", mime="text/html", key=f"dl_h_{p_id}", use_container_width=True)
                    with c2: st.download_button("📄 Download Word", data=hist_word, file_name=f"History_{p_id}.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document", key=f"dl_w_{p_id}", use_container_width=True)
                    with c3:
                        if st.button("🗑️ Delete", key=f"del_{p_id}", on_click=delete_paper, args=(p_id,), use_container_width=True): st.rerun()
