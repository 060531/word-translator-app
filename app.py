import io, json, re
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

# ── Streamlit page setup ────────────────────────────────────────────────────
st.set_page_config(page_title="📘 Word & Sentence Translator", layout="centered")
st.title("📘 โปรแกรมแปลศัพท์ + ประโยค + เสียงอ่าน")

# ── Normalize ────────────────────────────────────────────────────────────────
def normalize(w: str) -> str:
    return re.sub(r"[^A-Za-z0-9\-]", "", w).strip().lower()
st.write("DEBUG st.secrets[FIREBASE]:", list(st.secrets["FIREBASE"].keys()))
# ── Initialize Firebase ─────────────────────────────────────────────────────

@st.cache_resource
def init_firebase_ref():
    fb = st.secrets["FIREBASE"]

    # 1) เอา JSON string มา parse เป็น dict
    sa_dict = json.loads(fb["service_account"])

    # 2) เตรียม credential
    cred = credentials.Certificate(sa_dict)

    # 3) init firebase app (ถ้ายังไม่เคย init)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred, {
            "databaseURL": fb["database_url"]
        })

    # 4) คืน reference ชี้ไปยัง /vocabulary
    return db.reference("vocabulary")

# ── Save to Firebase ─────────────────────────────────────────────────────────
def save_to_firebase(pairs):
    ref = init_firebase_ref()
    existing = ref.get() or {}
    seen = {normalize(v.get("english","")) for v in existing.values()}

    added = 0
    for eng, th in pairs:
        k = normalize(eng)
        if k and k not in seen:
            ref.push({"english": eng.strip(), "thai": th.strip()})
            seen.add(k)
            added += 1

    if added:
        st.success(f"✅ เพิ่มคำใหม่ {added} คำลง Firebase")
    else:
        st.info("📌 ไม่มีคำใหม่ เพราะซ้ำหมดแล้ว")

# ── File upload & OCR/Extract ───────────────────────────────────────────────
uploaded = st.file_uploader("📤 อัปโหลดไฟล์ (.jpg .png .pdf .pptx)", type=["jpg","jpeg","png","pdf","pptx"])
text = ""
if uploaded:
    ctype = uploaded.type
    if ctype.startswith("image/"):
        img = Image.open(uploaded); st.image(img, use_container_width=True)
        text = pytesseract.image_to_string(img.convert("L"), lang="eng")

    elif ctype == "application/pdf":
        pdf = PdfReader(uploaded); n = len(pdf.pages)
        st.write(f"📄 พบ {n} หน้า")
        mode = st.radio("โหมด PDF", ["หน้าเดียว","ช่วงหน้า","ทุกหน้า"])
        if mode=="หน้าเดียว":
            p = st.selectbox("เลือกหน้า", list(range(1,n+1))) - 1
            text = pdf.pages[p].extract_text()
        elif mode=="ช่วงหน้า":
            s = st.number_input("หน้าเริ่ม",1,n,1)
            e = st.number_input("หน้าสิ้นสุด",s,n,s)
            text = "\n".join(pdf.pages[i-1].extract_text() for i in range(s,e+1))
        else:
            text = "\n\n".join(p.extract_text() for p in pdf.pages)

    else:  # pptx
        prs = Presentation(uploaded)
        slides = ["\n".join(shp.text for shp in sl.shapes if hasattr(shp,"text")) for sl in prs.slides]
        m = len(slides); st.write(f"📊 พบ {m} สไลด์")
        mode = st.radio("โหมด PPTX", ["สไลด์เดียว","ช่วงสไลด์","ทุกสไลด์"])
        if mode=="สไลด์เดียว":
            i = st.selectbox("เลือกสไลด์", list(range(1,m+1))) - 1
            text = slides[i]
        elif mode=="ช่วงสไลด์":
            s = st.number_input("สไลด์เริ่ม",1,m,1)
            e = st.number_input("สไลด์สุดท้าย",s,m,s)
            text = "\n\n".join(slides[j-1] for j in range(s,e+1))
        else:
            text = "\n\n".join(slides)

# ── แก้ไขข้อความก่อนแปล ─────────────────────────────────────────────────────
if text:
    editable = st.text_area("📋 ข้อความ OCR/Extract (แก้ไขได้)", text, height=200)

    if st.button("🔊 อ่านต้นฉบับ"):
        buf = io.BytesIO(); gTTS(editable, lang="en").write_to_fp(buf); buf.seek(0)
        st.audio(buf)

    if st.button("🧠 แปลคำศัพท์"):
        words = []
        for ln in editable.splitlines():
            for w in ln.split():
                w2 = re.sub(r"[^A-Za-z0-9\-]", "", w)
                if w2: words.append(w2)
        df = pd.DataFrame([
            {"english": w, "thai": GoogleTranslator("en","th").translate(w)}
            for w in words
        ])
        st.session_state.vocab = df

# ── ให้แก้ไข/ลบ ก่อนบันทึก ───────────────────────────────────────────────────
if "vocab" in st.session_state:
    st.info("✏️ แก้ไข/ลบ คำก่อนบันทึก")
    ed = st.data_editor(st.session_state.vocab, hide_index=True, use_container_width=True)
    if st.button("💾 บันทึกลง Firebase"):
        pairs = list(zip(ed.english, ed.thai))
        save_to_firebase(pairs)
        del st.session_state.vocab

# ── แปลเป็นประโยคเต็ม ───────────────────────────────────────────────────────
if text:
    st.subheader("📝 แปลประโยคเต็ม")
    full = GoogleTranslator("en","th").translate(editable)
    st.success(full)
    if st.button("🔊 อ่านคำแปลไทย"):
        buf = io.BytesIO(); gTTS(full, lang="th").write_to_fp(buf); buf.seek(0)
        st.audio(buf)