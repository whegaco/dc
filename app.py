import streamlit as st
import pandas as pd
import sqlite3
import bcrypt
import plotly.express as px
import re
from datetime import date, datetime
from io import BytesIO

# ==========================================
# 1. الإعدادات الأساسية
# ==========================================
st.set_page_config(page_title="IR Tracker Pro System", layout="wide")
DB_NAME = "ir_tracker.db"
DATA_SHEETS = ["STR", "ARCH", "ELEC", "MECH", "SURV"]

CODE_MAP = {
    "A": "Approved", "B": "Approved with notes", 
    "C": "Reject & Resubmit", "CC": "Not Resubmitted", 
    "D": "Rejected Final", "UR": "Under Review", "S": "Superseded"
}

# ==========================================
# 2. دوال قاعدة البيانات (Database Core)
# ==========================================
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # جدول المستخدمين
    c.execute('''CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password_hash BLOB, role TEXT)''')
    
    # جدول البيانات
    c.execute('''CREATE TABLE IF NOT EXISTS ir_logs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, sheet TEXT, reference TEXT, rev INTEGER,
                  element TEXT, location TEXT, description TEXT, code_action TEXT, sub_date TEXT, rec_date TEXT)''')
    
    # جدول سجل التتبع (الجديد)
    c.execute('''CREATE TABLE IF NOT EXISTS audit_logs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, action TEXT, target_ref TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    
    # إضافة المدير الافتراضي
    c.execute("SELECT * FROM users WHERE username='Dokdok'")
    if not c.fetchone():
        hashed_pw = bcrypt.hashpw("123456".encode('utf-8'), bcrypt.gensalt())
        c.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)", ("Dokdok", hashed_pw, "admin"))
    
    conn.commit()
    conn.close()

def log_action(username, action, target_ref):
    """دالة لتسجيل حركات المستخدمين في قاعدة البيانات"""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # استخدام التوقيت المحلي
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("INSERT INTO audit_logs (username, action, target_ref, timestamp) VALUES (?, ?, ?, ?)", 
              (username, action, target_ref, current_time))
    conn.commit()
    conn.close()

def verify_login(username, password):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT password_hash, role FROM users WHERE username=?", (username,))
    result = c.fetchone()
    conn.close()
    if result and bcrypt.checkpw(password.encode('utf-8'), result[0]):
        return result[1]
    return None

def extract_building(location):
    m = re.search(r'Building\s*:?\s*([A-Za-z0-9()\-_/ ]+)', str(location), re.IGNORECASE)
    return m.group(1).strip() if m else ""

def extract_zone(location):
    m = re.search(r'Zone\s*:?\s*([A-Za-z0-9\-_ ]+)', str(location), re.IGNORECASE)
    return m.group(1).strip() if m else ""

def load_data():
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT * FROM ir_logs", conn)
    conn.close()
    
    if df.empty:
        return df, df

    # معالجة البيانات
    df["sub_date"] = pd.to_datetime(df["sub_date"], errors="coerce")
    df["rec_date"] = pd.to_datetime(df["rec_date"], errors="coerce")
    df["Delay Days"] = (df["rec_date"] - df["sub_date"]).dt.days
    df["Delay Status"] = df["Delay Days"].apply(lambda x: "Pending" if pd.isna(x) else ("On Time" if x <= 2 else "Delayed"))
    df["Building"] = df["location"].apply(extract_building)
    df["Zone"] = df["location"].apply(extract_zone)
    df["Code Meaning"] = df["code_action"].map(CODE_MAP)

    # جلب أحدث مراجعة فقط
    latest_df = df.sort_values(["sheet", "reference", "rev", "id"], na_position="last").groupby(["sheet", "reference"], as_index=False).tail(1)
    
    # استبعاد الحالات الملغاة
    active_df = latest_df[latest_df["code_action"].astype(str).str.upper() != "S"].copy()
    
    return latest_df, active_df

def to_excel(df):
    """دالة مساعدة لتحويل البيانات إلى ملف إكسيل جاهز للتحميل"""
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Data')
    processed_data = output.getvalue()
    return processed_data

# ==========================================
# 3. صفحات التطبيق
# ==========================================
def dashboard(active_df):
    st.title("لوحة القيادة التفاعلية 📊")
    if active_df.empty:
        st.info("لا توجد بيانات لعرضها.")
        return

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("إجمالي الطلبات", len(active_df))
    c2.metric("معتمد (A/B)", len(active_df[active_df["code_action"].isin(["A", "B"])]))
    c3.metric("مرفوض (C / CC)", len(active_df[active_df["code_action"].isin(["C", "CC"])]))
    c4.metric("مرفوض نهائي (D)", len(active_df[active_df["code_action"] == "D"]))
    c5.metric("متأخر (Delayed)", len(active_df[active_df["Delay Status"] == "Delayed"]))

    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("الطلبات حسب القسم")
        fig1 = px.bar(active_df, x='sheet', color='sheet', text_auto=True)
        st.plotly_chart(fig1, use_container_width=True)
    with col2:
        st.subheader("توزيع الحالات (Code Actions)")
        fig2 = px.pie(active_df, names='code_action', hole=0.3)
        st.plotly_chart(fig2, use_container_width=True)

def add_ir_page(active_df):
    st.title("إضافة طلب فحص جديد (IR) ➕")
    with st.form("add_ir"):
        c1, c2, c3 = st.columns(3)
        with c1:
            sheet = st.selectbox("القسم (Sheet)", DATA_SHEETS)
            ref = st.text_input("رقم المرجع (Reference)")
            rev = st.number_input("REV", min_value=0, step=1)
        with c2:
            element = st.text_input("Element")
            zone = st.text_input("Zone", value="04")
            building = st.text_input("Building", value="VF-01")
        with c3:
            code = st.selectbox("Code Action", ["A", "B", "C", "CC", "D", "UR"])
            sub_date = st.date_input("تاريخ التسليم", value=date.today())
            rec_date = st.date_input("تاريخ الاستلام", value=date.today())
        
        desc = st.text_area("Description")
        submit = st.form_submit_button("إضافة لقاعدة البيانات")

        if submit:
            if not ref.strip():
                st.error("رقم المرجع مطلوب!")
                return
            
            exists = active_df["reference"].dropna().astype(str).str.upper().eq(ref.strip().upper()).any()
            if exists:
                st.error("هذا المرجع موجود مسبقاً! استخدم صفحة 'تحديث' لإضافة مراجعة جديدة.")
                return
            
            location_str = f"Zone: {zone}\nBuilding: {building}"
            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()
            c.execute('''INSERT INTO ir_logs (sheet, reference, rev, element, location, description, code_action, sub_date, rec_date) 
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                      (sheet, ref.strip(), rev, element, location_str, desc, code, str(sub_date), str(rec_date)))
            conn.commit()
            conn.close()
            
            # تسجيل الحركة في النظام
            log_action(st.session_state["username"], f"إضافة طلب جديد", ref.strip())
            
            st.success(f"تمت الإضافة بنجاح: {ref}")
            st.rerun()

