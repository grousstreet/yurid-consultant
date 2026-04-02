import streamlit as st
from openai import OpenAI
import uuid
from datetime import datetime
import sqlite3
import os

# Для PDF
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import simpleSplit
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

st.set_page_config(
    page_title="ЮрИИ Консультант",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded"
)

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=st.secrets["OPENROUTER_API_KEY"],
)

SYSTEM_PROMPT = """
Ты — ЮрИИ Консультант, официальный ИИ-помощник Торайгыров Университета (Павлодар, Казахстан).
Ты отвечаешь ТОЛЬКО по законодательству Республики Казахстан.

КРИТИЧЕСКИ ВАЖНЫЕ ПРАВИЛА:
1. Всегда отвечай только по законам РК (УК РК - Уголовный Кодекс Республики Казахстан https://adilet.zan.kz/rus/docs/K1400000226,
Трудовой Кодекс Республики Казахстан - ТК РК https://adilet.zan.kz/rus/docs/K1500000414
 Семейный кодекс Республики Казахстан-СК РК https://adilet.zan.kz/rus/docs/K1100000518
 Гражданский Процесуальный Кодекс-ГПК https://adilet.zan.kz/rus/docs/K1500000377
 Административное правонарушение-КоАП https://adilet.zan.kz/rus/docs/K1400000235
 Административный процедурно-процессуальный Кодекс-АППК https://adilet.zan.kz/rus/docs/K2000000350
 Уголовно-процессуальный кодекс Республики Казахстан-УПК РК https://adilet.zan.kz/rus/docs/K1400000231
 Предпринимательский кодекс Республики Казахстан- ПК РК https://adilet.zan.kz/rus/docs/K1500000375
 Гражданский кодекс Республики Казахстан-ГК РК https://adilet.zan.kz/rus/docs/K940001000_ , https://adilet.zan.kz/rus/docs/K990000409_

2. Строго запрещено:

Давать ответы без опоры на законы Республики Казахстан
Придумывать статьи или искажать нормы закона

3. В КАЖДОМ ответе обязательно начинай с предупреждения:
   "⚠️ Внимание: Я — ИИ и даю только общую информацию. Это НЕ является юридической консультацией. Для защиты ваших прав обратитесь к адвокату или в компетентный государственный орган."
4. Всегда указывай:

Точную статью закона (номер и название)
Краткое и понятное объяснение статьи
Прямую ссылку на источник (https://adilet.zan.kz
)

5. Формат ответа (обязательный):

1.Норма закона
(статья, кодекс)
2.Простое объяснение
(без сложных юридических терминов)
3.Пошаговый план действий
(что делать пользователю прямо сейчас)
4.Примеры судебных решений
(реальные решения из практики по аналогичным случаям)
5.Прогноз возможного исхода дела
(обоснованный, на основе законов и судебной практики)
6.Ссылка на закон
(обязательно с adilet)

6. Стиль ответа:

Понятный, простой язык
Без «воды»
Чётко и по делу
Ориентирован на людей без юридического образования

7. Дополнительно:

Если вопрос неясен → задай уточняющий вопрос
Если есть несколько вариантов решения → перечисли их
По возможности указывай реальные последствия (штраф, срок, ответственность)

Цель:

Помогать пользователям (гражданам, студентам, предпринимателям, пенсионерам) быстро понимать свои права и получать конкретные действия для решения проблемы, включая судебную практику и прогноз возможного исхода.
"""

# ====================== БАЗА ДАННЫХ ======================
DB_NAME = "yurii.db"

