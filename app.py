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
if "current_class" not in st.session_state: st.session_state.current_class = ""
if "current_marks" not in st.session_state: st.session_state.current_marks = ""

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
# BYOK Feature
st.sidebar.header("⚙️ Advanced Settings")
st.sidebar.write("Use your own free Gemini API Key when the server limit is reached.")
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
teacher_name = st.sidebar.text_input("Teacher Name", value="Mr. Suraj")
inst_address = st.sidebar.text_input("Institute Address", value="NH-22 Education Lane, City")
inst_contact = st.sidebar.text_input("Contact Number", value="+91 9310038172")

st.sidebar.markdown("---")
st.sidebar.header("📜 Formatting")
board_format = st.sidebar.selectbox("Board Pattern", ["Standard", "BSEB (Bihar Board)", "CBSE", "ICSE"])
paper_language = st.sidebar.selectbox("Paper Language", ["English", "Hindi", "Bilingual"])
include_answer_key = st.sidebar.toggle("Include Answer Key", value=True)
is_two_column = st.sidebar.toggle("📄 Two-Column Format", value=True) 

# ==========================================
# --- API CONFIGURATION LOGIC ---
# ==========================================
active_api_key = user_api_key if user_api_key.strip() != "" else SERVER_API_KEY
genai.configure(api_key=active_api_key)

try:
    valid_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
    flash_models = [m for m in valid_models if '1.5-flash' in m]
    working_model_name = flash_models[0] if flash_models else valid_models[0]
except Exception as e: 
    working_model_name = "gemini-1.5-flash" 
    if user_api_key:
        st.sidebar.error("❌ Invalid API Key. Please check your entry.")

# --- Helper Functions ---
def extract_text_from_pdf(uploaded_file, start_page, end_page):
    try:
        reader = PyPDF2.PdfReader(uploaded_file)
        start_index = max(0, start_page - 1) 
        end_index = min(len(reader.pages), end_page)
        return "".join([reader.pages[i].extract_text() + "\n" for i in range(start_index, end_index)])
    except Exception: return ""

def build_question_prompt(mcq_c, mcq_d, mcq_m, fib_c, fib_d, fib_m, tf_c, tf_d, tf_m, short_c, short_d, short_m, long_c, long_d, long_m, include_answers, selected_language, subject):
    reqs = []
    if mcq_c > 0: reqs.append(f"- {mcq_c} MCQs (Diff: {mcq_d}). [{mcq_m} Mark each]")
    if fib_c > 0: reqs.append(f"- {fib_c} FIBs (Diff: {fib_d}). [{fib_m} Marks each]")
    if tf_c > 0:  reqs.append(f"- {tf_c} True/False (Diff: {tf_d}). [{tf_m} Marks each]")
    if short_c > 0: reqs.append(f"- {short_c} Short Q (Diff: {short_d}). [{short_m} Marks each]")
    if long_c > 0:  reqs.append(f"- {long_c} Long Q (Diff: {long_d}). [{long_m} Marks each]")
    
    if selected_language == "English":
        lang_instruction = "LANGUAGE RULE: Generate the ENTIRE paper and answers strictly in the English language."
    elif selected_language == "Hindi":
        lang_instruction = "LANGUAGE RULE: Generate the paper in simple Hindi. Avoid tough academic Hindi words. Provide English terms in brackets for technical words. Example: 'अंश [Numerator]'."
    else:
        lang_instruction = "LANGUAGE RULE: Generate the paper in Hinglish (a mix of simple Hindi and English). Provide English terms in brackets for technical words."
    
    # 🌟 FIX: Stricter prompting for Q-numbering and options layout
    base_prompt = "\n".join(reqs) + f"\n\n{lang_instruction}\n\n" + f"""CRITICAL FORMATTING:
1. STRICTLY adhere to the subject: **{subject}**. Do NOT generate general knowledge questions or questions from other subjects.
2. START DIRECTLY WITH QUESTIONS. DO NOT GENERATE ANY INSTITUTE NAME, TIME, MARKS OR HEADER AT THE TOP.
3. Separate every Question and Answer Key with delimiter: `|||` on a new line.
4. MATH: USE UNICODE SYMBOLS ONLY (θ, π, √, ²). NO LaTeX. Write fractions as a/b.
5. NUMBERING: Always start a question with **Q** followed by the number, e.g., **Q1.**, **Q2.**, etc. DO NOT use markdown lists like `1. ` or `* `.
6. MCQs/FIBs OPTIONS: ALWAYS place the options on a NEW LINE below the question. Do NOT put them on the same line as the question.
   Example:
   **Q1.** What is the value of x?
   (A) 1   (B) 2   (C) 3   (D) 4
7. DO NOT use special checkboxes like ☐, ☑, •, ◦. Use [ ] or (A).
    """
    
    if include_answers: return base_prompt + "\nAdd '# Answer Key' at end, also separated by `|||`. Use the requested language in answers too."
    return base_prompt

