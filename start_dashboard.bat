@echo off
title Rewired Index Engine
echo 正在唤醒 Rewired Index 核心路由引擎...
cd /d "D:\MyProject\Rewired Index"
call .venv\Scripts\activate.bat
rewired gui --port 8080
pause