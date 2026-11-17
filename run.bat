@echo off
:: 터미널 인코딩을 UTF-8로 변경하여 한글 깨짐 방지
chcp 65001 > nul

echo ===================================================
echo  물류 출고 현황 분석 대시보드를 시작합니다.
echo ===================================================

.venv\Scripts\python.exe -m streamlit run app.py --server.runOnSave true

pause