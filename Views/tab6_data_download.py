import pandas as pd
import streamlit as st

def render_download_tab(df, df_prev, data_filter):
    st.markdown("### 💾 데이터 추출 및 가공 파일 다운로드")
    st.markdown("전일 미출고 건의 출고번호를 추출하여 WMS 조회에 활용하거나, 현재 필터링된 통합 데이터를 엑셀(CSV)로 다운로드할 수 있습니다.")
    
    tab_extract, tab_data = st.tabs(["📋 전일 미출고 출고번호 추출 (WMS 최적화용)", "📊 가공된 통합 데이터 엑셀 다운로드"])
    
    with tab_extract:
        st.info("💡 **WMS 최적화 팁:** 아래 추출된 출고번호를 복사하여 WMS에 검색하시면, 오늘 다시 작업해야 할 건만 깔끔하게 다운받아 불필요한 데이터 정리 시간을 아낄 수 있습니다.")
        
        if df_prev.empty:
            st.warning("⚠️ 현재 업로드된 데이터 중 '전일 이월' 데이터가 없습니다. 좌측 사이드바에서 '전일 미출고 실적' 파일을 먼저 업로드해 주세요.")
        else:
            prev_out_numbers = df_prev['출고번호_clean'].dropna().unique().tolist()
            st.metric("추출된 대상 출고번호", f"{len(prev_out_numbers):,}건")
            
            col_radio, _ = st.columns([5, 5])
            with col_radio:
                # 💡 [요청 반영] 쉼표(,)를 첫 번째(기본값)로 배치하여 우선 순위 변경
                copy_format = st.radio(
                    "복사 구분자 선택 (WMS 검색창 입력 방식에 맞춤):", 
                    ["쉼표 (,)", "줄바꿈 (Enter)"], 
                    horizontal=True
                )
            
            # 선택한 구분자에 맞춰 텍스트 생성
            if copy_format == "쉼표 (,)":
                out_text = ",".join(prev_out_numbers)
            else:
                out_text = "\n".join(prev_out_numbers)
            
            st.markdown("**👇 아래 박스 우측 상단의 [복사 아이콘]을 클릭하여 복사하세요!**")
            st.code(out_text, language="text")
            
            # CSV 파일 다운로드 생성
            csv_out = pd.DataFrame(prev_out_numbers, columns=['출고번호']).to_csv(index=False).encode('utf-8-sig')
            st.download_button("📥 출고번호 리스트 CSV 파일로 다운로드", data=csv_out, file_name="전일_미출고_출고번호.csv", mime="text/csv")
            
    with tab_data:
        st.markdown(f"##### 🔍 현재 조회 기준: **[{data_filter}]** 데이터베이스")
        st.dataframe(df, use_container_width=True, height=350)
        
        csv_data = df.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="📥 현재 화면의 가공 데이터 CSV 다운로드",
            data=csv_data,
            file_name="스마트물류_가공데이터.csv",
            mime="text/csv",
            type="primary"
        )