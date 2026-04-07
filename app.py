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
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
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
# --- SIDEBAR ---
# ==========================================
st.sidebar.header("💳 Your Account")
if is_pro: st.sidebar.success("🌟 PRO Member (Unlimited)")
else:
    papers_left = FREE_LIMIT - papers_used
    st.sidebar.info(f"🪙 Free Credits: {papers_left} / {FREE_LIMIT}")
    if papers_left <= 0:
        st.sidebar.error("⚠️ Free Trial Expired!")

st.sidebar.markdown("---")
st.sidebar.header("🏫 Institute Details")
inst_logo = st.sidebar.file_uploader("Upload Institute Logo (PNG/JPG)", type=["png", "jpg", "jpeg"])
inst_name = st.sidebar.text_input("Institute Name", value="My Success Academy")
exam_time = st.sidebar.text_input("Exam Time", value="2 Hours")

st.sidebar.markdown("---")
st.sidebar.header("🏢 Footer Details")
teacher_name = st.sidebar.text_input("Teacher Name", value="Mr. Sharma")
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

# 🛑 THE FIX: STRICT SIMPLE HINDI & UNICODE SYMBOLS
def build_question_prompt(mcq_c, mcq_d, mcq_m, fib_c, fib_d, fib_m, tf_c, tf_d, tf_m, short_c, short_d, short_m, long_c, long_d, long_m, include_answers):
    reqs = []
    if mcq_c > 0: reqs.append(f"- {mcq_c} Multiple Choice Questions (Diff: {mcq_d}). Provide 4 options. Write '[{mcq_m} Mark]' at the end of each question.")
    if fib_c > 0: reqs.append(f"- {fib_c} Fill in the Blanks (Diff: {fib_d}). Write '[{fib_m} Marks]' at the end of each question.")
    if tf_c > 0:  reqs.append(f"- {tf_c} True/False Questions (Diff: {tf_d}). Write '[{tf_m} Marks]' at the end of each question.")
    if short_c > 0: reqs.append(f"- {short_c} Short Answer Questions (Diff: {short_d}). Write '[{short_m} Marks]' at the end of each question.")
    if long_c > 0:  reqs.append(f"- {long_c} Long Answer Questions (Diff: {long_d}). Write '[{long_m} Marks]' at the end of each question.")
    if not reqs: return "No questions requested."
    
    lang_instruction = """
    LANGUAGE RULE: If the user selected Hindi or Bilingual, use extremely simple, easy-to-understand Hindi (Hinglish mix is encouraged). 
    DO NOT use difficult academic Hindi words. Always provide English terms in brackets for any technical or mathematical words. 
    Example: 'अभाज्य संख्या (Prime Number)', 'अंश (Numerator)', 'हर (Denominator)', 'वर्गमूल (Square Root)'.
    Tone should be like a helpful local teacher explaining to students in a simple way.
    """
    
    base_prompt = "\n".join(reqs) + f"\n\n{lang_instruction}\n\nCRITICAL FORMATTING:\n1. Separate every block with `|||` on a new line.\n2. MATH: Use actual Unicode symbols (θ, π, √, ², ³) instead of LaTeX or words."
    
    if include_answers: return base_prompt + "\nPut answers at the end under heading '# Answer Key'. Separate with `|||`. Answers must also be in simple language."
    else: return base_prompt + "\nDO NOT provide answers."

def regenerate_single_question(old_text):
    prompt = f"Regenerate this question in extremely simple language. Use Unicode symbols (θ, π, √, ², ³) instead of LaTeX. If Hindi, use Hinglish mix and brackets for technical terms:\n{old_text}"
    model = genai.GenerativeModel(working_model_name)
    return model.generate_content(prompt).text.strip()

def clean_math_for_word(text):
    text = re.sub(r'\\frac\{([^}]+)\}\{([^}]+)\}', r'(\1)/(\2)', text)
    text = re.sub(r'\\\((.*?)\\\)', r'\1', text)
    text = re.sub(r'\\\[(.*?)\\\]', r'\1', text)
    latex_symbols = {r'\times': '×', r'\div': '÷', r'\pi': 'π', r'\theta': 'θ', r'^2': '²', r'^3': '³', '$': ''}
    for latex, symbol in latex_symbols.items():
        text = text.replace(latex, symbol)
    return text.strip()