def update_ir_page(active_df):
    st.title("تحديث طلب فحص (Update IR) 🔄")
    refs = active_df["reference"].dropna().astype(str).sort_values().tolist()
    selected_ref = st.selectbox("اختر المرجع لتحديثه", refs)
    
    if selected_ref:
        row = active_df[active_df["reference"] == selected_ref].iloc[0]
        st.write("البيانات الحالية:")
        st.dataframe(pd.DataFrame([row[["reference", "rev", "code_action", "Building", "description"]]]), hide_index=True)

        with st.form("update_ir"):
            c1, c2, c3 = st.columns(3)
            with c1:
                new_rev = st.number_input("REV الجديد", min_value=int(row["rev"] if pd.notna(row["rev"]) else 0), step=1)
            with c2:
                new_code = st.selectbox("Code Action الجديد", ["A", "B", "C", "CC", "D", "UR"], index=["A", "B", "C", "CC", "D", "UR"].index(row["code_action"]) if row["code_action"] in ["A", "B", "C", "CC", "D", "UR"] else 5)
            with c3:
                new_rec_date = st.date_input("تاريخ الاستلام الجديد")
            
            new_desc = st.text_area("الوصف (Description)", value=str(row["description"] if pd.notna(row["description"]) else ""))
            submit = st.form_submit_button("حفظ التعديلات")
            
            if submit:
                conn = sqlite3.connect(DB_NAME)
                c = conn.cursor()
                c.execute('''UPDATE ir_logs SET rev=?, code_action=?, rec_date=?, description=? WHERE id=?''',
                          (new_rev, new_code, str(new_rec_date), new_desc, int(row["id"])))
                conn.commit()
                conn.close()
                
                # تسجيل الحركة في النظام
                log_action(st.session_state["username"], f"تحديث المراجعة إلى {new_rev} والحالة إلى {new_code}", selected_ref)
                
                st.success("تم تحديث البيانات بنجاح!")
                st.rerun()

