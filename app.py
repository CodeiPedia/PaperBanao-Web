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
        res = supabase.table("users").insert(data).execute()
        return True
    except Exception as e:
        st.error(f"Signup Error: {e}")
        return False

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
# --- SIDEBAR & SETTINGS ---
# ==========================================
st.sidebar.header("💳 Your Account")
if is_pro: st.sidebar.success("🌟 PRO Member (Unlimited)")
else:
    papers_left = FREE_LIMIT - papers_used
    st.sidebar.info(f"🪙 Free Credits: {papers_left} / {FREE_LIMIT}")
    st.sidebar.progress(papers_used / FREE_LIMIT if papers_used <= FREE_LIMIT else 1.0)
    if papers_left <= 0:
        st.sidebar.error("⚠️ Free Trial Expired!")

st.sidebar.markdown("---")
# 🌟 BYOK (Bring Your Own Key) Feature added here
st.sidebar.header("⚙️ Advanced Settings")
st.sidebar.write("सर्वर लिमिट खत्म होने पर अपनी खुद की फ्री Gemini API Key इस्तेमाल करें।")
user_api_key = st.sidebar.text_input("Your Gemini API Key (Optional)", type="password", help="Get your free key from Google AI Studio")

if user_api_key:
    st.sidebar.success("✅ Personal API Key Active!")

st.sidebar.markdown("---")
st.sidebar.header("🏫 Institute Details")
inst_logo = st.sidebar.file_uploader("Upload Logo", type=["png", "jpg", "jpeg"])
inst_name = st.sidebar.text_input("Institute Name", value="My Success Academy")
exam_time = st.sidebar.text_input("Exam Time", value="2 Hours")

st.sidebar.markdown("---")
st.sidebar.header("🏢 Footer Details")
teacher_name = st.sidebar.text_input("Teacher Name", value="Mr. Sharma")
inst_address = st.sidebar.text_input("Institute Address", value="123 Education Lane, City")
inst_contact = st.sidebar.text_input("Contact Number", value="+91 9876543210")

st.sidebar.markdown("---")
st.sidebar.header("📜 Formatting")
board_format = st.sidebar.selectbox("Board Pattern", ["Standard", "BSEB (Bihar Board)", "CBSE", "ICSE"])
paper_language = st.sidebar.selectbox("Paper Language", ["English", "Hindi", "Bilingual"])
include_answer_key = st.sidebar.toggle("Include Answer Key", value=True)
is_two_column = st.sidebar.toggle("📄 Two-Column Format", value=False)

# ==========================================
# --- API CONFIGURATION LOGIC ---
# ==========================================
# Use user's key if provided, otherwise use server default
active_api_key = user_api_key if user_api_key.strip() != "" else SERVER_API_KEY
genai.configure(api_key=active_api_key)

try:
    valid_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
    flash_models = [m for m in valid_models if '1.5-flash' in m]
    working_model_name = flash_models[0] if flash_models else valid_models[0]
except Exception as e: 
    working_model_name = "models/gemini-1.5-flash-latest"
    if user_api_key:
        st.sidebar.error("❌ आपकी API Key Invalid है। कृपया सही Key डालें।")

# --- Helper Functions ---
def extract_text_from_pdf(uploaded_file, start_page, end_page):
    try:
        reader = PyPDF2.PdfReader(uploaded_file)
        start_index = max(0, start_page - 1) 
        end_index = min(len(reader.pages), end_page)
        return "".join([reader.pages[i].extract_text() + "\n" for i in range(start_index, end_index)])
    except Exception: return ""

