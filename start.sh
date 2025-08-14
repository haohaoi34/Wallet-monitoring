#!/bin/bash

# EVM钱包监控软件启动脚本
# 自动检测依赖、安装并启动程序

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
PURPLE='\033[0;35m'
NC='\033[0m' # No Color

# 图标定义
CHECKMARK="✅"
CROSSMARK="❌"
WARNING="⚠️"
ROCKET="🚀"
GEAR="⚙️"
PACKAGE="📦"
LIGHTNING="⚡"

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo -e "${CYAN}${ROCKET} EVM钱包监控软件启动程序${NC}"
echo "=================================================="
echo -e "${BLUE}项目目录: ${SCRIPT_DIR}${NC}"
echo ""

# 检查Python环境
check_python() {
    echo -e "${BLUE}${GEAR} 检查Python环境...${NC}"
    
    if command -v python3 >/dev/null 2>&1; then
        PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2)
        PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d'.' -f1)
        PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d'.' -f2)
        
        if [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -ge 7 ]; then
            echo -e "${GREEN}${CHECKMARK} Python版本检查通过: $PYTHON_VERSION${NC}"
            PYTHON_CMD="python3"
            return 0
        else
            echo -e "${RED}${CROSSMARK} Python版本过低: $PYTHON_VERSION (需要 >= 3.7)${NC}"
            echo -e "${YELLOW}请升级Python或联系管理员${NC}"
            return 1
        fi
    else
        echo -e "${RED}${CROSSMARK} 未检测到Python3${NC}"
        echo -e "${YELLOW}请安装Python3 (版本 >= 3.7)${NC}"
        return 1
    fi
}

# 检查pip
check_pip() {
    echo -e "${BLUE}${GEAR} 检查pip...${NC}"
    
    if command -v pip3 >/dev/null 2>&1; then
        PIP_CMD="pip3"
        echo -e "${GREEN}${CHECKMARK} pip3 可用${NC}"
    elif command -v pip >/dev/null 2>&1; then
        PIP_CMD="pip"
        echo -e "${GREEN}${CHECKMARK} pip 可用${NC}"
    else
        echo -e "${YELLOW}${WARNING} pip不可用，尝试使用python -m pip${NC}"
        PIP_CMD="$PYTHON_CMD -m pip"
    fi
    
    return 0
}

# 检查单个Python包
check_package() {
    local package_name=$1
    if $PYTHON_CMD -c "import $package_name" 2>/dev/null; then
        return 0
    else
        return 1
    fi
}

# 安装单个包
install_package() {
    local package_spec=$1
    local package_name=$2
    
    echo -e "${YELLOW}正在安装 $package_spec...${NC}"
    
    # 尝试多种安装方法
    if $PIP_CMD install --user "$package_spec" >/dev/null 2>&1; then
        echo -e "${GREEN}${CHECKMARK} $package_name 安装成功${NC}"
        return 0
    elif $PIP_CMD install --user --break-system-packages "$package_spec" >/dev/null 2>&1; then
        echo -e "${GREEN}${CHECKMARK} $package_name 安装成功 (使用 --break-system-packages)${NC}"
        return 0
    elif $PIP_CMD install "$package_spec" >/dev/null 2>&1; then
        echo -e "${GREEN}${CHECKMARK} $package_name 安装成功 (全局安装)${NC}"
        return 0
    else
        echo -e "${RED}${CROSSMARK} $package_name 安装失败${NC}"
        return 1
    fi
}

