import streamlit as st
import google.generativeai as genai
import os
import base64
import time
import re
from PIL import Image
from datetime import datetime

# --- 0. SESSION STATE SETUP ---
if 'manual_text_content' not in st.session_state:
    st.session_state.manual_text_content = ""
if 'manual_uploaded_images' not in st.session_state:
    st.session_state.manual_uploaded_images = []
if 'paper_history' not in st.session_state:
    st.session_state.paper_history = []

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(page_title="PaperBanao.ai", page_icon="📄", layout="wide")

# --- 2. CUSTOM CSS ---
st.markdown("""
<style>
    .stButton>button { background-color: #1E88E5; color: white; font-size: 18px; width: 100%; border-radius: 8px; }
    .diagram-box { border: 2px dashed #1E88E5; padding: 15px; border-radius: 10px; background-color: #f0f8ff; margin-bottom: 20px;}
    .history-box { padding: 10px; border-bottom: 1px solid #ddd; margin-bottom: 5px; font-size: 14px; }
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
        # Remove existing numbering
        first_line = re.sub(r'^(Q\d+[.)]|\d+[.)]|Q\.)\s*', '', first_line, flags=re.IGNORECASE)
        formatted_question = f"<b>Q{current_q_num}. {first_line}</b>"
        
        # Horizontal Options Logic for Manual Text
        options_html = ""
        if len(lines) > 1:
            # Join options with spaces instead of breaks
            options_joined = " &nbsp;&nbsp;&nbsp;&nbsp; ".join([line.strip() for line in lines[1:]])
            options_html = f"<br><div style='margin-top:5px;'>{options_joined}</div>"
            
        formatted_html_parts.append(f"{formatted_question}{options_html}")
        current_q_num += 1
    return "<br><br>".join(formatted_html_parts)

def create_html_paper(ai_text, manual_text, manual_images, coaching, logo_data, details_dict, ai_q_count):
    split_marker = "[[BREAK]]"
    ai_questions, ai_answers = "", ""
    
    # Separation Logic
    if split_marker in ai_text:
        parts = ai_text.split(split_marker)
        ai_questions = parts[0].replace(chr(10), '<br>')
        if len(parts) > 1: 
            ai_answers = parts[1].replace(chr(10), '<br>')
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
            manual_images_html += f"<div class='question-box' style='margin-top: 20px;'><p><strong>Refer to figure:</strong></p><img src='{img_b64}' style='max-width: 100%; max-height: 300px; border: 1px solid #ccc; padding: 5px;'></div>"

    final_questions_body = ai_questions + manual_questions_html + manual_images_html
    
    logo_html = f'<img src="{logo_data}" class="logo">' if logo_data else ''

    # --- HTML STRUCTURE ---
    # We close the first main-container BEFORE the answer key to force a clean page break.
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset='UTF-8'>
        <title>{details_dict['Topic']}</title>
        <link href='https://fonts.googleapis.com/css2?family=Noto+Sans+Devanagari&family=Roboto&display=swap' rel='stylesheet'>
        <style>
            @media print {{
                .page-break {{ page-break-before: always !important; display: block; }}
                body {{ -webkit-print-color-adjust: exact; }}
            }}
            body {{ font-family: 'Roboto', sans-serif; padding: 20px; max-width: 900px; margin: auto; line-height: 1.4; }}
            
            /* Main Paper Container */
            .main-container {{ 
                border: 2px solid #000; 
                padding: 30px; 
                min-height: 950px; 
                position: relative; 
                background: white;
            }}
            
            /* Answer Key Container (Separate Style) */
            .answer-container {{
                border: 2px dashed #444;
                padding: 30px;
                margin-top: 50px;
                background: #fff;
                page-break-before: always; /* Force New Page */
            }}

            .header-container {{ display: flex; align-items: center; border-bottom: 2px double #000; padding-bottom: 15px; margin-bottom: 20px; }}
            .logo {{ max-width: 100px; max-height: 100px; margin-right: 20px; }}
            .header-text {{ flex-grow: 1; text-align: center; }}
            .header-text h1 {{ margin: 0; font-size: 32px; text-transform: uppercase; color: #d32f2f; }}
            
            .info-table {{ width: 100%; margin-top: 10px; border-collapse: collapse; }}
            .info-table td {{ padding: 5px; font-weight: bold; border: 1px solid #ddd; }}
            
            .question-box {{ margin-bottom: 15px; font-size: 16px; }}
            .footer {{ position: absolute; bottom: 10px; width: 100%; text-align: center; font-size: 10px; color: #555; }}
            
            .answer-key-grid {{
                column-count: 4;
                column-gap: 20px;
                font-size: 14px;
                margin-top: 10px;
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
            
            <div class='content'>{final_questions_body}</div>
            
            <div class='footer'>Created by PaperBanao.ai</div>
        </div>

        {f'''
        <div class='answer-container'>
            <div class='header'>
                <h2 style='text-align:center; margin-bottom:0;'>Answer Key</h2>
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

# --- 4. UI Setup ---
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

# Initialize API Key
api_key = None

with st.sidebar:
    st.header("⚙️ Control Panel")
    
    st.markdown("### 🔑 API License")
    user_key = st.text_input("Enter Your API Key (Optional):", type="password", help="Enter your own Gemini Key.")
    
    if user_key:
        api_key = user_key
        st.success("✅ Using: Personal Key")
    elif "GOOGLE_API_KEY" in st.secrets:
        api_key = st.secrets["GOOGLE_API_KEY"]
        st.warning("⚠️ Using: Shared Free Key")
    else:
        api_key = None
        st.error("❌ Key Missing: Add 'GOOGLE_API_KEY' in Secrets.")

    # --- MODEL SETUP ---
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
                            model_vision = genai.GenerativeModel(m.name)
            if not model_vision and model_text: model_vision = model_text
        except: pass

    st.markdown("---")
    coaching_name = st.text_input("Institute Name:", value="Patna Success Classes")
    uploaded_logo = st.file_uploader("Upload Institute Logo", type=['png', 'jpg'])
    final_logo = uploaded_logo 
    
    exam_name = st.text_input("Exam Name:", value="Class 10 Unit Test")
    subject = st.text_input("Subject:", value="Science")
    topic = st.text_input("Topic:", value="Light")
    col1, col2 = st.columns(2)
    with col1: time_limit = st.text_input("Time:", value="45 Mins")
    with col2: max_marks = st.text_input("Marks:", value="20")
    
    st.markdown("---")
    st.subheader("1️⃣ Text Questions")
    num_questions = st.slider("Num Questions:", 0, 50, 5)
    
    st.markdown("**Difficulty Level:**")
    c1, c2, c3 = st.columns(3)
    diff_easy = c1.checkbox("Easy", value=True)
    diff_medium = c2.checkbox("Medium", value=True)
    diff_hard = c3.checkbox("Hard")
    
    selected_levels = []
    if diff_easy: selected_levels.append("Easy")
    if diff_medium: selected_levels.append("Medium")
    if diff_hard: selected_levels.append("Hard")
    if not selected_levels: selected_levels = ["Medium"]
    difficulty_str = ", ".join(selected_levels)
    
    language = st.radio("Language:", ["Hindi", "English", "Bilingual"])
    
    st.markdown("---")
    st.subheader("2️⃣ Diagram Questions")
    with st.expander("✨ Generate from Diagram", expanded=True):
        diagram_img_upload = st.file_uploader("Upload Diagram:", type=['png', 'jpg', 'jpeg'], key="dia_up")
        
        if diagram_img_upload:
            st.image(diagram_img_upload, caption="Preview", use_column_width=True)
            diagram_prompt = st.text_input("Instruction:", key="dia_p")
            
            if st.button("Generate Question"):
                if not api_key: st.error("❌ API Key Required")
                elif not model_vision: st.error("❌ Vision Model unavailable.")
                elif not diagram_prompt: st.warning("⚠️ Enter instruction.")
                else:
                    with st.spinner("AI Looking..."):
                        try:
                            img_pil = Image.open(diagram_img_upload)
                            lang_hint = "in HINDI" if "Hindi" in language else "in ENGLISH"
                            # UPDATED PROMPT FOR HORIZONTAL OPTIONS IN DIAGRAMS
                            full_prompt = [f"Create 1 MCQ {lang_hint}. Instruction: {diagram_prompt}. Format: Question text, then (A)..(B)..(C)..(D).. (All on one line separated by spaces)", img_pil]
                            
                            response = model_vision.generate_content(full_prompt)
                            sep = "\n\n" if st.session_state.manual_text_content else ""
                            st.session_state.manual_text_content += sep + response.text.strip()
                            st.session_state.manual_uploaded_images.append(diagram_img_upload)
                            st.success("Added!")
                            st.rerun()
                        except Exception as e: st.error(f"Error: {e}")

    st.markdown("---")
    with st.expander("3️⃣ Review / Edit Manual"):
        manual_text = st.text_area("Editor", value=st.session_state.manual_text_content, height=200)
        st.session_state.manual_text_content = manual_text
        if st.button("Clear All"):
            st.session_state.manual_text_content = ""
            st.session_state.manual_uploaded_images = []
            st.rerun()

    btn_final = st.button("🚀 Generate Final Paper", type="primary")

    # --- HISTORY SECTION ---
    st.markdown("---")
    st.markdown("### 📜 Session History")
    if len(st.session_state.paper_history) > 0:
        for idx, item in enumerate(reversed(st.session_state.paper_history)):
            with st.expander(f"{item['time']} - {item['topic']}"):
                st.write(f"**Subject:** {item['subject']}")
                st.download_button(
                    label="📥 Download Again",
                    data=item['html'],
                    file_name=item['file_name'],
                    mime="text/html",
                    key=f"hist_btn_{idx}"
                )
    else:
        st.caption("No papers generated in this session yet.")

# --- 5. MAIN LOGIC ---
if btn_final:
