import os
import sys
import json
import pandas as pd
import streamlit as st
import traceback

# 💡 [초고속 엔진 설치 감지 로직 - 진짜 이름(python_calamine)으로 찾기 완벽 수정]
HAS_CALAMINE = False
try:
    import python_calamine  # 파이썬 내부 진짜 모듈명
    HAS_CALAMINE = True
except ImportError:
    try:
        import calamine
        HAS_CALAMINE = True
    except ImportError:
        HAS_CALAMINE = False

# ==============================================================================
# 0. [보안 및 권한 제어] 로컬(개발) vs 배포(서버) 자동 감지 프리패스 시스템
# ==============================================================================
if "user_id" not in st.session_state:
    st.session_state.user_id = None
    st.session_state.user_role = None

is_local_dev = False
try:
    users_db = st.secrets["users"]
except Exception:
    is_local_dev = True

if is_local_dev:
    st.session_state.user_id = "developer (로컬 개발모드)"
    st.session_state.user_role = "admin"

if st.session_state.user_id is None:
    st.set_page_config(page_title="로그인 | 스마트 물류 출고 대시보드", layout="wide", page_icon="🔒")
    st.title("🔒 물류 출고 현황 분석기")
    st.info("부여받은 개별 아이디와 비밀번호로 로그인해 주세요.")
    
    with st.form("login_form"):
        input_id = st.text_input("👤 아이디 (ID)", autocomplete="username").strip()
        input_pw = st.text_input("🔑 비밀번호 (Password)", type="password", autocomplete="current-password").strip()
        submit_btn = st.form_submit_button("로그인")
        
        if submit_btn:
            if input_id in users_db and str(users_db[input_id]["password"]) == input_pw:
                st.session_state.user_id = input_id
                st.session_state.user_role = str(users_db[input_id]["role"])
                st.rerun()
            else:
                st.error("🚫 아이디 또는 비밀번호가 일치하지 않습니다.")
    st.stop()

current_user_id = st.session_state.user_id
current_user_role = st.session_state.user_role

# ==============================================================================
# 0-1. [메뉴 권한 동적 관리]
# ==============================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "menu_config.json")

ALL_MENUS = [
    "출고 CAPA 분석", 
    "셀러별 출고 분석",
    "상품별 출고 분석",
    "시간대별 주문 분석",
    "이종합포 묶음 헬퍼",
    "데이터 추출 및 다운로드"
]

unique_roles = set(["admin"])
try:
    for uid, info in st.secrets["users"].items():
        if "role" in info:
            unique_roles.add(str(info["role"]))
except Exception:
    pass
unique_roles = sorted(list(unique_roles))

def load_menu_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

menu_config = load_menu_config()

for r in unique_roles:
    if r not in menu_config:
        menu_config[r] = ALL_MENUS if r == "admin" else ALL_MENUS[:4]

# ==============================================================================
# --- 1. 작업 경로 등록 및 모듈 경로 설정 ---
# ==============================================================================
sys.path.append(BASE_DIR)
view_dir_upper = os.path.join(BASE_DIR, "View")
view_dir_lower = os.path.join(BASE_DIR, "views")

if os.path.exists(view_dir_upper): sys.path.append(view_dir_upper)
elif os.path.exists(view_dir_lower): sys.path.append(view_dir_lower)

try:
    from tab1_dispatch import render_dispatch_tab
    from tab2_sellers import render_sellers_tab
    from tab3_products import render_products_tab
    from tab4_time_inflow import render_time_inflow_tab  
    from tab5_combinations import render_combinations_tab  
    from tab6_data_download import render_download_tab
except ModuleNotFoundError:
    try:
        from Views.tab1_dispatch import render_dispatch_tab
        from Views.tab2_sellers import render_sellers_tab
        from Views.tab3_products import render_products_tab
        from Views.tab4_time_inflow import render_time_inflow_tab  
        from Views.tab5_combinations import render_combinations_tab  
        from Views.tab6_data_download import render_download_tab
    except ModuleNotFoundError:
        pass 

