import re
import io
import json
import os

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

# ─── Streamlit UI ──────────────────────────────────────────────────────────
st.set_page_config(page_title="📘 Word & Sentence Translator", layout="centered")
st.title("📘 โปรแกรมแปลศัพท์ + ประโยค + เสียงอ่าน")

# ─── Normalize ──────────────────────────────────────────────────────────────
def normalize(word: str) -> str:
    return re.sub(r"[^a-zA-Z0-9\-]", "", word).strip().lower()

# ─── Firebase initializer ──────────────────────────────────────────────────
@st.cache_resource
def init_firebase_ref():
    """
    อ่าน credential จาก
      1) st.secrets["FIREBASE"]["service_account"] (JSON string)
      2) หรือ st.secrets["FIREBASE"] (dict)
      3) หรือ fallback ไปอ่านไฟล์ serviceAccountKey.json ในโปรเจกต์
    แล้วคืนค่า `db.reference("vocabulary")`
    """
    # 1) ถ้ามี Secret บน Cloud
    if "FIREBASE" in st.secrets:
        sec = st.secrets["FIREBASE"]
        # ถ้าเขาเก็บ JSON ไว้ใน key เดียว
        if "service_account" in sec:
            fb_conf = json.loads(sec["service_account"])
        else:
            fb_conf = sec
        db_url = sec.get("database_url")
    else:
        # 2) fallback อ่านจากไฟล์ local
        path = os.path.join(os.path.dirname(__file__), "serviceAccountKey.json")
        if not os.path.exists(path):
            st.error(f"❌ ไม่พบไฟล์ Firebase credentials: {path}")
            st.stop()
        fb_conf = json.load(open(path, "r"))
        db_url = fb_conf.get("databaseURL")

    # สร้าง credential และ initialize app
    cred = credentials.Certificate(fb_conf)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred, {"databaseURL": db_url})

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
            ref.push({"english": w.strip(), "thai": th.strip()})
            seen.add(key)
            added += 1

    if added:
        st.success(f"✅ เพิ่มคำใหม่ {added} คำลง Firebase เรียบร้อย")
    else:
        st.info("📌 ไม่มีคำใหม่ลง Firebase เพราะซ้ำทั้งหมด")

# ─── File upload & Extract ─────────────────────────────────────────────────
uploaded = st.file_uploader("📤 อัปโหลดไฟล์ (.jpg .png .pdf .pptx)", type=["jpg","jpeg","png","pdf","pptx"])
text = ""
if uploaded:
    ctype = uploaded.type
    if ctype.startswith("image/"):
        img = Image.open(uploaded)
        st.image(img, use_container_width=True)
        text = pytesseract.image_to_string(img.convert("L"), lang="eng")

    elif ctype == "application/pdf":
        pdf = PdfReader(uploaded)
        n = len(pdf.pages)
        st.write(f"📄 พบทั้งหมด {n} หน้า")
        mode = st.radio("โหมด PDF", ["หน้าเดียว","ช่วงหน้า","ทุกหน้า"])
        if mode == "หน้าเดียว":
            idx = st.selectbox("เลือกหน้า", list(range(1,n+1)), index=0) - 1
            text = pdf.pages[idx].extract_text()
        elif mode == "ช่วงหน้า":
            s = st.number_input("หน้าเริ่ม", 1, n, 1)
            e = st.number_input("หน้าสิ้นสุด", s, n, s)
            text = "\n\n".join(pdf.pages[i-1].extract_text() for i in range(s, e+1))
        else:
            text = "\n\n".join(p.extract_text() for p in pdf.pages)

    else:  # pptx
        prs = Presentation(uploaded)
        slides = ["\n".join(shape.text for shape in slide.shapes if hasattr(shape, "text"))
                  for slide in prs.slides]
        m = len(slides)
        st.write(f"📊 พบทั้งหมด {m} สไลด์")
        mode = st.radio("โหมด PPTX", ["สไลด์เดียว","ช่วงสไลด์","ทุกสไลด์"])
        if mode == "สไลด์เดียว":
            idx = st.selectbox("เลือกสไลด์", list(range(1,m+1)), index=0) - 1
            text = slides[idx]
        elif mode == "ช่วงสไลด์":
            s = st.number_input("สไลด์เริ่ม", 1, m, 1)
            e = st.number_input("สไลด์สุดท้าย", s, m, s)
            text = "\n\n".join(slides[i-1] for i in range(s, e+1))
        else:
            text = "\n\n".join(slides)

# ─── แก้ไขข้อความก่อนแปล ───────────────────────────────────────────────────
if text:
    editable = st.text_area("📋 ข้อความ OCR/Extract (แก้ไขได้)", text, height=200)

    # อ่านภาษาอังกฤษ
    if st.button("🔊 อ่านต้นฉบับ"):
        buf = io.BytesIO()
        gTTS(editable, lang="en").write_to_fp(buf)
        buf.seek(0)
        st.audio(buf)

    # แปลศัพท์ทีละคำ
    if st.button("🧠 แปลคำศัพท์"):
        words = []
        for ln in editable.splitlines():
            for w in ln.split():
                w2 = re.sub(r"[^a-zA-Z0-9\-]", "", w)
                if w2: words.append(w2)

        df = pd.DataFrame([{
            "english": w,
            "thai": GoogleTranslator(source="en", target="th").translate(w)
        } for w in words])

        st.session_state.vocab = df

# ─── แก้ไข/ลบ คำก่อนบันทึก ────────────────────────────────────────────────
if "vocab" in st.session_state:
    st.info("✏️ แก้ไข/ลบ คำก่อนบันทึก")
    edited = st.data_editor(
        st.session_state.vocab,
        use_container_width=True,
        num_rows="dynamic",
        hide_index=True,
        column_config={
            "english": st.column_config.TextColumn("English"),
            "thai": st.column_config.TextColumn("Thai Translation")
        }
    )
    if st.button("💾 บันทึกลง Firebase"):
        pairs = list(zip(edited.english, edited.thai))
        save_to_firebase(pairs)
        del st.session_state.vocab

# ─── แปลประโยคเต็ม ───────────────────────────────────────────────────────
if text:
    st.subheader("📝 แปลเป็นประโยคเต็ม")
    full = GoogleTranslator(source="en", target="th").translate(editable)
    st.success(full)
    if st.button("🔊 อ่านคำแปลไทย"):
        buf = io.BytesIO()
        gTTS(full, lang="th").write_to_fp(buf)
        buf.seek(0)
        st.audio(buf)