import streamlit as st
import google.generativeai as genai
import PyPDF2
import os

# --- Page Config ---
st.set_page_config(page_title="PaperBanao - AI Question Paper", layout="centered")

# --- App Header ---
st.title("📝 PaperBanao")
st.markdown("Generate precise question papers directly from your textbook PDFs.")

# --- API Key Setup (Sidebar) ---
st.sidebar.header("Settings")
api_key = st.sidebar.text_input("Enter Google Gemini API Key:", type="password")

if api_key:
    genai.configure(api_key=api_key)

# --- PDF Text Extraction Function ---
def extract_text_from_pdf(uploaded_file, start_page, end_page):
    try:
        reader = PyPDF2.PdfReader(uploaded_file)
        total_pages = len(reader.pages)
        
        # Ensure user doesn't enter page numbers outside the book
        start_index = max(0, start_page - 1) 
        end_index = min(total_pages, end_page)
        
        extracted_text = ""
        for i in range(start_index, end_index):
            extracted_text += reader.pages[i].extract_text() + "\n"
            
        return extracted_text
    except Exception as e:
        return f"Error reading PDF: {e}"

# --- User Inputs ---
with st.form("paper_form"):
    st.subheader("1. Upload & Select Pages")
    uploaded_pdf = st.file_uploader("Upload Book/Chapter (PDF)", type="pdf")
    
    col1, col2 = st.columns(2)
    with col1:
        start_p = st.number_input("Start Page (e.g., 45)", min_value=1, value=1)
    with col2:
        end_p = st.number_input("End Page (e.g., 55)", min_value=1, value=10)
        
    st.subheader("2. Exam Details")
    subject_name = st.text_input("Subject (e.g., Basic Science & Engineering)")
    topic_name = st.text_input("Specific Topic (e.g., Basic Electricity)")
    
    col3, col4, col5 = st.columns(3)
    with col3:
        mcq_count = st.number_input("Number of MCQs", min_value=0, value=5)
    with col4:
        short_count = st.number_input("Short Qs (2 Marks)", min_value=0, value=3)
    with col5:
        long_count = st.number_input("Long Qs (5 Marks)", min_value=0, value=2)

    submit_button = st.form_submit_button("🚀 Generate Paper")

# --- AI Generation Logic ---
if submit_button:
    if not api_key:
        st.error("Please enter your Gemini API Key in the sidebar first!")
    elif not uploaded_pdf:
        st.error("Please upload a PDF document.")
    elif not subject_name or not topic_name:
        st.error("Please fill in the Subject and Topic.")
    else:
        with st.spinner("Reading PDF and Generating Questions... Please wait."):
            
            # 1. Extract only the specific pages
            document_text = extract_text_from_pdf(uploaded_pdf, start_p, end_p)
            
            # 2. The Strict Prompt (Fixes the Needle in Haystack problem)
            prompt = f"""
            You are an expert exam creator. I am providing you with extracted text from specific pages of a textbook.
            
            Your STRICT task is to generate an exam paper ONLY for the topic requested below.
            - Subject: {subject_name}
            - Target Topic: {topic_name}
            
            CRITICAL INSTRUCTIONS:
            1. You MUST ignore any text that is NOT related to '{topic_name}'. 
            2. Extract questions STRICTLY from the text provided below. Do not use outside knowledge.
            3. Generate exactly {mcq_count} Multiple Choice Questions (with 4 options and the correct answer hidden at the end).
            4. Generate exactly {short_count} Short Answer Questions.
            5. Generate exactly {long_count} Long Answer Questions.
            6. Format the output professionally like a real exam paper using clear headings.

            Here is the textbook text:
            ---
            {document_text}
            ---
            """
            
            # 3. Call Gemini API
            try:
                # Using gemini-1.5-flash as it is fast and excellent for document processing
                model = genai.GenerativeModel('gemini-1.5-flash')
                response = model.generate_content(prompt)
                
                # 4. Display Results
                st.success("Paper Generated Successfully!")
                st.markdown("---")
                st.markdown(response.text)
                st.markdown("---")
                
                # 5. Download Button
                st.download_button(
                    label="📥 Download Paper as Text",
                    data=response.text,
                    file_name=f"{topic_name}_Paper.txt",
                    mime="text/plain"
                )
                
            except Exception as e:
                st.error(f"An error occurred with the AI: {e}")
