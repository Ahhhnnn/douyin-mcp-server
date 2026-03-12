#!/usr/bin/env python3
"""
抖音无水印视频下载和文案提取工具

功能:
1. 从抖音分享链接获取无水印视频下载链接
2. 下载视频并提取音频
3. 使用硅基流动 API 从音频中提取文本
4. 自动保存文案到文件 (一个视频一个文件夹)

环境变量:
- API_KEY: 硅基流动 API 密钥 (用于文案提取功能)

使用示例:
  # 获取下载链接 (无需 API 密钥)
  python douyin_downloader.py --link "抖音分享链接" --action info

  # 下载视频
  python douyin_downloader.py --link "抖音分享链接" --action download --output ./videos

  # 提取文案并保存到文件 (需要 API_KEY 环境变量)
  python douyin_downloader.py --link "抖音分享链接" --action extract --output ./output
"""

import os
import re
import sys
import json
import argparse
import tempfile
import shutil
import logging
import time
from pathlib import Path
from typing import Optional, Literal
from datetime import datetime
from abc import ABC, abstractmethod
from urllib import request
from http import HTTPStatus

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def check_dependencies():
    """检查必要的依赖是否已安装"""
    missing = []
    try:
        import requests
    except ImportError:
        missing.append("requests")
    try:
        import ffmpeg
    except ImportError:
        missing.append("ffmpeg-python")

    if missing:
        print(f"缺少依赖: {', '.join(missing)}")
        print(f"请运行: pip install {' '.join(missing)}")
        sys.exit(1)


check_dependencies()

import requests
import ffmpeg
import dashscope

# 请求头，模拟移动端访问
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) EdgiOS/121.0.2277.107 Version/17.0 Mobile/15E148 Safari/604.1'
}

# 硅基流动 API 配置
DEFAULT_API_BASE_URL = "https://api.siliconflow.cn/v1/audio/transcriptions"
DEFAULT_MODEL = "FunAudioLLM/SenseVoiceSmall"

# API Provider 配置
DASHSCOPE_MODEL = "paraformer-v2"
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY") or os.getenv("API_KEY", "")
SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY") or os.getenv("API_KEY", "")


class TranscriptionStrategy(ABC):
    """转录策略抽象基类"""

    def __init__(self, api_key: str):
        self.api_key = api_key

    @abstractmethod
    def extract_text(self, video_info: dict, show_progress: bool = True) -> str:
        """从视频信息中提取文本"""
        pass


class DashscopeStrategy(TranscriptionStrategy):
    """阿里云百炼转录策略 - 支持视频 URL 直传"""

    def __init__(self, api_key: str, model: str = None):
        super().__init__(api_key)
        self.model = model or DASHSCOPE_MODEL
        dashscope.api_key = api_key
        logger.info(f"初始化 DashscopeStrategy - 模型: {self.model}")

    def extract_text(self, video_info: dict, show_progress: bool = True) -> str:
        """使用阿里云百炼 API 从视频 URL 直接提取文本"""
        start_time = time.time()
        video_url = video_info['url']
        video_id = video_info.get('video_id', 'unknown')

        logger.info(f"[{video_id}] 开始提取文本")
        logger.info(f"[{video_id}] 视频URL: {video_url[:80]}...")
        logger.info(f"[{video_id}] 使用模型: {self.model}")

        try:
            if show_progress:
                print("正在使用阿里云百炼 API 提取文本...")

            # 发起异步转录任务
            submit_start = time.time()
            logger.info(f"[{video_id}] 提交转录任务...")

            task_response = dashscope.audio.asr.Transcription.async_call(
                model=self.model,
                file_urls=[video_url],
                language_hints=['zh', 'en']
            )

            submit_time = time.time() - submit_start
            task_id = task_response.output.task_id
            logger.info(f"[{video_id}] 任务已提交 - Task ID: {task_id} (耗时: {submit_time:.2f}秒)")

            if show_progress:
                print(f"转录任务已提交 (Task ID: {task_id})，等待处理完成...")

            # 等待转录完成
            wait_start = time.time()
            logger.info(f"[{video_id}] 等待转录完成...")

            transcription_response = dashscope.audio.asr.Transcription.wait(
                task=task_id
            )

            wait_time = time.time() - wait_start
            logger.info(f"[{video_id}] 转录完成 - 状态码: {transcription_response.status_code} (耗时: {wait_time:.2f}秒)")

            if transcription_response.status_code == HTTPStatus.OK:
                # 获取转录结果
                fetch_start = time.time()
                logger.info(f"[{video_id}] 获取转录结果...")

                for transcription in transcription_response.output['results']:
                    url = transcription['transcription_url']
                    response = requests.get(url, timeout=60)
                    response.raise_for_status()
                    result = response.json()

                    fetch_time = time.time() - fetch_start

                    # 提取文本内容
                    if 'transcripts' in result and len(result['transcripts']) > 0:
                        text = result['transcripts'][0]['text']
                        text_length = len(text)

                        total_time = time.time() - start_time

                        logger.info(f"[{video_id}] 文本提取成功!")
                        logger.info(f"[{video_id}] 文本长度: {text_length} 字符")
                        logger.info(f"[{video_id}] 获取结果耗时: {fetch_time:.2f}秒")
                        logger.info(f"[{video_id}] 总耗时: {total_time:.2f}秒")
                        logger.info(f"[{video_id}] 文本预览: {text[:100]}...")

                        if show_progress:
                            print(f"文本提取完成! (共{text_length}字, 耗时{total_time:.1f}秒)")
                        return text
                    else:
                        logger.warning(f"[{video_id}] 未识别到文本内容")
                        return "未识别到文本内容"
            else:
                error_msg = transcription_response.output.message
                logger.error(f"[{video_id}] 转录失败 - {error_msg}")
                raise Exception(f"转录失败: {error_msg}")

        except Exception as e:
            total_time = time.time() - start_time
            logger.error(f"[{video_id}] 提取出错 (耗时: {total_time:.2f}秒): {str(e)}")
            raise Exception(f"阿里云百炼 API 提取文字时出错: {str(e)}")


