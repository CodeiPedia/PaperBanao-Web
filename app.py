import streamlit as st
import google.generativeai as genai
import PyPDF2
import os

# --- Page Config ---
st.set_page_config(page_title="PaperBanao - AI Question Paper", page_icon="📝", layout="centered")

# --- App Header & Logo ---
col_logo, col_title = st.columns([1, 5])
with col_logo:
    if os.path.exists("logo.png"):
        st.image("logo.png", width=80)
    else:
        st.markdown("<h1>📝</h1>", unsafe_allow_html=True) 
with col_title:
    st.title("PaperBanao")
    
st.markdown("Generate precise, multi-format question papers in seconds using AI.")

# --- API Key Setup (Sidebar) ---
st.sidebar.header("⚙️ Settings")
api_key = st.sidebar.text_input("Enter Google Gemini API Key:", type="password")

if api_key:
    genai.configure(api_key=api_key)
else:
    st.sidebar.warning("Please enter your API key to start generating papers.")

# --- Helper Functions ---
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

def build_question_prompt(mcq_c, mcq_d, fib_c, fib_d, tf_c, tf_d, short_c, short_d, long_c, long_d):
    """Dynamically builds the instruction string based on user counts and difficulties"""
    reqs = []
    if mcq_c > 0:
        reqs.append(f"- {mcq_c} Multiple Choice Questions. Difficulty: {mcq_d}. (Include 4 options and answers hidden at the end).")
    if fib_c > 0:
        reqs.append(f"- {fib_c} Fill in the Blanks Questions. Difficulty: {fib_d}. (Include answers at the end).")
    if tf_c > 0:
        reqs.append(f"- {tf_c} True/False Questions. Difficulty: {tf_d}. (Include answers at the end).")
    if short_c > 0:
        reqs.append(f"- {short_c} Short Answer Questions (2-3 sentences). Difficulty: {short_d}.")
    if long_c > 0:
        reqs.append(f"- {long_c} Long Answer Questions (Detailed explanations). Difficulty: {long_d}.")
    
    if not reqs:
        return "No questions requested."
    
    return "\n".join(reqs) + "\n\n*NOTE: If difficulty is 'Mixed', provide a balanced mix of Easy, Medium, and Hard questions for that section.*"


# ==========================================
# --- CREATE TABS FOR PROFESSIONAL UI ---
# ==========================================
tab1, tab2 = st.tabs(["⚡ Quick Generate (By Syllabus)", "📄 Deep Extract (From PDF Book)"])

diff_options = ["Easy", "Medium", "Hard", "Mixed"]

