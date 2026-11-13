@echo off
chcp 65001 >nul
title npm 登录（发布 dsh-pet-holocubic 用）
set NODE=C:\Users\Chico\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe
set PNPM=C:\Users\Chico\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\pnpm\bin\pnpm.cjs

echo.
echo ============================================
echo   npm 登录
echo ============================================
echo.
echo 接下来会依次问你要三样东西：
echo   1) Username  -> 输入  chicochol
echo   2) Password  -> 输入你的 npm 密码（不显示，正常现象）
echo   3) OTP       -> 打开手机验证器 App，输入 6 位数字
echo.
echo 登录成功后，回到这里按任意键关闭，然后告诉助手「好了」。
echo.
pause

echo.
echo --- 开始登录 ---
"%NODE%" "%PNPM%" login

echo.
if %ERRORLEVEL% EQU 0 (
  echo ============================================
  echo   登录成功
  echo ============================================
) else (
  echo ============================================
  echo   登录失败（错误码 %ERRORLEVEL%）
  echo ============================================
)
echo.
pause
