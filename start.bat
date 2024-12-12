@echo off

REM 仮想環境を有効化
call .venv\Scripts\activate

REM スクリプトを実行
python main.py

REM 仮想環境を無効化
deactivate
