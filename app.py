import streamlit as st
import google.generativeai as genai
import os
import base64
import time
import re
from PIL import Image
from datetime import datetime

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(page_title="PaperBanao.ai", page_icon="📄", layout="wide")

# --- 2. SESSION STATE SETUP ---
if 'manual_text_content' not in st.session_state:
    st.session_state.manual_text_content = ""
if 'manual_uploaded_images' not in st.session_state:
    st.session_state.manual_uploaded_images = []
if 'paper_history' not in st.session_state:
    st.session_state.paper_history = []

# --- 3. CUSTOM CSS ---
st.markdown("""
<style>
    .stButton>button { background-color: #1E88E5; color: white; font-size: 18px; width: 100%; border-radius: 8px; }
    .diagram-box { border: 2px dashed #1E88E5; padding: 15px; border-radius: 10px; background-color: #f0f8ff; margin-bottom: 20px;}
    .q-box { background-color: #f8f9fa; padding: 10px; border-radius: 8px; margin-bottom: 10px; border: 1px solid #ddd; }
</style>
""", unsafe_allow_html=True)

# --- 4. HELPER FUNCTIONS ---
def get_image_base64(image_input):
    if not image_input: return None
    try:
        if isinstance(image_input, Image.Image):
            from io import BytesIO
            buffered = BytesIO()
            image_input.save(buffered, format="PNG")
            bytes_data = buffered.getvalue()
        elif isinstance(image_input, str):
            if os.path.exists(image_input):
                with open(image_input, "rb") as f: bytes_data = f.read()
            else: return None
        else:
            bytes_data = image_input.getvalue()
        base64_str = base64.b64encode(bytes_data).decode()
        return f"data:image/png;base64,{base64_str}"
    except Exception as e: return None

def process_manual_text_auto_number(text, start_num):
    if not text: return ""
    raw_questions = re.split(r'\n\s*\n', text)
    formatted_html_parts = []
    current_q_num = start_num
    for q_block in raw_questions:
        q_block = q_block.strip()
        if not q_block: continue
        lines = q_block.split('\n')
        first_line = lines[0].strip()
        first_line = re.sub(r'^(Q\d+[.)]|\d+[.)]|Q\.)\s*', '', first_line, flags=re.IGNORECASE)
        formatted_question = f"<b>Q{current_q_num}. {first_line}</b>"
        options_html = ""
        if len(lines) > 1:
            options_joined = " &nbsp;&nbsp;&nbsp;&nbsp; ".join([line.strip() for line in lines[1:]])
            options_html = f"<br><div style='margin-top:5px;'>{options_joined}</div>"
        formatted_html_parts.append(f"<div class='question-item'>{formatted_question}{options_html}</div>")
        current_q_num += 1
    return "<br><br>".join(formatted_html_parts)