# ==============================================================================
# --- 2. 상수 정의 및 ⚡ 초고속 엑셀 읽기 함수 ---
# ==============================================================================
DELIVERY_TYPES = ['일반 배송', '당일 배송', '휴일 배송']
PACKING_TYPES = ['단수', '단수단포', '단수합포', '이종합포', '혼합']
REQUIRED_COLUMNS = [
    '출고번호', '주문번호', '배송유형', 'OM셀러명', '기준재고번호', '기준재고명',
    '온도유형', '주문수량', '할당수량', '패킹타입', '할당상태', '출고상태',
    '출고예정일', '출고일자', '결제일시', '판매채널', '배송집하일'
]
DRY_ICE_SKUS = ['40574128111']

def read_excel_fast(file, **kwargs):
    """
    설치된 엔진을 감지하여 가장 빠른 속도로 엑셀을 읽어옵니다.
    """
    if HAS_CALAMINE:
        try:
            if hasattr(file, 'seek'): file.seek(0)
            return pd.read_excel(file, engine='calamine', **kwargs)
        except Exception:
            pass 
            
    if hasattr(file, 'seek'): file.seek(0)
    return pd.read_excel(file, **kwargs)

# ==============================================================================
# --- 3. 페이지 기본 설정 및 스타일 ---
# ==============================================================================
st.set_page_config(page_title="스마트 물류 출고 대시보드", layout="wide")

st.markdown("""
    <style>
    .block-container { padding-top: 3.0rem !important; padding-bottom: 5rem !important; }
    div[data-testid="stHeader"] { display: none; }
    hr { margin-top: 0.5rem !important; margin-bottom: 0.8rem !important; }
    div[data-testid="stExpander"] {
        border: 1px solid #333333 !important;
        border-radius: 8px !important;
        background-color: #11151C !important;
    }
    div.row-widget.stRadio > div { flex-direction: row; gap: 20px; }
    </style>
""", unsafe_allow_html=True)

# ==============================================================================
# --- 4. 사이드바 ---
# ==============================================================================
st.sidebar.markdown('<style>div[data-testid="stRadio"] label p {font-size: 15px !important; font-weight: 600 !important; color: var(--text-color) !important;}</style>', unsafe_allow_html=True)

st.sidebar.header("📥 데이터 업로드")
uploaded_file = st.sidebar.file_uploader("당일 출고 예정 데이터(.xlsx)", type=["xlsx", "xls"], key="main_file")

with st.sidebar.expander("▶ 선택 파일 업로드 (이월/부족)", expanded=False):
    st.caption("추가 분석이 필요한 경우에만 업로드하세요.")
    prev_file = st.file_uploader("1. 전일 미출고 실적 (선택)", type=["xlsx", "xls"], key="prev_file")
    shortage_file = st.file_uploader("2. 재고부족 리스트 (선택)", type=["xlsx", "xls"], key="short_file")

st.sidebar.markdown("---")
st.sidebar.header("📌 분석 메뉴")

ADMIN_MENU_NAME = "권한 제어 센터"
menu_options = []
allowed_menus = menu_config.get(current_user_role, [])
for m in ALL_MENUS:
    if m in allowed_menus: menu_options.append(m)
if current_user_role == "admin": menu_options.append(ADMIN_MENU_NAME)

selected_menu = st.sidebar.radio("분석 메뉴 선택:", menu_options, label_visibility="collapsed")

st.sidebar.markdown("---")

acc_col1, acc_col2 = st.sidebar.columns([7, 5])
with acc_col1:
    st.markdown(f"<div style='font-size: 13px; color: #AAAAAA; padding-top: 5px;'>👤 <b>{current_user_id}</b> ({current_user_role})</div>", unsafe_allow_html=True)
with acc_col2:
    if st.button("로그아웃", key="logout_btn", use_container_width=True):
        st.session_state.user_id = None
        st.session_state.user_role = None
        st.rerun()

# 💡 [엔진 상태 표시기] 설치가 잘 되었는지 여기서 바로 확인 가능합니다!
if HAS_CALAMINE:
    st.sidebar.markdown("<div style='font-size: 12px; color: #4CAF50; margin-top: 10px;'>⚡ 데이터 엔진: <b>초고속 모드</b> 작동 중</div>", unsafe_allow_html=True)
