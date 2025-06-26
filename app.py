import streamlit as st
import pytesseract
from PIL import Image
from deep_translator import GoogleTranslator
from gtts import gTTS
import io
import firebase_admin
from firebase_admin import credentials, db
import json

# ✅ ตั้งค่าหน้าเว็บ
st.set_page_config(page_title="📘 Word & Sentence Translator", layout="centered")
st.title("📘 โปรแกรมแปลศัพท์ + ประโยค + เสียงอ่าน")

# ✅ Firebase Init จาก st.secrets
def init_firebase():
    if not firebase_admin._apps:
        firebase_config = {
            "type": st.secrets["FIREBASE"]["type"],
            "project_id": st.secrets["FIREBASE"]["project_id"],
            "private_key_id": st.secrets["FIREBASE"]["private_key_id"],
            "private_key": st.secrets["FIREBASE"]["private_key"],  # ❌ เอา .replace(...) ออก
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

# ✅ Save to Firebase
def save_to_firebase(data):
    init_firebase()
    ref = db.reference('vocabulary')
    for word, translation in data:
        ref.push({
            "english": word,
            "thai": translation
        })

# ✅ ฟอร์มอัปโหลดภาพ
uploaded_file = st.file_uploader("📤 อัปโหลดภาพภาษาอังกฤษ", type=["jpg", "jpeg", "png"])
table_data = []

if uploaded_file:
    image = Image.open(uploaded_file)
    st.image(image, caption='📷 ภาพต้นฉบับ', use_container_width=True)

    gray_image = image.convert('L')
    text = pytesseract.image_to_string(gray_image, lang='eng').strip()
    st.subheader("🧠 ข้อความจากภาพ (OCR)")
    st.text_area("📋 ข้อความ OCR", value=text, height=200)

    if text:
        if st.button("🔊 อ่านข้อความภาษาอังกฤษ"):
            tts_en = gTTS(text, lang='en')
            en_audio = io.BytesIO()
            tts_en.write_to_fp(en_audio)
            en_audio.seek(0)
            st.audio(en_audio, format='audio/mp3')

        st.subheader("🔠 แปลคำศัพท์ (Word-by-word)")
        words = [word for line in text.splitlines() for word in line.strip().split()]
        for word in words:
            try:
                translated = GoogleTranslator(source='en', target='th').translate(word)
            except:
                translated = "-"
            table_data.append((word, translated))

        # ✅ แสดงตารางคำศัพท์
        if table_data:
            st.write(f"🔢 จำนวนคำทั้งหมด: {len(table_data)} คำ")
            st.write("| คำศัพท์ (อังกฤษ) | คำแปล (ไทย) |")
            st.write("|-------------------|--------------|")
            for eng, th in table_data:
                st.write(f"| {eng} | {th} |")

        # ✅ ปุ่มบันทึก แสดง *หลังจากมีคำศัพท์*
        if table_data and st.button("💾 บันทึกลง Firebase"):
            save_to_firebase(table_data)
            st.success("✅ บันทึกลง Firebase เรียบร้อยแล้ว")

        # ✅ แปลทั้งประโยค
        st.subheader("📝 แปลเป็นประโยคเต็ม")
        try:
            full_translation = GoogleTranslator(source='en', target='th').translate(text)
            st.success(full_translation)

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