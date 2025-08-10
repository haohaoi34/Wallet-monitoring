#!/bin/bash

# 🚀 钱包监控器 - 一键安装脚本
# 下载并执行: curl -fsSL https://raw.githubusercontent.com/haohaoi34/Wallet-monitoring/main/install.sh | bash

# 错误处理
set -e
trap 'error_handler $? $LINENO' ERR

# 错误处理函数
error_handler() {
    local exit_code=$1
    local line_number=$2
    
    echo -e "\n${RED}❌ 安装过程中发生错误 (行号: $line_number, 退出码: $exit_code)${NC}"
    echo -e "${YELLOW}💡 可能的解决方案:${NC}"
    echo "1. 确保您有足够的磁盘空间"
    echo "2. 确保您有网络连接"
    echo "3. 确保您有sudo权限"
    echo "4. 尝试手动安装: sudo apt-get update && sudo apt-get install python3-venv"
    echo "5. 如果问题持续，请检查错误日志"
    
    exit $exit_code
}

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
    echo "║                🚀 钱包监控器安装程序 🚀                         ║"
    echo "║              企业级多链钱包监控系统                              ║"
    echo "║                    版本 2.1                                   ║"
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

# 检查系统依赖
check_system_dependencies() {
    if [[ "$OS" == "linux" && "$DISTRO" == "debian" ]]; then
        log "检查系统依赖..."
        
        # 检查必要的系统包
        local missing_packages=()
        
        # 检查基础工具
        for pkg in curl wget git; do
            if ! command -v $pkg &> /dev/null; then
                missing_packages+=($pkg)
            fi
        done
        
        # 检查编译工具
        if ! command -v gcc &> /dev/null; then
            missing_packages+=(build-essential)
        fi
        
        # 检查Python开发包
        if ! dpkg -l | grep -q python3-dev; then
            missing_packages+=(python3-dev)
        fi
        
        # 检查SSL和FFI开发包
        if ! dpkg -l | grep -q libssl-dev; then
            missing_packages+=(libssl-dev)
        fi
        
        if ! dpkg -l | grep -q libffi-dev; then
            missing_packages+=(libffi-dev)
        fi
        
        # 安装缺失的包
        if [[ ${#missing_packages[@]} -gt 0 ]]; then
            warn "发现缺失的系统依赖: ${missing_packages[*]}"
            log "正在安装缺失的系统依赖..."
            sudo apt-get update
            sudo apt-get install -y "${missing_packages[@]}"
            success "系统依赖安装完成"
        else
            success "所有系统依赖已安装"
        fi
    fi
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
    
    # 在Ubuntu/Debian系统上检查并安装python3-venv
    if [[ "$OS" == "linux" && "$DISTRO" == "debian" ]]; then
        log "检查python3-venv包..."
        if ! dpkg -l | grep -q python3-venv; then
            warn "未找到python3-venv包，正在安装..."
            sudo apt-get update
            sudo apt-get install -y python3-venv
            success "python3-venv包安装完成"
        else
            success "python3-venv包已安装"
        fi
    fi
}

# 根据操作系统安装Python
install_python() {
    case $OS in
        "linux")
            case $DISTRO in
                "debian")
                    log "正在Debian/Ubuntu上安装Python和系统依赖..."
                    sudo apt-get update
                    sudo apt-get install -y python3 python3-pip python3-venv curl wget git build-essential python3-dev libssl-dev libffi-dev
                    success "系统依赖安装完成"
                    ;;
                "redhat")
                    log "正在RedHat/CentOS上安装Python..."
                    sudo yum install -y python3 python3-pip curl wget git gcc python3-devel openssl-devel libffi-devel
                    ;;
                "arch")
                    log "正在Arch Linux上安装Python..."
                    sudo pacman -S python python-pip curl wget git base-devel
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
    
    # 优先下载改进版脚本并命名为主程序
    if curl -fsSL "$REPO_URL/wallet_monitor_simplified.py" -o wallet_monitor.py; then
        success "已下载改进版程序 (wallet_monitor.py)"
    else
        warn "改进版脚本不可用，回落到原始版本"
        curl -fsSL "$REPO_URL/wallet_monitor.py" -o wallet_monitor.py
    fi
    
    curl -fsSL "$REPO_URL/requirements.txt" -o requirements.txt
    curl -fsSL "$REPO_URL/config.env.template" -o config.env.template
    
    success "项目文件下载完成"
}

