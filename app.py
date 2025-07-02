import streamlit as st
from PIL import Image
import pytesseract
from deep_translator import GoogleTranslator
from gtts import gTTS
import io
import firebase_admin
from firebase_admin import credentials, db
from PyPDF2 import PdfReader
from pptx import Presentation
import re

st.set_page_config(page_title="📘 Word & Sentence Translator", layout="centered")
st.title("📘 โปรแกรมแปลศัพท์ + ประโยค + เสียงอ่าน (ภาพ | PDF | PowerPoint)")

# ✅ Firebase Init
def init_firebase():
    if not firebase_admin._apps:
        firebase_config = {
            "type": st.secrets["FIREBASE"]["type"],
            "project_id": st.secrets["FIREBASE"]["project_id"],
            "private_key_id": st.secrets["FIREBASE"]["private_key_id"],
            "private_key": st.secrets["FIREBASE"]["private_key"],
            "client_email": st.secrets["FIREBASE"]["client_email"],
            "client_id": st.secrets["FIREBASE"]["client_id"],
            "auth_uri": st.secrets["FIREBASE"]["auth_uri"],
            "token_uri": st.secrets["FIREBASE"]["token_uri"],
            "auth_provider_x509_cert_url": st.secrets["FIREBASE"]["auth_provider_x509_cert_url"],
            "client_x509_cert_url": st.secrets["FIREBASE"]["client_x509_cert_url"]
        }
        cred = credentials.Certificate(firebase_config)
        firebase_admin.initialize_app(cred, {
            'databaseURL': 'https://vocab-tracker-7e059-default-rtdb.asia-southeast1.firebasedatabase.app/'
        })

# ✅ บันทึกเฉพาะคำใหม่ลง Firebase
def save_to_firebase(data):
    init_firebase()
    ref = db.reference('vocabulary')
    existing_data = ref.get()
    existing_words = set()

    if existing_data:
        for item in existing_data.values():
            clean_word = re.sub(r"[^a-zA-Z0-9\-]", "", item.get("english", "")).lower()
            existing_words.add(clean_word)

    added_count = 0
    for word, translation in data:
        clean_word = re.sub(r"[^a-zA-Z0-9\-]", "", word).lower()
        if clean_word and clean_word not in existing_words:
            ref.push({
                "english": word,
                "thai": translation
            })
            added_count += 1

    if added_count == 0:
        st.info("📌 ไม่มีคำใหม่เพิ่ม เพราะซ้ำใน Firebase")
    else:
        st.success(f"✅ บันทึกคำใหม่ {added_count} คำแล้ว")

# ✅ อ่านข้อความจาก PDF
def extract_text_from_pdf(file):
    reader = PdfReader(file)
    return "\n".join([page.extract_text() for page in reader.pages if page.extract_text()])

# ✅ อ่านข้อความจาก PPTX
def extract_text_from_pptx(file):
    prs = Presentation(file)
    text = ""
    for slide in prs.slides:
        for shape in slide.shapes:
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    text += para.text + "\n"
    return text

# ✅ ดึงคำ
def extract_words(text):
    return re.findall(r'\b\w+\b', text)

# ✅ แปลคำศัพท์
def translate_words(words):
    results = []
    for word in words:
        try:
            th = GoogleTranslator(source='en', target='th').translate(word)
        except:
            th = "-"
        results.append((word, th))
    return results

# ✅ รับไฟล์
uploaded_file = st.file_uploader("📤 อัปโหลดไฟล์ .jpg .png .pdf .pptx", type=["jpg", "jpeg", "png", "pdf", "pptx"])
table_data = []

if uploaded_file:
    file_type = uploaded_file.name.split('.')[-1].lower()
    st.info(f"📂 ประเภทไฟล์: {file_type.upper()}")

    if file_type in ["jpg", "jpeg", "png"]:
        image = Image.open(uploaded_file)
        st.image(image, caption='📷 ภาพต้นฉบับ', use_container_width=True)
        text = pytesseract.image_to_string(image.convert('L'), lang='eng').strip()

    elif file_type == "pdf":
        text = extract_text_from_pdf(uploaded_file)

    elif file_type == "pptx":
        text = extract_text_from_pptx(uploaded_file)

    else:
        text = ""

    st.subheader("🧠 ข้อความจากไฟล์")
    st.text_area("📋 ข้อความ", value=text, height=200)

    if text:
        st.subheader("🔠 แปลคำศัพท์")
        words = extract_words(text)
        table_data = translate_words(words)

        st.write(f"🔢 จำนวนคำทั้งหมด: {len(table_data)} คำ")
        st.write("| คำศัพท์ (อังกฤษ) | คำแปล (ไทย) |")
        st.write("|-------------------|--------------|")
        for eng, th in table_data:
            st.write(f"| {eng} | {th} |")

        if table_data and st.button("💾 บันทึกลง Firebase"):
            save_to_firebase(table_data)

        st.subheader("📝 แปลประโยคเต็ม")
        try:
            full_translation = GoogleTranslator(source='en', target='th').translate(text)
            st.success(full_translation)

            if st.button("🔊 อ่านคำแปลไทย"):
                tts_th = gTTS(full_translation, lang='th')
                th_audio = io.BytesIO()
                tts_th.write_to_fp(th_audio)
                th_audio.seek(0)
                st.audio(th_audio, format='audio/mp3')
        except Exception as e:
            st.error("⚠️ แปลไม่ได้: " + str(e))
    else:
        st.warning("📭 ไม่พบข้อความ กรุณาอัปโหลดไฟล์ใหม่ที่ชัดเจน")