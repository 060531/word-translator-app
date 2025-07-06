# app.py
import json, io, re
import streamlit as st
import pytesseract
import pandas as pd
from PIL import Image
from deep_translator import GoogleTranslator
from gtts import gTTS
import firebase_admin
from firebase_admin import credentials, db
from PyPDF2 import PdfReader
from pptx import Presentation

# ─── Streamlit page config ─────────────────────────────────────────────
st.set_page_config(page_title="📘 Word & Sentence Translator", layout="centered")
st.title("📘 โปรแกรมแปลศัพท์ + ประโยค + เสียงอ่าน")

# ─── Normalize helper ───────────────────────────────────────────────────
def normalize(word: str) -> str:
    return re.sub(r"[^a-zA-Z0-9\-]", "", word).strip().lower()

# ─── Firebase init (ใช้ st.secrets["FIREBASE"]["service_account"]) ──────
@st.cache_resource
def init_firebase():
    # อ่าน JSON string จาก triple-quoted secret
    svc_str = st.secrets["FIREBASE"]["service_account"]
    svc_json = json.loads(svc_str)
    cred = credentials.Certificate(svc_json)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(
            cred,
            {"databaseURL": f"https://{svc_json['project_id']}-default-rtdb.asia-southeast1.firebasedatabase.app"}
        )
    return db.reference("vocabulary")

# ─── ฟังก์ชันบันทึกคำใหม่ลง Firebase ─────────────────────────────────
def save_to_firebase(pairs: list[tuple[str,str]]):
    ref = init_firebase()
    existing = ref.get() or {}
    seen = { normalize(v.get("english","")) for v in existing.values() }
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

# ─── อัปโหลดไฟล์ OCR/Extract ────────────────────────────────────────────
uploaded = st.file_uploader("📤 อัปโหลดไฟล์ (.jpg .png .pdf .pptx)", type=["jpg","jpeg","png","pdf","pptx"])
text = ""
if uploaded:
    t = uploaded.type
    if t.startswith("image/"):
        img = Image.open(uploaded)
        st.image(img, use_container_width=True)
        text = pytesseract.image_to_string(img.convert("L"), lang="eng")
    elif t == "application/pdf":
        pdf = PdfReader(uploaded)
        n = len(pdf.pages)
        st.write(f"📄 พบ {n} หน้า")
        mode = st.radio("โหมด PDF", ["หน้าเดียว","ช่วงหน้า","ทุกหน้า"])
        if mode=="หน้าเดียว":
            p = st.selectbox("เลือกหน้า", list(range(1,n+1))) -1
            text = pdf.pages[p].extract_text()
        elif mode=="ช่วงหน้า":
            s = st.number_input("หน้าเริ่ม",1,n,1)
            e = st.number_input("หน้าสิ้นสุด",s,n,s)
            text = "\n".join(pdf.pages[i-1].extract_text() for i in range(s,e+1))
        else:
            text = "\n".join(p.extract_text() for p in pdf.pages)
    else:  # pptx
        prs = Presentation(uploaded)
        slides = ["\n".join(s.text for s in sl.shapes if hasattr(s,"text")) for sl in prs.slides]
        m = len(slides)
        st.write(f"📊 พบ {m} สไลด์")
        mode = st.radio("โหมด PPTX", ["สไลด์เดียว","ช่วงสไลด์","ทุกสไลด์"])
        if mode=="สไลด์เดียว":
            i = st.selectbox("เลือกสไลด์", list(range(1,m+1))) -1
            text = slides[i]
        elif mode=="ช่วงสไลด์":
            s = st.number_input("สไลด์เริ่ม",1,m,1)
            e = st.number_input("สไลด์สุดท้าย",s,m,s)
            text = "\n".join(slides[j-1] for j in range(s,e+1))
        else:
            text = "\n\n".join(slides)

# ─── แก้ไขข้อความก่อนแปล ─────────────────────────────────────────────────
if text:
    editable = st.text_area("📋 ข้อความ OCR/Extract (แก้ไขได้)", text, height=200)
    if st.button("🔊 อ่านต้นฉบับ"):
        buf = io.BytesIO()
        gTTS(editable, lang="en").write_to_fp(buf); buf.seek(0)
        st.audio(buf)

    if st.button("🧠 แปลคำศัพท์"):
        words = []
        for ln in editable.splitlines():
            for w in ln.split():
                w2 = re.sub(r"[^a-zA-Z0-9\-]","",w)
                if w2: words.append(w2)
        df = pd.DataFrame([{
            "english": w,
            "thai": GoogleTranslator(source="en", target="th").translate(w)
        } for w in words])
        st.session_state.vocab = df

# ─── แก้ไข/ลบก่อนบันทึก ───────────────────────────────────────────────────
if "vocab" in st.session_state:
    st.info("✏️ แก้ไข/ลบ คำก่อนบันทึก")
    edited = st.data_editor(
        st.session_state.vocab,
        use_container_width=True,
        num_rows="dynamic",
        hide_index=True
    )
    if st.button("💾 บันทึกคำศัพท์ลง Firebase"):
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
        gTTS(full, lang="th").write_to_fp(buf); buf.seek(0)
        st.audio(buf)