class SiliconFlowStrategy(TranscriptionStrategy):
    """硅基流动转录策略 - 需要下载视频并提取音频"""

    def __init__(self, api_key: str, api_base_url: str = None, model: str = None):
        super().__init__(api_key)
        self.api_base_url = api_base_url or DEFAULT_API_BASE_URL
        self.model = model or DEFAULT_MODEL
        self.temp_dir = Path(tempfile.mkdtemp())
        logger.info(f"初始化 SiliconFlowStrategy - 模型: {self.model}")

    def __del__(self):
        """清理临时目录"""
        if hasattr(self, 'temp_dir') and self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def download_video(self, video_info: dict, show_progress: bool = True) -> Path:
        """下载视频到临时目录"""
        filename = f"{video_info['video_id']}.mp4"
        filepath = self.temp_dir / filename

        if show_progress:
            print(f"正在下载视频: {video_info['title']}")

        response = requests.get(video_info['url'], headers=HEADERS, stream=True)
        response.raise_for_status()

        # 获取文件大小
        total_size = int(response.headers.get('content-length', 0))

        # 下载文件
        downloaded = 0
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if show_progress and total_size > 0:
                        progress = downloaded / total_size * 100
                        print(f"\r下载进度: {progress:.1f}%", end="", flush=True)

        if show_progress:
            print(f"\n视频下载完成: {filepath}")
        return filepath

    def extract_audio(self, video_path: Path, show_progress: bool = True) -> Path:
        """从视频文件中提取音频"""
        audio_path = video_path.with_suffix('.mp3')

        if show_progress:
            print("正在提取音频...")

        try:
            (
                ffmpeg
                .input(str(video_path))
                .output(str(audio_path), acodec='libmp3lame', q=0)
                .run(capture_stdout=True, capture_stderr=True, overwrite_output=True)
            )
            if show_progress:
                print(f"音频提取完成: {audio_path}")
            return audio_path
        except Exception as e:
            raise Exception(f"提取音频时出错: {str(e)}")

    def get_audio_info(self, audio_path: Path) -> dict:
        """获取音频文件信息（时长和大小）"""
        try:
            probe = ffmpeg.probe(str(audio_path))
            duration = float(probe['format'].get('duration', 0))
            size = audio_path.stat().st_size
            return {'duration': duration, 'size': size}
        except Exception:
            return {'duration': 0, 'size': audio_path.stat().st_size}

    def split_audio(self, audio_path: Path, segment_duration: int = 600, show_progress: bool = True) -> list:
        """将音频分割成多个片段"""
        audio_info = self.get_audio_info(audio_path)
        duration = audio_info['duration']

        if duration <= segment_duration:
            return [audio_path]

        segments = []
        segment_index = 0
        current_time = 0

        if show_progress:
            total_segments = int(duration / segment_duration) + 1
            print(f"音频时长 {duration:.0f} 秒，将分割为 {total_segments} 段...")

        while current_time < duration:
            segment_path = self.temp_dir / f"segment_{segment_index}.mp3"

            try:
                (
                    ffmpeg
                    .input(str(audio_path), ss=current_time, t=segment_duration)
                    .output(str(segment_path), acodec='libmp3lame', q=0)
                    .run(capture_stdout=True, capture_stderr=True, overwrite_output=True)
                )
                segments.append(segment_path)

                if show_progress:
                    print(f"  分割片段 {segment_index + 1}: {current_time:.0f}s - {min(current_time + segment_duration, duration):.0f}s")

            except Exception as e:
                raise Exception(f"分割音频片段 {segment_index} 时出错: {str(e)}")

            current_time += segment_duration
            segment_index += 1

        return segments

    def transcribe_single_audio(self, audio_path: Path) -> str:
        """转录单个音频文件"""
        transcribe_start = time.time()
        audio_size = audio_path.stat().st_size / 1024 / 1024  # MB

        logger.debug(f"调用 SiliconFlow API - 文件: {audio_path.name}, 大小: {audio_size:.2f}MB, 模型: {self.model}")

        files = {
            'file': (audio_path.name, open(audio_path, 'rb'), 'audio/mpeg'),
            'model': (None, self.model)
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}"
        }

        try:
            response = requests.post(self.api_base_url, files=files, headers=headers)
            response.raise_for_status()

            transcribe_time = time.time() - transcribe_start
            logger.debug(f"SiliconFlow API 响应 - 耗时: {transcribe_time:.2f}秒, 状态码: {response.status_code}")

            result = response.json()
            if 'text' in result:
                text_length = len(result['text'])
                logger.info(f"SiliconFlow 转录成功 - 文本长度: {text_length} 字符, 耗时: {transcribe_time:.2f}秒")
                return result['text']
            else:
                logger.warning(f"SiliconFlow 响应无文本内容: {response.text[:200]}")
                return response.text

        except Exception as e:
            transcribe_time = time.time() - transcribe_start
            logger.error(f"SiliconFlow API 调用失败 (耗时: {transcribe_time:.2f}秒): {str(e)}")
            raise Exception(f"提取文字时出错: {str(e)}")
        finally:
            files['file'][1].close()

    def cleanup_files(self, *file_paths: Path):
        """清理指定的文件"""
        for file_path in file_paths:
            if file_path.exists():
                file_path.unlink()

    def extract_text(self, video_info: dict, show_progress: bool = True) -> str:
        """从视频信息中提取文本（下载视频 + 提取音频 + 转录）"""
        start_time = time.time()
        video_id = video_info.get('video_id', 'unknown')

        logger.info(f"[{video_id}] 开始提取文本 (SiliconFlow)")
        logger.info(f"[{video_id}] 视频URL: {video_info['url'][:80]}...")

        if not self.api_key:
            raise ValueError("未设置 API 密钥")

        try:
            # 下载视频
            download_start = time.time()
            logger.info(f"[{video_id}] 开始下载视频...")
            video_path = self.download_video(video_info, show_progress=show_progress)
            download_time = time.time() - download_start
            video_size = video_path.stat().st_size / 1024 / 1024  # MB
            logger.info(f"[{video_id}] 视频下载完成 - 大小: {video_size:.2f}MB, 耗时: {download_time:.2f}秒")

            # 提取音频
            extract_start = time.time()
            logger.info(f"[{video_id}] 开始提取音频...")
            audio_path = self.extract_audio(video_path, show_progress=show_progress)
            extract_time = time.time() - extract_start
            audio_size = audio_path.stat().st_size / 1024 / 1024  # MB
            logger.info(f"[{video_id}] 音频提取完成 - 大小: {audio_size:.2f}MB, 耗时: {extract_time:.2f}秒")

            # 检查文件大小和时长
            audio_info = self.get_audio_info(audio_path)
            max_duration = 3600  # 1 小时
            max_size = 50 * 1024 * 1024  # 50MB

            logger.info(f"[{video_id}] 音频信息 - 时长: {audio_info['duration']:.1f}秒, 大小: {audio_info['size'] / 1024 / 1024:.2f}MB")

            # 判断是否需要分段
            need_split = audio_info['duration'] > max_duration or audio_info['size'] > max_size

            transcribe_start = time.time()

            if not need_split:
                # 文件在限制范围内，直接处理
                logger.info(f"[{video_id}] 开始语音识别...")
                if show_progress:
                    print("正在识别语音...")
                text = self.transcribe_single_audio(audio_path)
            else:
                # 需要分段处理
                logger.warning(f"[{video_id}] 文件较大，需要分段处理")
                if show_progress:
                    print(f"音频文件较大（时长: {audio_info['duration']:.0f}秒, 大小: {audio_info['size'] / 1024 / 1024:.1f}MB）")
                    print("将自动分段处理...")

                # 分割音频
                segments = self.split_audio(audio_path, segment_duration=540, show_progress=show_progress)
                logger.info(f"[{video_id}] 音频已分割为 {len(segments)} 段")

                # 逐段转录
                all_texts = []
                for i, segment_path in enumerate(segments):
                    if show_progress:
                        print(f"正在识别第 {i + 1}/{len(segments)} 段...")
                    logger.info(f"[{video_id}] 识别第 {i + 1}/{len(segments)} 段...")
                    text = self.transcribe_single_audio(segment_path)
                    all_texts.append(text)

                    # 清理分段文件
                    if segment_path != audio_path:
                        self.cleanup_files(segment_path)

                # 合并文本
                text = ''.join(all_texts)

                if show_progress:
                    print(f"语音识别完成，共处理 {len(segments)} 个片段")

            transcribe_time = time.time() - transcribe_start

            # 清理临时文件
            self.cleanup_files(video_path, audio_path)

            total_time = time.time() - start_time
            text_length = len(text)

            logger.info(f"[{video_id}] 提取完成!")
            logger.info(f"[{video_id}] 文本长度: {text_length} 字符")
            logger.info(f"[{video_id}] 语音识别耗时: {transcribe_time:.2f}秒")
            logger.info(f"[{video_id}] 总耗时: {total_time:.2f}秒")
            logger.info(f"[{video_id}] 文本预览: {text[:100]}...")

            if show_progress:
                print(f"文本提取完成! (共{text_length}字, 耗时{total_time:.1f}秒)")

            return text

        except Exception as e:
            total_time = time.time() - start_time
            logger.error(f"[{video_id}] 提取出错 (耗时: {total_time:.2f}秒): {str(e)}")
            raise