else:
    st.sidebar.markdown("<div style='font-size: 12px; color: #FF9800; margin-top: 10px;'>🐢 데이터 엔진: <b>일반 모드</b> (터미널 설치 재확인 필요)</div>", unsafe_allow_html=True)


if selected_menu != ADMIN_MENU_NAME:
    if uploaded_file is None:
        st.info("👈 좌측 사이드바 상단에서 분석할 **당일 출고현황 파일(.xlsx)**을 업로드해 주세요.")
        st.stop()
    try:
        # 미리보기는 단 0줄만 읽어서 필수 컬럼만 잽싸게 확인
        df_preview = read_excel_fast(uploaded_file, nrows=0) 
        missing_cols = [col for col in REQUIRED_COLUMNS if col not in df_preview.columns.tolist()]
        if missing_cols:
            st.sidebar.error(f"❌ 필수 컬럼 누락: {', '.join(missing_cols)}")
            st.stop()
    except Exception as e:
        st.sidebar.error(f"파일을 읽는 중 문제가 발생했습니다. ({e})")
        st.stop()

# ==============================================================================
# --- 5. 데이터 로드 및 전처리 ---
# ==============================================================================
@st.cache_data(show_spinner="데이터 추출 및 병합 가공 중... (최적화 엔진 가동)")
def load_and_preprocess(main_file, opt_prev_file, opt_short_file):
    # 💡 초고속 읽기 함수 + 필요한 컬럼 17개만 뽑아오는(usecols) 기술 결합!
    df_main = read_excel_fast(main_file, usecols=REQUIRED_COLUMNS, dtype={'출고번호': str, '기준재고번호': str})
    df_main['데이터구분'] = '금일 신규'
    
    if opt_prev_file is not None:
        if '출고예정일' in df_main.columns:
            target_date_str = str(df_main['출고예정일'].mode()[0])
            cutoff_time = pd.to_datetime(target_date_str) + pd.Timedelta(hours=3)
            try:
                df_prev = read_excel_fast(opt_prev_file, usecols=REQUIRED_COLUMNS, dtype={'출고번호': str, '기준재고번호': str})
                df_prev['출고일자_dt'] = pd.to_datetime(df_prev['출고일자'], errors='coerce')
                keep_mask = df_prev['출고일자_dt'].isna() | (df_prev['출고일자_dt'] >= cutoff_time)
                df_prev_filtered = df_prev[keep_mask].drop(columns=['출고일자_dt'])
                df_prev_filtered['데이터구분'] = '전일 이월'
                
                df_main = pd.concat([df_main, df_prev_filtered], ignore_index=True)
                df_main = df_main.drop_duplicates(subset=['출고번호', '기준재고번호'], keep='last')
            except ValueError:
                pass

    if '배송집하일' in df_main.columns: 
        df_main['배송집하일'] = df_main['배송집하일'].fillna(0)
    
    df_main['출고번호_clean'] = df_main['출고번호'].astype(str).str.strip()
    
    if '결제일시' in df_main.columns:
        date_str = df_main['결제일시'].astype(str).str.replace(r'\D', '', regex=True)
        df_main['결제일시_dt'] = pd.to_datetime(date_str, format='%Y%m%d%H%M%S', errors='coerce')

    if '할당상태' in df_main.columns:
        is_prev_unalloc = (df_main['데이터구분'] == '전일 이월') & (df_main['할당상태'] == '미할당')
        df_main.loc[is_prev_unalloc, '할당상태'] = '재고부족'

        if opt_short_file is not None:
            try:
                df_short = read_excel_fast(opt_short_file, dtype=str)
                short_col = '출고번호' if '출고번호' in df_short.columns else df_short.columns[0]
                short_ids = set(df_short[short_col].dropna().astype(str).str.strip().unique())
                
                cond_short = (df_main['데이터구분'] == '금일 신규') & (df_main['출고번호_clean'].isin(short_ids))
                df_main.loc[cond_short, '할당상태'] = '재고부족'
            except Exception:
                pass
        else:
            if '결제일시_dt' in df_main.columns:
                max_time = df_main['결제일시_dt'].max()
                threshold_time = max_time - pd.Timedelta(hours=1)
                cond_auto = (df_main['데이터구분'] == '금일 신규') & (df_main['할당상태'] == '미할당') & (df_main['결제일시_dt'] < threshold_time)
                df_main.loc[cond_auto, '할당상태'] = '재고부족'

        # 먼저 남은 미할당을 완전할당(미피킹)으로 변환합니다.
        df_main.loc[df_main['할당상태'] == '미할당', '할당상태'] = '완전할당(미피킹)'

        # 💡 [핵심 버그 수정: 부분 할당 방지 로직]
        # 같은 출고번호 내에 '재고부족'인 상품이 단 하나라도 있다면, 
        # 해당 출고번호에 속한 '모든' 상품의 상태를 '재고부족'으로 강제 동기화시킵니다.
        shortage_order_ids = df_main[df_main['할당상태'] == '재고부족']['출고번호'].dropna().unique()
        df_main.loc[df_main['출고번호'].isin(shortage_order_ids), '할당상태'] = '재고부족'

    if '출고예정일' in df_main.columns and '결제일시_dt' in df_main.columns:
        df_main['출고예정일_dt'] = pd.to_datetime(df_main['출고예정일'], errors='coerce')
        df_main['시간대'] = df_main['결제일시_dt'].dt.strftime('%H시')
        df_main.loc[df_main['결제일시_dt'] < df_main['출고예정일_dt'], '시간대'] = '00시 이전'

    for col in ['기준재고명', 'OM셀러명', '판매채널', '배송유형', '패킹타입', '데이터구분']:
        if col in df_main.columns: 
            df_main[col] = df_main[col].astype('category')

    return df_main

