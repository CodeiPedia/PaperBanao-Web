import streamlit as st
import google.generativeai as genai
import PyPDF2
import os
import markdown
from datetime import datetime, timedelta, timezone
import re
import uuid
import hashlib
import base64
import bcrypt
import threading
import time
import random
import smtplib
import razorpay
from email.mime.text import MIMEText
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from io import BytesIO

# --- SUPABASE ---
from supabase import create_client, Client

# --- Page Config ---
st.set_page_config(page_title="PaperBanao - AI Question Paper", page_icon="📝", layout="centered")

# ==========================================
# --- 🛑 SECRETS: PULLING KEYS SECURELY ---
# ==========================================
SERVER_API_KEY = st.secrets["GEMINI_API_KEY"]
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

# ==========================================
# --- INITIALIZE SUPABASE CLIENT ---
# ==========================================
@st.cache_resource
def init_supabase():
    try:
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        st.error(f"Database Connection Error: {e}")
        return None

supabase: Client = init_supabase()

# --- INITIALIZE RAZORPAY CLIENT ---
@st.cache_resource
def init_razorpay():
    try:
        return razorpay.Client(auth=(st.secrets["RAZORPAY_KEY_ID"], st.secrets["RAZORPAY_KEY_SECRET"]))
    except Exception as e:
        print(f"[Razorpay Init Error] {e}")
        return None

razorpay_client = init_razorpay()
APP_URL = "https://paperbanao-web-mpv5z8yturtkx25dduvfck.streamlit.app/"
PRO_PRICE_INR = 99
PRO_DURATION_DAYS = 30

# --- CONCURRENCY LOCK ---
# google.generativeai's genai.configure() sets a PROCESS-WIDE global.
# Streamlit runs concurrent users in separate threads of the SAME process,
# so without this lock, two users generating a paper at the same moment
# could end up using each other's API keys. This lock forces the
# configure -> generate sequence to run atomically, one request at a time.
GEMINI_LOCK = threading.Lock()

