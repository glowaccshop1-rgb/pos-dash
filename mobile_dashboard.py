# mobile_dashboard.py
import streamlit as st
import pandas as pd
from supabase import create_client, Client
import datetime
import plotly.express as px
import re
import time

# --- إعداد الصفحة ---
st.set_page_config(page_title="لوحة تحكم الإدارة", layout="wide", page_icon="📊")

# --- CSS for RTL support ---
st.markdown("""
    <style>
    /* General RTL settings */
    .main, .stSidebar {
        direction: rtl;
        text-align: right;
    }
    /* Ensure all inputs and selects are RTL */
    .stTextInput, .stNumberInput, .stSelectbox, .stDateInput, .stTextArea, .stMultiSelect {
        direction: rtl;
    }
    /* Align labels to the right */
    div[data-testid="stMarkdownContainer"] p, div[data-testid="stMetric"], div[data-testid="stText"] {
        text-align: right;
    }
    label {
        text-align: right !important;
        display: block;
        width: 100%;
    }
    </style>
""", unsafe_allow_html=True)

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

if not supabase:
    st.error("❌ فشل الاتصال بقاعدة البيانات. يرجى التحقق من بيانات الاتصال.")
    st.stop()

@st.cache_data(ttl=600)
def get_branches_list():
    """Fetches unique branch names from branches table and active history."""
    if not supabase: return ["الكل"]
    
    found_branches = set()
    
    # 1. المحاولة الأولى: جلب الفروع من جدول الفروع المخصص
    try:
        response = supabase.table('branches').select("name").execute()
        for item in response.data:
            if item.get('name'):
                found_branches.add(item['name'])
    except Exception:
        pass

    # 2. المحاولة الثانية: استكشاف الفروع من سجل دخول المستخدمين (لضمان ظهور الفروع النشطة)
    try:
        response = supabase.table('user_sessions').select("branch_name").order('login_time', desc=True).limit(100).execute()
        for item in response.data:
            if item.get('branch_name'):
                found_branches.add(item['branch_name'])
    except Exception:
        pass

    # ترتيب القائمة وإضافة خيار الكل
    branches = ["الكل"] + sorted(list(found_branches))
    return branches

