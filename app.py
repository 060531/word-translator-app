import streamlit as st
import pytesseract
from PIL import Image
from deep_translator import GoogleTranslator
from gtts import gTTS
import io

st.set_page_config(page_title="📘 Word & Sentence Translator", layout="centered")
st.title("📘 โปรแกรมแปลศัพท์ + ประโยค + เสียงอ่าน")

uploaded_file = st.file_uploader("📤 อัปโหลดภาพภาษาอังกฤษ", type=["jpg", "jpeg", "png"])

if uploaded_file:
    # 📷 แสดงภาพต้นฉบับ
    image = Image.open(uploaded_file)
    st.image(image, caption='📷 ภาพต้นฉบับ', use_container_width=True)

    # 🔍 แปลงเป็น grayscale (ไม่ใช้ OpenCV)
    gray_image = image.convert('L')

    # 🧠 OCR ดึงข้อความ
    text = pytesseract.image_to_string(gray_image, lang='eng').strip()
    st.subheader("🧠 ข้อความจากภาพ (OCR)")
    st.text_area("📋 ข้อความ OCR", value=text, height=200)

    if text:
        # 🎧 ปุ่มอ่านภาษาอังกฤษ
        if st.button("🔊 อ่านข้อความภาษาอังกฤษ"):
            tts_en = gTTS(text, lang='en')
            en_audio = io.BytesIO()
            tts_en.write_to_fp(en_audio)
            en_audio.seek(0)
            st.audio(en_audio, format='audio/mp3')

        # ✅ แปลคำศัพท์ทีละคำ
        st.subheader("🔠 แปลคำศัพท์ (Word-by-word)")
        words = [word for line in text.splitlines() for word in line.strip().split()]
        table_data = []

        for word in words:
            try:
                translated = GoogleTranslator(source='en', target='th').translate(word)
            except:
                translated = "-"
            table_data.append((word, translated))

        if table_data:
            st.write("| คำศัพท์ (อังกฤษ) | คำแปล (ไทย) |")
            st.write("|-------------------|--------------|")
            for eng, th in table_data:
                st.write(f"| {eng} | {th} |")

        # ✅ แปลเป็นประโยค
        st.subheader("📝 แปลเป็นประโยคเต็ม")
        try:
            full_translation = GoogleTranslator(source='en', target='th').translate(text)
            st.success(full_translation)

            # 🎧 ปุ่มอ่านภาษาไทย
            if st.button("🔊 อ่านคำแปลภาษาไทย"):
                tts_th = gTTS(full_translation, lang='th')
                th_audio = io.BytesIO()
                tts_th.write_to_fp(th_audio)
                th_audio.seek(0)
                st.audio(th_audio, format='audio/mp3')

        except Exception as e:
            st.error("⚠️ แปลประโยคไม่ได้: " + str(e))
    else:
        st.warning("📭 ไม่พบข้อความจากภาพ กรุณาอัปโหลดภาพใหม่ที่ชัดเจน")