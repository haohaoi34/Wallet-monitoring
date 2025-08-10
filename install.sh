#!/bin/bash

# 🚀 钱包监控器 - 一键安装脚本
# 下载并执行: curl -fsSL https://raw.githubusercontent.com/haohaoi34/Wallet-monitoring/main/install.sh | bash

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
PURPLE='\033[0;35m'
NC='\033[0m'

# 横幅
print_banner() {
    clear
    echo -e "${CYAN}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║                🚀 钱包监控器安装程序 🚀                    ║"
    echo "║              企业级多链钱包监控系统                          ║"
    echo "║                    版本 2.1                                 ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

# 日志函数
log() { echo -e "${BLUE}🔄 $1${NC}"; }
success() { echo -e "${GREEN}✅ $1${NC}"; }
warn() { echo -e "${YELLOW}⚠️  $1${NC}"; }
error() { echo -e "${RED}❌ $1${NC}"; }

# 检测操作系统
detect_os() {
    log "正在检测操作系统..."
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        OS="linux"
        if command -v apt-get &> /dev/null; then
            DISTRO="debian"
        elif command -v yum &> /dev/null; then
            DISTRO="redhat"
        elif command -v pacman &> /dev/null; then
            DISTRO="arch"
        else
            DISTRO="unknown"
        fi
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        OS="macos"
        DISTRO="macos"
    elif [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "win32" ]]; then
        OS="windows"
        DISTRO="windows"
    else
        OS="unknown"
        DISTRO="unknown"
    fi
    success "检测到: $OS ($DISTRO)"
}

# 检查并安装Python
check_python() {
    log "正在检查Python安装..."
    PYTHON_CMD=""
    
    for cmd in python3.11 python3.10 python3.9 python3.8 python3 python; do
        if command -v $cmd &> /dev/null; then
            VERSION=$($cmd --version 2>&1 | grep -oE '[0-9]+\.[0-9]+')
            MAJOR=$(echo $VERSION | cut -d. -f1)
            MINOR=$(echo $VERSION | cut -d. -f2)
            
            if [[ $MAJOR -eq 3 ]] && [[ $MINOR -ge 8 ]]; then
                PYTHON_CMD=$cmd
                PYTHON_VERSION=$VERSION
                break
            fi
        fi
    done
    
    if [[ -z "$PYTHON_CMD" ]]; then
        error "未找到Python 3.8+，正在安装..."
        install_python
    else
        success "找到Python $PYTHON_VERSION"
    fi
}

# 根据操作系统安装Python
install_python() {
    case $OS in
        "linux")
            case $DISTRO in
                "debian")
                    log "正在Debian/Ubuntu上安装Python..."
                    sudo apt-get update
                    sudo apt-get install -y python3 python3-pip python3-venv curl wget git
                    ;;
                "redhat")
                    log "正在RedHat/CentOS上安装Python..."
                    sudo yum install -y python3 python3-pip curl wget git
                    ;;
                "arch")
                    log "正在Arch Linux上安装Python..."
                    sudo pacman -S python python-pip curl wget git
                    ;;
                *)
                    error "不支持的Linux发行版。请手动安装Python 3.8+"
                    exit 1
                    ;;
            esac
            PYTHON_CMD="python3"
            ;;
        "macos")
            if command -v brew &> /dev/null; then
                log "正在通过Homebrew安装Python..."
                brew install python@3.9 curl wget git
            else
                error "未找到Homebrew。请从python.org安装Python 3.8+"
                exit 1
            fi
            PYTHON_CMD="python3"
            ;;
        "windows")
            error "请从python.org安装Python 3.8+并重新运行此脚本"
            exit 1
            ;;
        *)
            error "不支持的操作系统。请手动安装Python 3.8+"
            exit 1
            ;;
    esac
}

