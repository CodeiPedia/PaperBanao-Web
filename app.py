import streamlit as st
import google.generativeai as genai
import os
import base64
import time
import re

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(page_title="PaperBanao.ai", page_icon="📄", layout="wide")

# --- 2. CUSTOM CSS ---
st.markdown("""
<style>
    .main-header { font-size: 42px; color: #1E88E5; text-align: center; font-weight: bold; font-family: sans-serif; }
    .stButton>button { background-color: #1E88E5; color: white; font-size: 18px; width: 100%; border-radius: 8px; }
</style>
""", unsafe_allow_html=True)

# --- 3. HELPER FUNCTIONS ---
def get_image_base64(image_input):
    if not image_input: return None
    try:
        if isinstance(image_input, str):
            if os.path.exists(image_input):
                with open(image_input, "rb") as f: bytes_data = f.read()
            else: return None
        else: bytes_data = image_input.getvalue()
        base64_str = base64.b64encode(bytes_data).decode()
        return f"data:image/png;base64,{base64_str}"
    except: return None

def process_manual_text_auto_number(text, start_num):
    """
    Splits text by double newlines (\n\n) and assigns Q numbers automatically.
    """
    if not text: return ""
    
    # Split by double newline (User must leave gap between questions)
    raw_questions = re.split(r'\n\s*\n', text)
    formatted_html_parts = []
    
    current_q_num = start_num
    
    for q_block in raw_questions:
        q_block = q_block.strip()
        if not q_block: continue
        
        lines = q_block.split('\n')
        first_line = lines[0].strip()
        
        # Remove user typed number if exists (e.g. "1. Question" -> "Question")
        # This prevents "Q6. 1. Question"
        first_line = re.sub(r'^(Q\d+[.)]|\d+[.)]|Q\.)\s*', '', first_line, flags=re.IGNORECASE)
        
        # Format: Bold Question Number + Question Text
        formatted_question = f"<b>Q{current_q_num}. {first_line}</b>"
        
        # Handle Options (Rest of the lines)
        options_html = ""
        if len(lines) > 1:
            options_html = "<br>" + "<br>".join([line.strip() for line in lines[1:]])
            
        formatted_html_parts.append(f"{formatted_question}{options_html}")
        current_q_num += 1
        
    return "<br><br>".join(formatted_html_parts)

def create_html_paper(ai_text, manual_text, manual_images, coaching, logo_data, details_dict, ai_q_count):
    split_marker = "[[BREAK]]"
    ai_questions, ai_answers = "", ""
    
    # 1. Process AI Text
    if split_marker in ai_text:
        parts = ai_text.split(split_marker)
        ai_questions = parts[0].replace(chr(10), '<br>')
        ai_answers = parts[1].replace(chr(10), '<br>')
    else:
        ai_questions = ai_text.replace(chr(10), '<br>')

    # 2. Process Manual Text (AUTO NUMBERING)
    manual_questions_html = ""
    if manual_text:
        # Start number is AI count + 1
        start_from = ai_q_count + 1
        formatted_manual = process_manual_text_auto_number(manual_text, start_from)
        
        # Add a gap if there were AI questions
        prefix = "<br><br>" if ai_q_count > 0 else ""
        manual_questions_html = f"{prefix}{formatted_manual}"

    # 3. Process Manual Images
    manual_images_html = ""
    if manual_images:
        manual_images_html = "<br><br>"
        # Calculate image starting number
        # Note: Counting text lines is hard, so we just append images. 
        # Ideally, images are usually labeled "Figure Q".
        for img_file in manual_images:
            img_b64 = get_image_base64(img_file)
            manual_images_html += f"""
            <div class='question-box' style='margin-top: 20px;'>
                <p><strong>Question Figure:</strong></p>
                <img src='{img_b64}' style='max-width: 100%; border: 1px solid #ccc; padding: 5px; border-radius: 5px;'>
            </div>
            """

    final_body = ai_questions + manual_questions_html + manual_images_html

    if ai_answers:
        final_body += f"""
        <div class='page-break'></div>
        <div class='header'>
            <h2>Answer Key</h2>
            <p>{details_dict['Subject']} - {details_dict['Topic']}</p>
        </div>
        <div class='content'>{ai_answers}</div>
        """

    logo_html = f'<img src="{logo_data}" class="logo">' if logo_data else ''
    
    css_style = """
        body { font-family: 'Roboto', sans-serif; padding: 40px; max-width: 900px; margin: auto; line-height: 1.5; }
        .main-container { border: 2px solid #000; padding: 30px; min-height: 950px; position: relative; }
        .header-container { display: flex; align-items: center; border-bottom: 2px double #000; padding-bottom: 15px; margin-bottom: 20px; }
        .logo { max-width: 100px; max-height: 100px; margin-right: 20px; }
        .header-text { flex-grow: 1; text-align: center; }
        .header-text h1 { margin: 0; font-size: 32px; text-transform: uppercase; color: #d32f2f; }
        .info-table { width: 100%; margin-top: 10px; border-collapse: collapse; }
        .info-table td { padding: 5px; font-weight: bold; border: 1px solid #ddd; }
        .question-box { margin-bottom: 15px; font-size: 16px; }
        .page-break { page-break-before: always; }
        .footer { position: absolute; bottom: 10px; width: 100%; text-align: center; font-size: 10px; color: #555; }
    """

    return f"""<!DOCTYPE html><html><head><meta charset='UTF-8'><title>{details_dict['Topic']}</title>
    <link href='https://fonts.googleapis.com/css2?family=Noto+Sans+Devanagari&family=Roboto&display=swap' rel='stylesheet'>
    <style>{css_style}</style></head><body>
    <div class='main-container'>
        <div class='header-container'>{logo_html}<div class='header-text'><h1>{coaching}</h1></div></div>
        <table class='info-table'>
            <tr><td>Exam: {details_dict['Exam Name']}</td><td>Subject: {details_dict['Subject']}</td></tr>
            <tr><td>Time: {details_dict['Time']}</td><td>Marks: {details_dict['Marks']}</td></tr>
            <tr><td colspan='2' style='text-align:center; background-color:#eee;'>Topic: {details_dict['Topic']}</td></tr>
        </table>
        <div style='font-size:12px; font-style:italic; margin:15px 0; padding:8px; background:#f9f9f9; border-left:4px solid #444;'>
            Instructions: All questions are compulsory. / सभी प्रश्न अनिवार्य हैं।
        </div>
        <div class='content'>{final_body}</div>
        <div class='footer'>Created by PaperBanao.ai • Best of Luck!</div>
    </div></body></html>"""

