import pandas as pd
import streamlit as st

def render_dispatch_tab(df):
    st.markdown("## 🚚 배송 유형별 실시간 마감 예측 (B방식)")
    st.caption("주문 유입 속도와 마감 시한(13시/23시/25시)을 반영한 동적 물량 추정 대시보드입니다.")
    st.markdown("---")

    # --- 1. 현장 운영 및 보정 설정 영역 ---
    st.markdown("#### ⚙️ 현장 운영 시각 및 미집하 보정 설정")
    col_s1, col_s2, col_s3 = st.columns([2, 2, 1])
    
    with col_s1:
        current_hour = st.slider(
            "🕒 현재 현장 운영 시간 (시)", 
            min_value=8, max_value=24, value=11, step=1, key="tab1_curr_hour"
        )
    with col_s2:
        delay_ratio_percent = st.slider(
            "스캔 딜레이 미집하건 보정 비율 (%)", 
            min_value=0, max_value=100, value=20, step=10, key="tab1_slider"
        )
        delay_ratio = delay_ratio_percent / 100.0
    with col_s3:
        st.info(f"**설정 요약**\n- 운영시각: {current_hour}시\n- 보정비율: {delay_ratio_percent}%")

    st.markdown("---")

    # --- 2. 데이터 처리 및 B방식 계산 로직 ---
    def map_delivery_type(val):
        val_str = str(val).strip()
        if '당일' in val_str:
            return '당일 배송'
        elif '일반' in val_str:
            return '일반 배송'
        elif '휴일' in val_str:
            return '휴일 배송'
        else:
            return '기타 배송'

    df['배송대분류'] = df['배송유형'].apply(map_delivery_type)

    results = []
    total_inflow_sum = 0
    adjusted_completed_sum = 0
    projected_total_sum = 0

    for category, group in df.groupby('배송대분류'):
        total_inflow = group['출고번호'].nunique()
        has_pickup = group['배송집하일'].notna() & (group['배송집하일'] != 0)
        is_shipped = group['출고상태'] == '출고완료'
        
        pickup_count = len(set(group[has_pickup & is_shipped]['출고번호'].dropna().unique()))
        unpickup_shipped_count = len(set(group[~has_pickup & is_shipped]['출고번호'].dropna().unique()) - set(group[has_pickup & is_shipped]['출고번호'].dropna().unique()))
        
        adjusted_completed = pickup_count + (unpickup_shipped_count * delay_ratio)
        dynamic_completion_rate = (adjusted_completed / total_inflow * 100) if total_inflow > 0 else 0
        
        # B방식: 유입 마감 및 출고 마감 시한 정립
        if category == '당일 배송':
            inflow_cutoff, target_hour, ext_hour = 12, 13, 14
        elif category == '휴일 배송':
            inflow_cutoff, target_hour, ext_hour = 22, 23, 24
        else:
            inflow_cutoff, target_hour, ext_hour = 24, 25, 26

        remaining_inflow_hours = max(0, inflow_cutoff - current_hour)
        remaining_ship_hours = max(0, target_hour - current_hour)
        
        hourly_rate = round(total_inflow / 24, 1)
        projected_additional = round(remaining_inflow_hours * hourly_rate, 1)
        projected_total = round(total_inflow + projected_additional, 1)
        remaining_workload = round(projected_total - adjusted_completed, 1)

        if remaining_workload <= 0:
            status = "🟢 마감 완료"
        elif remaining_ship_hours >= 2:
            status = "🟢 정상 진행"
        elif remaining_ship_hours == 1:
            status = "🟡 연장 고려 (1시간 내)"
        else:
            status = "🔴 지연 위험 경보"

        # 전체 집계용 합산
        total_inflow_sum += total_inflow
        adjusted_completed_sum += adjusted_completed
        projected_total_sum += projected_total

        results.append({
            '배송 유형 대분류': category,
            '현재 유입 건수': total_inflow,
            '현재 보정 완료건': round(adjusted_completed, 1),
            '동적 출고율 (%)': f"{dynamic_completion_rate:.1f}%",
            '주문 유입 마감': f"{inflow_cutoff}시",
            '출고 작업 마감': f"{target_hour}시 (연장 {ext_hour}시)",
            '출고 남은시간': f"{remaining_ship_hours}시간",
            '예상 추가 유입건': projected_additional,
            '최종 마감 예상 물량': projected_total,
            '마감 잔여 작업량': remaining_workload,
            '현장 대응 상태': status
        })

    result_df = pd.DataFrame(results)

    # --- 3. 상단 통합 KPI 메트릭 카드 ---
    st.markdown("#### 📊 전체 현황 요약 (KPI)")
    overall_rate = (adjusted_completed_sum / total_inflow_sum * 100) if total_inflow_sum > 0 else 0
    overall_remaining = projected_total_sum - adjusted_completed_sum

    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    kpi1.metric("현재 총 유입건", f"{total_inflow_sum:,} 건")
    kpi2.metric("현재 보정 완료건", f"{round(adjusted_completed_sum, 1):,} 건", delta=f"{overall_rate:.1f}% 달성")
    kpi3.metric("최종 예상 총물량", f"{round(projected_total_sum, 1):,} 건")
    kpi4.metric("마감 잔여 필요 작업량", f"{round(overall_remaining, 1):,} 건", delta_color="inverse")

    st.markdown("---")

    # --- 4. 배송 유형별 현장 상태 시각 카드 ---
    st.markdown("#### 🚨 배송 유형별 실시간 대응 상태")
    cols = st.columns(len(results))
    for idx, row in enumerate(results):
        with cols[idx]:
            st.subheader(row['배송 유형 대분류'])
            st.markdown(f"**상태:** {row['현장 대응 상태']}")
            st.write(f"- 출고 마감: **{row['출고 작업 마감']}**")
            st.write(f"- 남은 시간: **{row['출고 남은시간']}**")
            st.write(f"- 잔여 작업량: **{row['마감 잔여 작업량']}건**")
            st.progress(min(1.0, float(row['동적 출고율 (%)'].replace('%', '')) / 100.0))

    st.markdown("---")

    # --- 5. 상세 예측 데이터 데이터프레임 ---
    st.markdown("#### 📋 상세 마감 예측 데이터")
    st.dataframe(result_df, use_container_width=True)