# 检查并安装python3-venv包
check_venv_package() {
    if [[ "$OS" == "linux" && "$DISTRO" == "debian" ]]; then
        log "检查python3-venv包..."
        if ! dpkg -l | grep -q python3-venv; then
            warn "未找到python3-venv包，正在安装..."
            sudo apt-get update
            sudo apt-get install -y python3-venv
            success "python3-venv包安装完成"
        else
            success "python3-venv包已安装"
        fi
    fi
}

# 清理不完整的虚拟环境
cleanup_incomplete_venv() {
    if [[ -d "venv" ]]; then
        # 检查虚拟环境是否完整
        if [[ ! -f "venv/bin/activate" ]] && [[ ! -f "venv/Scripts/activate" ]]; then
            warn "检测到不完整的虚拟环境，正在清理..."
            rm -rf venv
            success "不完整的虚拟环境已清理"
        fi
    fi
}

# 清理依赖冲突
cleanup_dependency_conflicts() {
    log "清理依赖冲突..."
    
    # 检查并清理可能冲突的包
    if python -m pip show urllib3 2>/dev/null | grep -q "Version: 2\."; then
        warn "检测到urllib3 2.x版本，正在降级到1.x..."
        python -m pip uninstall -y urllib3
        python -m pip install "urllib3>=1.26.0,<2.0.0" -q
    fi
    
    if python -m pip show requests 2>/dev/null | grep -q "Version: 2\."; then
        warn "检测到requests版本过低，正在升级..."
        python -m pip install --upgrade "requests>=2.25.1,<3.0.0" -q
    fi
    
    # 确保six包存在
    if ! python -c "import six" 2>/dev/null; then
        log "安装six包..."
        python -m pip install "six>=1.16.0" -q
    fi
}

# 调试虚拟环境状态
debug_venv_status() {
    log "调试虚拟环境状态..."
    echo "当前目录: $(pwd)"
    echo "Python命令: $PYTHON_CMD"
    echo "Python版本: $($PYTHON_CMD --version 2>&1)"
    echo "venv目录存在: $([[ -d "venv" ]] && echo "是" || echo "否")"
    if [[ -d "venv" ]]; then
        echo "venv目录内容:"
        ls -la venv/
        echo "venv/bin目录存在: $([[ -d "venv/bin" ]] && echo "是" || echo "否")"
        echo "venv/bin/activate存在: $([[ -f "venv/bin/activate" ]] && echo "是" || echo "否")"
    fi
}

# 设置虚拟环境
setup_venv() {
    log "正在设置Python虚拟环境..."
    
    # 检查并安装必要的包
    check_venv_package
    
    # 清理可能不完整的虚拟环境
    cleanup_incomplete_venv
    
    if [[ ! -d "venv" ]]; then
        # 尝试创建虚拟环境
        log "正在创建虚拟环境..."
        if ! $PYTHON_CMD -m venv venv; then
            error "创建虚拟环境失败"
            debug_venv_status
            if [[ "$OS" == "linux" && "$DISTRO" == "debian" ]]; then
                warn "尝试重新安装python3-venv包..."
                sudo apt-get install --reinstall -y python3-venv
                log "重新尝试创建虚拟环境..."
                if ! $PYTHON_CMD -m venv venv; then
                    error "虚拟环境创建仍然失败，请手动安装python3-venv包"
                    error "请运行: sudo apt-get install python3-venv"
                    debug_venv_status
                    exit 1
                fi
            else
                exit 1
            fi
        fi
        success "虚拟环境已创建"
    else
        success "虚拟环境已存在"
    fi
    
    # 验证虚拟环境是否真的创建成功
    if [[ ! -d "venv" ]]; then
        error "虚拟环境目录不存在，创建失败"
        exit 1
    fi
    
    # 检查激活脚本是否存在
    if [[ "$OS" == "windows" ]]; then
        ACTIVATE_SCRIPT="venv/Scripts/activate"
    else
        ACTIVATE_SCRIPT="venv/bin/activate"
    fi
    
    if [[ ! -f "$ACTIVATE_SCRIPT" ]]; then
        error "虚拟环境激活脚本不存在: $ACTIVATE_SCRIPT"
        error "虚拟环境可能创建不完整，请删除venv目录后重试"
        exit 1
    fi
    
    # 激活虚拟环境
    log "正在激活虚拟环境..."
    case $OS in
        "windows")
            source venv/Scripts/activate
            ;;
        *)
            source venv/bin/activate
            ;;
    esac
    
    success "虚拟环境已激活"
    
    # 清理依赖冲突
    cleanup_dependency_conflicts
}

