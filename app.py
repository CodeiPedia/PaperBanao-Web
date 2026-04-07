import streamlit as st
import google.generativeai as genai
import PyPDF2
import os
import markdown
from datetime import datetime
import re
import uuid
import hashlib
import base64
from docx import Document
from docx.shared import Inches
from docx.oxml.ns import qn
from io import BytesIO

# --- SUPABASE ---
from supabase import create_client, Client

# --- Page Config ---
st.set_page_config(page_title="PaperBanao - AI Question Paper", page_icon="📝", layout="centered")

# ==========================================
# --- 🛑 SECRETS: PULLING KEYS SECURELY ---
# ==========================================
SERVER_API_KEY = st.secrets["GEMINI_API_KEY"]
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

# ==========================================
# --- INITIALIZE SUPABASE CLIENT ---
# ==========================================
@st.cache_resource
def init_supabase():
    try:
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        st.error(f"Database Connection Error: {e}")
        return None

supabase: Client = init_supabase()

# --- DB HELPER FUNCTIONS ---
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def create_user(username, password):
    try:
        data = {"username": username, "password": hash_password(password), "papers_generated": 0, "is_pro": False}
        supabase.table("users").insert(data).execute()
        return True
    except Exception: return False

def authenticate_user(username, password):
    res = supabase.table("users").select("*").eq("username", username).eq("password", hash_password(password)).execute()
    if len(res.data) > 0: return res.data[0]
    return None

def get_user_data(username):
    res = supabase.table("users").select("papers_generated, is_pro").eq("username", username).execute()
    if len(res.data) > 0: return (res.data[0]["papers_generated"], res.data[0]["is_pro"])
    return (0, False)

def update_paper_count(username):
    current_count, _ = get_user_data(username)
    supabase.table("users").update({"papers_generated": current_count + 1}).eq("username", username).execute()

def delete_paper(paper_id):
    supabase.table("papers").delete().eq("id", paper_id).execute()

# --- INITIALIZE SESSION STATE ---
if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "username" not in st.session_state: st.session_state.username = ""
if "blocks" not in st.session_state: st.session_state.blocks = [] 
if "file_name" not in st.session_state: st.session_state.file_name = "PaperBanao_Exam"
if "current_subject" not in st.session_state: st.session_state.current_subject = "Unknown Subject"

# ==========================================
# --- 🔐 LOGIN & SIGNUP UI ---
# ==========================================
if not st.session_state.logged_in:
    st.markdown("<h1 style='text-align: center;'>📝 PaperBanao AI (Cloud)</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center;'>Generate precise question papers in seconds.</p>", unsafe_allow_html=True)
    
    if not supabase:
        st.error("⚠️ SYSTEM ADMIN: Please configure 'SUPABASE_URL' and 'SUPABASE_KEY' in the code to enable Login.")
        st.stop()
        
    st.markdown("---")
    t_login, t_signup = st.tabs(["Login", "Sign Up (Free Trial)"])
    
    with t_login:
        l_user = st.text_input("Username", key="l_user")
        l_pass = st.text_input("Password", type="password", key="l_pass")
        if st.button("Login", use_container_width=True):
            user = authenticate_user(l_user, l_pass)
            if user:
                st.session_state.logged_in = True
                st.session_state.username = l_user
                st.rerun()
            else: st.error("Invalid Username or Password")
                
    with t_signup:
        s_user = st.text_input("New Username", key="s_user")
        s_pass = st.text_input("New Password", type="password", key="s_pass")
        if st.button("Create Account & Get 5 Free Papers", use_container_width=True):
            if len(s_user) < 3 or len(s_pass) < 4: st.error("Username (>2) and Password (>3) must be longer.")
            else:
                if create_user(s_user, s_pass): st.success("Account created successfully! Please Login.")
                else: st.error("Username already exists. Choose another.")
    st.stop()