def regenerate_single_question(old_text):
    prompt = f"Generate a NEW question to replace this. Keep the original language style. Use Unicode math symbols (θ, π, √, ²). ONLY output the question text:\n{old_text}"
    model = genai.GenerativeModel(working_model_name)
    return model.generate_content(prompt).text.strip()

def clean_math_for_word(text):
    text = re.sub(r'\\frac\{([^}]+)\}\{([^}]+)\}', r'(\1)/(\2)', text)
    text = re.sub(r'\\\((.*?)\\\)', r'\1', text)
    text = re.sub(r'\\\[(.*?)\\\]', r'\1', text)
    latex_map = {r'\pi': 'π', r'\theta': 'θ', r'\sqrt': '√', r'\times': '×', r'\div': '÷', '$': '', '^2': '²', '^3': '³'}
    for k, v in latex_map.items(): text = text.replace(k, v)
    text = text.replace('☐', '[ ]').replace('☑', '[x]').replace('•', '-').replace('◦', '-')
    text = text.replace('\u200b', '').replace('\u2022', '-').replace('\u25cf', '-').replace('\u25cb', '-')
    text = text.replace('\u25a0', '[ ]').replace('\u25a1', '[ ]')
    return text.strip()

# 🌟 HTML RENDERER 🌟
def create_a4_html(md_content, i_name, i_address, i_contact, t_name, inst_logo=None, is_2_col=False, sub="Subject", grade="Class", total_m="Marks", exam_time="Time", topics=""):
    md_content = clean_math_for_word(md_content)
    
    md_content = re.sub(r"^#.*?\*\*\*", "", md_content, count=1, flags=re.DOTALL).strip()
    md_content = re.sub(r"^\*\*Subject:\*\*.*?\n", "", md_content, flags=re.MULTILINE)
    md_content = re.sub(r"^\*\*Class:\*\*.*?\n", "", md_content, flags=re.MULTILINE)
    md_content = re.sub(r"^\*\*Marks:\*\*.*?\n", "", md_content, flags=re.MULTILINE)
    md_content = re.sub(r"^\*\*Time:\*\*.*?\n", "", md_content, flags=re.MULTILINE)
    
    # Optional: Fix any leftover markdown lists from AI output just in case
    md_content = re.sub(r"^\d+\.\s", "**Q.** ", md_content, flags=re.MULTILINE)

    md_content = md_content.strip()
    
    logo_html_inline = ""
    logo_footer = ""
    if inst_logo:
        inst_logo.seek(0)
        b64 = base64.b64encode(inst_logo.getvalue()).decode()
        logo_html_inline = f"<td style='width: 1%; padding-right: 15px; vertical-align: middle;'><img src='data:{inst_logo.type};base64,{b64}' style='max-height: 55px;'/></td>"
        logo_footer = f"<img src='data:{inst_logo.type};base64,{b64}' style='height: 18px; vertical-align: middle; margin-right: 8px;'/>"
    
    main_heading_text = topics.strip().upper() if topics.strip() != "" else sub.upper()
    
    custom_header = f"""
    <div style='border-bottom: 2px solid black; padding-bottom: 10px; margin-bottom: 10px; width: 100%;'>
        <table style='width: 100%; border-collapse: collapse; border: none; margin-bottom: 10px;'>
            <tr>
                <td style='text-align: center; vertical-align: middle; border: none;'>
                    <table style='margin: 0 auto;'>
                        <tr>
                            {logo_html_inline}
                            <td style='vertical-align: middle;'>
                                <h1 style='margin: 0; font-size: 24px; font-family: "Times New Roman", serif; font-weight: 900; text-transform: uppercase; white-space: nowrap;'>{i_name}</h1>
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
        <table style='width: 100%; font-weight: bold; font-size: 13px; border: none;'>
            <tr>
                <td style='text-align: left; vertical-align: bottom; width: 33%; border: none;'>Class : {grade}<br>Time : {exam_time}</td>
                <td style='text-align: center; vertical-align: middle; width: 34%; border: none;'>
                    <div style='border: 2px solid black; border-radius: 12px; display: inline-block; padding: 4px 25px; font-weight: bold; font-size: 14px; background: white;'>
                        EXAMINATION
                    </div>
                </td>
                <td style='text-align: right; vertical-align: bottom; width: 33%; border: none;'>Sub.: {sub}<br>Marks: {total_m}</td>
            </tr>
        </table>
    </div>
    <div style='border-top: 1px solid black; border-bottom: 3px solid black; padding: 2px 0; margin-bottom: 15px;'>
        <div style='background-color: black; color: white; padding: 5px; text-align: center; font-weight: bold; font-size: 15px; text-transform: uppercase; letter-spacing: 1px;'>
            Multiple Choice Questions & Theory
        </div>
    </div>
    <h2 style='text-align: center; text-decoration: underline; text-transform: uppercase; margin-top: 0; margin-bottom: 15px; font-size: 18px;'>{main_heading_text}</h2>
    """

    ans_split_marker = "|||ANSWER_KEY_SPLIT|||"
    md_content = re.sub(r'(?im)^#+\s*Answer Key.*$', ans_split_marker, md_content)
    
    if ans_split_marker in md_content:
        q_part, a_part = md_content.split(ans_split_marker)
        final_inner_html = f"""
        {custom_header}
        <div class="content-body">{markdown.markdown(q_part.strip())}</div>
        <div style="page-break-before: always; width: 100%;"></div>
        {custom_header}
        <h2 style="text-align: center; text-decoration: underline; margin-bottom: 15px;">ANSWER KEY</h2>
        <div class="content-body">{markdown.markdown(a_part.strip())}</div>
        """
    else:
        final_inner_html = f"""
        {custom_header}
        <div class="content-body">{markdown.markdown(md_content.strip())}</div>
        """
    
    col_style = "column-count: 2; column-gap: 15mm; column-rule: 1px solid #000; font-size: 14px;" if is_2_col else "font-size: 16px;"

    # 🌟 FIX: Added CSS to handle spacing between paragraphs (questions) better
    return f"""<!DOCTYPE html><html><head><style>
    body {{ background: #f0f0f0; font-family: 'Times New Roman', serif; margin: 0; padding: 20px; display: flex; justify-content: center; }} 
    .a4-page {{ background: white; width: 210mm; min-height: 297mm; padding: 20px; box-shadow: 0 0 10px rgba(0,0,0,0.2); box-sizing: border-box; position: relative; overflow: hidden; }} 
    .watermark {{ position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%) rotate(-45deg); font-size: 80px; color: rgba(0, 0, 0, 0.05); z-index: 0; pointer-events: none; white-space: nowrap; font-weight: bold; }}
    table {{ width: 100%; border-collapse: collapse; border: none; position: relative; z-index: 1; }}
    td {{ border: none; padding: 0; }}
    @media print {{ 
        @page {{ size: A4; margin: 0; }} 
        body {{ background: white; padding: 0; margin: 0; display: block; }} 
        .a4-page {{ box-shadow: none; width: 100%; min-height: auto; padding: 10mm; margin: 0; page-break-after: always; }} 
        tfoot {{ display: table-footer-group; }}
    }} 
    h1, h2, h3 {{ text-align: center; column-span: all; }} 
    .content-body {{ {col_style} position: relative; z-index: 1; text-align: justify; }} 
    .content-body p {{ margin-bottom: 8px; margin-top: 4px; }}
    .footer-content {{ text-align: center; margin-top: 20px; padding-top: 10px; border-top: 2px dashed #bbb; font-size: 13px; color: #444; position: relative; z-index: 1; background: white; }}
    </style></head><body><div class="a4-page">
    <div class="watermark">{i_name}</div>
    <table>
        <thead><tr><td></td></tr></thead>
        <tbody><tr><td>{final_inner_html}</td></tr></tbody>
        <tfoot><tr><td>
            <div class="footer-content">
                {logo_footer}<strong>{i_name}</strong> | 📍 {i_address} | 📞 {i_contact} | 👨‍🏫 <strong>{t_name}</strong>
            </div>
        </td></tr></tfoot>
    </table>
    </div></body></html>"""

