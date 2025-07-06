import io, re
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

# ─── Streamlit config ─────────────────────────────
st.set_page_config(page_title="📘 Word & Sentence Translator", layout="centered")
st.title("📘 โปรแกรมแปลศัพท์ + ประโยค + เสียงอ่าน")

# ─── Normalize helper ──────────────────────────────
def normalize(w: str) -> str:
    return re.sub(r"[^A-Za-z0-9\-]", "", w).strip().lower()

# ─── Firebase init ─────────────────────────────────
@st.cache_resource
def init_firebase_ref():
    # โหลด config จาก st.secrets
    fb = dict(st.secrets["FIREBASE"])
    # แปลง "\n" ให้เป็น newline จริง
    fb["private_key"] = fb["private_key"].replace("\\n", "\n")
    cred = credentials.Certificate(fb)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(
            cred,
            {"databaseURL": f"https://{fb['project_id']}-default-rtdb.asia-southeast1.firebasedatabase.app"}
        )
    return db.reference("vocabulary")

# ─── Save to Firebase ──────────────────────────────
def save_to_firebase(pairs):
    ref = init_firebase_ref()
    existing = ref.get() or {}
    seen = { normalize(item["english"]) for item in existing.values() }
    added = 0
    for eng, th in pairs:
        key = normalize(eng)
        if key and key not in seen:
            ref.push({"english": eng, "thai": th})
            added += 1
            seen.add(key)
    if added:
        st.success(f"✅ เพิ่มคำใหม่ {added} คำลง Firebase")
    else:
        st.info("📌 ไม่มีคำใหม่เพราะซ้ำทั้งหมด")

# ─── File upload & extract text ────────────────────
uploaded = st.file_uploader("📤 อัปโหลดไฟล์ (.jpg .png .pdf .pptx)", type=["jpg","jpeg","png","pdf","pptx"])
text = ""
if uploaded:
    c = uploaded.type
    if c.startswith("image/"):
        img = Image.open(uploaded)
        st.image(img, use_container_width=True)
        text = pytesseract.image_to_string(img.convert("L"), lang="eng")
    elif c == "application/pdf":
        pdf = PdfReader(uploaded); n = len(pdf.pages)
        st.write(f"📄 พบบ {n} หน้า")
        mode = st.radio("โหมด PDF", ["หน้าเดียว","ช่วงหน้า","ทุกหน้า"])
        if mode == "หน้าเดียว":
            p = st.selectbox("เลือกหน้า", list(range(1,n+1))) - 1
            text = pdf.pages[p].extract_text() or ""
        elif mode == "ช่วงหน้า":
            s = st.number_input("หน้าเริ่ม",1,n,1)
            e = st.number_input("หน้าสิ้นสุด",s,n,s)
            texts = [pdf.pages[i-1].extract_text() or "" for i in range(s,e+1)]
            text = "\n".join(texts)
        else:
            texts = [p.extract_text() or "" for p in pdf.pages]
            text = "\n".join(texts)
    else:
        prs = Presentation(uploaded)
        slides = ["\n".join(shp.text for shp in sl.shapes if hasattr(shp,"text")) for sl in prs.slides]
        m = len(slides)
        st.write(f"📊 พบ {m} สไลด์")
        mode = st.radio("โหมด PPTX", ["สไลด์เดียว","ช่วงสไลด์","ทุกสไลด์"])
        if mode == "สไลด์เดียว":
            i = st.selectbox("เลือกสไลด์", list(range(1,m+1))) - 1
            text = slides[i]
        elif mode == "ช่วงสไลด์":
            s = st.number_input("สไลด์เริ่ม",1,m,1)
            e = st.number_input("สไลด์สุดท้าย",s,m,s)
            text = "\n".join(slides[j-1] for j in range(s,e+1))
        else:
            text = "\n\n".join(slides)

# ─── แก้ไข Text & แปลคำ ────────────────────────────
if text:
    editable = st.text_area("📋 ข้อความ (แก้ไขได้)", text, height=200)
    if st.button("🔊 อ่านต้นฉบับ"):
        buf = io.BytesIO(); gTTS(editable, lang="en").write_to_fp(buf); buf.seek(0)
        st.audio(buf, format="audio/mp3")

    if st.button("🧠 แปลคำศัพท์"):
        words = re.findall(r"[A-Za-z0-9\-]+", editable)
        df = pd.DataFrame([
            {"english": w, "thai": GoogleTranslator("en","th").translate(w)}
            for w in words if w
        ])
        st.session_state.vocab = df

# ─── แก้ไขก่อนบันทึก ────────────────────────────────
if "vocab" in st.session_state:
    st.info("✏️ แก้ไข/ลบ คำก่อนบันทึก")
    edited = st.data_editor(st.session_state.vocab, hide_index=True, num_rows="dynamic")
    if st.button("💾 บันทึกลง Firebase"):
        pairs = list(zip(edited.english, edited.thai))
        save_to_firebase(pairs)
        del st.session_state.vocab

# ─── แปลประโยคเต็ม ─────────────────────────────────
if text:
    st.subheader("📝 แปลเป็นประโยคเต็ม")
    full = GoogleTranslator("en","th").translate(editable)
    st.success(full)
    if st.button("🔊 อ่านแปลไทย"):
        buf = io.BytesIO(); gTTS(full, lang="th").write_to_fp(buf); buf.seek(0)
        st.audio(buf)