import streamlit as st
import google.generativeai as genai
import PyPDF2
import os

# --- Page Config ---
st.set_page_config(page_title="PaperBanao - AI Question Paper", page_icon="📝", layout="centered")

# --- App Header & Logo ---
col_logo, col_title = st.columns([1, 5])
with col_logo:
    # अगर आपके folder में logo.png नाम की image है, तो वो यहाँ दिखेगी
    if os.path.exists("logo.png"):
        st.image("logo.png", width=80)
    else:
        st.markdown("<h1>📝</h1>", unsafe_allow_html=True) # Placeholder अगर logo नहीं है
with col_title:
    st.title("PaperBanao")
    
st.markdown("Generate precise question papers in seconds using AI.")

# --- API Key Setup (Sidebar) ---
st.sidebar.header("⚙️ Settings")
api_key = st.sidebar.text_input("Enter Google Gemini API Key:", type="password")

if api_key:
    genai.configure(api_key=api_key)
else:
    st.sidebar.warning("Please enter your API key to start generating papers.")

# --- PDF Text Extraction Function ---
def extract_text_from_pdf(uploaded_file, start_page, end_page):
    try:
        reader = PyPDF2.PdfReader(uploaded_file)
        total_pages = len(reader.pages)
        start_index = max(0, start_page - 1) 
        end_index = min(total_pages, end_page)
        
        extracted_text = ""
        for i in range(start_index, end_index):
            extracted_text += reader.pages[i].extract_text() + "\n"
        return extracted_text
    except Exception as e:
        return f"Error reading PDF: {e}"

# ==========================================
# --- CREATE TABS FOR PROFESSIONAL UI ---
# ==========================================
tab1, tab2 = st.tabs(["⚡ Quick Generate (By Syllabus)", "📄 Deep Extract (From PDF Book)"])

# ------------------------------------------
# TAB 1: ORIGINAL FEATURE (Syllabus Based)
# ------------------------------------------
with tab1:
    st.markdown("### Generate from Syllabus or Topics")
    st.markdown("Best for general tests where you don't need to strictly follow a specific textbook.")
    
    with st.form("quick_gen_form"):
        col1, col2, col_diff = st.columns(3)
        with col1:
            subject_t1 = st.text_input("Subject (e.g., Science)")
        with col2:
            grade_t1 = st.text_input("Class / Grade")
        with col_diff:
            difficulty_t1 = st.selectbox("Difficulty Level", ["Easy", "Medium", "Hard"], key="diff1")
            
        col3, col4, col5 = st.columns(3)
        with col3:
            mcq_t1 = st.number_input("Number of MCQs", min_value=0, value=5, key="mcq1")
        with col4:
            short_t1 = st.number_input("Short Qs (2 Marks)", min_value=0, value=3, key="sq1")
        with col5:
            long_t1 = st.number_input("Long Qs (5 Marks)", min_value=0, value=2, key="lq1")
            
        syllabus_t1 = st.text_area("Paste Syllabus or Topics to Cover", placeholder="e.g., Light reflection, Newton's laws...")
        
        submit_t1 = st.form_submit_button("🚀 Generate Quick Paper")

    if submit_t1:
        if not api_key:
            st.error("API Key is missing!")
        elif not subject_t1 or not syllabus_t1:
            st.error("Please fill in the Subject and Syllabus.")
        else:
            with st.spinner("Generating Paper..."):
                prompt1 = f"""
                You are an expert educator. Create a {grade_t1} level {subject_t1} exam.
                Topics to cover strictly: {syllabus_t1}
                Difficulty Level: {difficulty_t1}
                
                Generate exactly:
                - {mcq_t1} Multiple Choice Questions (with 4 options, answers hidden at the end)
                - {short_t1} Short Answer Questions
                - {long_t1} Long Answer Questions
                
                Ensure the questions reflect a '{difficulty_t1}' difficulty level. 
                Format it beautifully as a ready-to-print exam paper.
                """
                try:
                    model = genai.GenerativeModel('gemini-1.5-flash')
                    response = model.generate_content(prompt1)
                    st.success("Success!")
                    st.markdown("---")
                    st.markdown(response.text)
                    st.download_button("📥 Download Paper", data=response.text, file_name=f"{subject_t1}_Paper.txt")
                except Exception as e:
                    st.error(f"Error: {e}")

# ------------------------------------------
# TAB 2: NEW FEATURE (PDF Based)
# ------------------------------------------
with tab2:
    st.markdown("### Extract from Specific Book Pages")
    st.markdown("Best when you want questions generated **only** from the exact text of a specific textbook chapter.")
    
    with st.form("pdf_gen_form"):
        uploaded_pdf = st.file_uploader("Upload Book/Chapter (PDF)", type="pdf")
        
        col6, col7 = st.columns(2)
        with col6:
            start_p = st.number_input("Start Page", min_value=1, value=1)
        with col7:
            end_p = st.number_input("End Page", min_value=1, value=5)
            
        st.markdown("#### Exam Details")
        col8, col9, col10 = st.columns(3)
        with col8:
            subject_t2 = st.text_input("Subject", key="sub2")
        with col9:
            topic_t2 = st.text_input("Specific Topic", key="top2")
        with col10:
            difficulty_t2 = st.selectbox("Difficulty Level", ["Easy", "Medium", "Hard"], key="diff2")
        
        col11, col12, col13 = st.columns(3)
        with col11:
            mcq_t2 = st.number_input("Number of MCQs", min_value=0, value=5, key="mcq2")
        with col12:
            short_t2 = st.number_input("Short Qs", min_value=0, value=3, key="sq2")
        with col13:
            long_t2 = st.number_input("Long Qs", min_value=0, value=2, key="lq2")

        submit_t2 = st.form_submit_button("📑 Extract & Generate Paper")

    if submit_t2:
        if not api_key:
            st.error("API Key is missing!")
        elif not uploaded_pdf:
            st.error("Please upload a PDF document.")
        elif not subject_t2 or not topic_t2:
            st.error("Please fill in the Subject and Topic.")
        else:
            with st.spinner("Reading PDF and Generating Questions..."):
                document_text = extract_text_from_pdf(uploaded_pdf, start_p, end_p)
                prompt2 = f"""
                You are an expert exam creator. Generate an exam ONLY for the topic requested below using the provided text.
                - Subject: {subject_t2}
                - Target Topic: {topic_t2}
                - Difficulty Level: {difficulty_t2}
                
                CRITICAL INSTRUCTIONS:
                1. Ignore any text NOT related to '{topic_t2}'.
                2. Extract questions STRICTLY from the text provided below.
                3. Ensure the questions reflect a '{difficulty_t2}' difficulty level.
                4. Generate {mcq_t2} MCQs, {short_t2} Short Answer, and {long_t2} Long Answer questions.
                
                Textbook text:
                ---
                {document_text}
                ---
                """
                try:
                    model = genai.GenerativeModel('gemini-1.5-flash')
                    response = model.generate_content(prompt2)
                    st.success("Success!")
                    st.markdown("---")
                    st.markdown(response.text)
                    st.download_button("📥 Download PDF Paper", data=response.text, file_name=f"{topic_t2}_Paper.txt")
                except Exception as e:
                    st.error(f"Error: {e}")