def create_html_paper(ai_text, manual_text, manual_images, coaching, logo_data, details_dict, paper_format):
    # Formatting Cleanups
    ai_text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', ai_text)
    ai_text = re.sub(r'#{1,6}\s?', '', ai_text)
    # Chemistry Fixes
    ai_text = re.sub(r'\$_\{([0-9a-zA-Z+-]+)\}\$', r'<sub>\1</sub>', ai_text)
    ai_text = re.sub(r'\$_([0-9a-zA-Z+-]+)\$', r'<sub>\1</sub>', ai_text)
    ai_text = re.sub(r'_\{([0-9a-zA-Z+-]+)\}', r'<sub>\1</sub>', ai_text)
    ai_text = re.sub(r'_([0-9]+)', r'<sub>\1</sub>', ai_text)
    ai_text = ai_text.replace('$', '')

    split_marker = "[[BREAK]]"
    ai_questions, ai_answers = "", ""
    if split_marker in ai_text:
        parts = ai_text.split(split_marker)
        ai_questions = parts[0].replace(chr(10), '<br>')
        if len(parts) > 1: ai_answers = parts[1].replace(chr(10), '<br>')
    else:
        ai_questions = ai_text.replace(chr(10), '<br>')

    manual_questions_html = ""
    current_count = 10 
    if manual_text:
        formatted_manual = process_manual_text_auto_number(manual_text, current_count)
        manual_questions_html = f"<br><br>{formatted_manual}"

    manual_images_html = ""
    if manual_images:
        manual_images_html = "<br><br>"
        for img_file in manual_images:
            img_b64 = get_image_base64(img_file)
            manual_images_html += f"<div class='question-box' style='margin-top: 20px;'><p><strong>Refer to figure:</strong></p><img src='{img_b64}' style='max-width: 100%; max-height: 300px; border: 1px solid #ccc; padding: 5px;'></div>"

    final_questions_body = ai_questions + manual_questions_html + manual_images_html
    logo_html = f'<img src="{logo_data}" class="logo">' if logo_data else ''
    content_class = "content-standard"
    if paper_format == "Coaching Style (2-Column PDF Style)":
        content_class = "content-2-column"

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset='UTF-8'>
        <title>{details_dict['Topic']}</title>
        <link href='https://fonts.googleapis.com/css2?family=Noto+Sans+Devanagari&family=Roboto&display=swap' rel='stylesheet'>
        <style>
            @page {{
                size: A4;
                margin: 10mm;
            }}
            @media print {{
                html, body {{ width: 210mm; height: 297mm; }}
                .main-container {{ border: 2px solid #000 !important; width: 100% !important; margin: 0 !important; box-shadow: none !important; }}
                .page-break {{ page-break-before: always !important; display: block; }}
                body {{ -webkit-print-color-adjust: exact; }}
            }}
            body {{ font-family: 'Roboto', sans-serif; padding: 20px; background: #f0f0f0; }}
            .main-container {{ 
                border: 2px solid #000; padding: 25px; background: white; 
                width: 100%; max-width: 210mm; margin: 0 auto; box-sizing: border-box; min-height: 290mm;
            }}
            .answer-container {{ border: 2px dashed #444; padding: 30px; margin-top: 50px; background: #fff; page-break-before: always; }}
            .header-container {{ display: flex; align-items: center; border-bottom: 2px double #000; padding-bottom: 10px; margin-bottom: 15px; }}
            .logo {{ max-width: 80px; max-height: 80px; margin-right: 20px; }}
            .header-text {{ flex-grow: 1; text-align: center; }}
            .header-text h1 {{ margin: 0; font-size: 26px; text-transform: uppercase; color: #000; }}
            .header-text p {{ margin: 2px 0; font-size: 14px; font-weight: bold; }}
            .info-table {{ width: 100%; margin-top: 10px; border-collapse: collapse; margin-bottom: 15px; }}
            .info-table td {{ padding: 5px; font-weight: bold; border: 1px solid #000; font-size: 13px; }}
            .content-2-column {{ column-count: 2; column-gap: 30px; column-rule: 1px solid #ccc; text-align: justify; }}
            .content-standard {{ column-count: 1; text-align: justify; }}
            .question-item {{ break-inside: avoid-column; margin-bottom: 12px; font-size: 15px; }}
            .footer {{ position: absolute; bottom: 5px; width: 100%; text-align: center; font-size: 10px; color: #555; left: 0; }}
            
            /* --- 🌟 UPDATED ANSWER KEY STYLE (Detailed) --- */
            .answer-key-grid {{ 
                column-count: 2; /* 2 Columns for better readability of long answers */
                column-gap: 40px; 
                font-size: 13px; 
                margin-top: 10px; 
                text-align: left;
            }}
            .answer-item {{ margin-bottom: 15px; break-inside: avoid-column; }}
            .ans-hint {{ color: #666; font-style: italic; font-size: 12px; display: block; margin-top: 2px; }}
            .ans-detail {{ color: #000; display: block; margin-top: 4px; border-left: 2px solid #ddd; padding-left: 8px; }}
        </style>
    </head>
    <body>
        <div class='main-container'>
            <div class='header-container'>{logo_html}<div class='header-text'><h1>{coaching}</h1><p>Viral Objective/Subjective Questions</p></div></div>
            <table class='info-table'>
                <tr><td>Exam: {details_dict['Exam Name']}</td><td>Subject: {details_dict['Subject']}</td></tr>
                <tr><td>Time: {details_dict['Time']}</td><td>Marks: {details_dict['Marks']}</td></tr>
                <tr><td colspan='2' style='text-align:center; background-color:#eee;'>Topic: {details_dict['Topic']}</td></tr>
            </table>
            <div class='{content_class}'>{final_questions_body}</div>
            <div class='footer'>Created by PaperBanao.ai</div>
        </div>
        {f'''
        <div class='answer-container'>
            <div class='header'>
                <h2 style='text-align:center; margin-bottom:0;'>Detailed Solutions & Hints</h2>
                <p style='text-align:center; color:#666;'>{details_dict['Subject']} - {details_dict['Topic']}</p>
                <hr>
            </div>
            <div class='answer-key-grid'>
                {ai_answers}
            </div>
        </div>
        ''' if ai_answers else ''}
    </body>
    </html>
    """
    return html_content

def get_working_model(api_key):
    genai.configure(api_key=api_key)
    best_model_name = None
    models = genai.list_models()
    for m in models:
        if 'generateContent' in m.supported_generation_methods:
            if '1.5-flash' in m.name: return genai.GenerativeModel(m.name)
            elif '1.5-pro' in m.name and not best_model_name: best_model_name = m.name
            elif 'gemini-pro' in m.name and not best_model_name: best_model_name = m.name
            elif not best_model_name: best_model_name = m.name
    if best_model_name: return genai.GenerativeModel(best_model_name)
    else: raise Exception("No text generation models found in your Google account.")

# --- 5. UI SETUP ---
if os.path.exists("logo.png"):
    logo_b64 = get_image_base64("logo.png")
    st.markdown(f"""
    <div style="display: flex; align-items: center; justify-content: center; margin-bottom: 20px;">
        <img src="{logo_b64}" style="width: 80px; height: 80px; margin-right: 20px; border-radius: 12px;">
        <div style="text-align: left;">
            <h1 style="margin: 0; font-size: 42px; color: #1E88E5; line-height: 1.2;">PaperBanao.ai</h1>
            <p style="margin: 0; font-size: 14px; color: #666;">AI Exam Paper Generator</p>
        </div>
    </div>
    """, unsafe_allow_html=True)
else:
    st.markdown('<div class="main-header" style="text-align: center; color: #1E88E5;"><h1>📄 PaperBanao.ai</h1></div>', unsafe_allow_html=True)

with st.sidebar:
    st.header("⚙️ Control Panel")
    st.markdown("### 🔑 API License")
    api_key = st.text_input("Enter Your Gemini API Key:", type="password")
    if api_key: st.success("✅ API Key Ready!")
    else: st.warning("⚠️ Enter API Key to proceed.")
    st.markdown("---")

    coaching_name = st.text_input("Institute Name:", value="Maa Sarswati Coaching Center")
    uploaded_logo = st.file_uploader("Upload Institute Logo", type=['png', 'jpg'])
    final_logo = uploaded_logo 
    
    st.markdown("---")
    st.subheader("📚 Exam Details")
    
    exam_name = st.text_input("Exam Name (e.g., Class 12, RRB, SSC):", value="Class 10 Board")
    subject = st.text_input("Subject (Leave EMPTY for All Subjects Mock Test):", value="Science")
    topic = st.text_input("Topic (Leave EMPTY for Full Syllabus):", value="Light and Reflection")
    
    col1, col2 = st.columns(2)
    with col1: time_limit = st.text_input("Time:", value="3 Hours")
    with col2: max_marks = st.text_input("Marks:", value="100")
    
    st.markdown("---")
    st.subheader("📝 Questions & Difficulty")
    st.caption("Select Qty & Difficulty Mix (Easy, Medium, Hard)")

    with st.container():
        st.markdown("**1. Multiple Choice (MCQs)**")
        c1, c2 = st.columns([1, 2])
        num_mcq = c1.number_input("Qty:", min_value=0, value=10, key="n_mc