def build_question_prompt(mcq_c, mcq_d, mcq_m, fib_c, fib_d, fib_m, tf_c, tf_d, tf_m, short_c, short_d, short_m, long_c, long_d, long_m, include_answers):
    reqs = []
    if mcq_c > 0: reqs.append(f"- {mcq_c} MCQs (Diff: {mcq_d}). [{mcq_m} Mark each]")
    if fib_c > 0: reqs.append(f"- {fib_c} FIBs (Diff: {fib_d}). [{fib_m} Marks each]")
    if tf_c > 0:  reqs.append(f"- {tf_c} True/False (Diff: {tf_d}). [{tf_m} Marks each]")
    if short_c > 0: reqs.append(f"- {short_c} Short Q (Diff: {short_d}). [{short_m} Marks each]")
    if long_c > 0:  reqs.append(f"- {long_c} Long Q (Diff: {long_d}). [{long_m} Marks each]")
    
    lang_instruction = """
    LANGUAGE RULE: If the subject is technical or language is Hindi/Bilingual, use extremely simple Hindi (Hinglish mix is encouraged). 
    Avoid tough academic Hindi words. Provide English terms in brackets for technical words. 
    Example: 'अंश [Numerator]', 'हर [Denominator]', 'अभाज्य संख्या [Prime Number]'.
    """
    
    base_prompt = "\n".join(reqs) + f"\n\n{lang_instruction}\n\n" + """CRITICAL FORMATTING:
1. Separate Main Header, every Question, and Answer Key with delimiter: `|||` on a new line.
2. MATH: USE UNICODE SYMBOLS ONLY (θ, π, √, ²). NO LaTeX. Write fractions as a/b.
    """
    
    if include_answers: return base_prompt + "\nAdd '# Answer Key' at end, also separated by `|||`. Use simple language in answers too."
    return base_prompt

def regenerate_single_question(old_text):
    prompt = f"Generate a NEW question to replace this. Use simple Hindi/Hinglish with English brackets where needed. Use Unicode math symbols (θ, π, √, ²). ONLY output the question text:\n{old_text}"
    model = genai.GenerativeModel(working_model_name)
    return model.generate_content(prompt).text.strip()

def clean_math_for_word(text):
    text = re.sub(r'\\frac\{([^}]+)\}\{([^}]+)\}', r'(\1)/(\2)', text)
    text = re.sub(r'\\\((.*?)\\\)', r'\1', text)
    text = re.sub(r'\\\[(.*?)\\\]', r'\1', text)
    latex_map = {r'\pi': 'π', r'\theta': 'θ', r'\sqrt': '√', r'\times': '×', r'\div': '÷', '$': '', '^2': '²', '^3': '³'}
    for k, v in latex_map.items(): text = text.replace(k, v)
    
    text = text.replace('☐', '[ ]')
    text = text.replace('☑', '[x]')
    text = text.replace('•', '-')
    text = text.replace('◦', '-')
    
    return text.strip()

# ✅ HTML EXPORT (Fixed Footer)
def create_a4_html(md_content, i_name, i_address, i_contact, t_name, inst_logo=None, is_2_col=False):
    md_content = clean_math_for_word(md_content)
    pb = "<div style='page-break-before: always; column-span: all; width: 100%;'></div>\n"
    md_content = md_content.replace("# Answer Key", pb + "# Answer Key")
    html_body = markdown.markdown(md_content)
    
    logo_top = ""
    logo_footer = ""
    if inst_logo:
        inst_logo.seek(0)
        b64 = base64.b64encode(inst_logo.getvalue()).decode()
        logo_top = f"<div style='text-align: center;'><img src='data:{inst_logo.type};base64,{b64}' style='max-height: 70px;'/></div>"
        logo_footer = f"<img src='data:{inst_logo.type};base64,{b64}' style='height: 18px; vertical-align: middle; margin-right: 8px;'/>"
    
    footer = f"""<div class="footer-container"><div class="footer"><p>{logo_footer}<strong>{i_name}</strong> | 📍 {i_address} | 📞 {i_contact} | 👨‍🏫 <strong>{t_name}</strong></p></div></div>"""
    padding = "10mm" if is_2_col else "20mm"
    col_style = "column-count: 2; column-gap: 10mm; font-size: 14px;" if is_2_col else "font-size: 16px;"

    return f"""<!DOCTYPE html><html><head><style>
    body {{ background: #f0f0f0; font-family: 'Times New Roman', serif; padding: 20px; display: flex; justify-content: center; }} 
    .a4-page {{ background: white; width: 210mm; min-height: 297mm; padding: {padding}; box-shadow: 0 0 10px rgba(0,0,0,0.2); position: relative; padding-bottom: 25mm; }} 
    @media print {{ 
        body {{ background: white; padding: 0; }} 
        .a4-page {{ box-shadow: none; width: 100%; padding-bottom: 20mm; }} 
        @page {{ size: A4; margin: 10mm; }} 
        .footer-container {{ position: fixed; bottom: 0; left: 0; width: 100%; background: white; }}
    }} 
    h1, h2, h3 {{ text-align: center; column-span: all; }} 
    .content-body {{ {col_style} }} 
    .footer-container {{ text-align: center; margin-top: 20px; }}
    .footer {{ padding-top: 10px; border-top: 2px dashed #bbb; font-size: 12px; color: #444; display: inline-block; width: 90%; }}
    </style></head><body><div class="a4-page">{logo_top}<div class="content-body">{html_body}</div>{footer}</div></body></html>"""

