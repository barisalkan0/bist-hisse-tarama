@echo off
chcp 65001 >nul
cd /d "%~dp0"

REM --- Streamlit ilk calistirma e-posta sorusunu kalici olarak atla ---
if not exist "%USERPROFILE%\.streamlit\credentials.toml" (
  if not exist "%USERPROFILE%\.streamlit" mkdir "%USERPROFILE%\.streamlit"
  >"%USERPROFILE%\.streamlit\credentials.toml" echo [general]
  >>"%USERPROFILE%\.streamlit\credentials.toml" echo email = ""
)

echo BIST Hisse Tarama baslatiliyor...
echo Tarayici otomatik acilacak. Kapatmak icin bu pencereyi kapatin.

REM Python 3.11 launcher ile calistir; bulunamazsa cipci 'python'a dus.
py -3.11 -m streamlit run app.py
if errorlevel 1 (
  echo.
  echo py -3.11 bulunamadi, normal python deneniyor...
  python -m streamlit run app.py
)
pause
