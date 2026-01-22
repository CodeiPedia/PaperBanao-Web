import streamlit as st
import google.generativeai as genai
import os
import base64
import time
import re
from PIL import Image

# --- 0. SESSION STATE SETUP ---
if 'manual_text_content' not in st.session_state:
    st.session_state.manual_text_content = ""
if 'manual_uploaded_images' not in st.session_state:
    st.session_state.manual_uploaded_images = []

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(page_title="PaperBanao.ai", page_icon="📄", layout="wide")

# --- 2. CUSTOM CSS ---
st.markdown("""
<style>
    .stButton>button { background-color: #1E88E5; color: white; font-size: 18px; width: 100%; border-radius: 8px; }
    .diagram-box { border: 2px dashed #1E88E5; padding: 15px; border-radius: 10px; background-color: #f0f8ff; margin-bottom: 20px;}
</style>
""", unsafe_allow_html=True)

# --- 3. HELPER FUNCTIONS ---
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
            options_html = "<br>" + "<br>".join([line.strip() for line in lines[1:]])
        formatted_html_parts.append(f"{formatted_question}{options_html}")
        current_q_num += 1
    return "<br><br>".join(formatted_html_parts)

def create_html_paper(ai_text, manual_text, manual_images, coaching, logo_data, details_dict, ai_q_count):
    split_marker = "[[BREAK]]"
    ai_questions, ai_answers = "", ""
    if split_marker in ai_text:
        parts = ai_text.split(split_marker)
        ai_questions = parts[0].replace(chr(10), '<br>')
        if len(parts) > 1: ai_answers = parts[1].replace(chr(10), '<br>')
    else:
        ai_questions = ai_text.replace(chr(10), '<br>')

    manual_questions_html = ""
    current_count = ai_q_count
    if manual_text:
        start_from = current_count + 1
        formatted_manual = process_manual_text_auto_number(manual_text, start_from)
        prefix = "<br><br>" if current_count > 0 else ""
        manual_questions_html = f"{prefix}{formatted_manual}"
        current_count += len(re.split(r'\n\s*\n', manual_text.strip()))

    manual_images_html = ""
    if manual_images:
        manual_images_html = "<br><br>"
        for img_file in manual_images:
            img_b64 = get_image_base64(img_file)
            manual_images_html += f"<div class='question-box' style='margin-top: 20px;'><p><strong>Refer to figure:</strong></p><img src='{img_b64}' style='max-width: 100%; max-height: 400px; border: 1px solid #ccc; padding: 5px;'></div>"

    final_body = ai_questions + manual_questions_html + manual_images_html
    
    # --- ANSWER KEY (COMPACT) ---
    if ai_answers:
        final_body += f"""
        <div class='page-break'></div>
        <div class='header'>
            <h2>Answer Key</h2>
            <p>{details_dict['Subject']} - {details_dict['Topic']}</p>
        </div>
        <div class='answer-key-grid'>
            {ai_answers}
        </div>
        """

    logo_html = f'<img src="{logo_data}" class="logo">' if logo_data else ''
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset='UTF-8'>
        <title>{details_dict['Topic']}</title>
        <link href='https://fonts.googleapis.com/css2?family=Noto+Sans+Devanagari&family=Roboto&display=swap' rel='stylesheet'>
        <style>
            body {{ font-family: 'Roboto', sans-serif; padding: 40px; max-width: 900px; margin: auto; line-height: 1.5; }}
            .main-container {{ border: 2px solid #000; padding: 30px; min-height: 950px; position: relative; }}
            .header-container {{ display: flex; align-items: center; border-bottom: 2px double #000; padding-bottom: 15px; margin-bottom: 20px; }}
            .logo {{ max-width: 100px; max-height: 100px; margin-right: 20px; }}
            .header-text {{ flex-grow: 1; text-align: center; }}
            .header-text h1 {{ margin: 0; font-size: 32px; text-transform: uppercase; color: #d32f2f; }}
            .info-table {{ width: 100%; margin-top: 10px; border-collapse: collapse; }}
            .info-table td {{ padding: 5px; font-weight: bold; border: 1px solid #ddd; }}
            .question-box {{ margin-bottom: 15px; font-size: 16px; }}
            .page-break {{ page-break-before: always; }}
            .footer {{ position: absolute; bottom: 10px; width: 100%; text-align: center; font-size: 10px; color: #555; }}
            
            /* Compact Answer Key */
            .answer-key-grid {{
                column-count: 4;
                column-gap: 20px;
                font-size: 14px;
                border: 1px solid #ccc;
                padding: 15px;
                background-color: #f9f9f9;
                text-align: left;
            }}
        </style>
    </head>
    <body>
        <div class='main-container'>
            <div class='header-container'>{logo_html}<div class='header-text'><h1>{coaching}</h1></div></div>
            <table class='info-table'>
                <tr><td>Exam: {details_dict['Exam Name']}</td><td>Subject: {details_dict['Subject']}</td></tr>
                <tr><td>Time: {details_dict['Time']}</td><td>Marks: {details_dict['Marks']}</td></tr>
                <tr><td colspan='2' style='text-align:center; background-color:#eee;'>Topic: {details_dict['Topic']}</td></tr>
            </table>
            <div style='font-size:12px; font-style:italic; margin:15px 0; padding:8px; background:#f9f9f9; border-left:4px solid #444;'>Instructions: All questions are compulsory.</div>
            <div class='content'>{final_body}</div>
            <div class='footer'>Created by PaperBanao.ai</div>
        </div>
    </body>
    </html>
    """
    return html_content

# --- 4. UI Setup ---

# --- HEADER LOGIC (SIDE-BY-SIDE LOGO & TEXT) ---
if os.path.exists("logo.png"):
    logo_b64 = get_image_base64("logo.png")
    # This HTML flexbox puts Logo LEFT and Text RIGHT perfectly
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
# -----------------------------------------------

with st.sidebar:
    st.header("⚙️ Control Panel")
    
    # API KEY
    user_key = st.text_input("Enter API Key (Optional):", type="password")
    if user_key: api_key = user_key
    elif "GOOGLE_API_KEY" in st.secrets: api_key = st.secrets["GOOGLE_API_KEY"]
    else: api_key = None

    # --- UNIVERSAL MODEL SELECTOR ---
    model_vision = None
    model_text = None
    
    if api_key:
        try:
            genai.configure(api_key=api_key)
            all_models = genai.list_models()
            for m in all_models:
                if 'generateContent' in m.supported_generation_methods:
                    if not model_text: model_text = genai.GenerativeModel(m.name)
                    if not model_vision:
                        if 'vision' in m.name or '1.5' in m.name or 'gemini-pro' in m.name:
                            model_vision = genai.GenerativeModel
