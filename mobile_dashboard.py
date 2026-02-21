# mobile_dashboard.py
import streamlit as st
import pandas as pd
from supabase import create_client, Client
import datetime
import plotly.express as px
import re

# --- إعداد الصفحة ---
st.set_page_config(page_title="لوحة تحكم الإدارة", layout="wide", page_icon="📊")

# --- دوال التحقق من الدخول والخروج ---
def check_login(username, password):
    """
    تحقق من بيانات الدخول.
    في تطبيق حقيقي، يجب استخدام st.secrets لتخزين البيانات بشكل آمن.
    """
    try:
        # محاولة جلب البيانات من st.secrets
        correct_username = st.secrets["login"]["username"]
        correct_password = st.secrets["login"]["password"]
    except Exception:
        # قيم افتراضية في حال عدم إعداد الأسرار بعد (للتجربة المحلية)
        correct_username = "admin"
        correct_password = "password123"
    return username == correct_username and password == correct_password

def logout():
    st.session_state.logged_in = False
    st.rerun()

# --- إدارة حالة تسجيل الدخول ---
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

# --- عرض صفحة الدخول إذا لم يتم التسجيل ---
if not st.session_state.logged_in:
    st.title("🔒 تسجيل الدخول للوحة التحكم")
    username = st.text_input("اسم المستخدم")
    password = st.text_input("كلمة المرور", type="password")
    if st.button("دخول"):
        if check_login(username, password):
            st.session_state.logged_in = True
            st.rerun()
        else:
            st.error("اسم المستخدم أو كلمة المرور غير صحيحة")
    st.stop() # إيقاف تنفيذ باقي الكود

# --- الاتصال بـ Supabase ---
# نستخدم نفس البيانات الموجودة في supabase_manager.py
try:
    SUPABASE_URL = st.secrets["supabase"]["url"]
    SUPABASE_KEY = st.secrets["supabase"]["key"]
except Exception:
    SUPABASE_URL = None
    SUPABASE_KEY = None

if not SUPABASE_URL:
    SUPABASE_URL = "https://ivpqqxhacraagicjsytx.supabase.co"
if not SUPABASE_KEY:
    SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Iml2cHFxeGhhY3JhYWdpY2pzeXR4Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzE1MTQ2MzUsImV4cCI6MjA4NzA5MDYzNX0.sBfLk05QMtFflQIRSFEVqYit_j9HOkoIWjpKXYrOWLo"

# تنظيف البيانات من المسافات والأحرف غير الصالحة
if SUPABASE_URL:
    SUPABASE_URL = str(SUPABASE_URL).encode('ascii', 'ignore').decode('ascii').strip()
if SUPABASE_KEY:
    SUPABASE_KEY = str(SUPABASE_KEY).encode('ascii', 'ignore').decode('ascii').strip()

@st.cache_resource
def init_connection(url, key):
    try:
        return create_client(url, key)
    except Exception as e:
        st.error(f"فشل الاتصال بقاعدة البيانات: {e}")
        return None

supabase = init_connection(SUPABASE_URL, SUPABASE_KEY)

# --- دوال جلب البيانات ---
def get_sales_data():
    if not supabase: return pd.DataFrame()
    # جلب الفواتير (آخر 100 فاتورة مثلاً)
    response = supabase.table('invoices').select("*").order('created_at', desc=True).limit(500).execute()
    df = pd.DataFrame(response.data)
    if not df.empty:
        df['invoice_date'] = pd.to_datetime(df['invoice_date'])
        df['total_amount'] = pd.to_numeric(df['total_amount'])
    return df

def get_inventory_data():
    if not supabase: return pd.DataFrame()
    response = supabase.table('products').select("*").execute()
    df = pd.DataFrame(response.data)
    if not df.empty:
        df['quantity'] = pd.to_numeric(df['quantity'])
        df['selling_price'] = pd.to_numeric(df['selling_price'])
    return df

def get_user_sessions():
    if not supabase: return pd.DataFrame()
    try:
        response = supabase.table('user_sessions').select("*").order('login_time', desc=True).limit(100).execute()
        df = pd.DataFrame(response.data)
        if not df.empty:
            df['login_time'] = pd.to_datetime(df['login_time'])
            if 'logout_time' in df.columns:
                df['logout_time'] = pd.to_datetime(df['logout_time'])
        return df
    except Exception as e:
        return pd.DataFrame()

def get_cash_discrepancies():
    if not supabase: return pd.DataFrame()
    try:
        response = supabase.table('cash_discrepancies').select("*").order('timestamp', desc=True).limit(50).execute()
        df = pd.DataFrame(response.data)
        if not df.empty:
            df['timestamp'] = pd.to_datetime(df['timestamp'])
        return df
    except Exception as e:
        return pd.DataFrame()

# --- الواجهة الرئيسية ---
st.title("📱 متابعة حركة الفروع والمخزون")
st.markdown("---")

# القائمة الجانبية
st.sidebar.button("تسجيل الخروج", on_click=logout)
sidebar_option = st.sidebar.radio("القائمة", ["ملخص المبيعات", "حالة المخزون", "حركة الفروع", "نشاط المستخدمين", "تنبيهات الخزينة"])