# --- DB HELPER FUNCTIONS ---
def hash_password(password):
    """bcrypt with a per-password salt (replaces old unsalted SHA-256)."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(password, stored_hash):
    """Verifies against bcrypt hashes, with a fallback for legacy SHA-256
    hashes created before this update. Legacy accounts are transparently
    upgraded to bcrypt on their next successful login."""
    if stored_hash.startswith("$2b$") or stored_hash.startswith("$2a$"):
        try:
            return bcrypt.checkpw(password.encode(), stored_hash.encode())
        except ValueError:
            return False
    # Legacy SHA-256 hash (64 hex chars, no bcrypt prefix)
    legacy_hash = hashlib.sha256(password.encode()).hexdigest()
    return legacy_hash == stored_hash

def create_user(username, password, email):
    username = username.strip()
    email = email.strip().lower()
    try:
        existing = supabase.table("users").select("username").ilike("username", username).execute()
        if existing.data:
            return False, "Username already exists. Choose another."
        existing_email = supabase.table("users").select("username").ilike("email", email).execute()
        if existing_email.data:
            return False, "An account with this email already exists."
        data = {"username": username, "password": hash_password(password), "email": email, "papers_generated": 0, "is_pro": False}
        supabase.table("users").insert(data).execute()
        return True, "Account created successfully! Please Login."
    except Exception as e:
        print(f"[Signup Error] {e}")  # log server-side, don't leak details to the user
        if st.secrets.get("DEBUG_MODE", False):
            return False, f"DEBUG: {e}"
        return False, "Something went wrong creating your account. Please try again."

def authenticate_user(username, password):
    username = username.strip()
    try:
        res = supabase.table("users").select("*").eq("username", username).execute()
    except Exception as e:
        print(f"[Auth Error] {e}")
        st.error("Login is temporarily unavailable. Please try again shortly.")
        return None
    if not res.data:
        return None
    user = res.data[0]
    if not verify_password(password, user["password"]):
        return None
    # Transparently upgrade legacy SHA-256 accounts to bcrypt
    if not (user["password"].startswith("$2b$") or user["password"].startswith("$2a$")):
        try:
            supabase.table("users").update({"password": hash_password(password)}).eq("username", username).execute()
        except Exception:
            pass
    return user

def get_user_data(username):
    try:
        res = supabase.table("users").select("papers_generated, is_pro, email, pro_expires_at").eq("username", username).execute()
        if len(res.data) > 0:
            row = res.data[0]
            expires_at = row.get("pro_expires_at")
            effective_pro = False
            if expires_at:
                try:
                    effective_pro = datetime.fromisoformat(expires_at) > datetime.now(timezone.utc)
                except ValueError:
                    effective_pro = False
            return {
                "papers_generated": row["papers_generated"],
                "is_pro": effective_pro,
                "email": row.get("email"),
                "pro_expires_at": expires_at
            }
    except Exception as e:
        print(f"[get_user_data Error] {e}")
    return {"papers_generated": 0, "is_pro": False, "email": None, "pro_expires_at": None}

def update_paper_count(username):
    try:
        current_count = get_user_data(username)["papers_generated"]
        supabase.table("users").update({"papers_generated": current_count + 1}).eq("username", username).execute()
    except Exception as e:
        print(f"[update_paper_count Error] {e}")

def delete_paper(paper_id, username):
    # Scope the delete to the logged-in user so one account can never
    # delete another account's saved paper by guessing/tampering with an id.
    try:
        supabase.table("papers").delete().eq("id", paper_id).eq("username", username).execute()
    except Exception as e:
        print(f"[delete_paper Error] {e}")
        st.error("Couldn't delete that paper. Please try again.")

# --- PASSWORD RESET (Email OTP) ---
def send_otp_email(to_email, otp):
    try:
        smtp_host = st.secrets.get("SMTP_HOST", "smtp.gmail.com")
        smtp_port = int(st.secrets.get("SMTP_PORT", 465))
        smtp_user = st.secrets["SMTP_USER"]
        smtp_pass = st.secrets["SMTP_PASSWORD"]

        msg = MIMEText(
            f"Your PaperBanao password reset code is: {otp}\n\n"
            f"This code expires in 10 minutes. If you didn't request this, you can ignore this email."
        )
        msg["Subject"] = "PaperBanao - Password Reset Code"
        msg["From"] = smtp_user
        msg["To"] = to_email

        with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, [to_email], msg.as_string())
        return True
    except Exception as e:
        print(f"[Email Send Error] {e}")
        return False

def request_password_reset(identifier):
    """identifier can be a username or an email. Returns (ok, message).
    Deliberately doesn't reveal whether the account exists, to avoid
    leaking which usernames/emails are registered."""
    identifier = identifier.strip()
    generic_msg = "If that account exists, a reset code has been sent to its registered email."
    try:
        res = supabase.table("users").select("username, email") \
            .or_(f"username.eq.{identifier},email.eq.{identifier.lower()}").execute()
    except Exception as e:
        print(f"[Reset Lookup Error] {e}")
        return False, "Something went wrong. Please try again."

    if not res.data:
        return True, generic_msg  # don't reveal non-existence

    user = res.data[0]
    if not user.get("email"):
        # Legacy account created before email was required
        return False, "This account has no email on file. Please contact support to reset it."

    otp = f"{random.randint(0, 999999):06d}"
    otp_hash = hash_password(otp)  # reuse the same bcrypt hashing as passwords
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()

    try:
        supabase.table("users").update({
            "reset_otp": otp_hash,
            "reset_otp_expires": expires_at
        }).eq("username", user["username"]).execute()
    except Exception as e:
        print(f"[Reset Store Error] {e}")
        return False, "Something went wrong. Please try again."

    if send_otp_email(user["email"], otp):
        return True, generic_msg
    else:
        return False, "Couldn't send the reset email right now. Please try again shortly."

def verify_and_reset_password(identifier, otp, new_password):
    identifier = identifier.strip()
    try:
        res = supabase.table("users").select("username, reset_otp, reset_otp_expires") \
            .or_(f"username.eq.{identifier},email.eq.{identifier.lower()}").execute()
    except Exception as e:
        print(f"[Reset Verify Error] {e}")
        return False, "Something went wrong. Please try again."

    if not res.data:
        return False, "Incorrect code or account."

    user = res.data[0]
    if not user.get("reset_otp") or not user.get("reset_otp_expires"):
        return False, "No active reset request found. Please request a new code."

    if datetime.fromisoformat(user["reset_otp_expires"]) < datetime.now(timezone.utc):
        return False, "This code has expired. Please request a new one."

    try:
        if not bcrypt.checkpw(otp.encode(), user["reset_otp"].encode()):
            return False, "Incorrect code."
    except ValueError:
        return False, "Incorrect code."

    try:
        supabase.table("users").update({
            "password": hash_password(new_password),
            "reset_otp": None,
            "reset_otp_expires": None
        }).eq("username", user["username"]).execute()
    except Exception as e:
        print(f"[Reset Update Error] {e}")
        return False, "Something went wrong. Please try again."

    return True, "Password updated! Please login with your new password."

# --- RAZORPAY: PAYMENT LINK + VERIFICATION ---
def create_pro_payment_link(username, email):
    if not razorpay_client:
        return None, "Payment system isn't configured right now."
    try:
        link_data = {
            "amount": PRO_PRICE_INR * 100,  # paise
            "currency": "INR",
            "accept_partial": False,
            "description": f"PaperBanao Pro - {PRO_DURATION_DAYS} Days",
            "customer": {"name": username, "email": email} if email else {"name": username},
            "notify": {"email": bool(email)},
            "reminder_enable": True,
            "notes": {"username": username},
            "callback_url": APP_URL,
            "callback_method": "get"
        }
        link = razorpay_client.payment_link.create(link_data)
        return link["short_url"], None
    except Exception as e:
        print(f"[Payment Link Error] {e}")
        return None, "Couldn't create the payment link. Please try again."

def process_payment_callback(params):
    """Verifies a Razorpay payment-link callback and, if valid and not
    already processed, upgrades the user to Pro for PRO_DURATION_DAYS."""
    required = ["razorpay_payment_link_id", "razorpay_payment_link_reference_id",
                "razorpay_payment_link_status", "razorpay_payment_id", "razorpay_signature"]
    if not all(k in params for k in required):
        return False, None

    try:
        razorpay_client.utility.verify_payment_link_signature(params)
    except razorpay.errors.SignatureVerificationError as e:
        print(f"[Payment Signature Error] {e}")
        return False, "Payment verification failed. If money was deducted, please contact support."

    if params["razorpay_payment_link_status"] != "paid":
        return False, None

    payment_id = params["razorpay_payment_id"]

    # Idempotency: if we've already recorded this payment_id, don't credit again
    # (this can happen if the user refreshes the page after a successful payment)
    try:
        existing = supabase.table("payments").select("payment_id").eq("payment_id", payment_id).execute()
        if existing.data:
            return True, "Payment already processed."
    except Exception as e:
        print(f"[Payment Idempotency Check Error] {e}")
        return False, "Something went wrong verifying your payment. Please contact support."

    try:
        link_details = razorpay_client.payment_link.fetch(params["razorpay_payment_link_id"])
        username = link_details.get("notes", {}).get("username")
    except Exception as e:
        print(f"[Payment Link Fetch Error] {e}")
        return False, "Couldn't confirm payment details. Please contact support."

    if not username:
        return False, "Couldn't identify the account for this payment. Please contact support."

    try:
        # Extend from current expiry if still active, else start from now
        user_res = supabase.table("users").select("pro_expires_at").eq("username", username).execute()
        now = datetime.now(timezone.utc)
        current_expiry = None
        if user_res.data and user_res.data[0].get("pro_expires_at"):
            current_expiry = datetime.fromisoformat(user_res.data[0]["pro_expires_at"])
        start_from = current_expiry if (current_expiry and current_expiry > now) else now
        new_expiry = start_from + timedelta(days=PRO_DURATION_DAYS)

        supabase.table("users").update({
            "is_pro": True,
            "pro_expires_at": new_expiry.isoformat()
        }).eq("username", username).execute()

        supabase.table("payments").insert({
            "payment_id": payment_id,
            "username": username,
            "amount_inr": PRO_PRICE_INR
        }).execute()
    except Exception as e:
        print(f"[Payment Credit Error] {e}")
        return False, "Payment received but activation failed. Please contact support with your payment ID: " + payment_id

    return True, f"Payment successful! Pro is active until {new_expiry.strftime('%d %b %Y')}."

# --- INITIALIZE SESSION STATE ---
if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "username" not in st.session_state: st.session_state.username = ""
if "blocks" not in st.session_state: st.session_state.blocks = [] 
if "file_name" not in st.session_state: st.session_state.file_name = "PaperBanao_Exam"
if "current_subject" not in st.session_state: st.session_state.current_subject = "Unknown Subject"
if "current_class" not in st.session_state: st.session_state.current_class = ""
if "current_marks" not in st.session_state: st.session_state.current_marks = ""
if "login_attempts" not in st.session_state: st.session_state.login_attempts = 0
if "login_locked_until" not in st.session_state: st.session_state.login_locked_until = 0

# ==========================================
# --- 🔐 LOGIN & SIGNUP UI ---
# ==========================================
if not st.session_state.logged_in:
    st.markdown("<h1 style='text-align: center;'>📝 PaperBanao AI (Cloud)</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center;'>Generate precise question papers in seconds.</p>", unsafe_allow_html=True)
    
    if not supabase:
        st.error("⚠️ SYSTEM ADMIN: Please configure 'SUPABASE_URL' and 'SUPABASE_KEY' in the code to enable Login.")
        st.stop()
        
    st.markdown("---")
    t_login, t_signup, t_forgot = st.tabs(["Login", "Sign Up (Free Trial)", "Forgot Password"])
    
    with t_login:
        l_user = st.text_input("Username", key="l_user")
        l_pass = st.text_input("Password", type="password", key="l_pass")

        locked_remaining = st.session_state.login_locked_until - time.time()
        if locked_remaining > 0:
            st.error(f"Too many failed attempts. Try again in {int(locked_remaining)}s.")
        elif st.button("Login", use_container_width=True):
            user = authenticate_user(l_user, l_pass)
            if user:
                st.session_state.logged_in = True
                st.session_state.username = user["username"]
                st.session_state.login_attempts = 0
                st.rerun()
            else:
                st.session_state.login_attempts += 1
                if st.session_state.login_attempts >= 5:
                    st.session_state.login_locked_until = time.time() + 60
                    st.session_state.login_attempts = 0
                    st.error("Too many failed attempts. Locked for 60s.")
                else:
                    st.error("Invalid Username or Password")
                
    with t_signup:
        s_user = st.text_input("New Username", key="s_user")
        s_email = st.text_input("Email", key="s_email", help="Needed for password reset")
        s_pass = st.text_input("New Password", type="password", key="s_pass")
        if st.button("Create Account & Get 5 Free Papers", use_container_width=True):
            if len(s_user.strip()) < 3:
                st.error("Username must be at least 3 characters.")
            elif not re.match(r'^[A-Za-z0-9_.]+$', s_user.strip()):
                st.error("Username can only contain letters, numbers, underscores, and dots.")
            elif not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', s_email.strip()):
                st.error("Please enter a valid email address.")
            elif len(s_pass) < 6:
                st.error("Password must be at least 6 characters.")
            else:
                ok, msg = create_user(s_user, s_pass, s_email)
                if ok: st.success(msg)
                else: st.error(msg)

    with t_forgot:
        if "reset_otp_sent" not in st.session_state: st.session_state.reset_otp_sent = False
        if "reset_identifier" not in st.session_state: st.session_state.reset_identifier = ""
        if "reset_request_locked_until" not in st.session_state: st.session_state.reset_request_locked_until = 0

        if not st.session_state.reset_otp_sent:
            st.write("Enter your username or email — we'll send a 6-digit code to your registered email.")
            f_id = st.text_input("Username or Email", key="f_id")

            req_locked_remaining = st.session_state.reset_request_locked_until - time.time()
            if req_locked_remaining > 0:
                st.info(f"Please wait {int(req_locked_remaining)}s before requesting another code.")
            elif st.button("Send Reset Code", use_container_width=True):
                if f_id.strip() == "":
                    st.error("Please enter your username or email.")
                else:
                    ok, msg = request_password_reset(f_id)
                    st.session_state.reset_request_locked_until = time.time() + 60
                    if ok:
                        st.session_state.reset_otp_sent = True
                        st.session_state.reset_identifier = f_id
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
        else:
            st.info("Code sent (if the account exists). Check your email — it expires in 10 minutes.")
            f_otp = st.text_input("6-digit Code", key="f_otp", max_chars=6)
            f_new_pass = st.text_input("New Password", type="password", key="f_new_pass")
            fc1, fc2 = st.columns(2)
            if fc1.button("Reset Password", use_container_width=True):
                if len(f_new_pass) < 6:
                    st.error("Password must be at least 6 characters.")
                else:
                    ok, msg = verify_and_reset_password(st.session_state.reset_identifier, f_otp, f_new_pass)
                    if ok:
                        st.success(msg)
                        st.session_state.reset_otp_sent = False
                    else:
                        st.error(msg)
            if fc2.button("Start Over", use_container_width=True):
                st.session_state.reset_otp_sent = False
                st.rerun()
    st.stop()

# ==========================================
# --- APP LOGIC (IF LOGGED IN) ---
# ==========================================

# Handle Razorpay payment-link callback (redirected back with query params)
qp = st.query_params
if "razorpay_payment_id" in qp:
    ok, msg = process_payment_callback(dict(qp))
    st.query_params.clear()
    if ok:
        st.success(msg)
    elif msg:
        st.error(msg)

user_data = get_user_data(st.session_state.username)
papers_used = user_data["papers_generated"]
is_pro = user_data["is_pro"]
pro_expires_at = user_data["pro_expires_at"]
user_email = user_data["email"]
FREE_LIMIT = 5

col_logo, col_title, col_logout = st.columns([1, 4, 1])
with col_logo: st.markdown("<h1>📝</h1>", unsafe_allow_html=True) 
with col_title: st.title("PaperBanao")
with col_logout:
    st.write(f"👤 **{st.session_state.username}**")
    if st.button("Logout"):
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.session_state.blocks = []
        st.session_state.blocks_saved = True
        st.session_state.confirm_overwrite = False
        st.rerun()

# ==========================================
# --- SIDEBAR & SETTINGS ---
# ==========================================
st.sidebar.header("💳 Your Account")
if is_pro:
    expiry_str = datetime.fromisoformat(pro_expires_at).strftime("%d %b %Y")
    st.sidebar.success(f"🌟 PRO Member (Unlimited)\n\nActive until {expiry_str}")
    if st.sidebar.button("Renew Pro (₹99 / 30 days)", use_container_width=True):
        with st.spinner("Creating payment link..."):
            link, err = create_pro_payment_link(st.session_state.username, user_email)
        if link:
            st.sidebar.link_button("Click to Pay ₹99", link, use_container_width=True)
        else:
            st.sidebar.error(err)
else:
    papers_left = FREE_LIMIT - papers_used
    st.sidebar.info(f"🪙 Free Credits: {papers_left} / {FREE_LIMIT}")
    st.sidebar.progress(papers_used / FREE_LIMIT if papers_used <= FREE_LIMIT else 1.0)
    if papers_left <= 0:
        st.sidebar.error("⚠️ Free Trial Expired!")
    if st.sidebar.button("⬆️ Upgrade to Pro (₹99 / 30 days)", use_container_width=True):
        with st.spinner("Creating payment link..."):
            link, err = create_pro_payment_link(st.session_state.username, user_email)
        if link:
            st.sidebar.link_button("Click to Pay ₹99", link, use_container_width=True)
        else:
            st.sidebar.error(err)

st.sidebar.markdown("---")
# BYOK Feature
st.sidebar.header("⚙️ Advanced Settings")
st.sidebar.write("Use your own free Gemini API Key when the server limit is reached.")
user_api_key = st.sidebar.text_input("Your Gemini API Key (Optional)", type="password", help="Get your free key from Google AI Studio")

if user_api_key:
    st.sidebar.success("✅ Personal API Key Active!")

st.sidebar.markdown("---")
st.sidebar.header("🏫 Institute Details")
inst_logo = st.sidebar.file_uploader("Upload Logo", type=["png", "jpg", "jpeg"])
inst_name = st.sidebar.text_input("Institute Name", value="My Success Academy")
exam_time = st.sidebar.text_input("Exam Time", value="2 Hours")

st.sidebar.markdown("---")
st.sidebar.header("🏢 Footer Details")
teacher_name = st.sidebar.text_input("Teacher Name", value="Mr. Suraj")
inst_address = st.sidebar.text_input("Institute Address", value="NH-22 Education Lane, City")
inst_contact = st.sidebar.text_input("Contact Number", value="+91 9310038172")

st.sidebar.markdown("---")
st.sidebar.header("📜 Formatting")
board_format = st.sidebar.selectbox("Board Pattern", ["Standard", "BSEB (Bihar Board)", "CBSE", "ICSE"])
paper_language = st.sidebar.selectbox("Paper Language", ["English", "Hindi", "Bilingual"])
include_answer_key = st.sidebar.toggle("Include Answer Key", value=True)
is_two_column = st.sidebar.toggle("📄 Two-Column Format", value=True) 

# ==========================================
# --- API CONFIGURATION LOGIC ---
# ==========================================
active_api_key = user_api_key if user_api_key.strip() != "" else SERVER_API_KEY

@st.cache_data(ttl=3600, show_spinner=False)
def get_working_model_name(api_key):
    """Cached for 1 hour per API key so we don't hit list_models() on every
    single UI interaction (button click, text input, etc all trigger a
    full Streamlit rerun)."""
    with GEMINI_LOCK:
        genai.configure(api_key=api_key)
        valid_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
    flash_models = [m for m in valid_models if '1.5-flash' in m]
    return flash_models[0] if flash_models else valid_models[0]

try:
    working_model_name = get_working_model_name(active_api_key)
except Exception:
    working_model_name = "gemini-1.5-flash"
    if user_api_key:
        st.sidebar.error("❌ Invalid API Key. Please check your entry.")

# --- Helper Functions ---
def extract_text_from_pdf(uploaded_file, start_page, end_page):
    try:
        reader = PyPDF2.PdfReader(uploaded_file)
        start_index = max(0, start_page - 1) 
        end_index = min(len(reader.pages), end_page)
        return "".join([reader.pages[i].extract_text() + "\n" for i in range(start_index, end_index)])
    except Exception: return ""

def build_question_prompt(mcq_c, mcq_d, mcq_m, fib_c, fib_d, fib_m, tf_c, tf_d, tf_m, short_c, short_d, short_m, long_c, long_d, long_m, include_answers, selected_language, subject):
    reqs = []
    if mcq_c > 0: reqs.append(f"- {mcq_c} MCQs (Diff: {mcq_d}). [{mcq_m} Mark each]")
    if fib_c > 0: reqs.append(f"- {fib_c} FIBs (Diff: {fib_d}). [{fib_m} Marks each]")
    if tf_c > 0:  reqs.append(f"- {tf_c} True/False (Diff: {tf_d}). [{tf_m} Marks each]")
    if short_c > 0: reqs.append(f"- {short_c} Short Q (Diff: {short_d}). [{short_m} Marks each]")
    if long_c > 0:  reqs.append(f"- {long_c} Long Q (Diff: {long_d}). [{long_m} Marks each]")
    
    if selected_language == "English":
        lang_instruction = "LANGUAGE RULE: Generate the ENTIRE paper and answers strictly in the English language."
    elif selected_language == "Hindi":
        lang_instruction = "LANGUAGE RULE: Generate the paper in simple Hindi. Avoid tough academic Hindi words. Provide English terms in brackets for technical words. Example: 'अंश [Numerator]'."
    else:
        lang_instruction = "LANGUAGE RULE: Generate the paper in Hinglish (a mix of simple Hindi and English). Provide English terms in brackets for technical words."
    
    # 🌟 FIX: Stricter prompting for Q-numbering and options layout
    base_prompt = "\n".join(reqs) + f"\n\n{lang_instruction}\n\n" + f"""CRITICAL FORMATTING:
