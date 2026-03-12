#!/bin/bash
# Ubuntu 服务器部署脚本 - 一键启动 douyin-mcp-server
# 使用方法: bash deploy.sh

set -e

echo "========================================="
echo "  抖音文案提取器 WebUI 部署脚本"
echo "========================================="
echo ""

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "📍 项目目录: $SCRIPT_DIR"
echo ""

# 检查 .env 文件
if [ ! -f ".env" ]; then
    echo "❌ 未找到 .env 文件，请先创建并配置 API Key"
    echo "   示例: echo 'DASHSCOPE_API_KEY=sk-xxx' > .env"
    exit 1
fi
echo "✅ 找到 .env 文件"

# 检查虚拟环境
if [ ! -d "venv" ]; then
    echo ""
    echo "📦 未找到虚拟环境，正在创建..."
    python3 -m venv venv
    source venv/bin/activate
    pip install --upgrade pip
    pip install -e .
else
    echo "✅ 虚拟环境已存在"
fi

# 检查 PORT 配置
PORT=$(grep "^PORT=" .env | cut -d'=' -f2)
PORT=${PORT:-8080}
echo "🔌 服务端口: $PORT"

# 获取当前用户
USER=$(whoami)

# 创建 systemd 服务文件
SERVICE_FILE="/tmp/douyin-webui.service"
cat > "$SERVICE_FILE" << EOF
[Unit]
Description=Douyin Video Transcript Extractor WebUI
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$SCRIPT_DIR
Environment="PATH=$SCRIPT_DIR/venv/bin"
EnvironmentFile=$SCRIPT_DIR/.env
ExecStart=$SCRIPT_DIR/venv/bin/python web/app.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

echo ""
echo "📋 安装 systemd 服务..."
sudo cp "$SERVICE_FILE" /etc/systemd/system/douyin-webui.service
sudo systemctl daemon-reload
sudo systemctl enable douyin-webui

echo ""
echo "▶️  启动服务..."
sudo systemctl restart douyin-webui

# 等待服务启动
sleep 2

# 检查服务状态
echo ""
echo "========================================="
echo "  部署完成！"
echo "========================================="
echo ""

# 显示服务状态
if sudo systemctl is-active --quiet douyin-webui; then
    echo "✅ 服务状态: 运行中"
else
    echo "❌ 服务状态: 未运行"
    echo ""
    echo "查看错误日志:"
    sudo journalctl -u douyin-webui -n 20 --no-pager
    exit 1
fi

echo ""
echo "🌐 访问地址: http://localhost:$PORT"
echo ""
echo "常用命令:"
echo "  查看状态:   sudo systemctl status douyin-webui"
echo "  重启服务:   sudo systemctl restart douyin-webui"
echo "  停止服务:   sudo systemctl stop douyin-webui"
echo "  查看日志:   sudo journalctl -u douyin-webui -f"
echo ""
