import os, json, re, io
import streamlit as st
import pytesseract
from PIL import Image
from deep_translator import GoogleTranslator
from gtts import gTTS
import pandas as pd
import firebase_admin
from firebase_admin import credentials, db
from PyPDF2 import PdfReader
from pptx import Presentation

# ─── Streamlit setup ─────────────────────────────────────────
st.set_page_config(page_title="📘 Word & Sentence Translator", layout="centered")
st.title("📘 โปรแกรมแปลศัพท์ + ประโยค + เสียงอ่าน")

# ─── Normalize ────────────────────────────────────────────────
def normalize(word):
    return re.sub(r"[^a-zA-Z0-9\-]", "", word).strip().lower()

# ─── Firebase init ────────────────────────────────────────────
@st.cache_resource(show_spinner=False)
def init_firebase():
    # โหลด config จาก st.secrets
    if "FIREBASE" not in st.secrets:
        st.error("❌ ไม่พบคอนฟิก Firebase ใน secrets.toml")
        st.stop()

    fb_conf = st.secrets["FIREBASE"]
    cred = credentials.Certificate(fb_conf)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(
            cred,
            {"databaseURL": f"https://{fb_conf['project_id']}-default-rtdb.asia-southeast1.firebasedatabase.app"}
        )

# ─── Save to Firebase ─────────────────────────────────────────
def save_to_firebase(data):
    init_firebase()
    ref = db.reference("vocabulary")
    existing = ref.get() or {}
    seen = { normalize(item.get("english","")) for item in existing.values() }

    new_count = 0
    for eng, th in data:
        key = normalize(eng)
        if key and key not in seen:
            ref.push({"english": eng, "thai": th})
            seen.add(key)
            new_count += 1

    if new_count:
        st.success(f"✅ เพิ่มคำศัพท์ใหม่ {new_count} คำ ลง Firebase")
    else:
        st.info("📌 ไม่มีคำใหม่ เพราะซ้ำหมด")

# ─── File upload & OCR/Extract ───────────────────────────────
uploaded = st.file_uploader("📤 อัปโหลดไฟล์ (.jpg .png .pdf .pptx)", type=["jpg","jpeg","png","pdf","pptx"])
text = ""

if uploaded:
    ctype = uploaded.type
    # IMAGE
    if ctype.startswith("image/"):
        img = Image.open(uploaded)
        st.image(img, use_container_width=True)
        text = pytesseract.image_to_string(img.convert("L"), lang="eng")

    # PDF
    elif ctype == "application/pdf":
        pdf = PdfReader(uploaded)
        pages = len(pdf.pages)
        st.write(f"📄 พบ {pages} หน้า")
        mode = st.radio("โหมด PDF", ["หน้าเดียว","ช่วงหน้า","ทุกหน้า"])
        if mode=="หน้าเดียว":
            p = st.selectbox("เลือกหน้า", list(range(1, pages+1))) - 1
            text = pdf.pages[p].extract_text() or ""
        elif mode=="ช่วงหน้า":
            s = st.number_input("หน้าเริ่ม", 1, pages, 1)
            e = st.number_input("หน้าสิ้นสุด", s, pages, s)
            text = "\n\n".join(pdf.pages[i-1].extract_text() or "" for i in range(int(s), int(e)+1))
        else:
            text = "\n\n".join(p.extract_text() or "" for p in pdf.pages)

    # PPTX
    else:
        prs = Presentation(uploaded)
        slides = [
            "\n".join(shp.text for shp in slide.shapes if hasattr(shp, "text"))
            for slide in prs.slides
        ]
        total = len(slides)
        st.write(f"📊 พบ {total} สไลด์")
        mode = st.radio("โหมด PPTX", ["สไลด์เดียว","ช่วงสไลด์","ทุกสไลด์"])
        if mode=="สไลด์เดียว":
            i = st.selectbox("เลือกสไลด์", list(range(1, total+1))) - 1
            text = slides[i]
        elif mode=="ช่วงสไลด์":
            s = st.number_input("สไลด์เริ่ม", 1, total, 1)
            e = st.number_input("สไลด์สุดท้าย", s, total, s)
            text = "\n\n".join(slides[j-1] for j in range(int(s), int(e)+1))
        else:
            text = "\n\n".join(slides)

# ─── Text & Translate UI ───────────────────────────────────────
if text:
    editable = st.text_area("📋 ข้อความ OCR/Extract (แก้ไขได้)", text, height=200)
    if st.button("🔊 อ่านต้นฉบับ"):
        buf = io.BytesIO()
        gTTS(editable, lang="en").write_to_fp(buf)
        buf.seek(0)
        st.audio(buf)

    if st.button("🧠 แปลคำศัพท์"):
        words = []
        for line in editable.splitlines():
            for w in line.split():
                w2 = re.sub(r"[^a-zA-Z0-9\-]","",w)
                if w2: words.append(w2)

        df = pd.DataFrame([{
            "english": w,
            "thai": GoogleTranslator(source="en", target="th").translate(w)
        } for w in words])
        st.session_state["vocab_df"] = df

# ─── แก้ไข / ลบ ก่อนบันทึก ───────────────────────────────────────
if "vocab_df" in st.session_state:
    st.info("✏️ แก้ไข/ลบ คำก่อนบันทึก")
    edited = st.data_editor(
        st.session_state["vocab_df"],
        use_container_width=True,
        num_rows="dynamic",
        hide_index=True
    )
    if st.button("💾 บันทึกลง Firebase"):
        save_to_firebase(list(zip(edited.english, edited.thai)))
        del st.session_state["vocab_df"]

# ─── แปลเป็นประโยคเต็ม ───────────────────────────────────────
if text:
    st.subheader("📝 แปลเป็นประโยคเต็ม")
    full = GoogleTranslator(source="en", target="th").translate(editable)
    st.success(full)
    if st.button("🔊 อ่านคำแปลไทย"):
        buf = io.BytesIO()
        gTTS(full, lang="th").write_to_fp(buf)
        buf.seek(0)
        st.audio(buf)