# 安装依赖
install_dependencies() {
    log "正在安装Python依赖..."
    
    # 升级pip
    log "升级pip..."
    if ! python -m pip install --upgrade pip -q; then
        warn "pip升级失败，继续安装依赖..."
    fi
    
    # 清理可能冲突的包
    log "清理可能冲突的依赖..."
    python -m pip uninstall -y urllib3 requests six types-requests 2>/dev/null || true
    
    # 安装基础HTTP依赖
    log "安装基础HTTP依赖..."
    python -m pip install "urllib3>=1.26.0,<2.0.0" "requests>=2.25.1,<3.0.0" "six>=1.16.0" -q
    
    # 安装依赖
    log "安装Python依赖包..."
    # 先尝试加速源（非强制）
    PIP_INDEX_URL=${PIP_INDEX_URL:-}
    if [[ -n "$PIP_INDEX_URL" ]]; then
        log "使用自定义PIP源: $PIP_INDEX_URL"
        export PIP_INDEX_URL
    fi
    if ! python -m pip install -r requirements.txt -q; then
        error "依赖安装失败，尝试逐个安装..."
        
        # 逐个安装关键依赖（按顺序避免冲突）
        local critical_deps=("six" "urllib3" "requests" "web3" "cryptography" "aiohttp" "python-dotenv" "colorama")
        for dep in "${critical_deps[@]}"; do
            log "安装 $dep..."
            if ! python -m pip install "$dep" -q; then
                warn "安装 $dep 失败，继续下一个..."
            fi
        done
        
        # 尝试安装可选依赖
        local optional_deps=("solana" "solders" "base58" "alchemy" "python-telegram-bot" "asyncio-throttle" "eth-account" "typing-extensions")
        for dep in "${optional_deps[@]}"; do
            log "安装可选依赖 $dep..."
            python -m pip install "$dep" -q || warn "安装 $dep 失败（可选）"
        done
    fi
    
    success "依赖安装完成"
}

