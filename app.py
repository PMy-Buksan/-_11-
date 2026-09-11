import os
import sys
import pandas as pd
import streamlit as st
import traceback  # 👈 에러 추적을 위해 추가됨

# ==============================================================================
# 0. [보안] 사내 및 외부 허가 인원 지정 (화이트리스트 방식)
# ==============================================================================
ALLOWED_EMAILS = [
    "pmy@buksan.pro",  # 👈 테스트 사용자 및 사용 허가 이메일 입력
    "dlee@hanjin.com"
    # 추가로 허용할 이메일들을 여기에 계속 작성하세요.
]

# 1) 미로그인 상태 처리
if not st.user.is_logged_in:
    st.set_page_config(page_title="로그인 필요 | 물류 출고 현황 분석기", page_icon="🔒")
    st.title("🔒 지정 사용자 전용 시스템 접속")
    st.subheader("물류 출고 현황 분석 대시보드")
    st.info("본 시스템은 사전 등록된 허가 인원만 이용 가능합니다. 구글 계정으로 로그인해 주세요.")
    
    if st.button("🔑 Google 계정으로 로그인", type="primary"):
        st.login("google")
    st.stop()

# 2) 허가되지 않은 이메일 차단 처리
user_email = str(st.user.email).strip().lower()
allowed_emails_lower = [email.strip().lower() for email in ALLOWED_EMAILS]

if user_email not in allowed_emails_lower:
    st.set_page_config(page_title="접근 제한 | 물류 출고 현황 분석기", page_icon="🚫")
    st.error(f"🚫 접근 권한이 없습니다. ({user_email})")
    st.warning("등록되지 않은 계정입니다. 시스템 관리자에게 권한 요청 후 다시 시도해 주세요.")
    
    if st.button("다른 계정으로 로그인"):
        st.logout()
    st.stop()
    
# ==============================================================================
# 1. 작업 경로 등록 및 모듈 경로 설정
# ==============================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE_DIR)

# 💡 폴더명을 Views (대문자 V)로 우선 탐색하도록 수정
view_dir_capital = os.path.join(BASE_DIR, "Views")
view_dir_lower = os.path.join(BASE_DIR, "views")

if os.path.exists(view_dir_capital):
    sys.path.append(view_dir_capital)
elif os.path.exists(view_dir_lower):
    sys.path.append(view_dir_lower)

# 💡 [핵심 수정]: Views (대문자) 폴더에서 모듈을 불러오도록 변경
try:
    from Views.tab1_dispatch import render_dispatch_tab
    from Views.tab2_sellers import render_sellers_tab
    from Views.tab3_products import render_products_tab
    from Views.tab4_time_inflow import render_time_inflow_tab
except Exception as e:
    st.error(f"🚨 **Views 폴더 내부 파일을 불러오는 중 에러가 발생했습니다.** (누락된 패키지나 경로 문제일 수 있습니다)")
    st.code(traceback.format_exc()) # 어떤 파일에서 무슨 에러가 났는지 상세히 출력합니다.

# ==============================================================================
# 2. 상수 정의
# ==============================================================================
DELIVERY_TYPES = ['일반 배송', '당일 배송', '휴일 배송']
PACKING_TYPES = ['단수', '단수단포', '단수합포', '이종합포', '혼합']

# ==============================================================================
# 3. 페이지 기본 설정 및 사이드바 접속 정보
# ==============================================================================
st.set_page_config(page_title="물류 출고 현황 분석기", layout="wide")

# 접속자 이메일 표시 및 로그아웃 버튼
st.sidebar.caption(f"👤 접속 계정: {st.user.email}")
if st.sidebar.button("🚪 로그아웃", key="logout_btn"):
    st.logout()
st.sidebar.markdown("---")

# ==============================================================================
# 4. 사이드바: 메뉴 라우팅 & 파일 업로드
# ==============================================================================
st.sidebar.markdown("""
    <style>
    div[data-testid="stRadio"] label p {
        font-size: 17px !important;
        font-weight: bold !important;
        color: var(--text-color) !important; 
    }
    </style>
""", unsafe_allow_html=True)

st.sidebar.header("📌 분석 메뉴 선택")
selected_menu = st.sidebar.radio(
    "원하시는 메뉴를 선택하세요:",
    [
        "🚚 1. 배송 유형별 마감 예측", 
        "🏢 2. 셀러별 상세 현황",
        "📦 3. 상품별 출고 현황",
        "⏱️ 4. 시간대별 주문 인입 분석",
        "🔗 5. 이종합포 조합 분석"
    ]
)

