import pandas as pd
import streamlit as st
import datetime
import uuid

def render_dispatch_tab(df):
    if df.empty:
        st.warning("분석할 데이터가 없습니다.")
        return

    # ==============================================================================
    # 🌟 [핵심 기능] 탭 이동 시 데이터 초기화 방지 & 버전 충돌 방어 (Auto-Heal)
    # ==============================================================================
    if "capa_state" not in st.session_state:
        st.session_state.capa_state = {
            "cutoff_time": datetime.time(11, 0),
            "spike_ratio": 30,
            "u_avg_today": None,
            "u_avg_normal": None,
            "events": [
                # 💡 [요청 반영] 초기 기본 행사 1개만 깔끔하게 세팅
                {"id": str(uuid.uuid4()), "name": "SK 스토아", "item_name": "", "del_type": "일반(휴일)", "packing": "기타", "qty": 30, "done": False}
            ]
        }
    else:
        for ev in st.session_state.capa_state.get("events", []):
            if "item_name" not in ev: ev["item_name"] = ""
            if "del_type" not in ev: ev["del_type"] = "일반(휴일)"
            if "packing" not in ev: ev["packing"] = "기타"
            if "done" not in ev: ev["done"] = False

    cs = st.session_state.capa_state

    # ==============================================================================
    # 0. 데이터 전처리 (재고부족 제외 및 시간 세팅)
    # ==============================================================================
    if '할당상태' in df.columns:
        df_active = df[df['할당상태'] != '재고부족'].copy()
        stockout_qty = df[df['할당상태'] == '재고부족']['출고번호'].nunique()
    else:
        df_active = df.copy()
        stockout_qty = 0

    if '결제일시_dt' in df_active.columns:
        valid_dts = df_active['결제일시_dt'].dropna()
        current_time_dt = valid_dts.max() if not valid_dts.empty else datetime.datetime.now()
    else:
        current_time_dt = datetime.datetime.now()

    current_hour = current_time_dt.hour
    current_time_str = current_time_dt.strftime('%H:%M')

    current_today_qty = df_active[df_active['배송대분류'] == '당일 배송']['출고번호'].nunique() if '배송대분류' in df_active.columns else 0
    current_normal_qty = df_active[df_active['배송대분류'] == '일반 배송']['출고번호'].nunique() if '배송대분류' in df_active.columns else df_active['출고번호'].nunique()
    
    has_today = '당일 배송' in df_active['배송대분류'].unique() if '배송대분류' in df_active.columns else False
    has_normal = '일반 배송' in df_active['배송대분류'].unique() if '배송대분류' in df_active.columns else True

    # ==============================================================================
    # 1. 자동 평균 및 최근 1시간 인입량 계산 엔진
    # ==============================================================================
    def calculate_speed_metrics(df_sub):
        if '결제일시_dt' not in df_sub.columns: return 0, 0
        df_new = df_sub[df_sub['데이터구분'] == '금일 신규'].copy() if '데이터구분' in df_sub.columns else df_sub.copy()
        
        df_new['hour'] = df_new['결제일시_dt'].dt.hour
        completed_df = df_new[(df_new['hour'] < current_hour) & (df_new['hour'] >= 8)]
        
        if completed_df.empty: return 0, 0
            
        hourly_counts = completed_df.groupby('hour')['출고번호'].nunique().to_dict()
        hours_list = range(8, current_hour)
        counts_list = [hourly_counts.get(h, 0) for h in hours_list]
        
        if not counts_list: return 0, 0
        
        recent_1h_val = counts_list[-1]
        
        max_val = max(counts_list)
        peak_idx = counts_list.index(max_val)
        true_peak_idx = -1
        
        if max_val > 0 and hours_list[peak_idx] != 8:
            if peak_idx > 0:
                prev_val = counts_list[peak_idx - 1]
                if prev_val == 0 or (max_val - prev_val) / prev_val >= 0.30:
                    true_peak_idx = peak_idx
        
        collected = []
        for i in range(len(counts_list)-1, -1, -1):
            if i == true_peak_idx: continue
            collected.append(counts_list[i])
            if len(collected) == 3: break
                
        avg_3h_val = int(round(sum(collected) / len(collected))) if collected else 0
        return avg_3h_val, recent_1h_val

    auto_avg_today, recent_today = calculate_speed_metrics(df_active[df_active['배송대분류'] == '당일 배송']) if has_today else (0, 0)
    auto_avg_normal, recent_normal = calculate_speed_metrics(df_active[df_active['배송대분류'] == '일반 배송']) if has_normal else (0, 0)

    def time_to_float(t): return t.hour + t.minute / 60.0
    current_t = time_to_float(current_time_dt.time())
    cutoff_t = time_to_float(cs["cutoff_time"])
    is_today_closed = (current_t >= cutoff_t)

    # ==============================================================================
    # 2. UI 레이아웃 컨테이너 선언
    # ==============================================================================
    zone1_dashboard = st.container()
    st.markdown("---")
    zone3_data = st.container()
    st.markdown("---")
    zone2_controls = st.container()

    # ==============================================================================
    # 3. [Zone 2] 컨트롤 패널 렌더링 및 입력값 받기
    # ==============================================================================
    with zone2_controls:
        st.markdown("#### ⚙️ 3. 현장 변수 및 행사 컨트롤 패널")
        
        c1, c2, c3 = st.columns([1, 1, 2])
        with c1:
            st.markdown("**⏰ 당일배송 마감**")
            cs["cutoff_time"] = st.time_input("마감시간", value=cs["cutoff_time"], label_visibility="collapsed")
            
        with c2:
            st.markdown("**🌙 야간 할증 (21시~)**")
            cs["spike_ratio"] = st.slider("할증률(%)", min_value=0, max_value=100, value=cs["spike_ratio"], step=5, label_visibility="collapsed")
            
        with c3:
            st.markdown("**🚀 시간당 유입 (건/h)**")
            speed_c1, speed_c2 = st.columns(2)
            
            if is_today_closed: auto_avg_today = 0
            
            val_today = int(auto_avg_today) if cs["u_avg_today"] is None else cs["u_avg_today"]
            user_avg_today = speed_c1.number_input("당일배송 유입", min_value=0, value=val_today, step=10, disabled=(not has_today or is_today_closed))
            cs["u_avg_today"] = user_avg_today
            
            val_normal = int(auto_avg_normal) if cs["u_avg_normal"] is None else cs["u_avg_normal"]
            user_avg_normal = speed_c2.number_input("일반배송 유입", min_value=0, value=val_normal, step=10, disabled=not has_normal)
            cs["u_avg_normal"] = user_avg_normal

        st.markdown("<br>", unsafe_allow_html=True)
        
        st.markdown("**🎉 행사 물량 상세 관리**")
        
        col_ratio = [3.5, 3.5, 2, 1.2, 1.2, 1, 1] 
        
        h1, h2, h3, h4, h5, h6, h7 = st.columns(col_ratio)
        h1.markdown("<div style='font-size: 13px; font-weight: bold; color: #888;'>행사명</div>", unsafe_allow_html=True)
        h2.markdown("<div style='font-size: 13px; font-weight: bold; color: #888;'>재고(상품)명</div>", unsafe_allow_html=True)
        h3.markdown("<div style='font-size: 13px; font-weight: bold; color: #888;'>배송유형</div>", unsafe_allow_html=True)
        h4.markdown("<div style='font-size: 13px; font-weight: bold; color: #888;'>패킹타입</div>", unsafe_allow_html=True)
        h5.markdown("<div style='font-size: 13px; font-weight: bold; color: #888;'>예상건수</div>", unsafe_allow_html=True)
        h6.markdown("<div style='font-size: 13px; font-weight: bold; color: #888; text-align:center;'>행사종료</div>", unsafe_allow_html=True)
        h7.markdown("<div style='font-size: 13px; font-weight: bold; color: #888; text-align:center;'>삭제</div>", unsafe_allow_html=True)
        
        events_to_keep = []
        need_rerun = False
        
        del_options = ['일반(휴일)', '일반(휴일) / 당일']
        packing_options = ['단수', '단수단포', '단수합포', '이종합포', '혼합', '기타']
        
        for ev in cs["events"]:
            c1, c2, c3, c4, c5, c6, c7 = st.columns(col_ratio)
            
            ev["name"] = c1.text_input("행사명", value=ev["name"], key=f"name_{ev['id']}", label_visibility="collapsed")
            ev["item_name"] = c2.text_input("상품명", value=ev["item_name"], key=f"item_{ev['id']}", label_visibility="collapsed")
            
            d_idx = del_options.index(ev["del_type"]) if ev["del_type"] in del_options else 0
            ev["del_type"] = c3.selectbox("배송유형", options=del_options, index=d_idx, key=f"del_{ev['id']}", label_visibility="collapsed")
            
            p_idx = packing_options.index(ev["packing"]) if ev["packing"] in packing_options else 5
            ev["packing"] = c4.selectbox("패킹타입", options=packing_options, index=p_idx, key=f"pack_{ev['id']}", label_visibility="collapsed")
            
            ev["qty"] = c5.number_input("건수", min_value=0, value=ev["qty"], step=50, key=f"qty_{ev['id']}", label_visibility="collapsed")
            
            _, chk_center, _ = c6.columns([1, 1, 1])
            ev["done"] = chk_center.checkbox(" ", value=ev["done"], key=f"done_{ev['id']}", label_visibility="collapsed")
            
            if c7.button("❌", key=f"rm_{ev['id']}", use_container_width=True):
                need_rerun = True
            else:
                events_to_keep.append(ev)
                
        if need_rerun:
            cs["events"] = events_to_keep
            st.rerun()

        if st.button("➕ 행사 추가하기"):
            cs["events"].append({
                "id": str(uuid.uuid4()), 
                "name": "", 
                "item_name": "", 
                "del_type": "일반(휴일)", 
                "packing": "기타", 
                "qty": 0, 
                "done": False
            })
            st.rerun()

    # ==============================================================================
    # 4. [Zone 3] 하단 데이터 및 이슈 안내 구역 렌더링
    # ==============================================================================
    with zone3_data:
        st.markdown("#### 📊 2. 백그라운드 데이터 분석 및 현장 이슈")
        
        d_col1, d_col2 = st.columns([6, 4])
        with d_col1:
            st.markdown(f"**📈 최근 데이터 인입 추이 (현재 <span style='color: #4CAF50;'>{current_time_str}</span> 기준)**", unsafe_allow_html=True)
            if has_today:
                if is_today_closed:
                    st.caption(f"- **[당일]** 🔴 마감 시간({cs['cutoff_time'].strftime('%H:%M')}) 종료됨 ➔ 추가 유입 차단(0건)")
                else:
                    st.caption(f"- **[당일]** 시스템 평균: {auto_avg_today}건/h &nbsp;|&nbsp; 가장 최근 1시간: **{recent_today}건**")
            if has_normal:
                st.caption(f"- **[일반]** 시스템 평균: {auto_avg_normal}건/h &nbsp;|&nbsp; 가장 최근 1시간: **{recent_normal}건**")
            
            st.info("💡 최근 유입량 급증 시 하단 패널에서 '시간당 유입' 수치를 상향 조정하세요.")

        with d_col2:
            st.markdown("**⚠️ 현장 특이사항 (결품)**")
            if stockout_qty > 0:
                st.markdown(f"<div style='color: #FF5252; font-size: 15px; font-weight: bold; padding: 10px; border: 1px solid #FF5252; border-radius: 5px; background-color: rgba(255, 82, 82, 0.1);'>🚨 현재 재고부족(미할당) 발생 : {stockout_qty:,} 건</div>", unsafe_allow_html=True)
                st.caption("※ 위 건수는 상단의 '최종 출고 예상 물량'에서 안전하게 제외되었습니다.")
            else:
                st.success("✅ 현재 확인된 재고부족(미할당) 이슈가 없습니다.")

    # ==============================================================================
    # 5. 구간별 남은 시간 및 예상 물량 계산 (Core Logic)
    # ==============================================================================
    spike_t = 21.0
    end_of_day = 24.0

    est_add_today = 0
    est_add_normal = 0
    
    if current_t < end_of_day:
        if current_t < cutoff_t:
            hours_in_A = cutoff_t - current_t
            est_add_today += (user_avg_today * hours_in_A)
            est_add_normal += (user_avg_normal * hours_in_A)
            
            merged_speed = user_avg_today + user_avg_normal
            if cutoff_t < spike_t:
                hours_in_B = spike_t - cutoff_t
                est_add_normal += (merged_speed * hours_in_B)
                hours_in_C = end_of_day - spike_t
                spike_speed = merged_speed * (1 + (cs["spike_ratio"] / 100.0))
                est_add_normal += (spike_speed * hours_in_C)
                
        else:
            merged_speed = user_avg_today + user_avg_normal
            if current_t < spike_t:
                hours_in_B = spike_t - current_t
                est_add_normal += (merged_speed * hours_in_B)
                hours_in_C = end_of_day - spike_t
                spike_speed = merged_speed * (1 + (cs["spike_ratio"] / 100.0))
                est_add_normal += (spike_speed * hours_in_C)
            else:
                hours_in_C = end_of_day - current_t
                spike_speed = merged_speed * (1 + (cs["spike_ratio"] / 100.0))
                est_add_normal += (spike_speed * hours_in_C)

    est_add_today = int(round(est_add_today)) if has_today else 0
    est_add_normal = int(round(est_add_normal)) if has_normal else 0

    event_today_qty = 0
    event_normal_qty = 0
    
    for ev in cs["events"]:
        if ev["done"]: continue 
        
        if ev["del_type"] == "일반(휴일) / 당일":
            if not is_today_closed:
                event_today_qty += ev["qty"] 
            else:
                event_normal_qty += ev["qty"] 
        else:
            event_normal_qty += ev["qty"] 

    final_today = current_today_qty + est_add_today + event_today_qty
    final_normal = current_normal_qty + est_add_normal + event_normal_qty
    final_total = final_today + final_normal

    # ==============================================================================
    # 6. [Zone 1] 최상단 대시보드 출력 렌더링
    # ==============================================================================
    with zone1_dashboard:
        st.markdown("## 🎯 1. 오늘의 최종 출고 예상 물량")
        st.caption("현장 변수(마감시간, 야간할증, 행사물량)와 유입 속도가 실시간 반영된 순수 예상 출고량입니다. **(재고부족 제외 완료)**")
        
        if has_today and has_normal:
            f_col1, f_col2, f_col3 = st.columns(3)
            f_col1.markdown(f"""
                <div style="background-color: #11151C; padding: 20px; border-radius: 10px; border: 1px solid #333; text-align: center;">
                    <div style="font-size: 14px; color: #888;">🔴 당일배송 (마감 {cs['cutoff_time'].strftime('%H:%M')})</div>
                    <div style="font-size: 32px; font-weight: bold; color: #FF5252; margin-top: 10px;">{final_today:,} 건</div>
                    <div style="font-size: 12px; color: #aaa; margin-top: 5px;">현재 {current_today_qty:,} + 예측 {est_add_today:,} + 행사 {event_today_qty:,}</div>
                </div>""", unsafe_allow_html=True)
            f_col2.markdown(f"""
                <div style="background-color: #11151C; padding: 20px; border-radius: 10px; border: 1px solid #333; text-align: center;">
                    <div style="font-size: 14px; color: #888;">🔵 일반/휴일배송</div>
                    <div style="font-size: 32px; font-weight: bold; color: #448AFF; margin-top: 10px;">{final_normal:,} 건</div>
                    <div style="font-size: 12px; color: #aaa; margin-top: 5px;">현재 {current_normal_qty:,} + 예측 {est_add_normal:,} + 행사 {event_normal_qty:,}</div>
                </div>""", unsafe_allow_html=True)
            f_col3.markdown(f"""
                <div style="background-color: #1E2530; padding: 20px; border-radius: 10px; border: 2px solid #4CAF50; text-align: center;">
                    <div style="font-size: 15px; font-weight: bold; color: #4CAF50;">📦 오늘 쳐내야 할 총 합계 물량</div>
                    <div style="font-size: 38px; font-weight: bold; color: #FFFFFF; margin-top: 5px;">{final_total:,} 건</div>
                </div>""", unsafe_allow_html=True)
        elif has_today and not has_normal:
            st.markdown(f"""
                <div style="background-color: #1E2530; padding: 30px; border-radius: 10px; border: 2px solid #FF5252; text-align: center;">
                    <div style="font-size: 16px; font-weight: bold; color: #FF5252;">🔴 당일배송 최종 예상 물량 (마감 {cs['cutoff_time'].strftime('%H:%M')} 기준)</div>
                    <div style="font-size: 45px; font-weight: bold; color: #FFFFFF; margin-top: 10px;">{final_today:,} 건</div>
                    <div style="font-size: 14px; color: #aaa; margin-top: 5px;">(누적 {current_today_qty:,}건 + 예측 {est_add_today:,}건 + 행사 {event_today_qty:,}건)</div>
                </div>""", unsafe_allow_html=True)
        elif has_normal and not has_today:
            st.markdown(f"""
                <div style="background-color: #1E2530; padding: 30px; border-radius: 10px; border: 2px solid #448AFF; text-align: center;">
                    <div style="font-size: 16px; font-weight: bold; color: #448AFF;">🔵 일반/휴일배송 최종 예상 물량 (야간할증 {cs['spike_ratio']}% 적용)</div>
                    <div style="font-size: 45px; font-weight: bold; color: #FFFFFF; margin-top: 10px;">{final_normal:,} 건</div>
                    <div style="font-size: 14px; color: #aaa; margin-top: 5px;">(누적 {current_normal_qty:,}건 + 예측 {est_add_normal:,}건 + 행사 {event_normal_qty:,}건)</div>
                </div>""", unsafe_allow_html=True)

# --- 파일 끝 ---