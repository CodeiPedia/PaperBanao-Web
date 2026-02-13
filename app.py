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
            <div class='header-container'>{logo_html}<div class='header-text'><h1>{coaching}</h1><p>Viral Objective/Subjective Questions</p></div></div>
            <table class='info-table'>
                <tr><td>Exam: {details_dict['Exam Name']}</td><td>Subject: {details_dict['Subject']}</td></tr>
                <tr><td>Time: {details_dict['Time']}</td><td>Marks: {details_dict['Marks']}</td></tr>
                <tr><td colspan='2' style='text-align:center; background-color:#eee;'>Topic: {details_dict['Topic']}</td></tr>
            </table>
            <div class='{content_class}'>{final_questions_body}</div>
            <div class='footer'>Created by PaperBanao.ai</div>
        </div>
        {f'''<div class='answer-container'><div class='header'><h2 style='text-align:center; margin-bottom:0;'>Answer Key</h2><p style='text-align:center; color:#666;'>{details_dict['Subject']} - {details_dict['Topic']}</p><hr></div><div class='answer-key-grid'>{ai_answers}</div></div>''' if ai_answers else ''}
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
    
    # --- 🌟 NEW: DIFFICULTY LEVEL ---
    difficulty = st.selectbox("Select Difficulty Level:", ["Easy", "Medium", "Hard"])
    # --------------------------------
    
    st.markdown("---")
    st.subheader("📝 Question Quantity")
    
    col_q1, col_q2 = st.columns(2)
    with col_q1:
        num_mcq = st.number_input("No. of MCQs:", min_value=0, value=10)
        num_fib = st.number_input("No. of Fill in Blanks:", min_value=0, value=5)
    with col_q2:
        num_tf = st.number_input("No. of True/False:", min_value=0, value=5)
        num_subj = st.number_input("No. of Short/Long Qs:", min_value=0, value=3)

    total_q = num_mcq + num_fib + num_tf + num_subj
    st.caption(f"Total Questions: {total_q}")

    paper_format = st.selectbox("Format Type:", ["Coaching Style (2-Column PDF Style)", "CBSE Board Pattern", "BSEB (Bihar Board) Pattern", "Standard Custom"])
    language = st.radio("Language:", ["Hindi", "English", "Bilingual"])
    
    st.markdown("---")
    st.subheader("2️⃣ Diagram Questions")
    with st.expander("✨ Generate from Diagram", expanded=False):
        diagram_img_upload = st.file_uploader("Upload Diagram:", type=['png', 'jpg', 'jpeg'], key="dia_up")
        if diagram_img_upload:
            st.image(diagram_img_upload, caption="Preview", use_column_width=True)
            diagram_prompt = st.text_input("Instruction:", key="dia_p")
            if st.button("Generate Question"):
                if not api_key: st.error("❌ API Key Required.")
                else:
                    with st.spinner("AI Looking..."):
                        try:
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

    st.markdown("---")
    st.markdown("### 📜 Session History")
    if len(st.session_state.paper_history) > 0:
        for idx, item in enumerate(reversed(st.session_state.paper_history)):
            with st.expander(f"{item['time']} - {item['format']}"):
                st.download_button(label="📥 Download Again", data=item['html'], file_name=item['file_name'], mime="text/html", key=f"hist_btn_{idx}")

