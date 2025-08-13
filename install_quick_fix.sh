#!/bin/bash

# 快速修复版本 - 解决rsync缺失问题
# 使用: curl -fsSL https://raw.githubusercontent.com/haohaoi34/Wallet-monitoring/main/install_quick_fix.sh | bash

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

echo -e "${BLUE}🚀 EVM钱包监控软件一键安装程序 (快速修复版)${NC}"
echo "=================================================="

# 1. 先安装必要工具
info "🔧 检查并安装必要工具..."

# 更新包管理器
if command -v apt-get &> /dev/null; then
    sudo apt-get update -qq
elif command -v yum &> /dev/null; then
    sudo yum check-update -q || true
fi

# 安装基础工具
tools_to_install=""
[ ! "$(command -v git)" ] && tools_to_install="$tools_to_install git"
[ ! "$(command -v python3)" ] && tools_to_install="$tools_to_install python3 python3-pip"
[ ! "$(command -v rsync)" ] && tools_to_install="$tools_to_install rsync"
[ ! "$(command -v curl)" ] && tools_to_install="$tools_to_install curl"
[ ! "$(command -v wget)" ] && tools_to_install="$tools_to_install wget"

if [ -n "$tools_to_install" ]; then
    info "安装工具: $tools_to_install"
    if command -v apt-get &> /dev/null; then
        sudo apt-get install -y $tools_to_install
    elif command -v yum &> /dev/null; then
        sudo yum install -y $tools_to_install
    elif command -v dnf &> /dev/null; then
        sudo dnf install -y $tools_to_install
    else
        warning "无法自动安装工具，请手动安装: $tools_to_install"
    fi
    success "工具安装完成"
else
    success "所有必要工具已安装"
fi

# 2. 智能检测现有项目
info "🔍 智能检测现有项目..."
existing_projects=()

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

# 5. 更新项目文件（使用兼容的方式）
info "🔄 更新项目文件..."

# 保护用户数据文件
protected_files=(
    "monitor_state.json"
    "wallets.json" 
    "networks.json"
)

# 备份用户数据
for file in "${protected_files[@]}"; do
    if [ -f "$INSTALL_DIR/$file" ]; then
        cp "$INSTALL_DIR/$file" "$INSTALL_DIR/$file.backup.$$"
    fi
done

# 复制新文件
if command -v rsync &> /dev/null; then
    # 使用rsync（如果可用）
    rsync -av \
        --exclude='monitor_state.json' \
        --exclude='wallets.json' \
        --exclude='networks.json' \
        --exclude='logs/' \
        --exclude='*.log' \
        --exclude='__pycache__/' \
        "$TEMP_DIR/" "$INSTALL_DIR/"
else
    # 使用cp命令
    info "使用cp命令同步文件（rsync不可用）..."
    
    # 创建目标目录
    mkdir -p "$INSTALL_DIR"
    
    # 复制所有文件，但跳过受保护的文件
    find "$TEMP_DIR" -type f | while read -r file; do
        relative_path="${file#$TEMP_DIR/}"
        
        # 检查是否为受保护的文件
        skip_file=false
        for protected in "${protected_files[@]}" "logs/" "*.log" "__pycache__/"; do
            if [[ "$relative_path" == *"$protected"* ]]; then
                skip_file=true
                break
            fi
        done
        
        # 如果不是受保护的文件，则复制
        if [ "$skip_file" = false ]; then
            target_file="$INSTALL_DIR/$relative_path"
            target_dir=$(dirname "$target_file")
            mkdir -p "$target_dir"
            cp "$file" "$target_file"
        fi
    done
    
    # 复制目录结构
    find "$TEMP_DIR" -type d | while read -r dir; do
        relative_path="${dir#$TEMP_DIR/}"
        if [ -n "$relative_path" ] && [[ "$relative_path" != *"__pycache__"* ]] && [[ "$relative_path" != *"logs"* ]]; then
            mkdir -p "$INSTALL_DIR/$relative_path"
        fi
    done
fi

# 恢复用户数据
for file in "${protected_files[@]}"; do
    if [ -f "$INSTALL_DIR/$file.backup.$$" ]; then
        mv "$INSTALL_DIR/$file.backup.$$" "$INSTALL_DIR/$file"
    fi
done

# 6. 安装Python依赖
info "📦 安装Python依赖..."
cd "$INSTALL_DIR"

# 安装必需包
packages=("web3>=6.0.0" "colorama" "requests" "websockets")
for package in "${packages[@]}"; do
    info "安装 $package..."
    pip3 install "$package" --user --break-system-packages 2>/dev/null || \
    pip3 install "$package" --user || \
    python3 -m pip install "$package" --user || true
done

# 7. 设置权限和启动脚本
chmod +x "$INSTALL_DIR/evm_monitor.py" 2>/dev/null || true

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

# 测试启动
echo
info "🧪 测试程序启动..."
cd "$INSTALL_DIR"
if python3 -c "import sys; print('Python版本:', sys.version)"; then
    success "Python环境正常"
else
    warning "Python环境可能有问题"
fi

if python3 -c "import web3, colorama, requests; print('依赖包检查通过')"; then
    success "所有依赖包安装正常"
else
    warning "部分依赖包可能安装失败，可以手动运行程序检查"
fi

echo
success "安装完成！可以运行 $INSTALL_DIR/start.sh 启动程序"
