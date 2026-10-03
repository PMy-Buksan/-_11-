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

    # 💡 2. 패킹타입 세부 분류 (공통)
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

    # 💡 3. 전일 이월 모드 단독 실행 여부 파악
    is_only_prev = False
    if '데이터구분' in df_box.columns and (df_box['데이터구분'] == '전일 이월').all():
        is_only_prev = True

    # ==============================================================================
    # 🟢 [모드 A] 글로벌 필터가 '전일 이월'일 때 ➔ "출고예정일별" 분석 화면 제공
    # ==============================================================================
    if is_only_prev:
        st.markdown("### 📅 4. 전일 이월 미출고 잔여건 분석")
        st.markdown(
            f"<div style='color: #888888; font-size: 14px; font-weight: 500; margin-top: -12px; margin-bottom: 15px;'>"
            f"(시간대 대신 <span style='color: #E53935; font-weight: bold;'>출고예정일 기준</span>으로 요약됩니다)</div>",
            unsafe_allow_html=True
        )

        if '출고예정일' in df_box.columns:
            # 💡 [버그 픽스] 1970-01-01 오류 방어. 8자리 숫자/날짜 포맷으로 강제 추출
            clean_date_str = df_box['출고예정일'].astype(str).str.replace(r'\D', '', regex=True).str[:8]
            df_box['출고예정일_표시'] = pd.to_datetime(clean_date_str, format='%Y%m%d', errors='coerce').dt.strftime('%Y-%m-%d')
            df_box['출고예정일_표시'] = df_box['출고예정일_표시'].fillna('예정일 미상')
        else:
            df_box['출고예정일_표시'] = '예정일 미상'

        date_cols = sorted([d for d in df_box['출고예정일_표시'].unique() if d != '예정일 미상'])
        if '예정일 미상' in df_box['출고예정일_표시'].unique():
            date_cols.append('예정일 미상')

        def build_date_pivot(data_df, group_col):
            pivot = data_df.pivot_table(index=group_col, columns='출고예정일_표시', values='출고번호', aggfunc='count', fill_value=0).reset_index()
            for c in date_cols:
                if c not in pivot.columns: pivot[c] = 0
            pivot['합계'] = pivot[date_cols].sum(axis=1)
            pivot = pivot.sort_values(by='합계', ascending=False).reset_index(drop=True)

            sum_row = {group_col: '전체 합계'}
            for c in date_cols + ['합계']:
                sum_row[c] = int(pivot[c].sum())
            
            sum_df = pd.DataFrame([sum_row])
            cols_order = [group_col, '합계'] + date_cols
            return pivot[cols_order], sum_df[cols_order], date_cols

        col_radio, _ = st.columns([5, 5])
        with col_radio:
            view_mode = st.radio("조회 기준을 선택하세요:", ["🏢 셀러별", "🛒 판매채널별"], horizontal=True, label_visibility="collapsed")
        
        group_col = 'OM셀러명' if view_mode == "🏢 셀러별" else '판매채널'
        group_label = "셀러명" if view_mode == "🏢 셀러별" else "판매채널명"

        if group_col not in df_box.columns:
            st.error(f"❌ '{group_col}' 컬럼이 존재하지 않습니다.")
            return

        main_pivot, main_sum, _ = build_date_pivot(df_box, group_col)
        
        date_cols_config = {
            group_col: st.column_config.TextColumn(group_label, width="medium"),
            '합계': st.column_config.NumberColumn("합계", format="%d 건", alignment="center")
        }
        for d in date_cols:
            date_cols_config[d] = st.column_config.NumberColumn(d, format="%d 건", alignment="center")

        st.markdown("##### 📊 전체 합계 유입 현황 (고정)")
        main_sum.rename(columns={group_col: group_label}, inplace=True)
        styled_sum = main_sum.style.apply(lambda x: ['font-weight: bold; font-size: 15px !important; background-color: rgba(76, 175, 80, 0.15);'] * len(x), axis=1)
        st.dataframe(styled_sum, column_config=date_cols_config, use_container_width=True, hide_index=True, height=75)

        st.markdown("#### 🔍 1. 상세 기준별 출고예정일 현황")
        st.caption(f"👇 표의 행을 클릭하시면 하단에 연동된 상세 현황(패킹/교차)이 표시됩니다.")
        main_pivot.rename(columns={group_col: group_label}, inplace=True)
        event = st.dataframe(main_pivot, column_config=date_cols_config, use_container_width=True, hide_index=True, height=280, on_select="rerun", selection_mode="single-row")

        selected_item = "전체 합계"
        if event and event.get("selection", {}).get("rows"):
            selected_idx = event["selection"]["rows"][0]
            selected_item = main_pivot[group_label].iloc[selected_idx]

        st.markdown("---")
        st.markdown(f"#### 🔍 2. [{selected_item}] 세부 현황 분석")

        cross_col = '판매채널' if group_col == 'OM셀러명' else 'OM셀러명'
        cross_label = '판매채널명' if group_col == 'OM셀러명' else '셀러명'
        
        df_selected = df_box.copy() if selected_item == "전체 합계" else df_box[df_box[group_col] == selected_item].copy()

        tab_pack, tab_cross = st.tabs(["📦 패킹타입별 상세", f"{'🛒' if group_col == 'OM셀러명' else '🏢'} {cross_label}별 상세"])

        def render_sub_date_table(pivot_df, sum_df, col_name, display_name):
            pivot_df.rename(columns={col_name: display_name}, inplace=True)
            sum_df.rename(columns={col_name: display_name}, inplace=True)
            combined_df = pd.concat([sum_df, pivot_df], ignore_index=True)

            styled_df = combined_df.style.apply(lambda row: ['font-weight: bold; font-size: 15px !important; background-color: rgba(255, 255, 255, 0.05);'] * len(row) if row[display_name] == '전체 합계' else [''] * len(row), axis=1)
            
            sub_config = dict(date_cols_config)
            sub_config[display_name] = st.column_config.TextColumn(display_name, width="medium")
            if group_label in sub_config and display_name != group_label: del sub_config[group_label]

            st.dataframe(styled_df, column_config=sub_config, use_container_width=True, hide_index=True, height=280)

        with tab_pack:
            pack_pivot, pack_sum, _ = build_date_pivot(df_selected, '패킹타입_세부')
            render_sub_date_table(pack_pivot, pack_sum, '패킹타입_세부', '패킹타입')

        with tab_cross:
            if cross_col in df_box.columns:
                cross_pivot, cross_sum, _ = build_date_pivot(df_selected, cross_col)
                render_sub_date_table(cross_pivot, cross_sum, cross_col, cross_label)

    # ==============================================================================
    # 🔵 [모드 B] 일반 시간대 분석 (글로벌 필터가 '금일 신규' 또는 '전체'일 때)
    # ==============================================================================
    else:
        max_dt_str = "미확인"
        max_hour = 0
        max_date = None

        df_today = df_box[df_box['데이터구분'] == '금일 신규'] if '데이터구분' in df_box.columns else df_box
        
        if '결제일시_dt' not in df_today.columns and '결제일시' in df_today.columns:
            date_str = df_today['결제일시'].astype(str).str.replace(r'\D', '', regex=True)
            df_today['결제일시_dt'] = pd.to_datetime(date_str, format='%Y%m%d%H%M%S', errors='coerce')

        if '결제일시_dt' in df_today.columns:
            valid_dts = df_today['결제일시_dt'].dropna()
            if not valid_dts.empty:
                max_dt = valid_dts.max()
                max_dt_str = max_dt.strftime('%y-%m-%d %H:%M')
                max_hour = max_dt.hour
                max_date = max_dt.date()

        st.markdown("### ⏱️ 4. 시간대별 주문 인입 분석")
        st.markdown(
            f"<div style='color: #888888; font-size: 14px; font-weight: 500; margin-top: -12px; margin-bottom: 15px;'>"
            f"(데이터 기준일시 : <span style='color: #4CAF50; font-weight: bold;'>{max_dt_str}</span> 기준)</div>",
            unsafe_allow_html=True
        )

        def classify_exact_time(row):
            if row.get('데이터구분') == '전일 이월':
                return '기준일 이전'
                
            dt = row.get('결제일시_dt')
            if pd.isna(dt): return '00~07시'
            if max_date and dt.date() < max_date: return '기준일 이전'
            
            h = dt.hour
            if 0 <= h <= 7: return '00~07시'
            elif h == max_hour: return f"{h:02d}시 (진행중)"
            else: return f"{h:02d}시"

        if '결제일시_dt' not in df_box.columns and '결제일시' in df_box.columns:
            date_str = df_box['결제일시'].astype(str).str.replace(r'\D', '', regex=True)
            df_box['결제일시_dt'] = pd.to_datetime(date_str, format='%Y%m%d%H%M%S', errors='coerce')

        df_box['시간대_표시'] = df_box.apply(classify_exact_time, axis=1)

        hours_cols = ['기준일 이전', '00~07시']
        for h in range(8, max_hour + 1):
            if h == max_hour: hours_cols.append(f"{h:02d}시 (진행중)")
            else: hours_cols.append(f"{h:02d}시")

        def build_time_pivot(data_df, group_col):
            pivot = data_df.pivot_table(index=group_col, columns='시간대_표시', values='출고번호', aggfunc='count', fill_value=0).reset_index()
            for h in hours_cols:
                if h not in pivot.columns: pivot[h] = 0

            # 💡 [새로운 로직 반영] 정규 완료 시간대 리스트 (피크/평균 탐색용)
            peak_candidates = [h for h in hours_cols if h not in ['기준일 이전', '00~07시'] and '(진행중)' not in h]

            def calc_peak_and_avg(row):
                # 1. 1차 최고점(후보) 찾기
                max_val = -1
                candidate_h = None
                for h in peak_candidates:
                    if row[h] > max_val:
                        max_val = row[h]
                        candidate_h = h
                
                true_peak_h = "-"
                # 2. 진짜 피크 검증 로직 (30% 룰 적용)
                if candidate_h and max_val > 0:
                    if candidate_h == '08시':
                        true_peak_h = "-" # 08시는 무조건 일반타임 (피크 없음)
                    else:
                        idx = peak_candidates.index(candidate_h)
                        if idx > 0:
                            prev_h = peak_candidates[idx - 1]
                            prev_val = row[prev_h]
                            if prev_val == 0:
                                true_peak_h = candidate_h # 이전 값이 0이면 무조건 피크 인정
                            else:
                                growth = (max_val - prev_val) / prev_val
                                if growth >= 0.30:
                                    true_peak_h = candidate_h
                                else:
                                    true_peak_h = "-" # 30% 이내면 피크 기각 (일반타임)

                # 3. 평균 인입량 계산 (최근 3시간, 진짜 피크 제외)
                collected_vals = []
                for h in reversed(peak_candidates):
                    if h == true_peak_h: continue # 진짜 피크만 스킵
                    collected_vals.append(row[h])
                    if len(collected_vals) == 3: break
                
                avg_val = int(round(sum(collected_vals) / len(collected_vals))) if collected_vals else 0
                return pd.Series([true_peak_h, avg_val])

            # 피크시간대 및 평균 인입량 일괄 적용
            pivot[['🔥 피크시간대', '평균 인입량']] = pivot.apply(calc_peak_and_avg, axis=1)
            pivot['합계'] = pivot[hours_cols].sum(axis=1)
            pivot = pivot.sort_values(by='합계', ascending=False).reset_index(drop=True)

            # 💡 전체 합계(Total) 행 계산 로직 (동일한 검증 룰 적용)
            sum_row = {group_col: '전체 합계'}
            for h in hours_cols + ['합계']:
                sum_row[h] = int(pivot[h].sum())
                
            max_sum_val = -1
            candidate_sum_h = None
            for h in peak_candidates:
                if sum_row[h] > max_sum_val:
                    max_sum_val = sum_row[h]
                    candidate_sum_h = h
                    
            true_peak_sum_h = "-"
            if candidate_sum_h and max_sum_val > 0:
                if candidate_sum_h == '08시':
                    true_peak_sum_h = "-"
                else:
                    idx = peak_candidates.index(candidate_sum_h)
                    if idx > 0:
                        prev_h = peak_candidates[idx - 1]
                        prev_val = sum_row[prev_h]
                        if prev_val == 0:
                            true_peak_sum_h = candidate_sum_h
                        else:
                            if (max_sum_val - prev_val) / prev_val >= 0.30:
                                true_peak_sum_h = candidate_sum_h
                            else:
                                true_peak_sum_h = "-"
                                
            sum_row['🔥 피크시간대'] = true_peak_sum_h
            
            sum_collected = []
            for h in reversed(peak_candidates):
                if h == true_peak_sum_h: continue
                sum_collected.append(sum_row[h])
                if len(sum_collected) == 3: break
                
            sum_row['평균 인입량'] = int(round(sum(sum_collected) / len(sum_collected))) if sum_collected else 0

            sum_df = pd.DataFrame([sum_row])
            cols_order = [group_col, '🔥 피크시간대', '합계', '평균 인입량'] + hours_cols
            return pivot[cols_order], sum_df[cols_order], hours_cols

        col_radio, _ = st.columns([5, 5])
        with col_radio:
            view_mode = st.radio("조회 기준을 선택하세요:", ["🏢 셀러별", "🛒 판매채널별"], horizontal=True, label_visibility="collapsed")
        
        group_col = 'OM셀러명' if view_mode == "🏢 셀러별" else '판매채널'
        group_label = "셀러명" if view_mode == "🏢 셀러별" else "판매채널명"

        if group_col not in df_box.columns:
            st.error(f"❌ '{group_col}' 컬럼이 존재하지 않습니다.")
            return

        main_pivot, main_sum, _ = build_time_pivot(df_box, group_col)

        time_cols_config = {
            group_col: st.column_config.TextColumn(group_label, width="medium"),
            '🔥 피크시간대': st.column_config.TextColumn("🔥 피크", alignment="center"),
            '합계': st.column_config.NumberColumn("합계", format="%d 건", alignment="center"),
            '평균 인입량': st.column_config.NumberColumn("평균", format="%d 건", alignment="center")
        }
        for h in hours_cols:
            time_cols_config[h] = st.column_config.NumberColumn(h, format="%d 건", alignment="center")

        st.markdown("##### 📊 전체 합계 유입 현황 (고정)")
        main_sum.rename(columns={group_col: group_label}, inplace=True)
        styled_sum = main_sum.style.apply(lambda x: ['font-weight: bold; font-size: 15px !important; background-color: rgba(76, 175, 80, 0.15);'] * len(x), axis=1)
        st.dataframe(styled_sum, column_config=time_cols_config, use_container_width=True, hide_index=True, height=75)

        st.markdown("#### 🔍 1. 상세 기준별 시간대 주문 인입 현황")
        st.caption(f"👇 표의 행을 클릭하시면 하단에 연동된 상세 현황(패킹/교차)이 표시됩니다.")
        main_pivot.rename(columns={group_col: group_label}, inplace=True)
        event = st.dataframe(main_pivot, column_config=time_cols_config, use_container_width=True, hide_index=True, height=280, on_select="rerun", selection_mode="single-row")

        selected_item = "전체 합계"
        if event and event.get("selection", {}).get("rows"):
            selected_idx = event["selection"]["rows"][0]
            selected_item = main_pivot[group_label].iloc[selected_idx]

        st.markdown("---")
        st.markdown(f"#### 🔍 2. [{selected_item}] 세부 현황 분석")

        cross_col = '판매채널' if group_col == 'OM셀러명' else 'OM셀러명'
        cross_label = '판매채널명' if group_col == 'OM셀러명' else '셀러명'
        
        df_selected = df_box.copy() if selected_item == "전체 합계" else df_box[df_box[group_col] == selected_item].copy()

        tab_pack, tab_cross = st.tabs(["📦 패킹타입별 상세", f"{'🛒' if group_col == 'OM셀러명' else '🏢'} {cross_label}별 상세"])

        def render_sub_time_table(pivot_df, sum_df, col_name, display_name):
            pivot_df.rename(columns={col_name: display_name}, inplace=True)
            sum_df.rename(columns={col_name: display_name}, inplace=True)
            combined_df = pd.concat([sum_df, pivot_df], ignore_index=True)

            styled_df = combined_df.style.apply(lambda row: ['font-weight: bold; font-size: 15px !important; background-color: rgba(255, 255, 255, 0.05);'] * len(row) if row[display_name] == '전체 합계' else [''] * len(row), axis=1)

            sub_config = dict(time_cols_config)
            sub_config[display_name] = st.column_config.TextColumn(display_name, width="medium")
            if group_label in sub_config and display_name != group_label: del sub_config[group_label]

            st.dataframe(styled_df, column_config=sub_config, use_container_width=True, hide_index=True, height=280)

        with tab_pack:
            pack_pivot, pack_sum, _ = build_time_pivot(df_selected, '패킹타입_세부')
            render_sub_time_table(pack_pivot, pack_sum, '패킹타입_세부', '패킹타입')

        with tab_cross:
            if cross_col in df_box.columns:
                cross_pivot, cross_sum, _ = build_time_pivot(df_selected, cross_col)
                render_sub_time_table(cross_pivot, cross_sum, cross_col, cross_label)