@st.cache_resource
def get_db_connection():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    email TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL
                 )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS chats (
                    id TEXT PRIMARY KEY,
                    user_email TEXT NOT NULL,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(user_email) REFERENCES users(email) ON DELETE CASCADE
                 )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(chat_id) REFERENCES chats(id) ON DELETE CASCADE
                 )''')
    conn.commit()

init_db()

def register_user(email: str) -> bool:
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (email, created_at) VALUES (?, ?)",
                  (email, datetime.now().isoformat()))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False

def login_user(email: str) -> bool:
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT email FROM users WHERE email = ?", (email,))
    exists = c.fetchone() is not None
    return exists

def create_chat(user_email: str, title: str = "Новый чат") -> str:
    chat_id = str(uuid.uuid4())
    now = datetime.now().isoformat()
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""INSERT INTO chats (id, user_email, title, created_at, updated_at)
                 VALUES (?, ?, ?, ?, ?)""", (chat_id, user_email, title, now, now))
    conn.commit()
    return chat_id

def save_message(chat_id: str, role: str, content: str):
    now = datetime.now().isoformat()
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""INSERT INTO messages (chat_id, role, content, created_at)
                 VALUES (?, ?, ?, ?)""", (chat_id, role, content, now))
    c.execute("UPDATE chats SET updated_at = ? WHERE id = ?", (now, chat_id))
    conn.commit()

def get_chat_messages(chat_id: str):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT role, content FROM messages WHERE chat_id = ? ORDER BY id ASC", (chat_id,))
    return [dict(row) for row in c.fetchall()]

def get_user_chats(email: str):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""SELECT id, title FROM chats 
                 WHERE user_email = ? ORDER BY updated_at DESC""", (email,))
    return [dict(row) for row in c.fetchall()]

def update_chat_title(chat_id: str, title: str):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE chats SET title = ?, updated_at = ? WHERE id = ?",
              (title, datetime.now().isoformat(), chat_id))
    conn.commit()

# ====================== ИНИЦИАЛИЗАЦИЯ СЕССИИ ======================
if "email" not in st.session_state:
    st.session_state.email = None
if "current_chat_id" not in st.session_state:
    st.session_state.current_chat_id = None
if "temp_chats" not in st.session_state:
    st.session_state.temp_chats = {}
if "auth_mode" not in st.session_state:
    st.session_state.auth_mode = None

# Создаём первый чат
if st.session_state.current_chat_id is None:
    if st.session_state.email:
        first_id = create_chat(st.session_state.email)
    else:
        first_id = str(uuid.uuid4())
        st.session_state.temp_chats[first_id] = {"title": "Новый чат", "history": []}
    st.session_state.current_chat_id = first_id

# ====================== SIDEBAR ======================
with st.sidebar:
    st.markdown("### ⚖️ ЮрИИ Консультант")
    st.caption("Торайгыров Университет • 2026")

    if st.session_state.email:
        st.success(f"✅ {st.session_state.email}")
        if st.button("🚪 Выйти", use_container_width=True):
            st.session_state.email = None
            st.session_state.auth_mode = None
            st.rerun()
    else:
        st.warning("🔑 Требуется авторизация")
        st.subheader("Авторизация")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Войти", use_container_width=True, type="primary"):
                st.session_state.auth_mode = "login"
                st.rerun()
        with col2:
            if st.button("Регистрация", use_container_width=True, type="secondary"):
                st.session_state.auth_mode = "register"
                st.rerun()

    st.divider()

    # Новый чат
    if st.button("➕ Новый чат", type="primary", use_container_width=True):
        if st.session_state.email:
            new_id = create_chat(st.session_state.email, f"Чат {len(get_user_chats(st.session_state.email)) + 1}")
        else:
            new_id = str(uuid.uuid4())
            st.session_state.temp_chats[new_id] = {"title": f"Чат {len(st.session_state.temp_chats) + 1}", "history": []}
        st.session_state.current_chat_id = new_id
        st.rerun()

    st.subheader("Ваши чаты")

    if st.session_state.email:
        for chat in get_user_chats(st.session_state.email):
            chat_id = chat["id"]
            title = chat["title"]
            is_current = chat_id == st.session_state.current_chat_id
            if st.button(
                f"{'● ' if is_current else ''}{title[:40]}{'...' if len(title)>40 else ''}",
                key=f"chat_{chat_id}",
                use_container_width=True,
                type="secondary" if not is_current else "primary"
            ):
                st.session_state.current_chat_id = chat_id
                st.rerun()
    else:
        for chat_id, chat in st.session_state.temp_chats.items():
            title = chat["title"]
            is_current = chat_id == st.session_state.current_chat_id
            if st.button(
                f"{'● ' if is_current else ''}{title[:40]}{'...' if len(title)>40 else ''}",
                key=f"temp_{chat_id}",
                use_container_width=True,
                type="secondary" if not is_current else "primary"
            ):
                st.session_state.current_chat_id = chat_id
                st.rerun()

    st.divider()

    # Экспорт
    if st.session_state.current_chat_id:
        if st.session_state.email:
            history = get_chat_messages(st.session_state.current_chat_id)
        else:
            history = st.session_state.temp_chats.get(st.session_state.current_chat_id, {}).get("history", [])

        if history:
            col1, col2 = st.columns(2)
            with col1:
                if st.button("📥 TXT", use_container_width=True):
                    txt_content = ""
                    for msg in history:
                        role = "Пользователь" if msg["role"] == "user" else "ЮрИИ"
                        txt_content += f"{role}: {msg['content']}\n\n"
                    st.download_button(
                        label="Скачать TXT",
                        data=txt_content,
                        file_name=f"чат_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
                        mime="text/plain",
                        use_container_width=True
                    )
            with col2:
                if st.button("📄 PDF", use_container_width=True):
                    if not PDF_AVAILABLE:
                        st.error("reportlab не установлен")
                        st.stop()
                    pdf_filename = f"юрИИ_чат_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
                    from reportlab.pdfbase import pdfmetrics
                    from reportlab.pdfbase.ttfonts import TTFont
                    font_path = "DejaVuSans.ttf"
                    pdfmetrics.registerFont(TTFont('DejaVuSans', font_path))
                    c = canvas.Canvas(pdf_filename, pagesize=A4)
                    width, height = A4
                    y = height - 80
                    margin = 50
                    c.setFont("DejaVuSans", 16)
                    c.drawString(margin, y, "⚖️ ЮрИИ Консультант — Чат")
                    y -= 30
                    c.setFont("DejaVuSans", 11)
                    c.drawString(margin, y, f"Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
                    c.drawString(margin, y - 15, f"Пользователь: {st.session_state.email or 'Гость'}")
                    y -= 50
                    c.setFont("DejaVuSans", 11)
                    line_height = 16
                    for msg in history:
                        role = "👤 Пользователь" if msg["role"] == "user" else "⚖️ ЮрИИ"
                        text = f"{role}:\n{msg['content']}\n"
                        lines = simpleSplit(text, "DejaVuSans", 11, width - 2*margin)
                        for line in lines:
                            if y < 50:
                                c.showPage()
                                y = height - 50
                                c.setFont("DejaVuSans", 11)
                            c.drawString(margin, y, line)
                            y -= line_height
                        y -= 10
                    c.save()
                    with open(pdf_filename, "rb") as f:
                        pdf_bytes = f.read()
                    st.download_button(
                        label="⬇️ Скачать PDF",
                        data=pdf_bytes,
                        file_name=pdf_filename,
                        mime="application/pdf",
                        use_container_width=True
                    )
                    try:
                        os.remove(pdf_filename)
                    except:
                        pass

    st.caption("Разработано кафедрой Computer Science")

# ====================== ГЛАВНАЯ ЧАСТЬ ======================
st.title("⚖️ ЮрИИ Консультант")
st.caption("ИИ-помощник по законодательству Республики Казахстан")

# Формы логина / регистрации
if not st.session_state.email:
    if st.session_state.auth_mode in ["login", "register"]:
        st.subheader("🔑 Вход" if st.session_state.auth_mode == "login" else "📝 Регистрация")
        
        email = st.text_input("Email:", placeholder="example@gmail.com", key="auth_email")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ Подтвердить", type="primary", use_container_width=True):
                if "@" in email and "." in email:
                    if st.session_state.auth_mode == "register":
                        if register_user(email):
                            st.success("Регистрация успешна!")
                            st.session_state.email = email
                            st.session_state.auth_mode = None
                            st.rerun()
                        else:
                            st.error("Такой email уже зарегистрирован")
                    else:  # login
                        if login_user(email):
                            st.success("Вход выполнен!")
                            st.session_state.email = email
                            st.session_state.auth_mode = None
                            st.rerun()
                        else:
                            st.error("Пользователь не найден. Зарегистрируйтесь.")
                else:
                    st.error("Введите корректный email")
        with col2:
            if st.button("❌ Отмена", use_container_width=True):
                st.session_state.auth_mode = None
                st.rerun()
    else:
        st.info("Нажмите **Войти** или **Регистрация** в боковой панели")

else:
    st.success(f"Вы вошли как: **{st.session_state.email}**")
    st.divider()

    history = get_chat_messages(st.session_state.current_chat_id) if st.session_state.email else \
              st.session_state.temp_chats.get(st.session_state.current_chat_id, {}).get("history", [])

    for msg in history:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    user_input = st.chat_input("Опишите вашу юридическую ситуацию...")

    if user_input:
        if st.session_state.email:
            save_message(st.session_state.current_chat_id, "user", user_input)
        else:
            st.session_state.temp_chats[st.session_state.current_chat_id]["history"].append({"role": "user", "content": user_input})

        with st.chat_message("user"):
            st.write(user_input)

        with st.spinner("ЮрИИ анализирует запрос по законодательству РК..."):
            if st.session_state.email:
                messages = [{"role": "system", "content": SYSTEM_PROMPT}] + get_chat_messages(st.session_state.current_chat_id)
            else:
                messages = [{"role": "system", "content": SYSTEM_PROMPT}] + st.session_state.temp_chats[st.session_state.current_chat_id]["history"]

            response = client.chat.completions.create(
                model="perplexity/sonar",
                messages=messages,
                temperature=0.6,
                max_tokens=1200
            )

        answer = response.choices[0].message.content

        if st.session_state.email:
            save_message(st.session_state.current_chat_id, "assistant", answer)
            if len(get_chat_messages(st.session_state.current_chat_id)) == 2:
                update_chat_title(st.session_state.current_chat_id, user_input[:50] + ("..." if len(user_input) > 50 else ""))
        else:
            st.session_state.temp_chats[st.session_state.current_chat_id]["history"].append({"role": "assistant", "content": answer})

        with st.chat_message("assistant"):
            st.write(answer)

        st.rerun()

st.divider()
st.markdown("""
⚠️ **Внимание:** Ответы носят исключительно информационный характер и не являются официальной юридической консультацией. 
Для защиты ваших прав обращайтесь к адвокату или в компетентный орган.
""")