1. STRICTLY adhere to the subject: **{subject}**. Do NOT generate general knowledge questions or questions from other subjects.
2. START DIRECTLY WITH QUESTIONS. DO NOT GENERATE ANY INSTITUTE NAME, TIME, MARKS OR HEADER AT THE TOP.
3. Separate every Question and Answer Key with delimiter: `|||` on a new line.
4. MATH: USE UNICODE SYMBOLS ONLY (θ, π, √, ²). NO LaTeX. Write fractions as a/b.
5. NUMBERING: Always start a question with **Q** followed by the number, e.g., **Q1.**, **Q2.**, etc. DO NOT use markdown lists like `1. ` or `* `.
6. MCQs/FIBs OPTIONS: ALWAYS place the options on a NEW LINE below the question. Do NOT put them on the same line as the question.
   Example:
   **Q1.** What is the value of x?
   (A) 1   (B) 2   (C) 3   (D) 4
7. DO NOT use special checkboxes like ☐, ☑, •, ◦. Use [ ] or (A).
    """
    
    if include_answers: return base_prompt + "\nAdd '# Answer Key' at end, also separated by `|||`. Use the requested language in answers too."
    return base_prompt

def regenerate_single_question(old_text, api_key, model_name):
    prompt = f"Generate a NEW question to replace this. Keep the original language style. Use Unicode math symbols (θ, π, √, ²). ONLY output the question text:\n{old_text}"
    with GEMINI_LOCK:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_name)
        return model.generate_content(prompt).text.strip()

def clean_math_for_word(text):
    text = re.sub(r'\\frac\{([^}]+)\}\{([^}]+)\}', r'(\1)/(\2)', text)
    text = re.sub(r'\\\((.*?)\\\)', r'\1', text)
    text = re.sub(r'\\\[(.*?)\\\]', r'\1', text)
    latex_map = {r'\pi': 'π', r'\theta': 'θ', r'\sqrt': '√', r'\times': '×', r'\div': '÷', '$': '', '^2': '²', '^3': '³'}
    for k, v in latex_map.items(): text = text.replace(k, v)
    text = text.replace('☐', '[ ]').replace('☑', '[x]').replace('•', '-').replace('◦', '-')
    text = text.replace('\u200b', '').replace('\u2022', '-').replace('\u25cf', '-').replace('\u25cb', '-')
    text = text.replace('\u25a0', '[ ]').replace('\u25a1', '[ ]')
    return text.strip()

# 🌟 HTML RENDERER 🌟
def create_a4_html(md_content, i_name, i_address, i_contact, t_name, inst_logo=None, is_2_col=False, sub="Subject", grade="Class", total_m="Marks", exam_time="Time", topics=""):
    md_content = clean_math_for_word(md_content)
    
    md_content = re.sub(r"^#.*?\*\*\*", "", md_content, count=1, flags=re.DOTALL).strip()
    md_content = re.sub(r"^\*\*Subject:\*\*.*?\n", "", md_content, flags=re.MULTILINE)
    md_content = re.sub(r"^\*\*Class:\*\*.*?\n", "", md_content, flags=re.MULTILINE)
    md_content = re.sub(r"^\*\*Marks:\*\*.*?\n", "", md_content, flags=re.MULTILINE)
    md_content = re.sub(r"^\*\*Time:\*\*.*?\n", "", md_content, flags=re.MULTILINE)
    
    # Optional: Fix any leftover markdown lists from AI output just in case
    md_content = re.sub(r"^\d+\.\s", "**Q.** ", md_content, flags=re.MULTILINE)

    md_content = md_content.strip()
    
    logo_html_inline = ""
    logo_footer = ""
    if inst_logo:
        inst_logo.seek(0)
        b64 = base64.b64encode(inst_logo.getvalue()).decode()
        logo_html_inline = f"<td style='width: 1%; padding-right: 15px; vertical-align: middle;'><img src='data:{inst_logo.type};base64,{b64}' style='max-height: 55px;'/></td>"
        logo_footer = f"<img src='data:{inst_logo.type};base64,{b64}' style='height: 18px; vertical-align: middle; margin-right: 8px;'/>"
    
    main_heading_text = topics.strip().upper() if topics.strip() != "" else sub.upper()
    
    custom_header = f"""
    <div style='border-bottom: 2px solid black; padding-bottom: 10px; margin-bottom: 10px; width: 100%;'>
        <table style='width: 100%; border-collapse: collapse; border: none; margin-bottom: 10px;'>
            <tr>
                <td style='text-align: center; vertical-align: middle; border: none;'>
                    <table style='margin: 0 auto;'>
                        <tr>
                            {logo_html_inline}
                            <td style='vertical-align: middle;'>
                                <h1 style='margin: 0; font-size: 24px; font-family: "Times New Roman", serif; font-weight: 900; text-transform: uppercase; white-space: nowrap;'>{i_name}</h1>
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
        <table style='width: 100%; font-weight: bold; font-size: 13px; border: none;'>
            <tr>
                <td style='text-align: left; vertical-align: bottom; width: 33%; border: none;'>Class : {grade}<br>Time : {exam_time}</td>
                <td style='text-align: center; vertical-align: middle; width: 34%; border: none;'>
                    <div style='border: 2px solid black; border-radius: 12px; display: inline-block; padding: 4px 25px; font-weight: bold; font-size: 14px; background: white;'>
                        EXAMINATION
                    </div>
                </td>
                <td style='text-align: right; vertical-align: bottom; width: 33%; border: none;'>Sub.: {sub}<br>Marks: {total_m}</td>
            </tr>
        </table>
    </div>
    <div style='border-top: 1px solid black; border-bottom: 3px solid black; padding: 2px 0; margin-bottom: 15px;'>
        <div style='background-color: black; color: white; padding: 5px; text-align: center; font-weight: bold; font-size: 15px; text-transform: uppercase; letter-spacing: 1px;'>
            Multiple Choice Questions & Theory
        </div>
    </div>
    <h2 style='text-align: center; text-decoration: underline; text-transform: uppercase; margin-top: 0; margin-bottom: 15px; font-size: 18px;'>{main_heading_text}</h2>
    """

    ans_split_marker = "|||ANSWER_KEY_SPLIT|||"
    md_content = re.sub(r'(?im)^#+\s*Answer Key.*$', ans_split_marker, md_content)
    
    if ans_split_marker in md_content:
        q_part, a_part = md_content.split(ans_split_marker)
        final_inner_html = f"""
        {custom_header}
        <div class="content-body">{markdown.markdown(q_part.strip())}</div>
        <div style="page-break-before: always; width: 100%;"></div>
        {custom_header}
        <h2 style="text-align: center; text-decoration: underline; margin-bottom: 15px;">ANSWER KEY</h2>
        <div class="content-body">{markdown.markdown(a_part.strip())}</div>
        """
    else:
        final_inner_html = f"""
        {custom_header}
        <div class="content-body">{markdown.markdown(md_content.strip())}</div>
        """
    
    col_style = "column-count: 2; column-gap: 15mm; column-rule: 1px solid #000; font-size: 14px;" if is_2_col else "font-size: 16px;"

    # 🌟 FIX: Added CSS to handle spacing between paragraphs (questions) better
    return f"""<!DOCTYPE html><html><head><style>
    body {{ background: #f0f0f0; font-family: 'Times New Roman', serif; margin: 0; padding: 20px; display: flex; justify-content: center; }} 
    .a4-page {{ background: white; width: 210mm; min-height: 297mm; padding: 20px; box-shadow: 0 0 10px rgba(0,0,0,0.2); box-sizing: border-box; position: relative; overflow: hidden; }} 
    .watermark {{ position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%) rotate(-45deg); font-size: 80px; color: rgba(0, 0, 0, 0.05); z-index: 0; pointer-events: none; white-space: nowrap; font-weight: bold; }}
    table {{ width: 100%; border-collapse: collapse; border: none; position: relative; z-index: 1; }}
    td {{ border: none; padding: 0; }}
    @media print {{ 
        @page {{ size: A4; margin: 0; }} 
        body {{ background: white; padding: 0; margin: 0; display: block; }} 
        .a4-page {{ box-shadow: none; width: 100%; min-height: auto; padding: 10mm; margin: 0; page-break-after: always; }} 
        tfoot {{ display: table-footer-group; }}
    }} 
    h1, h2, h3 {{ text-align: center; column-span: all; }} 
    .content-body {{ {col_style} position: relative; z-index: 1; text-align: justify; }} 
    .content-body p {{ margin-bottom: 8px; margin-top: 4px; }}
    .footer-content {{ text-align: center; margin-top: 20px; padding-top: 10px; border-top: 2px dashed #bbb; font-size: 13px; color: #444; position: relative; z-index: 1; background: white; }}
    </style></head><body><div class="a4-page">
    <div class="watermark">{i_name}</div>
    <table>
        <thead><tr><td></td></tr></thead>
        <tbody><tr><td>{final_inner_html}</td></tr></tbody>
        <tfoot><tr><td>
            <div class="footer-content">
                {logo_footer}<strong>{i_name}</strong> | 📍 {i_address} | 📞 {i_contact} | 👨‍🏫 <strong>{t_name}</strong>
            </div>
        </td></tr></tfoot>
    </table>
    </div></body></html>"""

# 🌟 WORD RENDERER 🌟
def create_word_docx(md_content, i_name, i_address, i_contact, t_name, inst_logo=None, is_2_col=False, sub="Subject", grade="Class", total_m="Marks", exam_time="Time", topics=""):
    doc = Document()
    
    md_content = re.sub(r"^#.*?\*\*\*", "", md_content, count=1, flags=re.DOTALL).strip()
    md_content = re.sub(r"^\*\*Subject:\*\*.*?\n", "", md_content, flags=re.MULTILINE)
    md_content = re.sub(r"^\*\*Class:\*\*.*?\n", "", md_content, flags=re.MULTILINE)
    md_content = re.sub(r"^\*\*Marks:\*\*.*?\n", "", md_content, flags=re.MULTILINE)
    md_content = re.sub(r"^\*\*Time:\*\*.*?\n", "", md_content, flags=re.MULTILINE)
    md_content = re.sub(r"^\d+\.\s", "**Q.** ", md_content, flags=re.MULTILINE)
    md_content = md_content.strip()
        
    md_content = md_content.replace('\r', '')
    
    style = doc.styles['Normal']
    font = style.font
    font.name = 'Arial' 
    font.size = Pt(11)
    
    rFonts = style.element.rPr.rFonts
    if rFonts is not None:
        rFonts.set(qn('w:cs'), 'Mangal') 
        rFonts.set(qn('w:ascii'), 'Arial')
        rFonts.set(qn('w:hAnsi'), 'Arial')
    
    for i in range(3):
        try:
            h_style = doc.styles[f'Heading {i}']
            h_style.font.name = 'Arial'
            if h_style.element.rPr.rFonts is not None:
                h_style.element.rPr.rFonts.set(qn('w:cs'), 'Mangal')
                h_style.element.rPr.rFonts.set(qn('w:ascii'), 'Arial')
                h_style.element.rPr.rFonts.set(qn('w:hAnsi'), 'Arial')
            h_style.font.color.rgb = RGBColor(0, 0, 0)
            if i == 0:
                h_style.font.size = Pt(16)
                h_style.font.bold = True
            elif i == 1:
                h_style.font.size = Pt(12)
                h_style.font.bold = True
            elif i == 2:
                h_style.font.size = Pt(11)
                h_style.font.bold = True
        except KeyError: pass

    if is_2_col:
        for section in doc.sections:
            section.top_margin = section.bottom_margin = section.left_margin = section.right_margin = Inches(0.4)

    def insert_chate_header():
        title_table = doc.add_table(rows=1, cols=1)
        p1 = title_table.cell(0,0).paragraphs[0]
        p1.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        if inst_logo is not None:
            try:
                inst_logo.seek(0)
                r_logo = p1.add_run()
                r_logo.add_picture(inst_logo, height=Inches(0.38))
                p1.add_run("   ") 
            except Exception: pass
            
        r1 = p1.add_run(i_name.upper())
        r1.bold = True
        r1.font.size = Pt(18)
        
        details_table = doc.add_table(rows=1, cols=3)
        details_table.autofit = False
        for cell in details_table.columns[0].cells: cell.width = Inches(2.0)
        for cell in details_table.columns[1].cells: cell.width = Inches(3.0)
        for cell in details_table.columns[2].cells: cell.width = Inches(2.0)

        p3 = details_table.cell(0,0).paragraphs[0]
        p3.alignment = WD_ALIGN_PARAGRAPH.LEFT
        r3 = p3.add_run(f"Class : {grade}\nTime : {exam_time}")
        r3.bold = True
        r3.font.size = Pt(10)

        p4 = details_table.cell(0,1).paragraphs[0]
        p4.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r4 = p4.add_run("\n[ EXAMINATION ]")
        r4.bold = True
        r4.font.size = Pt(12)

        p2 = details_table.cell(0,2).paragraphs[0]
        p2.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        r2 = p2.add_run(f"Sub.: {sub}\nMarks: {total_m}")
        r2.bold = True
        r2.font.size = Pt(10)
        
        doc.add_paragraph("__________________________________________________________________________").alignment = WD_ALIGN_PARAGRAPH.CENTER
        pt = doc.add_paragraph("MULTIPLE CHOICE QUESTIONS & THEORY")
        pt.alignment = WD_ALIGN_PARAGRAPH.CENTER
        pt.runs[0].bold = True
        
        main_heading_text = topics.strip().upper() if topics.strip() != "" else sub.upper()
        ptopics = doc.add_paragraph(main_heading_text)
        ptopics.alignment = WD_ALIGN_PARAGRAPH.CENTER
        ptopics.runs[0].underline = True
        ptopics.runs[0].font.size = Pt(14)
        ptopics.runs[0].bold = True
        doc.add_paragraph() 

    insert_chate_header()

    if is_2_col:
        new_section = doc.add_section(0) 
        sectPr = new_section._sectPr
        cols = sectPr.xpath('./w:cols')[0]
        cols.set(qn('w:num'), '2')
        cols.set(qn('w:space'), '720') 

    for line in md_content.split('\n'):
        line_clean = line.strip()
        if not line_clean: continue
        line_clean = clean_math_for_word(line_clean)
        
        if "Answer Key" in line_clean or "ANSWER KEY" in line_clean:
            doc.add_page_break() 
            insert_chate_header() 
            doc.add_heading("Answer Key", level=1)
            continue
            
        if line_clean.startswith('# '): 
            doc.add_heading(line_clean.replace('# ', ''), level=1)
        elif line_clean.startswith('## '): 
            doc.add_heading(line_clean.replace('## ', ''), level=2)
        else:
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY 
            parts = re.split(r'\*\*(.*?)\*\*', line_clean)
            for i, part in enumerate(parts):
                run = p.add_run(part)
                if i % 2 == 1: run.bold = True
                
    if doc.sections:
        footer = doc.sections[0].footer
        footer_para = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
        footer_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        if inst_logo is not None:
            try:
                inst_logo.seek(0)
                run_logo = footer_para.add_run()
                run_logo.add_picture(inst_logo, height=Inches(0.18))
                footer_para.add_run("  ") 
            except Exception: pass
            
        run_name = footer_para.add_run(f"{i_name}  |  ")
        run_name.font.size = Pt(10)
        run_name.font.bold = True
        run_name.font.color.rgb = RGBColor(100, 100, 100)
        
        run_rest = footer_para.add_run(f"📍 {i_address}  |  📞 {i_contact}  |  👨‍🏫 {t_name}")
        run_rest.font.size = Pt(10)
        run_rest.font.color.rgb = RGBColor(100, 100, 100)
            
    bio = BytesIO()
    doc.save(bio)
    return bio.getvalue()

# ==========================================
# --- MAIN LAYOUT ---
# ==========================================
tab_create, tab_history = st.tabs(["🏠 Create Paper", "🗂️ Cloud History"])

with tab_create:
    if not is_pro and papers_used >= FREE_LIMIT:
        st.error("Free Trial Expired! Please Upgrade.")
        st.stop()
        
    st.markdown("### 1. Source")
    source = st.radio("Method:", ["⚡ Quick", "📄 PDF Extract"], horizontal=True, label_visibility="collapsed")

    sub, grade, syl, up_pdf = "", "", "", None
    pdf_text = ""

    if source == "⚡ Quick":
        c1, c2 = st.columns(2)
        sub = c1.text_input("Subject")
        grade = c2.text_input("Class")
        syl = st.text_area("Topics")
    else:
        c1, c2 = st.columns(2)
        sub = c1.text_input("Subject (PDF)")
        grade = c2.text_input("Class (PDF)")
        syl = st.text_area("Specific Topics (Optional)")
        
        up_pdf = st.file_uploader("Upload PDF Book/Notes", type="pdf")
        
        c3, c4 = st.columns(2)
        start_p = c3.number_input("Start Page", min_value=1, value=1)
        end_p = c4.number_input("End Page", min_value=1, value=5)
        
        if up_pdf is not None:
            pdf_text = extract_text_from_pdf(up_pdf, start_p, end_p)
            st.success(f"Extracted {len(pdf_text)} characters from pages {start_p} to {end_p}.")

    st.markdown("---")
    st.markdown("### 2. Counts & Marks")
    h1, h2, h3, h4 = st.columns([3, 2, 2, 3])
    h1.write("**Type**"); h2.write("**Count**"); h3.write("**Marks**"); h4.write("**Diff**")

    # MCQ Row
    c1, c2, c3, c4 = st.columns([3, 2, 2, 3])
    c1.write("MCQs")
    mcq_c = c2.number_input("mcq_c", 0, 50, 5, label_visibility="collapsed", key="m_c")
    mcq_m = c3.number_input("mcq_m", 1, 10, 1, label_visibility="collapsed", key="m_m")
    mcq_d = c4.selectbox("mcq_d", ["Easy", "Medium", "Hard"], label_visibility="collapsed", key="m_d")

    # FIB Row
    c1, c2, c3, c4 = st.columns([3, 2, 2, 3])
    c1.write("Fill in the Blanks")
    fib_c = c2.number_input("fib_c", 0, 20, 3, label_visibility="collapsed", key="f_c")
    fib_m = c3.number_input("fib_m", 1, 10, 1, label_visibility="collapsed", key="f_m")
    fib_d = c4.selectbox("fib_d", ["Easy", "Medium", "Hard"], label_visibility="collapsed", key="f_d")

    # True/False Row
    c1, c2, c3, c4 = st.columns([3, 2, 2, 3])
    c1.write("True / False")
    tf_c = c2.number_input("tf_c", 0, 20, 3, label_visibility="collapsed", key="t_c")
    tf_m = c3.number_input("tf_m", 1, 10, 1, label_visibility="collapsed", key="t_m")
    tf_d = c4.selectbox("tf_d", ["Easy", "Medium", "Hard"], label_visibility="collapsed", key="t_d")

    # Short Row
    c1, c2, c3, c4 = st.columns([3, 2, 2, 3])
    c1.write("Short Answer")
    short_c = c2.number_input("sh_c", 0, 20, 3, label_visibility="collapsed", key="s_c")
    short_m = c3.number_input("sh_m", 1, 10, 2, label_visibility="collapsed", key="s_m")
    short_d = c4.selectbox("sh_d", ["Easy", "Medium", "Hard"], label_visibility="collapsed", key="s_d", index=1)

    # Long Row
    c1, c2, c3, c4 = st.columns([3, 2, 2, 3])
    c1.write("Long Answer")
    long_c = c2.number_input("l_c", 0, 20, 2, label_visibility="collapsed", key="l_c")
    long_m = c3.number_input("l_m", 1, 20, 5, label_visibility="collapsed", key="l_m")
    long_d = c4.selectbox("l_d", ["Easy", "Medium", "Hard"], label_visibility="collapsed", key="l_d", index=2)

    total_q = mcq_c + fib_c + tf_c + short_c + long_c
    total_m = (mcq_c * mcq_m) + (fib_c * fib_m) + (tf_c * tf_m) + (short_c * short_m) + (long_c * long_m)
    
    st.markdown("---")
    st.info(f"📊 Total Questions: {total_q} | 🏆 Maximum Marks: {total_m}")

    if "blocks_saved" not in st.session_state: st.session_state.blocks_saved = True
    if "confirm_overwrite" not in st.session_state: st.session_state.confirm_overwrite = False

    generate_clicked = st.button("🚀 Generate Paper", use_container_width=True)

    if generate_clicked and st.session_state.blocks and not st.session_state.blocks_saved and not st.session_state.confirm_overwrite:
        st.warning("You have an unsaved paper above (not saved to Cloud History yet). Generating a new one will replace it.")
        if st.button("Generate anyway (discard current paper)", use_container_width=True):
            st.session_state.confirm_overwrite = True
            st.rerun()
        generate_clicked = False

    if generate_clicked and (not st.session_state.blocks or st.session_state.blocks_saved or st.session_state.confirm_overwrite):
        st.session_state.confirm_overwrite = False
        if not sub.strip() or not grade.strip():
            st.error("Please fill in Subject and Class before generating.")
        elif total_q == 0:
            st.error("Please add at least one question (set a count > 0 for some question type).")
        else:
            st.session_state.current_subject = sub
            st.session_state.current_class = grade
            st.session_state.current_marks = str(total_m)

            q_reqs = build_question_prompt(
                mcq_c, mcq_d, mcq_m, fib_c, fib_d, fib_m, tf_c, tf_d, tf_m, short_c, short_d, short_m, long_c, long_d, long_m, include_answer_key, paper_language, sub
            )

            if source == "📄 PDF Extract" and pdf_text != "":
                prompt = f"Subject: {sub}\nClass: {grade}\nTopics: {syl}\n\n{q_reqs}\n\nIMPORTANT: Start directly with the questions. DO NOT generate any Title, Institute Name, Time, or Marks at the top.\n\nCREATE QUESTIONS STRICTLY FROM THE FOLLOWING TEXT EXTRACTED FROM A BOOK:\n\n{pdf_text}"
            else:
                prompt = f"Subject: {sub}\nClass: {grade}\nTopics: {syl}\n\n{q_reqs}\n\nIMPORTANT: Start directly with the questions. DO NOT generate any Title, Institute Name, Time, or Marks at the top."

            with st.spinner("Generating Paper..."):
                try:
                    # Locked so another user's concurrent request can't run
                    # with this session's API key (or vice versa) — see
                    # GEMINI_LOCK definition for why this matters.
                    with GEMINI_LOCK:
                        genai.configure(api_key=active_api_key)
                        model = genai.GenerativeModel(working_model_name)
                        resp = model.generate_content(prompt)
                    blocks = resp.text.split("|||")
                    st.session_state.blocks = [{'id': str(uuid.uuid4()), 'text': b.strip()} for b in blocks if b.strip()]
                    st.session_state.blocks_saved = False
                    st.session_state.file_name = f"{sub}_Paper"
                    update_paper_count(st.session_state.username)
                    st.rerun()
                except Exception as e:
                    error_msg = str(e).lower()
                    print(f"[Generation Error] {e}")  # full detail server-side only
                    if "429" in error_msg or "quota" in error_msg:
                        st.error("🚨 The daily generation limit has been reached! Try again later or add your own API key in Advanced Settings.")
                    else:
                        st.error("Something went wrong generating the paper. Please try again.")

    if st.session_state.blocks:
        st.markdown("---")
        with st.expander("🛠️ Edit Questions", expanded=False):
            for i, b in enumerate(st.session_state.blocks):
                edit_col, regen_col = st.columns([5, 1])
                new_text = edit_col.text_area(f"Question {i+1}", b['text'], height=100, key=f"block_text_{b['id']}")
                if new_text != st.session_state.blocks[i]['text']:
                    st.session_state.blocks[i]['text'] = new_text
                    st.session_state.blocks_saved = False
                if regen_col.button("🔄 Regenerate", key=f"regen_{b['id']}", help="Ask AI to write a fresh version of this question"):
                    with st.spinner("Regenerating..."):
                        try:
                            st.session_state.blocks[i]['text'] = regenerate_single_question(b['text'], active_api_key, working_model_name)
                            st.session_state.blocks_saved = False
                            st.rerun()
                        except Exception as e:
                            print(f"[Regenerate Error] {e}")
                            st.error("Couldn't regenerate this question. Please try again.")
        
        paper_md = "\n\n".join([b['text'] for b in st.session_state.blocks])
        
        f_html = create_a4_html(paper_md, inst_name, inst_address, inst_contact, teacher_name, inst_logo, is_two_column, st.session_state.current_subject, st.session_state.current_class, st.session_state.current_marks, exam_time, syl)
        f_word = create_word_docx(paper_md, inst_name, inst_address, inst_contact, teacher_name, inst_logo, is_two_column, st.session_state.current_subject, st.session_state.current_class, st.session_state.current_marks, exam_time, syl)
        
        c1, c2, c3 = st.columns(3)
        c1.download_button("🖨️ HTML", f_html, f"{st.session_state.current_subject}.html", "text/html")
        c2.download_button("📄 Word", f_word, f"{st.session_state.current_subject}.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        if c3.button("☁️ Save History"):
            data = {"username": st.session_state.username, "date": datetime.now().strftime("%Y-%m-%d"), "subject": st.session_state.current_subject, "board": board_format, "content": paper_md}
            try:
                supabase.table("papers").insert(data).execute()
                st.session_state.blocks_saved = True
                st.success("Saved!")
            except Exception as e:
                print(f"[Save History Error] {e}")
                st.error("Couldn't save to Cloud History. Please try again.")

with tab_history:
    st.markdown("### Cloud History")
    with st.spinner("Loading your saved papers..."):
        try:
            res = supabase.table("papers").select("*").eq("username", st.session_state.username).order("id", desc=True).execute()
            history_error = None
        except Exception as e:
            print(f"[History Load Error] {e}")
            res = None
            history_error = "Couldn't load your history right now. Please refresh."

    if history_error:
        st.error(history_error)
    elif res.data:
        st.caption(f"{len(res.data)} saved paper(s)")
        for p in res.data:
            with st.expander(f"📄 {p['subject']} ({p['date']})"):
                h_html = create_a4_html(p['content'], inst_name, inst_address, inst_contact, teacher_name, inst_logo, is_two_column, p['subject'], "N/A", "N/A", exam_time, "")
                h_word = create_word_docx(p['content'], inst_name, inst_address, inst_contact, teacher_name, inst_logo, is_two_column, p['subject'], "N/A", "N/A", exam_time, "")

                dl1, dl2, dl3 = st.columns(3)
                dl1.download_button("🖨️ HTML", h_html, f"History_{p['id']}.html", "text/html", key=f"h_{p['id']}")
                dl2.download_button("📄 Word", h_word, f"History_{p['id']}.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", key=f"w_{p['id']}")

                confirm_key = f"confirm_del_{p['id']}"
                if confirm_key not in st.session_state: st.session_state[confirm_key] = False

                if not st.session_state[confirm_key]:
                    if dl3.button("🗑️ Delete", key=f"d_{p['id']}"):
                        st.session_state[confirm_key] = True
                        st.rerun()
                else:
                    st.warning("Delete this paper permanently?")
                    yc, nc = st.columns(2)
                    if yc.button("Yes, delete", key=f"yd_{p['id']}"):
                        delete_paper(p['id'], st.session_state.username)
                        st.session_state[confirm_key] = False
                        st.rerun()
                    if nc.button("Cancel", key=f"nd_{p['id']}"):
                        st.session_state[confirm_key] = False
                        st.rerun()
    else:
        st.info("No saved papers yet — generate one and click '☁️ Save History' to keep it here.")