# 创建项目目录
setup_project() {
    log "正在设置项目目录..."
    
    # 创建项目目录
    PROJECT_DIR="$HOME/wallet-monitor"
    mkdir -p "$PROJECT_DIR"
    cd "$PROJECT_DIR"
    
    success "项目目录: $PROJECT_DIR"
}

# 下载项目文件
download_files() {
    log "正在下载项目文件..."
    
    # GitHub仓库URL
    REPO_URL="https://raw.githubusercontent.com/haohaoi34/Wallet-monitoring/main"
    
    # 下载主要文件
    curl -fsSL "$REPO_URL/wallet_monitor.py" -o wallet_monitor.py
    curl -fsSL "$REPO_URL/requirements.txt" -o requirements.txt
    curl -fsSL "$REPO_URL/config.env.template" -o config.env.template
    
    success "项目文件下载完成"
}

# 设置虚拟环境
setup_venv() {
    log "正在设置Python虚拟环境..."
    
    if [[ ! -d "venv" ]]; then
        $PYTHON_CMD -m venv venv
        success "虚拟环境已创建"
    else
        success "虚拟环境已存在"
    fi
    
    # 激活虚拟环境
    case $OS in
        "windows")
            source venv/Scripts/activate
            ;;
        *)
            source venv/bin/activate
            ;;
    esac
    
    success "虚拟环境已激活"
}

# 安装依赖
install_dependencies() {
    log "正在安装Python依赖..."
    
    # 升级pip
    python -m pip install --upgrade pip -q
    
    # 安装依赖
    python -m pip install -r requirements.txt -q
    
    success "依赖安装成功"
}

# 创建配置
create_config() {
    log "正在创建配置文件..."
    
    # 从模板创建.env
    if [[ ! -f ".env" ]]; then
        cp config.env.template .env
        success "配置模板已创建 (.env)"
        warn "请编辑.env文件，添加您的API密钥和设置"
    fi
    
    # 创建日志目录
    mkdir -p logs
    success "日志目录已创建"
}

# 显示后续步骤
show_next_steps() {
    echo -e "${CYAN}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║                    🎉 安装完成！ 🎉                        ║"
    echo "║                                                              ║"
    echo "║  后续步骤:                                                   ║"
    echo "║  1. 编辑配置: nano .env                                     ║"
    echo "║  2. 添加您的API密钥和目标地址                               ║"
    echo "║  3. 启动应用: python wallet_monitor.py                      ║"
    echo "║                                                              ║"
    echo "║  项目位置: $PROJECT_DIR                                     ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

# 启动应用选项
launch_app() {
    echo -e "${YELLOW}"
    read -p "是否现在启动应用程序？(y/N): " -n 1 -r
    echo -e "${NC}"
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        log "正在启动钱包监控器..."
        python wallet_monitor.py
    else
        echo -e "${GREEN}您可以稍后使用以下命令启动应用:${NC}"
        echo -e "${CYAN}cd $PROJECT_DIR && source venv/bin/activate && python wallet_monitor.py${NC}"
    fi
}

# 主安装函数
main() {
    print_banner
    
    # 安装步骤
    detect_os
    check_python
    setup_project
    download_files
    setup_venv
    install_dependencies
    create_config
    
    # 显示完成信息
    show_next_steps
    launch_app
}

# 处理命令行参数
case "${1:-}" in
    --help|-h)
        echo "钱包监控器一键安装程序"
        echo ""
        echo "使用方法:"
        echo "  curl -fsSL https://raw.githubusercontent.com/haohaoi34/Wallet-monitoring/main/install.sh | bash"
        echo ""
        echo "或下载后运行:"
        echo "  curl -fsSL https://raw.githubusercontent.com/haohaoi34/Wallet-monitoring/main/install.sh -o install.sh"
        echo "  chmod +x install.sh"
        echo "  ./install.sh"
        echo ""
        echo "选项:"
        echo "  --help, -h     显示此帮助信息"
        echo ""
        exit 0
        ;;
    *)
        main "$@"
        ;;
esac 
