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



echo -e "${BLUE}🚀 EVM钱包监控软件一键安装程序 v2.1 (自动启动版)${NC}"
echo "=================================================="

# 1. 先安装必要工具（解决rsync缺失问题）
info "🔧 检查并安装必要工具..."

# 更新包管理器
if command -v apt-get &> /dev/null; then
    sudo apt-get update -qq 2>/dev/null || true
elif command -v yum &> /dev/null; then
    sudo yum check-update -q 2>/dev/null || true
fi

# 检查并安装缺失的工具
tools_to_install=""
[ ! "$(command -v git)" ] && tools_to_install="$tools_to_install git"
[ ! "$(command -v python3)" ] && tools_to_install="$tools_to_install python3 python3-pip"
[ ! "$(command -v rsync)" ] && tools_to_install="$tools_to_install rsync"
[ ! "$(command -v curl)" ] && tools_to_install="$tools_to_install curl"

if [ -n "$tools_to_install" ]; then
    info "安装缺失的工具: $tools_to_install"
    if command -v apt-get &> /dev/null; then
        sudo apt-get install -y $tools_to_install 2>/dev/null || warning "部分工具安装失败，将使用替代方案"
    elif command -v yum &> /dev/null; then
        sudo yum install -y $tools_to_install 2>/dev/null || warning "部分工具安装失败，将使用替代方案"
    elif command -v dnf &> /dev/null; then
        sudo dnf install -y $tools_to_install 2>/dev/null || warning "部分工具安装失败，将使用替代方案"
    else
        warning "无法自动安装工具，将使用替代方案"
    fi
    success "工具检查完成"
else
    success "所有必要工具已就绪"
fi

# 2. 清理系统缓存
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

# 保护用户数据文件（但不保护安装脚本）
protected_files=(
    "monitor_state.json"
    "wallets.json" 
    "networks.json"
)

# 备份用户数据
for file in "${protected_files[@]}"; do
    if [ -f "$INSTALL_DIR/$file" ]; then
        cp "$INSTALL_DIR/$file" "$INSTALL_DIR/$file.backup.$$"
        info "备份用户数据: $file"
    fi
done

# 智能文件同步
if command -v rsync &> /dev/null; then
    info "使用rsync同步文件..."
    rsync -av \
        --exclude='monitor_state.json' \
        --exclude='wallets.json' \
        --exclude='networks.json' \
        --exclude='logs/' \
        --exclude='*.log' \
        --exclude='__pycache__/' \
        "$TEMP_DIR/" "$INSTALL_DIR/"
else
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
            cp "$file" "$target_file" 2>/dev/null || true
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
        success "恢复用户数据: $file"
    fi
done

# 6. 安装依赖
info "📦 安装Python依赖..."
cd "$INSTALL_DIR"



# 安装必需包
packages=("web3>=6.0.0" "colorama" "requests" "websockets")
for package in "${packages[@]}"; do
    pip3 install "$package" --user --break-system-packages 2>/dev/null || pip3 install "$package" --user || true
done

# 7. 设置权限和启动脚本
chmod +x "$INSTALL_DIR/evm_monitor.py"

cat > "$INSTALL_DIR/start.sh" << 'EOF'
#!/bin/bash
# EVM监控程序启动脚本

# 切换到程序目录
cd "$(dirname "$0")" || exit 1

# 设置环境变量
export PYTHONIOENCODING=utf-8
export PYTHONUNBUFFERED=1

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}🚀 EVM钱包监控程序启动器${NC}"
echo "=================================="

# 检查Python环境
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ 未找到Python3，请先安装Python3${NC}"
    exit 1
fi

# 检查主程序文件
if [ ! -f "evm_monitor.py" ]; then
    echo -e "${RED}❌ 未找到主程序文件 evm_monitor.py${NC}"
    exit 1
fi