# ==========================================
# --- APP LOGIC (IF LOGGED IN) ---
# ==========================================
genai.configure(api_key=SERVER_API_KEY)
try:
    valid_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
    flash_models = [m for m in valid_models if '1.5-flash' in m]
    working_model_name = flash_models[0] if flash_models else valid_models[0]
except Exception: working_model_name = "models/gemini-1.5-flash-latest"

user_data = get_user_data(st.session_state.username)
papers_used = user_data[0]
is_pro = bool(user_data[1])
FREE_LIMIT = 5

col_logo, col_title, col_logout = st.columns([1, 4, 1])
with col_logo: st.markdown("<h1>📝</h1>", unsafe_allow_html=True) 
with col_title: st.title("PaperBanao")
with col_logout:
    st.write(f"👤 **{st.session_state.username}**")
    if st.button("Logout"):
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.session_state.blocks = []
        st.rerun()

# ==========================================
# --- SIDEBAR: ACCOUNT & SETTINGS ---
# ==========================================
st.sidebar.header("💳 Your Account")
if is_pro: st.sidebar.success("🌟 PRO Member (Unlimited)")
else:
    papers_left = FREE_LIMIT - papers_used
    st.sidebar.info(f"🪙 Free Credits: {papers_left} / {FREE_LIMIT}")
    st.sidebar.progress(papers_used / FREE_LIMIT if papers_used <= FREE_LIMIT else 1.0)
    if papers_left <= 0:
        st.sidebar.error("⚠️ Free Trial Expired!")
        st.sidebar.button("💎 Upgrade to PRO", use_container_width=True)

st.sidebar.markdown("---")
st.sidebar.header("🏫 Institute Details")
inst_logo = st.sidebar.file_uploader("Upload Institute Logo (PNG/JPG)", type=["png", "jpg", "jpeg"])
inst_name = st.sidebar.text_input("Institute Name", value="My Success Academy")
exam_time = st.sidebar.text_input("Exam Time", value="2 Hours")
max_marks = st.sidebar.number_input("Maximum Marks", min_value=1, value=50)

st.sidebar.markdown("---")
st.sidebar.header("🏢 Footer Details")
inst_address = st.sidebar.text_input("Institute Address", value="123 Education Lane, City")
inst_contact = st.sidebar.text_input("Contact Number", value="+91 9876543210")

st.sidebar.markdown("---")
st.sidebar.header("📜 Formatting & Layout")
board_format = st.sidebar.selectbox("Board Pattern", ["Standard", "BSEB (Bihar Board)", "CBSE", "ICSE"])
paper_language = st.sidebar.selectbox("Paper Language", ["English", "Hindi", "Bilingual"])
include_answer_key = st.sidebar.toggle("Include Answer Key", value=True)
is_two_column = st.sidebar.toggle("📄 Two-Column Format (Save Paper)", value=False)


# --- Helper Functions ---
def extract_text_from_pdf(uploaded_file, start_page, end_page):
    try:
        reader = PyPDF2.PdfReader(uploaded_file)
        start_index = max(0, start_page - 1) 
        end_index = min(len(reader.pages), end_page)
        return "".join([reader.pages[i].extract_text() + "\n" for i in range(start_index, end_index)])
    except Exception: return ""

def build_question_prompt(mcq_c, mcq_d, fib_c, fib_d, tf_c, tf_d, short_c, short_d, long_c, long_d, include_answers):
    reqs = []
    if mcq_c > 0: reqs.append(f"- {mcq_c} Multiple Choice Questions (Diff: {mcq_d}). Provide 4 options.")
    if fib_c > 0: reqs.append(f"- {fib_c} Fill in the Blanks (Diff: {fib_d}).")
    if tf_c > 0:  reqs.append(f"- {tf_c} True/False Questions (Diff: {tf_d}).")
    if short_c > 0: reqs.append(f"- {short_c} Short Answer Questions (Diff: {short_d}).")
    if long_c > 0:  reqs.append(f"- {long_c} Long Answer Questions (Diff: {long_d}).")
    if not reqs: return "No questions requested."
    base_prompt = "\n".join(reqs) + "\n\nCRITICAL: Separate the Main Header, EVERY SINGLE Question, and the Answer Key using exactly this delimiter: `|||` on a new line."
    if include_answers: return base_prompt + "\nPut answers at the end under heading '# Answer Key'. Separate with `|||`."
    else: return base_prompt + "\nDO NOT provide answers. Provide ONLY the questions."

