import streamlit as st
import pandas as pd
import sqlite3
import bcrypt
import plotly.express as px
from datetime import date

# ==========================================
# 1. إعدادات الصفحة المتقدمة
# ==========================================
st.set_page_config(page_title="IR Tracker Pro", layout="wide")
DB_NAME = "ir_tracker.db"

# ==========================================
# 2. إنشاء وتهيئة قاعدة البيانات (SQLite)
# ==========================================
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # إنشاء جدول المستخدمين
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (username TEXT PRIMARY KEY, password_hash BLOB, role TEXT)''')
    
    # إنشاء جدول طلبات الفحص (IR Logs)
    c.execute('''CREATE TABLE IF NOT EXISTS ir_logs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  sheet TEXT, reference TEXT UNIQUE, rev INTEGER,
                  element TEXT, location TEXT, description TEXT,
                  code_action TEXT, sub_date TEXT, rec_date TEXT)''')
    
    # إضافة حساب مدير افتراضي (لأول مرة فقط) إذا كانت القاعدة فارغة
    c.execute("SELECT * FROM users WHERE username='Dokdok'")
    if not c.fetchone():
        # تشفير كلمة السر '123456' بأعلى معايير الأمان
        hashed_pw = bcrypt.hashpw("123456".encode('utf-8'), bcrypt.gensalt())
        c.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)", 
                  ("Dokdok", hashed_pw, "admin"))
    
    conn.commit()
    conn.close()

# ==========================================
# 3. نظام الأمان والمصادقة (Security)
# ==========================================
def verify_login(username, password):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT password_hash, role FROM users WHERE username=?", (username,))
    result = c.fetchone()
    conn.close()
    
    if result:
        stored_hash = result[0]
        role = result[1]
        # التحقق من المطابقة الآمنة
        if bcrypt.checkpw(password.encode('utf-8'), stored_hash):
            return role
    return None

def login_page():
    st.title("نظام التتبع المتقدم 🔐")
    st.markdown("يرجى إدخال بيانات الدخول المعتمدة للوصول إلى قاعدة البيانات.")
    with st.form("login"):
        user = st.text_input("اسم المستخدم")
        pw = st.text_input("كلمة المرور", type="password")
        submit = st.form_submit_button("تسجيل الدخول")
        
        if submit:
            role = verify_login(user.strip(), pw)
            if role:
                st.session_state["logged_in"] = True
                st.session_state["username"] = user.strip()
                st.session_state["role"] = role
                st.rerun()
            else:
                st.error("اسم المستخدم أو كلمة المرور غير صحيحة!")

# ==========================================
# 4. لوحة القيادة التفاعلية (Plotly UI/UX)
# ==========================================
def dashboard():
    st.title("لوحة القيادة التفاعلية 📊")
    
    # جلب البيانات من قاعدة البيانات باستخدام Pandas
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT * FROM ir_logs", conn)
    conn.close()
    
    if df.empty:
        st.info("قاعدة البيانات فارغة حالياً. ابدأ بإضافة الطلبات الجديدة.")
        return

    # مؤشرات علوية (KPIs)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("إجمالي الطلبات", len(df))
    c2.metric("معتمد (A / B)", len(df[df["code_action"].isin(["A", "B"])]))
    c3.metric("مرفوض (C / D)", len(df[df["code_action"].isin(["C", "D"])]))
    c4.metric("قيد المراجعة (UR)", len(df[df["code_action"] == "UR"]))

    st.markdown("---")

    # رسومات بيانية متقدمة باستخدام Plotly
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("توزيع الحالات (Code Actions)")
        fig_pie = px.pie(df, names='code_action', hole=0.4, 
                         color_discrete_sequence=px.colors.qualitative.Pastel)
        st.plotly_chart(fig_pie, use_container_width=True)
        
    with col2:
        st.subheader("الطلبات حسب الأقسام (Sheets)")
        fig_bar = px.bar(df, x='sheet', color='sheet', 
                         color_discrete_sequence=px.colors.qualitative.Set2)
        st.plotly_chart(fig_bar, use_container_width=True)

# ==========================================
# 5. واجهة إضافة البيانات (Database Insert)
# ==========================================
def add_ir_page():
    st.title("إضافة IR جديد ➕")
    with st.form("add_ir"):
        c1, c2 = st.columns(2)
        with c1:
            sheet = st.selectbox("القسم", ["STR", "ARCH", "ELEC", "MECH", "SURV"])
            ref = st.text_input("رقم المرجع (Reference)")
            code = st.selectbox("Code Action", ["A", "B", "C", "CC", "D", "UR"])
        with c2:
            sub_date = st.date_input("تاريخ التسليم", value=date.today())
            rec_date = st.date_input("تاريخ الاستلام", value=date.today())
            desc = st.text_area("الوصف (Description)")
            
        submit = st.form_submit_button("حفظ في قاعدة البيانات")
        
        if submit:
            if not ref.strip():
                st.error("رقم المرجع (Reference) مطلوب!")
                return
            
            try:
                conn = sqlite3.connect(DB_NAME)
                c = conn.cursor()
                c.execute('''INSERT INTO ir_logs 
                             (sheet, reference, code_action, description, sub_date, rec_date) 
                             VALUES (?, ?, ?, ?, ?, ?)''',
                          (sheet, ref.strip(), code, desc, str(sub_date), str(rec_date)))
                conn.commit()
                conn.close()
                st.success(f"تم تسجيل {ref} بنجاح في النظام العالي الأمان!")
            except sqlite3.IntegrityError:
                st.error("هذا المرجع (Reference) مسجل بالفعل في قاعدة البيانات!")

# ==========================================
# المحرك الأساسي للتطبيق
# ==========================================
def main():
    # التأكد من تجهيز قاعدة البيانات تلقائياً
    init_db() 
    
    if not st.session_state.get("logged_in", False):
        login_page()
        return

    # القائمة الجانبية المتقدمة
    with st.sidebar:
        st.title("IR Tracker Pro")
        st.caption(f"مرحباً بك: {st.session_state['username']} ({st.session_state['role']})")
        st.markdown("---")
        menu = ["لوحة القيادة", "إضافة IR"]
        choice = st.radio("القائمة الرئيسية", menu)
        st.markdown("---")
        if st.button("تسجيل الخروج"):
            st.session_state.clear()
            st.rerun()

    # التوجيه للصفحات
    if choice == "لوحة القيادة":
        dashboard()
    elif choice == "إضافة IR":
        add_ir_page()

if __name__ == "__main__":
    main()