# 检查是否在交互式环境中
if [ -t 0 ] && [ -t 1 ]; then
    echo -e "${GREEN}✅ 检测到交互式环境${NC}"
    echo -e "${YELLOW}💡 提示：使用 Ctrl+C 可随时退出程序${NC}"
    echo ""
    
    # 如果没有参数，强制交互式模式
    if [ $# -eq 0 ]; then
        python3 evm_monitor.py --force-interactive
    else
        python3 evm_monitor.py "$@"
    fi
else
    echo -e "${YELLOW}⚠️  检测到非交互式环境${NC}"
    echo -e "${CYAN}💡 建议使用参数：${NC}"
    echo "   --auto-start     自动开始监控"
    echo "   --daemon         守护进程模式"
    echo "   --force-interactive 强制交互模式"
    echo ""
    
    # 非交互式环境，传递所有参数
    python3 evm_monitor.py "$@"
fi

echo -e "${GREEN}✅ 程序执行完成${NC}"
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

# 测试安装结果
echo
info "🧪 测试安装结果..."
cd "$INSTALL_DIR"

if python3 -c "import sys; print('Python版本:', sys.version.split()[0])" 2>/dev/null; then
    success "Python环境正常"
else
    warning "Python环境可能有问题"
fi

if python3 -c "import web3, colorama, requests; print('关键依赖包检查通过')" 2>/dev/null; then
    success "依赖包安装正常"
else
    warning "部分依赖包可能缺失，建议手动检查"
    info "可以运行: pip3 install web3 colorama requests websockets --user"
fi

if [ -f "$INSTALL_DIR/evm_monitor.py" ] && [ -x "$INSTALL_DIR/evm_monitor.py" ]; then
    success "主程序文件正常"
else
    warning "主程序文件权限异常"
fi

echo
success "🎉 安装测试完成！正在自动启动程序..."

# 简短倒计时
echo -e "${YELLOW}⏰ 2秒后自动启动...${NC}"
sleep 2

echo -e "${GREEN}🚀 正在启动EVM钱包监控程序...${NC}"
echo "=================================================="

# 确保在正确目录
cd "$INSTALL_DIR" || exit 1

# 清除环境变量干扰
unset PYTHONPATH 2>/dev/null || true
export PYTHONIOENCODING=utf-8

# 创建Python启动器 - 最可靠的方法
cat > "$INSTALL_DIR/launcher.py" << 'LAUNCHER_EOF'
#!/usr/bin/env python3
import os, sys, subprocess

# 设置工作目录
os.chdir(os.path.expanduser("~/evm_monitor"))
sys.path.insert(0, os.getcwd())

# 设置环境变量
os.environ['PYTHONIOENCODING'] = 'utf-8'
os.environ['PYTHONUNBUFFERED'] = '1'

print("🚀 启动 EVM 钱包监控程序...")
print("=" * 50)

try:
    # 使用subprocess启动，避免exec的问题
    result = subprocess.run([sys.executable, 'evm_monitor.py', '--force-interactive'])
    sys.exit(result.returncode)
except KeyboardInterrupt:
    print("\n👋 程序被用户中断")
    sys.exit(0)
except Exception as e:
    print(f"❌ 启动失败: {e}")
    print("💡 尝试直接执行...")
    # 后备方案：直接exec
    exec(open('evm_monitor.py').read())
LAUNCHER_EOF

# 启动程序
echo "🔄 程序安装完成，准备启动..."

# 检查是否在交互式环境中
if [ -t 0 ] && [ -t 1 ]; then
    # 交互式环境（终端）
    echo "📋 检测到交互式环境"
    echo ""
    echo "🚀 启动选项："
    echo "1. 立即启动交互式程序 (推荐)"
    echo "2. 仅显示启动命令"
    echo ""
    
    # 提供用户选择
    read -p "请选择 [1-2，默认1]: " start_choice
    start_choice=${start_choice:-1}
    
    if [ "$start_choice" = "1" ]; then
        echo ""
        echo "🚀 正在启动EVM钱包监控程序..."
        echo "💡 提示：程序启动后可以使用 Ctrl+C 随时退出"
        echo "=================================================="
        sleep 1
        
        # 启动程序，不使用exec以避免替换shell
        cd "$INSTALL_DIR"
        python3 launcher.py
        
        echo ""
        success "程序运行结束"
    else
        echo ""
        echo "📝 手动启动命令："
        echo "   cd $INSTALL_DIR"
        echo "   python3 evm_monitor.py"
        echo ""
        success "安装完成！"
    fi
else
    # 非交互式环境（脚本、SSH等）
    echo "📋 检测到非交互式环境，将自动启动程序"
    echo ""
    echo "🚀 正在启动EVM钱包监控程序..."
    echo "💡 提示：程序将以强制交互模式启动，支持菜单操作"
    echo "=================================================="
    sleep 1
    
    # 切换到程序目录
    cd "$INSTALL_DIR" || exit 1
    
    # 设置环境变量以支持交互式操作
    export PYTHONIOENCODING=utf-8
    export PYTHONUNBUFFERED=1
    export FORCE_COLOR=1
    
    # 启动程序，强制交互模式
    echo "🔄 正在加载程序，请稍候..."
    
    # 直接启动程序
    python3 launcher.py
    
    echo ""
    success "程序运行结束"
    echo ""
    echo "📝 如需重新启动："
    echo "   cd $INSTALL_DIR && python3 evm_monitor.py"
    echo "   或使用: $INSTALL_DIR/start.sh"
fi