# ------------------------------------------
# TAB 1: ORIGINAL FEATURE (Syllabus Based)
# ------------------------------------------
with tab1:
    st.markdown("### Generate from Syllabus or Topics")
    
    with st.form("quick_gen_form"):
        col1, col2 = st.columns(2)
        with col1:
            subject_t1 = st.text_input("Subject (e.g., Science)")
        with col2:
            grade_t1 = st.text_input("Class / Grade")
            
        syllabus_t1 = st.text_area("Paste Syllabus or Topics to Cover", placeholder="e.g., Light reflection, Newton's laws...")
        
        st.markdown("#### Question Setup")
        st.markdown("<small>Set count to 0 if you don't want that question type.</small>", unsafe_allow_html=True)
        
        # Clean Grid Layout for Question Types
        c1, c2, c3 = st.columns([2, 1, 2])
        c1.markdown("**Type**"); c2.markdown("**Count**"); c3.markdown("**Difficulty**")
        
        c1.write("Multiple Choice (MCQs)")
        mcq_t1 = c2.number_input("MCQ count", min_value=0, value=5, label_visibility="collapsed", key="m_c1")
        mcq_d1 = c3.selectbox("MCQ Diff", diff_options, label_visibility="collapsed", key="m_d1")

        c1.write("Fill in the Blanks")
        fib_t1 = c2.number_input("FIB count", min_value=0, value=3, label_visibility="collapsed", key="f_c1")
        fib_d1 = c3.selectbox("FIB Diff", diff_options, label_visibility="collapsed", key="f_d1")

        c1.write("True / False")
        tf_t1 = c2.number_input("TF count", min_value=0, value=3, label_visibility="collapsed", key="t_c1")
        tf_d1 = c3.selectbox("TF Diff", diff_options, label_visibility="collapsed", key="t_d1")

        c1.write("Short Answer (2 Marks)")
        short_t1 = c2.number_input("Short count", min_value=0, value=3, label_visibility="collapsed", key="s_c1")
        short_d1 = c3.selectbox("Short Diff", diff_options, label_visibility="collapsed", key="s_d1")

        c1.write("Long Answer (5 Marks)")
        long_t1 = c2.number_input("Long count", min_value=0, value=2, label_visibility="collapsed", key="l_c1")
        long_d1 = c3.selectbox("Long Diff", diff_options, label_visibility="collapsed", key="l_d1")
        
        submit_t1 = st.form_submit_button("🚀 Generate Quick Paper")

    if submit_t1:
        if not api_key:
            st.error("API Key is missing!")
        elif not subject_t1 or not syllabus_t1:
            st.error("Please fill in the Subject and Syllabus.")
        else:
            with st.spinner("Generating Paper..."):
                q_requirements = build_question_prompt(mcq_t1, mcq_d1, fib_t1, fib_d1, tf_t1, tf_d1, short_t1, short_d1, long_t1, long_d1)
                
                prompt1 = f"""
                You are an expert educator. Create a {grade_t1} level {subject_t1} exam.
                Topics to cover strictly: {syllabus_t1}
                
                Generate exactly the following types of questions:
                {q_requirements}
                
                Format it beautifully as a ready-to-print exam paper with clear headings for each section.
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
    
    with st.form("pdf_gen_form"):
        uploaded_pdf = st.file_uploader("Upload Book/Chapter (PDF)", type="pdf")
        
        col4, col5 = st.columns(2)
        with col4:
            start_p = st.number_input("Start Page", min_value=1, value=1)
        with col5:
            end_p = st.number_input("End Page", min_value=1, value=5)
            
        col6, col7 = st.columns(2)
        with col6:
            subject_t2 = st.text_input("Subject", key="sub2")
        with col7:
            topic_t2 = st.text_input("Specific Topic", key="top2")
            
        st.markdown("#### Question Setup")
        
        # Clean Grid Layout for Question Types
        c4, c5, c6 = st.columns([2, 1, 2])
        c4.markdown("**Type**"); c5.markdown("**Count**"); c6.markdown("**Difficulty**")
        
        c4.write("Multiple Choice (MCQs)")
        mcq_t2 = c5.number_input("MCQ count", min_value=0, value=5, label_visibility="collapsed", key="m_c2")
        mcq_d2 = c6.selectbox("MCQ Diff", diff_options, label_visibility="collapsed", key="m_d2")

        c4.write("Fill in the Blanks")
        fib_t2 = c5.number_input("FIB count", min_value=0, value=3, label_visibility="collapsed", key="f_c2")
        fib_d2 = c6.selectbox("FIB Diff", diff_options, label_visibility="collapsed", key="f_d2")

        c4.write("True / False")
        tf_t2 = c5.number_input("TF count", min_value=0, value=3, label_visibility="collapsed", key="t_c2")
        tf_d2 = c6.selectbox("TF Diff", diff_options, label_visibility="collapsed", key="t_d2")

        c4.write("Short Answer")
        short_t2 = c5.number_input("Short count", min_value=0, value=3, label_visibility="collapsed", key="s_c2")
        short_d2 = c6.selectbox("Short Diff", diff_options, label_visibility="collapsed", key="s_d2")

        c4.write("Long Answer")
        long_t2 = c5.number_input("Long count", min_value=0, value=2, label_visibility="collapsed", key="l_c2")
        long_d2 = c6.selectbox("Long Diff", diff_options, label_visibility="collapsed", key="l_d2")

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
                q_requirements_pdf = build_question_prompt(mcq_t2, mcq_d2, fib_t2, fib_d2, tf_t2, tf_d2, short_t2, short_d2, long_t2, long_d2)
                
                prompt2 = f"""
                You are an expert exam creator. Generate an exam ONLY for the topic requested below using the provided text.
                - Subject: {subject_t2}
                - Target Topic: {topic_t2}
                
                CRITICAL INSTRUCTIONS:
                1. Ignore any text NOT related to '{topic_t2}'.
                2. Extract questions STRICTLY from the text provided below.
                3. Generate exactly the following types of questions:
                
                {q_requirements_pdf}
                
                Format the output beautifully as a real exam paper.
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
