import streamlit as st
import google.generativeai as genai
import os
import base64
import time

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(page_title="PaperBanao.ai", page_icon="📄", layout="wide")

# --- 2. CUSTOM CSS ---
st.markdown("""
<style>
    .main-header { font-size: 42px; color: #1E88E5; text-align: center; font-weight: bold; font-family: sans-serif; }
    .sub-header { font-size: 18px; color: #555; text-align: center; margin-bottom: 20px; }
    .stButton>button { background-color: #1E88E5; color: white; font-size: 18px; width: 100%; border-radius: 8px; }
    .manual-box { border: 1px dashed #ccc; padding: 15px; border-radius: 10px; background-color: #f9f9f9; }
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

def create_html_paper(ai_text, manual_text, manual_images, coaching, logo_data, details_dict):
    split_marker = "[[BREAK]]"
    ai_questions, ai_answers = "", ""
    if split_marker in ai_text:
        parts = ai_text.split(split_marker)
        ai_questions = parts[0].replace(chr(10), '<br>')
        ai_answers = parts[1].replace(chr(10), '<br>')
    else:
        ai_questions = ai_text.replace(chr(10), '<br>')

    manual_questions_html = ""
    if manual_text:
        manual_questions_html = f"<div class='manual-section'><hr><h3>🔹 Part B: Manual Questions</h3>{manual_text.replace(chr(10), '<br>')}</div>"

    manual_images_html = ""
    if manual_images:
        manual_images_html = "<div class='image-section'><hr><h3>🔹 Part C: Picture Questions</h3>"
        for img_file in manual_images:
            img_b64 = get_image_base64(img_file)
            manual_images_html += f"<div class='question-box'><p><strong>Question Image:</strong></p><img src='{img_b64}' style='max-width: 100%; border: 1px solid #ccc; padding: 5px;'></div>"
        manual_images_html += "</div>"

    final_body = ai_questions + manual_questions_html + manual_images_html
    if ai_answers:
        final_body += f"<div class='page-break'></div><div class='header'><h2>Answer Key</h2><p>{details_dict['Subject']}</p></div><div class='content'>{ai_answers}</div>"

    logo_html = f'<img src="{logo_data}" class="logo">' if logo_data else ''
    
    # CSS defined safely
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
    api_key = st.text_input("🔑 Google API Key:", type="password")
    st.markdown("---")
    coaching_name = st.text_input("Institute Name:", value="Patna Success Classes")
    
    uploaded_logo = st.file_uploader("Upload Logo", type=['png', 'jpg'])
    final_logo = uploaded_logo if uploaded_logo else ("logo.png" if os.path.exists("logo.png") else None)
    if final_logo == "logo.png": st.success("✅ Default Logo Loaded")

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
    with st.expander("Manual Questions"):
        manual_text = st.text_area("Type questions...", height=100)
        manual_imgs = st.file_uploader("Images", type=['png', 'jpg'], accept_multiple_files=True)
    
    btn = st.button("🚀 Generate Paper")

# --- 5. LOGIC WITH AUTO-MODEL-SELECTOR ---
if btn:
    if not api_key: st.warning("⚠️ API Key Required")
    else:
        try:
            genai.configure(api_key=api_key)
            
            # --- SUPER SMART MODEL SELECTOR ---
            # यह कोड पहले लिस्ट देखेगा, फिर जो मिलेगा उसे यूज़ करेगा
            available_models = []
            try:
                for m in genai.list_models():
                    if 'generateContent' in m.supported_generation_methods:
                        available_models.append(m.name)
            except Exception as e:
                st.error(f"API Error: {e}")
                st.stop()
            
            # Priority Search: 1.5-flash -> gemini-pro -> any gemini
            chosen_model = None
            
            # Check 1: Try finding 'gemini-1.5-flash' exactly
            for m in available_models:
                if 'gemini-1.5-flash' in m:
                    chosen_model = m
                    break
            
            # Check 2: If not found, look for 'gemini-pro'
            if not chosen_model:
                for m in available_models:
                    if 'gemini-pro' in m:
                        chosen_model = m
                        break
            
            # Check 3: If still not found, take ANY gemini model
            if not chosen_model:
                for m in available_models:
                    if 'gemini' in m:
                        chosen_model = m
                        break
            
            if not chosen_model:
                st.error("❌ No Gemini models found enabled for your API Key.")
                st.write("Available models were:", available_models)
                st.stop()
                
            # st.info(f"✅ Connected to: {chosen_model}") # (Optional: Debugging के लिए)
            model = genai.GenerativeModel(chosen_model)
            
            ai_text = ""
            if num_questions > 0:
                with st.spinner(f'🤖 AI thinking using {chosen_model.split("/")[-1]}...'):
                    # Retry Loop for 429 Errors
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
                                if attempt < 2:
                                    st.warning(f"⏳ Traffic high. Retrying in 5s... ({attempt+1}/3)")
                                    time.sleep(5)
                                else:
                                    st.error("❌ Quota finished. Try later.")
                                    st.stop()
                            else:
                                st.error(f"Error: {e}")
                                st.stop()

            logo_b64 = get_image_base64(final_logo)
            details = { "Exam Name": exam_name, "Subject": subject, "Topic": topic, "Time": time_limit, "Marks": max_marks }
            final_html = create_html_paper(ai_text, manual_text, manual_imgs, coaching_name, logo_b64, details)
            
            st.balloons()
            st.success("✅ Paper Ready!")
            st.download_button("📥 Download HTML", final_html, f"{subject}_{topic}.html", "text/html")

        except Exception as e:
            st.error(f"System Error: {e}")