# 🌟 WORD RENDERER 🌟
def create_word_docx(md_content, i_name, i_address, i_contact, t_name, inst_logo=None, is_2_col=False, sub="Subject", grade="Class", total_m="Marks", exam_time="Time", topics=""):
    doc = Document()
    
    md_content = re.sub(r"^#.*?\*\*\*", "", md_content, count=1, flags=re.DOTALL).strip()
    md_content = re.sub(r"^\*\*Subject:\*\*.*?\n", "", md_content, flags=re.MULTILINE)
    md_content = re.sub(r"^\*\*Class:\*\*.*?\n", "", md_content, flags=re.MULTILINE)
    md_content = re.sub(r"^\*\*Marks:\*\*.*?\n", "", md_content, flags=re.MULTILINE)
    md_content = re.sub(r"^\*\*Time:\*\*.*?\n", "", md_content, flags=re.MULTILINE)
    md_content = re.sub(r"^\d+\.\s", "**Q.** ", md_content, flags=re.MULTILINE)
    md_content = md_content.strip()
        
    md_content = md_content.replace('\r', '')
    
    style = doc.styles['Normal']
    font = style.font
    font.name = 'Arial' 
    font.size = Pt(11)
    
    rFonts = style.element.rPr.rFonts
    if rFonts is not None:
        rFonts.set(qn('w:cs'), 'Mangal') 
        rFonts.set(qn('w:ascii'), 'Arial')
        rFonts.set(qn('w:hAnsi'), 'Arial')
    
    for i in range(3):
        try:
            h_style = doc.styles[f'Heading {i}']
            h_style.font.name = 'Arial'
            if h_style.element.rPr.rFonts is not None:
                h_style.element.rPr.rFonts.set(qn('w:cs'), 'Mangal')
                h_style.element.rPr.rFonts.set(qn('w:ascii'), 'Arial')
                h_style.element.rPr.rFonts.set(qn('w:hAnsi'), 'Arial')
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

    def insert_chate_header():
        title_table = doc.add_table(rows=1, cols=1)
        p1 = title_table.cell(0,0).paragraphs[0]
        p1.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        if inst_logo is not None:
            try:
                inst_logo.seek(0)
                r_logo = p1.add_run()
                r_logo.add_picture(inst_logo, height=Inches(0.38))
                p1.add_run("   ") 
            except Exception: pass
            
        r1 = p1.add_run(i_name.upper())
        r1.bold = True
        r1.font.size = Pt(18)
        
        details_table = doc.add_table(rows=1, cols=3)
        details_table.autofit = False
        for cell in details_table.columns[0].cells: cell.width = Inches(2.0)
        for cell in details_table.columns[1].cells: cell.width = Inches(3.0)
        for cell in details_table.columns[2].cells: cell.width = Inches(2.0)

        p3 = details_table.cell(0,0).paragraphs[0]
        p3.alignment = WD_ALIGN_PARAGRAPH.LEFT
        r3 = p3.add_run(f"Class : {grade}\nTime : {exam_time}")
        r3.bold = True
        r3.font.size = Pt(10)

        p4 = details_table.cell(0,1).paragraphs[0]
        p4.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r4 = p4.add_run("\n[ EXAMINATION ]")
        r4.bold = True
        r4.font.size = Pt(12)

        p2 = details_table.cell(0,2).paragraphs[0]
        p2.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        r2 = p2.add_run(f"Sub.: {sub}\nMarks: {total_m}")
        r2.bold = True
        r2.font.size = Pt(10)
        
        doc.add_paragraph("__________________________________________________________________________").alignment = WD_ALIGN_PARAGRAPH.CENTER
        pt = doc.add_paragraph("MULTIPLE CHOICE QUESTIONS & THEORY")
        pt.alignment = WD_ALIGN_PARAGRAPH.CENTER
        pt.runs[0].bold = True
        
        main_heading_text = topics.strip().upper() if topics.strip() != "" else sub.upper()
        ptopics = doc.add_paragraph(main_heading_text)
        ptopics.alignment = WD_ALIGN_PARAGRAPH.CENTER
        ptopics.runs[0].underline = True
        ptopics.runs[0].font.size = Pt(14)
        ptopics.runs[0].bold = True
        doc.add_paragraph() 

    insert_chate_header()

    if is_2_col:
        new_section = doc.add_section(0) 
        sectPr = new_section._sectPr
        cols = sectPr.xpath('./w:cols')[0]
        cols.set(qn('w:num'), '2')
        cols.set(qn('w:space'), '720') 

    for line in md_content.split('\n'):
        line_clean = line.strip()
        if not line_clean: continue
        line_clean = clean_math_for_word(line_clean)
        
        if "Answer Key" in line_clean or "ANSWER KEY" in line_clean:
            doc.add_page_break() 
            insert_chate_header() 
            doc.add_heading("Answer Key", level=1)
            continue
            
        if line_clean.startswith('# '): 
            doc.add_heading(line_clean.replace('# ', ''), level=1)
        elif line_clean.startswith('## '): 
            doc.add_heading(line_clean.replace('## ', ''), level=2)
        else:
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY 
            parts = re.split(r'\*\*(.*?)\*\*', line_clean)
            for i, part in enumerate(parts):
                run = p.add_run(part)
                if i % 2 == 1: run.bold = True
                
    if doc.sections:
        footer = doc.sections[0].footer
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
        run_name.font.size = Pt(10)
        run_name.font.bold = True
        run_name.font.color.rgb = RGBColor(100, 100, 100)
        
        run_rest = footer_para.add_run(f"📍 {i_address}  |  📞 {i_contact}  |  👨‍🏫 {t_name}")
        run_rest.font.size = Pt(10)
        run_rest.font.color.rgb = RGBColor(100, 100, 100)
            
    bio = BytesIO()
    doc.save(bio)
    return bio.getvalue()

