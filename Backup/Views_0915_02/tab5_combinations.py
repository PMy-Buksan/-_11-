import pandas as pd
import streamlit as st
import re
from itertools import combinations
from collections import Counter

def render_combinations_tab(df, global_delivery_filter="전체"):
    # 💡 탭 이동 시 스크롤 요동(Layout Shift) 방지를 위한 통합 CSS 스타일
    st.markdown("""
        <style>
        /* 탭 전체 영역 최소 높이 고정으로 스크롤 요동 원천 차단 */
        div[data-testid="stTabs"] {
            min-height: 580px !important;
        }
        /* 탭 내부 여백 균일화 */
        div[data-testid="stTabContent"] {
            padding-top: 10px !important;
            padding-bottom: 20px !important;
        }
        </style>
    """, unsafe_allow_html=True)

    st.caption("💡 '똑같은 상품 조합'이나 '비슷한 공통 상품'끼리 주문을 묶어 피킹 동선과 포장 효율을 높입니다.")

    if df.empty:
        st.warning("분석할 데이터가 없습니다.")
        return

    # 1. 기본 필터링 (완전할당-미피킹 대상만)
    if '할당상태' in df.columns:
        df_active = df[df['할당상태'] == '완전할당(미피킹)'].copy()
    else:
        df_active = df.copy()

    if df_active.empty:
        st.info("현재 할당 가능한(완전할당-미피킹) 대기 물량이 없습니다.", icon="ℹ️")
        return

    # 2. 패킹타입 세부 분류 (이종합포 vs 혼합)
    if '온도유형' in df_active.columns:
        temp_counts = df_active.groupby('출고번호')['온도유형'].nunique()
        mixed_orders = set(temp_counts[temp_counts > 1].index)
    else:
        mixed_orders = set()

    def classify_pack(row):
        pt = str(row.get('패킹타입', '')).replace(" ", "")
        order_id = row.get('출고번호')
        if pt == '이종합포':
            return '혼합' if order_id in mixed_orders else '이종합포'
        return pt

    df_active['패킹타입_세부'] = df_active.apply(classify_pack, axis=1)
    df_multi = df_active[df_active['패킹타입_세부'].isin(['이종합포', '혼합'])].copy()

    if df_multi.empty:
        st.info("현재 할당 대기 중인 이종합포 및 혼합 물량이 없습니다.", icon="ℹ️")
        return

    # 2-1. 수량 계산용 컬럼 확보
    if '할당수량' in df_multi.columns:
        df_multi['계산용수량'] = pd.to_numeric(df_multi['할당수량'], errors='coerce').fillna(0)
    elif '주문수량' in df_multi.columns:
        df_multi['계산용수량'] = pd.to_numeric(df_multi['주문수량'], errors='coerce').fillna(0)
    else:
        df_multi['계산용수량'] = 1 

    # 글로벌 배송 필터 연동
    if global_delivery_filter != "전체":
        keyword = global_delivery_filter.replace(" 배송", "").strip() 
        df_multi = df_multi[df_multi['배송유형'].astype(str).str.contains(keyword)].copy()

    if df_multi.empty:
        st.info(f"메인에서 선택하신 [{global_delivery_filter}] 조건에 해당하는 물량이 없습니다.", icon="ℹ️")
        return

    # 3. 글로벌 상단 필터
    with st.container():
        st.markdown("##### 🔍 작업 대상 조건 선택")
        
        with st.expander("✂️ 이미 작업한 주문번호 제외하기 (숨기기)"):
            excluded_input = st.text_area(
                "WMS에서 이미 할당/작업 처리한 '주문번호'를 복사하여 붙여넣으세요. 실시간으로 목록에서 제외됩니다.", 
                placeholder="예: 3835001, 3835002 ... (쉼표나 띄어쓰기, 줄바꿈으로 구분)"
            )
        
        if excluded_input:
            excluded_orders = set(re.findall(r'[a-zA-Z0-9]+', excluded_input))
            if excluded_orders:
                df_multi = df_multi[~df_multi['주문번호'].astype(str).isin(excluded_orders)].copy()
                if df_multi.empty:
                    st.info("모든 대기 물량이 할당 제외 처리되었습니다.", icon="ℹ️")
                    return

        seller_counts = df_multi['OM셀러명'].value_counts().to_dict()
        priority_sellers = ["(주)아워홈", "주식회사 쿠캣", "십일번가 주식회사"]
        
        final_sellers = []
        for p in priority_sellers:
            if p in seller_counts:
                final_sellers.append(f"{p} ({seller_counts[p]}건)")
        for s, cnt in seller_counts.items():
            if s not in priority_sellers and cnt > 50:
                final_sellers.append(f"{s} ({cnt}건)")
                
        sellers_list = ["전체"] + final_sellers

        deliv_counts = df_multi['배송유형'].value_counts()
        delivery_types = ["전체"] + list(deliv_counts.index)

        col1, col2, col3 = st.columns(3)
        with col1:
            selected_seller_str = st.selectbox("🏢 셀러 선택", options=sellers_list)
            selected_seller = selected_seller_str.split(" (")[0] if selected_seller_str != "전체" else "전체"
        with col2:
            selected_delivery = st.selectbox("🚚 배송유형 선택", options=delivery_types)
        with col3:
            pack_opts = ["전체", "이종합포 (단일온도)", "혼합 (다중온도)"]
            selected_pack_str = st.selectbox("📦 포장 유형 선택", options=pack_opts)

    # 필터 적용
    df_filtered = df_multi.copy()
    if selected_delivery != "전체":
        df_filtered = df_filtered[df_filtered['배송유형'] == selected_delivery].copy()
    if selected_seller != "전체":
        df_filtered = df_filtered[df_filtered['OM셀러명'] == selected_seller].copy()
    if "이종합포" in selected_pack_str:
        df_filtered = df_filtered[df_filtered['패킹타입_세부'] == '이종합포'].copy()
    elif "혼합" in selected_pack_str:
        df_filtered = df_filtered[df_filtered['패킹타입_세부'] == '혼합'].copy()

    if df_filtered.empty:
        st.warning("선택한 조건에 해당하는 대기 물량이 없습니다.")
        return

    # SKU 코드 기준 연산
    df_filtered['기준재고번호_str'] = df_filtered['기준재고번호'].astype(str)
    box_to_items = df_filtered.groupby('출고번호')['기준재고번호_str'].unique().apply(lambda x: tuple(sorted(x)))
    box_to_orders = df_filtered.groupby('출고번호')['주문번호'].first() 
    box_to_qty = df_filtered.groupby('출고번호')['계산용수량'].sum().to_dict()
    
    sku_to_name = dict(zip(
        df_filtered['기준재고번호_str'], 
        df_filtered['기준재고명'].astype(str)
    ))

    def map_sku_to_names(sku_tuple):
        return [sku_to_name.get(sku, sku) for sku in sku_tuple]

    st.markdown("---")

    # =========================================================================================
    # 💡 [3개 탭 구성]
    # =========================================================================================
    tab_exact, tab_similar, tab_prod = st.tabs([
        "🧩 1. 확정 세트", 
        "🧩 2. 유사 세트", 
        "🎯 3. 인기 상품 (피킹 동선 단축)"
    ])

    # -----------------------------------------------------------------------------------------
    # 탭 1: 100% 확정 세트
    # -----------------------------------------------------------------------------------------
    with tab_exact:
        st.markdown("#### 1. 확정 세트 (구성품 100% 동일 묶음)")
        st.caption("💡 표 왼쪽의 체크박스를 누르면 여러 세트를 한 번에 선택하여 주문번호를 추출할 수 있습니다.")

        exact_counts = box_to_items.value_counts().reset_index()
        exact_counts.columns = ['구성품', '건수']
        exact_counts = exact_counts[exact_counts['건수'] >= 2]

        exact_cols_config = {
            '세트 분류': st.column_config.TextColumn("세트 이름", width="small"),
            '구성품_텍스트': st.column_config.TextColumn("포함 상품 목록", width="large"),
            '품목수': st.column_config.NumberColumn("상품 종류", format="%d 종", alignment="center"),
            '건수': st.column_config.NumberColumn("주문 건수", format="%d 건", alignment="center"),
            '총 피킹수량': st.column_config.NumberColumn("총 피킹 수량", format="%d 개", alignment="center")
        }

        if exact_counts.empty:
            # 💡 최소 세로 높이 유지용 박스
            st.info("100% 똑같이 구성된 상품 세트가 없습니다.", icon="ℹ️")
            st.markdown("<div style='height: 250px;'></div>", unsafe_allow_html=True)
        else:
            item_to_boxes = {}
            for b, items in box_to_items.items():
                item_to_boxes.setdefault(items, []).append(b)
                
            exact_counts['품목수'] = exact_counts['구성품'].apply(len)
            exact_counts['구성품_텍스트'] = exact_counts['구성품'].apply(lambda x: " + ".join(map_sku_to_names(x)))
            exact_counts['세트 분류'] = [f"기획세트 {i+1}" for i in range(len(exact_counts))]
            exact_counts['총 피킹수량'] = exact_counts['구성품'].apply(
                lambda x: sum(box_to_qty.get(b, 0) for b in item_to_boxes[x])
            ).astype(int)
            
            exact_display = exact_counts[['세트 분류', '구성품_텍스트', '품목수', '건수', '총 피킹수량']].copy()

            # 💡 데이터프레임 높이 230px 통일
            event_track1 = st.dataframe(
                exact_display,
                column_config=exact_cols_config,
                use_container_width=True,
                hide_index=True,
                height=230,
                on_select="rerun",
                selection_mode="multi-row", 
                key="track1"
            )

            if event_track1 and event_track1.get("selection", {}).get("rows"):
                selected_indices = event_track1["selection"]["rows"]
                all_boxes = []
                selected_names = []
                raw_total_count = 0
                
                for idx in selected_indices:
                    selected_names.append(exact_counts.iloc[idx]['세트 분류'])
                    selected_items = exact_counts.iloc[idx]['구성품']
                    raw_total_count += exact_counts.iloc[idx]['건수']
                    all_boxes.extend(item_to_boxes[selected_items])
                    
                unique_boxes = list(set(all_boxes))
                matching_orders = box_to_orders[unique_boxes].astype(str).tolist()
                order_str = ", ".join(matching_orders)
                dedup_total = len(matching_orders)
                
                df_group_exact = df_filtered[df_filtered['출고번호'].isin(unique_boxes)]
                sku_codes_exact = df_group_exact['기준재고번호'].dropna().astype(str).unique().tolist()
                sku_str_exact = ", ".join(sku_codes_exact)

                if raw_total_count > dedup_total:
                    group_title = f"[{', '.join(selected_names)}] 총 {raw_total_count}건 중 중복 제외 {dedup_total}건"
                else:
                    group_title = f"[{', '.join(selected_names)}] 총 {dedup_total}건"
                
                st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
                st.markdown(f"##### 📦 {group_title} 추출 목록")
                tab_wms_o1, tab_wms_s1 = st.tabs(["📝 WMS용 [주문번호] 복사", "🏷️ WMS용 [상품코드(SKU)] 복사"])
                
                with tab_wms_o1:
                    st.success(f"👇 **총 {dedup_total}건**의 주문번호입니다. 복사하여 WMS에 붙여넣으세요.")
                    st.code(order_str, language="text")
                with tab_wms_s1:
                    st.success(f"👇 해당 세트의 **총 {len(sku_codes_exact)}개** 고유 상품코드(SKU)입니다.")
                    st.code(sku_str_exact, language="text")
            else:
                # 클릭 전에도 바닥 높이를 살짝 비워두어 클릭 시 덜컥거림을 완화
                st.markdown("<div style='height: 100px;'></div>", unsafe_allow_html=True)

    # -----------------------------------------------------------------------------------------
    # 탭 2: 유사 세트 (공통 상품 묶음)
    # -----------------------------------------------------------------------------------------
    with tab_similar:
        col_anchor, _ = st.columns([4, 6])
        with col_anchor:
            anchor_options = [f"{i}개" for i in range(1, 9)]
            selected_anchor_str = st.selectbox("⚙️ 겹치는 공통 상품 수 설정", options=anchor_options, index=1)
            anchor_n = int(selected_anchor_str.replace("개", ""))

        st.markdown(f"#### 2. 유사 세트 (공통 상품 {anchor_n}개 묶음)")
        st.caption("💡 완전히 일치하지 않더라도, 지정한 개수만큼 상품이 겹치는 주문들을 모아서 보여줍니다.")
        
        counter_final = Counter()
        for items in box_to_items:
            calc_items = items[:25] if len(items) > 25 else items
            if len(calc_items) >= anchor_n:
                counter_final.update(combinations(calc_items, anchor_n))
        
        anchor_df = pd.DataFrame(counter_final.items(), columns=['앵커조합', '건수']).sort_values('건수', ascending=False)
        anchor_df = anchor_df[anchor_df['건수'] >= 2] 

        if anchor_df.empty:
            st.info(f"선택하신 조건에서 {anchor_n}개의 상품이 겹치는 주문이 없습니다.", icon="ℹ️")
            st.markdown("<div style='height: 250px;'></div>", unsafe_allow_html=True)
        else:
            anchor_df = anchor_df.head(20) 
            anchor_df['추천 그룹'] = [f"유사그룹 {i+1}" for i in range(len(anchor_df))]
            anchor_df['앵커_텍스트'] = anchor_df['앵커조합'].apply(lambda x: " + ".join(map_sku_to_names(x)))
            
            def get_anchor_stats(anchor):
                boxes = [b for b, items in box_to_items.items() if set(anchor).issubset(set(items))]
                all_items = set()
                total_qty = 0
                for b in boxes:
                    all_items.update(box_to_items[b])
                    total_qty += box_to_qty.get(b, 0)
                return len(all_items), total_qty

            stats = anchor_df['앵커조합'].apply(get_anchor_stats)
            anchor_df['총 필요 SKU수'] = stats.apply(lambda x: x[0])
            anchor_df['총 피킹수량'] = stats.apply(lambda x: x[1]).astype(int)
            
            anchor_display = anchor_df[['추천 그룹', '앵커_텍스트', '총 필요 SKU수', '건수', '총 피킹수량']].copy()

            exact_cols_config2 = {
                '추천 그룹': st.column_config.TextColumn("그룹 이름", width="small"),
                '앵커_텍스트': st.column_config.TextColumn("겹치는 공통 상품", width="large"),
                '총 필요 SKU수': st.column_config.NumberColumn("필요한 총 상품 수", format="%d 종", alignment="center"),
                '건수': st.column_config.NumberColumn("주문 건수", format="%d 건", alignment="center"),
                '총 피킹수량': st.column_config.NumberColumn("총 피킹 수량", format="%d 개", alignment="center")
            }

            event_track2 = st.dataframe(
                anchor_display,
                column_config=exact_cols_config2, 
                use_container_width=True,
                hide_index=True,
                height=230,
                on_select="rerun",
                selection_mode="multi-row", 
                key="track2"
            )

            if event_track2 and event_track2.get("selection", {}).get("rows"):
                selected_indices = event_track2["selection"]["rows"]
                all_boxes = []
                selected_groups = []
                raw_total_count = 0
                
                for idx in selected_indices:
                    selected_anchor = anchor_df.iloc[idx]['앵커조합']
                    selected_groups.append(anchor_df.iloc[idx]['추천 그룹'])
                    raw_total_count += anchor_df.iloc[idx]['건수']
                    matching_boxes = [b for b, items in box_to_items.items() if set(selected_anchor).issubset(set(items))]
                    all_boxes.extend(matching_boxes)
                    
                unique_boxes = list(set(all_boxes))
                matching_orders = box_to_orders[unique_boxes].astype(str).tolist()
                order_str = ", ".join(matching_orders)
                dedup_total = len(matching_orders)
                
                group_title = ", ".join(selected_groups)
                if len(group_title) > 30:
                    group_title = f"{selected_groups[0]} 외 {len(selected_groups)-1}개 그룹"
                
                st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
                st.markdown(f"##### 📦 [{group_title}] 통합 작업 리스트")
                
                tab_das, tab_wms_o, tab_wms_s = st.tabs([
                    "🛒 통합 피킹 리스트 (총 수량)", 
                    "📝 WMS용 [주문번호] 복사", 
                    "🏷️ WMS용 [상품코드(SKU)] 복사"
                ])
                
                df_group = df_filtered[df_filtered['출고번호'].isin(unique_boxes)].copy()
                df_group['기준재고명'] = df_group['기준재고명'].astype(str)
                das_list = df_group.groupby(['기준재고번호', '기준재고명'], as_index=False).agg(
                    필요총수량=('계산용수량', 'sum'),
                    포함된건수=('출고번호', 'nunique')
                )
                das_list = das_list[das_list['포함된건수'] > 0].sort_values(by='포함된건수', ascending=False)
                
                das_list['필요총수량'] = das_list['필요총수량'].astype(int)
                sku_codes = das_list['기준재고번호'].astype(str).unique().tolist()
                sku_str = ", ".join(sku_codes)
                
                with tab_das:
                    st.markdown(
                        f"<div style='text-align: right; margin-bottom: 8px; font-weight: bold; color: #4CAF50;'>"
                        f"🎯 총 피킹 상품: {len(das_list)} 종 &nbsp;&nbsp;|&nbsp;&nbsp; 📦 총 피킹 수량: {das_list['필요총수량'].sum():,} 개"
                        f"</div>", 
                        unsafe_allow_html=True
                    )
                    st.dataframe(das_list, use_container_width=True, hide_index=True, height=180)
                    
                with tab_wms_o:
                    st.success(f"👇 **총 {dedup_total}건**의 주문번호입니다.")
                    st.code(order_str, language="text")
                    
                with tab_wms_s:
                    st.success(f"👇 할당을 위한 **총 {len(sku_codes)}개**의 상품코드(SKU)입니다.")
                    st.code(sku_str, language="text")
            else:
                st.markdown("<div style='height: 100px;'></div>", unsafe_allow_html=True)

    # -----------------------------------------------------------------------------------------
    # 탭 3: 인기 상품 묶음 (피킹 동선 단축)
    # -----------------------------------------------------------------------------------------
    with tab_prod:
        st.markdown("#### 3. 다빈도 상품 집중 묶음")
        st.caption("💡 지정한 몇 가지 상품만 가져오면 한 번에 처리할 수 있는 '최대 주문 조합'을 찾아 피킹 동선을 최대로 아낍니다.")
        
        col_prod, _ = st.columns([4, 6])
        with col_prod:
            prod_opts = [f"{i}종" for i in range(3, 16)]
            target_sku_str = st.selectbox("⚙️ 한 번에 피킹할 상품 종류 수", options=prod_opts, index=2)
            target_k = int(target_sku_str.replace("종", ""))

        valid_boxes = {b: items for b, items in box_to_items.items() if len(items) <= target_k}
        
        if not valid_boxes:
            st.info(f"선택한 {target_k}종 이하 상품으로만 구성된 주문이 없습니다.", icon="ℹ️")
            st.markdown("<div style='height: 250px;'></div>", unsafe_allow_html=True)
        else:
            unique_configs = {}
            unique_qty = {}
            unique_ids = {}
            
            for b, items in valid_boxes.items():
                t = tuple(sorted(items))
                unique_configs[t] = unique_configs.get(t, 0) + 1
                unique_qty[t] = unique_qty.get(t, 0) + box_to_qty.get(b, 0)
                if t not in unique_ids:
                    unique_ids[t] = []
                unique_ids[t].append(b)

            item_counts = Counter()
            for items, count in unique_configs.items():
                for item in items:
                    item_counts[item] += count
                    
            if target_k <= 5:
                top_n = 15
            elif target_k <= 7:
                top_n = target_k + 5
            elif target_k <= 10:
                top_n = target_k + 4
            else:
                top_n = target_k + 2 
                
            top_skus = [item for item, _ in item_counts.most_common(top_n)]
            candidate_combs = set(combinations(top_skus, target_k))
            
            for t in unique_configs.keys():
                if len(t) == target_k:
                    candidate_combs.add(t)

            cluster_list = []
            for target_comb in candidate_combs:
                t_set = set(target_comb)
                covered_count = 0
                covered_qty = 0
                covered_box_ids = []
                
                for config, count in unique_configs.items():
                    if set(config).issubset(t_set):
                        covered_count += count
                        covered_qty += unique_qty[config]
                        covered_box_ids.extend(unique_ids[config])
                        
                if covered_count >= 2:
                    cluster_list.append({
                        '추천 그룹': '',
                        '집중 피킹 대상 SKU': " + ".join(map_sku_to_names(target_comb)),
                        '건수': covered_count,
                        '총 피킹수량': covered_qty,
                        'box_list': covered_box_ids
                    })
                    
            if not cluster_list:
                st.info(f"{target_k}종 묶음으로 처리할 수 있는 다수 주문 그룹이 없습니다.", icon="ℹ️")
                st.markdown("<div style='height: 250px;'></div>", unsafe_allow_html=True)
            else:
                prod_df = pd.DataFrame(cluster_list).sort_values('건수', ascending=False).head(20).reset_index(drop=True)
                prod_df['추천 그룹'] = [f"집중 {i+1}" for i in range(len(prod_df))]
                
                prod_display = prod_df[['추천 그룹', '집중 피킹 대상 SKU', '건수', '총 피킹수량']].copy()
                
                prod_cols_config = {
                    '추천 그룹': st.column_config.TextColumn("그룹 이름", width="small"),
                    '집중 피킹 대상 SKU': st.column_config.TextColumn(f"피킹할 집중 상품 ({target_k}종 이하)", width="large"),
                    '건수': st.column_config.NumberColumn("해결 가능 주문 수", format="%d 건", alignment="center"),
                    '총 피킹수량': st.column_config.NumberColumn("총 피킹 수량", format="%d 개", alignment="center")
                }

                event_track3 = st.dataframe(
                    prod_display,
                    column_config=prod_cols_config,
                    use_container_width=True,
                    hide_index=True,
                    height=230,
                    on_select="rerun",
                    selection_mode="multi-row", 
                    key="track3"
                )

                if event_track3 and event_track3.get("selection", {}).get("rows"):
                    selected_indices = event_track3["selection"]["rows"]
                    
                    all_boxes = []
                    selected_groups = []
                    raw_total_count = 0
                    
                    for idx in selected_indices:
                        selected_groups.append(prod_df.iloc[idx]['추천 그룹'])
                        raw_total_count += prod_df.iloc[idx]['건수']
                        all_boxes.extend(prod_df.iloc[idx]['box_list'])
                        
                    unique_boxes = list(set(all_boxes))
                    matching_orders = box_to_orders[unique_boxes].astype(str).tolist()
                    order_str = ", ".join(matching_orders)
                    dedup_total = len(matching_orders)
                    
                    group_title = ", ".join(selected_groups)
                    if len(group_title) > 30:
                        group_title = f"{selected_groups[0]} 외 {len(selected_groups)-1}개 그룹"
                    
                    st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
                    st.markdown(f"##### 📦 [{group_title}] 집중 피킹 작업 리스트")
                    
                    tab_das_p, tab_wms_op, tab_wms_sp = st.tabs([
                        "🛒 통합 피킹 리스트 (총 수량)", 
                        "📝 WMS용 [주문번호] 복사",
                        "🏷️ WMS용 [상품코드(SKU)] 복사"
                    ])
                    
                    df_group = df_filtered[df_filtered['출고번호'].isin(unique_boxes)].copy()
                    df_group['기준재고명'] = df_group['기준재고명'].astype(str)
                    das_list = df_group.groupby(['기준재고번호', '기준재고명'], as_index=False).agg(
                        필요총수량=('계산용수량', 'sum'),
                        포함된건수=('출고번호', 'nunique')
                    )
                    das_list = das_list[das_list['포함된건수'] > 0].sort_values(by='포함된건수', ascending=False)
                    
                    das_list['필요총수량'] = das_list['필요총수량'].astype(int)
                    sku_codes = das_list['기준재고번호'].astype(str).unique().tolist()
                    sku_str = ", ".join(sku_codes)
                    
                    with tab_das_p:
                        st.markdown(
                            f"<div style='text-align: right; margin-bottom: 8px; font-weight: bold; color: #4CAF50;'>"
                            f"🎯 총 피킹 상품: {len(das_list)} 종 &nbsp;&nbsp;|&nbsp;&nbsp; 📦 총 피킹 수량: {das_list['필요총수량'].sum():,} 개"
                            f"</div>", 
                            unsafe_allow_html=True
                        )
                        st.dataframe(das_list, use_container_width=True, hide_index=True, height=180)
                        
                    with tab_wms_op:
                        st.success(f"👇 **총 {dedup_total}건**의 주문번호입니다.")
                        st.code(order_str, language="text")
                        
                    with tab_wms_sp:
                        st.success(f"👇 할당을 위한 **총 {len(sku_codes)}개**의 상품코드(SKU)입니다.")
                        st.code(sku_str, language="text")
                else:
                    st.markdown("<div style='height: 100px;'></div>", unsafe_allow_html=True)