# 验证安装
verify_installation() {
    log "验证安装..."
    
    # 检查虚拟环境
    if [[ ! -d "venv" ]]; then
        error "虚拟环境不存在"
        return 1
    fi
    
    # 检查激活脚本
    if [[ ! -f "venv/bin/activate" ]]; then
        error "虚拟环境激活脚本不存在"
        return 1
    fi
    
    # 检查主要Python文件
    if [[ ! -f "wallet_monitor.py" ]]; then
        error "主程序文件不存在"
        return 1
    fi
    
    # 检查配置文件模板
    if [[ ! -f "config.env.template" ]]; then
        error "配置文件模板不存在"
        return 1
    fi
    
    # 测试Python导入
    log "测试Python依赖..."
    
    # 测试基础HTTP依赖
    if ! python -c "import urllib3, requests, six" 2>/dev/null; then
        error "基础HTTP依赖导入失败"
        return 1
    fi
    
    # 测试核心依赖
    if ! python -c "import web3, solana, cryptography, aiohttp, dotenv, colorama" 2>/dev/null; then
        warn "部分Python依赖导入失败，但程序可能仍能运行"
    else
        success "所有关键Python依赖导入成功"
    fi
    
    # 检查依赖版本
    log "检查依赖版本..."
    python -c "
import sys
try:
    import urllib3
    print(f'urllib3版本: {urllib3.__version__}')
    if urllib3.__version__.startswith('2.'):
        print('⚠️  urllib3版本过高，可能导致兼容性问题')
except:
    pass

try:
    import requests
    print(f'requests版本: {requests.__version__}')
except:
    pass

try:
    import web3
    print(f'web3版本: {web3.__version__}')
except:
    pass
"
    
    success "安装验证完成"
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
    echo "║  1. 选择是否立即启动程序                                     ║"
    echo "║  2. 在主菜单中配置API密钥和钱包地址                         ║"
    echo "║  3. 开始监控您的钱包                                         ║"
    echo "║                                                              ║"
    echo "║  项目位置: $PROJECT_DIR                                        ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

# 启动应用选项
launch_app() {
    echo -e "${YELLOW}"
    read -p "是否现在启动应用程序？(y/N): " -n 1 -r
    echo -e "${NC}"
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        auto_launch_app
    else
        echo -e "${GREEN}您可以稍后使用以下命令启动应用:${NC}"
        echo -e "${CYAN}cd $PROJECT_DIR && source venv/bin/activate && python wallet_monitor.py${NC}"
    fi
}

# 自动启动应用
auto_launch_app() {
    log "正在启动钱包监控器..."
    echo -e "${GREEN}🚀 钱包监控器安装完成${NC}"
    echo ""
    
    # 直接提供两种启动方式
    echo -e "${CYAN}┌─────────────────────────────────────────────────────────────┐${NC}"
    echo -e "${CYAN}│${NC} ${YELLOW}🎯 启动方式选择${NC} ${CYAN}│${NC}"
    echo -e "${CYAN}├─────────────────────────────────────────────────────────────┤${NC}"
    echo -e "${CYAN}│${NC} ${GREEN}方式1: 立即启动（推荐）${NC} ${CYAN}│${NC}"
    echo -e "${CYAN}│${NC} 输入: ${GREEN}1${NC} 然后按回车 ${CYAN}│${NC}"
    echo -e "${CYAN}│${NC} ${CYAN}│${NC}"
    echo -e "${CYAN}│${NC} ${YELLOW}方式2: 手动启动${NC} ${CYAN}│${NC}"
    echo -e "${CYAN}│${NC} 复制以下命令执行: ${CYAN}│${NC}"
    echo -e "${CYAN}│${NC} ${GREEN}cd $(pwd)${NC} ${CYAN}│${NC}"
    echo -e "${CYAN}│${NC} ${GREEN}source venv/bin/activate${NC} ${CYAN}│${NC}"
    echo -e "${CYAN}│${NC} ${GREEN}python wallet_monitor.py --force-interactive${NC} ${CYAN}│${NC}"
    echo -e "${CYAN}└─────────────────────────────────────────────────────────────┘${NC}"
    echo ""
    
    # 使用更兼容的输入方式，添加超时
    echo -n "请选择启动方式 (1 立即启动 / 其他键显示手动启动说明): "
    
    # 尝试读取用户输入，如果失败则使用默认值
    if read -t 30 choice 2>/dev/null && [ "$choice" = "1" ]; then
        echo ""
        echo -e "${GREEN}🚀 启动交互式钱包监控器...${NC}"
        echo -e "${CYAN}💡 如果程序无法正常运行，请按 Ctrl+C 退出后手动启动${NC}"
        echo ""
        sleep 2
        # 直接启动交互式模式
        python wallet_monitor.py --force-interactive
    else
        echo ""
        echo -e "${YELLOW}📝 手动启动说明:${NC}"
        echo ""
        echo -e "${GREEN}1. 进入项目目录:${NC}"
        echo -e "   cd $(pwd)"
        echo ""
        echo -e "${GREEN}2. 激活虚拟环境:${NC}"
        echo -e "   source venv/bin/activate"
        echo ""
        echo -e "${GREEN}3. 启动程序:${NC}"
        echo -e "   python wallet_monitor.py --force-interactive"
        echo ""
        echo -e "${CYAN}💡 复制上述命令逐行执行即可启动程序${NC}"
        echo -e "${YELLOW}📍 项目位置: $(pwd)${NC}"
    fi
}

# 主安装函数
main() {
    print_banner
    
    # 安装步骤
    detect_os
    check_system_dependencies
    check_python
    setup_project
    download_files
    setup_venv
    install_dependencies
    create_config
    verify_installation
    
    # 显示完成信息
    show_next_steps
    
    # 根据设置决定是否自动启动
    if [[ "${AUTO_LAUNCH:-true}" == "true" ]]; then
        auto_launch_app
    else
        launch_app
    fi
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
        echo "  --no-auto      安装完成后不自动启动程序"
        echo ""
        exit 0
        ;;
    --no-auto)
        AUTO_LAUNCH=false
        main "$@"
        ;;
    *)
        AUTO_LAUNCH=true
        main "$@"
        ;;
esac 
