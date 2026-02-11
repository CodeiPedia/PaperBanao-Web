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
            @media print {{
                .page-break {{ page-break-before: always !important; display: block; }}
                body {{ -webkit-print-color-adjust: exact; }}
            }}
            body {{ font-family: 'Roboto', sans-serif; padding: 20px; max-width: 900px; margin: auto; line-height: 1.4; font-size: 14px; }}
            
            .main-container {{ border: 2px solid #000; padding: 30px; min-height: 950px; position: relative; background: white; }}
            .answer-container {{ border: 2px dashed #444; padding: 30px; margin-top: 50px; background: #fff; page-break-before: always; }}
            .header-container {{ display: flex; align-items: center; border-bottom: 2px double #000; padding-bottom: 10px; margin-bottom: 15px; }}
            .logo {{ max-width: 80px; max-height: 80px; margin-right: 20px; }}
            .header-text {{ flex-grow: 1; text-align: center; }}
            .header-text h1 {{ margin: 0; font-size: 28px; text-transform: uppercase; color: #111; }}
            .header-text p {{ margin: 2px 0; font-size: 14px; font-weight: bold; }}
            
            .info-table {{ width: 100%; margin-top: 10px; border-collapse: collapse; margin-bottom: 15px; }}
            .info-table td {{ padding: 5px; font-weight: bold; border: 1px solid #ddd; font-size: 13px; }}
            
            .content-2-column {{ column-count: 2; column-gap: 40px; column-rule: 1px solid #ccc; }}
            .content-standard {{ column-count: 1; }}
            .question-item {{ break-inside: avoid-column; margin-bottom: 15px; }}
            
            .footer {{ position: absolute; bottom: 10px; width: 100%; text-align: center; font-size: 10px; color: #555; left: 0; }}
            .answer-key-grid {{ column-count: 4; column-gap: 20px; font-size: 14px; margin-top: 10px; }}
        </style>
    </head>
    <body>
        <div class='main-container'>
            <div class='header-container'>
                {logo_html}
                <div class='header-text'>
                    <h1>{coaching}</h1>
                    <p>Viral Objective/Subjective Questions</p>
                </div>
            </div>
            <table class='info-table'>
                <tr><td>Exam: {details_dict['Exam Name']}</td><td>Subject: {details_dict['Subject']}</td></tr>
                <tr><td>Time: {details_dict['Time']}</td><td>Marks: {details_dict['Marks']}</td></tr>
                <tr><td colspan='2' style='text-align:center; background-color:#eee;'>Topic: {details_dict['Topic']}</td></tr>
            </table>
            
            <div class='{content_class}'>
                {final_questions_body}
            </div>
            
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


# --- NEW SMART MODEL FINDER (ANTI-404 ERROR) ---
def get_working_model(api_key):
    genai.configure(api_key=api_key)
    best_model_name = None
    
    # Google से पूछें कि कौन से मॉडल उपलब्ध हैं
    models = genai.list_models()
    for m in models:
        if 'generateContent' in m.supported_generation_methods:
            # 1.5 Flash सबसे तेज़ है, अगर मिले तो तुरंत चुन लें
            if '1.5-flash' in m.name:
                return genai.GenerativeModel(m.name)
            # अगर Flash नहीं है, तो 1.5 Pro ढूँढें
            elif '1.5-pro' in m.name and not best_model_name:
                best_model_name = m.name
            # अगर कुछ नहीं मिल रहा, तो जो भी 'gemini-pro' मिले उसे चुन लें
            elif 'gemini-pro' in m.name and not best_model_name:
                best_model_name = m.name
            # सबसे आखिर में, जो भी मॉडल मिले उसे सेव कर लें
            elif not best_model_name:
                best_model_name = m.name
                
    if best_model_name:
        return genai.GenerativeModel(best_model_name)
    else:
        raise Exception("No text generation models found in your Google account.")
# ----------------------------------------------


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

with st.sidebar:
    st.header("⚙️ Control Panel")
    
    st.markdown("### 🔑 API License Required")
    api_key = st.text_input("Enter Your Gemini API Key:", type="password", help="Get your free key from Google AI Studio")
    
    if not api_key:
        st.warning("⚠️ Please enter your API Key to proceed.")
    else:
        st.success("✅ API Key Ready!")

    st.markdown("---")
    coaching_name = st.text_input("Institute Name:", value="Maa Sarswati Coaching Center")
    uploaded_logo = st.file_uploader("Upload Institute Logo", type=['png', 'jpg'])
    final_logo = uploaded_logo 
    
    exam_name = st.text_input("Exam Name:", value="Final Board Exam")
    subject = st.text_input("Subject:", value="Biology")
    topic = st.text_input("Topic:", value="Life Processes")
    col1, col2 = st.columns(2)
    with col1: time_limit = st.text_input("Time:", value="3 Hours")
    with col2: max_marks = st.text_input("Marks:", value="50")
    
    st.markdown("---")
    st.subheader("📑 Select Paper Format")
    paper_format = st.selectbox("Format Type:", [
        "Coaching Style (2-Column PDF Style)", 
        "CBSE Board Pattern", 
        "BSEB (Bihar Board) Pattern",
        "Standard Custom"
    ])

    st.markdown("**Question Types to Include:**")
    q_mcq = st.checkbox("Multiple Choice (MCQs)", value=True)
    q_tf = st.checkbox("True / False", value=False)
    q_fib = st.checkbox("Fill in the Blanks", value=False)
    q_subj = st.checkbox("Subjective (Short/Long Qs)", value=False)

    num_questions = st.slider("Approx. Number of Questions:", 5, 150, 20)
    language = st.radio("Language:", ["Hindi", "English", "Bilingual"])
    
    st.markdown("---")
    st.subheader("2️⃣ Diagram Questions")
    with st.expander("✨ Generate from Diagram", expanded=False):
        diagram_img_upload = st.file_uploader("Upload Diagram:", type=['png', 'jpg', 'jpeg'], key="dia_up")
        
        if diagram_img_upload:
            st.image(diagram_img_upload, caption="Preview", use_column_width=True)
            diagram_prompt = st.text_input("Instruction:", key="dia_p")
            
            if st.button("Generate Question"):
                if not api_key: st.error("❌ API Key Required. Enter it at the top of the sidebar.")
                elif not diagram_prompt: st.warning("⚠️ Enter instruction.")
                else:
                    with st.spinner("AI Looking..."):
                        try:
                            # Using Smart Model Finder
                            smart_model = get_working_model(api_key)
                            
                            img_pil = Image.open(diagram_img_upload)
                            lang_hint = "in HINDI" if "Hindi" in language else "in ENGLISH"
                            full_prompt = [f"Create 1 MCQ {lang_hint}. Instruction: {diagram_prompt}. Format: Question text, then (A)..(B)..(C)..(D).. (All on one line separated by spaces)", img_pil]
                            
                            response = smart_model.generate_content(full_prompt)
                            sep = "\n\n" if st.session_state.manual_text_content else ""
                            st.session_state.manual_text_content += sep + response.text.strip()
                            st.session_state.manual_uploaded_images.append(diagram_img_upload)
                            st.success("Added!")
                            st.rerun()
                        except Exception as e: st.error(f"Error (Check API Key): {e}")

    st.markdown("---")
    with st.expander("3️⃣ Review / Edit Manual"):
        manual_text = st.text_area("Editor", value=st.session_state.manual_text_content, height=200)
        st.session_state.manual_text_content = manual_text
        if st.button("Clear All"):
            st.session_state.manual_text_content = ""
            st.session_state.manual_uploaded_images = []
            st.rerun()

    btn_final = st.button("🚀 Generate Final Paper", type="primary")

    st.markdown("---")
    st.markdown("### 📜 Session History")
    if len(st.session_state.paper_history) > 0:
        for idx, item in enumerate(reversed(st.session_state.paper_history)):
            with st.expander(f"{item['time']} - {item['format']}"):
                st.download_button(label="📥 Download Again", data=item['html'], file_name=item['file_name'], mime="text/html", key=f"hist_btn_{idx}")

# --- 5. MAIN LOGIC ---
if btn_final:
    if not api_key:
        st.error("⚠️ Please enter your API Key in the sidebar first!")
    else:
        if num_questions > 0:
            with st.spinner(f'Generating {paper_format} Paper...'):
                try:
                    # Using Smart Model Finder
                    smart_model = get_working_model(api_key)
                    
                    lang_prompt = "HINDI (Use authentic Hindi terminology)" if "Hindi" in language else "ENGLISH"
                    
                    types_list = []
                    if q_mcq: types_list.append("MCQs")
                    if q_tf: types_list.append("True/False")
                    if q_fib: types_list.append("Fill in the Blanks")
                    if q_subj: types_list.append("Subjective (Short and Long Answer questions)")
                    types_str = ", ".join(types_list) if types_list else "MCQs"

                    base_prompt = ""
                    
                    if paper_format == "CBSE Board Pattern":
                        base_prompt = f"""
                        Create a CBSE style question paper for topic '{topic}' ({subject}). Language: {lang_prompt}.
                        Include the following question types: {types_str}. Total approx questions: {num_questions}.
                        Structure it strictly like a CBSE Final Exam:
                        <b>General Instructions:</b><br>...<br><br>
                        <b>SECTION A (Objective Type):</b> Include MCQs, Assertion-Reason, Fill in blanks (if selected).<br>
                        <b>SECTION B (Short Answer Type):</b> 2-3 mark questions.<br>
                        <b>SECTION C (Long Answer Type):</b> 5 mark questions.<br>
                        Wrap each question in <div class='question-item'>...</div> for formatting.
                        """
                    elif paper_format == "BSEB (Bihar Board) Pattern":
                        base_prompt = f"""
                        Create a BSEB (Bihar Board) style question paper for topic '{topic}' ({subject}). Language: {lang_prompt}. Total approx questions: {num_questions}.
                        Structure it strictly like a Bihar Board Exam:
                        <b>खण्ड-अ (वस्तुनिष्ठ प्रश्न / Objective Type):</b> 50% MCQs (Provide 4 options A, B, C, D for each).<br>
                        <b>खण्ड-ब (विषयनिष्ठ प्रश्न / Subjective Type):</b> 50% Short and Long answer questions.<br>
                        Include these types if selected: {types_str}.
                        Wrap each question in <div class='question-item'>...</div>.
                        """
                    else: 
                        base_prompt = f"""
                        Create a Test Paper for topic '{topic}' ({subject}). Language: {lang_prompt}. Total Questions: {num_questions}.
                        Include ONLY these selected question types: {types_str}.
                        Format guidelines for MCQs: 
                        <div class='question-item'><b>Q1. Question Text Here?</b><br>(A) Option A &nbsp;&nbsp;&nbsp;&nbsp; (B) Option B &nbsp;&nbsp;&nbsp;&nbsp; (C) Option C &nbsp;&nbsp;&nbsp;&nbsp; (D) Option D</div>
                        Format guidelines for True/False or Fill in Blanks:
                        <div class='question-item'><b>Qx. Question Text Here.</b> (True/False)</div>
                        Format guidelines for Subjective:
                        <div class='question-item'><b>Qx. Question Text Here.</b><br><br><br></div>
                        """

                    final_prompt = base_prompt + """
                    \n\nAt the very end of the output, add exactly [[BREAK]] followed by the Answer Key for ALL objective and subjective questions.
                    """

                    response = smart_model.generate_content(final_prompt)
                    ai_text_final = response.text
                    
                    details = {"Exam Name": exam_name, "Subject": subject, "Topic": topic, "Time": time_limit, "Marks": max_marks}
                    
                    final_manual_text = st.session_state.manual_text_content
                    final_manual_images = st.session_state.manual_uploaded_images
                    
                    final_html = create_html_paper(ai_text_final, final_manual_text, final_manual_images, coaching_name, get_image_base64(final_logo), details, paper_format)
                    
                    timestamp = datetime.now().strftime("%I:%M %p")
                    st.session_state.paper_history.append({"time": timestamp, "topic": topic, "subject": subject, "format": paper_format, "html": final_html, "file_name": f"{subject}_{paper_format}.html"})
                    
                    st.balloons()
                    st.download_button("📥 Download HTML", final_html, f"paper_{paper_format}.html", "text/html")
                except Exception as e: 
                    st.error(f"❌ AI Error (Please check your API Key / Network): {e}")
