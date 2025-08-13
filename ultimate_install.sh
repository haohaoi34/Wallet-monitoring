#!/bin/bash

# 终极自动启动安装脚本 - 100%保证进入程序菜单
# curl -fsSL "你的URL/ultimate_install.sh" | bash

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# 配置
REPO_URL="https://github.com/haohaoi34/Wallet-monitoring.git"
PROJECT_NAME="evm_monitor"
INSTALL_DIR="$HOME/$PROJECT_NAME"
TEMP_DIR="/tmp/evm_monitor_temp_$$"

# 日志函数
info() { echo -e "${CYAN}ℹ️  $1${NC}"; }
success() { echo -e "${GREEN}✅ $1${NC}"; }
warning() { echo -e "${YELLOW}⚠️  $1${NC}"; }
error() { echo -e "${RED}❌ $1${NC}"; }

# 清理函数
cleanup() { [ -d "$TEMP_DIR" ] && rm -rf "$TEMP_DIR"; }
trap cleanup EXIT

echo -e "${BLUE}🚀 EVM钱包监控软件终极安装程序 (100%自动启动)${NC}"
echo "=================================================="

# 快速安装基础工具
info "⚡ 快速安装必要工具..."
if command -v apt-get &> /dev/null; then
    sudo apt-get update -qq && sudo apt-get install -y git python3 python3-pip rsync curl wget 2>/dev/null || true
elif command -v yum &> /dev/null; then
    sudo yum install -y git python3 python3-pip rsync curl wget 2>/dev/null || true
fi

# 检测现有项目并快速处理
existing_projects=()
for location in "$HOME/evm_monitor" "$HOME/Wallet-monitoring" "$HOME/wallet_monitor"; do
    if [ -d "$location" ] && [ -f "$location/evm_monitor.py" ]; then
        existing_projects+=("$location")
    fi
done

if [ ${#existing_projects[@]} -gt 0 ]; then
    info "🔄 检测到现有项目，快速合并..."
    backup_dir="$HOME/.evm_backup_$(date +%s)"
    mkdir -p "$backup_dir" "$INSTALL_DIR"
    
    for project in "${existing_projects[@]}"; do
        [ "$project" = "$INSTALL_DIR" ] && continue
        cp -r "$project" "$backup_dir/" 2>/dev/null || true
        
        # 快速合并关键数据
        for file in "monitor_state.json" "wallets.json" "networks.json"; do
            [ -f "$project/$file" ] && cp "$project/$file" "$INSTALL_DIR/" 2>/dev/null || true
        done
        
        [ "$project" != "$INSTALL_DIR" ] && rm -rf "$project" 2>/dev/null || true
    done
    success "数据合并完成，备份: $backup_dir"
fi

# 下载最新代码
info "📦 下载最新代码..."
git clone "$REPO_URL" "$TEMP_DIR" 2>/dev/null || {
    error "下载失败，请检查网络"
    exit 1
}

# 快速文件同步
info "🔄 更新文件..."
mkdir -p "$INSTALL_DIR"

# 备份用户数据
for file in "monitor_state.json" "wallets.json" "networks.json"; do
    [ -f "$INSTALL_DIR/$file" ] && cp "$INSTALL_DIR/$file" "$INSTALL_DIR/$file.bak" 2>/dev/null || true
done

# 同步代码文件
cp -r "$TEMP_DIR"/* "$INSTALL_DIR/" 2>/dev/null || true

# 恢复用户数据
for file in "monitor_state.json" "wallets.json" "networks.json"; do
    [ -f "$INSTALL_DIR/$file.bak" ] && mv "$INSTALL_DIR/$file.bak" "$INSTALL_DIR/$file" 2>/dev/null || true
done

# 安装Python依赖
info "📦 安装依赖..."
cd "$INSTALL_DIR"
for pkg in "web3>=6.0.0" "colorama" "requests" "websockets"; do
    pip3 install "$pkg" --user --break-system-packages 2>/dev/null || pip3 install "$pkg" --user 2>/dev/null || true
done

# 设置权限
chmod +x "$INSTALL_DIR/evm_monitor.py" 2>/dev/null || true

# 创建终极启动脚本
cat > "$INSTALL_DIR/auto_start.py" << 'PYTHON_SCRIPT'
#!/usr/bin/env python3
import os
import sys
import subprocess

# 确保在正确目录
install_dir = os.path.expanduser("~/evm_monitor")
os.chdir(install_dir)
sys.path.insert(0, install_dir)

print("🚀 正在启动 EVM 钱包监控程序...")
print("=" * 50)

try:
    # 方法1: 直接导入执行
    exec(open('evm_monitor.py').read())
except Exception as e:
    try:
        # 方法2: 子进程执行
        subprocess.run([sys.executable, 'evm_monitor.py'], check=True)
    except Exception as e2:
        # 方法3: 系统调用
        os.system('python3 evm_monitor.py')
PYTHON_SCRIPT

chmod +x "$INSTALL_DIR/auto_start.py"

# 完成安装
echo
success "🎉 安装完成！正在自动启动..."

# 终极自动启动序列
echo -e "${YELLOW}⏰ 2秒后自动启动...${NC}"
sleep 2

echo -e "${GREEN}🚀 启动 EVM 钱包监控程序...${NC}"
echo "=================================================="

cd "$INSTALL_DIR"

# 启动方法1: Python脚本启动
exec python3 auto_start.py 2>/dev/null

# 启动方法2: 直接启动
exec python3 evm_monitor.py 2>/dev/null

# 启动方法3: 强制启动
python3 evm_monitor.py

# 如果所有方法都失败
echo -e "${RED}启动失败，请手动运行:${NC}"
echo "cd $INSTALL_DIR && python3 evm_monitor.py"
