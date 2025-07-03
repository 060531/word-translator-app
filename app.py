import streamlit as st
import pytesseract
from PIL import Image
from deep_translator import GoogleTranslator
from gtts import gTTS
import io
import firebase_admin
from firebase_admin import credentials, db
import re
import pandas as pd
from PyPDF2 import PdfReader
from pptx import Presentation

# ✅ ตั้งค่าหน้าเว็บ
st.set_page_config(page_title="📘 Word & Sentence Translator", layout="centered")
st.title("📘 โปรแกรมแปลศัพท์ + ประโยค + เสียงอ่าน")

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

# ✅ Save only new words
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
        st.info("📌 ไม่มีคำใหม่เพิ่ม เพราะคำศัพท์ทั้งหมดมีอยู่แล้วใน Firebase")
    else:
        st.success(f"✅ บันทึกคำใหม่ {added_count} คำ ลง Firebase แล้ว")

# ✅ อัปโหลดและดึงข้อความ
uploaded_file = st.file_uploader("📤 อัปโหลดไฟล์ (jpg, png, pdf, pptx)", type=["jpg", "jpeg", "png", "pdf", "pptx"])
text = ""

if uploaded_file:
    file_type = uploaded_file.type

    if file_type.startswith("image/"):
        image = Image.open(uploaded_file)
        st.image(image, caption='📷 ภาพต้นฉบับ', use_container_width=True)
        gray_image = image.convert("L")
        text = pytesseract.image_to_string(gray_image, lang="eng")

    elif file_type == "application/pdf":
        reader = PdfReader(uploaded_file)
        num_pages = len(reader.pages)
        selected_page = st.selectbox("📄 เลือกหน้าที่ต้องการอ่าน", list(range(1, num_pages + 1)), index=0)
        text = reader.pages[selected_page - 1].extract_text()

    elif file_type == "application/vnd.openxmlformats-officedocument.presentationml.presentation":
        prs = Presentation(uploaded_file)
        slides = [s for s in prs.slides]
        selected_slide = st.selectbox("📊 เลือกสไลด์ที่ต้องการอ่าน", list(range(1, len(slides) + 1)), index=0)
        text_content = [shape.text for shape in slides[selected_slide].shapes if hasattr(shape, "text")]
        text = "\n".join(text_content)

# ✅ แสดงข้อความให้แก้ไข
if text:
    editable_text = st.text_area("🧠 ข้อความที่ตรวจจับได้ (แก้ไขได้)", value=text.strip(), height=200)

    # อ่านเสียงภาษาอังกฤษ
    if st.button("🔊 อ่านข้อความภาษาอังกฤษ"):
        tts_en = gTTS(editable_text, lang='en')
        en_audio = io.BytesIO()
        tts_en.write_to_fp(en_audio)
        en_audio.seek(0)
        st.audio(en_audio, format='audio/mp3')

    # ✅ แปลคำศัพท์ทีละคำ
    if st.button("🧠 แปลคำศัพท์"):
        words = []
        for line in editable_text.splitlines():
            for word in line.split():
                clean_word = re.sub(r"[^a-zA-Z0-9\-]", "", word)
                if clean_word:
                    words.append(clean_word)

        unique_words = sorted(set(words))
        table_data = []
        for word in unique_words:
            try:
                th = GoogleTranslator(source="en", target="th").translate(word)
            except:
                th = "-"
            table_data.append({"english": word, "thai": th})

        df = pd.DataFrame(table_data)
        st.info("✏️ แก้ไขคำศัพท์หรือลบแถวก่อนบันทึก")
        edited_df = st.data_editor(
            df,
            use_container_width=True,
            num_rows="dynamic",
            hide_index=True,
            column_config={
                "english": st.column_config.TextColumn(label="English"),
                "thai": st.column_config.TextColumn(label="Thai Translation")
            }
        )

        if st.button("💾 บันทึกคำศัพท์ลง Firebase"):
            if not edited_df.empty:
                data_to_save = list(zip(edited_df["english"], edited_df["thai"]))
                save_to_firebase(data_to_save)
            else:
                st.warning("⚠️ ไม่มีคำศัพท์ที่จะแสดง")

    # ✅ แปลเป็นประโยค
    st.subheader("📑 แปลประโยคเต็ม")
    try:
        sentences = re.split(r'(?<=[.!?]) +', editable_text.strip())
        translated_sentences = []
        for sent in sentences:
            try:
                translated = GoogleTranslator(source='en', target='th').translate(sent)
            except:
                translated = "-"
            translated_sentences.append(translated)

        full_translation = "\n".join(translated_sentences)
        st.success(full_translation)

        if st.button("🔊 อ่านคำแปลภาษาไทย"):
            tts_th = gTTS(full_translation, lang='th')
            th_audio = io.BytesIO()
            tts_th.write_to_fp(th_audio)
            th_audio.seek(0)
            st.audio(th_audio, format='audio/mp3')

    except Exception as e:
        st.error("⚠️ แปลประโยคไม่ได้: " + str(e))