# --- 6. MAIN LOGIC ---
if btn_final:
    if not api_key:
        st.error("⚠️ Please enter your API Key in the sidebar first!")
    elif total_q == 0:
        st.error("⚠️ Please select at least one question (MCQ, T/F etc).")
    else:
        with st.spinner(f'Generating {exam_name} Paper...'):
            try:
                smart_model = get_working_model(api_key)
                lang_prompt = "HINDI (Use authentic Hindi terminology)" if "Hindi" in language else "ENGLISH"

                # --- 🧠 INTELLIGENT PROMPT BUILDING ---
                
                has_exam = bool(exam_name.strip())
                has_subject = bool(subject.strip())
                has_topic = bool(topic.strip())

                scope_instruction = ""
                display_topic = "Full Syllabus"

                if has_exam and has_subject and has_topic:
                    scope_instruction = f"Strictly focus on Topic '{topic}' from Subject '{subject}' for Exam '{exam_name}'. Do not ask outside this topic."
                    display_topic = topic
                
                elif has_exam and has_subject and not has_topic:
                    scope_instruction = f"Create a FULL SYLLABUS paper for Subject '{subject}' relevant to Exam '{exam_name}'. Cover all important chapters of this subject."
                    display_topic = f"Full Syllabus ({subject})"

                elif has_exam and not has_subject:
                    scope_instruction = f"Create a FULL MOCK TEST for Exam '{exam_name}'. Include questions from ALL standard subjects (e.g. Math, Reasoning, GK, English etc) that appear in {exam_name}."
                    display_topic = "Full Mock Test (All Subjects)"
                
                else:
                    scope_instruction = f"Create a generic test paper for {subject if has_subject else 'General Knowledge'}."

                # --- 🌟 DIFFICULTY LOGIC ---
                diff_prompt = ""
                if difficulty == "Easy":
                    diff_prompt = "Questions should be DIRECT, Simple definitions, and basic formula based. Avoid complex twisting."
                elif difficulty == "Medium":
                    diff_prompt = "Questions should be moderate. Test conceptual understanding. Balance between easy and hard."
                else: # Hard
                    diff_prompt = "Questions should be CHALLENGING. Focus on in-depth application, multi-step problems, and high-level reasoning (JEE/NEET/Advanced style)."
                # ---------------------------

                qty_instruction = f"""
                You must generate EXACTLY:
                - {num_mcq} Multiple Choice Questions (MCQs)
                - {num_fib} Fill in the Blanks
                - {num_tf} True / False
                - {num_subj} Subjective (Short/Long) Questions
                Total: {total_q} Questions.
                """

                base_prompt = f"""
                You are an expert exam setter.
                Language: {lang_prompt}
                
                SCOPE: {scope_instruction}
                DIFFICULTY LEVEL: {difficulty} - {diff_prompt}
                
                QUANTITY: {qty_instruction}

                CRITICAL RULES: 
                1. DO NOT USE markdown asterisks (**) for bold text. Use HTML <b> tags.
                2. DO NOT USE LaTeX or `$` signs for chemical formulas. Use HTML <sub> tags strictly (e.g., C<sub>6</sub>H<sub>12</sub>O<sub>6</sub>).
                
                FORMATTING:
                - MCQs: <div class='question-item'><b>Q. Question?</b><br>(A) .. (B) .. (C) .. (D) ..</div>
                - True/False: <div class='question-item'><b>Q. Question?</b> (True/False)</div>
                - Fill in Blanks: <div class='question-item'><b>Q. Question with ______ ?</b></div>
                - Subjective: <div class='question-item'><b>Q. Question?</b><br><br></div>
                """
                
                if paper_format == "CBSE Board Pattern":
                    base_prompt += "\nTry to follow CBSE question phrasing style where possible."
                elif paper_format == "BSEB (Bihar Board) Pattern":
                    base_prompt += "\nTry to follow Bihar Board question phrasing style where possible."

                final_prompt = base_prompt + """
                \n\nAt the very end of the output, add exactly [[BREAK]] followed by the Answer Key for ALL objective questions.
                """
                
                response = smart_model.generate_content(final_prompt)
                ai_text_final = response.text
                
                # Update details for header
                final_sub_display = subject if has_subject else "All Subjects"
                details = {"Exam Name": exam_name, "Subject": final_sub_display, "Topic": display_topic, "Time": time_limit, "Marks": max_marks}
                
                final_manual_text = st.session_state.manual_text_content
                final_manual_images = st.session_state.manual_uploaded_images
                final_html = create_html_paper(ai_text_final, final_manual_text, final_manual_images, coaching_name, get_image_base64(final_logo), details, paper_format)
                
                timestamp = datetime.now().strftime("%I:%M %p")
                st.session_state.paper_history.append({"time": timestamp, "topic": display_topic, "subject": final_sub_display, "format": paper_format, "html": final_html, "file_name": f"{final_sub_display}_paper.html"})
                
                st.balloons()
                st.download_button("📥 Download HTML", final_html, f"paper_{exam_name}.html", "text/html")
            except Exception as e: st.error(f"❌ AI Error: {e}")
