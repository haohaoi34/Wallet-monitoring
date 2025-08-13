#!/bin/bash

# EVM钱包监控软件智能安装脚本 - 支持数据合并与去重
# curl -fsSL https://raw.githubusercontent.com/haohaoi34/Wallet-monitoring/main/install.sh | bash

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

# 智能文件同步函数
smart_sync() {
    local source="$1"
    local target="$2"
    local exclude_patterns=("${@:3}")
    
    if command -v rsync &> /dev/null; then
        # 使用rsync进行高效同步
        local rsync_excludes=()
        for pattern in "${exclude_patterns[@]}"; do
            rsync_excludes+=("--exclude=$pattern")
        done
        rsync -av "${rsync_excludes[@]}" "$source/" "$target/"
    else
        # 使用cp命令替代
        info "使用cp命令同步文件..."
        
        # 创建目标目录
        mkdir -p "$target"
        
        # 复制文件，排除指定模式
        find "$source" -type f | while read -r file; do
            local relative_path="${file#$source/}"
            local should_exclude=false
            
            # 检查是否应该排除
            for pattern in "${exclude_patterns[@]}"; do
                if [[ "$relative_path" == *"$pattern"* ]]; then
                    should_exclude=true
                    break
                fi
            done
            
            # 如果不需要排除，则复制文件
            if [ "$should_exclude" = false ]; then
                local target_file="$target/$relative_path"
                local target_dir=$(dirname "$target_file")
                mkdir -p "$target_dir"
                cp "$file" "$target_file"
            fi
        done
        
        # 复制目录结构
        find "$source" -type d | while read -r dir; do
            local relative_path="${dir#$source/}"
            if [ -n "$relative_path" ]; then
                mkdir -p "$target/$relative_path"
            fi
        done
    fi
}

echo -e "${BLUE}🚀 EVM钱包监控软件一键安装程序${NC}"
echo "=================================================="

# 1. 清理系统缓存
info "🧹 清理系统缓存..."
sudo apt-get clean 2>/dev/null || true

# 2. 智能检测现有项目
info "🔍 智能检测现有项目..."
existing_projects=()

# 搜索所有可能的项目位置
search_locations=(
    "$HOME/evm_monitor"
    "$HOME/Wallet-monitoring" 
    "$HOME/wallet_monitor"
    "$HOME/EVM_Monitor"
    "$HOME/evm-monitor"
)

for location in "${search_locations[@]}"; do
    if [ -d "$location" ] && [ -f "$location/evm_monitor.py" ]; then
        existing_projects+=("$location")
        info "找到项目: $location"
    fi
done