st.sidebar.markdown("---")
st.sidebar.header("📂 1. 출고 파일 업로드 (필수)")
uploaded_file = st.sidebar.file_uploader(
    "출고현황 파일(.xlsx)을 업로드하세요", 
    type=["xlsx", "xls"],
    key="main_file"
)

st.sidebar.markdown("---")
st.sidebar.header("🚨 2. 재고부족 리스트 (선택)")
shortage_file = st.sidebar.file_uploader(
    "정확한 결품 확인이 필요할 때만 업로드", 
    type=["xlsx", "xls"],
    key="short_file"
)

if uploaded_file is None:
    st.info("👈 좌측 사이드바에서 분석할 **출고현황 파일(.xlsx)**을 업로드해 주세요.")
    st.stop()

# ==============================================================================
# 5. 데이터 로드 및 미할당 처리 핵심 로직
# ==============================================================================
@st.cache_data(show_spinner="데이터 병합 및 시간대 분석 중...")
def load_and_preprocess(main_file, opt_short_file):
    df_main = pd.read_excel(main_file, dtype={'출고번호': str})
    
    if '배송집하일' in df_main.columns:
        df_main['배송집하일'] = df_main['배송집하일'].fillna(0)
    
    df_main['출고번호_clean'] = df_main['출고번호'].astype(str).str.strip()
    
    # [결제일시 파싱]: 시간대 분석을 위한 전처리
    if '결제일시' in df_main.columns:
        date_str = df_main['결제일시'].astype(str).str.replace(r'\D', '', regex=True)
        df_main['결제일시_dt'] = pd.to_datetime(date_str, format='%Y%m%d%H%M%S', errors='coerce')
    
    # [상황 1]: 미할당 파일 업로드 시
    if opt_short_file is not None:
        df_short = pd.read_excel(opt_short_file, dtype=str)
        short_col = '출고번호' if '출고번호' in df_short.columns else df_short.columns[0]
        short_ids = set(df_short[short_col].dropna().astype(str).str.strip().unique())
        
        cond = df_main['출고번호_clean'].isin(short_ids)
        if '할당상태' in df_main.columns:
            df_main.loc[cond, '할당상태'] = '재고부족'
            
    # [상황 2]: 미할당 파일 없을 시 (1시간 경과 로직 적용)
    else:
        if '결제일시_dt' in df_main.columns and '할당상태' in df_main.columns:
            max_time = df_main['결제일시_dt'].max()
            threshold_time = max_time - pd.Timedelta(hours=1)
            
            cond = (df_main['할당상태'] == '미할당') & (df_main['결제일시_dt'] < threshold_time)
            df_main.loc[cond, '할당상태'] = '재고부족'

    # 정상 1시간 이내 보류건은 '완전할당(미피킹)'으로 흡수
    if '할당상태' in df_main.columns:
        df_main.loc[df_main['할당상태'] == '미할당', '할당상태'] = '완전할당(미피킹)'

    # 시간대 파생 변수 생성
    if '출고예정일' in df_main.columns and '결제일시_dt' in df_main.columns:
        df_main['출고예정일_dt'] = pd.to_datetime(df_main['출고예정일'], errors='coerce')
        df_main['시간대'] = df_main['결제일시_dt'].dt.strftime('%H시')
        
        cond_before_midnight = df_main['결제일시_dt'] < df_main['출고예정일_dt']
        df_main.loc[cond_before_midnight, '시간대'] = '00시 이전'

    return df_main

try:
    df = load_and_preprocess(uploaded_file, shortage_file)
except Exception as e:
    st.error(f"❌ 데이터 분석 중 오류가 발생했습니다: {e}")
    st.stop()

# ==============================================================================
# 6. 데이터 전처리 및 대시보드 헤더
# ==============================================================================
def map_delivery_type(val):
    val_str = str(val).replace(" ", "")
    if '당일' in val_str:
        return '당일 배송'
    elif '일반' in val_str:
        return '일반 배송'
    elif '휴일' in val_str:
        return '휴일 배송'
    else:
        return '기타 배송'

df['배송대분류'] = df['배송유형'].apply(map_delivery_type)

total_inflow = df['출고번호'].nunique()
type_counts = df.groupby('배송대분류')['출고번호'].nunique().to_dict()