def regenerate_single_question(old_text):
    prompt = f"You are an expert exam creator. Generate a NEW question to replace this old one:\n{old_text}\nProvide ONLY the new question text."
    model = genai.GenerativeModel(working_model_name)
    return model.generate_content(prompt).text.strip()

# ✅ WORD EXPORT के लिए Math Cleaner Function
def clean_math_for_word(text):
    math_symbols = {
        r'\times': '×', r'\div': '÷', r'\pi': 'π', r'\theta': 'θ',
        r'\leq': '≤', r'\geq': '≥', r'\neq': '≠', r'^2': '²', r'^3': '³',
        r'\alpha': 'α', r'\beta': 'β', r'\pm': '±', r'\circ': '°', r'\sqrt': '√'
    }
    for latex, symbol in math_symbols.items():
        text = text.replace(latex, symbol)
    text = text.replace('$$', '').replace('$', '')
    return text

# ✅ UPDATED HTML EXPORT
def create_a4_html(md_content, i_name, i_address, i_contact, inst_logo=None, is_2_col=False):
    md_content = md_content.replace('\r', '') 
    pb = "<div style='page-break-before: always; break-before: page; column-span: all; -webkit-column-span: all; width: 100%;'></div>\n"
    md_content = md_content.replace("# Answer Key", pb + "# Answer Key")
    md_content = md_content.replace("## Answer Key", pb + "## Answer Key")
    md_content = md_content.replace("# ANSWER KEY", pb + "# ANSWER KEY")
    
    html_body = markdown.markdown(md_content)
    logo_html = ""
    if inst_logo is not None:
        base64_img = base64.b64encode(inst_logo.getvalue()).decode()
        img_type = inst_logo.type
        logo_html = f"<div style='text-align: center; margin-bottom: 10px;'><img src='data:{img_type};base64,{base64_img}' style='max-height: 80px; width: auto;'/></div>"
    
    footer_html = f"""<div class="footer" style="column-span: all;"><p><strong>{i_name}</strong> | 📍 {i_address} | 📞 {i_contact}</p></div>"""
    
    page_padding = "10mm" if is_2_col else "20mm"
    column_style = "column-count: 2; column-gap: 10mm; font-size: 14px;" if is_2_col else "font-size: 16px;"

    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><title>Question Paper</title><script>MathJax = {{ tex: {{ inlineMath: [['$', '$'], ['\\\\(', '\\\\)']], displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']] }} }};</script><script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script><style>body {{ background-color: #f0f0f0; font-family: 'Times New Roman', Times, serif; margin: 0; padding: 20px; display: flex; justify-content: center; }} .a4-page {{ background-color: white; width: 210mm; min-height: 297mm; padding: {page_padding}; box-sizing: border-box; box-shadow: 0 0 10px rgba(0,0,0,0.2); }} @media print {{ body {{ background-color: white; padding: 0; display: block; }} .a4-page {{ box-shadow: none; width: 100%; padding: {page_padding}; margin: 0; min-height: auto; }} @page {{ size: A4; margin: 0; }} }} h1, h2, h3 {{ text-align: center; color: #111; column-span: all; }} p, li {{ line-height: 1.5; color: #000; }} hr {{ border: 1px solid #ccc; margin: 15px 0; column-span: all; }} .content-body {{ {column_style} }}</style></head><body><div class="a4-page">{logo_html}<div class="content-body">{html_body}</div>{footer_html}</div></body></html>"""

# ✅ UPDATED WORD EXPORT
def create_word_docx(md_content, i_name, i_address, i_contact, inst_logo=None, is_2_col=False):
    doc = Document()
    md_content = md_content.replace('\r', '')
    
    if is_2_col:
        for section in doc.sections:
            section.top_margin = Inches(0.4)
            section.bottom_margin = Inches(0.4)
            section.left_margin = Inches(0.4)
            section.right_margin = Inches(0.4)

    if inst_logo is not None:
        try:
            doc.add_picture(inst_logo, height=Inches(0.8))
            doc.paragraphs[-1].alignment = 1 
        except Exception: pass
    header = doc.add_heading(i_name, level=0)
    header.alignment = 1 

    if is_2_col:
        new_section = doc.add_section(0) 
        sectPr = new_section._sectPr
        cols = sectPr.xpath('./w:cols')[0]
        cols.set(qn('w:num'), '2')
        cols.set(qn('w:space'), '360') 

    for line in md_content.split('\n'):
        if line.strip() == "": continue
        
        line = clean_math_for_word(line)
        
        if "Answer Key" in line or "ANSWER KEY" in line:
            doc.add_page_break() 
            doc.add_heading("Answer Key", level=1)
            continue
            
        if line.startswith('# '): doc.add_heading(line.replace('# ', ''), level=1)
        elif line.startswith('## '): doc.add_heading(line.replace('## ', ''), level=2)
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
tab_create, tab_history = st.tabs(["🏠 Create New Paper", "🗂️ My Past Papers (Cloud)"])

with tab_create:
    if not is_pro and papers_used >= FREE_LIMIT:
        st.error("🚨 **Your Free Trial has expired!**")
        st.warning("You have generated 5 papers. To continue using PaperBanao, please upgrade to the PRO plan.")
        st.stop()
        
    st.markdown("### 1. Choose Paper Source")
    source_choice = st.radio("Select Method:", ["⚡ Quick Generate (By Syllabus)", "📄 Deep Extract (From PDF Book)"], horizontal=True, label_visibility="collapsed")

    sub1, grade1, syl1, up_pdf, start_p, end_p, sub2, top2 = "", "", "", None, 1, 5, "", ""
    if "Syllabus" in source_choice:
        c1, c2 = st.columns(2)
        with c1: sub1 = st.text_input("Subject")
        with c2: grade1 = st.text_input("Class")
        syl1 = st.text_area("Topics to Cover")
    else:
        up_pdf = st.file_uploader("Upload Book/Chapter (PDF)", type="pdf")
        c1, c2 = st.columns(2)
        with c1: start_p = st.number_input("Start Page", min_value=1, value=1)
        with c2: end_p = st.number_input("End Page", min_value=1, value=5)
        c3, c4 = st.columns(2)
        with c3: sub2 = st.text_input("Subject")
        with c4: top2 = st.text_input("Specific Topic")

    st.markdown("---")
    st.markdown("### 2. Set Questions & Difficulty")
    diff_options = ["Easy", "Medium", "Hard", "Mixed"]
    
    # ✅ FIX: MCQ Max limit is now 50
    c1, c2, c3 = st.columns([2, 1, 2])
    with c1: st.markdown("<div style='padding-top: 10px;'>Multiple Choice (MCQs)</div>", unsafe_allow_html=True)
    with c2: mcq_c = st.number_input("MCQ count", min_value=0, max_value=50, value=5, label_visibility="collapsed", key="m_c")
    with c3: mcq_d = st.selectbox("MCQ Diff", diff_options, label_visibility="collapsed", key="m_d")

    # ✅ FIX: All other questions max limit is 20
    c1, c2, c3 = st.columns([2, 1, 2])
    with c1: st.markdown("<div style='padding-top: 10px;'>Fill in the Blanks</div>", unsafe_allow_html=True)
    with c2: fib_c = st.number_input("FIB count", min_value=0, max_value=20, value=3, label_visibility="collapsed", key="f_c")
    with c3: fib_d = st.selectbox("FIB Diff", diff_options, label_visibility="collapsed", key="f_d")

    c1, c2, c3 = st.columns([2, 1, 2])
    with c1: st.markdown("<div style='padding-top: 10px;'>True / False</div>", unsafe_allow_html=True)
    with c2: tf_c = st.number_input("TF count", min_value=0, max_value=20, value=3, label_visibility="collapsed", key="t_c")
    with c3: tf_d = st.selectbox("TF Diff", diff_options, label_visibility="collapsed", key="t_d")

    c1, c2, c3 = st.columns([2, 1, 2])
    with c1: st.markdown("<div style='padding-top: 10px;'>Short Answer</div>", unsafe_allow_html=True)
    with c2: short_c = st.number_input("Short count", min_value=0, max_value=20, value=3, label_visibility="collapsed", key="s_c")
    with c3: short_d = st.selectbox("Short Diff", diff_options, label_visibility="collapsed", key="s_d")

    c1, c2, c3 = st.columns([2, 1, 2])
    with c1: st.markdown("<div style='padding-top: 10px;'>Long Answer</div>", unsafe_allow_html=True)
    with c2: long_c = st.number_input("Long count", min_value=0, max_value=20, value=2, label_visibility="collapsed", key="l_c")
    with c3: long_d = st.selectbox("Long Diff", diff_options, label_visibility="collapsed", key="l_d")

    st.markdown("---")
    if st.button("🚀 Generate Exam Paper", use_container_width=True):
        total_q = mcq_c + fib_c + tf_c + short_c + long_c
        
        # ✅ FIX: Hard Limit increased to 100 to allow 50 MCQs + other questions
        if total_q > 100:
            st.error("🚨 Quality Alert: To maintain AI quality, you can only generate up to 100 total questions at a time.")
            st.stop()
        elif total_q == 0:
            st.warning("⚠️ Please select at least 1 question to generate.")
            st.stop()

        q_reqs = build_question_prompt(mcq_c, mcq_d, fib_c, fib_d, tf_c, tf_d, short_c, short_d, long_c, long_d, include_answer_key)
        board_rules = f"Structure the paper matching {board_format} patterns."
        lang_rules = f"Generate paper in {paper_language}."
        prompt = ""
        
        if "Syllabus" in source_choice and sub1 and syl1:
            header = f"# {inst_name}\n**Class:** {grade1} | **Subject:** {sub1} | **Pattern:** {board_format}\n**Time Allowed:** {exam_time} | **Maximum Marks:** {max_marks} | **Total Questions:** {total_q}\n***"
            prompt = f"Create exam strictly covering: {syl1}\n{board_rules}\n{lang_rules}\nMUST START EXACTLY WITH HEADER:\n{header}\nQuestions:\n{q_reqs}"
            st.session_state.file_name = f"{sub1}_Paper"
            st.session_state.current_subject = f"{sub1} (Class: {grade1})"
        elif "Deep Extract" in source_choice and up_pdf and sub2 and top2:
            document_text = extract_text_from_pdf(up_pdf, start_p, end_p)
            header = f"# {inst_name}\n**Subject:** {sub2} | **Topic:** {top2} | **Pattern:** {board_format}\n**Time Allowed:** {exam_time} | **Maximum Marks:** {max_marks} | **Total Questions:** {total_q}\n***"
            prompt = f"Create exam ONLY for requested topic using text below.\n- Topic: {top2}\n{board_rules}\n{lang_rules}\nMUST START EXACTLY WITH HEADER:\n{header}\nQuestions:\n{q_reqs}\nText:\n---\n{document_text}\n---"
            st.session_state.file_name = f"{top2}_Paper"
            st.session_state.current_subject = f"{sub2} - {top2}"

        if prompt:
            with st.spinner("Generating Paper via Cloud AI..."):
                try:
                    model = genai.GenerativeModel(working_model_name)
                    response = model.generate_content(prompt)
                    raw_blocks = response.text.split("|||")
                    st.session_state.blocks = [{'id': str(uuid.uuid4()), 'text': b.strip()} for b in raw_blocks if b.strip()]
                    update_paper_count(st.session_state.username) 
                except Exception as e: st.error(f"API Error: {e}")

    if st.session_state.blocks:
        st.markdown("---")
        with st.expander("🛠️ Open Question Bank Manager (Edit / Delete / Regenerate)", expanded=False):
            for i, block in enumerate(st.session_state.blocks):
                with st.container(border=True):
                    st.session_state.blocks[i]['text'] = st.text_area(f"Block {i}", value=block['text'], key=f"edit_{block['id']}", height=120, label_visibility="collapsed")
                    c1, c2, c3 = st.columns([1, 1, 4])
                    with c1:
                        if st.button("🗑️ Delete", key=f"del_{block['id']}", use_container_width=True):
                            if f"edit_{block['id']}" in st.session_state: del st.session_state[f"edit_{block['id']}"]
                            st.session_state.blocks.pop(i); st.rerun()
                    with c2:
                        if st.button("🔄 Regenerate", key=f"reg_{block['id']}", use_container_width=True):
                            with st.spinner("Generating..."):
                                st.session_state.blocks[i]['text'] = regenerate_single_question(block['text'])
                                if f"edit_{block['id']}" in st.session_state: del st.session_state[f"edit_{block['id']}"]
                                st.rerun()

        final_markdown_paper = "\n\n".join([b['text'] for b in st.session_state.blocks])
        st.markdown("### 🖨️ Finalize & Download")
        
        with st.expander("👁️ Preview Final Paper Layout", expanded=False):
            if inst_logo is not None:
                st.columns([2, 1, 2])[1].image(inst_logo, width=150)
            st.markdown(final_markdown_paper)
            
        final_html = create_a4_html(final_markdown_paper, inst_name, inst_address, inst_contact, inst_logo, is_two_column)
        final_word = create_word_docx(final_markdown_paper, inst_name, inst_address, inst_contact, inst_logo, is_two_column)
        
        c1, c2, c3 = st.columns(3)
        with c1: st.download_button("🖨️ Download HTML", data=final_html, file_name=st.session_state.file_name + ".html", mime="text/html", use_container_width=True)
        with c2: st.download_button("📄 Download MS Word", data=final_word, file_name=st.session_state.file_name + ".docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document", use_container_width=True)
        with c3:
            if st.button("☁️ Save to Cloud History", use_container_width=True):
                data = {"username": st.session_state.username, "date": datetime.now().strftime("%Y-%m-%d %H:%M"), "subject": st.session_state.current_subject, "board": board_format, "content": final_markdown_paper}
                supabase.table("papers").insert(data).execute()
                st.success("✅ Saved securely to Cloud!")

with tab_history:
    st.markdown(f"### ☁️ Cloud Papers for {st.session_state.username}")
    res = supabase.table("papers").select("*").eq("username", st.session_state.username).order("id", desc=True).execute()
    if not res.data: st.warning("You haven't saved any papers to the cloud yet!")
    else:
        for p in res.data:
            with st.expander(f"📄 {p['subject']} | {p['board']} | 🕒 {p['date']}"):
                
                h_html = create_a4_html(p['content'], inst_name, inst_address, inst_contact, inst_logo, is_two_column)
                h_word = create_word_docx(p['content'], inst_name, inst_address, inst_contact, inst_logo, is_two_column)
                
                c1, c2, c3 = st.columns(3)
                with c1: st.download_button("🖨️ Download HTML", data=h_html, file_name=f"History_{p['id']}.html", mime="text/html", key=f"dl_h_{p['id']}", use_container_width=True)
                with c2: st.download_button("📄 Download Word", data=h_word, file_name=f"History_{p['id']}.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document", key=f"dl_w_{p['id']}", use_container_width=True)
                with c3: 
                    if st.button("🗑️ Delete", key=f"del_{p['id']}", on_click=delete_paper, args=(p['id'],), use_container_width=True): st.rerun()
