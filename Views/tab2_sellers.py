import pandas as pd
import streamlit as st

def render_sellers_tab(df):
    st.markdown("### 🏢 2. 셀러별 상세 현황")
    st.markdown("결품(재고부족)을 제외한 **'실질 작업 물량'**을 기준으로 현장 작업 진척도를 파악합니다.")
    
    if 'OM셀러명' not in df.columns:
        st.error("❌ 데이터에 'OM셀러명' 컬럼이 존재하지 않습니다.")
        return

    # 💡 1. 결품(재고부족) 데이터 원천 제외
    if '할당상태' in df.columns:
        df_active = df[df['할당상태'] != '재고부족'].copy()
    else:
        df_active = df.copy()

    if df_active.empty:
        st.warning("조건에 해당하는 작업 데이터가 없습니다.")
        return

    # 💡 2. 패킹타입 세부 분류 로직
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

    use_cols = ['출고번호', 'OM셀러명', '패킹타입', '출고상태', '온도유형']
    valid_cols = [col for col in use_cols if col in df_active.columns]
    df_orders = df_active[valid_cols].copy()
    df_orders['패킹타입_세부'] = df_orders.apply(classify_pack, axis=1)

    # 💡 3. 상단: 셀러별 작업 현황판
    st.markdown("#### 📊 셀러별 작업 현황판")
    
    view_mode = st.radio(
        "🔍 데이터 조회 기준", 
        ["전체 주문", "미출고", "출고"], 
        horizontal=True,
        label_visibility="collapsed"
    )

    df_unique_box = df_orders.drop_duplicates(subset=['출고번호']).copy()

    # 💡 [핵심 수정]: view_mode에 따라 상단 표(target_df)와 하단 표(df_bottom_base)의 기초 데이터를 동시에 필터링!
    if view_mode == "전체 주문":
        df_bottom_base = df_orders.copy()
        target_df = df_unique_box.copy()
        
        seller_stats = target_df.groupby('OM셀러명').agg(
            총주문=('출고번호', 'count'),
            출고=('출고상태', lambda x: (x == '출고완료').sum())
        ).reset_index()
        seller_stats['미출고'] = seller_stats['총주문'] - seller_stats['출고']
        seller_stats['진행률'] = (seller_stats['출고'] / seller_stats['총주문'] * 100).round(1)
        sort_col = '미출고'
        
    elif view_mode == "미출고":
        df_bottom_base = df_orders[df_orders['출고상태'] != '출고완료'].copy()
        target_df = df_unique_box[df_unique_box['출고상태'] != '출고완료'].copy()
        
        seller_stats = target_df.groupby('OM셀러명').agg(미출고=('출고번호', 'count')).reset_index()
        sort_col = '미출고'
        
    else: # "출고"
        df_bottom_base = df_orders[df_orders['출고상태'] == '출고완료'].copy()
        target_df = df_unique_box[df_unique_box['출고상태'] == '출고완료'].copy()
        
        seller_stats = target_df.groupby('OM셀러명').agg(출고=('출고번호', 'count')).reset_index()
        sort_col = '출고'

    if not target_df.empty:
        pack_pivot = target_df.pivot_table(
            index='OM셀러명', columns='패킹타입_세부', values='출고번호', aggfunc='count', fill_value=0
        ).reset_index()
        
        for p_name in ['단수', '단수단포', '단수합포', '이종합포', '혼합']:
            if p_name not in pack_pivot.columns:
                pack_pivot[p_name] = 0
                
        df_summary = pd.merge(seller_stats, pack_pivot[['OM셀러명', '단수', '단수단포', '단수합포', '이종합포', '혼합']], on='OM셀러명', how='left').fillna(0)
    else:
        df_summary = seller_stats.copy()
        for p_name in ['단수', '단수단포', '단수합포', '이종합포', '혼합']:
            df_summary[p_name] = 0

    if sort_col in df_summary.columns:
        df_summary = df_summary.sort_values(by=sort_col, ascending=False)

    cols_config = {
        'OM셀러명': st.column_config.TextColumn("셀러명", width="medium"),
        '총주문': st.column_config.NumberColumn("실질 작업대상", format="%d 건", alignment="center", width="small"),
        '출고': st.column_config.NumberColumn("출고완료", format="%d 건", alignment="center", width="small"),
        '미출고': st.column_config.NumberColumn("작업 잔여(미출고)", format="%d 건", alignment="center", width="small"),
        '진행률': st.column_config.ProgressColumn("실질 진행률 (%)", format="%.1f%%", min_value=0, max_value=100, width="small"),
        '단수': st.column_config.NumberColumn("단수", alignment="center", width="small"),
        '단수단포': st.column_config.NumberColumn("단수단포", alignment="center", width="small"),
        '단수합포': st.column_config.NumberColumn("단수합포", alignment="center", width="small"),
        '이종합포': st.column_config.NumberColumn("이종합포", alignment="center", width="small"),
        '혼합': st.column_config.NumberColumn("혼합", alignment="center", width="small"),
    }

    st.dataframe(df_summary, column_config=cols_config, use_container_width=True, hide_index=True, height=320)
    st.markdown("---")

    # 💡 4. 하단: 셀러선택 + 패킹타입 x 온도유형 피벗
    st.markdown("#### 🌡️ 셀러별 패킹타입 & 온도유형 상세 현황")
    
    if not df_summary.empty:
        sellers_list = df_summary['OM셀러명'].tolist()
        
        col_sel, _ = st.columns([1, 2])
        with col_sel:
            selected_seller = st.selectbox("🔍 상세 조회할 셀러 선택", options=sellers_list)
            
        # 💡 [핵심 수정]: 하단 데이터도 동기화된 df_bottom_base에서 추출!
        df_seller_active = df_bottom_base[df_bottom_base['OM셀러명'] == selected_seller].copy()

        if '온도유형' in df_seller_active.columns:
            order_temp_map = {}
            for oid, group in df_seller_active.groupby('출고번호'):
                temps = set(group['온도유형'].dropna().unique())
                if len(temps) > 1:
                    order_temp_map[oid] = '혼합'
                elif len(temps) == 1:
                    order_temp_map[oid] = list(temps)[0]
                else:
                    order_temp_map[oid] = '미지정'
            
            df_seller_active['온도_세부'] = df_seller_active['출고번호'].map(order_temp_map)
        else:
            df_seller_active['온도_세부'] = '미지정'

        df_calc = df_seller_active.drop_duplicates(subset=['출고번호']).copy()

        temp_pivot = df_calc.pivot_table(
            index='패킹타입_세부',
            columns='온도_세부',
            values='출고번호',
            aggfunc='count',
            fill_value=0
        ).reset_index()

        base_packing = pd.DataFrame({'패킹타입_세부': ['단수', '단수단포', '단수합포', '이종합포', '혼합']})
        temp_pivot = pd.merge(base_packing, temp_pivot, on='패킹타입_세부', how='left').fillna(0)

        for t_col in ['상온', '냉장', '냉동', '혼합']:
            if t_col not in temp_pivot.columns:
                temp_pivot[t_col] = 0

        cols_order = ['상온', '냉장', '냉동', '혼합']
        existing_cols = [c for c in cols_order if c in temp_pivot.columns]
        temp_pivot['합계'] = temp_pivot[existing_cols].sum(axis=1)

        sum_row = {'패킹타입_세부': '합계'}
        for c in existing_cols + ['합계']:
            sum_row[c] = temp_pivot[c].sum()
        
        temp_pivot = pd.concat([temp_pivot, pd.DataFrame([sum_row])], ignore_index=True)
        temp_pivot.rename(columns={'패킹타입_세부': '패킹타입'}, inplace=True)

        def highlight_sum_row(row):
            if row['패킹타입'] == '합계':
                return ['font-weight: bold; font-size: 15px !important;'] * len(row)
            return [''] * len(row)

        num_cols = ['상온', '냉장', '냉동', '혼합', '합계']
        styled_df = temp_pivot.style.apply(highlight_sum_row, axis=1).format({col: "{:,.0f} 건" for col in num_cols})

        temp_cols_config = {
            '패킹타입': st.column_config.TextColumn("패킹타입", width="medium", alignment="center"),
            '상온': st.column_config.TextColumn("상온", alignment="center"),
            '냉장': st.column_config.TextColumn("냉장", alignment="center"),
            '냉동': st.column_config.TextColumn("냉동", alignment="center"),
            '혼합': st.column_config.TextColumn("혼합", alignment="center"),
            '합계': st.column_config.TextColumn("합계", alignment="center"),
        }

        st.dataframe(
            styled_df,
            column_config=temp_cols_config,
            use_container_width=True,
            hide_index=True,
            height=260
        )
    else:
        st.info("조회할 셀러 데이터가 없습니다.")