# [A구역]: 다이내믹 서브텍스트 생성 로직
active_types = {k: v for k, v in type_counts.items() if v > 0}
sorted_types = sorted(active_types.items(), key=lambda item: item[1], reverse=True)
formatted_texts = [f"{k.replace(' 배송', '')} {v:,}건" for k, v in sorted_types]
dynamic_sub_text = f"↑ ({' | '.join(formatted_texts)})" if formatted_texts else "↑ (데이터 없음)"

title_col, summary_col = st.columns([6, 6])
with title_col:
    st.title("🚚 물류 출고 현황 분석 대시보드")
    if '결제일시_dt' in df.columns and not df['결제일시_dt'].isna().all():
        main_max_str = df['결제일시_dt'].max().strftime('%y-%m-%d %H:%M')
        st.caption(f"(데이터 기준일시 : {main_max_str} 기준)")
with summary_col:
    st.markdown(
        f"""
        <div style="text-align: right; padding-top: 10px;">
            <div style="font-size: 20px; font-weight: bold; color: #FFFFFF;">
                📦 오늘 총 주문 유입 <span style="font-size: 28px; margin-left: 15px; color: #FFFFFF;">{total_inflow:,} 건</span>
            </div>
            <div style="font-size: 13px; color: #888888; margin-top: 4px;">
                {dynamic_sub_text}
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

st.markdown("---")

# ==============================================================================
# 8. [B/C구역] 좌/우 Split 헤더 영역
# ==============================================================================
left_header_col, right_header_col = st.columns([6, 6])

# --- [B구역]: 세부 출고 현황 ---
with left_header_col:
    st.markdown("#### 🔍 세부 출고 현황 설정")
    
    filter_col1, filter_col2 = st.columns(2)
    with filter_col1:
        available_types = [t for t in DELIVERY_TYPES if t in type_counts]
        if not available_types:
            available_types = DELIVERY_TYPES
        
        dropdown_options = ['전체'] + available_types
        selected_type = st.selectbox(
            "🔍 조회할 배송 유형 선택", 
            options=dropdown_options, 
            index=0, 
            key="app_header_selectbox"
        )

    with filter_col2:
        if selected_type == '당일 배송':
            st.markdown(
                "<div style='color: #E53935; font-size: 13.5px; margin-top: 32px; font-weight: 500;'>"
                "💡 당일 배송은 집하가 아닌 <b>'출고완료'</b> 상태 기준 집계됩니다."
                "</div>",
                unsafe_allow_html=True
            )
            delay_ratio = 1.0
        else:
            delay_ratio_percent = st.selectbox(
                "⚙️ 미집하 보정비율 (%)", 
                options=[0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100], 
                index=2,
                format_func=lambda x: f"{x}%",
                key="global_delay_ratio_selectbox"
            )
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

    if '할당상태' in group_type.columns:
        unalloc_t = group_type[group_type['할당상태'] == '재고부족']['출고번호'].nunique()
    else:
        unalloc_t = 0
    alloc_unshipped_t = max(0, unshipped_t - unalloc_t)

    sub_m1, sub_m2, sub_m3 = st.columns(3)
    sub_m1.metric(f"[{selected_type}]", f"{type_total:,}건")
    sub_m2.metric(
        "출고완료" if selected_type == '당일 배송' else "출고완료(미집하 보정)", 
        f"{adj_completed_t:,}건", 
        delta=delta_completed_text,
        delta_color="off"
    )
    
    sub_m3.metric(
        "미출고 (총 잔여)", 
        f"{unshipped_t:,}건", 
        delta=f"[할당 {alloc_unshipped_t:,}건 / 미할당 {unalloc_t:,}건]",
        delta_color="off"
    )

# --- [C구역]: 패킹 현황표 ---
with right_header_col:
    st.markdown("""
        <style>
        div[data-testid="stDataFrame"] [data-testid="stHeaderCell"] > div {
            justify-content: center !important;
            text-align: center !important;
        }
        div[data-testid="stDataFrame"] [data-testid="stHeaderCell"] p {
            text-align: center !important;
            width: 100% !important;
        }
        div[data-testid="stDataFrame"] [data-backend-type] {
            justify-content: center !important;
            text-align: center !important;
        }
        </style>
    """, unsafe_allow_html=True)

    if '온도유형' in df.columns:
        temp_counts_per_order = df.groupby('출고번호')['온도유형'].nunique()
        mixed_temp_orders = set(temp_counts_per_order[temp_counts_per_order > 1].index)
    else:
        mixed_temp_orders = set()

    def classify_packing_detail(row):
        ptype = str(row.get('패킹타입', '')).replace(" ", "")
        order_id = row.get('출고번호')
        if ptype == '이종합포':
            return '혼합' if order_id in mixed_temp_orders else '이종합포'
        return ptype

    use_cols = ['출고번호', '패킹타입', '배송집하일', '출고상태', '할당상태']
    valid_cols = [col for col in use_cols if col in group_type.columns]
    df_order_packing = group_type[valid_cols].drop_duplicates(subset=['출고번호']).copy()
    
    df_order_packing['패킹타입_세부'] = df_order_packing.apply(classify_packing_detail, axis=1)

    col_title, col_toggle = st.columns([7, 5])
    with col_title:
        st.markdown(
            f"#### 📦 [{selected_type}] 패킹 유형 현황", 
            unsafe_allow_html=True
        )
    with col_toggle:
        show_details = st.checkbox("🔘 세부 할당(대기) 상태 펼쳐보기", value=False)

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
            p_unalloc = 0
            p_packing_wait = 0
            p_alloc_wait = 0

        packing_rows.append({
            '패킹타입': p_name,
            '주문': f"{p_count:,}",
            '비율(%)': f"{p_ratio:.1f}%",
            '출고완료': f"{p_adj_shipped:,}",
            '미출고': f"{p_unshipped:,}",
            '할당(포장대기)': f"{p_packing_wait:,}",
            '할당(할당대기)': f"{p_alloc_wait:,}",
            '미할당': f"{p_unalloc:,}"
        })

    df_packing_summary = pd.DataFrame(packing_rows)
    
    if not show_details:
        df_packing_summary = df_packing_summary.drop(columns=['할당(포장대기)', '할당(할당대기)'])

    column_configs = {
        col: st.column_config.TextColumn(col, alignment="center")
        for col in df_packing_summary.columns
    }

    st.dataframe(
        df_packing_summary, 
        column_config=column_configs,
        use_container_width=True, 
        height=215,
        hide_index=True
    )

    if '기준재고명' in group_type.columns:
        ice_mask = group_type['기준재고명'].str.contains('아이스', na=False)
        ice_order_ids = set(group_type[ice_mask]['출고번호'].dropna().unique())
        total_ice = len(ice_order_ids)
        
        if total_ice > 0:
            ice_orders_df = group_type[group_type['출고번호'].isin(ice_order_ids)]
            ice_no_dry_df = ice_orders_df[~ice_orders_df['기준재고명'].str.contains('드라이아이스', na=False)]
            
            sku_counts = ice_no_dry_df.groupby('출고번호')['기준재고명'].nunique()
            ice_single = (sku_counts == 1).sum()
            ice_multi = (sku_counts >= 2).sum()
            
            ice_sub_text = f"🍦 아이스크림 주문: 총 {total_ice:,}건 (단품 {ice_single:,}건 / 혼합 {ice_multi:,}건)"
        else:
            ice_sub_text = "🍦 현재 아이스크림 주문 없음"
    else:
        ice_sub_text = "🍦 아이스크림 정보 없음"

    st.markdown(
        f"<div style='text-align: right; font-size: 13.5px; color: #4CAF50; font-weight: 500; margin-top: 5px; padding-right: 5px;'>{ice_sub_text}</div>",
        unsafe_allow_html=True
    )

st.markdown("---")

# ==============================================================================
# 9. [D구역] 메뉴별 라우터
# ==============================================================================
if selected_menu == "🚚 1. 배송 유형별 마감 예측":
    try:
        render_dispatch_tab(group_type)
    except NameError:
        st.info("🚚 1번 메뉴: 기존 배송 유형 예측 화면입니다.")
        
elif selected_menu == "🏢 2. 셀러별 상세 현황":
    try:
        render_sellers_tab(group_type)
    except NameError:
        st.info("🏢 2번 메뉴: 셀러별 상세 현황 모듈 연결 실패.")

elif selected_menu == "📦 3. 상품별 출고 현황":
    try:
        render_products_tab(group_type)
    except NameError:
        st.error("❌ `render_products_tab` 모듈을 찾을 수 없습니다. `Views/tab3_products.py` 파일의 존재 여부를 확인해 주세요.")

elif selected_menu == "⏱️ 4. 시간대별 주문 인입 분석":
    try:
        render_time_inflow_tab(group_type)
    except NameError:
        st.error("❌ `render_time_inflow_tab` 모듈을 찾을 수 없습니다.")

elif selected_menu == "🔗 5. 이종합포 조합 분석":
    st.info("🚧 5번 메뉴: 동일 상품 조합의 이종합포 묶음 분석 화면을 개발 중입니다.")