# 检查并安装所有依赖
check_dependencies() {
    echo -e "${BLUE}${PACKAGE} 检查Python依赖包...${NC}"
    
    # 定义核心依赖包映射 (导入名 -> 包规格)
    declare -A core_packages=(
        ["web3"]="web3==6.11.3"
        ["eth_account"]="eth-account==0.10.0"
        ["colorama"]="colorama==0.4.6"
        ["requests"]="requests==2.31.0"
        ["psutil"]="psutil==5.9.6"
        ["Crypto"]="pycryptodome==3.19.0"
    )
    
    # 定义可选依赖包 (用于增强功能)
    declare -A optional_packages=(
        ["yaml"]="pyyaml==6.0.1"
        ["aiohttp"]="aiohttp==3.9.1"
        ["pandas"]="pandas==2.1.4"
        ["numpy"]="numpy==1.24.4"
    )
    
    missing_packages=()
    optional_missing=()
    
    # 检查核心依赖包
    echo -e "${CYAN}检查核心依赖包...${NC}"
    for import_name in "${!core_packages[@]}"; do
        package_spec="${core_packages[$import_name]}"
        package_display=$(echo "$package_spec" | cut -d'=' -f1)
        
        if check_package "$import_name"; then
            echo -e "${GREEN}${CHECKMARK} $package_display 已安装${NC}"
        else
            echo -e "${YELLOW}${WARNING} $package_display 未安装 (核心依赖)${NC}"
            missing_packages+=("$package_spec:$package_display")
        fi
    done
    
    # 检查可选依赖包
    echo -e "${CYAN}检查可选依赖包...${NC}"
    for import_name in "${!optional_packages[@]}"; do
        package_spec="${optional_packages[$import_name]}"
        package_display=$(echo "$package_spec" | cut -d'=' -f1)
        
        if check_package "$import_name"; then
            echo -e "${GREEN}${CHECKMARK} $package_display 已安装 (可选)${NC}"
        else
            echo -e "${BLUE}${WARNING} $package_display 未安装 (可选，可提升性能)${NC}"
            optional_missing+=("$package_spec:$package_display")
        fi
    done
    
    # 安装缺失的包
    if [ ${#missing_packages[@]} -ne 0 ]; then
        echo -e "\n${YELLOW}${PACKAGE} 需要安装 ${#missing_packages[@]} 个依赖包...${NC}"
        
        failed_packages=()
        for package_info in "${missing_packages[@]}"; do
            package_spec=$(echo "$package_info" | cut -d':' -f1)
            package_name=$(echo "$package_info" | cut -d':' -f2)
            
            if ! install_package "$package_spec" "$package_name"; then
                failed_packages+=("$package_name")
            fi
        done
        
        if [ ${#failed_packages[@]} -ne 0 ]; then
            echo -e "\n${RED}${CROSSMARK} 以下核心包安装失败: ${failed_packages[*]}${NC}"
            echo -e "${YELLOW}请手动安装这些包或检查网络连接${NC}"
            echo -e "${YELLOW}手动安装命令示例:${NC}"
            for pkg in "${failed_packages[@]}"; do
                echo -e "  pip3 install --user $pkg"
            done
            return 1
        else
            echo -e "\n${GREEN}${CHECKMARK} 所有核心依赖包安装完成${NC}"
        fi
    else
        echo -e "${GREEN}${CHECKMARK} 所有核心依赖包已满足${NC}"
    fi
    
    # 尝试安装可选依赖包
    if [ ${#optional_missing[@]} -ne 0 ]; then
        echo -e "\n${BLUE}${PACKAGE} 检测到 ${#optional_missing[@]} 个可选依赖包未安装${NC}"
        read -p "是否安装可选依赖包以提升性能? (Y/n): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Nn]$ ]]; then
            echo -e "${YELLOW}已跳过可选依赖包安装${NC}"
        else
            echo -e "${BLUE}正在安装可选依赖包...${NC}"
            for package_info in "${optional_missing[@]}"; do
                package_spec=$(echo "$package_info" | cut -d':' -f1)
                package_name=$(echo "$package_info" | cut -d':' -f2)
                
                if ! install_package "$package_spec" "$package_name"; then
                    echo -e "${YELLOW}${WARNING} $package_name 安装失败 (可选包，不影响核心功能)${NC}"
                fi
            done
        fi
    fi
    
    return 0
}

# 检查主程序文件
check_main_program() {
    echo -e "${BLUE}${GEAR} 检查主程序文件...${NC}"
    
    if [ -f "evm_monitor.py" ]; then
        echo -e "${GREEN}${CHECKMARK} 主程序文件存在${NC}"
        return 0
    else
        echo -e "${RED}${CROSSMARK} 主程序文件不存在: evm_monitor.py${NC}"
        echo -e "${YELLOW}请确保在正确的目录运行此脚本${NC}"
        return 1
    fi
}

# 显示系统信息
show_system_info() {
    echo -e "${CYAN}系统信息:${NC}"
    echo "  操作系统: $(uname -s)"
    echo "  架构: $(uname -m)"
    if command -v python3 >/dev/null 2>&1; then
        echo "  Python版本: $(python3 --version 2>&1)"
    fi
    echo "  工作目录: $(pwd)"
    echo ""
}

# 显示启动横幅
show_banner() {
    echo -e "${PURPLE}"
    echo "╔══════════════════════════════════════════════╗"
    echo "║          EVM 钱包监控软件 v2.1               ║"
    echo "║                                              ║"
    echo "║  🔐 安全的私钥加密存储                        ║"
    echo "║  🌐 支持 12+ 主流区块链网络                   ║"
    echo "║  💸 自动余额监控和转账                        ║"
    echo "║  ⚡ 智能调速和并发优化                        ║"
    echo "║  🧠 多RPC故障转移                            ║"
    echo "║  📊 实时性能监控                             ║"
    echo "║  📝 完整的日志记录                           ║"
    echo "║  🔄 状态恢复功能                             ║"
    echo "║  🎮 友好的交互界面                           ║"
    echo "╚══════════════════════════════════════════════╝"
    echo -e "${NC}"
}

# 主启动流程
main() {
    show_banner
    show_system_info
    
    # 环境检查
    if ! check_python; then
        echo -e "\n${RED}环境检查失败，无法启动程序${NC}"
        exit 1
    fi
    
    if ! check_pip; then
        echo -e "\n${RED}pip检查失败，无法继续${NC}"
        exit 1
    fi
    
    if ! check_main_program; then
        echo -e "\n${RED}程序文件检查失败${NC}"
        exit 1
    fi
    
    # 依赖检查和安装
    if ! check_dependencies; then
        echo -e "\n${YELLOW}依赖安装不完整，但仍可尝试启动程序${NC}"
        echo -e "${YELLOW}如果程序启动失败，请手动安装缺失的依赖包${NC}"
        read -p "是否继续启动程序? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo -e "${YELLOW}已取消启动${NC}"
            exit 1
        fi
    fi
    
    echo -e "\n${GREEN}${LIGHTNING} 环境检查完成，正在启动程序...${NC}"
    echo "=================================================="
    echo ""
    
    # 启动主程序
    exec $PYTHON_CMD evm_monitor.py
}

# 错误处理
handle_error() {
    echo -e "\n${RED}${CROSSMARK} 启动过程中出现错误${NC}"
    echo -e "${YELLOW}请检查错误信息并重试${NC}"
    exit 1
}

# 捕获错误和中断
trap 'handle_error' ERR
trap 'echo -e "\n${YELLOW}启动已取消${NC}"; exit 0' INT

# 执行主函数
main "$@"
