#!/usr/bin/env python3
"""
项目入口点 - 从根目录启动 FastAPI 服务

使用方法:
    python run.py
    或
    ./run.py
"""
import sys
import os

# 确保项目根目录在 Python 路径中
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

if __name__ == "__main__":
    import uvicorn
    from src.main import app
    
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)
