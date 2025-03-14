import sys
import os

# リポジトリのルートパスを sys.path に追加（tests フォルダの一つ上）
sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")))
