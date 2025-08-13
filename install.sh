#!/bin/bash

# EVM钱包监控软件一键安装脚本
# 使用方法: curl -fsSL https://raw.githubusercontent.com/haohaoi34/Wallet-monitoring/main/install.sh | bash

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${CYAN}🚀 EVM钱包监控软件一键安装程序${NC}"
echo "=================================================="

# 清理pip缓存
echo -e "${BLUE}🧹 清理系统缓存...${NC}"
pip3 cache purge >/dev/null 2>&1 || true
rm -rf ~/.cache/pip/* >/dev/null 2>&1 || true

# 创建项目目录
PROJECT_DIR="$HOME/evm_wallet_monitor"

if [ -d "$PROJECT_DIR" ]; then
    echo -e "${YELLOW}⚠️ 项目目录已存在${NC}"
    
    # 备份重要文件
    echo -e "${BLUE}📦 备份重要文件...${NC}"
    BACKUP_DIR="${PROJECT_DIR}_backup_$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$BACKUP_DIR"
    
    # 保存日志文件
    if [ -f "$PROJECT_DIR/monitor.log" ]; then
        cp "$PROJECT_DIR/monitor.log" "$BACKUP_DIR/"
        echo -e "${GREEN}✅ 日志文件已备份${NC}"
    fi
    
    # 保存钱包文件
    if [ -f "$PROJECT_DIR/wallets.json" ]; then
        cp "$PROJECT_DIR/wallets.json" "$BACKUP_DIR/"
        echo -e "${GREEN}✅ 钱包文件已备份${NC}"
    fi
    
    # 保存监控状态
    if [ -f "$PROJECT_DIR/monitor_state.json" ]; then
        cp "$PROJECT_DIR/monitor_state.json" "$BACKUP_DIR/"
        echo -e "${GREEN}✅ 监控状态已备份${NC}"
    fi
    
    # 删除旧目录
    rm -rf "$PROJECT_DIR"
    echo -e "${GREEN}✅ 旧文件清理完成${NC}"
fi

# 创建新的项目目录
mkdir -p "$PROJECT_DIR"
cd "$PROJECT_DIR"
echo -e "${GREEN}✅ 项目目录创建完成: $PROJECT_DIR${NC}"

# 恢复备份的文件
if [ -n "$BACKUP_DIR" ]; then
    echo -e "${BLUE}📦 恢复重要文件...${NC}"
    [ -f "$BACKUP_DIR/monitor.log" ] && cp "$BACKUP_DIR/monitor.log" ./ && echo -e "${GREEN}✅ 日志文件已恢复${NC}"
    [ -f "$BACKUP_DIR/wallets.json" ] && cp "$BACKUP_DIR/wallets.json" ./ && echo -e "${GREEN}✅ 钱包文件已恢复${NC}"
    [ -f "$BACKUP_DIR/monitor_state.json" ] && cp "$BACKUP_DIR/monitor_state.json" ./ && echo -e "${GREEN}✅ 监控状态已恢复${NC}"
fi

# 安装Python依赖包
echo -e "${BLUE}⚙️ 安装Python依赖包...${NC}"

PACKAGES=(
    "web3==6.11.3"
    "eth-account==0.10.0"
    "colorama==0.4.6"
    "pyyaml==6.0.1"
    "requests==2.31.0"
    "pycryptodome==3.19.0"
)

for package in "${PACKAGES[@]}"; do
    echo -e "${YELLOW}正在安装 $package...${NC}"
    pip3 install --user "$package" --break-system-packages --no-cache-dir >/dev/null 2>&1 || true
done

echo -e "${GREEN}✅ 依赖安装完成${NC}"

# 下载程序文件
echo -e "${BLUE}📥 正在下载程序文件...${NC}"

# 清理GitHub缓存
REPO_URL="https://raw.githubusercontent.com/haohaoi34/Wallet-monitoring/main"
GITHUB_CACHE_BUSTER="?$(date +%s)"

# 下载主程序
if curl -fsSL "$REPO_URL/evm_monitor.py$GITHUB_CACHE_BUSTER" -o evm_monitor.py; then
    echo -e "${GREEN}✅ 主程序下载完成${NC}"
else
    echo -e "${RED}❌ 主程序下载失败${NC}"
    touch evm_monitor.py
fi

# 下载启动脚本
if curl -fsSL "$REPO_URL/start.sh$GITHUB_CACHE_BUSTER" -o start.sh; then
    echo -e "${GREEN}✅ 启动脚本下载完成${NC}"
else
    echo -e "${YELLOW}⚠️ 启动脚本下载失败，创建本地版本${NC}"
    cat > start.sh << 'EOF'
#!/bin/bash
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}🚀 启动EVM钱包监控软件${NC}"
echo "================================"

check_dependencies() {
    echo -e "${BLUE}📦 检查Python依赖...${NC}"
    
    REQUIRED_PACKAGES=(
        "web3"
        "eth_account"
        "colorama"
        "pyyaml"
        "requests"
        "pycryptodome"
    )
    
    MISSING_PACKAGES=()
    
    for package in "${REQUIRED_PACKAGES[@]}"; do
        if ! python3 -c "import $package" 2>/dev/null; then
            MISSING_PACKAGES+=("$package")
        fi
    done
    
    if [ ${#MISSING_PACKAGES[@]} -ne 0 ]; then
        echo -e "${YELLOW}⚠️ 检测到缺失依赖包，正在安装...${NC}"
        pip3 install --user web3==6.11.3 eth-account==0.10.0 colorama==0.4.6 pyyaml==6.0.1 requests==2.31.0 pycryptodome==3.19.0 --break-system-packages --no-cache-dir
    else
        echo -e "${GREEN}✅ 所有依赖已满足${NC}"
    fi
}

main() {
    check_dependencies
    echo -e "${GREEN}✅ 环境检查完成，启动程序...${NC}"
    echo "================================"
    python3 evm_monitor.py
}

trap 'echo -e "\n${YELLOW}👋 程序已退出${NC}"; exit 0' INT
main "$@"
EOF
fi

chmod +x *.py *.sh

# 创建命令行快捷方式
BASHRC="$HOME/.bashrc"
if [ -f "$BASHRC" ]; then
    if ! grep -q "alias evm-monitor=" "$BASHRC"; then
        echo "alias evm-monitor='cd $PROJECT_DIR && ./start.sh'" >> "$BASHRC"
        echo -e "${GREEN}✅ 命令行快捷方式已创建 (使用 'evm-monitor' 命令启动)${NC}"
    fi
fi

# 安装完成
echo ""
echo "=================================================="
echo -e "${GREEN}✅ EVM钱包监控软件安装完成！${NC}"
echo "=================================================="
echo ""

# 创建启动器
cat > "$PROJECT_DIR/run.sh" << 'EOF'
#!/bin/bash
cd "$(dirname "$0")"
exec setsid ./start.sh < /dev/tty > /dev/tty 2>&1
EOF
chmod +x "$PROJECT_DIR/run.sh"

# 自动启动程序
echo -e "${CYAN}正在启动程序...${NC}"
echo ""
"$PROJECT_DIR/run.sh"