def reminder_page(active_df):
    st.title("المتابعة والتذكير ⏰")
    pending = active_df[(active_df["Delay Status"] == "Delayed") | (active_df["code_action"].isin(["UR", "C", "CC"]))]
    st.metric("طلبات تحتاج متابعة", len(pending))
    show_cols = ["sheet", "reference", "rev", "Building", "description", "sub_date", "rec_date", "Delay Days", "Delay Status", "code_action"]
    st.dataframe(pending[show_cols], use_container_width=True, hide_index=True)

    if not pending.empty:
        # زر تحميل إكسيل
        excel_data = to_excel(pending[show_cols])
        st.download_button(label="📥 تحميل التقرير (Excel)", data=excel_data, file_name="Followup_List.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

def search_page(active_df):
    st.title("البحث المتقدم 🔍")
    c1, c2, c3, c4 = st.columns(4)
    ref = c1.text_input("بحث بالمرجع (Reference)")
    bld = c2.text_input("بحث بالمبنى (Building)")
    sht = c3.selectbox("القسم", [""] + DATA_SHEETS)
    cod = c4.selectbox("الكود", ["", "A", "B", "C", "CC", "D", "UR"])
    
    result = active_df.copy()
    if ref: result = result[result["reference"].astype(str).str.contains(ref, case=False, na=False)]
    if bld: result = result[result["Building"].astype(str).str.contains(bld, case=False, na=False)]
    if sht: result = result[result["sheet"] == sht]
    if cod: result = result[result["code_action"] == cod]
    
    st.write(f"نتائج البحث: {len(result)}")
    show_cols = ["sheet", "reference", "rev", "Building", "description", "sub_date", "rec_date", "Delay Status", "code_action"]
    st.dataframe(result[show_cols], use_container_width=True, hide_index=True)
    
    if not result.empty:
        # زر تحميل إكسيل لنتائج البحث
        excel_data = to_excel(result[show_cols])
        st.download_button(label="📥 تحميل نتائج البحث (Excel)", data=excel_data, file_name="Search_Results.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

def audit_log_page():
    st.title("سجل حركات النظام 🕵️‍♂️")
    st.markdown("تتيح لك هذه الصفحة مراقبة كل الإضافات والتعديلات التي قام بها المستخدمون.")
    conn = sqlite3.connect(DB_NAME)
    df_audit = pd.read_sql_query("SELECT * FROM audit_logs ORDER BY timestamp DESC", conn)
    conn.close()
    
    if df_audit.empty:
        st.info("لا توجد حركات مسجلة حتى الآن.")
    else:
        st.dataframe(df_audit[["timestamp", "username", "action", "target_ref"]], use_container_width=True, hide_index=True)

def manage_users_page():
    st.title("إدارة المستخدمين 👥")
    conn = sqlite3.connect(DB_NAME)
    df_users = pd.read_sql_query("SELECT username, role FROM users", conn)
    st.dataframe(df_users, hide_index=True)
    
    with st.form("add_user"):
        st.subheader("إضافة مشاهد جديد (Viewer)")
        n_user = st.text_input("اسم المستخدم")
        n_pass = st.text_input("كلمة المرور", type="password")
        if st.form_submit_button("إضافة"):
            if n_user and n_pass:
                hashed = bcrypt.hashpw(n_pass.encode('utf-8'), bcrypt.gensalt())
                try:
                    c = conn.cursor()
                    c.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)", (n_user.strip(), hashed, "viewer"))
                    conn.commit()
                    log_action(st.session_state["username"], f"إضافة مستخدم جديد", n_user.strip())
                    st.success("تم الإضافة بنجاح")
                    st.rerun()
                except:
                    st.error("اسم المستخدم موجود بالفعل!")
            else:
                st.error("الرجاء إدخال البيانات كاملة.")
    conn.close()

# ==========================================
# 4. محرك التطبيق الرئيسي
# ==========================================
def main():
    init_db()
    if not st.session_state.get("logged_in", False):
        st.title("IR Tracker Pro 🔐")
        with st.form("login_form"):
            u = st.text_input("اسم المستخدم")
            p = st.text_input("كلمة المرور", type="password")
            if st.form_submit_button("دخول"):
                role = verify_login(u.strip(), p)
                if role:
                    st.session_state.update({"logged_in": True, "username": u.strip(), "role": role})
                    # تسجيل الدخول في السجل
                    log_action(u.strip(), "تسجيل دخول للنظام", "N/A")
                    st.rerun()
                else:
                    st.error("بيانات الدخول خاطئة!")
        return

    # تحميل البيانات
    latest_df, active_df = load_data()
    role = st.session_state["role"]

    with st.sidebar:
        st.title("اللوحة الجانبية")
        st.caption(f"المستخدم: {st.session_state['username']} ({role})")
        
        pages = ["لوحة القيادة", "المتابعة والتذكير", "البحث المتقدم"]
        if role == "admin":
            pages = ["لوحة القيادة", "إضافة IR", "تحديث IR", "المتابعة والتذكير", "البحث المتقدم", "إدارة المستخدمين", "سجل حركات النظام"]
            
        choice = st.radio("القائمة", pages)
        st.markdown("---")
        if st.button("تسجيل خروج"):
            log_action(st.session_state["username"], "تسجيل خروج", "N/A")
            st.session_state.clear()
            st.rerun()

    # التوجيه
    if choice == "لوحة القيادة": dashboard(active_df)
    elif choice == "إضافة IR": add_ir_page(active_df)
    elif choice == "تحديث IR": update_ir_page(active_df)
    elif choice == "المتابعة والتذكير": reminder_page(active_df)
    elif choice == "البحث المتقدم": search_page(active_df)
    elif choice == "إدارة المستخدمين": manage_users_page()
    elif choice == "سجل حركات النظام" and role == "admin": audit_log_page()

if __name__ == "__main__":
    main()
