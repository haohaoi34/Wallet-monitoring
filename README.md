# 🚀 EVM钱包监控软件 - 智能安装系统

## 🎯 智能合并特性

新版安装脚本具备智能检测和数据合并功能，解决多次安装导致项目目录混乱的问题。

### ✨ 核心功能

#### 🔍 智能检测
- 自动扫描所有可能的项目位置
- 识别包含 `evm_monitor.py` 的目录
- 支持多种命名方式的项目文件夹

#### 📦 数据合并
- **监控地址**: 合并所有钱包地址，无重复
- **RPC设置**: 保留所有自定义RPC和屏蔽列表
- **用户配置**: 合并代币设置和个人偏好
- **日志文件**: 保留最近7天的运行日志

#### 🛡️ 安全备份
- 安装前自动备份所有现有数据
- 时间戳标记，便于数据恢复
- 完整保留原始项目结构

## 🚀 使用方法

### 一键安装（推荐）
```bash
curl -fsSL https://raw.githubusercontent.com/haohaoi34/Wallet-monitoring/main/install.sh | bash
```

### 手动下载安装
```bash
wget https://raw.githubusercontent.com/haohaoi34/Wallet-monitoring/main/install.sh
chmod +x install.sh
./install.sh
```

## 🔄 智能安装流程

```
🚀 EVM钱包监控软件一键安装程序
==================================================
🧹 清理系统缓存...
🔍 智能检测现有项目...
找到项目: /home/user/evm_monitor
找到项目: /home/user/Wallet-monitoring
⚠️ 检测到 2 个现有项目，开始智能合并...
📦 备份并合并: /home/user/evm_monitor
✅ 合并完成: monitor_state.json
✅ 合并完成: wallets.json
✅ 清理旧目录: /home/user/evm_monitor
📦 备份并合并: /home/user/Wallet-monitoring
✅ 清理旧目录: /home/user/Wallet-monitoring
✅ 数据合并完成，备份位置: /home/user/.evm_monitor_backup_20241201_143022
📦 下载最新项目代码...
🔄 更新项目文件...
📦 安装Python依赖...
🎉 安装完成！
==================================================
✅ 项目目录: /home/user/evm_monitor
✅ 启动命令: cd /home/user/evm_monitor && python3 evm_monitor.py
✅ 快捷启动: /home/user/evm_monitor/start.sh

📊 智能合并报告:
  • 已合并 2 个项目的数据
  • 监控地址、钱包、RPC设置已保留
  • 重复数据已自动去除
  • 原数据备份: /home/user/.evm_monitor_backup_20241201_143022

💡 提示: 现在系统中只有一个统一的项目目录
```

## 📊 数据合并策略

### 🎯 监控状态文件 (`monitor_state.json`)
```json
{
  "monitored_addresses": {
    // 合并所有项目的监控地址，保持唯一性
  },
  "blocked_rpcs": {
    // 合并所有屏蔽的RPC，避免重复测试失效节点
  },
  "user_added_tokens": [
    // 合并用户添加的代币，自动去重
  ],
  "rpc_test_cache": {
    // 合并RPC测试缓存，提高检测效率
  }
}
```

### 💰 钱包文件 (`wallets.json`)
```json
{
  // 合并所有钱包配置
  // 保留助记词、私钥等敏感信息
  // 去重处理，避免重复钱包
}
```

### 🌐 网络配置 (`networks.json`)
```json
{
  // 保留最新的网络配置
  // 合并用户自定义的RPC节点
  // 保持网络兼容性
}
```

## 🛡️ 安全保障

### ✅ 数据保护
- **完整备份**: 安装前备份所有现有数据
- **增量合并**: 只添加新数据，不覆盖现有配置
- **版本控制**: 保留多个备份版本

### 🔐 隐私安全
- **本地处理**: 所有数据合并在本地完成
- **权限控制**: 严格的文件权限设置
- **敏感信息**: 钱包私钥等信息完全保留

### 🚨 错误恢复
```bash
# 如果安装出现问题，可以从备份恢复
backup_dir="/home/user/.evm_monitor_backup_YYYYMMDD_HHMMSS"
cp -r "$backup_dir/evm_monitor" "$HOME/"
```

## 🎛️ 高级选项

### 🔧 自定义安装路径
```bash
# 设置自定义安装目录
export INSTALL_DIR="/opt/evm_monitor"
./install.sh
```

### 📋 查看安装日志
```bash
# 安装时保存日志
./install.sh 2>&1 | tee install.log
```

### 🗂️ 手动数据迁移
```bash
# 如需手动迁移特定数据
python3 -c "
import json
import sys

# 合并两个JSON文件
def merge_json(src_file, dst_file):
    with open(src_file) as f: src = json.load(f)
    with open(dst_file) as f: dst = json.load(f)
    
    if isinstance(src, dict) and isinstance(dst, dict):
        dst.update(src)
    
    with open(dst_file, 'w') as f:
        json.dump(dst, f, indent=2, ensure_ascii=False)

merge_json(sys.argv[1], sys.argv[2])
" source.json target.json
```

## 🚀 快速启动

安装完成后，使用以下任一方式启动：

```bash
# 方式1: 直接启动
cd ~/evm_monitor && python3 evm_monitor.py

# 方式2: 使用启动脚本
~/evm_monitor/start.sh

# 方式3: 后台运行
nohup ~/evm_monitor/start.sh &
```

## 🆘 常见问题

### ❓ 多个项目目录怎么办？
答：新版安装脚本会自动检测并合并所有项目，最终只保留一个统一目录。

### ❓ 数据会丢失吗？
答：不会。所有数据都会完整备份并智能合并，确保零数据丢失。

### ❓ 如何回滚到之前版本？
答：使用备份目录中的数据即可完全恢复到安装前状态。

### ❓ 网络问题无法下载？
答：可以手动下载安装脚本，或使用代理：
```bash
# 使用代理
export https_proxy=http://proxy:port
curl -fsSL https://raw.githubusercontent.com/haohaoi34/Wallet-monitoring/main/install.sh | bash
```

## 📞 技术支持

如遇到任何安装问题，请检查：
1. 网络连接是否正常
2. Python3 和 git 是否已安装
3. 磁盘空间是否充足
4. 备份目录中的原始数据是否完整

---

💡 **提示**: 新的智能安装系统确保您的所有数据和配置都能完美保留，同时享受最新功能！
