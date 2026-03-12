#!/usr/bin/env python3
"""
抖音视频文案提取器 WebUI

启动方式:
    cd douyin-mcp-server
    export API_KEY="sk-xxx"
    python web/app.py
    # 访问 http://localhost:8080
"""

import os
import sys
import logging
from pathlib import Path

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent / "douyin-video" / "scripts"))

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import uvicorn
import requests

# 从 .env 文件加载配置
from dotenv import load_dotenv
load_dotenv()  # 自动查找 .env 文件并加载

# 导入抖音处理模块
from douyin_downloader import get_video_info, extract_text, HEADERS

app = FastAPI(title="抖音文案提取器", version="1.0.0")
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

# 获取日志记录器
logger = logging.getLogger(__name__)


class VideoRequest(BaseModel):
    """视频请求模型"""
    url: str


class VideoInfoResponse(BaseModel):
    """视频信息响应"""
    success: bool
    video_id: str = ""
    title: str = ""
    download_url: str = ""
    error: str = ""


class ExtractResponse(BaseModel):
    """文案提取响应"""
    success: bool
    video_id: str = ""
    title: str = ""
    text: str = ""
    download_url: str = ""
    error: str = ""


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """主页面"""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/health")
async def health_check():
    """健康检查 - 检查后端 API Key 配置状态"""
    # 支持多种 API Key 配置方式
    api_key = (
        os.getenv("DASHSCOPE_API_KEY") or
        os.getenv("SILICONFLOW_API_KEY") or
        os.getenv("API_KEY") or
        ""
    )
    provider = (
        "dashscope" if os.getenv("DASHSCOPE_API_KEY") else
        "siliconflow" if os.getenv("SILICONFLOW_API_KEY") else
        "auto"
    )
    return {
        "status": "ok",
        "api_key_configured": bool(api_key),
        "provider": provider,
        "message": "API Key 未配置，请在 .env 文件中设置 DASHSCOPE_API_KEY 或 SILICONFLOW_API_KEY" if not api_key else f"API Key 已配置 ({provider})"
    }


@app.post("/api/video/info", response_model=VideoInfoResponse)
async def get_info(req: VideoRequest):
    """获取视频信息（无需 API_KEY）"""
    try:
        info = get_video_info(req.url)
        return VideoInfoResponse(
            success=True,
            video_id=info["video_id"],
            title=info["title"],
            download_url=info["url"]
        )
    except Exception as e:
        return VideoInfoResponse(success=False, error=str(e))


@app.post("/api/video/extract", response_model=ExtractResponse)
async def extract_transcript(req: VideoRequest):
    """提取视频文案（需要 .env 文件中配置 API Key）"""
    # 从 .env 文件或环境变量获取 API Key（支持多种配置方式）
    dashscope_key = os.getenv("DASHSCOPE_API_KEY", "")
    siliconflow_key = os.getenv("SILICONFLOW_API_KEY", "")
    api_key = dashscope_key or siliconflow_key or os.getenv("API_KEY", "")

    if not api_key:
        logger.warning("提取请求失败: 未配置 API Key")
        return ExtractResponse(
            success=False,
            error="后端未配置 API Key，请在项目根目录的 .env 文件中设置 DASHSCOPE_API_KEY 或 SILICONFLOW_API_KEY"
        )

    # 确定使用的 provider
    provider = os.getenv("TRANSCRIPTION_PROVIDER", "auto")
    if dashscope_key and (provider == "auto" or provider == "dashscope"):
        provider = "dashscope"
    elif siliconflow_key and (provider == "auto" or provider == "siliconflow"):
        provider = "siliconflow"

    logger.info(f"[WebUI] 收到提取请求 - Provider: {provider}")

    try:
        result = extract_text(req.url, api_key=api_key, provider=provider, show_progress=False)
        text_length = len(result["text"])

        logger.info(f"[WebUI] 提取成功 - Video ID: {result['video_info']['video_id']}, 文案长度: {text_length} 字符")

        return ExtractResponse(
            success=True,
            video_id=result["video_info"]["video_id"],
            title=result["video_info"]["title"],
            text=result["text"],
            download_url=result["video_info"]["url"]
        )
    except Exception as e:
        logger.error(f"[WebUI] 提取失败: {str(e)}")
        return ExtractResponse(success=False, error=str(e))


@app.get("/api/video/download")
async def download_video(url: str, filename: str = "video.mp4"):
    """代理下载视频（解决跨域和请求头问题）"""
    print(f"[Download] URL: {url}")
    print(f"[Download] Filename: {filename}")
    try:
        # 完整的请求头，模拟浏览器访问
        download_headers = {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) EdgiOS/121.0.2277.107 Version/17.0 Mobile/15E148 Safari/604.1',
            'Referer': 'https://www.douyin.com/',
            'Accept': '*/*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'identity',
            'Connection': 'keep-alive',
        }

        response = requests.get(url, headers=download_headers, stream=True, allow_redirects=True)
        print(f"[Download] Response status: {response.status_code}")
        print(f"[Download] Final URL: {response.url}")
        response.raise_for_status()

        content_length = response.headers.get("content-length", "")

        def iter_content():
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    yield chunk

        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
        }
        if content_length:
            headers["Content-Length"] = content_length

        return StreamingResponse(
            iter_content(),
            media_type="video/mp4",
            headers=headers
        )
    except requests.exceptions.HTTPError as e:
        raise HTTPException(status_code=e.response.status_code, detail=f"下载失败: {e.response.status_code}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def main():
    """启动服务"""
    port = int(os.getenv("PORT", "8080"))

    # 检查 API Key 配置
    dashscope_key = os.getenv("DASHSCOPE_API_KEY", "")
    siliconflow_key = os.getenv("SILICONFLOW_API_KEY", "")
    api_key = dashscope_key or siliconflow_key or os.getenv("API_KEY", "")

    print(f"🚀 启动文案提取器 WebUI: http://localhost:{port}")

    if api_key:
        provider = (
            "阿里云百炼 (Dashscope)" if dashscope_key else
            "硅基流动 (SiliconFlow)" if siliconflow_key else
            "API"
        )
        print(f"✅ API_KEY 已配置 ({provider})")
    else:
        print(f"⚠️  API_KEY 未配置，请在 .env 文件中设置 DASHSCOPE_API_KEY 或 SILICONFLOW_API_KEY")
        print(f"   文案提取功能将不可用")

    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
