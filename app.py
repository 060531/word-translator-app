import os
import re
import io
import json

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

# ─── Streamlit UI setup ────────────────────────────────────────────────────
st.set_page_config(page_title="📘 Word & Sentence Translator", layout="centered")
st.title("📘 โปรแกรมแปลศัพท์ + ประโยค + เสียงอ่าน")

# ─── Normalize helper ───────────────────────────────────────────────────────
def normalize(word: str) -> str:
    """ลบอักขระพิเศษและ lower-case"""
    return re.sub(r"[^a-zA-Z0-9\-]", "", word).strip().lower()

# ─── Firebase init ─────────────────────────────────────────────────────────
@st.cache_resource
def init_firebase() -> None:
    """
    อ่าน config จาก st.secrets["FIREBASE"] แล้ว initialize_app
    (แปลงเป็น dict ธรรมดาก่อนส่งเข้า Certificate)
    """
    # โหลด dict จาก secrets.toml
    fb_conf = dict(st.secrets["FIREBASE"])
    cred = credentials.Certificate(fb_conf)

    if not firebase_admin._apps:
        firebase_admin.initialize_app(
            cred,
            {
                # Database URL ปรับให้ตรงกับ project_id ของคุณ
                "databaseURL": f"https://{fb_conf['project_id']}-default-rtdb.asia-southeast1.firebasedatabase.app"
            }
        )

# ─── Save to Firebase ───────────────────────────────────────────────────────
def save_to_firebase(pairs: list[tuple[str,str]]) -> None:
    """บันทึกคู่คำ (eng, th) ลง Firebase Realtime DB (key: vocabulary)"""
    init_firebase()
    ref = db.reference("vocabulary")

    existing = ref.get() or {}
    seen = { normalize(item.get("english","")) for item in existing.values() }

    added = 0
    for eng, th in pairs:
        key = normalize(eng)
        if key and key not in seen:
            ref.push({"english": eng.strip(), "thai": th.strip()})
            seen.add(key)
            added += 1

    if added:
        st.success(f"✅ เพิ่มคำใหม่ {added} คำ ลง Firebase เรียบร้อยแล้ว")
    else:
        st.info("📌 ไม่มีคำใหม่เพิ่ม เพราะซ้ำทั้งหมด")

# ─── Upload & Extract Text ─────────────────────────────────────────────────
uploaded = st.file_uploader(
    "📤 อัปโหลดไฟล์ (.jpg .png .pdf .pptx)",
    type=["jpg","jpeg","png","pdf","pptx"]
)

text = ""
if uploaded:
    ctype = uploaded.type

    # — IMAGE via OCR —
    if ctype.startswith("image/"):
        img = Image.open(uploaded)
        st.image(img, use_container_width=True)
        text = pytesseract.image_to_string(img.convert("L"), lang="eng")

    # — PDF text-extract —
    elif ctype == "application/pdf":
        pdf = PdfReader(uploaded)
        n = len(pdf.pages)
        st.write(f"📄 พบทั้งหมด {n} หน้า")
        mode = st.radio("โหมด PDF", ["หน้าเดียว", "ช่วงหน้า", "ทุกหน้า"])
        if mode == "หน้าเดียว":
            p = st.selectbox("เลือกหน้า", list(range(1, n+1))) - 1
            text = pdf.pages[p].extract_text() or ""
        elif mode == "ช่วงหน้า":
            s = st.number_input("หน้าเริ่ม", 1, n, 1)
            e = st.number_input("หน้าสิ้นสุด", s, n, s)
            text = "\n".join(pdf.pages[i-1].extract_text() or "" for i in range(s, e+1))
        else:
            text = "\n\n".join(p.extract_text() or "" for p in pdf.pages)

    # — PowerPoint text-extract —
    else:  # pptx
        prs = Presentation(uploaded)
        slides = [
            "\n".join(shape.text for shape in slide.shapes if hasattr(shape, "text"))
            for slide in prs.slides
        ]
        m = len(slides)
        st.write(f"📊 พบทั้งหมด {m} สไลด์")
        mode = st.radio("โหมด PPTX", ["สไลด์เดียว", "ช่วงสไลด์", "ทุกสไลด์"])
        if mode == "สไลด์เดียว":
            i = st.selectbox("เลือกสไลด์", list(range(1, m+1))) - 1
            text = slides[i]
        elif mode == "ช่วงสไลด์":
            s = st.number_input("สไลด์เริ่ม", 1, m, 1)
            e = st.number_input("สไลด์สุดท้าย", s, m, s)
            text = "\n".join(slides[j-1] for j in range(s, e+1))
        else:
            text = "\n\n".join(slides)

# ─── Editable OCR/Text Area ─────────────────────────────────────────────────
if text:
    editable = st.text_area("📋 ข้อความ OCR/Extract (แก้ไขได้)", text, height=200)

    # อ่านต้นฉบับออกเสียง (อังกฤษ)
    if st.button("🔊 อ่านต้นฉบับ"):
        buf = io.BytesIO()
        gTTS(editable, lang="en").write_to_fp(buf)
        buf.seek(0)
        st.audio(buf, format="audio/mp3")

    # แปลคำศัพท์ทีละคำ
    if st.button("🧠 แปลคำศัพท์"):
        words = []
        for line in editable.splitlines():
            for w in line.split():
                w2 = re.sub(r"[^a-zA-Z0-9\-]", "", w)
                if w2:
                    words.append(w2)

        df = pd.DataFrame([
            {"english": w, "thai": GoogleTranslator(source="en", target="th").translate(w)}
            for w in words
        ])
        st.session_state.vocab = df

# ─── แก้ไข/ลบ คำก่อนบันทึกลง Firebase ────────────────────────────────────
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

# ─── แปลเป็นประโยคเต็ม ───────────────────────────────────────────────────
if text:
    st.subheader("📝 แปลเป็นประโยคเต็ม")
    try:
        full = GoogleTranslator(source="en", target="th").translate(editable)
        st.success(full)
        if st.button("🔊 อ่านคำแปลไทย"):
            buf2 = io.BytesIO()
            gTTS(full, lang="th").write_to_fp(buf2)
            buf2.seek(0)
            st.audio(buf2, format="audio/mp3")
    except Exception as e:
        st.error("⚠️ แปลประโยคไม่สำเร็จ: " + str(e))