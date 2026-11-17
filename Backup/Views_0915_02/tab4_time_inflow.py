import pandas as pd
import streamlit as st

def render_time_inflow_tab(df):
    if df.empty:
        st.warning("분석할 데이터가 없습니다.")
        return

    # 💡 1. 결품(재고부족) 제외
    if '할당상태' in df.columns:
        df_active = df[df['할당상태'] != '재고부족'].copy()
    else:
        df_active = df.copy()

    # 💡 2. 데이터 기준일시 계산
    max_dt_str = "26-09-09 22:34"
    max_hour = 22
    max_date = None

    if '결제일시' in df_active.columns:
        date_str = df_active['결제일시'].astype(str).str.replace(r'\D', '', regex=True)
        df_active['결제일시_dt'] = pd.to_datetime(date_str, format='%Y%m%d%H%M%S', errors='coerce')
        
        valid_dts = df_active['결제일시_dt'].dropna()
        if not valid_dts.empty:
            max_dt = valid_dts.max()
            max_dt_str = max_dt.strftime('%y-%m-%d %H:%M')
            max_hour = max_dt.hour
            max_date = max_dt.date()

    st.markdown("### ⏱️ 4. 시간대별 주문 인입 분석")
    st.markdown(
        f"<div style='color: #888888; font-size: 14px; font-weight: 500; margin-top: -12px; margin-bottom: 15px;'>"
        f"(데이터 기준일시 : <span style='color: #4CAF50; font-weight: bold;'>{max_dt_str}</span> 기준)"
        f"</div>",
        unsafe_allow_html=True
    )

    # 💡 3. 패킹타입 세부 분류
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

    df_box = df_active.drop_duplicates(subset=['출고번호']).copy()
    df_box['패킹타입_세부'] = df_box.apply(classify_pack, axis=1)

    # 💡 4. 시간대 정밀 재분류
    def classify_exact_time(row):
        dt = row.get('결제일시_dt')
        if pd.isna(dt):
            return '00~07시'
        if max_date and dt.date() < max_date:
            return '기준일 이전'
        
        h = dt.hour
        if 0 <= h <= 7:
            return '00~07시'
        elif h == max_hour:
            return f"{h:02d}시 (진행중)"
        else:
            return f"{h:02d}시"

    df_box['시간대_표시'] = df_box.apply(classify_exact_time, axis=1)

    hours_cols = ['기준일 이전', '00~07시']
    for h in range(8, max_hour + 1):
        if h == max_hour:
            hours_cols.append(f"{h:02d}시 (진행중)")
        else:
            hours_cols.append(f"{h:02d}시")

    # 💡 5. 공통 피벗 생성 함수
    def build_time_pivot(data_df, group_col):
        pivot = data_df.pivot_table(
            index=group_col,
            columns='시간대_표시',
            values='출고번호',
            aggfunc='count',
            fill_value=0
        ).reset_index()

        for h in hours_cols:
            if h not in pivot.columns:
                pivot[h] = 0

        pivot['합계'] = pivot[hours_cols].sum(axis=1)

        completed_hours = [h for h in hours_cols if '(진행중)' not in h]
        valid_h_cnt = max(1, len(completed_hours))
        pivot['평균 인입량'] = (pivot[completed_hours].sum(axis=1) / valid_h_cnt).round().astype(int)

        peak_candidates = [h for h in hours_cols if h not in ['기준일 이전', '00~07시']]

        def find_peak_hour(row):
            max_val = 0
            peak_h = "-"
            for h in peak_candidates:
                if row[h] > max_val:
                    max_val = row[h]
                    peak_h = h.replace(" (진행중)", "")
            return peak_h if max_val > 0 else "-"

        pivot['🔥 피크시간대'] = pivot.apply(find_peak_hour, axis=1)
        pivot = pivot.sort_values(by='합계', ascending=False).reset_index(drop=True)

        sum_row = {group_col: '전체 합계', '🔥 피크시간대': '-'}
        for h in hours_cols + ['합계']:
            sum_row[h] = int(pivot[h].sum())
        
        sum_row['평균 인입량'] = int(round(sum(sum_row[h] for h in completed_hours) / valid_h_cnt))

        max_sum_val = 0
        peak_sum_h = "-"
        for h in peak_candidates:
            if sum_row[h] > max_sum_val:
                max_sum_val = sum_row[h]
                peak_sum_h = h.replace(" (진행중)", "")
        sum_row['🔥 피크시간대'] = peak_sum_h

        sum_df = pd.DataFrame([sum_row])

        cols_order = [group_col, '🔥 피크시간대', '합계', '평균 인입량'] + hours_cols
        pivot = pivot[cols_order]
        sum_df = sum_df[cols_order]

        return pivot, sum_df, hours_cols

    # 💡 6. [전체 합계] 상단 고정 표
    st.markdown("##### 📊 전체 합계 유입 현황 (고정)")
    
    _, sum_df_total, _ = build_time_pivot(df_box, 'OM셀러명')
    sum_df_total.rename(columns={'OM셀러명': '구분'}, inplace=True)

    format_dict = {col: "{:,.0f} 건" for col in hours_cols + ['합계', '평균 인입량']}
    
    sum_cols_config = {
        '구분': st.column_config.TextColumn("구분", width="small"),
        '🔥 피크시간대': st.column_config.TextColumn("🔥 피크", alignment="center"),
        '합계': st.column_config.TextColumn("합계", alignment="center"),
        '평균 인입량': st.column_config.TextColumn("평균", alignment="center")
    }
    for h in hours_cols:
        sum_cols_config[h] = st.column_config.TextColumn(h, alignment="center")

    styled_sum_df = sum_df_total.style.apply(
        lambda x: ['font-weight: bold; font-size: 15px !important; background-color: rgba(76, 175, 80, 0.15);'] * len(x), axis=1
    ).format(format_dict)

    st.dataframe(
        styled_sum_df,
        column_config=sum_cols_config,
        use_container_width=True,
        hide_index=True,
        height=75
    )

    # 💡 7. [상단]: 조회 기준 토글 (셀러별 vs 판매채널별)
    st.markdown("#### 🔍 1. 상세 기준별 시간대 주문 인입 현황")
    
    col_radio, _ = st.columns([5, 5])
    with col_radio:
        view_mode = st.radio(
            "조회 기준을 선택하세요:", 
            ["🏢 셀러별", "🛒 판매채널별"], 
            horizontal=True,
            label_visibility="collapsed"
        )
    
    if view_mode == "🏢 셀러별":
        group_col = 'OM셀러명'
        group_label = "셀러명"
    else:
        group_col = '판매채널'
        group_label = "판매채널명"

    if group_col not in df_box.columns:
        st.error(f"❌ '{group_col}' 컬럼이 존재하지 않습니다.")
        return

    main_pivot, _, hours_cols = build_time_pivot(df_box, group_col)

    main_cols_config = {
        group_col: st.column_config.TextColumn(group_label, width="medium"),
        '🔥 피크시간대': st.column_config.TextColumn("🔥 피크", alignment="center"),
        '합계': st.column_config.TextColumn("합계", alignment="center"),
        '평균 인입량': st.column_config.TextColumn("평균", alignment="center")
    }
    for h in hours_cols:
        main_cols_config[h] = st.column_config.TextColumn(h, alignment="center")

    st.caption(f"👇 표의 행을 클릭하시면 하단에 연동된 상세 현황(패킹/교차)이 표시됩니다.")

    styled_main_df = main_pivot.style.format(format_dict)

    event = st.dataframe(
        styled_main_df,
        column_config=main_cols_config,
        use_container_width=True,
        hide_index=True,
        height=280,
        on_select="rerun",
        selection_mode="single-row"
    )

    # 💡 8. 클릭 이벤트 감지
    selected_item = "전체 합계"
    if event and event.get("selection", {}).get("rows"):
        selected_idx = event["selection"]["rows"][0]
        selected_item = main_pivot[group_col].iloc[selected_idx]

    st.markdown("---")

    # 💡 9. [하단]: 서브 탭을 활용한 교차 상세 분석
    st.markdown(f"#### 🔍 2. [{selected_item}] 세부 현황 분석")

    # 교차 분석할 대상 컬럼 설정
    cross_col = '판매채널' if group_col == 'OM셀러명' else 'OM셀러명'
    cross_label = '판매채널명' if group_col == 'OM셀러명' else '셀러명'
    tab_name_2 = f"🛒 {cross_label}별 상세" if group_col == 'OM셀러명' else f"🏢 {cross_label}별 상세"

    if selected_item == "전체 합계":
        df_selected = df_box.copy() 
    else:
        df_selected = df_box[df_box[group_col] == selected_item].copy()

    if df_selected.empty:
        st.info(f"선택한 {group_label}의 데이터가 없습니다.")
        return

    # 하단 탭 2개 분리
    tab_pack, tab_cross = st.tabs(["📦 패킹타입별 상세", tab_name_2])

    def render_detail_table(pivot_df, sum_df, col_name, display_name):
        pivot_df.rename(columns={col_name: display_name}, inplace=True)
        sum_df.rename(columns={col_name: display_name}, inplace=True)
        
        combined_df = pd.concat([sum_df, pivot_df], ignore_index=True)

        def highlight_sum(row):
            if row[display_name] == '전체 합계':
                return ['font-weight: bold; font-size: 15px !important; background-color: rgba(255, 255, 255, 0.05);'] * len(row)
            return [''] * len(row)

        styled_df = combined_df.style.apply(highlight_sum, axis=1).format(format_dict)

        cols_config = {
            display_name: st.column_config.TextColumn(display_name, width="medium"),
            '🔥 피크시간대': st.column_config.TextColumn("🔥 피크", alignment="center"),
            '합계': st.column_config.TextColumn("합계", alignment="center"),
            '평균 인입량': st.column_config.TextColumn("평균", alignment="center")
        }
        for h in hours_cols:
            cols_config[h] = st.column_config.TextColumn(h, alignment="center")

        st.dataframe(
            styled_df,
            column_config=cols_config,
            use_container_width=True,
            hide_index=True,
            height=280
        )

    # 탭 1: 패킹타입별 상세
    with tab_pack:
        pack_pivot, pack_sum, _ = build_time_pivot(df_selected, '패킹타입_세부')
        render_detail_table(pack_pivot, pack_sum, '패킹타입_세부', '패킹타입')

    # 탭 2: 교차 분석 (셀러/채널 상호 전환)
    with tab_cross:
        if cross_col in df_box.columns:
            cross_pivot, cross_sum, _ = build_time_pivot(df_selected, cross_col)
            render_detail_table(cross_pivot, cross_sum, cross_col, cross_label)
        else:
            st.error(f"데이터에 '{cross_col}' 컬럼이 없습니다.")