class DouyinProcessor:
    """抖音视频处理器 - 支持多种转录策略"""

    def __init__(
        self,
        api_key: str = "",
        provider: str = "auto",
        api_base_url: Optional[str] = None,
        model: Optional[str] = None
    ):
        # 自动检测 API 密钥和 provider
        if not api_key:
            api_key = self._detect_api_key(provider)

        self.provider = self._normalize_provider(provider, api_key)
        self.api_key = api_key
        self.temp_dir = Path(tempfile.mkdtemp())

        # 创建对应的策略实例
        if self.provider == "dashscope":
            self.strategy = DashscopeStrategy(api_key, model=model)
        else:
            self.strategy = SiliconFlowStrategy(
                api_key,
                api_base_url=api_base_url,
                model=model
            )

    def _detect_api_key(self, provider: str) -> str:
        """根据 provider 选择对应的 API_KEY"""
        if provider == "dashscope":
            key = DASHSCOPE_API_KEY
        elif provider == "siliconflow":
            key = SILICONFLOW_API_KEY
        else:  # auto
            # 优先使用 Dashscope API Key
            key = DASHSCOPE_API_KEY or SILICONFLOW_API_KEY

        if not key:
            raise ValueError(
                "未设置 API 密钥。请设置以下环境变量之一:\n"
                "- DASHSCOPE_API_KEY (阿里云百炼，推荐)\n"
                "- SILICONFLOW_API_KEY (硅基流动)\n"
                "- API_KEY (通用)"
            )
        return key

    def _normalize_provider(self, provider: str, api_key: str) -> Literal["dashscope", "siliconflow"]:
        """规范化 provider 名称，支持 auto 自动检测"""
        if provider == "auto":
            # 自动检测：优先使用 Dashscope，其次 SiliconFlow
            if DASHSCOPE_API_KEY or (api_key and "dashscope" in api_key.lower()):
                return "dashscope"
            return "siliconflow"

        provider = provider.lower()
        if provider in ("dashscope", "aliyun", "百炼"):
            return "dashscope"
        elif provider in ("siliconflow", "硅基流动"):
            return "siliconflow"
        else:
            raise ValueError(f"不支持的 provider: {provider}")

    def __del__(self):
        """清理临时目录"""
        if hasattr(self, 'temp_dir') and self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def parse_share_url(self, share_text: str) -> dict:
        """从分享文本中提取无水印视频链接"""
        # 提取分享链接
        urls = re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', share_text)
        if not urls:
            raise ValueError("未找到有效的分享链接")

        share_url = urls[0]
        share_response = requests.get(share_url, headers=HEADERS)
        video_id = share_response.url.split("?")[0].strip("/").split("/")[-1]
        share_url = f'https://www.iesdouyin.com/share/video/{video_id}'

        # 获取视频页面内容
        response = requests.get(share_url, headers=HEADERS)
        response.raise_for_status()

        pattern = re.compile(
            pattern=r"window\._ROUTER_DATA\s*=\s*(.*?)</script>",
            flags=re.DOTALL,
        )
        find_res = pattern.search(response.text)

        if not find_res or not find_res.group(1):
            raise ValueError("从HTML中解析视频信息失败")

        # 解析JSON数据
        json_data = json.loads(find_res.group(1).strip())
        VIDEO_ID_PAGE_KEY = "video_(id)/page"
        NOTE_ID_PAGE_KEY = "note_(id)/page"

        if VIDEO_ID_PAGE_KEY in json_data["loaderData"]:
            original_video_info = json_data["loaderData"][VIDEO_ID_PAGE_KEY]["videoInfoRes"]
        elif NOTE_ID_PAGE_KEY in json_data["loaderData"]:
            original_video_info = json_data["loaderData"][NOTE_ID_PAGE_KEY]["videoInfoRes"]
        else:
            raise Exception("无法从JSON中解析视频或图集信息")

        data = original_video_info["item_list"][0]

        # 获取视频信息
        video_url = data["video"]["play_addr"]["url_list"][0].replace("playwm", "play")
        desc = data.get("desc", "").strip() or f"douyin_{video_id}"

        # 替换文件名中的非法字符
        desc = re.sub(r'[\\/:*?"<>|]', '_', desc)

        return {
            "url": video_url,
            "title": desc,
            "video_id": video_id
        }

    def download_video(self, video_info: dict, output_dir: Optional[Path] = None, show_progress: bool = True) -> Path:
        """下载视频到指定目录"""
        if output_dir is None:
            output_dir = self.temp_dir
        else:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{video_info['video_id']}.mp4"
        filepath = output_dir / filename

        if show_progress:
            print(f"正在下载视频: {video_info['title']}")

        response = requests.get(video_info['url'], headers=HEADERS, stream=True)
        response.raise_for_status()

        # 获取文件大小
        total_size = int(response.headers.get('content-length', 0))

        # 下载文件
        downloaded = 0
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if show_progress and total_size > 0:
                        progress = downloaded / total_size * 100
                        print(f"\r下载进度: {progress:.1f}%", end="", flush=True)

        if show_progress:
            print(f"\n视频下载完成: {filepath}")
        return filepath


