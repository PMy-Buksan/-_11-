import pandas as pd
import streamlit as st

def render_products_tab(df):
    st.markdown("### 📦 3. 상품별 출고 현황")
    st.markdown("결품(재고부족)을 제외한 **'실질 작업 물량'** 기준의 상품별 라인(단수/이종) 현황 및 합포 조합을 분석합니다.")

    # 필수 컬럼 체크
    required_cols = ['OM셀러명', '출고번호', '출고상태']
    item_col = '기준재고명' if '기준재고명' in df.columns else ('상품명' if '상품명' in df.columns else None)
    code_col = '기준재고번호' if '기준재고번호' in df.columns else ('상품코드' if '상품코드' in df.columns else None)
    
    if not all(col in df.columns for col in required_cols) or not item_col:
        st.error("❌ 필수 데이터 컬럼(셀러명, 출고번호, 상품명 등)이 부족하여 화면을 렌더링할 수 없습니다.")
        return

    # 💡 1. 결품(재고부족) 데이터 원천 제외
    if '할당상태' in df.columns:
        df_active = df[df['할당상태'] != '재고부족'].copy()
    else:
        df_active = df.copy()

    if df_active.empty:
        st.warning("조건에 해당하는 작업 데이터가 없습니다.")
        return

    # 💡 2. 패킹타입 세부 분류 (단수 vs 이종 vs 혼합 분류)
    if '온도유형' in df_active.columns:
        temp_counts = df_active.groupby('출고번호')['온도유형'].nunique()
        mixed_orders = set(temp_counts[temp_counts > 1].index)
    else:
        mixed_orders = set()

    def classify_pack_detail(row):
        pt = str(row.get('패킹타입', '')).replace(" ", "")
        order_id = row.get('출고번호')
        if pt == '이종합포':
            return '혼합' if order_id in mixed_orders else '이종합포'
        elif pt == '혼합' or order_id in mixed_orders:
            return '혼합'
        return '단수'

    df_active['패킹_세부'] = df_active.apply(classify_pack_detail, axis=1)
    df_active['패킹_그룹'] = df_active['패킹_세부'].apply(lambda x: '이종' if x in ['이종합포', '혼합'] else '단수')

    # 💡 3. 상단 필터 레이아웃
    col_filter1, col_filter2 = st.columns([6, 4])
    
    with col_filter1:
        view_mode = st.radio(
            "🔍 데이터 조회 기준", 
            ["전체 주문", "미출고", "출고"], 
            horizontal=True,
            key="prod_view_mode"
        )
        
    with col_filter2:
        sellers = ["전체"] + sorted(list(df_active['OM셀러명'].dropna().unique()))
        selected_seller = st.selectbox("🏢 셀러 선택", options=sellers, key="prod_seller_select")

    # 상단 필터 적용
    df_filtered = df_active.copy()
    if view_mode == "미출고":
        df_filtered = df_filtered[df_filtered['출고상태'] != '출고완료']
    elif view_mode == "출고":
        df_filtered = df_filtered[df_filtered['출고상태'] == '출고완료']

    if selected_seller != "전체":
        df_filtered = df_filtered[df_filtered['OM셀러명'] == selected_seller]

    st.markdown("#### 📊 상품별 출고 현황")

    if df_filtered.empty:
        st.info("선택한 조건에 해당하는 데이터가 없습니다.")
        return

    # 💡 4. 상단 표 집계 (이종 내림차순 정렬)
    group_cols = ['OM셀러명', item_col]
    if code_col:
        group_cols.insert(1, code_col)

    df_unique_item_box = df_filtered.drop_duplicates(subset=['출고번호', item_col]).copy()

    pivot_df = df_unique_item_box.pivot_table(
        index=group_cols,
        columns='패킹_그룹',
        values='출고번호',
        aggfunc='count',
        fill_value=0
    ).reset_index()

    for col in ['단수', '이종']:
        if col not in pivot_df.columns:
            pivot_df[col] = 0

    pivot_df['종합'] = pivot_df['단수'] + pivot_df['이종']
    pivot_df = pivot_df.sort_values(by=['이종', '종합'], ascending=[False, False])

    rename_dict = {
        'OM셀러명': '셀러명',
        item_col: '상품명',
        '단수': '단수 건수',
        '이종': '이종 건수',
        '종합': '종합 건수'
    }
    if code_col:
        rename_dict[code_col] = '기준재고번호'

    pivot_df.rename(columns=rename_dict, inplace=True)

    summary_cols_config = {
        '셀러명': st.column_config.TextColumn("셀러명", width="medium"),
        '기준재고번호': st.column_config.TextColumn("기준재고번호", width="medium"),
        '상품명': st.column_config.TextColumn("상품명", width="large"),
        '단수 건수': st.column_config.NumberColumn("단수", format="%d 건", alignment="center"),
        '이종 건수': st.column_config.NumberColumn("이종", format="%d 건", alignment="center"),
        '종합 건수': st.column_config.NumberColumn("종합", format="%d 건", alignment="center"),
    }

    st.dataframe(
        pivot_df,
        column_config=summary_cols_config,
        use_container_width=True,
        hide_index=True,
        height=320
    )

    st.markdown("---")

    # 💡 5. [하단 2단 레이아웃]: 이종합포 동시 구매 조합 상세 분석
    st.markdown("#### 🔗 이종합포 동시 구매 조합 상세 분석")
    st.caption("선택한 상품이 '이종합포/혼합'으로 출고될 때 함께 포장되는 세트 조합 및 연관 상품 내역입니다.")

    product_options = pivot_df[pivot_df['이종 건수'] > 0]['상품명'].tolist()
    if not product_options:
        product_options = pivot_df['상품명'].tolist()
    
    col_target_prod, _ = st.columns([2, 1])
    with col_target_prod:
        selected_product = st.selectbox("🔍 연관 조합을 확인할 상품 선택", options=product_options)

    # 선택된 상품의 이종합포 출고번호 추출
    target_orders_df = df_active[
        (df_active[item_col] == selected_product) & 
        (df_active['패킹_그룹'] == '이종')
    ]
    target_orders = set(target_orders_df['출고번호'].unique())

    if not target_orders:
        st.info(f"💡 **'{selected_product}'** 상품은 이종합포(합포/혼합) 출고 건이 없습니다.")
    else:
        df_combo_orders = df_active[df_active['출고번호'].isin(target_orders)].copy()
        df_combo_items = df_combo_orders[df_combo_orders[item_col] != selected_product].copy()

        # ----------------------------------------------------
        # 💡 [2안 적용]: 좌측 요약 카드 + 우측 상세 표
        # ----------------------------------------------------
        col_summary_card, col_detail_table = st.columns([3, 9])

        # A. [좌측]: 추천 2안 (작업 잔여 & 병목 추적형 카드)
        with col_summary_card:
            total_combo_boxes = len(target_orders)
            
            # 1. 미출고 잔여 계산
            unshipped_orders_set = set(df_combo_orders[df_combo_orders['출고상태'] != '출고완료']['출고번호'].unique())
            unshipped_cnt = len(unshipped_orders_set)
            unshipped_rate = (unshipped_cnt / total_combo_boxes * 100) if total_combo_boxes > 0 else 0.0

            # 2. 미출고 병목 연관 상품 1위 추적
            df_unshipped_items = df_combo_items[df_combo_items['출고번호'].isin(unshipped_orders_set)]
            if not df_unshipped_items.empty:
                bottleneck_series = df_unshipped_items.groupby(item_col)['출고번호'].nunique().nlargest(1)
                bottleneck_item = bottleneck_series.index[0]
                bottleneck_cnt = bottleneck_series.values[0]
                bottleneck_str = f"<b>{bottleneck_item}</b> ({bottleneck_cnt:,}건 잔여)"
            else:
                bottleneck_str = "지연 유발 상품 없음 (완료)"

            # 3. 박스당 평균 품목수(SKU) 계산
            avg_sku_per_box = df_combo_orders.groupby('출고번호')[item_col].nunique().mean()

            st.markdown(
                f"""
                <div style="background-color: var(--background-secondary, #1E1E1E); padding: 18px; border-radius: 8px; border: 1px solid #333333;">
                    <div style="font-size: 16px; font-weight: bold; margin-bottom: 12px; color: #FFFFFF;">📊 작업 잔여 & 병목 추적 요약</div>
                    <div style="font-size: 13.5px; line-height: 1.8; color: #DDDDDD;">
                        • <b>이종합포 총 물량</b> : <b>{total_combo_boxes:,}건</b><br>
                        • <b>🚨 미출고 잔여</b> : <span style="color: #FF5252; font-weight: bold;">{unshipped_cnt:,}건</span> 
                          <span style="font-size: 12px; color: #888888;">(잔여율 {unshipped_rate:.1f}%)</span><br>
                        • <b>주요 병목 연관 상품</b> :<br>
                        <div style="background-color: var(--background-primary, #121212); padding: 8px 10px; border-radius: 4px; font-size: 12px; margin-top: 4px; margin-bottom: 8px; color: #FFB74D; word-break: keep-all;">
                            {bottleneck_str}
                        </div>
                        • <b>박스당 평균 품목수</b> : <b>{avg_sku_per_box:.1f}개 SKU</b> / 박스
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )

        # B. [우측]: 함께 묶인 연관 상품 세부 현황 표
        with col_detail_table:
            if df_combo_items.empty:
                st.info("함께 출고된 다른 연관 상품이 없습니다.")
            else:
                group_keys = ['OM셀러명', item_col]
                if code_col:
                    group_keys.insert(1, code_col)

                combo_stats = df_combo_items.groupby(group_keys).agg(
                    동시출고건수=('출고번호', 'nunique')
                ).reset_index()

                # 정확한 잔여 미출고 박스 수 계산
                unshipped_boxes = df_combo_items[df_combo_items['출고상태'] != '출고완료'].groupby(group_keys)['출고번호'].nunique().reset_index()
                unshipped_boxes.rename(columns={'출고번호': '잔여_미출고_건수'}, inplace=True)

                combo_stats = pd.merge(combo_stats, unshipped_boxes, on=group_keys, how='left').fillna(0)
                combo_stats['잔여_미출고_건수'] = combo_stats['잔여_미출고_건수'].astype(int)

                # 동시 출고 비중 (%)
                combo_stats['동시출고비중'] = (combo_stats['동시출고건수'] / total_combo_boxes * 100).round(1)
                combo_stats = combo_stats.sort_values(by='동시출고건수', ascending=False)

                combo_rename = {
                    'OM셀러명': '셀러명',
                    item_col: '기준재고명',
                    '동시출고건수': '동시 출고건수',
                    '동시출고비중': '동시 출고 비중',
                    '잔여_미출고_건수': '잔여(미출고)'
                }
                if code_col:
                    combo_rename[code_col] = '기준재고번호'

                combo_stats.rename(columns=combo_rename, inplace=True)

                combo_cols_config = {
                    '셀러명': st.column_config.TextColumn("셀러명", width="small"),
                    '기준재고번호': st.column_config.TextColumn("기준재고번호", width="medium"),
                    '기준재고명': st.column_config.TextColumn("기준재고명", width="large"),
                    '동시 출고건수': st.column_config.NumberColumn("동시 출고건수", format="%d 건", alignment="center"),
                    '동시 출고 비중': st.column_config.ProgressColumn("동시 출고 비중", format="%.1f%%", min_value=0, max_value=100),
                    '잔여(미출고)': st.column_config.NumberColumn("잔여(미출고)", format="%d 건", alignment="center"),
                }

                st.dataframe(
                    combo_stats,
                    column_config=combo_cols_config,
                    use_container_width=True,
                    hide_index=True,
                    height=280
                )