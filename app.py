import streamlit as st
import pytesseract
from PIL import Image
from deep_translator import GoogleTranslator
import numpy as np
import cv2
from gtts import gTTS
import io

st.set_page_config(page_title="Word-by-Word & Sentence Translator with Voice", layout="centered")
st.title("📘 โปรแกรมแปลศัพท์ + ประโยค + เสียงอ่าน")

uploaded_file = st.file_uploader("📤 อัปโหลดภาพภาษาอังกฤษ", type=["jpg", "jpeg", "png"])

if uploaded_file:
    # โหลดภาพ
    image = Image.open(uploaded_file)
    st.image(image, caption='📷 ภาพต้นฉบับ', use_container_width=True)

    # 🔍 Preprocess
    img_cv = np.array(image)
    img_gray = cv2.cvtColor(img_cv, cv2.COLOR_RGB2GRAY)
    _, img_thresh = cv2.threshold(img_gray, 150, 255, cv2.THRESH_BINARY)

    # 🧠 OCR
    text = pytesseract.image_to_string(img_thresh, lang='eng')
    st.subheader("🧠 ข้อความที่ตรวจพบจากภาพ")
    st.text_area("📋 ข้อความ OCR", value=text, height=200)

    # 🎧 ปุ่มอ่านข้อความอังกฤษ
    if st.button("🔊 อ่านข้อความภาษาอังกฤษ"):
        tts_en = gTTS(text, lang='en')
        en_audio = io.BytesIO()
        tts_en.write_to_fp(en_audio)
        st.audio(en_audio, format='audio/mp3')

    # ✅ แปลคำศัพท์
    lines = text.splitlines()
    words = []
    for line in lines:
        words += line.strip().split()

    st.subheader("🔠 แปลคำศัพท์ทีละคำ (Word-by-word)")
    table_data = []
    for word in words:
        try:
            translated = GoogleTranslator(source='en', target='th').translate(word)
        except:
            translated = "-"
        table_data.append((word, translated))

    st.write("| คำศัพท์ (อังกฤษ) | คำแปล (ไทย) |")
    st.write("|-------------------|--------------|")
    for eng, th in table_data:
        st.write(f"| {eng} | {th} |")

    # ✅ แปลประโยค
    st.subheader("📝 แปลเป็นประโยคเต็ม")
    try:
        full_translation = GoogleTranslator(source='en', target='th').translate(text)
        st.success(full_translation)

        # 🎧 ปุ่มอ่านข้อความแปลไทย
        if st.button("🔊 อ่านคำแปลภาษาไทย"):
            tts_th = gTTS(full_translation, lang='th')
            th_audio = io.BytesIO()
            tts_th.write_to_fp(th_audio)
            st.audio(th_audio, format='audio/mp3')

    except Exception as e:
        st.error("⚠️ แปลประโยคไม่ได้: " + str(e))