# ✅ HTML EXPORT (With Fixed Footer)
def create_a4_html(md_content, i_name, i_address, i_contact, t_name, inst_logo=None, is_2_col=False):
    md_content = md_content.replace('\r', '') 
    md_content = clean_math_for_word(md_content)
    pb = "<div style='page-break-before: always; break-before: page; column-span: all; -webkit-column-span: all; width: 100%;'></div>\n"
    md_content = md_content.replace("# Answer Key", pb + "# Answer Key")
    html_body = markdown.markdown(md_content)
    
    logo_html_top = ""
    logo_html_footer = ""
    if inst_logo is not None:
        inst_logo.seek(0)
        base64_img = base64.b64encode(inst_logo.getvalue()).decode()
        img_type = inst_logo.type
        logo_html_top = f"<div style='text-align: center; margin-bottom: 10px;'><img src='data:{img_type};base64,{base64_img}' style='max-height: 80px;'/></div>"
        logo_html_footer = f"<img src='data:{img_type};base64,{base64_img}' style='height: 18px; vertical-align: middle; margin-right: 8px;'/>"
    
    footer_html = f'<div class="footer-container"><div class="footer"><p>{logo_html_footer}<strong>{i_name}</strong> | 📍 {i_address} | 📞 {i_contact} | 👨‍🏫 <strong>{t_name}</strong></p></div></div>'
    padding = "10mm" if is_2_col else "20mm"
    col_style = "column-count: 2; column-gap: 10mm; font-size: 14px;" if is_2_col else "font-size: 16px;"

    return f"""<!DOCTYPE html><html lang="en"><head><style>
    body {{ background: #f0f0f0; font-family: 'Times New Roman', serif; padding: 20px; display: flex; justify-content: center; }} 
    .a4-page {{ background: white; width: 210mm; min-height: 297mm; padding: {padding}; box-shadow: 0 0 10px rgba(0,0,0,0.2); position: relative; padding-bottom: 25mm; }} 
    @media print {{ 
        body {{ background: white; padding: 0; display: block; }} 
        .a4-page {{ box-shadow: none; width: 100%; padding: {padding}; margin: 0; min-height: auto; padding-bottom: 20mm; }} 
        @page {{ size: A4; margin: 10mm; }} 
        .footer-container {{ position: fixed; bottom: 0; left: 0; width: 100%; background: white; z-index: 1000; }}
    }} 
    h1, h2, h3 {{ text-align: center; color: #111; column-span: all; }} 
    p, li {{ line-height: 1.5; color: #000; text-align: justify; word-wrap: break-word; }} 
    hr {{ border: 1px solid #ccc; margin: 15px 0; column-span: all; }} 
    .content-body {{ {column_style} }} 
    .footer-container {{ width: 100%; text-align: center; margin-top: 20px; }}
    .footer {{ padding-top: 10px; border-top: 2px dashed #bbb; font-size: 13px; color: #444; display: inline-block; width: 90%; }}
    </style></head><body><div class="a4-page">{logo_html_top}<div class="content-body">{html_body}</div>{footer_html}</div></body></html>"""

# ✅ WORD EXPORT
def create_word_docx(md_content, i_name, i_address, i_contact, t_name, inst_logo=None, is_2_col=False):
    doc = Document()
    md_content = md_content.replace('\r', '')
    style = doc.styles['Normal']; font = style.font; font.name = 'Times New Roman'; font.size = Pt(11)
    
    if is_2_col:
        for s in doc.sections: s.top_margin = s.bottom_margin = s.left_margin = s.right_margin = Inches(0.4)

    if inst_logo:
        try:
            inst_logo.seek(0)
            doc.add_picture(inst_logo, height=Inches(0.8))
            doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
        except Exception: pass
        
    doc.add_heading(i_name, 0).alignment = WD_ALIGN_PARAGRAPH.CENTER

    if is_2_col:
        new_section = doc.add_section(0); sectPr = new_section._sectPr
        cols = sectPr.xpath('./w:cols')[0]; cols.set(qn('w:num'), '2'); cols.set(qn('w:space'), '720') 

    for line in md_content.split('\n'):
        if line.strip() == "": continue
        line = clean_math_for_word(line)
        if "Answer Key" in line or "ANSWER KEY" in line:
            doc.add_page_break(); doc.add_heading("Answer Key", 1); continue
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        parts = re.split(r'\*\*(.*?)\*\*', line)
        for i, part in enumerate(parts):
            if i % 2 == 1: p.add_run(part).bold = True
            else: p.add_run(part)
                
    for section in doc.sections:
        footer = section.footer.paragraphs[0] if section.footer.paragraphs else section.footer.add_paragraph()
        footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
        if inst_logo:
            try:
                inst_logo.seek(0)
                footer.add_run().add_picture(inst_logo, height=Inches(0.18))
                footer.add_run("  ")
            except Exception: pass
        run = footer.add_run(f"{i_name} | 📍 {i_address} | 📞 {i_contact} | 👨‍🏫 {t_name}")
        run.font.size = Pt(10); run.font.color.rgb = RGBColor(100, 100, 100)
            
    bio = BytesIO(); doc.save(bio); return bio.getvalue()

# ==========================================
# --- MAIN UI ---
# ==========================================
tab_create, tab_history = st.tabs(["🏠 Create New Paper", "🗂️ My Past Papers"])