# ✅ WORD EXPORT
def create_word_docx(md_content, i_name, i_address, i_contact, t_name, inst_logo=None, is_2_col=False):
    doc = Document()
    md_content = md_content.replace('\r', '')
    
    style = doc.styles['Normal']
    font = style.font
    font.name = 'Arial' 
    font.size = Pt(11)
    
    rFonts = style.element.rPr.rFonts
    if rFonts is not None:
        rFonts.set(qn('w:cs'), 'Mangal') 
    
    for i in range(3):
        try:
            h_style = doc.styles[f'Heading {i}']
            h_style.font.name = 'Arial'
            if h_style.element.rPr.rFonts is not None:
                h_style.element.rPr.rFonts.set(qn('w:cs'), 'Mangal')
            h_style.font.color.rgb = RGBColor(0, 0, 0)
            if i == 0:
                h_style.font.size = Pt(16)
                h_style.font.bold = True
            elif i == 1:
                h_style.font.size = Pt(12)
                h_style.font.bold = True
            elif i == 2:
                h_style.font.size = Pt(11)
                h_style.font.bold = True
        except KeyError: pass

    if is_2_col:
        for section in doc.sections:
            section.top_margin = section.bottom_margin = section.left_margin = section.right_margin = Inches(0.4)

    if inst_logo is not None:
        try:
            inst_logo.seek(0)
            doc.add_picture(inst_logo, height=Inches(0.7))
            doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
        except Exception: pass
        
    header = doc.add_heading(i_name, level=0)
    header.alignment = WD_ALIGN_PARAGRAPH.CENTER

    if is_2_col:
        new_section = doc.add_section(0) 
        sectPr = new_section._sectPr
        cols = sectPr.xpath('./w:cols')[0]
        cols.set(qn('w:num'), '2')
        cols.set(qn('w:space'), '720') 

    for line in md_content.split('\n'):
        if line.strip() == "": continue
        line = clean_math_for_word(line)
        
        if "Answer Key" in line or "ANSWER KEY" in line:
            doc.add_page_break() 
            doc.add_heading("Answer Key", level=1)
            continue
            
        if line.startswith('# '): 
            doc.add_heading(line.replace('# ', ''), level=1)
        elif line.startswith('## '): 
            doc.add_heading(line.replace('## ', ''), level=2)
        else:
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY 
            parts = re.split(r'\*\*(.*?)\*\*', line)
            for i, part in enumerate(parts):
                run = p.add_run(part)
                if i % 2 == 1: run.bold = True
                
    for section in doc.sections:
        footer = section.footer
        footer_para = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
        footer_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        if inst_logo is not None:
            try:
                inst_logo.seek(0)
                run_logo = footer_para.add_run()
                run_logo.add_picture(inst_logo, height=Inches(0.18))
                footer_para.add_run("  ") 
            except Exception: pass
            
        run_name = footer_para.add_run(f"{i_name}  |  ")
        run_name.font.name = 'Arial'
        run_name.font.size = Pt(10)
        run_name.font.bold = True
        run_name
