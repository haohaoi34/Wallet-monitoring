# 🚀 Wallet Monitor - Enterprise Multi-Chain Wallet Monitor

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20macOS%20%7C%20Windows-lightgrey.svg)](https://github.com/haohaoi34/Wallet-monitoring)

> 专业级多链钱包监控系统，支持EVM链和Solana，具备自动转账、智能RPC切换、缓存优化等企业级功能。

## ✨ 主要特性

### 🔐 安全特性
- **私钥加密存储** - 使用Fernet加密算法保护私钥
- **多格式私钥支持** - 自动识别EVM和Solana私钥格式
- **原子性交易** - 防止竞争条件的交易锁机制
- **安全状态保存** - 原子性文件操作和自动备份

### ⛓️ 多链支持
- **EVM链**: Ethereum, BSC, Polygon, Arbitrum, Optimism, Avalanche等
- **Solana**: 主网和测试网完整支持
- **智能RPC管理** - 自动故障转移和负载均衡
- **公共RPC回退** - API限制时自动切换到公共节点

### 🚀 性能优化
- **智能缓存系统** - 减少30-40%重复RPC调用
- **分页代币检测** - 支持大量代币的完整扫描
- **并发处理** - 多线程异步操作
- **错误分类处理** - 智能错误恢复机制

### 📊 监控功能
- **实时余额监控** - 原生代币和ERC-20/SPL代币
- **自动转账** - 达到阈值自动归集到目标地址
- **Telegram通知** - 实时转账和状态通知
- **详细日志** - 完整的操作审计日志

### 🎛️ 管理界面
- **交互式菜单** - 友好的命令行界面
- **实时状态显示** - 彩色状态指示器
- **配置管理** - 在线配置API密钥和参数
- **日志查看** - 内置日志分析工具

## 🛠️ 一键安装

### 一键安装（推荐）

```bash
# 一行命令完成安装
curl -fsSL https://raw.githubusercontent.com/haohaoi34/Wallet-monitoring/main/install.sh | bash
```

**或者下载后运行：**
```bash
curl -fsSL https://raw.githubusercontent.com/haohaoi34/Wallet-monitoring/main/install.sh -o install.sh
chmod +x install.sh
./install.sh
```

**安装脚本自动处理:**
- ✅ 检测操作系统和Python版本
- ✅ 安装Python 3.8+（如需要）
- ✅ 创建虚拟环境
- ✅ 安装所有依赖包
- ✅ 生成配置模板
- ✅ 启动应用程序

### 传统安装方式

```bash
# 下载项目
git clone https://github.com/haohaoi34/Wallet-monitoring.git
cd Wallet-monitoring

# 一键安装并启动
chmod +x setup.sh
./setup.sh
```

**安装脚本自动处理:**
- ✅ 检测操作系统和Python版本
- ✅ 安装Python 3.8+（如需要）
- ✅ 创建虚拟环境
- ✅ 安装所有依赖包
- ✅ 生成配置模板
- ✅ 启动应用程序

### 支持的系统
- **Linux**: Ubuntu, Debian, CentOS, RHEL
- **macOS**: 10.14+ (需要Homebrew)
- **Windows**: WSL或PowerShell

### 手动安装

```bash
# 1. 确保Python 3.8+
python3 --version

# 2. 创建虚拟环境
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate    # Windows

# 3. 安装依赖
pip install -r requirements.txt

# 4. 启动程序
python wallet_monitor.py
```

## ⚙️ 配置说明

### 必须配置项

首次启动后，在应用菜单中配置以下必要信息：

#### API密钥配置
```bash
# EVM链监控需要 (选择其一)
ALCHEMY_API_KEY=your_alchemy_key_here
INFURA_API_KEY=your_infura_key_here

# Solana监控 (可选，有免费RPC)
SOLANA_RPC_URL=https://api.mainnet-beta.solana.com
```

#### 目标地址配置
```bash
# 资金归集目标地址
EVM_TARGET_ADDRESS=0x你的EVM目标地址
SOLANA_TARGET_ADDRESS=你的Solana目标地址
```

### 可选配置项

#### Telegram通知
```bash
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

#### 监控参数
```bash
SLEEP_INTERVAL=30              # 监控间隔(秒)
MIN_BALANCE_THRESHOLD=0.001    # 最小余额阈值
MIN_TRANSACTION_COUNT=0        # 最小交易数阈值
```

## 🚀 使用指南

### 1. 添加钱包地址

支持三种方式添加钱包：

#### 方式一：从私钥生成
```
🔑 选择"添加新地址" -> "从私钥生成"
支持格式：
- EVM: 64位十六进制 (带或不带0x前缀)
- Solana: Base58, Base64, 十六进制, 字节数组
```

#### 方式二：导入现有地址
```
📝 选择"添加新地址" -> "手动输入地址"
直接输入要监控的钱包地址
```

#### 方式三：批量导入
```
📁 选择"批量导入" -> 从文件导入多个地址
支持CSV, TXT格式
```

### 2. 预检查地址

```
🔍 系统自动检查每个地址在各链上的活跃状态：
- 交易历史记录
- 原生代币余额  
- ERC-20/SPL代币余额
```

### 3. 开始监控

```
🚀 选择运行模式：
1. 自动监控 - 后台持续监控
2. 手动检查 - 立即检查一次
3. 配置模式 - 修改监控参数
```

### 4. 实时状态查看

监控界面显示：
- 📊 实时余额信息
- ⛓️ RPC连接状态
- 🔄 缓存命中率
- 📈 性能统计

## 🛡️ 安全最佳实践

### 私钥安全
- ✅ 所有私钥使用Fernet加密存储
- ✅ 内存中私钥及时清理
- ✅ 日志自动过滤敏感信息
- ✅ 状态文件原子性写入

### 网络安全
- ✅ RPC请求使用HTTPS
- ✅ API密钥环境变量存储
- ✅ 智能重试避免频率限制
- ✅ 错误信息脱敏处理

### 运行安全
- ✅ 非root用户运行
- ✅ 虚拟环境隔离
- ✅ 自动备份重要文件
- ✅ 异常自动恢复

## 📁 项目结构

```
Wallet-monitoring/
├── wallet_monitor.py      # 主程序(完整功能)
├── setup.sh              # 一键安装脚本
├── README.md              # 项目说明文档
├── requirements.txt       # Python依赖列表
├── .env.example          # 配置文件模板
├── logs/                 # 日志文件目录
│   ├── wallet_monitor.log
│   ├── error.log
│   └── performance.log
└── data/                 # 数据文件目录
    ├── wallet_state.json
    └── wallet_state.backup
```

## 🔧 高级功能

### 智能RPC管理
```python
# 自动检测最佳RPC节点
# 故障时自动切换备用节点
# API限制时切换公共节点
```

### 性能监控
```python
# 缓存命中率统计
# RPC响应时间监控  
# 错误恢复时间优化
```

### 批量操作
```python
# 多地址并发监控
# 批量代币检测
# 智能交易排队
```

## 📋 支持的代币

### EVM链代币
- **原生代币**: ETH, BNB, MATIC, AVAX等
- **ERC-20代币**: USDT, USDC, DAI, WBTC等
- **自动检测**: 合约地址自动识别

### Solana代币  
- **原生代币**: SOL
- **SPL代币**: 自动扫描所有SPL代币
- **元数据支持**: 自动获取代币符号和精度

## ❓ 常见问题

<details>
<summary><strong>Q: 如何获取API密钥？</strong></summary>

**Alchemy (推荐)**
1. 访问 [alchemy.com](https://alchemy.com)
2. 注册账户并创建应用
3. 复制API密钥到配置中

**Infura**
1. 访问 [infura.io](https://infura.io)
2. 注册账户并创建项目
3. 复制项目ID到配置中
</details>

<details>
<summary><strong>Q: 私钥安全吗？</strong></summary>

✅ **完全安全**
- 使用Fernet对称加密算法
- 密钥使用强密码派生
- 内存中及时清理敏感数据
- 日志自动过滤私钥信息
</details>

<details>
<summary><strong>Q: 支持哪些操作系统？</strong></summary>

✅ **全平台支持**
- Linux: Ubuntu 18.04+, CentOS 7+
- macOS: 10.14+
- Windows: 10+ (推荐WSL)
</details>

<details>
<summary><strong>Q: 如何设置Telegram通知？</strong></summary>

1. 创建Telegram Bot (@BotFather)
2. 获取Bot Token
3. 获取Chat ID (@userinfobot)
4. 在应用配置中填入Token和Chat ID
</details>

<details>
<summary><strong>Q: 监控多少个地址比较合适？</strong></summary>

📊 **建议配置**
- 轻量使用: 10-50个地址
- 中等使用: 50-200个地址  
- 重度使用: 200-1000个地址
- 企业使用: 1000+个地址 (建议部署多实例)
</details>

## 🤝 贡献指南

欢迎贡献代码和建议！

### 提交问题
1. 使用GitHub Issues报告bug
2. 提供详细的错误信息和日志
3. 说明您的运行环境

### 贡献代码
1. Fork本项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启Pull Request

## 📄 许可证

本项目使用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情。

## 🙏 致谢

- [Web3.py](https://github.com/ethereum/web3.py) - Ethereum Python库
- [Solana Python API](https://github.com/michaelhly/solana-py) - Solana Python库
- [Colorama](https://github.com/tartley/colorama) - 跨平台彩色终端输出

## 📞 支持

- 📧 Email: [Your Email]
- 💬 Telegram: [Your Telegram]
- 🐛 Issues: [GitHub Issues](https://github.com/haohaoi34/Wallet-monitoring/issues)

---

<div align="center">

**⭐ 如果这个项目对您有帮助，请给个Star支持一下！⭐**

[🚀 快速开始](#🛠️-一键安装) · [📖 使用指南](#🚀-使用指南) · [❓ 常见问题](#❓-常见问题) · [🤝 贡献代码](#🤝-贡献指南)

</div> 