def get_video_info(share_link: str) -> dict:
    """获取视频信息和下载链接"""
    processor = DouyinProcessor()
    return processor.parse_share_url(share_link)


def download_video(share_link: str, output_dir: str = ".") -> Path:
    """下载视频到指定目录"""
    processor = DouyinProcessor()
    video_info = processor.parse_share_url(share_link)
    return processor.download_video(video_info, Path(output_dir))


def extract_text(
    share_link: str,
    api_key: Optional[str] = None,
    provider: str = "auto",
    output_dir: Optional[str] = None,
    save_video: bool = False,
    show_progress: bool = True
) -> dict:
    """
    从视频中提取文案并保存到文件

    参数:
        share_link: 抖音分享链接或包含链接的文本
        api_key: API 密钥 (可选，默认从环境变量读取)
        provider: API 提供商 (可选: "auto", "dashscope", "siliconflow")
        output_dir: 输出目录 (可选)
        save_video: 是否保存视频 (可选)
        show_progress: 是否显示进度 (可选)

    返回:
        dict: 包含 video_info, text, output_path 的字典
    """
    processor = DouyinProcessor(api_key=api_key or "", provider=provider)

    if show_progress:
        print("正在解析抖音分享链接...")
    video_info = processor.parse_share_url(share_link)

    if show_progress:
        print(f"使用 {processor.provider.upper()} API 提取文本...")

    # 使用策略模式提取文本
    text_content = processor.strategy.extract_text(video_info, show_progress=show_progress)

    result = {
        "video_info": video_info,
        "text": text_content,
        "output_path": None,
        "provider": processor.provider
    }

    # 保存到文件
    if output_dir:
        output_base = Path(output_dir)
        video_folder = output_base / video_info['video_id']
        video_folder.mkdir(parents=True, exist_ok=True)

        # 保存文案为 Markdown 格式
        transcript_path = video_folder / "transcript.md"
        with open(transcript_path, 'w', encoding='utf-8') as f:
            f.write(f"# {video_info['title']}\n\n")
            f.write(f"| 属性 | 值 |\n")
            f.write(f"|------|----|\n")
            f.write(f"| 视频ID | `{video_info['video_id']}` |\n")
            f.write(f"| 提取时间 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} |\n")
            f.write(f"| API提供商 | {processor.provider} |\n")
            f.write(f"| 下载链接 | [点击下载]({video_info['url']}) |\n\n")
            f.write(f"---\n\n")
            f.write(f"## 文案内容\n\n")
            f.write(text_content)

        result["output_path"] = str(video_folder)

        if show_progress:
            print(f"文案已保存到: {transcript_path}")

        # 保存视频 (可选)
        if save_video:
            if show_progress:
                print("正在下载视频...")
            video_path = processor.download_video(video_info, output_dir=video_folder, show_progress=show_progress)
            if show_progress:
                print(f"视频已保存到: {video_path}")

    return result