# --- دوال جلب البيانات ---
@st.cache_data(ttl=600) # Cache for 10 minutes
def get_sales_data(start_date, end_date, branch_name=None):
    if not supabase: return pd.DataFrame()
    
    start_str = start_date.strftime('%Y-%m-%d')
    # Add one day to end_date to include the whole day in the query
    end_str = (end_date + datetime.timedelta(days=1)).strftime('%Y-%m-%d')

    try:
        query = supabase.table('invoices').select("*", count='exact') \
            .gte('invoice_date', start_str) \
            .lt('invoice_date', end_str)

        if branch_name and branch_name != "الكل":
            query = query.eq('branch_name', branch_name)

        response = query.order('created_at', desc=True).execute()
        df = pd.DataFrame(response.data)
        if not df.empty:
            # Filter out returns manually in Python to avoid API filter issues
            if 'transaction_type' in df.columns:
                df = df[df['transaction_type'] != 'return']
            
            # منع تكرار الفواتير في العرض لضمان صحة الإجماليات
            if 'reference_number' in df.columns and 'branch_name' in df.columns:
                df = df.drop_duplicates(subset=['reference_number', 'branch_name'])
            
            df['invoice_date'] = pd.to_datetime(df['invoice_date'])
            df['total_amount'] = pd.to_numeric(df['total_amount'])
        return df
    except Exception as e:
        st.error(f"خطأ في جلب بيانات المبيعات: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=600)
def get_sold_products_data(start_date, end_date, branch_name=None):
    """Fetches and aggregates sold products data within a date range."""
    if not supabase: return pd.DataFrame()

    start_str = start_date.strftime('%Y-%m-%d')
    end_str = (end_date + datetime.timedelta(days=1)).strftime('%Y-%m-%d')

    try:
        # Step 1: Get invoice IDs within the date range
        query = supabase.table('invoices').select("id, reference_number, branch_name, transaction_type", count='exact') \
            .gte('invoice_date', start_str) \
            .lt('invoice_date', end_str)

        if branch_name and branch_name != "الكل":
            query = query.eq('branch_name', branch_name)

        invoices_response = query.execute()

        # Filter invoices manually and handle potential duplicates in the database
        df_inv = pd.DataFrame(invoices_response.data)
        if df_inv.empty:
            return pd.DataFrame()
        
        # استبعاد المرتجعات ومنع تكرار الفواتير
        df_inv = df_inv[df_inv['transaction_type'] != 'return']
        if 'reference_number' in df_inv.columns and 'branch_name' in df_inv.columns:
            df_inv = df_inv.drop_duplicates(subset=['reference_number', 'branch_name'])
            
        invoice_ids = df_inv['id'].tolist()

        if not invoice_ids:
            return pd.DataFrame()
        
        # Step 2: Get transaction items for those invoices
        # Chunking invoice_ids to avoid URL length limit errors
        chunk_size = 50
        all_items = []
        for i in range(0, len(invoice_ids), chunk_size):
            chunk = invoice_ids[i:i + chunk_size]
            items_response = supabase.table('transaction_items').select("product_name, product_barcode, quantity, transaction_type") \
                .in_('invoice_id', chunk) \
                .execute()
            all_items.extend(items_response.data)
        
        df_items = pd.DataFrame(all_items)
        
        # Filter items manually
        if not df_items.empty and 'transaction_type' in df_items.columns:
            df_items = df_items[df_items['transaction_type'] != 'return']
            
        if df_items.empty:
            return pd.DataFrame()

        # Step 3: Aggregate the data
        df_items['quantity'] = pd.to_numeric(df_items['quantity'])
        sold_products = df_items.groupby(['product_name', 'product_barcode']).agg(total_quantity=('quantity', 'sum')).reset_index()
        
        return sold_products.sort_values(by='total_quantity', ascending=False)

    except Exception as e:
        st.error(f"خطأ في جلب بيانات المنتجات المباعة: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=300)
def get_leave_requests(branch_name=None):
    """Fetches leave requests from the Supabase database."""
    if not supabase: return pd.DataFrame()
    try:
        query = supabase.table('employee_leaves').select("*").order('requested_at', desc=True).limit(200)
        
        if branch_name and branch_name != "الكل":
            query = query.eq('branch_name', branch_name)
            
        response = query.execute()
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

def get_inventory_data(branch_name=None):
    if not supabase: return pd.DataFrame()
    try:
        query = supabase.table('products').select("name, quantity, selling_price, branch_name, barcode")

        if branch_name and branch_name != "الكل":
            query = query.eq('branch_name', branch_name)

        response = query.execute()
        df = pd.DataFrame(response.data)
        if not df.empty:
            df['quantity'] = pd.to_numeric(df['quantity'], errors='coerce').fillna(0)
            df['selling_price'] = pd.to_numeric(df['selling_price'], errors='coerce').fillna(0.0)
            
            # تجميع الكميات للمنتجات المكررة في نفس الفرع لضمان دقة الأعداد
            if 'barcode' in df.columns and 'branch_name' in df.columns:
                df = df.groupby(['barcode', 'branch_name'], as_index=False).agg({
                    'name': 'first',
                    'quantity': 'sum',
                    'selling_price': 'first'
                })
        return df
    except Exception as e:
        st.error(f"خطأ في جلب بيانات المخزون: {e}")
        return pd.DataFrame()

def get_user_sessions(branch_name=None):
    if not supabase: return pd.DataFrame()
    try:
        query = supabase.table('user_sessions').select("*").order('login_time', desc=True).limit(100)
        
        if branch_name and branch_name != "الكل":
            query = query.eq('branch_name', branch_name)
            
        response = query.execute()
        df = pd.DataFrame(response.data)
        if not df.empty:
            df['login_time'] = pd.to_datetime(df['login_time'])
            if 'logout_time' in df.columns:
                df['logout_time'] = pd.to_datetime(df['logout_time'])
        return df
    except Exception as e:
        return pd.DataFrame()

def get_cash_discrepancies(branch_name=None):
    if not supabase: return pd.DataFrame()
    try:
        query = supabase.table('cash_discrepancies').select("*").order('timestamp', desc=True).limit(50)
        
        if branch_name and branch_name != "الكل":
            query = query.eq('branch_name', branch_name)
            
        response = query.execute()
        df = pd.DataFrame(response.data)
        if not df.empty:
            df['timestamp'] = pd.to_datetime(df['timestamp'])
        return df
    except Exception as e:
        return pd.DataFrame()

@st.cache_data(ttl=300)
def get_discounts_data():
    """Fetches all discounts from the Supabase database."""
    if not supabase: return pd.DataFrame()
    try:
        response = supabase.table('discounts').select("*").execute()
        return pd.DataFrame(response.data)
    except Exception as e:
        if "PGRST205" in str(e):
            st.warning("⚠️ جدول الخصومات (discounts) غير موجود في Supabase. يرجى تشغيل ملف SQL المرفق لإنشائه.")
            return pd.DataFrame()
        st.error(f"خطأ في جلب بيانات الخصومات: {e}")
        return pd.DataFrame()

def get_discount_branches(discount_name):
    """Fetches branch names where a specific discount is applicable."""
    if not supabase: return []
    try:
        response = supabase.table('discount_branch_applicability').select("branch_name").eq("discount_name", discount_name).execute()
        return [b['branch_name'] for b in response.data]
    except Exception:
        return []

def update_discount_branches(discount_name, branch_names):
    """Updates the branch applicability for a specific discount."""
    if not supabase: return False
    try:
        # Delete existing mappings
        supabase.table('discount_branch_applicability').delete().eq("discount_name", discount_name).execute()
        
        # Insert new mappings
        if branch_names:
            data = [{"discount_name": discount_name, "branch_name": b} for b in branch_names]
            supabase.table('discount_branch_applicability').insert(data).execute()
        return True
    except Exception as e:
        st.error(f"خطأ في تحديث فروع الخصم: {e}")
        if "PGRST205" in str(e):
            st.error("⚠️ جدول صلاحيات الفروع (discount_branch_applicability) غير موجود في Supabase.")
        else:
            st.error(f"خطأ في تحديث فروع الخصم: {e}")
        return False

def get_discount_products(discount_name):
    """Fetches product barcodes where a specific discount is applicable."""
    if not supabase: return []
    try:
        response = supabase.table('discount_product_applicability').select("product_barcode, product_name").eq("discount_name", discount_name).execute()
        return [(p['product_barcode'], p['product_name']) for p in response.data]
    except Exception:
        return []

def get_all_products():
    """Fetches all products from the products table."""
    if not supabase: return []
    try:
        response = supabase.table('products').select("barcode, name").execute()
        return [(p['barcode'], p['name']) for p in response.data]
    except Exception:
        return []

def add_product_to_db(data):
    """إضافة المنتج لقاعدة البيانات مع دعم upsert"""
    if not supabase: return False, "No Supabase connection"
    try:
        # Use upsert to update if exists, or insert if new
        # The composite primary key is usually (barcode, branch_name)
        response = supabase.table('products').upsert(data, on_conflict='barcode, branch_name').execute()
        
        # Check for errors in response (works for supabase-py v1 and v2)
        if hasattr(response, 'error') and response.error:
            return False, str(response.error)
        
        # For some errors, the data might be empty and an error is in the response object itself
        if not response.data and (hasattr(response, 'status_code') and response.status_code >= 400):
             # Try to parse a more specific message if available
             try:
                 error_details = response.json()
                 message = error_details.get('message', 'Unknown error')
                 return False, f"Error: {message}"
             except:
                 return False, f"Error {response.status_code}: Unknown error from server."

        return True, response.data
    except Exception as e:
        return False, str(e)

def update_discount_products(discount_name, products_list):
    """Updates the product applicability for a specific discount."""
    if not supabase: return False
    try:
        # Delete existing mappings
        supabase.table('discount_product_applicability').delete().eq("discount_name", discount_name).execute()
        
        # Insert new mappings
        if products_list:
            data = [{"discount_name": discount_name, "product_barcode": barcode, "product_name": name} for barcode, name in products_list]
            supabase.table('discount_product_applicability').insert(data).execute()
        return True
    except Exception as e:
        st.error(f"خطأ في تحديث منتجات الخصم: {e}")
        if "PGRST205" in str(e):
            st.error("⚠️ جدول صلاحيات المنتجات (discount_product_applicability) غير موجود في Supabase. يرجى تشغيل ملف SQL جديد.")
        return False

def update_product_quantity(barcode, branch_name, new_quantity):
    """Updates product quantity in Supabase, handling duplicates."""
    if not supabase: return False
    try:
        # Fetch rows to handle duplicates
        response = supabase.table('products').select("id").eq('barcode', barcode).eq('branch_name', branch_name).execute()
        rows = response.data
        
        if not rows:
            return False
            
        # Update the first row
        first_id = rows[0]['id']
        supabase.table('products').update({'quantity': new_quantity}).eq('id', first_id).execute()
        
        # Delete duplicates if any (cleaning up data)
        if len(rows) > 1:
            for row in rows[1:]:
                supabase.table('products').delete().eq('id', row['id']).execute()
                
        return True
    except Exception as e:
        st.error(f"خطأ في تحديث المنتج {barcode}: {e}")
        return False

# --- الواجهة الرئيسية ---
st.title("📱 متابعة حركة الفروع والمخزون")
st.markdown("---")

# القائمة الجانبية
st.sidebar.button("تسجيل الخروج", on_click=logout)

branches = get_branches_list()
if not branches or branches == ["الكل"]:
    branches = ["الكل"]
selected_branch = st.sidebar.selectbox("اختر الفرع:", branches)

if st.sidebar.button("🔄 تحديث جميع البيانات"):
    st.cache_data.clear()
    st.rerun()

sidebar_option = st.sidebar.radio("القائمة", ["ملخص المبيعات", "حالة المخزون", "إضافة منتج جديد", "المنتجات التي قاربت على الانتهاء", "طلبات الإجازات", "حركة الفروع", "نشاط المستخدمين", "تنبيهات الخزينة", "رسائل للمستخدمين", "الخصومات والعروض"])

if sidebar_option == "ملخص المبيعات":
    st.header("💰 ملخص المبيعات")
    
    # Date filter
    col1, col2 = st.columns(2)
    start_date = col1.date_input("من تاريخ", datetime.date.today())
    end_date = col2.date_input("إلى تاريخ", datetime.date.today())

    if start_date > end_date:
        st.error("تاريخ البداية لا يمكن أن يكون بعد تاريخ النهاية.")
        st.stop()

    df_sales = get_sales_data(start_date, end_date, selected_branch)
    
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
            df_sold_products = get_sold_products_data(start_date, end_date, selected_branch)
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
        st.rerun()
        
    df_products = get_inventory_data(selected_branch)
    
    if not df_products.empty:
        # تنبيهات النواقص
        low_stock = df_products[df_products['quantity'] <= 5]
        if not low_stock.empty:
            st.error(f"⚠️ هناك {len(low_stock)} منتجات قاربت على النفاذ!")
            st.dataframe(low_stock[['name', 'quantity', 'branch_name']], use_container_width=True)
        
        # البحث
        search_term = st.text_input("بحث عن منتج (الاسم أو الباركود):")
        df_display = df_products.copy()
        if search_term:
            df_display = df_display[
                df_display['name'].str.contains(search_term, case=False, na=False) |
                df_display['barcode'].astype(str).str.contains(search_term, case=False, na=False)
            ]
            
        # Reorder columns for editor
        cols = ['name', 'quantity', 'selling_price', 'branch_name', 'barcode']
        # Ensure columns exist
        cols = [c for c in cols if c in df_display.columns]
        df_display = df_display[cols]

        st.caption("يمكنك تعديل الكميات في الجدول أدناه ثم الضغط على 'حفظ التعديلات'.")
        
        edited_df = st.data_editor(
            df_display,
            use_container_width=True,
            column_config={
                "name": st.column_config.TextColumn("اسم المنتج", disabled=True),
                "quantity": st.column_config.NumberColumn("الكمية", min_value=0, step=1, required=True),
                "selling_price": st.column_config.NumberColumn("سعر البيع", disabled=True),
                "branch_name": st.column_config.TextColumn("الفرع", disabled=True),
                "barcode": st.column_config.TextColumn("الباركود", disabled=True),
            },
            disabled=["name", "selling_price", "branch_name", "barcode"],
            hide_index=True,
            key="inventory_editor"
        )

        if st.button("حفظ التعديلات 💾", type="primary"):
            updated_count = 0
            with st.spinner("جاري حفظ التعديلات..."):
                for index, row in edited_df.iterrows():
                    barcode = row['barcode']
                    branch = row['branch_name']
                    new_qty = row['quantity']
                    
                    # Find original quantity to compare
                    original_rows = df_products[
                        (df_products['barcode'] == barcode) & 
                        (df_products['branch_name'] == branch)
                    ]
                    
                    if not original_rows.empty:
                        old_qty = original_rows.iloc[0]['quantity']
                        if new_qty != old_qty:
                            if update_product_quantity(barcode, branch, new_qty):
                                updated_count += 1
            
            if updated_count > 0:
                st.success(f"تم تحديث {updated_count} منتجات بنجاح!")
                time.sleep(1)
                st.cache_data.clear()
                st.rerun()
            else:
                st.info("لم يتم إجراء أي تغييرات.")
    else:
        st.info("لا توجد منتجات مسجلة.")

elif sidebar_option == "إضافة منتج جديد":
    st.header("📦 إضافة منتج جديد")
    st.markdown("---")

    # Use the existing get_branches_list function
    all_branches = get_branches_list()
    # Remove "الكل" option as it's not a valid branch to add to
    if "الكل" in all_branches:
        all_branches.remove("الكل")

    # If a specific branch is selected in the sidebar, default to it
    default_branch_index = 0
    if selected_branch != "الكل" and selected_branch in all_branches:
        try:
            default_branch_index = all_branches.index(selected_branch)
        except ValueError:
            default_branch_index = 0 # Fallback

    with st.form("product_form", clear_on_submit=True):
        st.subheader("📍 بيانات الفرع والمنتج الأساسية")
        
        col1, col2 = st.columns(2)
        with col1:
            branch_to_add = st.selectbox("اختر الفرع لإضافة المنتج إليه:", all_branches, index=default_branch_index)
        with col2:
            barcode = st.text_input("الباركود *")

        name = st.text_input("اسم المنتج *")
        product_type = st.text_input("نوع المنتج")
        supplier = st.text_input("المورد")
        
        st.markdown("---")
        st.subheader("💰 الأسعار والتكلفة")
        
        c1, c2 = st.columns(2)
        with c1:
            cost_price = st.number_input("سعر التكلفة", min_value=0.0, step=0.5, format="%.2f")
        with c2:
            selling_price = st.number_input("سعر البيع", min_value=0.0, step=0.5, format="%.2f")
            
        st.markdown("---")
        st.subheader("🔢 المخزون")
        
        q1, q2 = st.columns(2)
        with q1:
            quantity = st.number_input("الكمية الحالية", min_value=0, step=1)
        with q2:
            alert_limit = st.number_input("حد التنبيه (Alert Limit)", min_value=0, step=1, value=5)
            
        st.markdown("---")
        st.subheader("🏷️ الخصومات")
        
        d1, d2 = st.columns(2)
        with d1:
            discount_amount = st.number_input("مبلغ الخصم", min_value=0.0, step=0.5, format="%.2f")
        
        d3, d4 = st.columns(2)
        with d3:
            discount_start = st.date_input("تاريخ بداية الخصم", value=None)
        with d4:
            discount_end = st.date_input("تاريخ نهاية الخصم", value=None)

        st.markdown("**خصم الكمية**")
        qd1, qd2 = st.columns(2)
        with qd1:
            quantity_discount_threshold = st.number_input("الكمية المطلوبة للخصم", min_value=0, step=1)
        with qd2:
            quantity_discount_amount = st.number_input("خصم القطعة الواحدة", min_value=0.0, step=0.5, format="%.2f")

        st.markdown("<br>", unsafe_allow_html=True)
        
        submitted = st.form_submit_button("➕ حفظ المنتج في المخزون")
        
        if submitted:
            if not barcode or not name:
                st.error("⚠️ يجب إدخال الباركود واسم المنتج.")
            else:
                # حساب الربح والسعر بعد الخصم
                profit = selling_price - cost_price
                discounted_price = selling_price - discount_amount if discount_amount else selling_price

                product_data = { 
                    "barcode": barcode, 
                    "name": name, 
                    "branch_name": branch_to_add, 
                    "cost_price": cost_price, 
                    "selling_price": selling_price, 
                    "quantity": quantity, 
                    "alert_limit": alert_limit, 
                    "supplier": supplier,
                    "discount_amount": discount_amount,
                    "discount_start": str(discount_start) if discount_start else None,
                    "discount_end": str(discount_end) if discount_end else None,
                    "quantity_discount_threshold": quantity_discount_threshold,
                    "quantity_discount_amount": quantity_discount_amount,
                    "profit": profit,
                    "discounted_price": discounted_price,
                    "created_at": datetime.datetime.now().isoformat() 
                }
                
                with st.spinner('جاري حفظ المنتج في السحابة...'):
                    success, result = add_product_to_db(product_data)
                
                if success:
                    st.success(f"✅ تم حفظ المنتج '{name}' بنجاح في فرع '{branch_to_add}'!")
                    st.balloons()
                    st.cache_data.clear()
                else:
                    st.error(f"❌ حدث خطأ أثناء الحفظ: {result}")

elif sidebar_option == "المنتجات التي قاربت على الانتهاء":
    st.header("📉 المنتجات التي قاربت على الانتهاء")
    
    # السماح للمستخدم بتحديد حد النواقص
    low_stock_threshold = st.number_input("عرض المنتجات التي كميتها أقل من أو تساوي:", min_value=0, value=5, step=1)

    if st.button("تحديث البيانات 🔄"):
        st.cache_data.clear()
        
    df_products = get_inventory_data(selected_branch)
    
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

    df_leaves = get_leave_requests(selected_branch)

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
    
    df_sessions = get_user_sessions(selected_branch)
    
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
    
    df_alerts = get_cash_discrepancies(selected_branch)
    
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

elif sidebar_option == "الخصومات والعروض":
    st.header("🎟️ إدارة الخصومات والعروض")
    
    if st.button("تحديث البيانات 🔄"):
        st.cache_data.clear()
        
    df_discounts = get_discounts_data()
    branches = get_branches_list()
    
    if not df_discounts.empty:
        st.subheader("قائمة الخصومات الحالية")
        
        # Display discounts table
        display_df = df_discounts.copy()
        # Rename columns for display
        rename_map = {
            'name': 'اسم الخصم',
            'value': 'القيمة',
            'value_type': 'نوع القيمة',
            'discount_type': 'نوع الخصم',
            'start_date': 'تاريخ البدء',
            'end_date': 'تاريخ الانتهاء'
        }
        display_df = display_df.rename(columns=rename_map)
        
        cols_to_show = ['اسم الخصم', 'القيمة', 'نوع القيمة', 'نوع الخصم', 'تاريخ البدء', 'تاريخ الانتهاء']
        cols_to_show = [c for c in cols_to_show if c in display_df.columns]
        
        st.dataframe(display_df[cols_to_show], use_container_width=True)
        
        st.divider()
        st.subheader("⚙️ تخصيص الخصومات للفروع والمنتجات")
        
        selected_discount = st.selectbox("اختر الخصم لتعديل تطبيقه:", df_discounts['name'].tolist())
        
        if selected_discount:
            current_discount_branches = get_discount_branches(selected_discount)
            current_discount_products = get_discount_products(selected_discount)
            all_products = get_all_products()
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.write(f"**تحديد الفروع** - {selected_discount}")
                selected_branches = st.multiselect(
                    "اختر الفروع:",
                    options=branches,
                    default=[b for b in current_discount_branches if b in branches],
                    key="discount_branches"
                )
            
            with col2:
                st.write(f"**تحديد المنتجات** - {selected_discount}")
                product_options = {f"{name} ({barcode})": (barcode, name) for barcode, name in all_products}
                default_products = [f"{name} ({barcode})" for barcode, name in current_discount_products if any(p[0] == barcode for p in all_products)]
                
                selected_product_keys = st.multiselect(
                    "اختر المنتجات (اتركها فارغة لتطبيق على جميع المنتجات):",
                    options=list(product_options.keys()),
                    default=default_products,
                    key="discount_products"
                )
                selected_products = [product_options[key] for key in selected_product_keys]
            
            col1, col2 = st.columns(2)
            
            with col1:
                if st.button("حفظ إعدادات الفروع 💾", key="save_branches"):
                    if update_discount_branches(selected_discount, selected_branches):
                        st.success(f"تم تحديث فروع تطبيق الخصم '{selected_discount}' بنجاح!")
                        st.cache_data.clear()
                    else:
                        st.error("فشل في تحديث فروع تطبيق الخصم.")
            
            with col2:
                if st.button("حفظ إعدادات المنتجات 💾", key="save_products"):
                    if update_discount_products(selected_discount, selected_products):
                        st.success(f"تم تحديث المنتجات لخصم '{selected_discount}' بنجاح!")
                        st.cache_data.clear()
                    else:
                        st.error("فشل في تحديث المنتجات.")
    else:
        st.info("لا توجد خصومات مسجلة حالياً.")
    
    st.divider()
    st.subheader("➕ إضافة خصم جديد (مبسط)")
    
    with st.form("add_discount_form"):
        d_name = st.text_input("اسم الخصم:")
        col1, col2 = st.columns(2)
        d_value = col1.number_input("القيمة:", min_value=0.0, step=0.01)
        d_value_type = col2.selectbox("نوع القيمة:", ["percentage", "amount"])
        
        d_type = st.selectbox("نوع الخصم:", ["lifetime", "temporary", "usage_limit", "invoice_threshold"])
        
        d_start = st.date_input("تاريخ البدء:", datetime.date.today())
        d_end = st.date_input("تاريخ الانتهاء:", datetime.date.today() + datetime.timedelta(days=30))
        
        col1, col2 = st.columns(2)
        
        with col1:
            d_branches = st.multiselect("تطبيق على الفروع:", options=branches)
        
        with col2:
            all_products_form = get_all_products()
            product_options_form = {f"{name} ({barcode})": (barcode, name) for barcode, name in all_products_form}
            selected_product_keys_form = st.multiselect(
                "اختر المنتجات (اتركها فارغة لجميع المنتجات):",
                options=list(product_options_form.keys())
            )
            d_products = [product_options_form[key] for key in selected_product_keys_form]
        
        submitted = st.form_submit_button("إضافة الخصم 🚀")
        
        if submitted:
            if d_name:
                try:
                    discount_data = {
                        "name": d_name,
                        "value": d_value,
                        "value_type": d_value_type,
                        "discount_type": d_type,
                        "start_date": d_start.isoformat() if d_type != "lifetime" else None,
                        "end_date": d_end.isoformat() if d_type != "lifetime" else None,
                        "created_at": datetime.datetime.now().isoformat()
                    }
                    # Insert discount
                    supabase.table('discounts').insert(discount_data).execute()
                    
                    # Insert branch applicability
                    if d_branches:
                        update_discount_branches(d_name, d_branches)
                    
                    # Insert product applicability
                    if d_products:
                        update_discount_products(d_name, d_products)
                        
                    st.success(f"تم إضافة الخصم '{d_name}' بنجاح!")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"حدث خطأ أثناء إضافة الخصم: {e}")
            else:
                st.warning("الرجاء إدخال اسم الخصم.")
