import streamlit as st
import pytesseract
from PIL import Image
from deep_translator import GoogleTranslator
from gtts import gTTS
import io
import re
import pandas as pd
import firebase_admin
from firebase_admin import credentials, db
from PyPDF2 import PdfReader
from pptx import Presentation

# ─── Streamlit page config ─────────────────────────────────────────────────
st.set_page_config(
    page_title="📘 Word & Sentence Translator",
    layout="centered"
)
st.title("📘 โปรแกรมแปลศัพท์ + ประโยค + เสียงอ่าน")

# ─── Helpers ────────────────────────────────────────────────────────────────
def normalize(w: str) -> str:
    """Strip non-alphanumeric and lowercase for dedupe."""
    return re.sub(r"[^A-Za-z0-9\-]", "", w).lower().strip()

@st.cache_resource
def init_firebase():
    # อ่าน JSON string จาก secrets
    svc_json = st.secrets["FIREBASE"]["service_account"]
    fb_conf = json.loads(svc_json)
    cred = credentials.Certificate(fb_conf)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred, {
            "databaseURL": f"https://{fb_conf['project_id']}-default-rtdb.asia-southeast1.firebasedatabase.app"
        })
def save_to_firebase(pairs: list[tuple[str,str]]):
    """Save only new words to Firebase under /vocabulary."""
    ref = init_firebase_ref()
    existing = ref.get() or {}
    seen = { normalize(item.get("english","")) for item in existing.values() }

    added = 0
    for eng, th in pairs:
        key = normalize(eng)
        if key and key not in seen:
            ref.push({"english": eng, "thai": th})
            seen.add(key)
            added += 1

    if added:
        st.success(f"✅ บันทึกคำใหม่ {added} คำลง Firebase")
    else:
        st.info("📌 ไม่มีคำใหม่เพิ่ม เพราะคำศัพท์ทั้งหมดมีอยู่แล้ว")

# ─── File upload & text extraction ─────────────────────────────────────────
uploaded = st.file_uploader(
    "📤 อัปโหลดไฟล์ (.jpg .png .pdf .pptx)",
    type=["jpg","jpeg","png","pdf","pptx"]
)

text = ""
if uploaded:
    ctype = uploaded.type

    # ── IMAGE OCR
    if ctype.startswith("image/"):
        img = Image.open(uploaded)
        st.image(img, caption="📷 ภาพต้นฉบับ", use_container_width=True)
        text = pytesseract.image_to_string(img.convert("L"), lang="eng")

    # ── PDF text
    elif ctype == "application/pdf":
        pdf = PdfReader(uploaded)
        n = len(pdf.pages)
        st.write(f"📄 พบทั้งหมด {n} หน้า")

        mode = st.radio("โหมด PDF", ["หน้าเดียว", "ช่วงหน้า", "ทุกหน้า"])
        if mode == "หน้าเดียว":
            p = st.selectbox("เลือกหน้า", list(range(1, n+1))) - 1
            text = pdf.pages[p].extract_text() or ""
        elif mode == "ช่วงหน้า":
            s = st.number_input("จากหน้า", 1, n, 1)
            e = st.number_input("ถึงหน้า", s, n, s)
            text = "\n\n".join(
                pdf.pages[i-1].extract_text() or ""
                for i in range(s, e+1)
            )
        else:
            text = "\n\n".join(p.extract_text() or "" for p in pdf.pages)

    # ── PPTX text
    else:
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
            s = st.number_input("จากสไลด์", 1, m, 1)
            e = st.number_input("ถึงสไลด์", s, m, s)
            text = "\n\n".join(slides[j-1] for j in range(s, e+1))
        else:
            text = "\n\n".join(slides)

# ─── Editable OCR/extracted text ───────────────────────────────────────────
if text:
    editable = st.text_area("📋 ข้อความที่ตรวจจับได้ (แก้ไขได้)", text, height=200)

    # ── TTS original English
    if st.button("🔊 อ่านต้นฉบับ"):
        buf = io.BytesIO()
        gTTS(editable, lang="en").write_to_fp(buf)
        buf.seek(0)
        st.audio(buf)

    # ── Word-by-word translation
    if st.button("🧠 แปลคำศัพท์"):
        words = []
        for ln in editable.splitlines():
            for w in ln.split():
                w2 = re.sub(r"[^A-Za-z0-9\-]", "", w)
                if w2:
                    words.append(w2)
        df = pd.DataFrame([
            {
                "english": w,
                "thai": GoogleTranslator(source="en", target="th").translate(w)
            }
            for w in words
        ])
        st.session_state["vocab_df"] = df

# ─── Edit & save your vocabulary ────────────────────────────────────────────
if "vocab_df" in st.session_state:
    st.info("✏️ แก้ไข/ลบคำศัพท์ก่อนบันทึก")
    edited = st.data_editor(
        st.session_state["vocab_df"],
        use_container_width=True,
        num_rows="dynamic",
        hide_index=True,
        column_config={
            "english": st.column_config.TextColumn("English"),
            "thai":    st.column_config.TextColumn("Thai Translation")
        }
    )
    if st.button("💾 บันทึกคำศัพท์ลง Firebase"):
        pairs = list(zip(edited.english, edited.thai))
        save_to_firebase(pairs)
        del st.session_state["vocab_df"]

# ─── Full-sentence translation & TTS ────────────────────────────────────────
if text:
    st.subheader("📝 แปลเป็นประโยคเต็ม")
    try:
        full = GoogleTranslator(source="en", target="th").translate(editable)
        st.success(full)
        if st.button("🔊 อ่านคำแปลไทย"):
            buf2 = io.BytesIO()
            gTTS(full, lang="th").write_to_fp(buf2)
            buf2.seek(0)
            st.audio(buf2)
    except Exception as e:
        st.error("⚠️ แปลประโยคไม่ได้: " + str(e))