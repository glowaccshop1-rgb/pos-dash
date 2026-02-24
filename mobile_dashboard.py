
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
@st.cache_data(ttl=600) # Cache for 10 minutes
def get_sales_data(start_date, end_date):
    if not supabase: return pd.DataFrame()
    
    start_str = start_date.strftime('%Y-%m-%d')
    # Add one day to end_date to include the whole day in the query
    end_str = (end_date + datetime.timedelta(days=1)).strftime('%Y-%m-%d')

    try:
        response = supabase.table('invoices').select("*") \
            .gte('invoice_date', start_str) \
            .lt('invoice_date', end_str) \
            .order('created_at', desc=True).execute()
        df = pd.DataFrame(response.data)
        if not df.empty:
            df['invoice_date'] = pd.to_datetime(df['invoice_date'])
            df['total_amount'] = pd.to_numeric(df['total_amount'])
        return df
    except Exception as e:
        st.error(f"خطأ في جلب بيانات المبيعات: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=600)
def get_sold_products_data(start_date, end_date):
    """Fetches and aggregates sold products data within a date range."""
    if not supabase: return pd.DataFrame()

    start_str = start_date.strftime('%Y-%m-%d')
    end_str = (end_date + datetime.timedelta(days=1)).strftime('%Y-%m-%d')

    try:
        # Step 1: Get invoice IDs within the date range
        invoices_response = supabase.table('invoices').select("id") \
            .gte('invoice_date', start_str) \
            .lt('invoice_date', end_str).execute()
        invoice_ids = [inv['id'] for inv in invoices_response.data]

        if not invoice_ids:
            return pd.DataFrame()

        # Step 2: Get transaction items for those invoices
        items_response = supabase.table('transaction_items').select("product_name, product_barcode, quantity") \
            .in_('invoice_id', invoice_ids).execute()
        
        df_items = pd.DataFrame(items_response.data)
        
        if df_items.empty:
            return pd.DataFrame()

        # Step 3: Aggregate the data
        df_items['quantity'] = pd.to_numeric(df_items['quantity'])
        sold_products = df_items.groupby(['product_name', 'product_barcode']).agg(total_quantity=('quantity', 'sum')).reset_index()
        
        return sold_products.sort_values(by='total_quantity', ascending=False)

    except Exception as e:
        st.error(f"خطأ في جلب بيانات المنتجات المباعة: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=300) # Cache for 5 minutes
def get_leave_requests():
    """Fetches leave requests from the Supabase database."""
    if not supabase: return pd.DataFrame()
    try:
        response = supabase.table('employee_leaves').select("*").order('requested_at', desc=True).limit(200).execute()
        df = pd.DataFrame(response.data)
        if not df.empty and 'requested_at' in df.columns:
            df['requested_at'] = pd.to_datetime(df['requested_at']).dt.strftime('%Y-%m-%d %H:%M')
        return df
    except Exception as e:
        st.error(f"خطأ في جلب طلبات الإجازة: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=300)
def get_users_list():
    """Fetches unique usernames from user sessions history."""
    if not supabase: return []
    try:
        response = supabase.table('user_sessions').select('username').execute()
        # Get unique usernames and sort them
        users = sorted(list(set([item['username'] for item in response.data if item.get('username')])))
        return users
    except Exception:
        return []

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
sidebar_option = st.sidebar.radio("القائمة", ["ملخص المبيعات", "حالة المخزون", "المنتجات التي قاربت على الانتهاء", "طلبات الإجازات", "حركة الفروع", "نشاط المستخدمين", "تنبيهات الخزينة", "رسائل للمستخدمين"])

if sidebar_option == "ملخص المبيعات":
    st.header("💰 ملخص المبيعات")
    
    # Date filter
    col1, col2 = st.columns(2)
    start_date = col1.date_input("من تاريخ", datetime.date.today())
    end_date = col2.date_input("إلى تاريخ", datetime.date.today())

    if start_date > end_date:
        st.error("تاريخ البداية لا يمكن أن يكون بعد تاريخ النهاية.")
        st.stop()

    df_sales = get_sales_data(start_date, end_date)
    
    if not df_sales.empty:
        # مؤشرات سريعة
        total_sales = df_sales['total_amount'].sum()
        invoices_count = len(df_sales)
        
        col1, col2 = st.columns(2)
        col1.metric("إجمالي المبيعات (للفترة المحددة)", f"{total_sales:,.2f} ج.م")
        col2.metric("عدد الفواتير", invoices_count)
        
        # رسم بياني للمبيعات
        st.subheader("تطور المبيعات اليومي")
        daily_sales = df_sales.set_index('invoice_date').resample('D')['total_amount'].sum().reset_index()
        fig = px.bar(daily_sales, x='invoice_date', y='total_amount', title="المبيعات حسب اليوم")
        st.plotly_chart(fig, use_container_width=True)
        
        # عرض المنتجات المباعة
        with st.expander("📦 عرض المنتجات المباعة في الفترة المحددة"):
            df_sold_products = get_sold_products_data(start_date, end_date)
            if not df_sold_products.empty:
                st.dataframe(df_sold_products, use_container_width=True)
            else:
                st.info("لم يتم بيع أي منتجات في هذه الفترة.")

        # جدول البيانات
        st.subheader("آخر الفواتير في الفترة")
        st.dataframe(df_sales[['reference_number', 'total_amount', 'invoice_date', 'branch_name']], use_container_width=True)
    else:
        st.info("لا توجد بيانات مبيعات مسجلة في الفترة المحددة.")

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

elif sidebar_option == "المنتجات التي قاربت على الانتهاء":
    st.header("📉 المنتجات التي قاربت على الانتهاء")
    
    # السماح للمستخدم بتحديد حد النواقص
    low_stock_threshold = st.number_input("عرض المنتجات التي كميتها أقل من أو تساوي:", min_value=0, value=5, step=1)

    if st.button("تحديث البيانات 🔄"):
        st.cache_data.clear()
        
    df_products = get_inventory_data()
    
    if not df_products.empty:
        # فلترة المنتجات التي قاربت على النفاذ بناءً على الحد الذي أدخله المستخدم
        low_stock_products = df_products[df_products['quantity'] <= low_stock_threshold].sort_values(by='quantity')
        
        if not low_stock_products.empty:
            st.error(f"⚠️ هناك {len(low_stock_products)} منتجات قاربت على النفاذ (الكمية <= {low_stock_threshold})")
            # عرض الأعمدة المهمة
            st.dataframe(low_stock_products[['name', 'quantity', 'branch_name', 'selling_price']], use_container_width=True)
        else:
            st.success(f"✅ لا توجد منتجات كميتها أقل من أو تساوي {low_stock_threshold}.")
    else:
        st.info("لا توجد بيانات مخزون لعرضها.")

elif sidebar_option == "طلبات الإجازات":
    st.header("📅 طلبات الإجازات")
    if st.button("تحديث الطلبات 🔄"):
        st.cache_data.clear()

    df_leaves = get_leave_requests()

    if not df_leaves.empty:
        # Metrics
        pending_count = df_leaves[df_leaves['status'] == 'pending'].shape[0]
        approved_count = df_leaves[df_leaves['status'] == 'approved'].shape[0]
        
        col1, col2 = st.columns(2)
        col1.metric("طلبات قيد المراجعة", pending_count)
        col2.metric("طلبات موافق عليها", approved_count)

        # Filters
        st.subheader("فلترة الطلبات")
        all_branches = ['الكل'] + df_leaves['branch_name'].unique().tolist()
        all_statuses = ['الكل', 'pending', 'approved', 'rejected']

        f_col1, f_col2 = st.columns(2)
        selected_branch = f_col1.selectbox("اختر الفرع:", all_branches)
        selected_status = f_col2.selectbox("اختر الحالة:", all_statuses)

        # Apply filters
        filtered_df = df_leaves.copy()
        if selected_branch != 'الكل':
            filtered_df = filtered_df[filtered_df['branch_name'] == selected_branch]
        if selected_status != 'الكل':
            filtered_df = filtered_df[filtered_df['status'] == selected_status]

        # Display data
        st.dataframe(filtered_df[[
            'username', 'branch_name', 'leave_type', 'start_date', 'end_date', 
            'status', 'reason', 'requested_at', 'approver_username'
        ]].rename(columns={
            'username': 'الموظف', 'branch_name': 'الفرع', 'leave_type': 'نوع الإجازة',
            'start_date': 'من تاريخ', 'end_date': 'إلى تاريخ', 'status': 'الحالة',
            'reason': 'السبب', 'requested_at': 'تاريخ الطلب', 'approver_username': 'تم بواسطة'
        }), use_container_width=True)

    else:
        st.info("لا توجد طلبات إجازة مسجلة على السحابة.")

elif sidebar_option == "حركة الفروع":
    st.header("🏢 أداء الفروع")
    
    # Date filter for branch performance
    col1, col2 = st.columns(2)
    start_date_branch = col1.date_input("من تاريخ", datetime.date.today() - datetime.timedelta(days=7))
    end_date_branch = col2.date_input("إلى تاريخ", datetime.date.today())

    if start_date_branch > end_date_branch:
        st.error("تاريخ البداية لا يمكن أن يكون بعد تاريخ النهاية.")
        st.stop()

    df_sales = get_sales_data(start_date_branch, end_date_branch)
    
    if not df_sales.empty and 'branch_name' in df_sales.columns:
        branch_sales = df_sales.groupby('branch_name')['total_amount'].sum().reset_index()
        
        fig = px.pie(branch_sales, values='total_amount', names='branch_name', title="توزيع المبيعات على الفروع")
        st.plotly_chart(fig, use_container_width=True)
        st.table(branch_sales)
    else:
        st.warning("لا توجد بيانات كافية لتحليل الفروع في الفترة المحددة.")

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

elif sidebar_option == "رسائل للمستخدمين":
    st.header("📩 إرسال رسائل للمستخدمين")
    
    users_list = get_users_list()
    
    with st.form("send_message_form"):
        col1, col2 = st.columns([1, 2])
        with col1:
            selected_user = st.selectbox("اختر المستخدم:", users_list)
        with col2:
            message_text = st.text_input("نص الرسالة:", placeholder="اكتب رسالتك هنا...")
            
        submitted = st.form_submit_button("إرسال الرسالة 🚀")
        
        if submitted:
            if selected_user and message_text:
                try:
                    data = {
                        "username": selected_user,
                        "message": message_text,
                        "sender": "الإدارة",
                        "is_read": False,
                        "created_at": datetime.datetime.now().isoformat()
                    }
                    supabase.table('user_messages').insert(data).execute()
                    st.success(f"تم إرسال الرسالة إلى {selected_user} بنجاح!")
                except Exception as e:
                    st.error(f"حدث خطأ أثناء الإرسال: {e}")
            else:
                st.warning("الرجاء اختيار مستخدم وكتابة نص الرسالة.")

    st.divider()
    st.subheader("سجل الرسائل المرسلة (آخر 20)")
    try:
        msgs_response = supabase.table('user_messages').select("*").order('created_at', desc=True).limit(20).execute()
        df_msgs = pd.DataFrame(msgs_response.data)
        if not df_msgs.empty:
            st.dataframe(df_msgs[['username', 'message', 'is_read', 'created_at']], use_container_width=True)
    except Exception:
        st.info("لا توجد رسائل سابقة.")
