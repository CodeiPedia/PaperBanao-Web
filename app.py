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
        <link href='https://fonts.googleapis.com
