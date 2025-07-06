import streamlit as st
import pytesseract
from PIL import Image
from deep_translator import GoogleTranslator
from gtts import gTTS
import io
import re
import pandas as pd

# Firebase SDK
import firebase_admin
from firebase_admin import credentials, db

from PyPDF2 import PdfReader
from pptx import Presentation

# ─── Streamlit setup ────────────────────────────────────────────────────────
st.set_page_config(page_title="📘 Word & Sentence Translator", layout="centered")
st.title("📘 โปรแกรมแปลศัพท์ + ประโยค + เสียงอ่าน")

# ─── Normalize helper ───────────────────────────────────────────────────────
def normalize(word: str) -> str:
    return re.sub(r"[^A-Za-z0-9\-]", "", word).strip().lower()

# ─── Firebase init ─────────────────────────────────────────────────────────
@st.cache_resource
def init_firebase_ref():
    fb = st.secrets["FIREBASE"]

    # สร้าง Credential จาก dict ที่ได้จาก secrets.toml
    cred = credentials.Certificate({
        "type":                    fb["type"],
        "project_id":              fb["project_id"],
        "private_key_id":          fb["private_key_id"],
        "private_key":             fb["private_key"],
        "client_email":            fb["client_email"],
        "client_id":               fb["client_id"],
        "auth_uri":                fb["auth_uri"],
        "token_uri":               fb["token_uri"],
        "auth_provider_x509_cert_url": fb["auth_provider_x509_cert_url"],
        "client_x509_cert_url":    fb["client_x509_cert_url"],
    })

    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred, {
            "databaseURL": fb["database_url"]
        })

    return db.reference("vocabulary")

# ─── Save to Firebase ───────────────────────────────────────────────────────
def save_to_firebase(pairs: list[tuple[str,str]]):
    ref = init_firebase_ref()
    existing = ref.get() or {}
    seen = { normalize(item.get("english","")) for item in existing.values() }

    added = 0
    for w, th in pairs:
        key = normalize(w)
        if key and key not in seen:
            ref.push({"english": w, "thai": th})
            seen.add(key)
            added += 1

    if added:
        st.success(f"✅ เพิ่มคำใหม่ {added} คำลง Firebase")
    else:
        st.info("📌 ไม่มีคำใหม่ลง Firebase เพราะซ้ำทั้งหมด")

# ─── File upload & Extract ─────────────────────────────────────────────────
uploaded_file = st.file_uploader("📤 อัปโหลดไฟล์ (.jpg .png .pdf .pptx)", 
                                 type=["jpg","jpeg","png","pdf","pptx"])
text = ""

if uploaded_file:
    mime = uploaded_file.type
    if mime.startswith("image/"):
        img = Image.open(uploaded_file)
        st.image(img, use_container_width=True)
        text = pytesseract.image_to_string(img.convert("L"), lang="eng")

    elif mime == "application/pdf":
        pdf = PdfReader(uploaded_file)
        n = len(pdf.pages)
        st.write(f"📄 พบทั้งหมด {n} หน้า")
        mode = st.radio("โหมด PDF", ["หน้าเดียว","ช่วงหน้า","ทุกหน้า"])

        if mode == "หน้าเดียว":
            p = st.selectbox("เลือกหน้า", list(range(1,n+1))) - 1
            text = pdf.pages[p].extract_text()
        elif mode == "ช่วงหน้า":
            s = st.number_input("หน้าเริ่ม", 1, n, 1)
            e = st.number_input("หน้าสิ้นสุด", s, n, s)
            text = "\n".join(pdf.pages[i-1].extract_text() for i in range(s,e+1))
        else:
            text = "\n".join(p.extract_text() for p in pdf.pages)

    else:  # pptx
        prs = Presentation(uploaded_file)
        slides = [
            "\n".join(shp.text for shp in slide.shapes if hasattr(shp,"text"))
            for slide in prs.slides
        ]
        m = len(slides)
        st.write(f"📊 พบทั้งหมด {m} สไลด์")
        mode = st.radio("โหมด PPTX", ["สไลด์เดียว","ช่วงสไลด์","ทุกสไลด์"])

        if mode == "สไลด์เดียว":
            i = st.selectbox("เลือกสไลด์", list(range(1,m+1))) - 1
            text = slides[i]
        elif mode == "ช่วงสไลด์":
            s = st.number_input("สไลด์เริ่ม", 1, m, 1)
            e = st.number_input("สไลด์สุดท้าย", s, m, s)
            text = "\n\n".join(slides[j-1] for j in range(s,e+1))
        else:
            text = "\n\n".join(slides)

# ─── Show & edit extracted text ─────────────────────────────────────────────
if text:
    editable = st.text_area("📋 ข้อความ (แก้ไขได้)", text, height=200)

    if st.button("🔊 อ่านต้นฉบับ"):
        buf = io.BytesIO()
        gTTS(editable, lang="en").write_to_fp(buf); buf.seek(0)
        st.audio(buf, format="audio/mp3")

    if st.button("🧠 แปลคำศัพท์"):
        words = re.findall(r"[A-Za-z0-9\-]+", editable)
        df = pd.DataFrame([{
            "english": w,
            "thai": GoogleTranslator(source="en", target="th").translate(w)
        } for w in words])
        st.session_state.vocab = df

# ─── Edit vocab & save ──────────────────────────────────────────────────────
if "vocab" in st.session_state:
    st.info("✏️ แก้ไข/ลบ คำก่อนบันทึก")
    edited = st.data_editor(
        st.session_state.vocab,
        use_container_width=True,
        hide_index=True
    )

    if st.button("💾 บันทึกลง Firebase"):
        pairs = list(zip(edited.english, edited.thai))
        save_to_firebase(pairs)
        del st.session_state.vocab

# ─── Translate whole sentence ────────────────────────────────────────────────
if text:
    st.subheader("📝 แปลเป็นประโยคเต็ม")
    full = GoogleTranslator(source="en", target="th").translate(editable)
    st.success(full)
    if st.button("🔊 อ่านคำแปลไทย"):
        buf = io.BytesIO()
        gTTS(full, lang="th").write_to_fp(buf); buf.seek(0)
        st.audio(buf, format="audio/mp3")