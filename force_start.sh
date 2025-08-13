#!/bin/bash

# 强制启动脚本 - 100%确保能进入程序菜单
# 这个脚本会在安装完成后自动执行

set -e

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

INSTALL_DIR="$HOME/evm_monitor"

echo -e "${GREEN}🚀 强制启动 EVM 钱包监控程序...${NC}"
echo "=================================================="

# 确保在正确目录
cd "$INSTALL_DIR" 2>/dev/null || {
    echo "错误：无法进入目录 $INSTALL_DIR"
    exit 1
}

# 检查文件
if [ ! -f "evm_monitor.py" ]; then
    echo "错误：找不到主程序文件"
    exit 1
fi

echo -e "${CYAN}🎯 正在启动程序...${NC}"

# 清除所有可能的环境变量干扰
unset PYTHONPATH
export PYTHONIOENCODING=utf-8

# 强制启动方法1: 直接替换shell进程
exec python3 -u evm_monitor.py 2>&1

# 如果上面失败，下面的代码永远不会执行，但作为备份
python3 -u evm_monitor.py
exit 0