def main():
    parser = argparse.ArgumentParser(
        description="抖音无水印视频下载和文案提取工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 获取视频信息和下载链接
  python douyin_downloader.py --link "抖音分享链接" --action info

  # 下载视频
  python douyin_downloader.py --link "抖音分享链接" --action download --output ./videos

  # 提取文案 (自动选择 API)
  python douyin_downloader.py --link "抖音分享链接" --action extract --output ./output

  # 使用阿里云百炼 API 提取文案 (推荐，支持视频 URL 直传)
  python douyin_downloader.py --link "抖音分享链接" --action extract --provider dashscope

  # 使用硅基流动 API 提取文案
  python douyin_downloader.py --link "抖音分享链接" --action extract --provider siliconflow

  # 提取文案并同时保存视频
  python douyin_downloader.py --link "抖音分享链接" --action extract --output ./output --save-video
        """
    )

    parser.add_argument("--link", "-l", required=True, help="抖音分享链接或包含链接的文本")
    parser.add_argument("--action", "-a", choices=["info", "download", "extract"],
                        default="info", help="操作类型: info(获取信息), download(下载视频), extract(提取文案)")
    parser.add_argument("--output", "-o", default="./output", help="输出目录 (默认 ./output)")
    parser.add_argument("--api-key", "-k", help="API 密钥 (也可通过环境变量设置)")
    parser.add_argument("--provider", "-p", choices=["siliconflow", "dashscope", "auto"],
                        default="auto", help="API 提供商: auto(自动), dashscope(阿里云百炼), siliconflow(硅基流动)")
    parser.add_argument("--save-video", "-v", action="store_true", help="提取文案时同时保存视频")
    parser.add_argument("--quiet", "-q", action="store_true", help="安静模式，减少输出")

    args = parser.parse_args()

    try:
        if args.action == "info":
            info = get_video_info(args.link)
            print("\n" + "=" * 50)
            print("视频信息:")
            print("=" * 50)
            print(f"视频ID: {info['video_id']}")
            print(f"标题: {info['title']}")
            print(f"下载链接: {info['url']}")
            print("=" * 50)

        elif args.action == "download":
            video_path = download_video(args.link, args.output)
            print(f"\n视频已保存到: {video_path}")

        elif args.action == "extract":
            result = extract_text(
                args.link,
                api_key=args.api_key,
                provider=args.provider,
                output_dir=args.output,
                save_video=args.save_video,
                show_progress=not args.quiet
            )

            if not args.quiet:
                print("\n" + "=" * 50)
                print("提取完成!")
                print("=" * 50)
                print(f"视频ID: {result['video_info']['video_id']}")
                print(f"标题: {result['video_info']['title']}")
                print(f"API提供商: {result.get('provider', 'N/A')}")
                if result['output_path']:
                    print(f"保存位置: {result['output_path']}")
                print("=" * 50)
                print("\n文案内容:\n")
                print(result['text'][:500] + "..." if len(result['text']) > 500 else result['text'])
                print("\n" + "=" * 50)

    except Exception as e:
        print(f"\n错误: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