# 3. 数据合并策略
if [ ${#existing_projects[@]} -gt 0 ]; then
    warning "检测到 ${#existing_projects[@]} 个现有项目，开始智能合并..."
    
    # 创建备份目录
    backup_dir="$HOME/.evm_monitor_backup_$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$backup_dir"
    
    # 准备合并目录
    merge_dir="$INSTALL_DIR"
    mkdir -p "$merge_dir"
    
    # 合并所有项目数据
    for project in "${existing_projects[@]}"; do
        if [ "$project" = "$merge_dir" ]; then continue; fi
        
        info "📦 备份并合并: $project"
        
        # 创建项目备份
        cp -r "$project" "$backup_dir/$(basename "$project")"
        
        # 智能合并JSON数据文件
        for json_file in "monitor_state.json" "wallets.json" "networks.json"; do
            if [ -f "$project/$json_file" ]; then
                if [ -f "$merge_dir/$json_file" ]; then
                    # 合并JSON文件
                    python3 -c "
import json
try:
    with open('$project/$json_file', 'r', encoding='utf-8') as f:
        src = json.load(f)
    with open('$merge_dir/$json_file', 'r', encoding='utf-8') as f:
        dst = json.load(f)
    
    # 智能合并逻辑
    if isinstance(src, dict) and isinstance(dst, dict):
        if 'monitored_addresses' in src and 'monitored_addresses' in dst:
            dst['monitored_addresses'].update(src['monitored_addresses'])
        if 'blocked_rpcs' in src:
            dst.setdefault('blocked_rpcs', {}).update(src['blocked_rpcs'])
        if 'user_added_tokens' in src:
            existing_tokens = set(dst.get('user_added_tokens', []))
            for token in src.get('user_added_tokens', []):
                if token not in existing_tokens:
                    dst.setdefault('user_added_tokens', []).append(token)
        dst.update({k: v for k, v in src.items() if k not in dst})
    
    with open('$merge_dir/$json_file', 'w', encoding='utf-8') as f:
        json.dump(dst, f, indent=2, ensure_ascii=False)
    print('✅ 合并完成: $json_file')
except Exception as e:
    print('⚠️ 合并失败: $json_file -', str(e))
" 2>/dev/null || cp "$project/$json_file" "$merge_dir/"
                else
                    cp "$project/$json_file" "$merge_dir/"
                fi
            fi
        done
        
        # 合并日志文件（保留最近7天）
        if [ -d "$project/logs" ]; then
            mkdir -p "$merge_dir/logs"
            find "$project/logs" -name "*.log" -mtime -7 -exec cp {} "$merge_dir/logs/" \; 2>/dev/null || true
        fi
        
        # 删除旧项目目录
        if [ "$project" != "$merge_dir" ]; then
            rm -rf "$project"
            success "清理旧目录: $project"
        fi
    done
    
    success "数据合并完成，备份位置: $backup_dir"
else
    info "未发现现有项目，执行全新安装"
fi

# 4. 下载最新代码
info "📦 下载最新项目代码..."
git clone "$REPO_URL" "$TEMP_DIR" 2>/dev/null || {
    error "代码下载失败，请检查网络连接"
    exit 1
}

# 5. 更新项目文件（保护用户数据）
info "🔄 更新项目文件..."
smart_sync "$TEMP_DIR" "$INSTALL_DIR" \
    "monitor_state.json" \
    "wallets.json" \
    "networks.json" \
    "logs/" \
    "*.log" \
    "__pycache__/" \
    "*.pyc"

# 6. 安装依赖
info "📦 安装Python依赖..."
cd "$INSTALL_DIR"

# 检查并安装必要工具
if ! command -v python3 &> /dev/null; then
    info "安装Python3..."
    sudo apt-get update && sudo apt-get install -y python3 python3-pip
fi

if ! command -v rsync &> /dev/null; then
    info "安装rsync工具..."
    if command -v apt-get &> /dev/null; then
        sudo apt-get update && sudo apt-get install -y rsync
    elif command -v yum &> /dev/null; then
        sudo yum install -y rsync
    elif command -v dnf &> /dev/null; then
        sudo dnf install -y rsync
    else
        warning "无法自动安装rsync，将使用cp命令替代"
    fi
fi

# 安装必需包
packages=("web3>=6.0.0" "colorama" "requests" "websockets")
for package in "${packages[@]}"; do
    pip3 install "$package" --user --break-system-packages 2>/dev/null || pip3 install "$package" --user || true
done

# 7. 设置权限和启动脚本
chmod +x "$INSTALL_DIR/evm_monitor.py"

cat > "$INSTALL_DIR/start.sh" << 'EOF'
#!/bin/bash
cd "$(dirname "$0")"
python3 evm_monitor.py "$@"
EOF
chmod +x "$INSTALL_DIR/start.sh"

# 8. 完成安装
echo
echo -e "${GREEN}🎉 安装完成！${NC}"
echo "=================================================="
success "项目目录: $INSTALL_DIR" 
success "启动命令: cd $INSTALL_DIR && python3 evm_monitor.py"
success "快捷启动: $INSTALL_DIR/start.sh"

if [ ${#existing_projects[@]} -gt 0 ]; then
    echo
    info "📊 智能合并报告:"
    echo "  • 已合并 ${#existing_projects[@]} 个项目的数据"
    echo "  • 监控地址、钱包、RPC设置已保留"
    echo "  • 重复数据已自动去除" 
    echo "  • 原数据备份: $backup_dir"
fi

echo
warning "💡 提示: 现在系统中只有一个统一的项目目录"
info "如有问题，请检查备份目录中的原始数据"
