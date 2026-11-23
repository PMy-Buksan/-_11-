import pandas as pd
import streamlit as st
import datetime
import uuid
import math

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
                {"id": str(uuid.uuid4()), "name": "SK 스토아", "item_name": "", "del_type": "일반배송", "packing": "기타", "qty": 30, "done": False}
            ]
        }
    else:
        for ev in st.session_state.capa_state.get("events", []):
            if "item_name" not in ev: ev["item_name"] = ""
            if "del_type" not in ev: ev["del_type"] = "일반배송"
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

    if '배송대분류' in df_active.columns:
        cond_today = df_active['배송대분류'].str.contains('당일', na=False)
        cond_holi = df_active['배송대분류'].str.contains('휴일', na=False)
        cond_norm = df_active['배송대분류'].str.contains('일반', na=False)
        
        current_today_qty = df_active[cond_today]['출고번호'].nunique()
        qty_holi = df_active[cond_holi]['출고번호'].nunique()
        qty_norm = df_active[cond_norm]['출고번호'].nunique()
        
        if qty_holi >= qty_norm and qty_holi > 0:
            dominant_name = "휴일배송"
            minor_name = "일반배송"
            cond_dominant = cond_holi
            current_dominant_qty = qty_holi
            current_minor_qty = qty_norm
        else:
            dominant_name = "일반배송"
            minor_name = "휴일배송"
            cond_dominant = cond_norm
            current_dominant_qty = qty_norm
            current_minor_qty = qty_holi
            
        has_today = cond_today.any()
        has_dominant = cond_dominant.any()
    else:
        current_today_qty = 0
        current_dominant_qty = df_active['출고번호'].nunique()
        current_minor_qty = 0
        has_today = False
        has_dominant = True
        cond_today = pd.Series(False, index=df_active.index)
        cond_dominant = pd.Series(True, index=df_active.index)
        dominant_name = "일반배송"
        minor_name = "휴일배송"

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

    auto_avg_today, recent_today = calculate_speed_metrics(df_active[cond_today]) if has_today else (0, 0)
    auto_avg_dominant, recent_dominant = calculate_speed_metrics(df_active[cond_dominant]) if has_dominant else (0, 0)

    def time_to_float(t): return t.hour + t.minute / 60.0
    current_t = time_to_float(current_time_dt.time())
    
    cutoff_t = time_to_float(cs["cutoff_time"])
    dominant_cutoff_t = 22.0
    
    is_today_closed = (current_t >= cutoff_t)
    is_dominant_closed = (current_t >= dominant_cutoff_t)

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
            
            val_today = int(auto_avg_today) if cs["u_avg_today"] is None else cs["u_avg_today"]
            user_avg_today = speed_c1.number_input("당일배송 유입", min_value=0, value=val_today, step=10, disabled=(not has_today or is_today_closed))
            cs["u_avg_today"] = user_avg_today
            
            val_dominant = int(auto_avg_dominant) if cs["u_avg_normal"] is None else cs["u_avg_normal"]
            user_avg_dominant = speed_c2.number_input(f"{dominant_name} 유입", min_value=0, value=val_dominant, step=10, disabled=(not has_dominant or is_dominant_closed))
            cs["u_avg_normal"] = user_avg_dominant

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
        
        del_options = [dominant_name, f'{dominant_name} / 당일']
        packing_options = ['단수', '단수단포', '단수합포', '이종합포', '혼합', '기타']
        
        for ev in cs["events"]:
            if ev["del_type"] not in del_options:
                if "당일" in ev["del_type"]: ev["del_type"] = f'{dominant_name} / 당일'
                else: ev["del_type"] = dominant_name
                
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
                "del_type": dominant_name, 
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
            if has_dominant:
                if is_dominant_closed:
                    st.caption(f"- **[{dominant_name}]** 🔴 마감 시간 종료됨 ➔ 추가 유입 차단(0건)")
                else:
                    st.caption(f"- **[{dominant_name}]** 시스템 평균: {auto_avg_dominant}건/h &nbsp;|&nbsp; 가장 최근 1시간: **{recent_dominant}건**")
            
            st.info("💡 최근 유입량 급증 시 하단 패널에서 '시간당 유입' 수치를 상향 조정하세요.")

        with d_col2:
            st.markdown("**⚠️ 현장 특이사항 (결품)**")
            if stockout_qty > 0:
                st.markdown(f"<div style='color: #FF5252; font-size: 15px; font-weight: bold; padding: 10px; border: 1px solid #FF5252; border-radius: 5px; background-color: rgba(255, 82, 82, 0.1);'>🚨 현재 재고부족(미할당) 발생 : {stockout_qty:,} 건</div>", unsafe_allow_html=True)
                st.caption("※ 위 건수는 상단의 '최종 출고 예상 물량'에서 안전하게 제외되었습니다.")
            else:
                st.success("✅ 현재 확인된 재고부족(미할당) 이슈가 없습니다.")

    # ==============================================================================
    # 5. 구간별 남은 시간 및 예상 물량 계산 (신규 정밀 예측 엔진)
    # ==============================================================================
    spike_t = 21.0
    end_of_day = 24.0

    t_points = sorted([current_t, cutoff_t, dominant_cutoff_t, spike_t, end_of_day])
    t_points = [t for t in t_points if t >= current_t and t <= end_of_day]

    est_add_today = 0
    est_add_dominant = 0

    for i in range(len(t_points) - 1):
        start = t_points[i]
        end = t_points[i+1]
        if start >= end: continue
        
        duration = end - start
        
        active_today = (start < cutoff_t)
        active_dominant = (start < dominant_cutoff_t)
        
        current_today_speed = user_avg_today if active_today else 0
        current_dominant_speed = user_avg_dominant if active_dominant else 0
        
        if not active_today and active_dominant:
            current_dominant_speed += user_avg_today
            
        if start >= spike_t:
            current_dominant_speed = current_dominant_speed * (1 + (cs["spike_ratio"] / 100.0))
            
        est_add_today += current_today_speed * duration
        est_add_dominant += current_dominant_speed * duration

    est_add_today = int(round(est_add_today)) if has_today else 0
    est_add_dominant = int(round(est_add_dominant)) if has_dominant else 0

    event_today_qty = 0
    event_dominant_qty = 0
    
    for ev in cs["events"]:
        if ev["done"]: continue 
        
        if ev["del_type"] == f"{dominant_name} / 당일":
            if not is_today_closed:
                event_today_qty += ev["qty"] 
            else:
                event_dominant_qty += ev["qty"] 
        else:
            event_dominant_qty += ev["qty"] 

    final_today = current_today_qty + est_add_today + event_today_qty
    final_dominant = current_dominant_qty + est_add_dominant + event_dominant_qty
    
    final_total = final_today + final_dominant + current_minor_qty

    # ==============================================================================
    # 6. [Zone 1] 최상단 대시보드 출력 렌더링 및 업체별 수량 추출
    # ==============================================================================
    with zone1_dashboard:
        st.markdown("## 🎯 1. 오늘의 최종 출고 예상 물량")
        st.caption("현장 변수(마감시간, 야간할증, 행사물량)와 유입 속도가 실시간 반영된 순수 예상 출고량입니다. **(재고부족 제외 완료)**")
        
        if has_today and has_dominant:
            f_col1, f_col2, f_col3 = st.columns(3)
            f_col1.markdown(f"""
                <div style="background-color: #11151C; padding: 20px; border-radius: 10px; border: 1px solid #333; text-align: center;">
                    <div style="font-size: 14px; color: #888;">🔴 당일배송 (마감 {cs['cutoff_time'].strftime('%H:%M')})</div>
                    <div style="font-size: 32px; font-weight: bold; color: #FF5252; margin-top: 10px;">{final_today:,} 건</div>
                    <div style="font-size: 12px; color: #aaa; margin-top: 5px;">현재 {current_today_qty:,} + 예측 {est_add_today:,} + 행사 {event_today_qty:,}</div>
                </div>""", unsafe_allow_html=True)
            f_col2.markdown(f"""
                <div style="background-color: #11151C; padding: 20px; border-radius: 10px; border: 1px solid #333; text-align: center;">
                    <div style="font-size: 14px; color: #888;">🔵 {dominant_name}</div>
                    <div style="font-size: 32px; font-weight: bold; color: #448AFF; margin-top: 10px;">{final_dominant:,} 건</div>
                    <div style="font-size: 12px; color: #aaa; margin-top: 5px;">현재 {current_dominant_qty:,} + 예측 {est_add_dominant:,} + 행사 {event_dominant_qty:,}</div>
                </div>""", unsafe_allow_html=True)
            
            minor_text = f"<div style='font-size: 12px; color: #aaa; margin-top: 5px;'>(※ 예측 제외된 {minor_name} {current_minor_qty:,}건 포함)</div>" if current_minor_qty > 0 else ""
            f_col3.markdown(f"""
                <div style="background-color: #1E2530; padding: 20px; border-radius: 10px; border: 2px solid #4CAF50; text-align: center;">
                    <div style="font-size: 15px; font-weight: bold; color: #4CAF50;">📦 오늘 쳐내야 할 총 합계 물량</div>
                    <div style="font-size: 38px; font-weight: bold; color: #FFFFFF; margin-top: 5px;">{final_total:,} 건</div>
                    {minor_text}
                </div>""", unsafe_allow_html=True)
                
        elif has_today and not has_dominant:
            st.markdown(f"""
                <div style="background-color: #1E2530; padding: 30px; border-radius: 10px; border: 2px solid #FF5252; text-align: center;">
                    <div style="font-size: 16px; font-weight: bold; color: #FF5252;">🔴 당일배송 최종 예상 물량 (마감 {cs['cutoff_time'].strftime('%H:%M')} 기준)</div>
                    <div style="font-size: 45px; font-weight: bold; color: #FFFFFF; margin-top: 10px;">{final_today:,} 건</div>
                    <div style="font-size: 14px; color: #aaa; margin-top: 5px;">(누적 {current_today_qty:,}건 + 예측 {est_add_today:,}건 + 행사 {event_today_qty:,}건)</div>
                </div>""", unsafe_allow_html=True)
                
        elif has_dominant and not has_today:
            d_col1, d_col2 = st.columns(2)
            
            with d_col1:
                st.markdown(f"""
                    <div style="background-color: #1E2530; padding: 30px; border-radius: 10px; border: 2px solid #448AFF; text-align: center; height: 100%;">
                        <div style="font-size: 16px; font-weight: bold; color: #448AFF;">🔵 {dominant_name} 최종 예상 물량</div>
                        <div style="font-size: 45px; font-weight: bold; color: #FFFFFF; margin-top: 10px;">{final_dominant:,} 건</div>
                        <div style="font-size: 14px; color: #aaa; margin-top: 5px;">(누적 {current_dominant_qty:,}건 + 예측 {est_add_dominant:,}건 + 행사 {event_dominant_qty:,}건)</div>
                    </div>""", unsafe_allow_html=True)
            
            with d_col2:
                qty_rice, qty_sk, qty_yonsei = 0, 0, 0
                
                seller_col = None
                for col in ['OM셀러', 'OM셀러명', '판매처', '고객사', '업체명', '쇼핑몰', '셀러']:
                    if col in df_active.columns:
                        seller_col = col
                        break
                        
                if seller_col:
                    df_dom = df_active[cond_dominant]
                    qty_rice = df_dom[df_dom[seller_col].str.contains('옥정영농|자연이랑|명성정미소', na=False, case=False)]['출고번호'].nunique()
                    qty_sk = df_dom[df_dom[seller_col].str.contains('SK스토아|SK 스토아|SK', na=False, case=False)]['출고번호'].nunique()
                    qty_yonsei = df_dom[df_dom[seller_col].str.contains('연세', na=False, case=False)]['출고번호'].nunique()
                
                buffered_total = final_dominant + 200
                rounded_total = math.ceil(buffered_total / 100.0) * 100
                
                adjusted_add_qty = max(0, rounded_total - current_dominant_qty)
                
                weekdays = ['월', '화', '수', '목', '금', '토', '일']
                wday = weekdays[current_time_dt.weekday()]
                date_str = current_time_dt.strftime(f'%m월 %d일({wday})')
                hour_str = f"{current_time_dt.hour}시"
                
                # 💡 [요청 반영] 마우스 오버 시 자동으로 '복사(Copy)' 버튼이 나타나는 st.code 활용!
                st.markdown("<div style='font-size: 15px; font-weight: bold; color: #FFEB3B; margin-bottom: 5px;'>💬 집하 카톡</div>", unsafe_allow_html=True)
                
                msg_text = f"{date_str} 인천3센터 {hour_str}기준\n\n현시각 유입량 : {current_dominant_qty:,}건\n(쌀 {qty_rice:,}건) (SK스토아 {qty_sk:,}건) (연세 {qty_yonsei:,}건)\n추가 유입예상량 : 약 {adjusted_add_qty:,}건\n금일 약 {rounded_total:,}건 유입 예상되오니 참고바랍니다."
                
                st.code(msg_text, language="plaintext")

# --- 파일 끝 ---