with tab_create:
    if not is_pro and papers_used >= FREE_LIMIT:
        st.error("Free Trial Expired! Please Upgrade to PRO.")
        st.stop()
        
    st.markdown("### 1. Paper Details")
    c1, c2 = st.columns(2)
    with c1: sub = st.text_input("Subject")
    with c2: grade = st.text_input("Class")
    syl = st.text_area("Topics to Cover")

    st.markdown("---")
    st.markdown("### 2. Set Questions & Marks")
    diff_options = ["Easy", "Medium", "Hard", "Mixed"]
    
    h1, h2, h3, h4 = st.columns([3, 2, 2, 3])
    with h1: st.markdown("**Type**")
    with h2: st.markdown("**Count**")
    with h3: st.markdown("**Marks/Q**")
    with h4: st.markdown("**Difficulty**")

    # MCQ
    c1, c2, c3, c4 = st.columns([3, 2, 2, 3])
    with c1: st.write("Multiple Choice (MCQs)")
    with c2: mcq_c = st.number_input("mcq_c", 0, 50, 5, label_visibility="collapsed", key="m_c")
    with c3: mcq_m = st.number_input("mcq_m", 1, 10, 1, label_visibility="collapsed", key="m_m")
    with c4: mcq_d = st.selectbox("mcq_d", diff_options, label_visibility="collapsed", key="m_d")

    # Short
    c1, c2, c3, c4 = st.columns([3, 2, 2, 3])
    with c1: st.write("Short Answer")
    with c2: short_c = st.number_input("sh_c", 0, 20, 3, label_visibility="collapsed", key="s_c")
    with c3: short_m = st.number_input("sh_m", 1, 10, 2, label_visibility="collapsed", key="s_m")
    with c4: short_d = st.selectbox("sh_d", diff_options, label_visibility="collapsed", key="s_d", index=1)

    # Long
    c1, c2, c3, c4 = st.columns([3, 2, 2, 3])
    with c1: st.write("Long Answer")
    with c2: long_c = st.number_input("l_c", 0, 20, 2, label_visibility="collapsed", key="l_c")
    with c3: long_m = st.number_input("l_m", 1, 20, 5, label_visibility="collapsed", key="l_m")
    with c4: long_d = st.selectbox("l_d", diff_options, label_visibility="collapsed", key="l_d", index=2)

    total_q = mcq_c + short_c + long_c
    calc_max_marks = (mcq_c * mcq_m) + (short_c * short_m) + (long_c * long_m)

    st.info(f"📊 Total Questions: {total_q} | 🏆 Maximum Marks: {calc_max_marks}")

    if st.button("🚀 Generate Exam Paper", use_container_width=True):
        header = f"# {inst_name}\n**Subject:** {sub} | **Class:** {grade} | **Pattern:** {board_format}\n**Marks:** {calc_max_marks} | **Time:** {exam_time}\n***"
        q_reqs = build_question_prompt(mcq_c, mcq_d, mcq_m, 0, '', 1, 0, '', 1, short_c, short_d, short_m, long_c, long_d, long_m, include_answer_key)
        prompt = f"Topic: {syl}\n{header}\nQuestions:\n{q_reqs}\nLanguage: {paper_language}"
        
        with st.spinner("Generating paper in simple language..."):
            try:
                model = genai.GenerativeModel(working_model_name)
                response = model.generate_content(prompt)
                blocks = response.text.split("|||")
                st.session_state.blocks = [{'id': str(uuid.uuid4()), 'text': b.strip()} for b in blocks if b.strip()]
                st.session_state.file_name = f"{sub}_Paper"
                update_paper_count(st.session_state.username)
            except Exception as e: st.error(f"Error: {e}")

    if st.session_state.blocks:
        final_markdown = "\n\n".join([b['text'] for b in st.session_state.blocks])
        final_html = create_a4_html(final_markdown, inst_name, inst_address, inst_contact, teacher_name, inst_logo, is_two_column)
        final_word = create_word_docx(final_markdown, inst_name, inst_address, inst_contact, teacher_name, inst_logo, is_two_column)
        
        st.download_button("🖨️ Download HTML", final_html, f"{st.session_state.file_name}.html", "text/html")
        st.download_button("📄 Download Word", final_word, f"{st.session_state.file_name}.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        if st.button("☁️ Save to Cloud"):
            data = {"username": st.session_state.username, "date": datetime.now().strftime("%Y-%m-%d %H:%M"), "subject": sub, "board": board_format, "content": final_markdown}
            supabase.table("papers").insert(data).execute()
            st.success("Saved to Cloud!")

with tab_history:
    st.markdown(f"### ☁️ Cloud Papers for {st.session_state.username}")
    res = supabase.table("papers").select("*").eq("username", st.session_state.username).order("id", desc=True).execute()
    if not res.data: st.warning("No papers saved yet!")
    else:
        for p in res.data:
            with st.expander(f"📄 {p['subject']} | {p['date']}"):
                h_html = create_a4_html(p['content'], inst_name, inst_address, inst_contact, teacher_name, inst_logo, is_two_column)
                h_word = create_word_docx(p['content'], inst_name, inst_address, inst_contact, teacher_name, inst_logo, is_two_column)
                st.download_button("🖨️ HTML", h_html, f"History_{p['id']}.html", "text/html", key=f"h_{p['id']}")
                st.download_button("📄 Word", h_word, f"History_{p['id']}.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", key=f"w_{p['id']}")
                if st.button("🗑️ Delete", key=f"d_{p['id']}"): delete_paper(p['id']); st.rerun()