# ==============================================================================
# --- 9. 메인 영역 & 메뉴 라우팅 ---
# ==============================================================================
if selected_menu == ADMIN_MENU_NAME:
    st.title("⚙️ 권한 제어 센터")
    st.info("아래 표에서 각 권한(Role) 그룹에게 노출할 메뉴를 체크(☑️)한 뒤 [저장] 버튼을 누르세요.")
    
    records = []
    for role in unique_roles:
        record = {"접속 역할 (Role)": role, "_role_key": role}
        role_menus = menu_config.get(role, [])
        for m in ALL_MENUS: record[m] = (m in role_menus)
        records.append(record)
        
    edited_df = st.data_editor(pd.DataFrame(records).drop(columns=["_role_key"]), hide_index=True, use_container_width=True)
    if st.button("💾 변경된 설정 저장", type="primary"):
        new_config = {}
        for idx, row in edited_df.iterrows():
            new_config[pd.DataFrame(records).iloc[idx]["_role_key"]] = [m for m in ALL_MENUS if row[m] == True]
        with open(CONFIG_FILE, "w", encoding="utf-8") as f: json.dump(new_config, f, ensure_ascii=False, indent=4)
        st.success("✅ 메뉴 노출 설정 저장 완료!")

elif selected_menu != ADMIN_MENU_NAME:
    try:
        df_full = load_and_preprocess(uploaded_file, prev_file, shortage_file)
    except Exception as e:
        st.error(f"❌ 데이터 분석 중 오류: {e}")
        st.stop()
        
    def map_delivery_type(val):
        val_str = str(val).replace(" ", "")
        if '당일' in val_str: return '당일 배송'
        elif '일반' in val_str: return '일반 배송'
        elif '휴일' in val_str: return '휴일 배송'
        return '기타 배송'

    df_full['배송대분류'] = df_full['배송유형'].apply(map_delivery_type)

    if '출고예정일' in df_full.columns and not df_full['출고예정일'].isna().all():
        target_date_val = str(df_full['출고예정일'].mode()[0])
        if len(target_date_val) == 8 and target_date_val.isdigit(): formatted_target_date = f"{target_date_val[:4]}-{target_date_val[4:6]}-{target_date_val[6:]}"
        else: formatted_target_date = str(pd.to_datetime(target_date_val).strftime('%Y-%m-%d'))
    else: formatted_target_date = "미확인"

    title_col, summary_col = st.columns([7, 5])
    with title_col:
        st.title("📦 스마트 물류 출고 통합 대시보드")
        main_max_str = df_full['결제일시_dt'].max().strftime('%y-%m-%d %H:%M') if '결제일시_dt' in df_full.columns and not df_full['결제일시_dt'].isna().all() else "미확인"
        st.caption(f"📅 **출고예정일 : {formatted_target_date}** &nbsp;|&nbsp; ⏱️ 데이터 생성일시 : {main_max_str}")

    with summary_col:
        full_inflow = df_full['출고번호'].nunique()
        
        def build_delivery_text(df_sub):
            tc = df_sub.groupby('배송대분류')['출고번호'].nunique().to_dict()
            active = sorted({k: v for k, v in tc.items() if v > 0}.items(), key=lambda x: x[1], reverse=True)
            return " | ".join([f"{k.replace(' 배송', '')} {v:,}건" for k, v in active]) if active else "데이터 없음"

        df_today = df_full[df_full['데이터구분'] == '금일 신규']
        df_prev = df_full[df_full['데이터구분'] == '전일 이월']

        today_sub_text = build_delivery_text(df_today)
        
        if not df_prev.empty:
            prev_sub_text = build_delivery_text(df_prev)
            prev_line_str = f"전일 ({prev_sub_text})"
        else:
            prev_line_str = "전일 (미출고 데이터 없음)"

        st.markdown(
            f"""<div style="text-align: right; padding-top: 2px;">
                <div style="font-size: 19px; font-weight: bold; color: #FFFFFF;">
                    📦 오늘 총 주문 유입 <span style="font-size: 26px; margin-left: 10px; color: #4CAF50;">{full_inflow:,} 건</span>
                </div>
                <div style="font-size: 12px; color: #888888; margin-top: 2px;">금일 ({today_sub_text})</div>
                <div style="font-size: 12px; color: #888888; margin-top: 1px;">{prev_line_str}</div>
            </div>""", unsafe_allow_html=True
        )

    st.markdown("---")

    data_filter = st.radio(
        "조회 기준 선택",
        ["전체", "금일 신규", "전일 이월"],
        horizontal=True,
        label_visibility="collapsed"
    )

    if data_filter == "전체":
        df = df_full.copy()
    else:
        df = df_full[df_full['데이터구분'] == data_filter].copy()

    type_counts = df.groupby('배송대분류')['출고번호'].nunique().to_dict()
    total_inflow = df['출고번호'].nunique()

    with st.expander("📊 세부 출고 및 패킹 현황 요약 (클릭하여 접기/펴기)", expanded=True):
        left_header_col, right_header_col = st.columns([6, 6])
        with left_header_col:
            st.markdown("#### 🔍 세부 출고 현황 설정")
            filter_col1, filter_col2 = st.columns(2)
            with filter_col1:
                available_types = [t for t in DELIVERY_TYPES if t in type_counts]
                if not available_types: available_types = DELIVERY_TYPES
                selected_type = st.selectbox("🔍 조회할 배송 유형 선택", ['전체'] + available_types, index=0, key="app_header_selectbox")

            with filter_col2:
                if selected_type == '당일 배송':
                    st.markdown("<div style='color: #E53935; font-size: 13px; margin-top: 32px; font-weight: 500;'>💡 당일 배송은 <b>'출고완료'</b> 기준 집계됩니다.</div>", unsafe_allow_html=True)
                    delay_ratio = 1.0
                else:
                    delay_ratio_percent = st.selectbox("⚙️ 미집하 보정비율 (%)", [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100], index=2, format_func=lambda x: f"{x}%", key="global_delay_ratio_selectbox")
                    delay_ratio = delay_ratio_percent / 100.0

            if selected_type == '전체':
                group_type = df.copy()
                type_total = total_inflow
            else:
                group_type = df[df['배송대분류'] == selected_type].copy()
                type_total = group_type['출고번호'].nunique()

            if selected_type == '당일 배송':
                is_shipped_set = set(group_type[group_type['출고상태'] == '출고완료']['출고번호'].dropna().unique())
                adj_completed_t = len(is_shipped_set)
                unshipped_t = type_total - adj_completed_t
                delta_completed_text = "[당일 실시간 현황]"
            else:
                has_pickup_t = group_type['배송집하일'] != 0
                is_shipped_t = group_type['출고상태'] == '출고완료'
                pickup_set = set(group_type[has_pickup_t & is_shipped_t]['출고번호'].dropna().unique())
                unpickup_set = set(group_type[~has_pickup_t & is_shipped_t]['출고번호'].dropna().unique()) - pickup_set
                pickup_t = len(pickup_set)
                unpickup_t = len(unpickup_set)
                adj_completed_t = round(pickup_t + (unpickup_t * delay_ratio))
                unshipped_t = round(type_total - adj_completed_t)
                delta_completed_text = f"[집하 {pickup_t:,}건 / 미집하 {unpickup_t:,}건]"

            unalloc_t = group_type[group_type['할당상태'] == '재고부족']['출고번호'].nunique() if '할당상태' in group_type.columns else 0
            alloc_unshipped_t = max(0, unshipped_t - unalloc_t)

            sub_m1, sub_m2, sub_m3 = st.columns(3)
            
            if selected_type == '전체' and data_filter == '전체':
                today_count = group_type[group_type['데이터구분'] == '금일 신규']['출고번호'].nunique()
                prev_count = group_type[group_type['데이터구분'] == '전일 이월']['출고번호'].nunique()
                metric_title = "총 건수"
                metric_delta = f"(금일 {today_count:,}건 / 전일 {prev_count:,}건)"
                sub_m1.metric(metric_title, f"{type_total:,}건", delta=metric_delta, delta_color="off")
            else:
                sub_m1.metric(f"[{selected_type}]", f"{type_total:,}건")

            sub_m2.metric("출고완료" if selected_type == '당일 배송' else "출고완료(미집하 보정)", f"{adj_completed_t:,}건", delta=delta_completed_text, delta_color="off")
            sub_m3.metric("미출고 (총 잔여)", f"{unshipped_t:,}건", delta=f"[할당 {alloc_unshipped_t:,}건 / 미할당 {unalloc_t:,}건]", delta_color="off")

        with right_header_col:
            st.markdown("""<style>div[data-testid="stDataFrame"] [data-testid="stHeaderCell"] > div, div[data-testid="stDataFrame"] [data-testid="stHeaderCell"] p, div[data-testid="stDataFrame"] [data-backend-type] {justify-content: center !important; text-align: center !important; width: 100% !important;}</style>""", unsafe_allow_html=True)
            
            temp_counts_per_order = df.groupby('출고번호')['온도유형'].nunique() if '온도유형' in df.columns else None
            mixed_temp_orders = set(temp_counts_per_order[temp_counts_per_order > 1].index) if temp_counts_per_order is not None else set()

            def classify_packing_detail(row):
                ptype = str(row.get('패킹타입', '')).replace(" ", "")
                return '혼합' if ptype == '이종합포' and row.get('출고번호') in mixed_temp_orders else ptype

            use_cols_packing = [c for c in ['출고번호', '패킹타입', '배송집하일', '출고상태', '할당상태'] if c in group_type.columns]
            df_order_packing = group_type[use_cols_packing].drop_duplicates(subset=['출고번호']).copy()
            df_order_packing['패킹타입_세부'] = df_order_packing.apply(classify_packing_detail, axis=1)

            col_title, col_toggle = st.columns([7, 5])
            with col_title: st.markdown(f"#### 📦 [{selected_type}] 패킹 유형 현황", unsafe_allow_html=True)
            with col_toggle: show_details = st.checkbox("🔘 세부 할당(대기) 상태 펼쳐보기", value=False)

            packing_rows = []
            for p_name in PACKING_TYPES:
                p_group = df_order_packing[df_order_packing['패킹타입_세부'] == p_name]
                p_count = len(p_group)
                p_ratio = (p_count / type_total * 100) if type_total > 0 else 0
                
                if selected_type == '당일 배송':
                    p_adj_shipped = p_group[p_group['출고상태'] == '출고완료']['출고번호'].nunique()
                else:
                    p_has_pickup = p_group['배송집하일'] != 0
                    p_is_shipped = p_group['출고상태'] == '출고완료'
                    p_pickup_set = set(p_group[p_has_pickup & p_is_shipped]['출고번호'].dropna().unique())
                    p_unpickup_set = set(p_group[~p_has_pickup & p_is_shipped]['출고번호'].dropna().unique()) - p_pickup_set
                    p_adj_shipped = round(len(p_pickup_set) + (len(p_unpickup_set) * delay_ratio))
                    
                p_unshipped = p_count - p_adj_shipped
                
                if '할당상태' in p_group.columns:
                    p_unalloc = p_group[p_group['할당상태'] == '재고부족']['출고번호'].nunique()
                    p_packing_wait = p_group[(p_group['할당상태'] == '피킹완료') & (p_group['출고상태'] != '출고완료')]['출고번호'].nunique()
                    p_alloc_wait = max(0, p_unshipped - p_packing_wait - p_unalloc)
                else:
                    p_unalloc, p_packing_wait, p_alloc_wait = 0, 0, 0

                packing_rows.append({'패킹타입': p_name, '주문': f"{p_count:,}", '비율(%)': f"{p_ratio:.1f}%", '출고완료': f"{p_adj_shipped:,}", '미출고': f"{p_unshipped:,}", '할당(포장대기)': f"{p_packing_wait:,}", '할당(할당대기)': f"{p_alloc_wait:,}", '미할당': f"{p_unalloc:,}"})

            df_packing_summary = pd.DataFrame(packing_rows)
            if not show_details: df_packing_summary = df_packing_summary.drop(columns=['할당(포장대기)', '할당(할당대기)'])

            st.dataframe(df_packing_summary, column_config={col: st.column_config.TextColumn(col, alignment="center") for col in df_packing_summary.columns}, use_container_width=True, height=195, hide_index=True)

            if '기준재고명' in group_type.columns and '기준재고번호' in group_type.columns:
                ice_mask = group_type['기준재고명'].str.contains('아이스', na=False)
                ice_order_ids = set(group_type[ice_mask]['출고번호'].dropna().unique())
                total_ice = len(ice_order_ids)
                if total_ice > 0:
                    ice_no_dry_df = group_type[group_type['출고번호'].isin(ice_order_ids) & ~group_type['기준재고번호'].astype(str).isin(DRY_ICE_SKUS)]
                    sku_counts = ice_no_dry_df.groupby('출고번호')['기준재고번호'].nunique()
                    ice_sub_text = f"🍦 아이스크림 주문: 총 {total_ice:,}건 (단품 {(sku_counts == 1).sum():,}건 / 혼합 {(sku_counts >= 2).sum():,}건)"
                else: ice_sub_text = "🍦 현재 아이스크림 주문 없음"
            else: ice_sub_text = "🍦 아이스크림 정보 없음"
            st.markdown(f"<div style='text-align: right; font-size: 13px; color: #4CAF50; font-weight: 500; margin-top: 3px; padding-right: 5px;'>{ice_sub_text}</div>", unsafe_allow_html=True)

    st.markdown("---")

    if selected_menu == "출고 CAPA 분석":
        st.info("🚧 **[개발 중]** 현장 상황에 맞춘 최적의 마감 예측 알고리즘을 설계하고 있습니다.")
    elif selected_menu == "셀러별 출고 분석":
        try: render_sellers_tab(group_type)
        except NameError: st.error("🏢 `render_sellers_tab` 모듈 연결 실패.")
    elif selected_menu == "상품별 출고 분석":
        try: render_products_tab(group_type)
        except NameError: st.error("❌ `render_products_tab` 모듈을 찾을 수 없습니다.")
    elif selected_menu == "시간대별 주문 분석":
        try: render_time_inflow_tab(group_type)
        except NameError: st.error("❌ `render_time_inflow_tab` 모듈을 찾을 수 없습니다.")
    elif selected_menu == "이종합포 묶음 헬퍼":
        try: render_combinations_tab(df, selected_type) 
        except NameError: st.error("❌ `render_combinations_tab` 모듈을 찾을 수 없습니다.")
        except Exception as e: st.error(f"❌ 메뉴 실행 중 오류 발생: {e}")
    elif selected_menu == "데이터 추출 및 다운로드":
        try: render_download_tab(df, df_prev, data_filter)
        except NameError: st.error("❌ `render_download_tab` 모듈을 찾을 수 없습니다.")
        except Exception as e: st.error(f"❌ 메뉴 실행 중 오류 발생: {e}")

    st.markdown("<div style='height: 100px;'></div>", unsafe_allow_html=True)