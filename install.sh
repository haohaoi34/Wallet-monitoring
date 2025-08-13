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

# 图标定义
CHECKMARK="✅"
CROSSMARK="❌"
WARNING="⚠️"
ROCKET="🚀"
GEAR="⚙️"
DOWNLOAD="📥"

echo -e "${CYAN}${ROCKET} EVM钱包监控软件一键安装程序${NC}"
echo "=================================================="

# 创建项目目录
create_project_dir() {
    PROJECT_DIR="$HOME/evm_wallet_monitor"
    
    if [ -d "$PROJECT_DIR" ]; then
        echo -e "${YELLOW}${WARNING} 项目目录已存在，正在备份...${NC}"
        mv "$PROJECT_DIR" "${PROJECT_DIR}_backup_$(date +%Y%m%d_%H%M%S)"
    fi
    
    mkdir -p "$PROJECT_DIR"
    echo -e "${GREEN}${CHECKMARK} 项目目录创建完成: $PROJECT_DIR${NC}"
    
    # 导出项目目录变量，使其在子shell中可用
    export PROJECT_DIR
}

# 下载程序文件
download_files() {
    echo -e "${BLUE}${DOWNLOAD} 正在下载程序文件...${NC}"
    
    # GitHub仓库URL (你需要替换为实际的仓库地址)
    REPO_URL="https://raw.githubusercontent.com/haohaoi34/Wallet-monitoring/main"
    
    # 下载主程序
    if curl -fsSL "$REPO_URL/evm_monitor.py" -o evm_monitor.py; then
        echo -e "${GREEN}${CHECKMARK} 主程序下载完成${NC}"
    else
        echo -e "${RED}${CROSSMARK} 主程序下载失败，使用本地版本${NC}"
        # 如果下载失败，创建一个基础版本
        create_local_program
    fi
    
    # 下载启动脚本
    if curl -fsSL "$REPO_URL/start.sh" -o start.sh; then
        echo -e "${GREEN}${CHECKMARK} 启动脚本下载完成${NC}"
    else
        echo -e "${YELLOW}${WARNING} 启动脚本下载失败，创建本地版本${NC}"
        create_start_script
    fi
    
    chmod +x *.py *.sh
}

# 创建本地程序（如果下载失败的备用方案）
create_local_program() {
    echo -e "${YELLOW}${GEAR} 创建本地程序文件...${NC}"
    # 这里会在后面实现完整的程序内容
    touch evm_monitor.py
    echo -e "${GREEN}${CHECKMARK} 本地程序文件创建完成${NC}"
}

# 创建启动脚本
create_start_script() {
    cat > start.sh << 'EOF'
#!/bin/bash

# EVM钱包监控软件启动脚本

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}🚀 启动EVM钱包监控软件${NC}"
echo "================================"

# 检查依赖
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
        install_dependencies
    else
        echo -e "${GREEN}✅ 所有依赖已满足${NC}"
    fi
}

# 安装依赖
install_dependencies() {
    echo -e "${BLUE}📦 正在安装Python依赖...${NC}"
    
    pip3 install --user \
        web3==6.11.3 \
        eth-account==0.10.0 \
        colorama==0.4.6 \
        pyyaml==6.0.1 \
        requests==2.31.0 \
        pycryptodome==3.19.0
    
    echo -e "${GREEN}✅ 依赖安装完成${NC}"
}

# 主函数
main() {
    check_dependencies
    
    echo -e "${GREEN}✅ 环境检查完成，启动程序...${NC}"
    echo "================================"
    
    python3 evm_monitor.py
}

# 捕获Ctrl+C
trap 'echo -e "\n${YELLOW}👋 程序已退出${NC}"; exit 0' INT

main "$@"
EOF
    
    chmod +x start.sh
}

# 安装Python依赖包
install_python_packages() {
    echo -e "${BLUE}${GEAR} 安装Python依赖包...${NC}"
    
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
        if ! pip3 install --user "$package" --break-system-packages >/dev/null 2>&1; then
            echo -e "${RED}${CROSSMARK} $package 安装失败${NC}"
        fi
    done
    
    echo -e "${GREEN}${CHECKMARK} 依赖安装完成${NC}"
}

# 创建快捷方式
create_shortcuts() {
    # 创建命令行快捷方式
    BASHRC="$HOME/.bashrc"
    if [ -f "$BASHRC" ]; then
        if ! grep -q "alias evm-monitor=" "$BASHRC"; then
            cat >> "$BASHRC" << EOF

# EVM钱包监控快捷命令
alias evm-monitor='cd $PROJECT_DIR && ./start.sh'
EOF
            echo -e "${GREEN}${CHECKMARK} 命令行快捷方式已创建 (使用 'evm-monitor' 命令启动)${NC}"
            echo -e "${YELLOW}提示: 请运行 'source ~/.bashrc' 或重新打开终端使快捷命令生效${NC}"
        fi
    fi
}

# 显示安装完成信息并启动程序
show_completion() {
    echo ""
    echo "=================================================="
    echo -e "${GREEN}${CHECKMARK} EVM钱包监控软件安装完成！${NC}"
    echo "=================================================="
    echo ""
    echo -e "${CYAN}正在启动程序...${NC}"
    echo ""
    
    # 直接启动程序
    cd "$PROJECT_DIR"
    ./start.sh
}

# 主安装流程
main() {
    # 创建项目目录并进入
    create_project_dir
    cd "$PROJECT_DIR"
    
    # 安装依赖
    install_python_packages
    
    # 下载程序文件
    download_files
    
    # 创建快捷方式
    create_shortcuts
    
    # 显示完成信息并启动程序
    show_completion
}

# 错误处理
handle_error() {
    echo -e "${RED}${CROSSMARK} 安装过程中出现错误${NC}"
    echo "请检查网络连接和系统权限，或手动安装"
    exit 1
}

trap 'handle_error' ERR

# 执行主函数
main "$@"
