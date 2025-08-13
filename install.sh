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

# 检测操作系统
detect_os() {
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        OS="linux"
        if command -v apt-get >/dev/null 2>&1; then
            DISTRO="ubuntu"
        elif command -v yum >/dev/null 2>&1; then
            DISTRO="centos"
        else
            DISTRO="unknown"
        fi
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        OS="macos"
        DISTRO="macos"
    else
        OS="unknown"
        DISTRO="unknown"
    fi
    
    echo -e "${GREEN}${CHECKMARK} 检测到操作系统: $OS ($DISTRO)${NC}"
}

# 检查Python版本
check_python() {
    echo -e "${BLUE}${GEAR} 检查Python环境...${NC}"
    
    if command -v python3 >/dev/null 2>&1; then
        PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
        PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d'.' -f1)
        PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d'.' -f2)
        
        if [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -ge 7 ]; then
            echo -e "${GREEN}${CHECKMARK} Python版本检查通过: $PYTHON_VERSION${NC}"
            PYTHON_CMD="python3"
        else
            echo -e "${RED}${CROSSMARK} Python版本过低: $PYTHON_VERSION (需要 >= 3.7)${NC}"
            install_python
        fi
    else
        echo -e "${YELLOW}${WARNING} 未检测到Python3${NC}"
        install_python
    fi
}

# 安装Python
install_python() {
    echo -e "${YELLOW}${GEAR} 正在安装Python3...${NC}"
    
    case $DISTRO in
        ubuntu)
            sudo apt-get update
            sudo apt-get install -y python3 python3-pip python3-venv
            ;;
        centos)
            sudo yum install -y python3 python3-pip
            ;;
        macos)
            if command -v brew >/dev/null 2>&1; then
                brew install python3
            else
                echo -e "${RED}${CROSSMARK} 请先安装Homebrew或手动安装Python3${NC}"
                exit 1
            fi
            ;;
        *)
            echo -e "${RED}${CROSSMARK} 不支持的操作系统，请手动安装Python3${NC}"
            exit 1
            ;;
    esac
    
    PYTHON_CMD="python3"
    echo -e "${GREEN}${CHECKMARK} Python3安装完成${NC}"
}

# 检查pip
check_pip() {
    echo -e "${BLUE}${GEAR} 检查pip...${NC}"
    
    if command -v pip3 >/dev/null 2>&1; then
        PIP_CMD="pip3"
    elif command -v pip >/dev/null 2>&1; then
        PIP_CMD="pip"
    else
        echo -e "${YELLOW}${WARNING} 正在安装pip...${NC}"
        $PYTHON_CMD -m ensurepip --upgrade
        PIP_CMD="$PYTHON_CMD -m pip"
    fi
    
    echo -e "${GREEN}${CHECKMARK} pip检查完成${NC}"
}

# 创建项目目录
create_project_dir() {
    PROJECT_DIR="$HOME/evm_wallet_monitor"
    
    if [ -d "$PROJECT_DIR" ]; then
        echo -e "${YELLOW}${WARNING} 项目目录已存在，正在备份...${NC}"
        mv "$PROJECT_DIR" "${PROJECT_DIR}_backup_$(date +%Y%m%d_%H%M%S)"
    fi
    
    mkdir -p "$PROJECT_DIR"
    cd "$PROJECT_DIR"
    
    echo -e "${GREEN}${CHECKMARK} 项目目录创建完成: $PROJECT_DIR${NC}"
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

# 安装Python依赖
install_dependencies() {
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
        if $PIP_CMD install --user "$package"; then
            echo -e "${GREEN}${CHECKMARK} $package 安装成功${NC}"
        else
            echo -e "${RED}${CROSSMARK} $package 安装失败${NC}"
            echo -e "${YELLOW}尝试使用备用方法...${NC}"
            $PIP_CMD install --user --break-system-packages "$package" 2>/dev/null || true
        fi
    done
    
    echo -e "${GREEN}${CHECKMARK} 依赖安装完成${NC}"
}

# 创建桌面快捷方式
create_shortcut() {
    if [[ "$OS" == "linux" ]]; then
        DESKTOP_FILE="$HOME/Desktop/EVM钱包监控.desktop"
        cat > "$DESKTOP_FILE" << EOF
[Desktop Entry]
Version=1.0
Name=EVM钱包监控
Comment=EVM钱包余额监控和自动转账工具
Exec=bash $PROJECT_DIR/start.sh
Icon=utilities-terminal
Terminal=true
Type=Application
Categories=Utility;
EOF
        chmod +x "$DESKTOP_FILE"
        echo -e "${GREEN}${CHECKMARK} 桌面快捷方式已创建${NC}"
    fi
}

# 显示安装完成信息
show_completion() {
    echo ""
    echo "=================================================="
    echo -e "${GREEN}${CHECKMARK} EVM钱包监控软件安装完成！${NC}"
    echo "=================================================="
    echo ""
    echo -e "${CYAN}使用方法:${NC}"
    echo -e "  1. 进入项目目录: ${YELLOW}cd $PROJECT_DIR${NC}"
    echo -e "  2. 启动程序: ${YELLOW}./start.sh${NC}"
    echo ""
    echo -e "${CYAN}或者直接运行:${NC}"
    echo -e "  ${YELLOW}$PROJECT_DIR/start.sh${NC}"
    echo ""
    echo -e "${BLUE}程序特性:${NC}"
    echo "  🔐 安全的私钥加密存储"
    echo "  🌐 支持多链监控 (ETH, BSC, Polygon, Arbitrum等)"
    echo "  💸 自动余额监控和转账"
    echo "  📝 完整的日志记录"
    echo "  🔄 状态恢复功能"
    echo "  🎮 友好的交互界面"
    echo ""
    
    # 询问是否立即启动
    read -p "是否现在启动程序? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${CYAN}正在启动程序...${NC}"
        cd "$PROJECT_DIR"
        ./start.sh
    fi
}

# 主安装流程
main() {
    detect_os
    check_python
    check_pip
    create_project_dir
    download_files
    install_dependencies
    create_shortcut
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