# --- 4. UI ---
st.markdown('<div class="main-header">📄 PaperBanao.ai</div>', unsafe_allow_html=True)

with st.sidebar:
    st.header("⚙️ Control Panel")
    
    st.markdown("### 🔑 API License")
    user_key = st.text_input("Enter Your API Key (Optional):", type="password")
    
    if user_key:
        api_key = user_key
        st.info("👤 Using: Personal Key")
    elif "GOOGLE_API_KEY" in st.secrets:
        api_key = st.secrets["GOOGLE_API_KEY"]
        st.success("✅ Using: Free Shared License")
    else:
        api_key = None
        st.error("❌ No License Found.")

    st.markdown("---")
    coaching_name = st.text_input("Institute Name:", value="Patna Success Classes")
    
    uploaded_logo = st.file_uploader("Upload Logo", type=['png', 'jpg'])
    final_logo = uploaded_logo if uploaded_logo else ("logo.png" if os.path.exists("logo.png") else None)

    exam_name = st.text_input("Exam Name:", value="Class 10 Unit Test")
    subject = st.text_input("Subject:", value="Science")
    topic = st.text_input("Topic:", value="Light")
    col1, col2 = st.columns(2)
    with col1: time_limit = st.text_input("Time:", value="45 Mins")
    with col2: max_marks = st.text_input("Marks:", value="20")
    
    st.markdown("---")
    num_questions = st.slider("AI Questions:", 0, 50, 5)
    language = st.radio("Language:", ["Hindi", "English", "Bilingual"])
    
    st.markdown("---")
    with st.expander("Manual Questions (Type here)"):
        st.caption("✨ Auto-Numbering Active: Just type question and options. Leave a blank line between questions.")
        manual_text = st.text_area("Question Box", height=200, placeholder="What is the capital of India?\n(A) Patna\n(B) Delhi\n\nWho is the PM?\n(A) Modi\n(B) Rahul")
        manual_imgs = st.file_uploader("Images", type=['png', 'jpg'], accept_multiple_files=True)
    
    btn = st.button("🚀 Generate Paper")

# --- 5. LOGIC ---
if btn:
    if not api_key: st.warning("⚠️ API Key Required.")
    else:
        try:
            genai.configure(api_key=api_key)
            
            # Smart Model Selector
            available_models = []
            try:
                for m in genai.list_models():
                    if 'generateContent' in m.supported_generation_methods:
                        available_models.append(m.name)
            except: pass

            chosen_model = None
            for m in available_models:
                if 'gemini-1.5-flash' in m: chosen_model = m; break
            if not chosen_model:
                for m in available_models:
                    if 'gemini' in m: chosen_model = m; break
            
            # If AI questions needed but no model found
            if not chosen_model and num_questions > 0:
                st.error("❌ No AI Model found.")
                st.stop()
                
            model = genai.GenerativeModel(chosen_model) if chosen_model else None
            
            ai_text = ""
            # Only call API if num_questions > 0
            if num_questions > 0 and model:
                with st.spinner(f'🤖 Thinking...'):
                    for attempt in range(3):
                        try:
                            lang_prompt = "HINDI (Devanagari)" if "Hindi" in language else "ENGLISH"
                            if "Bilingual" in language: lang_prompt = "ENGLISH followed by HINDI translation"
                            prompt = f"Create {num_questions} MCQ for '{topic}' ({subject}). Lang: {lang_prompt}. Format: <b>Q1. ?</b><br>(A)..<br> End with [[BREAK]] then Answer Key."
                            
                            response = model.generate_content(prompt)
                            ai_text = response.text
                            break 
                        except Exception as e:
                            if "429" in str(e) or "quota" in str(e).lower():
                                if attempt < 2: time.sleep(5)
                                else: st.error("❌ Quota full.")
                            else:
                                st.error(f"Error: {e}")
                                st.stop()

            logo_b64 = get_image_base64(final_logo)
            details = { "Exam Name": exam_name, "Subject": subject, "Topic": topic, "Time": time_limit, "Marks": max_marks }
            
            # Pass num_questions to the function so it knows where to start numbering manual ones
            final_html = create_html_paper(ai_text, manual_text, manual_imgs, coaching_name, logo_b64, details, num_questions)
            
            st.balloons()
            st.success("✅ Paper Ready!")
            st.download_button("📥 Download HTML", final_html, f"{subject}_{topic}.html", "text/html")

        except Exception as e:
            st.error(f"System Error: {e}")