# ==========================================
# --- MAIN LAYOUT ---
# ==========================================
tab_create, tab_history = st.tabs(["🏠 Create Paper", "🗂️ Cloud History"])

with tab_create:
    if not is_pro and papers_used >= FREE_LIMIT:
        st.error("Free Trial Expired! Please Upgrade.")
        st.stop()
        
    st.markdown("### 1. Source")
    source = st.radio("Method:", ["⚡ Quick", "📄 PDF Extract"], horizontal=True, label_visibility="collapsed")

    sub, grade, syl, up_pdf = "", "", "", None
    pdf_text = ""

    if source == "⚡ Quick":
        c1, c2 = st.columns(2)
        sub = c1.text_input("Subject")
        grade = c2.text_input("Class")
        syl = st.text_area("Topics")
    else:
        c1, c2 = st.columns(2)
        sub = c1.text_input("Subject (PDF)")
        grade = c2.text_input("Class (PDF)")
        syl = st.text_area("Specific Topics (Optional)")
        
        up_pdf = st.file_uploader("Upload PDF Book/Notes", type="pdf")
        
        c3, c4 = st.columns(2)
        start_p = c3.number_input("Start Page", min_value=1, value=1)
        end_p = c4.number_input("End Page", min_value=1, value=5)
        
        if up_pdf is not None:
            pdf_text = extract_text_from_pdf(up_pdf, start_p, end_p)
            st.success(f"Extracted {len(pdf_text)} characters from pages {start_p} to {end_p}.")

    st.markdown("---")
    st.markdown("### 2. Counts & Marks")
    h1, h2, h3, h4 = st.columns([3, 2, 2, 3])
    h1.write("**Type**"); h2.write("**Count**"); h3.write("**Marks**"); h4.write("**Diff**")

    # MCQ Row
    c1, c2, c3, c4 = st.columns([3, 2, 2, 3])
    c1.write("MCQs")
    mcq_c = c2.number_input("mcq_c", 0, 50, 5, label_visibility="collapsed", key="m_c")
    mcq_m = c3.number_input("mcq_m", 1, 10, 1, label_visibility="collapsed", key="m_m")
    mcq_d = c4.selectbox("mcq_d", ["Easy", "Medium", "Hard"], label_visibility="collapsed", key="m_d")

    # FIB Row
    c1, c2, c3, c4 = st.columns([3, 2, 2, 3])
    c1.write("Fill in the Blanks")
    fib_c = c2.number_input("fib_c", 0, 20, 3, label_visibility="collapsed", key="f_c")
    fib_m = c3.number_input("fib_m", 1, 10, 1, label_visibility="collapsed", key="f_m")
    fib_d = c4.selectbox("fib_d", ["Easy", "Medium", "Hard"], label_visibility="collapsed", key="f_d")

    # True/False Row
    c1, c2, c3, c4 = st.columns([3, 2, 2, 3])
    c1.write("True / False")
    tf_c = c2.number_input("tf_c", 0, 20, 3, label_visibility="collapsed", key="t_c")
    tf_m = c3.number_input("tf_m", 1, 10, 1, label_visibility="collapsed", key="t_m")
    tf_d = c4.selectbox("tf_d", ["Easy", "Medium", "Hard"], label_visibility="collapsed", key="t_d")

    # Short Row
    c1, c2, c3, c4 = st.columns([3, 2, 2, 3])
    c1.write("Short Answer")
    short_c = c2.number_input("sh_c", 0, 20, 3, label_visibility="collapsed", key="s_c")
    short_m = c3.number_input("sh_m", 1, 10, 2, label_visibility="collapsed", key="s_m")
    short_d = c4.selectbox("sh_d", ["Easy", "Medium", "Hard"], label_visibility="collapsed", key="s_d", index=1)

    # Long Row
    c1, c2, c3, c4 = st.columns([3, 2, 2, 3])
    c1.write("Long Answer")
    long_c = c2.number_input("l_c", 0, 20, 2, label_visibility="collapsed", key="l_c")
    long_m = c3.number_input("l_m", 1, 20, 5, label_visibility="collapsed", key="l_m")
    long_d = c4.selectbox("l_d", ["Easy", "Medium", "Hard"], label_visibility="collapsed", key="l_d", index=2)

    total_q = mcq_c + fib_c + tf_c + short_c + long_c
    total_m = (mcq_c * mcq_m) + (fib_c * fib_m) + (tf_c * tf_m) + (short_c * short_m) + (long_c * long_m)
    
    st.markdown("---")
    st.info(f"📊 Total Questions: {total_q} | 🏆 Maximum Marks: {total_m}")

    if st.button("🚀 Generate Paper", use_container_width=True):
        st.session_state.current_subject = sub
        st.session_state.current_class = grade
        st.session_state.current_marks = str(total_m)
        
        q_reqs = build_question_prompt(
            mcq_c, mcq_d, mcq_m, fib_c, fib_d, fib_m, tf_c, tf_d, tf_m, short_c, short_d, short_m, long_c, long_d, long_m, include_answer_key, paper_language, sub
        )
        
        if source == "📄 PDF Extract" and pdf_text != "":
            prompt = f"Subject: {sub}\nClass: {grade}\nTopics: {syl}\n\n{q_reqs}\n\nIMPORTANT: Start directly with the questions. DO NOT generate any Title, Institute Name, Time, or Marks at the top.\n\nCREATE QUESTIONS STRICTLY FROM THE FOLLOWING TEXT EXTRACTED FROM A BOOK:\n\n{pdf_text}"
        else:
            prompt = f"Subject: {sub}\nClass: {grade}\nTopics: {syl}\n\n{q_reqs}\n\nIMPORTANT: Start directly with the questions. DO NOT generate any Title, Institute Name, Time, or Marks at the top."
        
        with st.spinner("Generating Paper..."):
            try:
                model = genai.GenerativeModel(working_model_name)
                resp = model.generate_content(prompt)
                blocks = resp.text.split("|||")
                st.session_state.blocks = [{'id': str(uuid.uuid4()), 'text': b.strip()} for b in blocks if b.strip()]
                st.session_state.file_name = f"{sub}_Paper"
                update_paper_count(st.session_state.username)
                st.rerun()
            except Exception as e:
                error_msg = str(e).lower()
                if "429" in error_msg or "quota" in error_msg:
                    st.error("🚨 The server's daily limit has been reached!")
                else:
                    st.error(f"Error: {e}")

    if st.session_state.blocks:
        st.markdown("---")
        with st.expander("🛠️ Edit Questions"):
            for i, b in enumerate(st.session_state.blocks):
                st.session_state.blocks[i]['text'] = st.text_area(f"Block {i}", b['text'], height=100)
        
        paper_md = "\n\n".join([b['text'] for b in st.session_state.blocks])
        
        f_html = create_a4_html(paper_md, inst_name, inst_address, inst_contact, teacher_name, inst_logo, is_two_column, st.session_state.current_subject, st.session_state.current_class, st.session_state.current_marks, exam_time, syl)
        f_word = create_word_docx(paper_md, inst_name, inst_address, inst_contact, teacher_name, inst_logo, is_two_column, st.session_state.current_subject, st.session_state.current_class, st.session_state.current_marks, exam_time, syl)
        
        c1, c2, c3 = st.columns(3)
        c1.download_button("🖨️ HTML", f_html, f"{st.session_state.current_subject}.html", "text/html")
        c2.download_button("📄 Word", f_word, f"{st.session_state.current_subject}.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        if c3.button("☁️ Save History"):
            data = {"username": st.session_state.username, "date": datetime.now().strftime("%Y-%m-%d"), "subject": st.session_state.current_subject, "board": board_format, "content": paper_md}
            supabase.table("papers").insert(data).execute()
            st.success("Saved!")

with tab_history:
    st.markdown("### Cloud History")
    res = supabase.table("papers").select("*").eq("username", st.session_state.username).order("id", desc=True).execute()
    if res.data:
        for p in res.data:
            with st.expander(f"📄 {p['subject']} ({p['date']})"):
                h_html = create_a4_html(p['content'], inst_name, inst_address, inst_contact, teacher_name, inst_logo, is_two_column, p['subject'], "N/A", "N/A", exam_time, "")
                st.download_button("Download HTML", h_html, f"History_{p['id']}.html", "text/html", key=f"h_{p['id']}")
                if st.button("Delete", key=f"d_{p['id']}"):
                    delete_paper(p['id']); st.rerun()
