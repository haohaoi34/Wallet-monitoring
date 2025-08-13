#!/bin/bash

# EVM钱包监控软件智能安装脚本
# 支持智能检测、数据合并、去重处理

set -e  # 遇到错误立即退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# 配置变量
REPO_URL="https://github.com/haohaoi34/Wallet-monitoring.git"
PROJECT_NAME="evm_monitor"
INSTALL_BASE_DIR="$HOME"
INSTALL_DIR="$INSTALL_BASE_DIR/$PROJECT_NAME"
TEMP_DIR="/tmp/evm_monitor_install_$$"
BACKUP_DIR="$HOME/.evm_monitor_backups"

# 日志函数
log_info() {
    echo -e "${CYAN}ℹ️  $1${NC}"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
}

# 清理函数
cleanup() {
    if [ -d "$TEMP_DIR" ]; then
        rm -rf "$TEMP_DIR"
    fi
}

# 注册清理函数
trap cleanup EXIT

# 检查依赖
check_dependencies() {
    log_info "检查系统依赖..."
    
    # 检查必需的命令
    local deps=("git" "python3" "pip3" "rsync")
    local missing_deps=()
    
    for dep in "${deps[@]}"; do
        if ! command -v "$dep" &> /dev/null; then
            missing_deps+=("$dep")
        fi
    done
    
    if [ ${#missing_deps[@]} -ne 0 ]; then
        log_error "缺少必需的依赖: ${missing_deps[*]}"
        log_info "正在安装缺少的依赖..."
        
        if command -v apt-get &> /dev/null; then
            sudo apt-get update
            sudo apt-get install -y git python3 python3-pip rsync
        elif command -v yum &> /dev/null; then
            sudo yum install -y git python3 python3-pip rsync
        elif command -v brew &> /dev/null; then
            brew install git python3 rsync
        else
            log_error "无法自动安装依赖，请手动安装: ${missing_deps[*]}"
            exit 1
        fi
    fi
    
    log_success "依赖检查完成"
}

# 创建备份目录
create_backup_dir() {
    if [ ! -d "$BACKUP_DIR" ]; then
        mkdir -p "$BACKUP_DIR"
        log_info "创建备份目录: $BACKUP_DIR"
    fi
}

# 检测现有项目
detect_existing_projects() {
    log_info "检测现有项目..."
    
    local found_projects=()
    
    # 搜索可能的项目位置
    local search_paths=(
        "$HOME/evm_monitor"
        "$HOME/Wallet-monitoring"
        "$HOME/wallet_monitor"
        "$HOME/EVM_Monitor"
        "$HOME/evm-monitor"
        "/opt/evm_monitor"
        "/usr/local/evm_monitor"
    )
    
    for path in "${search_paths[@]}"; do
        if [ -d "$path" ] && [ -f "$path/evm_monitor.py" ]; then
            found_projects+=("$path")
        fi
    done
    
    # 也搜索当前目录下的所有可能项目
    while IFS= read -r -d '' dir; do
        if [ -f "$dir/evm_monitor.py" ]; then
            found_projects+=("$dir")
        fi
    done < <(find "$HOME" -maxdepth 3 -type d -name "*monitor*" -print0 2>/dev/null || true)
    
    # 去重
    local unique_projects=()
    for project in "${found_projects[@]}"; do
        local realpath_project=$(realpath "$project" 2>/dev/null || echo "$project")
        if [[ ! " ${unique_projects[@]} " =~ " ${realpath_project} " ]]; then
            unique_projects+=("$realpath_project")
        fi
    done
    
    echo "${unique_projects[@]}"
}

# 分析项目数据
analyze_project_data() {
    local project_dir="$1"
    local data_files=()
    local config_files=()
    local wallet_files=()
    local log_files=()
    
    if [ -f "$project_dir/monitor_state.json" ]; then
        data_files+=("monitor_state.json")
    fi
    
    if [ -f "$project_dir/wallets.json" ]; then
        wallet_files+=("wallets.json")
    fi
    
    if [ -f "$project_dir/networks.json" ]; then
        config_files+=("networks.json")
    fi
    
    if [ -d "$project_dir/logs" ]; then
        log_files+=($(find "$project_dir/logs" -name "*.log" -type f 2>/dev/null || true))
    fi
    
    echo "DATA:${data_files[*]};CONFIG:${config_files[*]};WALLET:${wallet_files[*]};LOG:${log_files[*]}"
}

# 合并JSON文件
merge_json_files() {
    local source_file="$1"
    local target_file="$2"
    local merge_type="$3"
    
    if [ ! -f "$source_file" ]; then
        return 0
    fi
    
    if [ ! -f "$target_file" ]; then
        cp "$source_file" "$target_file"
        log_success "复制文件: $(basename "$source_file")"
        return 0
    fi
    
    log_info "合并JSON文件: $(basename "$source_file")"
    
    # 使用Python进行智能JSON合并
    python3 << EOF
import json
import sys

try:
    # 读取源文件和目标文件
    with open('$source_file', 'r', encoding='utf-8') as f:
        source_data = json.load(f)
    
    with open('$target_file', 'r', encoding='utf-8') as f:
        target_data = json.load(f)
    
    # 根据文件类型进行不同的合并策略
    merge_type = '$merge_type'
    
    if merge_type == 'state':
        # 监控状态合并：保留较新的数据，合并地址列表
        if isinstance(source_data, dict) and isinstance(target_data, dict):
            # 合并监控地址
            if 'monitored_addresses' in source_data and 'monitored_addresses' in target_data:
                for addr, data in source_data['monitored_addresses'].items():
                    if addr not in target_data['monitored_addresses']:
                        target_data['monitored_addresses'][addr] = data
            
            # 合并屏蔽的RPC
            if 'blocked_rpcs' in source_data:
                if 'blocked_rpcs' not in target_data:
                    target_data['blocked_rpcs'] = {}
                target_data['blocked_rpcs'].update(source_data['blocked_rpcs'])
            
            # 合并用户添加的代币
            if 'user_added_tokens' in source_data:
                if 'user_added_tokens' not in target_data:
                    target_data['user_added_tokens'] = []
                target_tokens = set(target_data['user_added_tokens'])
                for token in source_data['user_added_tokens']:
                    if token not in target_tokens:
                        target_data['user_added_tokens'].append(token)
    
    elif merge_type == 'wallets':
        # 钱包文件合并：去重合并
        if isinstance(source_data, dict) and isinstance(target_data, dict):
            for key, value in source_data.items():
                if key not in target_data:
                    target_data[key] = value
        elif isinstance(source_data, list) and isinstance(target_data, list):
            # 列表去重合并
            combined = target_data + [item for item in source_data if item not in target_data]
            target_data = combined
    
    elif merge_type == 'config':
        # 配置文件合并：保留目标文件，只添加新的网络配置
        if isinstance(source_data, dict) and isinstance(target_data, dict):
            for key, value in source_data.items():
                if key not in target_data:
                    target_data[key] = value
    
    # 写回目标文件
    with open('$target_file', 'w', encoding='utf-8') as f:
        json.dump(target_data, f, indent=2, ensure_ascii=False)
    
    print("✅ JSON合并成功")

except Exception as e:
    print(f"❌ JSON合并失败: {e}")
    sys.exit(1)
EOF
}

# 智能合并项目数据
smart_merge_projects() {
    local existing_projects=($1)
    
    if [ ${#existing_projects[@]} -eq 0 ]; then
        log_info "未发现现有项目，将进行全新安装"
        return 0
    fi
    
    log_warning "发现 ${#existing_projects[@]} 个现有项目:"
    for i in "${!existing_projects[@]}"; do
        local project="${existing_projects[$i]}"
        local size=$(du -sh "$project" 2>/dev/null | cut -f1 || echo "未知")
        echo "  $((i+1)). $project (大小: $size)"
    done
    
    echo
    log_info "智能合并策略:"
    echo "  • 保留所有监控地址和钱包数据"
    echo "  • 合并屏蔽的RPC和用户设置"
    echo "  • 去重处理，避免数据冗余"
    echo "  • 自动备份原始数据"
    
    # 创建统一的安装目录
    if [ ! -d "$INSTALL_DIR" ]; then
        mkdir -p "$INSTALL_DIR"
        log_info "创建统一项目目录: $INSTALL_DIR"
    fi
    
    # 备份并合并每个项目的数据
    for project_path in "${existing_projects[@]}"; do
        if [ "$project_path" = "$INSTALL_DIR" ]; then
            continue  # 跳过目标目录本身
        fi
        
        log_info "处理项目: $project_path"
        
        # 创建备份
        local backup_name="backup_$(basename "$project_path")_$(date +%Y%m%d_%H%M%S)"
        local backup_path="$BACKUP_DIR/$backup_name"
        
        cp -r "$project_path" "$backup_path"
        log_success "备份到: $backup_path"
        
        # 分析项目数据
        local data_info=$(analyze_project_data "$project_path")
        
        # 合并关键数据文件
        if [ -f "$project_path/monitor_state.json" ]; then
            merge_json_files "$project_path/monitor_state.json" "$INSTALL_DIR/monitor_state.json" "state"
        fi
        
        if [ -f "$project_path/wallets.json" ]; then
            merge_json_files "$project_path/wallets.json" "$INSTALL_DIR/wallets.json" "wallets"
        fi
        
        if [ -f "$project_path/networks.json" ]; then
            merge_json_files "$project_path/networks.json" "$INSTALL_DIR/networks.json" "config"
        fi
        
        # 合并日志文件（保留最近30天的）
        if [ -d "$project_path/logs" ]; then
            mkdir -p "$INSTALL_DIR/logs"
            find "$project_path/logs" -name "*.log" -type f -mtime -30 -exec cp {} "$INSTALL_DIR/logs/" \; 2>/dev/null || true
        fi
        
        # 删除旧项目目录（如果不是目标目录）
        if [ "$project_path" != "$INSTALL_DIR" ]; then
            log_info "清理旧项目目录: $project_path"
            rm -rf "$project_path"
        fi
    done
    
    log_success "所有项目数据已合并到: $INSTALL_DIR"
}

# 下载最新代码
download_latest_code() {
    log_info "下载最新代码..."
    
    # 创建临时目录
    mkdir -p "$TEMP_DIR"
    
    # 克隆仓库到临时目录
    if git clone "$REPO_URL" "$TEMP_DIR"; then
        log_success "代码下载成功"
    else
        log_error "代码下载失败"
        exit 1
    fi
}

# 更新项目文件
update_project_files() {
    log_info "更新项目文件..."
    
    # 复制新的代码文件（不覆盖数据文件）
    local exclude_patterns=(
        "--exclude=monitor_state.json"
        "--exclude=wallets.json" 
        "--exclude=networks.json"
        "--exclude=logs/"
        "--exclude=*.log"
        "--exclude=__pycache__/"
        "--exclude=*.pyc"
    )
    
    rsync -av "${exclude_patterns[@]}" "$TEMP_DIR/" "$INSTALL_DIR/"
    
    log_success "项目文件更新完成"
}

# 安装Python依赖
install_python_dependencies() {
    log_info "安装Python依赖..."
    
    cd "$INSTALL_DIR"
    
    # 检查requirements.txt
    if [ -f "requirements.txt" ]; then
        pip3 install -r requirements.txt --user
        log_success "Python依赖安装完成"
    else
        # 手动安装必需的包
        local packages=("web3" "colorama" "requests")
        for package in "${packages[@]}"; do
            pip3 install "$package" --user
        done
        log_success "核心Python包安装完成"
    fi
}

# 设置权限
set_permissions() {
    log_info "设置文件权限..."
    
    chmod +x "$INSTALL_DIR/evm_monitor.py"
    
    # 创建启动脚本
    cat > "$INSTALL_DIR/start.sh" << 'EOF'
#!/bin/bash
cd "$(dirname "$0")"
python3 evm_monitor.py "$@"
EOF
    
    chmod +x "$INSTALL_DIR/start.sh"
    
    log_success "权限设置完成"
}

# 主安装流程
main() {
    echo -e "${BLUE}"
    echo "🚀 EVM钱包监控软件智能安装程序"
    echo "=================================================="
    echo -e "${NC}"
    
    # 检查系统依赖
    check_dependencies
    
    # 创建备份目录
    create_backup_dir
    
    # 检测现有项目
    local existing_projects=($(detect_existing_projects))
    
    # 智能合并项目数据
    smart_merge_projects "${existing_projects[*]}"
    
    # 下载最新代码
    download_latest_code
    
    # 更新项目文件
    update_project_files
    
    # 安装Python依赖
    install_python_dependencies
    
    # 设置权限
    set_permissions
    
    echo
    echo -e "${GREEN}"
    echo "🎉 安装完成！"
    echo "=================================================="
    echo -e "${NC}"
    echo
    log_success "项目目录: $INSTALL_DIR"
    log_success "启动命令: cd $INSTALL_DIR && python3 evm_monitor.py"
    log_success "快捷启动: $INSTALL_DIR/start.sh"
    
    if [ ${#existing_projects[@]} -gt 0 ]; then
        echo
        log_info "数据合并完成:"
        echo "  • 所有项目数据已智能合并到统一目录"
        echo "  • 原始数据已备份到: $BACKUP_DIR"
        echo "  • 重复数据已自动去除"
    fi
    
    echo
    log_info "提示: 如果遇到任何问题，备份数据位于 $BACKUP_DIR"
}

# 运行主程序
main "$@"
