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

# ─── Streamlit ───────────────────────────────────────
st.set_page_config(page_title="📘 Word & Sentence Translator", layout="centered")
st.title("📘 โปรแกรมแปลศัพท์ + ประโยค + เสียงอ่าน")

# ─── Normalize ────────────────────────────────────────
def normalize(w):  
    return re.sub(r"[^a-zA-Z0-9\-]", "", w).strip().lower()

# ─── Firebase Init ────────────────────────────────────
@st.cache_resource
def init_firebase_ref():
    fb = dict(st.secrets["FIREBASE"])
    # แปลง "\n" ให้กลับเป็น newline จริง
    fb["private_key"] = fb["private_key"].replace("\\n", "\n")
    
    cred = credentials.Certificate(fb)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(
            cred,
            {"databaseURL": f"https://{fb['project_id']}-default-rtdb.asia-southeast1.firebasedatabase.app"}
        )
    return db.reference("vocabulary")

def save_to_firebase(pairs):
    ref = init_firebase_ref()
    data = ref.get() or {}
    seen = { normalize(v["english"]) for v in data.values() }
    added = 0
    for en, th in pairs:
        key = normalize(en)
        if key and key not in seen:
            ref.push({"english": en, "thai": th})
            seen.add(key)
            added += 1
    if added:
        st.success(f"✅ เพิ่มคำใหม่ {added} คำ ลง Firebase")
    else:
        st.info("📌 ไม่มีคำใหม่ลง Firebase (ซ้ำทั้งหมด)")

# ─── File upload & OCR/Extract ───────────────────────
uploaded = st.file_uploader("📤 อัปโหลดไฟล์ (.jpg/.png/.pdf/.pptx)", type=["jpg","jpeg","png","pdf","pptx"])
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
            text = "\n".join(page.extract_text() for page in pdf.pages)
    else:
        prs = Presentation(uploaded)
        slides = ["\n".join([shp.text for shp in sl.shapes if hasattr(shp,"text")]) for sl in prs.slides]
        m = len(slides)
        st.write(f"📊 พบ {m} สไลด์")
        mode = st.radio("โหมด PPTX", ["สไลด์เดียว","ช่วงสไลด์","ทุกสไลด์"])
        if mode=="สไลด์เดียว":
            i = st.selectbox("เลือกสไลด์", list(range(1,m+1))) -1
            text = slides[i]
        elif mode=="ช่วงสไลด์":
            s = st.number_input("เริ่มสไลด์",1,m,1)
            e = st.number_input("ถึงสไลด์",s,m,s)
            text = "\n".join(slides[j-1] for j in range(s,e+1))
        else:
            text = "\n\n".join(slides)

# ─── แก้ไขข้อความก่อนแปล ─────────────────────────────
if text:
    editable = st.text_area("📋 ข้อความ OCR/Extract (แก้ไขได้)", text, height=200)

    # อ่านต้นฉบับ
    if st.button("🔊 อ่านต้นฉบับ"):
        buf = io.BytesIO()
        gTTS(editable, lang="en").write_to_fp(buf); buf.seek(0)
        st.audio(buf, format="audio/mp3")

    # แปลคำศัพท์ทีละคำ
    if st.button("🧠 แปลคำศัพท์"):
        words = []
        for ln in editable.splitlines():
            for w in ln.split():
                w2 = re.sub(r"[^a-zA-Z0-9\-]","", w)
                if w2: words.append(w2)
        df = pd.DataFrame([{
            "english": w,
            "thai": GoogleTranslator(source="en", target="th").translate(w)
        } for w in words])
        st.session_state["vocab_df"] = df

# ─── ตารางให้แก้ไข/ลบ ก่อนบันทึก ─────────────────────
if "vocab_df" in st.session_state:
    st.info("✏️ แก้ไข/ลบ คำก่อนบันทึก")
    edited = st.data_editor(
        st.session_state["vocab_df"],
        use_container_width=True, num_rows="dynamic", hide_index=True
    )
    if st.button("💾 บันทึกลง Firebase"):
        pairs = list(zip(edited.english, edited.thai))
        save_to_firebase(pairs)
        del st.session_state["vocab_df"]

# ─── แปลประโยคเต็ม ───────────────────────────────────
if text:
    st.subheader("📝 แปลเป็นประโยคเต็ม")
    try:
        full = GoogleTranslator(source="en", target="th").translate(editable)
        st.success(full)
        if st.button("🔊 อ่านคำแปลไทย"):
            buf2 = io.BytesIO()
            gTTS(full, lang="th").write_to_fp(buf2); buf2.seek(0)
            st.audio(buf2, format="audio/mp3")
    except Exception as e:
        st.error("⚠️ แปลประโยคไม่ได้: " + str(e))