if sidebar_option == "ملخص المبيعات":
    st.header("💰 ملخص المبيعات")
    if st.button("تحديث البيانات 🔄"):
        st.cache_data.clear()
    
    df_sales = get_sales_data()
    
    if not df_sales.empty:
        # مؤشرات سريعة
        total_sales = df_sales['total_amount'].sum()
        invoices_count = len(df_sales)
        
        col1, col2 = st.columns(2)
        col1.metric("إجمالي المبيعات (المعروضة)", f"{total_sales:,.2f} ج.م")
        col2.metric("عدد الفواتير", invoices_count)
        
        # رسم بياني للمبيعات
        st.subheader("تطور المبيعات")
        fig = px.bar(df_sales, x='invoice_date', y='total_amount', title="المبيعات حسب الوقت")
        st.plotly_chart(fig, use_container_width=True)
        
        # جدول البيانات
        st.subheader("آخر الفواتير")
        st.dataframe(df_sales[['reference_number', 'total_amount', 'invoice_date', 'branch_name']], use_container_width=True)
    else:
        st.info("لا توجد بيانات مبيعات مسجلة في السحابة حالياً.")

elif sidebar_option == "حالة المخزون":
    st.header("📦 حالة المخزون")
    if st.button("تحديث المخزون 🔄"):
        st.cache_data.clear()
        
    df_products = get_inventory_data()
    
    if not df_products.empty:
        # تنبيهات النواقص
        low_stock = df_products[df_products['quantity'] <= 5]
        if not low_stock.empty:
            st.error(f"⚠️ هناك {len(low_stock)} منتجات قاربت على النفاذ!")
            st.dataframe(low_stock[['name', 'quantity', 'branch_name']], use_container_width=True)
        
        # البحث
        search_term = st.text_input("بحث عن منتج:")
        if search_term:
            df_products = df_products[df_products['name'].str.contains(search_term, case=False)]
            
        st.dataframe(df_products[['name', 'quantity', 'selling_price', 'branch_name']], use_container_width=True)
    else:
        st.info("لا توجد منتجات مسجلة.")

elif sidebar_option == "حركة الفروع":
    st.header("🏢 أداء الفروع")
    df_sales = get_sales_data()
    
    if not df_sales.empty and 'branch_name' in df_sales.columns:
        branch_sales = df_sales.groupby('branch_name')['total_amount'].sum().reset_index()
        
        fig = px.pie(branch_sales, values='total_amount', names='branch_name', title="توزيع المبيعات على الفروع")
        st.plotly_chart(fig, use_container_width=True)
        
        st.table(branch_sales)
    else:
        st.warning("لا توجد بيانات كافية لتحليل الفروع.")

elif sidebar_option == "نشاط المستخدمين":
    st.header("👥 نشاط المستخدمين")
    if st.button("تحديث النشاط 🔄"):
        st.cache_data.clear()
    
    df_sessions = get_user_sessions()
    
    if not df_sessions.empty:
        # تنسيق العرض
        display_df = df_sessions.copy()
        
        # تنسيق التواريخ للعرض
        if 'login_time' in display_df.columns:
            display_df['login_time'] = display_df['login_time'].dt.strftime('%Y-%m-%d %H:%M:%S')
        
        if 'logout_time' in display_df.columns:
            display_df['logout_time'] = display_df['logout_time'].dt.strftime('%Y-%m-%d %H:%M:%S').fillna('نشط الآن')
        else:
            display_df['logout_time'] = 'نشط الآن'
        
        # إعادة تسمية الأعمدة للعربية
        rename_map = {
            'username': 'المستخدم',
            'login_time': 'وقت الدخول',
            'logout_time': 'وقت الخروج',
            'branch_name': 'الفرع'
        }
        display_df = display_df.rename(columns=rename_map)
        
        # اختيار الأعمدة للعرض
        cols_to_show = ['المستخدم', 'الفرع', 'وقت الدخول', 'وقت الخروج']
        cols_to_show = [c for c in cols_to_show if c in display_df.columns]
        
        st.dataframe(display_df[cols_to_show], use_container_width=True)
        
        # إحصائيات سريعة
        if 'وقت الخروج' in display_df.columns:
             active_users = display_df[display_df['وقت الخروج'] == 'نشط الآن'].shape[0]
             st.metric("المستخدمين النشطين حالياً", active_users)
        
    else:
        st.info("لا توجد سجلات نشاط للمستخدمين.")

elif sidebar_option == "تنبيهات الخزينة":
    st.header("🚨 تنبيهات عجز/زيادة الخزينة")
    if st.button("تحديث التنبيهات 🔄"):
        st.cache_data.clear()
    
    df_alerts = get_cash_discrepancies()
    
    if not df_alerts.empty:
        # تنسيق العرض
        display_df = df_alerts.copy()
        display_df['timestamp'] = display_df['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')
        
        # إعادة تسمية الأعمدة للعربية
        rename_map = {
            'username': 'المستخدم',
            'branch_name': 'الفرع',
            'timestamp': 'الوقت',
            'calculated_balance': 'الرصيد المتوقع',
            'actual_balance': 'الرصيد الفعلي',
            'difference': 'الفرق'
        }
        display_df = display_df.rename(columns=rename_map)
        
        # إضافة عمود الحالة (زيادة/عجز)
        def get_status(diff):
            if diff > 0: return "زيادة 🟢"
            elif diff < 0: return "عجز 🔴"
            return "متطابق"
        
        display_df['الحالة'] = display_df['الفرق'].apply(get_status)
        
        cols = ['المستخدم', 'الفرع', 'الوقت', 'الرصيد المتوقع', 'الرصيد الفعلي', 'الفرق', 'الحالة']
        st.dataframe(display_df[cols], use_container_width=True)
    else:
        st.success("لا توجد تنبيهات عجز أو زيادة مسجلة.")
