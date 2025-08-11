import asyncio
import logging
import os
import json
import base64
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
    # 定义空的类以避免导入错误
    class Web3:
        def __init__(self, *args, **kwargs):
            pass
        
        @staticmethod
        def from_wei(value, unit='ether'):
            """模拟from_wei方法"""
            if unit == 'ether':
                return float(value) / 1e18
            return float(value)
        
        @staticmethod
        def to_wei(value, unit='ether'):
            """模拟to_wei方法"""
            if unit == 'ether':
                return int(float(value) * 1e18)
            return int(value)
        
        @staticmethod
        def is_address(address):
            """模拟is_address方法"""
            if not isinstance(address, str):
                return False
            # 简单的EVM地址格式检查
            return (address.startswith('0x') and 
                    len(address) == 42 and 
                    all(c in '0123456789abcdefABCDEF' for c in address[2:]))
    
    class HTTPProvider:
        def __init__(self, *args, **kwargs):
            pass

# eth_account导入
try:
    from eth_account import Account
    ETH_ACCOUNT_AVAILABLE = True
    print("✅ eth_account库已加载")
except ImportError as e:
    ETH_ACCOUNT_AVAILABLE = False
    print(f"⚠️  eth_account库导入失败: {str(e)}")
    print("📦 请运行: pip install eth-account")
    # 定义空的类以避免导入错误
    class Account:
        def __init__(self, *args, **kwargs):
            pass
        
        @staticmethod
        def from_key(private_key):
            """模拟from_key方法"""
            class MockAccount:
                def __init__(self):
                    self.address = "0x0000000000000000000000000000000000000000"
            return MockAccount()
# Alchemy导入 - 使用正确的包
try:
    from alchemy import Alchemy, Network
    ALCHEMY_AVAILABLE = True
    print("✅ Alchemy SDK已加载")
except ImportError:
    try:
        # 尝试使用alchemy-sdk包
        from alchemy_sdk import Alchemy, Network
        ALCHEMY_AVAILABLE = True
        print("✅ Alchemy SDK (alchemy-sdk)已加载")
    except ImportError:
        ALCHEMY_AVAILABLE = False
        print("⚠️  Alchemy SDK不可用，EVM全链查询功能将受限")
        print("📦 请运行: pip install alchemy")
        # 定义空的类以避免导入错误
        class Alchemy:
            def __init__(self, *args, **kwargs):
                pass
        class Network:
            # 定义常用的网络常量
            ETH_MAINNET = "eth-mainnet"
            ETH_GOERLI = "eth-goerli"
            MATIC_MAINNET = "polygon-mainnet"
            ARB_MAINNET = "arbitrum-one"
            OPT_MAINNET = "optimism-mainnet"
            BASE_MAINNET = "base-mainnet"
            MATIC_MUMBAI = "polygon-mumbai"
            ARB_GOERLI = "arb-goerli"
            OPT_GOERLI = "opt-goerli"
import aiohttp
try:
    from telegram import Bot
    TELEGRAM_AVAILABLE = True
    print("✅ Telegram库已加载")
except ImportError:
    TELEGRAM_AVAILABLE = False
    print("⚠️  Telegram库不可用，通知功能将被禁用")
    print("📦 请运行: pip install python-telegram-bot")
    # 定义空的类以避免导入错误
    class Bot:
        def __init__(self, *args, **kwargs):
            pass

from logging.handlers import RotatingFileHandler
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import threading

# Solana相关导入
try:
    # 尝试导入Solana核心模块
    from solana.rpc.async_api import AsyncClient
    from solana.keypair import Keypair
    from solana.publickey import PublicKey
    from solana.rpc.commitment import Commitment
    from solana.transaction import Transaction
    from solana.system_program import TransferParams, transfer
    from solana.rpc.types import TxOpts
    SOLANA_AVAILABLE = True
    print("✅ Solana基本功能已加载")
    
    # 尝试导入SPL Token功能
    try:
        from spl.token.client import Token
        from spl.token.constants import TOKEN_PROGRAM_ID
        SPL_TOKEN_AVAILABLE = True
        print("✅ SPL Token功能已加载")
    except ImportError:
        SPL_TOKEN_AVAILABLE = False
        print("⚠️ SPL Token功能未加载")
    
    # 尝试导入SPL Token高级功能
    if SPL_TOKEN_AVAILABLE:
        try:
            from solders.pubkey import Pubkey as SoldersPubkey
            from spl.token.instructions import transfer_checked, TransferCheckedParams
            from solana.rpc.types import TokenAccountOpts
            print("✅ SPL Token高级功能已加载")
        except ImportError:
            print("💡 SPL Token高级功能不可用，但基本功能正常")
        
except ImportError as e:
    SOLANA_AVAILABLE = False
    SPL_TOKEN_AVAILABLE = False
    print(f"⚠️  Solana支持未完全安装: {str(e)}")
    print("📦 请运行以下命令安装Solana支持:")
    print("   pip install solana")
    print("   pip install base58")
    print("   或者运行: pip install -r requirements.txt")
    
    # 定义空的类以避免导入错误
    class AsyncClient:
        def __init__(self, *args, **kwargs):
            pass
    class Keypair:
        def __init__(self, *args, **kwargs):
            pass
    class PublicKey:
        def __init__(self, *args, **kwargs):
            pass
    class Commitment:
        pass
    class Transaction:
        def __init__(self, *args, **kwargs):
            pass
    class TransferParams:
        pass
    def transfer(*args, **kwargs):
        pass
    class TxOpts:
        pass

# 检查colorama依赖（用于彩色输出）
try:
    from colorama import init, Fore, Back, Style
    COLORAMA_AVAILABLE = True
except ImportError:
    COLORAMA_AVAILABLE = False
    print("⚠️  colorama库未安装，将使用普通输出")
    print("📦 请运行: pip install colorama")
    # 定义空的颜色常量
    class MockColor:
        def __getattr__(self, name): return ""
    Fore = Back = Style = MockColor()

# 检查base58依赖（用于Solana私钥处理）
try:
    import base58
    BASE58_AVAILABLE = True
except ImportError:
    BASE58_AVAILABLE = False
    if SOLANA_AVAILABLE:
        print("⚠️  base58库未安装，Solana私钥处理可能受限")
        print("📦 请运行: pip install base58")

# 配置
class Config:
    def __init__(self):
        # API配置
        self.ALCHEMY_API_KEY = "S0hs4qoXIR1SMD8P7I6Wt"
        
        # 转账目标地址（分别配置EVM和Solana）
        self.EVM_TARGET_ADDRESS = "0x6b219df8c31c6b39a1a9b88446e0199be8f63cf1"
        self.SOLANA_TARGET_ADDRESS = "B39mmDg6MM9itBHJeNm2GPcQeNckFYMaW3HUUu5SmDuk"
        
        # Solana配置
        self.SOLANA_RPC_ENDPOINTS = [
            "https://api.mainnet-beta.solana.com",
            "https://solana-api.projectserum.com",
            "https://rpc.ankr.com/solana",
            "https://solana.public-rpc.com"
        ]
        self.SOLANA_DEVNET_RPC = "https://api.devnet.solana.com"
        self.SOLANA_TESTNET_RPC = "https://api.devnet.solana.com"
        
        # 监控配置
        try:
            self.MIN_BALANCE_WEI = Web3.to_wei(0.0001, 'ether')
        except:
            self.MIN_BALANCE_WEI = int(0.0001 * 1e18)  # 备用计算
        self.MIN_TOKEN_BALANCE = 0.0001
        self.MIN_SOL_BALANCE = 0.001  # Solana最小余额（SOL）
        self.SLEEP_INTERVAL = 30
        self.NUM_THREADS = 10
        
        # 文件配置
        self.STATE_FILE = "wallet_state.json"
        self.LOG_FILE = "wallet_monitor.log"
        self.MAX_LOG_SIZE = 500 * 1024 * 1024  # 500MB
        self.LOG_BACKUP_COUNT = 1  # 只保留1个备份文件，超过大小限制时覆盖
        
        # 加密配置
        self.ENCRYPTION_PASSWORD = "wallet_monitor_secure_password_2024"
        
        # 代币查询配置
        self.ENABLE_FULL_CHAIN_TOKEN_DISCOVERY = True  # 启用EVM全链代币自动发现
        self.ENABLE_SOLANA_TOKEN_DISCOVERY = True  # 启用Solana全链代币自动发现
        self.ENABLE_MANUAL_TOKEN_CHECK = True  # 启用手动配置代币检查（备用方案）
        self.MAX_TOKENS_PER_CHAIN = 100  # 每个链最多查询的代币数量
        self.MAX_SOLANA_TOKENS = 200  # Solana最多查询的代币数量
        
        # RPC切换配置
        self.ALCHEMY_ERROR_THRESHOLD = 5  # Alchemy连续错误次数阈值
        self.ALCHEMY_SWITCH_DURATION = 5 * 60 * 60  # 切换到公共RPC的持续时间（5小时）
        self.USE_PUBLIC_RPC = False  # 是否使用公共RPC
        self.ALCHEMY_ERROR_COUNT = 0  # Alchemy错误计数
        self.LAST_ALCHEMY_SWITCH_TIME = 0  # 上次Alchemy切换时间
        
        # 地址预检查配置
        self.ENABLE_ADDRESS_PRE_CHECK = True  # 启用地址预检查
        self.MIN_TRANSACTION_COUNT = 1  # 最小交易记录数量
        self.MIN_BALANCE_THRESHOLD = 0  # 最小余额阈值
        
        # Telegram配置（可选）
        self.TELEGRAM_BOT_TOKEN = None  # 可以设置为None
        self.TELEGRAM_CHAT_ID = None    # 可以设置为None
        
        # 控制菜单配置
        self.ENABLE_CONTROL_MENU = True  # 启用控制菜单
        self.MENU_REFRESH_INTERVAL = 60  # 菜单刷新间隔（秒）
        
        # 验证地址格式
        self._validate_addresses()
    
    def _validate_addresses(self):
        """验证目标地址格式"""
        try:
            # 验证EVM地址
            if not Web3.is_address(self.EVM_TARGET_ADDRESS):
                print(f"⚠️ 无效的EVM目标地址: {self.EVM_TARGET_ADDRESS}")
                print("🔧 请检查配置文件中的EVM_TARGET_ADDRESS设置")
                return False
            
            # 验证Solana地址（安全检查）
            try:
                if SOLANA_AVAILABLE:
                    from solana.publickey import PublicKey
                    PublicKey(self.SOLANA_TARGET_ADDRESS)
                    print(f"✅ 地址验证通过")
                else:
                    print(f"⚠️ Solana库未安装，跳过Solana地址验证")
            except Exception as e:
                print(f"⚠️ Solana地址验证失败: {self.SOLANA_TARGET_ADDRESS}")
                print(f"🔧 错误: {str(e)}")
                return False
            
            return True
            
        except Exception as e:
            print(f"❌ 地址验证过程出错: {str(e)}")
            return False

config = Config()

# 增强的日志系统
class EnhancedRotatingFileHandler(RotatingFileHandler):
    """增强的日志轮换处理器，支持时间和大小双重轮换"""
    
    def __init__(self, filename, mode='a', maxBytes=0, backupCount=0, 
                 encoding=None, delay=False, rotate_time_hours=24):
        super().__init__(filename, mode, maxBytes, backupCount, encoding, delay)
        self.rotate_time_hours = rotate_time_hours
        self.last_rotate_time = time.time()
        
    def shouldRollover(self, record):
        """检查是否应该轮换日志"""
        # 检查大小限制
        if super().shouldRollover(record):
            return True
            
        # 检查时间限制
        current_time = time.time()
        if current_time - self.last_rotate_time >= (self.rotate_time_hours * 3600):
            self.last_rotate_time = current_time
            return True
            
        return False

class SensitiveLogFilter(logging.Filter):
    """敏感信息过滤器"""
    
    def filter(self, record):
        """过滤日志中的敏感信息"""
        try:
            if hasattr(record, 'msg') and isinstance(record.msg, str):
                record.msg = self._filter_sensitive_info(record.msg)
            
            # 过滤args中的敏感信息
            if hasattr(record, 'args') and record.args:
                filtered_args = []
                for arg in record.args:
                    if isinstance(arg, str):
                        filtered_args.append(self._filter_sensitive_info(arg))
                    else:
                        filtered_args.append(arg)
                record.args = tuple(filtered_args)
        except Exception:
            # 如果过滤失败，返回原始记录
            pass
        
        return True
    
    def _filter_sensitive_info(self, text: str) -> str:
        """过滤敏感信息的本地实现"""
        if not isinstance(text, str):
            return text
            
        # 过滤EVM私钥模式 (64位十六进制字符)
        text = re.sub(r'\b[0-9a-fA-F]{64}\b', '[PRIVATE_KEY_FILTERED]', text)
        
        # 过滤Solana私钥模式 (Base58编码，通常44-88字符)
        text = re.sub(r'\b[1-9A-HJ-NP-Za-km-z]{44,88}\b', '[SOLANA_KEY_FILTERED]', text)
        
        # 过滤助记词模式 (12-24个英文单词)
        text = re.sub(r'\b(?:[a-z]+\s+){11,23}[a-z]+\b', '[MNEMONIC_FILTERED]', text, flags=re.IGNORECASE)
        
        # 过滤可能的API密钥
        text = re.sub(r'\b[A-Za-z0-9]{32,}\b', lambda m: '[API_KEY_FILTERED]' if len(m.group()) > 40 else m.group(), text)
        
        return text

# 日志配置
def setup_logging():
    """设置增强的日志记录系统"""
    if COLORAMA_AVAILABLE:
        init(autoreset=True)  # 初始化colorama
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    
    # 如果已经有handler，清理后重新设置
    if logger.handlers:
        logger.handlers.clear()
    
    # 创建带颜色的格式化器
    class ColorFormatter(logging.Formatter):
        FORMATS = {
            logging.INFO: Fore.GREEN + "%(asctime)s " + Style.BRIGHT + "✅ [%(levelname)s]" + Style.RESET_ALL + " %(message)s",
            logging.WARNING: Fore.YELLOW + "%(asctime)s " + Style.BRIGHT + "⚠️ [%(levelname)s]" + Style.RESET_ALL + " %(message)s",
            logging.ERROR: Fore.RED + "%(asctime)s " + Style.BRIGHT + "❌ [%(levelname)s]" + Style.RESET_ALL + " %(message)s",
            logging.DEBUG: Fore.CYAN + "%(asctime)s [%(levelname)s] %(message)s" + Style.RESET_ALL
        }

        def format(self, record):
            log_fmt = self.FORMATS.get(record.levelno, self.FORMATS[logging.DEBUG])
            formatter = logging.Formatter(log_fmt, datefmt='%Y-%m-%d %H:%M:%S')
            return formatter.format(record)
    
    # 敏感信息过滤器
    sensitive_filter = SensitiveLogFilter()
    
    # 控制台处理器（彩色输出）
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(ColorFormatter())
    console_handler.addFilter(sensitive_filter)
    
    # 增强的主日志文件处理器
    main_file_handler = EnhancedRotatingFileHandler(
        config.LOG_FILE, 
        maxBytes=config.MAX_LOG_SIZE,
        backupCount=config.LOG_BACKUP_COUNT,
        rotate_time_hours=24
    )
    main_file_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
    ))
    main_file_handler.addFilter(sensitive_filter)
    
    # 错误专用日志处理器
    error_file_handler = EnhancedRotatingFileHandler(
        'wallet_monitor_errors.log',
        maxBytes=50*1024*1024,  # 50MB
        backupCount=3,
        rotate_time_hours=168  # 一周
    )
    error_file_handler.setLevel(logging.ERROR)
    error_file_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s\nFile: %(pathname)s'
    ))
    error_file_handler.addFilter(sensitive_filter)
    
    # 性能监控日志处理器
    class PerformanceFilter(logging.Filter):
        def filter(self, record):
            message = record.getMessage().lower()
            return any(keyword in message for keyword in ['performance', 'cache', 'rpc', 'response_time'])
    
    performance_file_handler = EnhancedRotatingFileHandler(
        'wallet_monitor_performance.log',
        maxBytes=20*1024*1024,  # 20MB
        backupCount=2,
        rotate_time_hours=72  # 三天
    )
    performance_file_handler.addFilter(PerformanceFilter())
    performance_file_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(message)s'
    ))
    
    # 添加处理器
    logger.addHandler(console_handler)
    logger.addHandler(main_file_handler)
    logger.addHandler(error_file_handler)
    logger.addHandler(performance_file_handler)
    
    return logger

logger = setup_logging()

# 加密工具
def generate_fernet_key(password: str) -> Fernet:
    salt = b'wallet_monitor_salt_2024'
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100000)
    key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
    return Fernet(key)

cipher = generate_fernet_key(config.ENCRYPTION_PASSWORD)

def identify_private_key_type(private_key: str) -> str:
    """
    自动识别私钥类型 - 增强版本，修复识别逻辑缺陷
    返回: 'evm' 或 'solana'
    """
    try:
        # 移除0x前缀
        cleaned_key = private_key[2:] if private_key.startswith("0x") else private_key
        
        # 首先尝试识别为Solana私钥（优先级更高，避免误判）
        # 1. 检查base58格式的Solana私钥
        if len(cleaned_key) >= 87 and len(cleaned_key) <= 88:
            try:
                import base58
                decoded = base58.b58decode(cleaned_key)
                if len(decoded) == 64:
                    # 进一步验证是否为有效的Solana私钥
                    if SOLANA_AVAILABLE:
                        from solana.keypair import Keypair
                        Keypair.from_secret_key(decoded)
                        return "solana"
                    else:
                        return "solana"  # 无法验证但格式正确
            except Exception:
                pass
        
        # 2. 检查base64格式的Solana私钥
        try:
            import base64
            decoded = base64.b64decode(cleaned_key)
            if len(decoded) == 64:
                # 进一步验证是否为有效的Solana私钥
                if SOLANA_AVAILABLE:
                    from solana.keypair import Keypair
                    Keypair.from_secret_key(decoded)
                    return "solana"
                else:
                    return "solana"  # 无法验证但格式正确
        except Exception:
            pass
        
        # 3. 检查64字符十六进制格式（可能是EVM或Solana）
        if len(cleaned_key) == 64 and all(c in "0123456789abcdefABCDEF" for c in cleaned_key):
            # 优先尝试作为EVM私钥验证
            try:
                if ETH_ACCOUNT_AVAILABLE:
                    from eth_account import Account
                    Account.from_key(cleaned_key)
                else:
                    # 使用已定义的Mock Account类
                    Account.from_key(cleaned_key)
                
                # 如果EVM验证成功，再检查是否也是有效的Solana私钥
                if SOLANA_AVAILABLE:
                    try:
                        from solana.keypair import Keypair
                        key_bytes = bytes.fromhex(cleaned_key)
                        Keypair.from_secret_key(key_bytes)
                        # 如果两者都有效，根据前缀判断用户意图
                        if private_key.startswith("0x"):
                            return "evm"  # 有0x前缀，用户可能倾向于EVM
                        else:
                            # 无前缀时，需要额外判断逻辑
                            # 可以添加用户选择或其他判断逻辑
                            logger.warning(f"私钥同时适用于EVM和Solana，默认识别为EVM")
                            return "evm"
                    except Exception:
                        pass  # Solana验证失败，确定是EVM
                
                return "evm"
            except Exception:
                # EVM验证失败，尝试作为Solana十六进制私钥
                if SOLANA_AVAILABLE:
                    try:
                        from solana.keypair import Keypair
                        key_bytes = bytes.fromhex(cleaned_key)
                        if len(key_bytes) == 64:
                            Keypair.from_secret_key(key_bytes)
                            return "solana"
                    except Exception:
                        pass
        
        # 4. 检查其他可能的Solana格式（字节数组的字符串表示等）
        if '[' in cleaned_key and ']' in cleaned_key:
            try:
                # 可能是字节数组的字符串表示，如 "[1,2,3,...]"
                import json
                byte_array = json.loads(cleaned_key)
                if isinstance(byte_array, list) and len(byte_array) == 64:
                    key_bytes = bytes(byte_array)
                    if SOLANA_AVAILABLE:
                        from solana.keypair import Keypair
                        Keypair.from_secret_key(key_bytes)
                        return "solana"
            except Exception:
                pass
        
        logger.warning(f"无法识别私钥类型，私钥长度: {len(cleaned_key)}")
        return "unknown"
        
    except Exception as e:
        logger.error(f"私钥类型识别失败: {str(e)}")
        return "unknown"

def generate_solana_address_from_private_key(private_key: str) -> str:
    """从Solana私钥生成地址 - 增强版本，修复十六进制验证漏洞"""
    try:
        if not SOLANA_AVAILABLE:
            raise ImportError("Solana库未安装")
        
        # 移除可能的0x前缀
        cleaned_key = private_key[2:] if private_key.startswith("0x") else private_key
        key_bytes = None
        
        # 处理不同格式的私钥
        if len(cleaned_key) == 64:
            # 64字符十六进制格式 - 添加严格验证
            if not all(c in "0123456789abcdefABCDEF" for c in cleaned_key):
                raise ValueError(f"无效的十六进制字符串: 包含非十六进制字符")
            
            try:
                key_bytes = bytes.fromhex(cleaned_key)
            except ValueError as e:
                raise ValueError(f"十六进制解码失败: {str(e)}")
                
        elif len(cleaned_key) >= 87 and len(cleaned_key) <= 88:
            # base58格式
            try:
                import base58
                key_bytes = base58.b58decode(cleaned_key)
            except Exception as e:
                raise ValueError(f"Base58解码失败: {str(e)}")
                
        elif len(cleaned_key) > 64:
            # 可能是base64格式
            try:
                import base64
                key_bytes = base64.b64decode(cleaned_key)
            except Exception as e:
                raise ValueError(f"Base64解码失败: {str(e)}")
                
        elif '[' in cleaned_key and ']' in cleaned_key:
            # 字节数组格式，如 "[1,2,3,...]"
            try:
                import json
                byte_array = json.loads(cleaned_key)
                if not isinstance(byte_array, list):
                    raise ValueError("字节数组格式不正确")
                if not all(isinstance(b, int) and 0 <= b <= 255 for b in byte_array):
                    raise ValueError("字节数组包含无效值")
                key_bytes = bytes(byte_array)
            except json.JSONDecodeError as e:
                raise ValueError(f"JSON解析失败: {str(e)}")
            except Exception as e:
                raise ValueError(f"字节数组处理失败: {str(e)}")
        else:
            raise ValueError(f"不支持的私钥格式，长度: {len(cleaned_key)}")
        
        # 验证密钥长度
        if key_bytes is None:
            raise ValueError("私钥解析失败")
        
        if len(key_bytes) != 64:
            raise ValueError(f"私钥长度不正确: 期望64字节，实际{len(key_bytes)}字节")
        
        # 创建Keypair并生成地址
        try:
            from solana.keypair import Keypair
            keypair = Keypair.from_secret_key(key_bytes)
            address = str(keypair.public_key)
            
            # 验证生成的地址格式
            if not address or len(address) < 32:
                raise ValueError("生成的地址格式不正确")
                
            logger.debug(f"成功生成Solana地址: {address}")
            return address
            
        except Exception as e:
            raise ValueError(f"Keypair创建失败: {str(e)}")
            
    except Exception as e:
        logger.error(f"生成Solana地址失败: {str(e)}")
        return None

def is_solana_address(address: str) -> bool:
    """检查是否为Solana地址"""
    try:
        if SOLANA_AVAILABLE:
            PublicKey(address)
            return True
        else:
            # 简单检查：Solana地址通常是base58编码，长度约44字符
            return len(address) >= 32 and len(address) <= 44
    except:
        return False

def is_evm_address(address: str) -> bool:
    """检查是否为EVM地址"""
    try:
        return Web3.is_address(address)
    except:
        return False

# EVM链配置
ALCHEMY_CHAINS = [
    # ===== 主网 =====
    # 主要链
    {"name": "Ethereum", "network": Network.ETH_MAINNET, "rpc_url": f"https://eth-mainnet.g.alchemy.com/v2/{config.ALCHEMY_API_KEY}", "chain_id": 1, "native_token": "ETH", "public_rpc": "https://eth.llamarpc.com", "backup_rpcs": ["https://rpc.ankr.com/eth", "https://ethereum.publicnode.com", "https://1rpc.io/eth"]},
    {"name": "Polygon PoS", "network": Network.MATIC_MAINNET, "rpc_url": f"https://polygon-mainnet.g.alchemy.com/v2/{config.ALCHEMY_API_KEY}", "chain_id": 137, "native_token": "MATIC", "public_rpc": "https://polygon-rpc.com", "backup_rpcs": ["https://rpc.ankr.com/polygon", "https://polygon.llamarpc.com", "https://polygon-rpc.com"]},
    {"name": "Arbitrum", "network": Network.ARB_MAINNET, "rpc_url": f"https://arb-mainnet.g.alchemy.com/v2/{config.ALCHEMY_API_KEY}", "chain_id": 42161, "native_token": "ETH", "public_rpc": "https://arb1.arbitrum.io/rpc", "backup_rpcs": ["https://rpc.ankr.com/arbitrum", "https://arbitrum.llamarpc.com", "https://arbitrum-one.publicnode.com"]},
    {"name": "Optimism", "network": Network.OPT_MAINNET, "rpc_url": f"https://opt-mainnet.g.alchemy.com/v2/{config.ALCHEMY_API_KEY}", "chain_id": 10, "native_token": "ETH", "public_rpc": "https://mainnet.optimism.io", "backup_rpcs": ["https://rpc.ankr.com/optimism", "https://optimism.llamarpc.com", "https://optimism.publicnode.com"]},
    
    # Layer2和扩展链
    {"name": "Base", "network": None, "rpc_url": f"https://base-mainnet.g.alchemy.com/v2/{config.ALCHEMY_API_KEY}", "chain_id": 8453, "native_token": "ETH", "public_rpc": "https://mainnet.base.org", "backup_rpcs": ["https://base.llamarpc.com", "https://base.publicnode.com", "https://1rpc.io/base"]},
    {"name": "Polygon zkEVM", "network": None, "rpc_url": f"https://polygonzkevm-mainnet.g.alchemy.com/v2/{config.ALCHEMY_API_KEY}", "chain_id": 1101, "native_token": "ETH", "public_rpc": "https://zkevm-rpc.com", "backup_rpcs": ["https://rpc.ankr.com/polygon_zkevm", "https://polygon-zkevm.drpc.org", "https://zkevm-rpc.com"]},
    {"name": "zkSync Era", "network": None, "rpc_url": f"https://zksync-mainnet.g.alchemy.com/v2/{config.ALCHEMY_API_KEY}", "chain_id": 324, "native_token": "ETH", "public_rpc": "https://mainnet.era.zksync.io", "backup_rpcs": ["https://zksync.drpc.org", "https://mainnet.era.zksync.io", "https://zksync.me"]},
    {"name": "Scroll", "network": None, "rpc_url": f"https://scroll-mainnet.g.alchemy.com/v2/{config.ALCHEMY_API_KEY}", "chain_id": 534352, "native_token": "ETH", "public_rpc": "https://rpc.scroll.io", "backup_rpcs": ["https://scroll.drpc.org", "https://rpc.scroll.io", "https://scroll-mainnet.public.blastapi.io"]},
    {"name": "Blast", "network": None, "rpc_url": f"https://blast-mainnet.g.alchemy.com/v2/{config.ALCHEMY_API_KEY}", "chain_id": 81457, "native_token": "ETH", "public_rpc": "https://rpc.blast.io", "backup_rpcs": ["https://rpc.blast.io", "https://blast.blockpi.network/v1/rpc/public", "https://blast.drpc.org"]},
    {"name": "Linea", "network": None, "rpc_url": f"https://linea-mainnet.g.alchemy.com/v2/{config.ALCHEMY_API_KEY}", "chain_id": 59144, "native_token": "ETH", "public_rpc": "https://rpc.linea.build", "backup_rpcs": ["https://linea.drpc.org", "https://rpc.linea.build", "https://1rpc.io/linea"]},
    {"name": "Zora", "network": None, "rpc_url": f"https://zora-mainnet.g.alchemy.com/v2/{config.ALCHEMY_API_KEY}", "chain_id": 7777777, "native_token": "ETH", "public_rpc": "https://rpc.zora.energy", "backup_rpcs": ["https://rpc.zora.energy", "https://zora.drpc.org", "https://1rpc.io/zora"]},
    {"name": "opBNB", "network": None, "rpc_url": f"https://opbnb-mainnet.g.alchemy.com/v2/{config.ALCHEMY_API_KEY}", "chain_id": 204, "native_token": "BNB", "public_rpc": "https://opbnb-mainnet-rpc.bnbchain.org", "backup_rpcs": ["https://opbnb-mainnet-rpc.bnbchain.org", "https://opbnb.drpc.org", "https://1rpc.io/opbnb"]},
    
    # 其他主网
    {"name": "Celo", "network": None, "rpc_url": f"https://celo-mainnet.g.alchemy.com/v2/{config.ALCHEMY_API_KEY}", "chain_id": 42220, "native_token": "CELO", "public_rpc": "https://forno.celo.org", "backup_rpcs": ["https://forno.celo.org", "https://celo.drpc.org", "https://1rpc.io/celo"]},
    {"name": "Astar", "network": None, "rpc_url": f"https://astar-mainnet.g.alchemy.com/v2/{config.ALCHEMY_API_KEY}", "chain_id": 592, "native_token": "ASTR", "public_rpc": "https://astar.api.onfinality.io/public", "backup_rpcs": ["https://astar.api.onfinality.io/public", "https://astar.drpc.org", "https://1rpc.io/astar"]},
    {"name": "Arbitrum Nova", "network": None, "rpc_url": f"https://arbnova-mainnet.g.alchemy.com/v2/{config.ALCHEMY_API_KEY}", "chain_id": 42170, "native_token": "ETH", "public_rpc": "https://nova.arbitrum.io/rpc", "backup_rpcs": ["https://nova.arbitrum.io/rpc", "https://arbitrum-nova.drpc.org", "https://1rpc.io/arbitrum-nova"]},
    {"name": "ZetaChain", "network": None, "rpc_url": f"https://zetachain-mainnet.g.alchemy.com/v2/{config.ALCHEMY_API_KEY}", "chain_id": 7000, "native_token": "ZETA", "public_rpc": "https://api.mainnet.zetachain.com/evm", "backup_rpcs": ["https://api.mainnet.zetachain.com/evm", "https://zetachain.drpc.org", "https://1rpc.io/zetachain"]},
    {"name": "Fantom", "network": None, "rpc_url": f"https://fantom-mainnet.g.alchemy.com/v2/{config.ALCHEMY_API_KEY}", "chain_id": 250, "native_token": "FTM", "public_rpc": "https://rpc.ftm.tools", "backup_rpcs": ["https://rpc.ftm.tools", "https://fantom.drpc.org", "https://1rpc.io/fantom"]},
    {"name": "Mantle", "network": None, "rpc_url": f"https://mantle-mainnet.g.alchemy.com/v2/{config.ALCHEMY_API_KEY}", "chain_id": 5000, "native_token": "MNT", "public_rpc": "https://rpc.mantle.xyz", "backup_rpcs": ["https://rpc.mantle.xyz", "https://mantle.drpc.org", "https://1rpc.io/mantle"]},
    {"name": "Berachain", "network": None, "rpc_url": f"https://berachain-mainnet.g.alchemy.com/v2/{config.ALCHEMY_API_KEY}", "chain_id": 80094, "native_token": "BERA", "public_rpc": "https://artio.rpc.berachain.com", "backup_rpcs": ["https://artio.rpc.berachain.com", "https://berachain.drpc.org", "https://1rpc.io/berachain"]},
    {"name": "Ronin", "network": None, "rpc_url": f"https://ronin-mainnet.g.alchemy.com/v2/{config.ALCHEMY_API_KEY}", "chain_id": 2020, "native_token": "RON", "public_rpc": "https://api.roninchain.com/rpc", "backup_rpcs": ["https://api.roninchain.com/rpc", "https://ronin.drpc.org", "https://1rpc.io/ronin"]},
    {"name": "Settlus", "network": None, "rpc_url": f"https://settlus-mainnet.g.alchemy.com/v2/{config.ALCHEMY_API_KEY}", "chain_id": 7373, "native_token": "SETTL", "public_rpc": "https://rpc.settlus.com", "backup_rpcs": ["https://rpc.settlus.com", "https://settlus.drpc.org", "https://1rpc.io/settlus"]},
    {"name": "Rootstock", "network": None, "rpc_url": f"https://rootstock-mainnet.g.alchemy.com/v2/{config.ALCHEMY_API_KEY}", "chain_id": 30, "native_token": "RBTC", "public_rpc": "https://public-node.rsk.co", "backup_rpcs": ["https://public-node.rsk.co", "https://rootstock.drpc.org", "https://1rpc.io/rootstock"]},
    {"name": "Story", "network": None, "rpc_url": f"https://story-mainnet.g.alchemy.com/v2/{config.ALCHEMY_API_KEY}", "chain_id": 1513, "native_token": "IP", "public_rpc": "https://rpc.story.xyz", "backup_rpcs": ["https://rpc.story.xyz", "https://story.drpc.org", "https://1rpc.io/story"]},
    {"name": "Lens", "network": None, "rpc_url": f"https://lens-mainnet.g.alchemy.com/v2/{config.ALCHEMY_API_KEY}", "chain_id": 80002, "native_token": "LENS", "public_rpc": "https://rpc.lens.xyz", "backup_rpcs": ["https://rpc.lens.xyz", "https://lens.drpc.org", "https://1rpc.io/lens"]},
    {"name": "Frax", "network": None, "rpc_url": f"https://frax-mainnet.g.alchemy.com/v2/{config.ALCHEMY_API_KEY}", "chain_id": 252, "native_token": "FRAX", "public_rpc": "https://rpc.frax.com", "backup_rpcs": ["https://rpc.frax.com", "https://frax.drpc.org", "https://1rpc.io/frax"]},
    {"name": "Avalanche", "network": None, "rpc_url": f"https://avax-mainnet.g.alchemy.com/v2/{config.ALCHEMY_API_KEY}", "chain_id": 43114, "native_token": "AVAX", "public_rpc": "https://api.avax.network/ext/bc/C/rpc", "backup_rpcs": ["https://api.avax.network/ext/bc/C/rpc", "https://avalanche.drpc.org", "https://1rpc.io/avax"]},
    {"name": "Gnosis", "network": None, "rpc_url": f"https://gnosis-mainnet.g.alchemy.com/v2/{config.ALCHEMY_API_KEY}", "chain_id": 100, "native_token": "xDAI", "public_rpc": "https://rpc.gnosischain.com", "backup_rpcs": ["https://rpc.gnosischain.com", "https://gnosis.drpc.org", "https://1rpc.io/gnosis"]},
    {"name": "BNB Smart Chain", "network": None, "rpc_url": f"https://bnb-mainnet.g.alchemy.com/v2/{config.ALCHEMY_API_KEY}", "chain_id": 56, "native_token": "BNB", "public_rpc": "https://bsc-dataseed.binance.org", "backup_rpcs": ["https://bsc-dataseed.binance.org", "https://bsc.drpc.org", "https://1rpc.io/bnb"]},
    {"name": "Unichain", "network": None, "rpc_url": f"https://unichain-mainnet.g.alchemy.com/v2/{config.ALCHEMY_API_KEY}", "chain_id": 130, "native_token": "ETH", "public_rpc": "https://rpc-mainnet.unichain.world", "backup_rpcs": ["https://rpc-mainnet.unichain.world", "https://unichain.drpc.org", "https://1rpc.io/unichain"]},
    {"name": "Superseed", "network": None, "rpc_url": f"https://superseed-mainnet.g.alchemy.com/v2/{config.ALCHEMY_API_KEY}", "chain_id": 5330, "native_token": "SEED", "public_rpc": "https://rpc.superseed.xyz", "backup_rpcs": ["https://rpc.superseed.xyz", "https://superseed.drpc.org", "https://1rpc.io/superseed"]},
    {"name": "Flow EVM", "network": None, "rpc_url": f"https://flow-mainnet.g.alchemy.com/v2/{config.ALCHEMY_API_KEY}", "chain_id": 747, "native_token": "FLOW", "public_rpc": "https://flow-rpc.galaxy.com", "backup_rpcs": ["https://flow-rpc.galaxy.com", "https://flow.drpc.org", "https://1rpc.io/flow"]},
    {"name": "Degen", "network": None, "rpc_url": f"https://degen-mainnet.g.alchemy.com/v2/{config.ALCHEMY_API_KEY}", "chain_id": 101, "native_token": "DEGEN", "public_rpc": "https://rpc.degen.tips", "backup_rpcs": ["https://rpc.degen.tips", "https://degen.drpc.org", "https://1rpc.io/degen"]},

    {"name": "ApeChain", "network": None, "rpc_url": f"https://apechain-mainnet.g.alchemy.com/v2/{config.ALCHEMY_API_KEY}", "chain_id": 33139, "native_token": "APE", "public_rpc": "https://rpc.apechain.com", "backup_rpcs": ["https://rpc.apechain.com", "https://apechain.drpc.org", "https://1rpc.io/apechain"]},
    {"name": "Metis", "network": None, "rpc_url": f"https://metis-mainnet.g.alchemy.com/v2/{config.ALCHEMY_API_KEY}", "chain_id": 1088, "native_token": "METIS", "public_rpc": "https://andromeda.metis.io", "backup_rpcs": ["https://andromeda.metis.io", "https://metis.drpc.org", "https://1rpc.io/metis"]},
    {"name": "Sonic", "network": None, "rpc_url": f"https://sonic-mainnet.g.alchemy.com/v2/{config.ALCHEMY_API_KEY}", "chain_id": 64165, "native_token": "SONIC", "public_rpc": "https://rpc.sonic.network", "backup_rpcs": ["https://rpc.sonic.network", "https://sonic.drpc.org", "https://1rpc.io/sonic"]},
    {"name": "Soneium", "network": None, "rpc_url": f"https://soneium-mainnet.g.alchemy.com/v2/{config.ALCHEMY_API_KEY}", "chain_id": 1946, "native_token": "SONE", "public_rpc": "https://rpc.soneium.com", "backup_rpcs": ["https://rpc.soneium.com", "https://soneium.drpc.org", "https://1rpc.io/soneium"]},
    {"name": "Abstract", "network": None, "rpc_url": f"https://abstract-mainnet.g.alchemy.com/v2/{config.ALCHEMY_API_KEY}", "chain_id": 11124, "native_token": "ABST", "public_rpc": "https://rpc.abstract.network", "backup_rpcs": ["https://rpc.abstract.network", "https://abstract.drpc.org", "https://1rpc.io/abstract"]},

    
    # ===== 测试网（仅保留活跃的）=====
    # 主要测试网
    {"name": "Ethereum Sepolia", "network": None, "rpc_url": f"https://eth-sepolia.g.alchemy.com/v2/{config.ALCHEMY_API_KEY}", "chain_id": 11155111, "native_token": "ETH", "public_rpc": "https://rpc.sepolia.org", "backup_rpcs": ["https://rpc.sepolia.org", "https://sepolia.drpc.org", "https://1rpc.io/sepolia"]},
    {"name": "Arbitrum Sepolia", "network": None, "rpc_url": f"https://arb-sepolia.g.alchemy.com/v2/{config.ALCHEMY_API_KEY}", "chain_id": 421614, "native_token": "ETH", "public_rpc": "https://sepolia-rollup.arbitrum.io/rpc", "backup_rpcs": ["https://sepolia-rollup.arbitrum.io/rpc", "https://arbitrum-sepolia.drpc.org", "https://1rpc.io/arbitrum-sepolia"]},
    {"name": "Optimism Sepolia", "network": None, "rpc_url": f"https://opt-sepolia.g.alchemy.com/v2/{config.ALCHEMY_API_KEY}", "chain_id": 11155420, "native_token": "ETH", "public_rpc": "https://sepolia.optimism.io", "backup_rpcs": ["https://sepolia.optimism.io", "https://optimism-sepolia.drpc.org", "https://1rpc.io/optimism-sepolia"]},
    {"name": "Base Sepolia", "network": None, "rpc_url": f"https://base-sepolia.g.alchemy.com/v2/{config.ALCHEMY_API_KEY}", "chain_id": 84532, "native_token": "ETH", "public_rpc": "https://sepolia.base.org", "backup_rpcs": ["https://sepolia.base.org", "https://base-sepolia.drpc.org", "https://1rpc.io/base-sepolia"]},
    {"name": "Avalanche Fuji", "network": None, "rpc_url": f"https://avax-fuji.g.alchemy.com/v2/{config.ALCHEMY_API_KEY}", "chain_id": 43113, "native_token": "AVAX", "public_rpc": "https://api.avax-test.network/ext/bc/C/rpc", "backup_rpcs": ["https://api.avax-test.network/ext/bc/C/rpc", "https://avalanche-fuji.drpc.org", "https://1rpc.io/avax-fuji"]},
]

# Solana链配置
SOLANA_CHAINS = [
    # 主网
    {"name": "Solana Mainnet", "rpc_url": "https://api.mainnet-beta.solana.com", "is_mainnet": True, "native_token": "SOL", "public_rpc": "https://solana-api.projectserum.com"},
    {"name": "Solana Devnet", "rpc_url": "https://api.devnet.solana.com", "is_mainnet": False, "native_token": "SOL", "public_rpc": "https://api.devnet.solana.com"},
    {"name": "Solana Testnet", "rpc_url": "https://api.testnet.solana.com", "is_mainnet": False, "native_token": "SOL", "public_rpc": "https://api.testnet.solana.com"},
    
    # Solana兼容链
    {"name": "Sui", "rpc_url": "https://fullnode.mainnet.sui.io:443", "is_mainnet": True, "native_token": "SUI", "public_rpc": "https://sui-mainnet-rpc.allthatnode.com"},
    {"name": "Aptos", "rpc_url": "https://fullnode.mainnet.aptoslabs.com/v1", "is_mainnet": True, "native_token": "APT", "public_rpc": "https://aptos-mainnet.pontem.network"},
    {"name": "Sei", "rpc_url": "https://rpc.atlantic-2.seinetwork.io", "is_mainnet": True, "native_token": "SEI", "public_rpc": "https://sei-rpc.publicnode.com"},
    {"name": "Injective", "rpc_url": "https://sentry.tm.injective.network:26657", "is_mainnet": True, "native_token": "INJ", "public_rpc": "https://tm.injective.network:26657"},
    {"name": "Celestia", "rpc_url": "https://rpc.celestia.nodestake.top", "is_mainnet": True, "native_token": "TIA", "public_rpc": "https://rpc.celestia.nodestake.top"},
    {"name": "NEAR", "rpc_url": "https://rpc.mainnet.near.org", "is_mainnet": True, "native_token": "NEAR", "public_rpc": "https://rpc.mainnet.near.org"},
    {"name": "Polkadot", "rpc_url": "https://rpc.polkadot.io", "is_mainnet": True, "native_token": "DOT", "public_rpc": "https://rpc.polkadot.io"},
    {"name": "Cosmos", "rpc_url": "https://rpc.cosmos.network:26657", "is_mainnet": True, "native_token": "ATOM", "public_rpc": "https://rpc.cosmos.network:26657"},
    
    # 测试网
    {"name": "Sui Testnet", "rpc_url": "https://fullnode.testnet.sui.io:443", "is_mainnet": False, "native_token": "SUI", "public_rpc": "https://fullnode.testnet.sui.io:443"},
    {"name": "Aptos Testnet", "rpc_url": "https://fullnode.testnet.aptoslabs.com/v1", "is_mainnet": False, "native_token": "APT", "public_rpc": "https://fullnode.testnet.aptoslabs.com/v1"},
    {"name": "Sei Testnet", "rpc_url": "https://rpc.atlantic-1.seinetwork.io", "is_mainnet": False, "native_token": "SEI", "public_rpc": "https://rpc.atlantic-1.seinetwork.io"},
    {"name": "Injective Testnet", "rpc_url": "https://testnet.sentry.tm.injective.network:26657", "is_mainnet": False, "native_token": "INJ", "public_rpc": "https://testnet.sentry.tm.injective.network:26657"},
    {"name": "Celestia Testnet", "rpc_url": "https://rpc.mocha-4.arabica-10.celestia.nodestake.top", "is_mainnet": False, "native_token": "TIA", "public_rpc": "https://rpc.mocha-4.arabica-10.celestia.nodestake.top"},
    {"name": "NEAR Testnet", "rpc_url": "https://rpc.testnet.near.org", "is_mainnet": False, "native_token": "NEAR", "public_rpc": "https://rpc.testnet.near.org"},
    {"name": "Polkadot Testnet", "rpc_url": "https://rpc.polkadot.io", "is_mainnet": False, "native_token": "DOT", "public_rpc": "https://rpc.polkadot.io"},
    {"name": "Cosmos Testnet", "rpc_url": "https://rpc.testnet.cosmos.network:26657", "is_mainnet": False, "native_token": "ATOM", "public_rpc": "https://rpc.testnet.cosmos.network:26657"},
]

# ERC-20 Token configurations - 常见代币配置（作为备用方案）
ERC20_TOKENS = {
    # 稳定币
    "USDT": {
        "Ethereum": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
        "Polygon PoS": "0xc2132D05D31c914a87C6611C10748AEb04B58e8F",
        "Arbitrum": "0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9",
        "OP Mainnet": "0x94b008aA00579c1307B0EF2c499aD98a8ce58e58",
        "BSC": "0x55d398326f99059fF775485246999027B3197955",
        "Base": "0x50c5725949A6F0c72E6C4a641F24049A917DB0Cb6",
        "Avalanche": "0x9702230A8Ea53601f5cD2dc00fDBc13d4dF4A8c7",
        "Fantom": "0x049d68029688eAbF473097a2fC38ef61633A3C7A",
        "Gnosis": "0x4ECaBa5870353805a9F068101A40E0f32ed605C6",
        "Metis": "0xbb06D5A0b1c8C8e8B5C0C0C0C0C0C0C0C0C0C0C",
    },
    "USDC": {
        "Ethereum": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        "Polygon PoS": "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",
        "Arbitrum": "0xFF970A61A04b1cA14834A43f5dE4533eBDDB5CC8",
        "OP Mainnet": "0x7F5c764cBc14f9669B88837ca1490cCa17c31607",
        "BSC": "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d",
        "Base": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
        "Avalanche": "0xB97EF9Ef8734C71904D8002F8b6Bc66Dd9c48a6E",
        "Fantom": "0x04068DA6C83AFCFA0e13ba15A6696662335D5B75",
        "Gnosis": "0xDDAfbb505ad214D7b80b1f830fcCc89B60fb7A83",
        "Metis": "0xEA32A96608495e54156A489dF60bbE4b5c3b500E",
    },
    "DAI": {
        "Ethereum": "0x6B175474E89094C44Da98b954EedeAC495271d0F",
        "Polygon PoS": "0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063",
        "Arbitrum": "0xDA10009cBd5D07dd0CeCc66161FC93D7c9000da1",
        "OP Mainnet": "0xDA10009cBd5D07dd0CeCc66161FC93D7c9000da1",
        "BSC": "0x1AF3F329e8BE154074D8769D1FFa4eE058B1DBc3",
        "Base": "0x50c5725949A6F0c72E6C4a641F24049A917DB0Cb6",
        "Avalanche": "0xd586E7F844cEa2F87f50152665BCbc2C279D8d70",
        "Fantom": "0x8D11eC38a3EB5E956B852f9F0C1C2C5C3B9e0C0C",
        "Gnosis": "0xe91d153e0b41518a2ce8dd3d7944fa863463a97d",
        "Metis": "0x4c078361FC9FbBf02f3024BD062f79279327ebd4B",
    },
    
    # DeFi代币
    "WETH": {
        "Ethereum": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
        "Polygon PoS": "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f613",
        "Arbitrum": "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
        "OP Mainnet": "0x4200000000000000000000000000000000000006",
        "BSC": "0x2170Ed0880ac9A755fd29B2688956BD959F933F8",
        "Base": "0x4200000000000000000000000000000000000006",
        "Avalanche": "0x49D5c2BdFfac6CE2BFdB6640F4F80f226bc10bAB",
        "Fantom": "0x74b23882a30290451A17c44f4F05243b6b58C76d",
        "Gnosis": "0x6A023CCd1ff6F2045C3309768eAd9E68F978f6e1",
        "Metis": "0x75cb093E4D1dC2cD4C6C011C2C0C0C0C0C0C0C0C",
    },
    "WBTC": {
        "Ethereum": "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599",
        "Polygon PoS": "0x1BFD67037B42Cf73acF2047067bd4F2C47D9BfD6",
        "Arbitrum": "0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
        "OP Mainnet": "0x68f180fcCe6836688e9084f035309E29Bf0A2095",
        "BSC": "0x7130d2A12B9BCbFAe4f2634d864A1Ee1Ce3Ead9c",
        "Base": "0x2Ae3F1Ec7F1F5012CFEab0185bfc7aa3cf0DEc22",
        "Avalanche": "0x50b7545627a5162F82A992c33b87aDc75187B218",
        "Fantom": "0x321162Cd933E2Be498Cd2267a90534A804051b11",
        "Gnosis": "0x8e5bBbb09Ed1ebdE8674Cda39A0c169401db4252",
        "Metis": "0x433E077d4da9B8E8C1C1C0C0C0C0C0C0C0C0C0C",
    },
    
    # 链原生代币包装版本
    "WMATIC": {
        "Polygon PoS": "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270",
    },
    "WBNB": {
        "BSC": "0xbb4CdB9CBd36B01bD1cBaEF2aF8a6C5C6C0C0C0C",
    },
    "WAVAX": {
        "Avalanche": "0xB31f66AA3C1e785363F0875A1B74E27b85FD66c7",
    },
    "WFTM": {
        "Fantom": "0x21be370D5312f44cB42ce377BC9b8a0cEF1A4C83",
    },
    
    # 其他常见代币
    "LINK": {
        "Ethereum": "0x514910771AF9Ca656af840dff83E8264EcF986CA",
        "Polygon PoS": "0x53E0bca35eC356BD5ddDFebD1Fc0fD03FaBad39B",
        "Arbitrum": "0xf97f4df75117a78c1A5a0DBb814Af92458539FB4",
        "OP Mainnet": "0x350a791Bfc2C21F9Ed5d10980Dad2e2638ffa7f6",
        "BSC": "0xF8A0BF9cF54Bb92F17374d9e9A321E6a111a51bD",
    },
    "UNI": {
        "Ethereum": "0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984",
        "Polygon PoS": "0xb33EaAd8d922B08A611545E7f97e0e5C0C0C0C0C",
        "Arbitrum": "0xFa7F8980b0f1E64A2062791cc3b0871572f1F7f0",
        "OP Mainnet": "0x6fd9d7AD17242c41f7131d25720c4C9c0C0C0C0C",
        "BSC": "0xBf5140A22578168FD562DCcF235E5D43A02ce9B1",
    },
    "AAVE": {
        "Ethereum": "0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9",
        "Polygon PoS": "0xD6DF932A45C0f255f85145f286eA0b292B21C90B",
        "Arbitrum": "0xBa5DdD1F9d7F570dc94a51479a000E3bE96777e7",
        "OP Mainnet": "0x76FB31f4F7785a6E0C0C0C0C0C0C0C0C0C0C0C",
        "BSC": "0xfb6115445Bff7b52FeB98650C87f44907E58f802f",
    },
    
    # 自定义代币（保留原有配置）
    "UNIQUE_TOKEN": {
        "Arbitrum": "0x1114982539A2Bfb84e8B9e4e320bbC04532a9e44",
    }
}

# 缓存和性能优化模块
class CacheManager:
    """智能缓存管理器"""
    
    def __init__(self):
        self._cache = {}
        self._cache_lock = threading.Lock()
        self._cache_stats = {"hits": 0, "misses": 0, "total_requests": 0}
        
    def get(self, key: str, max_age: int = 300):
        """获取缓存数据（默认5分钟过期）"""
        with self._cache_lock:
            self._cache_stats["total_requests"] += 1
            
            if key in self._cache:
                data, timestamp = self._cache[key]
                if time.time() - timestamp < max_age:
                    self._cache_stats["hits"] += 1
                    return data
                else:
                    # 缓存过期，删除
                    del self._cache[key]
            
            self._cache_stats["misses"] += 1
            return None
    
    def set(self, key: str, value):
        """设置缓存数据"""
        with self._cache_lock:
            self._cache[key] = (value, time.time())
            
            # 限制缓存大小，清理最老的条目
            if len(self._cache) > 1000:
                oldest_key = min(self._cache.keys(), 
                               key=lambda k: self._cache[k][1])
                del self._cache[oldest_key]
    
    def clear(self):
        """清理所有缓存"""
        with self._cache_lock:
            self._cache.clear()
    
    def get_stats(self):
        """获取缓存统计"""
        with self._cache_lock:
            total = self._cache_stats["total_requests"]
            hits = self._cache_stats["hits"]
            hit_rate = (hits / total * 100) if total > 0 else 0
            return {
                "hit_rate": f"{hit_rate:.1f}%",
                "total_requests": total,
                "cache_size": len(self._cache)
            }

class RPCLoadBalancer:
    """智能RPC负载均衡器"""
    
    def __init__(self):
        self._rpc_stats = {}
        self._stats_lock = threading.Lock()
        
    def record_request(self, rpc_url: str, success: bool, response_time: float):
        """记录RPC请求统计"""
        with self._stats_lock:
            if rpc_url not in self._rpc_stats:
                self._rpc_stats[rpc_url] = {
                    "success_count": 0,
                    "error_count": 0,
                    "total_response_time": 0.0,
                    "request_count": 0,
                    "last_used": 0,
                    "consecutive_errors": 0
                }
            
            stats = self._rpc_stats[rpc_url]
            stats["request_count"] += 1
            stats["total_response_time"] += response_time
            stats["last_used"] = time.time()
            
            if success:
                stats["success_count"] += 1
                stats["consecutive_errors"] = 0
            else:
                stats["error_count"] += 1
                stats["consecutive_errors"] += 1
    
    def get_best_rpc(self, rpc_list: list) -> dict:
        """选择最佳RPC节点"""
        if not rpc_list:
            return None
        
        with self._stats_lock:
            # 计算每个RPC的评分
            scored_rpcs = []
            
            for rpc in rpc_list:
                rpc_url = rpc.get("rpc_url", "")
                stats = self._rpc_stats.get(rpc_url, {})
                
                # 评分因子
                success_rate = 1.0
                avg_response_time = 1.0
                consecutive_errors = stats.get("consecutive_errors", 0)
                
                if stats.get("request_count", 0) > 0:
                    success_rate = stats["success_count"] / stats["request_count"]
                    avg_response_time = stats["total_response_time"] / stats["request_count"]
                
                # 如果连续错误超过5次，大幅降低评分
                if consecutive_errors >= 5:
                    score = 0.1
                else:
                    # 综合评分：成功率70% + 响应时间30%
                    time_score = max(0.1, 1.0 / (avg_response_time + 0.1))
                    score = success_rate * 0.7 + time_score * 0.3
                
                scored_rpcs.append((score, rpc))
            
            # 返回评分最高的RPC
            if scored_rpcs:
                return max(scored_rpcs, key=lambda x: x[0])[1]
            
            return rpc_list[0]  # 默认返回第一个
    
    def get_stats_summary(self) -> dict:
        """获取RPC统计摘要"""
        with self._stats_lock:
            summary = {}
            for rpc_url, stats in self._rpc_stats.items():
                if stats["request_count"] > 0:
                    success_rate = stats["success_count"] / stats["request_count"] * 100
                    avg_response = stats["total_response_time"] / stats["request_count"]
                    summary[rpc_url] = {
                        "success_rate": f"{success_rate:.1f}%",
                        "avg_response_time": f"{avg_response:.3f}s",
                        "total_requests": stats["request_count"],
                        "consecutive_errors": stats["consecutive_errors"]
                    }
            return summary

# 进度条和用户界面增强
class ProgressBar:
    """美化的进度条显示"""
    
    def __init__(self, total: int, desc: str = "", width: int = 40):
        self.total = total
        self.current = 0
        self.desc = desc
        self.width = width
        self.start_time = time.time()
        
    def update(self, current: int = None, desc: str = None):
        """更新进度"""
        if current is not None:
            self.current = current
        else:
            self.current += 1
            
        if desc:
            self.desc = desc
            
        # 计算进度百分比
        percentage = (self.current / self.total) * 100 if self.total > 0 else 0
        
        # 创建进度条
        filled_width = int(self.width * self.current // self.total) if self.total > 0 else 0
        bar = '█' * filled_width + '░' * (self.width - filled_width)
        
        # 计算估计剩余时间
        elapsed = time.time() - self.start_time
        if self.current > 0:
            eta = (elapsed / self.current) * (self.total - self.current)
            eta_str = f"{eta:.1f}s" if eta < 60 else f"{eta/60:.1f}m"
        else:
            eta_str = "未知"
        
        # 构建显示字符串
        if COLORAMA_AVAILABLE:
            progress_line = (
                f"\r{Fore.CYAN}[{bar}] "
                f"{Fore.YELLOW}{percentage:5.1f}% "
                f"{Fore.WHITE}({self.current}/{self.total}) "
                f"{Fore.GREEN}{self.desc} "
                f"{Fore.BLUE}ETA: {eta_str}{Style.RESET_ALL}"
            )
        else:
            progress_line = f"\r[{bar}] {percentage:5.1f}% ({self.current}/{self.total}) {self.desc} ETA: {eta_str}"
        
        print(progress_line, end='', flush=True)
        
        if self.current >= self.total:
            print()  # 完成时换行

class IPRateLimiter:
    """IP访问速率限制器"""
    
    def __init__(self, max_requests: int = 100, time_window: int = 3600):
        self.max_requests = max_requests
        self.time_window = time_window
        self._requests = {}
        self._lock = threading.Lock()
        
    def is_allowed(self, ip_address: str) -> bool:
        """检查IP是否被允许访问"""
        current_time = time.time()
        
        with self._lock:
            if ip_address not in self._requests:
                self._requests[ip_address] = []
            
            # 清理过期的请求记录
            requests = self._requests[ip_address]
            self._requests[ip_address] = [
                req_time for req_time in requests 
                if current_time - req_time < self.time_window
            ]
            
            # 检查是否超出限制
            if len(self._requests[ip_address]) >= self.max_requests:
                return False
            
            # 记录新请求
            self._requests[ip_address].append(current_time)
            return True
    
    def get_remaining_requests(self, ip_address: str) -> int:
        """获取剩余请求次数"""
        current_time = time.time()
        
        with self._lock:
            if ip_address not in self._requests:
                return self.max_requests
            
            # 清理过期请求
            requests = self._requests[ip_address]
            valid_requests = [
                req_time for req_time in requests 
                if current_time - req_time < self.time_window
            ]
            
            return max(0, self.max_requests - len(valid_requests))

class SensitiveDataFilter:
    """敏感数据过滤器"""
    
    @staticmethod
    def filter_private_key(text: str) -> str:
        """过滤私钥信息"""
        # EVM私钥模式 (64位十六进制字符)
        evm_pattern = r'\b[0-9a-fA-F]{64}\b'
        text = re.sub(evm_pattern, '[PRIVATE_KEY_FILTERED]', text)
        
        # Solana私钥模式 (Base58编码，通常44-88字符)
        solana_pattern = r'\b[1-9A-HJ-NP-Za-km-z]{44,88}\b'
        text = re.sub(solana_pattern, '[SOLANA_KEY_FILTERED]', text)
        
        # 助记词模式 (12-24个英文单词)
        mnemonic_pattern = r'\b(?:[a-z]+\s+){11,23}[a-z]+\b'
        text = re.sub(mnemonic_pattern, '[MNEMONIC_FILTERED]', text, flags=re.IGNORECASE)
        
        return text
    
    @staticmethod
    def filter_sensitive_info(text: str) -> str:
        """过滤所有敏感信息"""
        # 过滤私钥
        text = SensitiveDataFilter.filter_private_key(text)
        
        # 过滤可能的API密钥
        api_key_pattern = r'\b[A-Za-z0-9]{32,}\b'
        text = re.sub(api_key_pattern, lambda m: '[API_KEY_FILTERED]' if len(m.group()) > 40 else m.group(), text)
        
        return text

# 全局实例
cache_manager = CacheManager()
rpc_load_balancer = RPCLoadBalancer()
rate_limiter = IPRateLimiter()

class WalletMonitor:
    def __init__(self):
        # 基础配置
        self.private_keys = []
        self.addresses = []
        self.addr_to_key = {}
        self.addr_type = {}
        self.active_addr_to_chains = {}
        self.evm_clients = []
        self.solana_clients = []
        
        # 线程安全的状态变量
        self._state_lock = threading.Lock()  # 保护共享状态的锁
        self._alchemy_error_count = 0
        self._use_public_rpc = False
        self._rpc_switch_time = 0
        self._client_error_counts = {}  # 每个客户端的错误计数
        
        # 监控状态
        self.monitoring_active = False
        
        # 缓存和性能优化
        self.cache_manager = cache_manager
        self.rpc_load_balancer = rpc_load_balancer
        self.rate_limiter = rate_limiter
        
        logger.info("🚀 钱包监控器初始化完成")
        logger.info("📊 性能优化模块已启用: 缓存、负载均衡、速率限制")
    
    @property
    def alchemy_error_count(self):
        """线程安全的错误计数访问"""
        with self._state_lock:
            return self._alchemy_error_count
    
    @alchemy_error_count.setter
    def alchemy_error_count(self, value):
        """线程安全的错误计数设置"""
        with self._state_lock:
            self._alchemy_error_count = value
    
    @property
    def use_public_rpc(self):
        """线程安全的RPC模式访问"""
        with self._state_lock:
            return self._use_public_rpc
    
    @use_public_rpc.setter
    def use_public_rpc(self, value):
        """线程安全的RPC模式设置"""
        with self._state_lock:
            self._use_public_rpc = value
    
    def increment_client_error_count(self, client_name: str) -> int:
        """线程安全地增加客户端错误计数"""
        with self._state_lock:
            if client_name not in self._client_error_counts:
                self._client_error_counts[client_name] = 0
            self._client_error_counts[client_name] += 1
            return self._client_error_counts[client_name]
    
    def reset_client_error_count(self, client_name: str):
        """线程安全地重置客户端错误计数"""
        with self._state_lock:
            self._client_error_counts[client_name] = 0
    
    def get_client_error_count(self, client_name: str) -> int:
        """线程安全地获取客户端错误计数"""
        with self._state_lock:
            return self._client_error_counts.get(client_name, 0)

    def initialize_evm_clients(self):
        """初始化EVM链客户端"""
        logger.info("正在初始化EVM链客户端...")
        clients = []
        
        # 检查是否需要切换到公共RPC
        current_time = time.time()
        if (self.alchemy_error_count >= config.ALCHEMY_ERROR_THRESHOLD and 
            current_time - self._rpc_switch_time >= config.ALCHEMY_SWITCH_DURATION):
            self.use_public_rpc = True
            self._rpc_switch_time = current_time
            logger.warning(f"⚠️  Alchemy连续错误 {self.alchemy_error_count} 次，切换到公共RPC")
        elif (self.use_public_rpc and 
              current_time - self._rpc_switch_time >= config.ALCHEMY_SWITCH_DURATION):
            self.use_public_rpc = False
            self.alchemy_error_count = 0
            logger.info("✅ 切换回Alchemy RPC")
        
        for chain in ALCHEMY_CHAINS:
            try:
                # 根据配置选择RPC
                if self.use_public_rpc:
                    # 使用公共RPC，优先使用主要公共RPC，失败时轮换备用RPC
                    rpc_urls = [chain["public_rpc"]] + chain.get("backup_rpcs", [])
                    rpc_type = "公共RPC"
                else:
                    # 使用Alchemy RPC
                    rpc_urls = [chain["rpc_url"]]
                    rpc_type = "Alchemy"
                
                # 尝试连接RPC
                w3 = None
                used_rpc = None
                
                for rpc_url in rpc_urls:
                    try:
                        w3 = Web3(Web3.HTTPProvider(rpc_url))
                        if hasattr(w3, 'is_connected') and w3.is_connected():
                            used_rpc = rpc_url
                            break
                    except Exception as e:
                        logger.debug(f"尝试连接 {chain['name']} 的RPC {rpc_url} 失败: {str(e)}")
                        continue
                
                if w3 and (getattr(w3, 'is_connected', lambda: True)()):
                    # 初始化Alchemy客户端（如果可用且使用Alchemy RPC）
                    alchemy_client = None
                    if (not self.use_public_rpc) and chain.get("network") and ALCHEMY_AVAILABLE:
                        try:
                            alchemy_client = Alchemy(api_key=config.ALCHEMY_API_KEY, network=chain["network"])
                        except Exception as e:
                            logger.warning(f"初始化 {chain['name']} 的Alchemy客户端失败: {str(e)}")
                    
                    clients.append({
                        "name": chain["name"],
                        "w3": w3,
                        "network": chain["network"],
                        "rpc_url": used_rpc,
                        "rpc_type": rpc_type,
                        "chain_id": chain["chain_id"],
                        "native_token": chain["native_token"],
                        "original_rpc_url": chain["rpc_url"],
                        "public_rpc_url": chain.get("public_rpc", ""),
                        "backup_rpcs": chain.get("backup_rpcs", []),
                        "last_error_time": 0,
                        "error_count": 0,
                        "alchemy": alchemy_client  # 添加Alchemy客户端
                    })
                    logger.info(f"✅ 成功连接到 {chain['name']} ({rpc_type}) - {used_rpc}")
                else:
                    logger.error(f"❌ 无法连接到 {chain['name']} 的任何RPC")
                    # 如果是Alchemy RPC失败，增加错误计数
                    if not self.use_public_rpc:
                        self.alchemy_error_count += 1
                    
            except Exception as e:
                logger.error(f"❌ 初始化 {chain['name']} 失败: {str(e)}")
                # 如果是Alchemy RPC失败，增加错误计数
                if not self.use_public_rpc:
                    self.alchemy_error_count += 1
        
        self.evm_clients = clients
        logger.info(f"总共初始化了 {len(clients)} 个EVM链客户端")
        return len(clients) > 0

    def initialize_solana_clients(self):
        """初始化Solana链客户端"""
        if not SOLANA_AVAILABLE:
            logger.warning("⚠️  Solana支持未安装，跳过Solana客户端初始化")
            return False
            
        logger.info("正在初始化Solana链客户端...")
        clients = []
        
        for chain in SOLANA_CHAINS:
            try:
                # 创建Solana客户端
                client = AsyncClient(chain["rpc_url"])
                clients.append({
                    "name": chain["name"],
                    "client": client,
                    "rpc_url": chain["rpc_url"],
                    "is_mainnet": chain["is_mainnet"],
                    "native_token": chain["native_token"]
                })
                logger.info(f"✅ 成功连接到 {chain['name']}")
            except Exception as e:
                logger.error(f"❌ 初始化 {chain['name']} 失败: {str(e)}")
        
        self.solana_clients = clients
        logger.info(f"总共初始化了 {len(clients)} 个Solana链客户端")
        return len(clients) > 0

    def collect_private_keys(self):
        """收集私钥"""
        if not is_interactive():
            print("⚠️ 非交互式环境，跳过私钥收集")
            return []
            
        print("\n" + "="*60)
        print("🔑 请输入私钥（一行一个，支持EVM和Solana格式）")
        print("📝 程序会自动识别私钥类型（EVM或Solana）")
        print("📝 输入完成后按两次回车开始监控")
        print("="*60)
        
        private_keys = []
        while True:
            try:
                key = safe_input("", "").strip()
                if key == "":
                    if len(private_keys) > 0:
                        confirm = safe_input("", "")
                        if confirm == "":
                            break
                    continue
                
                # 识别私钥类型
                key_type = identify_private_key_type(key)
                
                if key_type == "evm":
                    # 处理EVM私钥格式
                    if key.startswith("0x"):
                        key = key[2:]
                    
                    # 验证私钥格式
                    if len(key) == 64 and all(c in "0123456789abcdefABCDEF" for c in key):
                        private_keys.append({"key": key, "type": "evm"})
                        print(f"✅ 已添加EVM私钥 {len(private_keys)}")
                    else:
                        print(f"❌ 无效EVM私钥格式，已跳过")
                        
                elif key_type == "solana":
                    # 处理Solana私钥
                    private_keys.append({"key": key, "type": "solana"})
                    print(f"✅ 已添加Solana私钥 {len(private_keys)}")
                    
                else:
                    print(f"❌ 无法识别的私钥格式，已跳过")
                    
            except KeyboardInterrupt:
                print("\n❌ 用户中断输入")
                return []
            except Exception as e:
                print(f"❌ 输入错误: {str(e)}")
        
        logger.info(f"收集到 {len(private_keys)} 个私钥")
        return private_keys

    def check_transaction_history(self, address: str, clients: list) -> list:
        """检查地址的交易记录"""
        active_chains = []
        
        for client in clients:
            try:
                w3 = client["w3"]
                tx_count = w3.eth.get_transaction_count(address)
                if tx_count > 0:
                    active_chains.append(client)
                    logger.info(f"📊 地址 {address} 在链 {client['name']} 有 {tx_count} 笔交易记录")
                else:
                    logger.info(f"📊 地址 {address} 在链 {client['name']} 无交易记录")
            except Exception as e:
                logger.error(f"❌ 检查地址 {address} 在链 {client['name']} 交易记录失败: {str(e)}")
        
        return active_chains

    async def check_solana_transaction_history(self, address: str, clients: list) -> list:
        """检查Solana地址的交易记录"""
        active_chains = []
        
        for client in clients:
            try:
                sol_client = client["client"]
                # 获取账户信息
                response = await sol_client.get_account_info(PublicKey(address))
                
                if response.value is not None:
                    # 账户存在，检查是否有交易记录
                    try:
                        # 获取最近的交易签名
                        signatures = await sol_client.get_signatures_for_address(PublicKey(address), limit=1)
                        if signatures.value and len(signatures.value) > 0:
                            active_chains.append(client)
                            logger.info(f"📊 Solana地址 {address} 在链 {client['name']} 有交易记录")
                        else:
                            logger.info(f"📊 Solana地址 {address} 在链 {client['name']} 无交易记录")
                    except Exception as e:
                        logger.warning(f"⚠️  检查Solana地址 {address} 在链 {client['name']} 交易记录时出错: {str(e)}")
                        # 如果无法获取交易记录，但账户存在，仍然监控
                        active_chains.append(client)
                        logger.info(f"📊 Solana地址 {address} 在链 {client['name']} 账户存在，将监控")
                else:
                    logger.info(f"📊 Solana地址 {address} 在链 {client['name']} 账户不存在")
                    
            except Exception as e:
                logger.error(f"❌ 检查Solana地址 {address} 在链 {client['name']} 失败: {str(e)}")
        
        return active_chains

    async def filter_addresses_with_history(self):
        """过滤有交易记录的地址"""
        logger.info("🔍 正在检查地址交易记录...")
        
        for i, address in enumerate(self.addresses):
            logger.info(f"检查地址 {i+1}/{len(self.addresses)}: {address}")
            
            if self.addr_type[address] == "evm":
                # EVM地址
                active_chains = self.check_transaction_history(address, self.evm_clients)
            else:
                # Solana地址
                active_chains = await self.check_solana_transaction_history(address, self.solana_clients)
            
            if active_chains:
                self.active_addr_to_chains[address] = active_chains
                logger.info(f"✅ 地址 {address} 将在 {len(active_chains)} 条链上监控")
            else:
                logger.info(f"❌ 地址 {address} 在所有链上无交易记录，跳过监控")
        
        logger.info(f"📈 总共 {len(self.active_addr_to_chains)} 个地址有交易记录，将进行监控")

    async def send_telegram_message(self, message: str):
        """发送Telegram消息"""
        if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
            return
            
        try:
            async with aiohttp.ClientSession() as session:
                bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
                await bot.send_message(chat_id=config.TELEGRAM_CHAT_ID, text=message)
                logger.info(f"📱 Telegram通知发送成功")
        except Exception as e:
            logger.error(f"❌ Telegram通知失败: {str(e)}")

    async def check_native_balance(self, client: dict, address: str) -> tuple:
        """检查原生代币余额 - 集成缓存管理"""
        try:
            network_name = client["name"]
            cache_key = f"native_balance_{network_name}_{address}"
            
            # 尝试从缓存获取
            if hasattr(self, 'cache_manager'):
                cached_result = self.cache_manager.get(cache_key, max_age=30)  # 30秒缓存
                if cached_result is not None:
                    logger.debug(f"[{network_name}] 使用缓存的余额数据: {address}")
                    return cached_result
            
            w3 = client["w3"]
            balance = w3.eth.get_balance(address)
            balance_readable = Web3.from_wei(balance, 'ether')
            
            logger.info(f"[{client['name']}] 地址 {address}: {client['native_token']} 余额 {balance_readable:.6f}")
            
            result = None, None
            if balance > config.MIN_BALANCE_WEI:
                result = balance, client['native_token']
            
            # 缓存结果
            if hasattr(self, 'cache_manager'):
                self.cache_manager.set(cache_key, result)
            
            return result
            
        except Exception as e:
            logger.error(f"[{client['name']}] 检查地址 {address} 原生代币余额失败: {str(e)}")
            return None, None

    async def check_solana_native_balance(self, client: dict, address: str) -> tuple:
        """检查Solana原生代币余额"""
        try:
            sol_client = client["client"]
            response = await sol_client.get_balance(PublicKey(address))
            
            if response.value is not None:
                balance = response.value
                balance_readable = balance / (10 ** 9)  # Solana有9位小数
                
                logger.info(f"[{client['name']}] Solana地址 {address}: {client['native_token']} 余额 {balance_readable:.6f}")
                
                if balance_readable > config.MIN_SOL_BALANCE:
                    return balance, client['native_token']
                
                return None, None
            else:
                logger.warning(f"[{client['name']}] 无法获取Solana地址 {address} 余额")
                return None, None
                
        except Exception as e:
            logger.error(f"[{client['name']}] 检查Solana地址 {address} 原生代币余额失败: {str(e)}")
            return None, None

    async def check_token_balances(self, client, address: str) -> list:
        """Check ERC-20 token balances for an address"""
        token_balances = []
        network_name = client["name"]
        
        # 1. 全链代币自动发现（通过Alchemy SDK）
        if config.ENABLE_FULL_CHAIN_TOKEN_DISCOVERY and client.get("alchemy"):
            try:
                logger.info(f"[{network_name}] 正在通过Alchemy进行全链代币发现...")
                # Alchemy SDK是同步的，不是异步的
                token_data = client["alchemy"].core.get_token_balances(address)
                
                discovered_tokens = 0
                for token in token_data.get("tokenBalances", []):
                    if discovered_tokens >= config.MAX_TOKENS_PER_CHAIN:
                        logger.info(f"[{network_name}] 已达到最大代币查询数量限制 ({config.MAX_TOKENS_PER_CHAIN})")
                        break
                        
                    balance = int(token["tokenBalance"], 16)
                    if balance > 0:
                        contract_address = token["contractAddress"]
                        try:
                            # Alchemy SDK也是同步的
                            token_metadata = client["alchemy"].core.get_token_metadata(contract_address)
                            symbol = token_metadata.get("symbol", "Unknown")
                            decimals = token_metadata.get("decimals", 18) or 18
                            readable_balance = balance / (10 ** decimals)
                            
                            if readable_balance > config.MIN_TOKEN_BALANCE:
                                # 避免重复
                                if not any(addr == contract_address for _, _, addr, _ in token_balances):
                                    token_balances.append((balance, symbol, contract_address, decimals))
                                    discovered_tokens += 1
                                    logger.info(f"[{network_name}] 发现代币: {symbol} 余额 {readable_balance:.6f} (合约: {contract_address[:10]}...)")
                        except Exception as e:
                            logger.warning(f"[{network_name}] 获取代币 {contract_address} 元数据失败: {str(e)}")
                
                logger.info(f"[{network_name}] 全链发现完成，共发现 {discovered_tokens} 个代币")
                
            except Exception as e:
                logger.warning(f"[{network_name}] Alchemy全链代币查询失败: {str(e)}")
        else:
            logger.info(f"[{network_name}] Alchemy客户端不可用，跳过全链代币发现")
        
        # 2. 手动配置代币检查（备用方案）
        if config.ENABLE_MANUAL_TOKEN_CHECK:
            logger.info(f"[{network_name}] 正在检查手动配置的常见代币...")
            manual_tokens_found = 0
            
            for token_symbol, chain_contracts in ERC20_TOKENS.items():
                contract_address = chain_contracts.get(network_name)
                if contract_address:
                    try:
                        contract_abi = [
                            {"constant": True, "inputs": [{"name": "_owner", "type": "address"}], "name": "balanceOf", "outputs": [{"name": "balance", "type": "uint256"}], "type": "function"},
                            {"constant": True, "inputs": [], "name": "symbol", "outputs": [{"name": "", "type": "string"}], "type": "function"},
                            {"constant": True, "inputs": [], "name": "decimals", "outputs": [{"name": "", "type": "uint256"}], "type": "function"}
                        ]
                        
                        w3 = client["w3"]
                        contract = w3.eth.contract(address=contract_address, abi=contract_abi)
                        balance = contract.functions.balanceOf(address).call()
                        
                        if balance > 0:
                            symbol = contract.functions.symbol().call()
                            decimals = contract.functions.decimals().call() or 18
                            readable_balance = balance / (10 ** decimals)
                            
                            if readable_balance > config.MIN_TOKEN_BALANCE:
                                # 避免重复
                                if not any(addr == contract_address for _, _, addr, _ in token_balances):
                                    token_balances.append((balance, symbol, contract_address, decimals))
                                    manual_tokens_found += 1
                                    logger.info(f"[{network_name}] 手动检查发现代币: {symbol} 余额 {readable_balance:.6f}")
                    
                    except Exception as e:
                        logger.warning(f"[{network_name}] 手动检查代币 {token_symbol} 失败: {str(e)}")
            
            logger.info(f"[{network_name}] 手动代币检查完成，共发现 {manual_tokens_found} 个代币")
        
        # 3. 去重和排序
        unique_tokens = []
        seen_contracts = set()
        
        for balance, symbol, contract_address, decimals in token_balances:
            if contract_address not in seen_contracts:
                unique_tokens.append((balance, symbol, contract_address, decimals))
                seen_contracts.add(contract_address)
        
        logger.info(f"[{network_name}] 地址 {address} 最终发现 {len(unique_tokens)} 个唯一代币")
        return unique_tokens

    async def check_solana_token_balances(self, client: dict, address: str) -> list:
        """检查Solana地址的SPL代币余额 - 修复分页处理问题"""
        token_balances = []
        network_name = client["name"]
        
        if not SOLANA_AVAILABLE:
            logger.warning(f"[{network_name}] Solana支持未安装，跳过代币查询")
            return token_balances
        
        try:
            sol_client = client["client"]
            pubkey = PublicKey(address)
            
            # 使用 get_token_accounts_by_owner 的新方法 - 支持分页
            from solana.rpc.types import TokenAccountOpts
            
            discovered_tokens = 0
            offset = 0
            batch_size = 100  # 每次查询的数量
            max_total_tokens = getattr(config, 'MAX_SOLANA_TOKENS', 50)
            
            while discovered_tokens < max_total_tokens:
                try:
                    # 获取SPL代币账户 - 支持分页
                    response = await sol_client.get_token_accounts_by_owner(
                        pubkey,
                        TokenAccountOpts(program_id=PublicKey("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")),
                        encoding="jsonParsed",
                        # commitment="confirmed"  # 使用确认的数据
                    )
                    
                    if not response.value:
                        logger.debug(f"[{network_name}] 没有发现更多SPL代币账户")
                        break
                    
                    current_batch_count = 0
                    for token_account in response.value[offset:]:
                        if discovered_tokens >= max_total_tokens:
                            logger.info(f"[{network_name}] 已达到最大Solana代币查询数量限制 ({max_total_tokens})")
                            break
                        
                        try:
                            # 使用jsonParsed数据结构 - 更安全可靠
                            parsed_info = token_account.account.data.parsed.info
                            
                            mint_address = parsed_info.mint
                            balance_str = parsed_info.token_amount.amount
                            decimals = parsed_info.token_amount.decimals
                            balance = int(balance_str)
                            
                            if balance > 0:
                                # 尝试获取代币的元数据
                                symbol = f"SPL-{mint_address[:8]}..."
                                
                                # 可选：尝试获取代币符号（需要额外的RPC调用）
                                try:
                                    # 这里可以添加元数据查询逻辑
                                    # 但要注意RPC调用限制
                                    pass
                                except Exception:
                                    pass  # 使用默认符号
                                
                                readable_balance = balance / (10 ** decimals)
                                
                                # 只记录有意义的余额，避免粉尘代币
                                min_balance_threshold = 0.000001
                                if readable_balance >= min_balance_threshold:
                                    token_balances.append((balance, symbol, mint_address, decimals))
                                    discovered_tokens += 1
                                    current_batch_count += 1
                                    
                                    logger.debug(f"[{network_name}] 发现SPL代币: {symbol} "
                                              f"余额: {readable_balance:.6f} "
                                              f"mint: {mint_address}")
                        
                        except Exception as e:
                            logger.warning(f"[{network_name}] 解析代币账户失败: {str(e)}")
                            continue
                    
                    # 如果当前批次没有发现新代币，或者已经处理完所有账户，退出循环
                    if current_batch_count == 0 or len(response.value) <= offset + batch_size:
                        break
                    
                    # 更新偏移量准备下一批查询
                    offset += batch_size
                    
                    # 添加短暂延迟避免RPC限制
                    if discovered_tokens > 0 and discovered_tokens % 20 == 0:
                        await asyncio.sleep(0.1)
                        
                except Exception as e:
                    logger.error(f"[{network_name}] 批量查询SPL代币失败: {str(e)}")
                    break
            
            logger.info(f"[{network_name}] 地址 {address} 发现 {len(token_balances)} 个SPL代币 "
                       f"(查询了{discovered_tokens}个有效代币)")
            
        except Exception as e:
            logger.error(f"[{network_name}] 检查Solana代币余额失败: {str(e)}")
        
        return token_balances

    async def send_transaction(self, client: dict, address: str, private_key: str, 
                             amount: int, token_symbol: str, is_token: bool = False, 
                             contract_address: str = None, decimals: int = 18) -> bool:
        """发送交易 - 修复余额检查竞争条件"""
        # 使用锁确保同一地址的交易操作原子性
        lock_key = f"tx_{address}_{client['name']}"
        if not hasattr(self, '_transaction_locks'):
            self._transaction_locks = {}
        
        if lock_key not in self._transaction_locks:
            self._transaction_locks[lock_key] = asyncio.Lock()
        
        async with self._transaction_locks[lock_key]:
            try:
                w3 = client["w3"]
                
                # 确保使用正确的目标地址
                target_address = config.EVM_TARGET_ADDRESS
                if not Web3.is_address(target_address):
                    logger.error(f"[{client['name']}] 无效的目标地址: {target_address}")
                    return False
                
                # 在锁内获取最新的nonce和余额信息
                try:
                    nonce = w3.eth.get_transaction_count(address, 'pending')  # 使用pending获取最新nonce
                    gas_price = w3.eth.gas_price
                    eth_balance = w3.eth.get_balance(address, 'latest')  # 获取最新余额
                except Exception as e:
                    logger.error(f"[{client['name']}] 获取账户状态失败: {str(e)}")
                    return False
                
                if is_token:
                    # ERC-20转账
                    contract_abi = [
                        {"constant": False, "inputs": [{"name": "_to", "type": "address"}, {"name": "_value", "type": "uint256"}], "name": "transfer", "outputs": [{"name": "", "type": "bool"}], "type": "function"},
                        {"constant": True, "inputs": [{"name": "_owner", "type": "address"}], "name": "balanceOf", "outputs": [{"name": "balance", "type": "uint256"}], "type": "function"}
                    ]
                    contract = w3.eth.contract(address=contract_address, abi=contract_abi)
                    
                    # 原子性验证代币余额（在锁内重新检查）
                    try:
                        current_token_balance = contract.functions.balanceOf(address).call(block_identifier='latest')
                        if current_token_balance < amount:
                            logger.warning(f"[{client['name']}] 代币余额不足: 当前 {current_token_balance}, 需要 {amount}")
                            return False
                        
                        # 双重检查：如果余额刚好等于要发送的金额，可能存在竞争
                        if current_token_balance == amount:
                            logger.info(f"[{client['name']}] 代币余额刚好等于转账金额，进行二次确认")
                            await asyncio.sleep(1)  # 等待1秒
                            recheck_balance = contract.functions.balanceOf(address).call(block_identifier='latest')
                            if recheck_balance < amount:
                                logger.warning(f"[{client['name']}] 二次检查余额不足: {recheck_balance} < {amount}")
                                return False
                    except Exception as e:
                        logger.error(f"[{client['name']}] 验证代币余额失败: {str(e)}")
                        return False
                    
                    # 估算Gas
                    try:
                        gas_limit = contract.functions.transfer(target_address, amount).estimate_gas({'from': address})
                        gas_limit = int(gas_limit * 1.2)  # 增加20%缓冲
                    except Exception as e:
                        logger.warning(f"[{client['name']}] Gas估算失败，使用默认值: {str(e)}")
                        gas_limit = 100000  # 默认值
                    
                    # 检查ETH余额是否足够支付gas费用
                    estimated_gas_cost = gas_limit * gas_price
                    if eth_balance < estimated_gas_cost:
                        logger.warning(f"[{client['name']}] ETH余额不足以支付Gas费用: 需要 {Web3.from_wei(estimated_gas_cost, 'ether'):.6f} ETH")
                        return False
                    
                    # 构建交易
                    tx = contract.functions.transfer(target_address, amount).build_transaction({
                        "chainId": client["chain_id"],
                        "gas": gas_limit,
                        "gasPrice": gas_price,
                        "nonce": nonce
                    })
                    
                    readable_amount = amount / (10 ** decimals)
                    
                else:
                    # 原生代币转账
                    gas_limit = 21000
                    total_gas_cost = gas_limit * gas_price
                    
                    if amount <= total_gas_cost:
                        logger.warning(f"[{client['name']}] 地址 {address} 余额不足以支付Gas费用")
                        return False
                    
                    amount_to_send = amount - total_gas_cost
                    
                    tx = {
                        "to": target_address,
                        "value": amount_to_send,
                        "gas": gas_limit,
                        "gasPrice": gas_price,
                        "nonce": nonce,
                        "chainId": client["chain_id"]
                    }
                    
                    readable_amount = Web3.from_wei(amount_to_send, 'ether')
                
                # 签名并发送交易
                signed_tx = w3.eth.account.sign_transaction(tx, private_key)
                tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
                
                # 发送Telegram通知
                message = (
                    f"🔔 EVM转账完成！\n"
                    f"⛓️ 链: {client['name']}\n"
                    f"📤 发送地址: {address}\n"
                    f"📥 接收地址: {target_address}\n"
                    f"💰 金额: {readable_amount:.6f} {token_symbol}\n"
                    f"⛽ Gas费用: {Web3.from_wei(gas_limit * gas_price, 'ether'):.6f} ETH\n"
                    f"🔗 交易哈希: {tx_hash.hex()}\n"
                    f"⏰ 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                )
                
                await self.send_telegram_message(message)
                logger.info(f"[{client['name']}] 地址 {address} 转账成功: {tx_hash.hex()}")
                return True
                
            except Exception as e:
                logger.error(f"[{client['name']}] 地址 {address} 转账失败: {str(e)}")
                return False

    async def monitor_address_on_chain(self, client: dict, address: str):
        """监控单个地址在特定链上（带安全检查）"""
        if address not in self.addr_to_key:
            return
        
        private_key_info = self.addr_to_key[address]
        private_key = private_key_info["key"] if isinstance(private_key_info, dict) else private_key_info
        
        # 根据地址类型选择监控方法
        if self.addr_type[address] == "evm":
            # EVM地址监控（带安全检查）
            await self.monitor_evm_address_with_safety(client, address, private_key)
        else:
            # Solana地址监控
            await self.monitor_solana_address(client, address, private_key)

    async def monitor_evm_address(self, client: dict, address: str, private_key: str):
        """监控EVM地址"""
        # 检查原生代币余额（使用重试机制）
        native_balance, native_symbol = await self.check_native_balance_with_retry(client, address)
        if native_balance:
            balance_readable = Web3.from_wei(native_balance, 'ether')
            message = (f"💰 发现余额!\n"
                      f"链: {client['name']}\n"
                      f"地址: {address}\n"
                      f"代币: {native_symbol}\n"
                      f"余额: {balance_readable:.6f}\n"
                      f"私钥: 0x{private_key}")
            await self.send_telegram_message(message)
            
            # 发送转账
            await self.send_transaction(client, address, private_key, native_balance, native_symbol)
        
        # 检查ERC-20代币余额（使用重试机制）
        token_balances = await self.check_token_balances_with_retry(client, address)
        for balance, symbol, contract_address, decimals in token_balances:
            readable_balance = balance / (10 ** decimals)
            message = (f"💰 发现代币余额!\n"
                      f"链: {client['name']}\n"
                      f"地址: {address}\n"
                      f"代币: {symbol}\n"
                      f"余额: {readable_balance:.6f}\n"
                      f"私钥: 0x{private_key}")
            await self.send_telegram_message(message)
            
            # 发送转账
            await self.send_transaction(client, address, private_key, balance, symbol, 
                                      is_token=True, contract_address=contract_address, decimals=decimals)

    async def send_solana_transaction(self, client: dict, address: str, private_key: str, 
                                    amount: int, token_symbol: str, is_token: bool = False, 
                                    mint_address: str = None, decimals: int = 9) -> bool:
        """发送Solana交易"""
        if not SOLANA_AVAILABLE:
            logger.error("Solana库未安装，无法发送交易")
            return False
            
        try:
            sol_client = client["client"]
            
            # 验证目标地址
            target_address = config.SOLANA_TARGET_ADDRESS
            try:
                PublicKey(target_address)  # 验证地址格式
            except Exception:
                logger.error(f"[{client['name']}] 无效的Solana目标地址: {target_address}")
                return False
            
            # 生成Keypair
            try:
                if len(private_key) == 64:
                    # 十六进制格式
                    key_bytes = bytes.fromhex(private_key)
                elif len(private_key) >= 87 and len(private_key) <= 88:
                    # base58格式
                    key_bytes = base58.b58decode(private_key)
                else:
                    # base64格式
                    key_bytes = base64.b64decode(private_key)
                
                if len(key_bytes) != 64:
                    logger.error(f"[{client['name']}] 私钥长度不正确: {len(key_bytes)} bytes")
                    return False
                
                keypair = Keypair.from_secret_key(key_bytes)
            except Exception as e:
                logger.error(f"[{client['name']}] 私钥解析失败: {str(e)}")
                return False
            
            # 获取最新区块哈希
            try:
                recent_blockhash_response = await sol_client.get_latest_blockhash()
                recent_blockhash = recent_blockhash_response.value.blockhash
            except Exception as e:
                logger.error(f"[{client['name']}] 获取区块哈希失败: {str(e)}")
                return False
            
            if is_token and SPL_TOKEN_AVAILABLE:
                # SPL代币转账
                logger.info(f"[{client['name']}] 准备转账SPL代币 {token_symbol}")
                
                try:
                    # 验证mint地址
                    mint_pubkey = PublicKey(mint_address)
                    
                    # 获取发送方代币账户
                    sender_token_accounts = await sol_client.get_token_accounts_by_owner(
                        keypair.public_key,
                        TokenAccountOpts(mint=mint_pubkey)
                    )
                    
                    if not sender_token_accounts.value:
                        logger.error(f"[{client['name']}] 发送方没有代币账户: {mint_address}")
                        return False
                    
                    sender_token_account = PublicKey(sender_token_accounts.value[0].pubkey)
                    
                    # 验证代币余额
                    sender_account_info = await sol_client.get_account_info(sender_token_account)
                    if sender_account_info.value and sender_account_info.value.data:
                        account_data = sender_account_info.value.data
                        if len(account_data) >= 72:
                            balance_bytes = account_data[64:72]
                            current_balance = int.from_bytes(balance_bytes, 'little')
                            if current_balance < amount:
                                logger.warning(f"[{client['name']}] SPL代币余额不足: 当前 {current_balance}, 需要 {amount}")
                                return False
                        else:
                            logger.error(f"[{client['name']}] 无法解析代币账户数据")
                            return False
                    else:
                        logger.error(f"[{client['name']}] 无法获取代币账户信息")
                        return False
                    
                    # 获取接收方代币账户
                    receiver_pubkey = PublicKey(target_address)
                    
                    # 获取或创建接收方关联代币账户
                    from spl.token.instructions import get_associated_token_address
                    receiver_token_account = get_associated_token_address(
                        receiver_pubkey, mint_pubkey
                    )
                    
                    # 检查接收方代币账户是否存在
                    receiver_account_info = await sol_client.get_account_info(receiver_token_account)
                    
                    transaction = Transaction()
                    
                    # 如果接收方代币账户不存在，需要先创建
                    if not receiver_account_info.value:
                        from spl.token.instructions import create_associated_token_account
                        create_account_ix = create_associated_token_account(
                            payer=keypair.public_key,
                            owner=receiver_pubkey,
                            mint=mint_pubkey
                        )
                        transaction.add(create_account_ix)
                        logger.info(f"[{client['name']}] 将创建接收方关联代币账户")
                    
                    # 创建转账指令
                    transfer_ix = transfer_checked(
                        TransferCheckedParams(
                            program_id=TOKEN_PROGRAM_ID,
                            source=sender_token_account,
                            mint=mint_pubkey,
                            dest=receiver_token_account,
                            owner=keypair.public_key,
                            amount=amount,
                            decimals=decimals
                        )
                    )
                    
                    transaction.add(transfer_ix)
                    transaction.recent_blockhash = recent_blockhash
                    transaction.fee_payer = keypair.public_key
                    
                    # 签名交易
                    transaction.sign(keypair)
                    
                    # 发送交易
                    opts = TxOpts(skip_confirmation=False, preflight_commitment=Commitment("confirmed"))
                    result = await sol_client.send_transaction(transaction, keypair, opts=opts)
                    
                    if result.value:
                        tx_signature = str(result.value)
                        readable_amount = amount / (10 ** decimals)
                        
                        # 计算手续费（估算）
                        sol_fee = 0.00025  # Solana典型手续费
                        
                        message = (
                            f"🔔 Solana SPL代币转账完成！\n"
                            f"⛓️ 网络: {client['name']}\n"
                            f"📤 发送地址: {address[:8]}...{address[-8:]}\n"
                            f"📥 接收地址: {target_address[:8]}...{target_address[-8:]}\n"
                            f"🪙 代币: {token_symbol}\n"
                            f"💰 金额: {readable_amount:.6f}\n"
                            f"🏠 合约: {mint_address[:8]}...{mint_address[-8:]}\n"
                            f"💸 手续费: {sol_fee:.6f} SOL\n"
                            f"🔗 交易签名: {tx_signature}\n"
                            f"⏰ 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                        )
                        
                        await self.send_telegram_message(message)
                        logger.info(f"[{client['name']}] Solana SPL代币转账成功: {tx_signature}")
                        return True
                    else:
                        logger.error(f"[{client['name']}] Solana SPL代币转账失败：无返回值")
                        return False
                        
                except Exception as e:
                    logger.error(f"[{client['name']}] SPL代币转账失败: {str(e)}")
                    return False
                    
            else:
                # 原生SOL转账
                # 预留一些SOL作为交易费用（约0.000005 SOL）
                tx_fee = 5000  # lamports
                
                if amount <= tx_fee:
                    logger.warning(f"[{client['name']}] 地址 {address} 余额不足以支付交易费用")
                    return False
                
                amount_to_send = amount - tx_fee
                readable_amount = amount_to_send / (10 ** 9)
                
                # 创建转账指令
                transfer_instruction = transfer(
                    TransferParams(
                        from_pubkey=keypair.public_key,
                        to_pubkey=PublicKey(target_address),
                        lamports=amount_to_send
                    )
                )
                
                # 创建交易
                transaction = Transaction()
                transaction.add(transfer_instruction)
                transaction.recent_blockhash = recent_blockhash
                transaction.fee_payer = keypair.public_key
                
                # 签名交易
                transaction.sign(keypair)
                
                # 发送交易
                opts = TxOpts(skip_confirmation=False, preflight_commitment=Commitment("confirmed"))
                result = await sol_client.send_transaction(transaction, keypair, opts=opts)
                
                if result.value:
                    tx_signature = str(result.value)
                    readable_amount = amount_to_send / (10 ** 9)
                    
                    # 计算手续费（估算）
                    sol_fee = 0.00025  # Solana典型手续费
                    
                    message = (
                        f"🔔 Solana转账完成！\n"
                        f"⛓️ 网络: {client['name']}\n"
                        f"📤 发送地址: {address[:8]}...{address[-8:]}\n"
                        f"📥 接收地址: {target_address[:8]}...{target_address[-8:]}\n"
                        f"🪙 代币: {token_symbol}\n"
                        f"💰 金额: {readable_amount:.6f}\n"
                        f"🏠 合约: {target_address[:8]}...{target_address[-8:]}\n"
                        f"💸 手续费: {sol_fee:.6f} SOL\n"
                        f"🔗 交易签名: {tx_signature}\n"
                        f"⏰ 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    )
                    
                    await self.send_telegram_message(message)
                    logger.info(f"[{client['name']}] Solana地址 {address} 转账成功: {tx_signature}")
                    return True
                else:
                    logger.error(f"[{client['name']}] Solana转账失败：无返回值")
                    return False
                    
        except Exception as e:
            logger.error(f"[{client['name']}] Solana地址 {address} 转账失败: {str(e)}")
            return False

    async def monitor_solana_address(self, client: dict, address: str, private_key: str):
        """监控Solana地址"""
        # 检查原生代币余额（使用重试机制）
        native_balance, native_symbol = await self.check_native_balance_with_retry(client, address)
        if native_balance:
            balance_readable = native_balance / (10 ** 9)  # Solana有9位小数
            message = (f"💰 发现Solana余额!\n"
                      f"链: {client['name']}\n"
                      f"地址: {address}\n"
                      f"代币: {native_symbol}\n"
                      f"余额: {balance_readable:.6f}\n"
                      f"私钥: {private_key}")
            await self.send_telegram_message(message)
            
            # 发送Solana转账
            await self.send_solana_transaction(client, address, private_key, native_balance, native_symbol)
        
        # 检查SPL代币余额（使用重试机制）
        token_balances = await self.check_token_balances_with_retry(client, address)
        for balance, symbol, mint_address, decimals in token_balances:
            readable_balance = balance / (10 ** decimals)
            message = (f"💰 发现Solana代币余额!\n"
                      f"链: {client['name']}\n"
                      f"地址: {address}\n"
                      f"代币: {symbol}\n"
                      f"余额: {readable_balance:.6f}\n"
                      f"私钥: {private_key}")
            await self.send_telegram_message(message)
            
            # 发送SPL代币转账
            await self.send_solana_transaction(client, address, private_key, balance, symbol, 
                                             is_token=True, mint_address=mint_address, decimals=decimals)

    def save_state(self):
        """保存状态 - 修复私钥编码安全漏洞"""
        try:
            # 生成加密密钥
            fernet = generate_fernet_key(config.FERNET_PASSWORD)
            
            # 安全地处理私钥加密
            encrypted_keys = []
            key_types = []
            
            for key_item in self.private_keys:
                try:
                    # 统一处理不同格式的私钥数据
                    if isinstance(key_item, dict):
                        # 字典格式: {"key": "...", "type": "..."}
                        if "key" not in key_item:
                            logger.error(f"私钥字典缺少'key'字段: {key_item}")
                            continue
                        
                        key_str = key_item["key"]
                        key_type = key_item.get("type", "evm")
                        
                    elif isinstance(key_item, str):
                        # 字符串格式
                        key_str = key_item
                        key_type = "evm"  # 默认类型
                        
                    else:
                        logger.error(f"不支持的私钥格式: {type(key_item)}")
                        continue
                    
                    # 验证私钥字符串
                    if not isinstance(key_str, str):
                        logger.error(f"私钥不是字符串格式: {type(key_str)}")
                        continue
                    
                    if not key_str.strip():
                        logger.error("发现空的私钥")
                        continue
                    
                    # 加密私钥
                    encrypted_key = fernet.encrypt(key_str.encode('utf-8')).decode('utf-8')
                    encrypted_keys.append(encrypted_key)
                    key_types.append(key_type)
                    
                except Exception as e:
                    logger.error(f"处理私钥失败: {str(e)}, 私钥项: {type(key_item)}")
                    continue
            
            # 构建状态数据
            state = {
                "private_keys": encrypted_keys,
                "private_key_types": key_types,
                "active_addr_to_chains": {
                    addr: [
                        {
                            "chain_id": client.get("chain_id", client["name"]),
                            "name": client["name"],
                            "chain_type": "evm" if "chain_id" in client else "solana"
                        }
                        for client in chains
                    ]
                    for addr, chains in self.active_addr_to_chains.items()
                },
                "timestamp": time.time(),
                "version": "2.1"  # 更新版本号表示修复了安全漏洞
            }
            
            # 原子性写入文件
            temp_file = config.STATE_FILE + ".tmp"
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
            
            # 原子性移动文件
            import os
            if os.path.exists(config.STATE_FILE):
                backup_file = config.STATE_FILE + ".backup"
                if os.path.exists(backup_file):
                    os.remove(backup_file)
                os.rename(config.STATE_FILE, backup_file)
            
            os.rename(temp_file, config.STATE_FILE)
            
            logger.info(f"💾 状态已安全保存到 {config.STATE_FILE} (加密{len(encrypted_keys)}个私钥)")
            
        except Exception as e:
            logger.error(f"❌ 保存状态失败: {str(e)}")
            # 清理临时文件
            temp_file = config.STATE_FILE + ".tmp"
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except:
                    pass

    def load_state(self) -> bool:
        """加载监控状态 - 增强版本兼容性"""
        try:
            logger.info(f"📂 正在从 {config.STATE_FILE} 加载状态...")
            
            with open(config.STATE_FILE, 'r') as f:
                state = json.load(f)
            
            # 版本兼容性检查和迁移
            state_version = state.get("version", "1.0")
            logger.info(f"📋 检测到状态文件版本: {state_version}")
            
            # 迁移不同版本的状态格式
            if state_version == "1.0":
                logger.info("🔄 正在从v1.0迁移状态格式...")
                # v1.0 没有版本字段，active_addr_to_chains 存储的是链名称字符串
                state = self._migrate_from_v1_0(state)
            elif state_version == "2.0":
                logger.info("✅ 状态文件版本2.0，无需迁移")
            else:
                logger.warning(f"⚠️ 未知状态版本 {state_version}，尝试按最新格式解析")
            
            # 解密私钥
            encrypted_keys = state["private_keys"]
            fernet = generate_fernet_key(config.FERNET_PASSWORD)
            
            self.private_keys = []
            for encrypted_key in encrypted_keys:
                try:
                    decrypted_key = fernet.decrypt(encrypted_key.encode()).decode()
                    key_info = json.loads(decrypted_key)
                    self.private_keys.append(key_info)
                except Exception as e:
                    logger.error(f"❌ 解密私钥失败: {str(e)}")
                    continue
            
            if not self.private_keys:
                logger.error("❌ 没有成功解密的私钥")
                return False
            
            # 重建地址映射
            self.addresses = []
            self.addr_to_key = {}
            self.addr_type = {}
            
            for key_info in self.private_keys:
                try:
                    if key_info["type"] == "evm":
                        if ETH_ACCOUNT_AVAILABLE:
                            address = Account.from_key(key_info["key"]).address
                        else:
                            logger.warning("eth_account库不可用，无法处理EVM私钥")
                            continue
                    else:
                        address = generate_solana_address_from_private_key(key_info["key"])
                        if not address:
                            logger.warning(f"⚠️ 无法生成Solana地址，跳过私钥")
                            continue
                    
                    self.addresses.append(address)
                    self.addr_to_key[address] = key_info
                    self.addr_type[address] = key_info["type"]
                except Exception as e:
                    logger.error(f"❌ 处理私钥失败: {str(e)}")
                    continue
            
            # 重建活跃地址到链的映射
            self.active_addr_to_chains = {}
            
            if "active_addr_to_chains" in state:
                chain_mapping_success = self._rebuild_chain_mapping(state["active_addr_to_chains"])
                if not chain_mapping_success:
                    logger.warning("⚠️ 链映射重建部分失败，但将继续运行")
            
            success_count = len(self.active_addr_to_chains)
            total_count = len(state.get("active_addr_to_chains", {}))
            
            logger.info(f"✅ 状态加载完成: {success_count}/{total_count} 个地址映射成功")
            logger.info(f"📊 加载了 {len(self.private_keys)} 个私钥，{len(self.addresses)} 个地址")
            
            # 保存迁移后的状态（如果有迁移）
            if state_version != "2.0":
                logger.info("💾 保存迁移后的状态...")
                self.save_state()
            
            return True
            
        except FileNotFoundError:
            logger.info(f"📂 {config.STATE_FILE} 不存在，将创建新状态")
            return False
        except json.JSONDecodeError as e:
            logger.error(f"❌ 状态文件JSON格式错误: {str(e)}")
            # 备份损坏的文件
            backup_file = f"{config.STATE_FILE}.corrupted.{int(time.time())}"
            try:
                import shutil
                shutil.copy2(config.STATE_FILE, backup_file)
                logger.info(f"💾 已备份损坏的状态文件到: {backup_file}")
            except Exception:
                pass
            return False
        except Exception as e:
            logger.error(f"❌ 加载状态失败: {str(e)}")
            return False
    
    def _migrate_from_v1_0(self, state: dict) -> dict:
        """从v1.0格式迁移状态"""
        logger.info("🔄 执行v1.0到v2.0状态迁移...")
        
        # 更新版本号
        state["version"] = "2.0"
        
        # 迁移 active_addr_to_chains 格式
        if "active_addr_to_chains" in state:
            old_mapping = state["active_addr_to_chains"]
            new_mapping = {}
            
            for addr, chain_names in old_mapping.items():
                new_chains = []
                
                if isinstance(chain_names, list):
                    for chain_name in chain_names:
                        if isinstance(chain_name, str):
                            # 尝试推断链类型和ID
                            chain_info = self._guess_chain_info(chain_name)
                            new_chains.append(chain_info)
                        else:
                            # 已经是新格式
                            new_chains.append(chain_name)
                
                new_mapping[addr] = new_chains
            
            state["active_addr_to_chains"] = new_mapping
        
        logger.info("✅ v1.0到v2.0迁移完成")
        return state
    
    def _guess_chain_info(self, chain_name: str) -> dict:
        """推断链信息（用于迁移）"""
        # 常见EVM链的映射
        evm_chain_ids = {
            "Ethereum": 1,
            "Polygon": 137,
            "Arbitrum One": 42161,
            "Optimism": 10,
            "Base": 8453,
            "BSC": 56,
            "Avalanche": 43114
        }
        
        if chain_name in evm_chain_ids:
            return {
                "chain_id": evm_chain_ids[chain_name],
                "name": chain_name,
                "chain_type": "evm"
            }
        elif "solana" in chain_name.lower() or "sol" in chain_name.lower():
            return {
                "name": chain_name,
                "chain_type": "solana"
            }
        else:
            # 默认当作EVM链
            return {
                "name": chain_name,
                "chain_type": "evm"
            }
    
    def _rebuild_chain_mapping(self, saved_mapping: dict) -> bool:
        """重建链映射"""
        try:
            # 创建链查找映射
            evm_chain_lookup = {}
            for client in getattr(self, 'evm_clients', []):
                evm_chain_lookup[client["chain_id"]] = client
                evm_chain_lookup[client["name"]] = client
            
            solana_chain_lookup = {}
            for client in getattr(self, 'solana_clients', []):
                solana_chain_lookup[client["name"]] = client
            
            success_count = 0
            
            for addr, chain_info_list in saved_mapping.items():
                chains = []
                
                for chain_info in chain_info_list:
                    client = None
                    
                    if isinstance(chain_info, str):
                        # 兼容旧格式（仅链名称）
                        chain_name = chain_info
                        client = evm_chain_lookup.get(chain_name) or solana_chain_lookup.get(chain_name)
                    else:
                        # 新格式（包含详细信息）
                        chain_type = chain_info.get("chain_type", "evm")
                        
                        if chain_type == "evm":
                            chain_id = chain_info.get("chain_id")
                            chain_name = chain_info.get("name")
                            client = evm_chain_lookup.get(chain_id) or evm_chain_lookup.get(chain_name)
                        else:
                            chain_name = chain_info.get("name")
                            client = solana_chain_lookup.get(chain_name)
                    
                    if client:
                        chains.append(client)
                    else:
                        logger.warning(f"⚠️ 找不到链配置: {chain_info}")
                
                if chains:
                    self.active_addr_to_chains[addr] = chains
                    success_count += 1
            
            logger.info(f"🔗 重建链映射: {success_count}/{len(saved_mapping)} 个地址成功")
            return success_count > 0
            
        except Exception as e:
            logger.error(f"❌ 重建链映射失败: {str(e)}")
            return False

    async def run_monitoring_round(self):
        """运行一轮监控"""
        logger.info("🔄 开始新一轮余额检查")
        
        tasks = []
        for address, chains in self.active_addr_to_chains.items():
            for client in chains:
                task = self.monitor_address_on_chain(client, address)
                tasks.append(task)
        
        # 并发执行所有监控任务
        await asyncio.gather(*tasks, return_exceptions=True)
        
        logger.info("✅ 完成一轮检查")

    async def start_monitoring(self):
        """开始监控"""
        logger.info("🚀 钱包监控开始运行")
        self.monitoring_active = True
        
        try:
            while self.monitoring_active:
                await self.run_monitoring_round()
                self.save_state()
                logger.info(f"😴 休眠 {config.SLEEP_INTERVAL} 秒")
                await asyncio.sleep(config.SLEEP_INTERVAL)
                
        except KeyboardInterrupt:
            logger.info("⏹️ 用户停止监控")
            self.monitoring_active = False
            self.save_state()
        except Exception as e:
            logger.error(f"❌ 监控异常: {str(e)}")
            self.monitoring_active = False
            self.save_state()
            raise

    async def pre_check_address(self, address: str) -> dict:
        """
        预检查地址在每条链上的状态
        返回: {chain_name: {"has_history": bool, "has_balance": bool, "tx_count": int, "balance": float}}
        """
        logger.info(f"🔍 预检查地址: {address}")
        results = {}
        
        # 检查EVM链
        for client in self.evm_clients:
            try:
                chain_name = client["name"]
                logger.info(f"  检查 {chain_name}...")
                
                # 检查交易记录
                tx_count = 0
                try:
                    tx_count = client["w3"].eth.get_transaction_count(address)
                except Exception as e:
                    logger.debug(f"    获取 {chain_name} 交易数量失败: {str(e)}")
                
                # 检查余额
                balance = 0
                try:
                    balance_wei = client["w3"].eth.get_balance(address)
                    balance = Web3.from_wei(balance_wei, 'ether')
                except Exception as e:
                    logger.debug(f"    获取 {chain_name} 余额失败: {str(e)}")
                
                # 判断是否有活动 - 修复预检查逻辑
                has_history = tx_count > getattr(config, 'MIN_TRANSACTION_COUNT', 0)
                has_balance = balance > getattr(config, 'MIN_BALANCE_THRESHOLD', 0.001)
                
                # 增强检查：检查代币余额
                has_token_balance = False
                try:
                    token_balances = await self.check_token_balances(client, address)
                    has_token_balance = len(token_balances) > 0
                except Exception as e:
                    logger.debug(f"    {chain_name} 代币余额检查失败: {str(e)}")
                
                # 任何一种余额存在就认为地址活跃
                is_active = has_history or has_balance or has_token_balance
                
                results[chain_name] = {
                    "has_history": has_history,
                    "has_balance": has_balance,
                    "has_token_balance": has_token_balance,
                    "is_active": is_active,
                    "tx_count": tx_count,
                    "balance": float(balance),
                    "chain_type": "evm"
                }
                
                status = "✅" if is_active else "❌"
                activity_detail = []
                if has_history:
                    activity_detail.append(f"交易{tx_count}")
                if has_balance:
                    activity_detail.append(f"原生{balance:.6f}")
                if has_token_balance:
                    activity_detail.append(f"代币{len(token_balances)}")
                
                detail_str = ", ".join(activity_detail) if activity_detail else "无活动"
                logger.info(f"    {status} {chain_name}: {detail_str}")
                
            except Exception as e:
                logger.error(f"    检查 {chain_name} 失败: {str(e)}")
                results[chain_name] = {
                    "has_history": False,
                    "has_balance": False,
                    "tx_count": 0,
                    "balance": 0,
                    "chain_type": "evm",
                    "error": str(e)
                }
        
        # 检查Solana链
        if hasattr(self, 'solana_clients') and self.solana_clients:
            for client in self.solana_clients:
                try:
                    chain_name = client["name"]
                    logger.info(f"  检查 {chain_name}...")
                    
                    # 检查交易记录
                    tx_count = 0
                    try:
                        # 获取最近的交易签名
                        signatures = await client["client"].get_signatures_for_address(
                            PublicKey(address),
                            limit=1
                        )
                        tx_count = len(signatures.value) if signatures.value else 0
                    except Exception as e:
                        logger.debug(f"    获取 {chain_name} 交易数量失败: {str(e)}")
                    
                    # 检查余额
                    balance = 0
                    try:
                        balance_response = await client["client"].get_balance(PublicKey(address))
                        if balance_response.value is not None:
                            balance = balance_response.value / 10**9  # 转换为SOL
                    except Exception as e:
                        logger.debug(f"    获取 {chain_name} 余额失败: {str(e)}")
                    
                    # 判断是否有活动
                    has_history = tx_count > config.MIN_TRANSACTION_COUNT
                    has_balance = balance > config.MIN_BALANCE_THRESHOLD
                    
                    results[chain_name] = {
                        "has_history": has_history,
                        "has_balance": has_balance,
                        "tx_count": tx_count,
                        "balance": float(balance),
                        "chain_type": "solana"
                    }
                    
                    status = "✅" if (has_history or has_balance) else "❌"
                    logger.info(f"    {status} {chain_name}: 交易数={tx_count}, 余额={balance:.6f}")
                    
                except Exception as e:
                    logger.error(f"    检查 {chain_name} 失败: {str(e)}")
                    results[chain_name] = {
                        "has_history": False,
                        "has_balance": False,
                        "tx_count": 0,
                        "balance": 0,
                        "chain_type": "solana",
                        "error": str(e)
                    }
        
        # 统计结果
        active_chains = [name for name, data in results.items() 
                        if data["has_history"] or data["has_balance"]]
        
        logger.info(f"📊 预检查完成: {address}")
        logger.info(f"   活跃链数: {len(active_chains)}/{len(results)}")
        logger.info(f"   活跃链: {', '.join(active_chains) if active_chains else '无'}")
        
        return results

    def print_banner(self):
        """打印美化的横幅"""
        banner = f"""
{Fore.CYAN}{Style.BRIGHT}
╔══════════════════════════════════════════════════════════════════════════════╗
║  🚀 钱包监控系统 v2.0 - 全链自动监控 & 智能转账                                   ║
║  💎 EVM + Solana 全生态支持 | 🛡️ 多重安全保护 | ⚡ 实时余额监控                     ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  🌟 特色功能:                                                                 ║
║  • 🔍 50+ EVM链自动发现    • ☀️ Solana SPL代币支持                              ║
║  • 🛡️ 智能安全验证        • 🔄 自动RPC故障转移                                   ║
║  • 📱 Telegram实时通知     • 💾 加密状态存储                                    ║
║  • 🎨 彩色终端界面         • 📊 详细监控统计                                     ║
╚══════════════════════════════════════════════════════════════════════════════╝
{Style.RESET_ALL}"""
        print(banner)
        
        # 显示系统状态概览
        print(f"\n{Fore.WHITE}{Back.BLUE} 📊 系统状态概览 {Style.RESET_ALL}")
        
        # 监控状态
        if hasattr(self, 'monitoring_active') and self.monitoring_active:
            status = f"{Fore.GREEN}🟢 监控运行中{Style.RESET_ALL}"
        else:
            status = f"{Fore.RED}🔴 监控已停止{Style.RESET_ALL}"
        
        # RPC状态
        rpc_mode = "🔄 公共RPC" if getattr(self, 'use_public_rpc', False) else "⚡ Alchemy"
        rpc_color = Fore.YELLOW if getattr(self, 'use_public_rpc', False) else Fore.GREEN
        
        # 地址统计
        total_addresses = len(getattr(self, 'addresses', []))
        active_addresses = len(getattr(self, 'active_addr_to_chains', {}))
        
        # 链连接统计
        evm_chains = len(getattr(self, 'evm_clients', []))
        solana_chains = len(getattr(self, 'solana_clients', []))
        
        print(f"┌─ 🔧 运行状态: {status}")
        print(f"├─ 🌐 RPC模式: {rpc_color}{rpc_mode}{Style.RESET_ALL}")
        print(f"├─ 👛 监控地址: {Fore.CYAN}{active_addresses}/{total_addresses}{Style.RESET_ALL} 个")
        print(f"├─ ⛓️  EVM链: {Fore.BLUE}{evm_chains}{Style.RESET_ALL} 条")
        print(f"└─ ☀️  Solana链: {Fore.MAGENTA}{solana_chains}{Style.RESET_ALL} 条")
    
    def manual_initialize_system(self):
        """手动初始化系统"""
        if is_interactive() or is_force_interactive():
            print("\033[2J\033[H")
        print(f"\n{Fore.WHITE}{Back.BLUE} 🚀 系统手动初始化 {Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*90}{Style.RESET_ALL}")
        
        # 检查是否已经初始化
        if self.evm_clients or self.solana_clients:
            print(f"\n{Fore.YELLOW}⚠️ 系统已部分初始化{Style.RESET_ALL}")
            print(f"   EVM链客户端: {len(self.evm_clients)} 个")
            print(f"   Solana客户端: {len(self.solana_clients)} 个")
            
            reinit = safe_input(f"\n{Fore.YELLOW}是否重新初始化? (y/N): {Style.RESET_ALL}", "n", allow_empty=True).lower()
            if reinit != 'y':
                safe_input(f"\n{Fore.YELLOW}💡 按回车键返回主菜单...{Style.RESET_ALL}", "")
                return
            
            # 清空现有客户端
            self.evm_clients = []
            self.solana_clients = []
        
        print(f"\n{Fore.YELLOW}📋 开始系统初始化...{Style.RESET_ALL}")
        
        # 初始化EVM链客户端
        print(f"\n{Fore.CYAN}🔗 正在初始化EVM链客户端...{Style.RESET_ALL}")
        evm_success = self.initialize_evm_clients()
        
        if evm_success:
            print(f"{Fore.GREEN}✅ EVM链初始化成功 - 连接了 {len(self.evm_clients)} 条链{Style.RESET_ALL}")
        else:
            print(f"{Fore.RED}❌ EVM链初始化失败{Style.RESET_ALL}")
            safe_input(f"\n{Fore.YELLOW}💡 按回车键返回主菜单...{Style.RESET_ALL}", "")
            return
        
        # 初始化Solana客户端
        print(f"\n{Fore.CYAN}☀️ 正在初始化Solana客户端...{Style.RESET_ALL}")
        solana_success = self.initialize_solana_clients()
        
        if solana_success:
            print(f"{Fore.GREEN}✅ Solana初始化成功 - 连接了 {len(self.solana_clients)} 个节点{Style.RESET_ALL}")
        else:
            print(f"{Fore.YELLOW}⚠️ Solana初始化部分成功或失败，将只支持EVM链{Style.RESET_ALL}")
        
        # 显示初始化结果
        print(f"\n{Fore.GREEN}🎉 系统初始化完成！{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*90}{Style.RESET_ALL}")
        print(f"\n{Fore.WHITE}{Style.BRIGHT}📊 初始化结果：{Style.RESET_ALL}")
        print(f"   🔗 EVM链连接: {Fore.BLUE}{len(self.evm_clients)}{Style.RESET_ALL} 条")
        print(f"   ☀️ Solana连接: {Fore.MAGENTA}{len(self.solana_clients)}{Style.RESET_ALL} 个")
        print(f"   🌍 总连接数: {Fore.CYAN}{len(self.evm_clients) + len(self.solana_clients)}{Style.RESET_ALL}")
        
        # 检查是否有保存的状态
        print(f"\n{Fore.YELLOW}📂 检查保存的配置...{Style.RESET_ALL}")
        if self.load_state():
            print(f"{Fore.GREEN}✅ 已加载保存的地址配置 - {len(self.addresses)} 个地址{Style.RESET_ALL}")
        else:
            print(f"{Fore.CYAN}💡 未找到保存的配置，可以在地址管理中添加新地址{Style.RESET_ALL}")
        
        safe_input(f"\n{Fore.YELLOW}💡 按回车键返回主菜单...{Style.RESET_ALL}", "")

    def show_control_menu(self):
        """重写的简化菜单系统 - 更健壮的实现"""
        import time
        
        print(f"\n{Fore.GREEN}🎉 欢迎使用钱包监控系统控制中心！{Style.RESET_ALL}")
        
        # 纯交互模式：不支持非交互/守护/演示模式
        if not (is_force_interactive() or is_interactive()):
            print(f"{Fore.RED}❌ 未检测到交互式终端。请使用：python wallet_monitor.py --force-interactive{Style.RESET_ALL}")
            return
        
        # 主菜单循环（纯交互）
        while True:
            try:
                self._display_simple_menu()
                choice = self._get_safe_choice()
                if not self._execute_menu_choice(choice):
                    break
            except KeyboardInterrupt:
                print(f"\n{Fore.YELLOW}⏹️ 程序被用户中断{Style.RESET_ALL}")
                break
            except Exception as e:
                print(f"\n{Fore.RED}❌ 菜单系统错误: {str(e)}{Style.RESET_ALL}")
                time.sleep(2)
    
    # 守护模式已移除（纯交互模式）
    
    def _display_simple_menu(self):
        """显示简化菜单"""
        # 仅在真实交互环境下清屏
        if is_interactive() or is_force_interactive():
            print("\033[2J\033[H")
        self.print_banner()
        
        print(f"\n{Fore.WHITE}{Back.MAGENTA} 🎛️  钱包监控控制中心 {Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*70}{Style.RESET_ALL}")
        
        # 系统状态简要显示
        evm_count = len(getattr(self, 'evm_clients', []))
        solana_count = len(getattr(self, 'solana_clients', []))
        addr_count = len(getattr(self, 'addresses', []))
        
        init_status = "已初始化" if (evm_count > 0) else "未初始化"
        status_color = Fore.GREEN if (evm_count > 0) else Fore.RED
        
        print(f"\n{Fore.CYAN}📊 状态: {status_color}{init_status}{Style.RESET_ALL} | "
              f"EVM:{Fore.BLUE}{evm_count}{Style.RESET_ALL} | "
              f"Solana:{Fore.MAGENTA}{solana_count}{Style.RESET_ALL} | "
              f"地址:{Fore.YELLOW}{addr_count}{Style.RESET_ALL}")
        
        print(f"\n{Fore.YELLOW}📋 主要功能{Style.RESET_ALL}")
        print(f"  {Fore.RED}1.{Style.RESET_ALL} 🚀 初始化系统     {Fore.GREEN}2.{Style.RESET_ALL} 📊 系统状态")
        print(f"  {Fore.GREEN}3.{Style.RESET_ALL} 🎮 监控控制     {Fore.BLUE}4.{Style.RESET_ALL} 👛 地址管理")
        print(f"  {Fore.MAGENTA}5.{Style.RESET_ALL} ⚙️ 系统设置     {Fore.RED}6.{Style.RESET_ALL} ❌ 退出程序")
        
        print(f"\n{Fore.CYAN}{'='*70}{Style.RESET_ALL}")
    
    def _get_safe_choice(self):
        """安全获取用户选择"""
        import sys
        
        # 纯交互输入
        try:
            # 优先走标准输入
            if sys.stdin and hasattr(sys.stdin, 'readline'):
                print(f"{Fore.YELLOW}👉 请选择 (1-6): {Style.RESET_ALL}", end="", flush=True)
                line = sys.stdin.readline()
                if not line:
                    # 退回到内置input（已适配tty）
                    line = input(f"{Fore.YELLOW}👉 请选择 (1-6): {Style.RESET_ALL}")
                choice = (line or '').strip()
                return choice if choice else "2"
            # 回退到input（已适配tty）
            choice = input(f"{Fore.YELLOW}👉 请选择 (1-6): {Style.RESET_ALL}").strip()
            return choice if choice else "2"
        except (EOFError, KeyboardInterrupt):
            return "2"
        except Exception:
            return "2"
    
    def _execute_menu_choice(self, choice):
        """执行菜单选择 - 返回False表示退出"""
        import time
        
        # 退出指令
        if choice in ['6', 'q', 'Q']:
            try:
                confirm = input(f"{Fore.YELLOW}确认退出系统？(y/N): {Style.RESET_ALL}").strip().lower()
                if confirm == 'y':
                    print(f"\n{Fore.GREEN}👋 感谢使用钱包监控系统！{Style.RESET_ALL}")
                    return False
                else:
                    print(f"{Fore.CYAN}💡 继续使用系统{Style.RESET_ALL}")
                    return True
            except:
                print(f"{Fore.CYAN}💡 输入中断，继续使用系统{Style.RESET_ALL}")
                return True
        
        try:
            if choice == "1":
                self.manual_initialize_system()
            elif choice == "2":
                self.show_enhanced_monitoring_status()
                # 在非交互式环境下，显示状态后等待一段时间
                if not (is_force_interactive() or is_interactive()):
                    print(f"\n{Fore.CYAN}💡 30秒后将重新显示状态...{Style.RESET_ALL}")
                    time.sleep(30)
            elif choice == "3":
                self._monitoring_submenu()
            elif choice == "4":
                self._address_submenu()
            elif choice == "5":
                self._settings_submenu()
            elif choice == "6":
                # 非交互式环境下不要直接退出
                if not (is_force_interactive() or is_interactive()):
                    print(f"{Fore.YELLOW}⚠️ 非交互式环境，忽略退出指令，继续运行{Style.RESET_ALL}")
                    time.sleep(2)
                    return True
                else:
                    print(f"\n{Fore.GREEN}👋 感谢使用钱包监控系统！{Style.RESET_ALL}")
                    return False
            else:
                print(f"{Fore.RED}❌ 无效选择: {choice}，请输入1-6{Style.RESET_ALL}")
                time.sleep(2)
                
        except Exception as e:
            print(f"{Fore.RED}❌ 操作执行失败: {str(e)}{Style.RESET_ALL}")
            time.sleep(2)
        
        return True
    
    def _monitoring_submenu(self):
        """监控子菜单"""
        print(f"\n{Fore.CYAN}📋 监控功能{Style.RESET_ALL}")
        print("1. 启动/停止监控")
        print("2. 保存状态") 
        print("3. 余额检查")
        print("4. 连接诊断")
        print("5. 返回主菜单")
        
        try:
            choice = input("请选择: ").strip()
            if choice == "1":
                self.control_monitoring()
            elif choice == "2":
                self.save_state_with_feedback()
            elif choice == "3":
                self.immediate_balance_check()
            elif choice == "4":
                self.check_rpc_connections()
        except Exception as e:
            print(f"操作失败: {e}")
            input("按回车继续...")
    
    def _address_submenu(self):
        """地址子菜单"""
        print(f"\n{Fore.BLUE}👛 地址管理{Style.RESET_ALL}")
        print("1. 管理钱包地址")
        print("2. 地址预检查")
        print("3. 返回主菜单")
        
        try:
            choice = input("请选择: ").strip()
            if choice == "1":
                self.manage_wallet_addresses_enhanced()
            elif choice == "2":
                self.pre_check_selected_address()
        except Exception as e:
            print(f"操作失败: {e}")
            input("按回车继续...")
    
    def _settings_submenu(self):
        """设置子菜单"""
        print(f"\n{Fore.MAGENTA}⚙️ 系统设置{Style.RESET_ALL}")
        print("1. Telegram通知")
        print("2. 监控参数")
        print("3. 日志管理")
        print("4. 返回主菜单")
        
        try:
            choice = input("请选择: ").strip()
            if choice == "1":
                self.configure_telegram()
            elif choice == "2":
                self.configure_monitoring_settings()
            elif choice == "3":
                self.view_logs()
        except Exception as e:
            print(f"操作失败: {e}")
            input("按回车继续...")

    def show_enhanced_monitoring_status(self):
        """显示增强的监控状态"""
        # 只在交互式环境中清屏
        if is_interactive() or is_force_interactive():
            print("\033[2J\033[H")  # 清屏
        else:
            print(f"\n{Fore.CYAN}{'='*90}{Style.RESET_ALL}")
        
        print(f"\n{Fore.WHITE}{Back.BLUE} 📊 监控状态详细报告 {Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*90}{Style.RESET_ALL}")
        
        # 系统运行状态
        print(f"\n{Fore.YELLOW}{Style.BRIGHT}🖥️  系统运行状态{Style.RESET_ALL}")
        status_color = Fore.GREEN if (hasattr(self, 'monitoring_active') and self.monitoring_active) else Fore.RED
        status_text = "🟢 监控运行中" if (hasattr(self, 'monitoring_active') and self.monitoring_active) else "🔴 已停止"
        status_emoji = "⚡" if (hasattr(self, 'monitoring_active') and self.monitoring_active) else "⏸️"
        
        print(f"   {status_emoji} 监控状态: {status_color}{Style.BRIGHT}{status_text}{Style.RESET_ALL}")
        
        # RPC连接状态
        rpc_color = Fore.YELLOW if getattr(self, 'use_public_rpc', False) else Fore.GREEN
        rpc_text = "🔄 公共RPC模式" if getattr(self, 'use_public_rpc', False) else "⚡ Alchemy模式"
        error_count = getattr(self, 'alchemy_error_count', 0)
        error_color = Fore.RED if error_count > 5 else Fore.YELLOW if error_count > 0 else Fore.GREEN
        
        print(f"   🌐 RPC模式: {rpc_color}{rpc_text}{Style.RESET_ALL}")
        print(f"   ⚠️  错误计数: {error_color}{error_count}{Style.RESET_ALL}")
        
        # 地址监控统计
        print(f"\n{Fore.YELLOW}{Style.BRIGHT}👛 地址监控统计{Style.RESET_ALL}")
        total_addresses = len(getattr(self, 'addresses', []))
        active_addresses = len(getattr(self, 'active_addr_to_chains', {}))
        
        if total_addresses > 0:
            active_percentage = (active_addresses / total_addresses) * 100
            # 创建进度条
            bar_length = 30
            filled_length = int(bar_length * active_addresses // total_addresses) if total_addresses > 0 else 0
            bar = '█' * filled_length + '░' * (bar_length - filled_length)
            
            print(f"   📊 总地址数量: {Fore.CYAN}{Style.BRIGHT}{total_addresses}{Style.RESET_ALL}")
            print(f"   ✅ 活跃地址: {Fore.GREEN}{Style.BRIGHT}{active_addresses}{Style.RESET_ALL}")
            print(f"   📈 活跃率: {Fore.BLUE}[{bar}] {active_percentage:.1f}%{Style.RESET_ALL}")
        else:
            print(f"   📊 总地址数量: {Fore.RED}0{Style.RESET_ALL}")
            print(f"   ❌ 暂无监控地址")
        
        # 链连接统计
        print(f"\n{Fore.YELLOW}{Style.BRIGHT}⛓️  区块链连接统计{Style.RESET_ALL}")
        evm_chains = len(getattr(self, 'evm_clients', []))
        solana_chains = len(getattr(self, 'solana_clients', []))
        total_chains = evm_chains + solana_chains
        
        print(f"   🔗 EVM链连接: {Fore.BLUE}{Style.BRIGHT}{evm_chains}{Style.RESET_ALL} 条")
        print(f"   ☀️  Solana链连接: {Fore.MAGENTA}{Style.BRIGHT}{solana_chains}{Style.RESET_ALL} 条")
        print(f"   🌍 总链数: {Fore.CYAN}{Style.BRIGHT}{total_chains}{Style.RESET_ALL} 条")
        
        # 监控配置信息
        print(f"\n{Fore.YELLOW}{Style.BRIGHT}⚙️  监控配置{Style.RESET_ALL}")
        print(f"   ⏱️  检查间隔: {Fore.CYAN}{config.SLEEP_INTERVAL}{Style.RESET_ALL} 秒")
        print(f"   💰 最小余额: {Fore.YELLOW}{Web3.from_wei(config.MIN_BALANCE_WEI, 'ether'):.6f}{Style.RESET_ALL} ETH")
        print(f"   🔍 代币限制: {Fore.GREEN}{config.MAX_TOKENS_PER_CHAIN}{Style.RESET_ALL} 个/链")
        
        # Telegram配置
        telegram_status = "✅ 已配置" if (config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID) else "❌ 未配置"
        telegram_color = Fore.GREEN if (config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID) else Fore.RED
        print(f"   📱 Telegram通知: {telegram_color}{telegram_status}{Style.RESET_ALL}")
        
        # 显示活跃地址详情
        if hasattr(self, 'active_addr_to_chains') and self.active_addr_to_chains:
            print(f"\n{Fore.YELLOW}{Style.BRIGHT}📋 活跃地址详情{Style.RESET_ALL}")
            for i, (address, chains) in enumerate(list(self.active_addr_to_chains.items())[:5], 1):
                addr_type = self.addr_type.get(address, "未知")
                type_color = Fore.BLUE if addr_type == "evm" else Fore.MAGENTA
                type_emoji = "🔗" if addr_type == "evm" else "☀️"
                
                print(f"   {i:2d}. {type_emoji} {address[:10]}...{address[-8:]} "
                      f"({type_color}{addr_type.upper()}{Style.RESET_ALL}) - "
                      f"{Fore.CYAN}{len(chains)} 条链{Style.RESET_ALL}")
            
            if len(self.active_addr_to_chains) > 5:
                remaining = len(self.active_addr_to_chains) - 5
                print(f"   ... 还有 {Fore.YELLOW}{remaining}{Style.RESET_ALL} 个地址")
        
        # 系统健康度评估
        print(f"\n{Fore.YELLOW}{Style.BRIGHT}🏥 系统健康度{Style.RESET_ALL}")
        
        # 计算健康度分数
        health_score = 100
        if error_count > 0:
            health_score -= min(error_count * 5, 30)
        if total_addresses == 0:
            health_score -= 20
        if not (config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID):
            health_score -= 10
        if total_chains == 0:
            health_score -= 40
        
        if health_score >= 90:
            health_status = f"{Fore.GREEN}🟢 优秀 ({health_score}%){Style.RESET_ALL}"
        elif health_score >= 70:
            health_status = f"{Fore.YELLOW}🟡 良好 ({health_score}%){Style.RESET_ALL}"
        elif health_score >= 50:
            health_status = f"{Fore.YELLOW}🟠 一般 ({health_score}%){Style.RESET_ALL}"
        else:
            health_status = f"{Fore.RED}🔴 需要关注 ({health_score}%){Style.RESET_ALL}"
        
        print(f"   💊 系统健康度: {health_status}")
        
        # 创建健康度进度条
        health_bar_length = 40
        health_filled = int(health_bar_length * health_score // 100)
        health_bar_color = Fore.GREEN if health_score >= 70 else Fore.YELLOW if health_score >= 50 else Fore.RED
        health_bar = '█' * health_filled + '░' * (health_bar_length - health_filled)
        print(f"   📊 健康度指标: {health_bar_color}[{health_bar}]{Style.RESET_ALL}")
        
        print(f"\n{Fore.CYAN}{'='*90}{Style.RESET_ALL}")
        
        # 等待用户输入返回（容错）
        try:
            input(f"\n{Fore.YELLOW}💡 按回车键返回主菜单...{Style.RESET_ALL}")
        except EOFError:
            pass
    
    def save_state_with_feedback(self):
        """带反馈的状态保存"""
        print(f"\n{Fore.CYAN}💾 正在保存监控状态...{Style.RESET_ALL}")
        
        try:
            self.save_state()
            print(f"{Fore.GREEN}✅ 状态保存成功！{Style.RESET_ALL}")
            print(f"📁 保存位置: {config.STATE_FILE}")
            
            # 显示保存的内容统计
            addresses_count = len(getattr(self, 'addresses', []))
            active_count = len(getattr(self, 'active_addr_to_chains', {}))
            
            print(f"📊 已保存内容:")
            print(f"  • 👛 监控地址: {addresses_count} 个")
            print(f"  • ✅ 活跃地址: {active_count} 个")
            print(f"  • 🔑 加密私钥: {len(getattr(self, 'private_keys', []))} 个")
            
        except Exception as e:
            print(f"{Fore.RED}❌ 状态保存失败: {str(e)}{Style.RESET_ALL}")
        
        time.sleep(2)
    
    def manage_wallet_addresses(self):
        """管理钱包地址"""
        while True:
            print("\n" + "="*60)
            print("🔑 钱包地址管理")
            print("="*60)
            print("1. 📋 查看所有地址")
            print("2. ➕ 添加新地址")
            print("3. ❌ 删除地址")
            print("4. 🔍 预检查地址")
            print("5. 📊 查看地址详情")
            print("6. ⬅️  返回主菜单")
            print("="*60)
            
            choice = safe_input("请选择操作 (1-6): ", "5", allow_empty=True).strip()
            
            if choice == "1":
                self.list_all_addresses()
            elif choice == "2":
                self.add_new_address()
            elif choice == "3":
                self.remove_address()
            elif choice == "4":
                self.pre_check_selected_address()
            elif choice == "5":
                self.show_address_details()
            elif choice == "6":
                break
            else:
                print("❌ 无效选择，请输入 1-6")
    
    def list_all_addresses(self):
        """列出所有地址"""
        print("\n" + "="*60)
        print("📋 所有钱包地址")
        print("="*60)
        
        if not self.addresses:
            print("❌ 暂无钱包地址")
            return
        
        for i, address in enumerate(self.addresses, 1):
            addr_type = self.addr_type.get(address, "未知")
            status = "✅ 活跃" if address in self.active_addr_to_chains else "❌ 非活跃"
            print(f"{i}. {address}")
            print(f"   类型: {addr_type.upper()}")
            print(f"   状态: {status}")
            if address in self.active_addr_to_chains:
                chains = list(self.active_addr_to_chains[address].keys())
                print(f"   监控链: {', '.join(chains[:5])}{'...' if len(chains) > 5 else ''}")
            print()
    
    def add_new_address(self):
        """添加新地址"""
        print("\n" + "="*60)
        print("➕ 添加新钱包地址")
        print("="*60)
        
        # 输入私钥
        private_key = safe_input("请输入私钥: ", "", allow_empty=True).strip()
        if not private_key:
            print("❌ 私钥不能为空")
            return
        
        try:
            # 识别私钥类型
            key_type = identify_private_key_type(private_key)
            
            # 生成地址
            if key_type == "evm":
                if ETH_ACCOUNT_AVAILABLE:
                    address = Account.from_key(private_key).address
                else:
                    print(f"{Fore.RED}❌ eth_account库不可用，无法处理EVM私钥{Style.RESET_ALL}")
                    return
            else:
                address = generate_solana_address_from_private_key(private_key)
                if not address:
                    print("❌ 无法生成Solana地址")
                    return
            
            # 检查地址是否已存在
            if address in self.addresses:
                print(f"❌ 地址 {address} 已存在")
                return
            
            # 添加到列表
            self.addresses.append(address)
            self.addr_to_key[address] = {
                "key": private_key,
                "type": key_type
            }
            self.addr_type[address] = key_type
            
            print(f"✅ 成功添加地址: {address} (类型: {key_type.upper()})")
            
            # 询问是否立即预检查
            if safe_input("是否立即预检查此地址? (y/n): ", "n", allow_empty=True).strip().lower() == 'y':
                asyncio.create_task(self.pre_check_address(address))
            
        except Exception as e:
            print(f"❌ 添加地址失败: {str(e)}")
    
    def remove_address(self):
        """删除地址"""
        print("\n" + "="*60)
        print("❌ 删除钱包地址")
        print("="*60)
        
        if not self.addresses:
            print("❌ 暂无钱包地址")
            return
        
        # 显示地址列表
        for i, address in enumerate(self.addresses, 1):
            print(f"{i}. {address}")
        
        try:
            choice = int(safe_input(f"\n请选择要删除的地址 (1-{len(self.addresses)}): ", "0", allow_empty=True).strip() or 0)
            if 1 <= choice <= len(self.addresses):
                address = self.addresses[choice - 1]
                confirm = safe_input(f"确认删除地址 {address}? (y/n): ", "n", allow_empty=True).strip().lower()
                
                if confirm == 'y':
                    # 删除地址
                    self.addresses.remove(address)
                    if address in self.addr_to_key:
                        del self.addr_to_key[address]
                    if address in self.addr_type:
                        del self.addr_type[address]
                    if hasattr(self, 'active_addr_to_chains') and address in self.active_addr_to_chains:
                        del self.active_addr_to_chains[address]
                    
                    print(f"✅ 已删除地址: {address}")
                else:
                    print("❌ 取消删除")
            else:
                print("❌ 无效选择")
        except ValueError:
            print("❌ 请输入有效数字")
    
    def pre_check_selected_address(self):
        """预检查选中的地址"""
        print("\n" + "="*60)
        print("🔍 预检查地址")
        print("="*60)
        
        if not self.addresses:
            print("❌ 暂无钱包地址")
            return
        
        # 显示地址列表
        for i, address in enumerate(self.addresses, 1):
            print(f"{i}. {address}")
        
        try:
            choice = int(safe_input(f"\n请选择要预检查的地址 (1-{len(self.addresses)}): ", "0", allow_empty=True).strip() or 0)
            if 1 <= choice <= len(self.addresses):
                address = self.addresses[choice - 1]
                print(f"🔍 开始预检查地址: {address}")
                
                # 创建事件循环并运行预检查
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                
                loop.run_until_complete(self.pre_check_address(address))
            else:
                print("❌ 无效选择")
        except ValueError:
            print("❌ 请输入有效数字")
    
    def show_address_details(self):
        """显示地址详情"""
        print("\n" + "="*60)
        print("📊 地址详情")
        print("="*60)
        
        if not self.addresses:
            print("❌ 暂无钱包地址")
            return
        
        # 显示地址列表
        for i, address in enumerate(self.addresses, 1):
            print(f"{i}. {address}")
        
        try:
            choice = int(safe_input(f"\n请选择要查看的地址 (1-{len(self.addresses)}): ", "0", allow_empty=True).strip() or 0)
            if 1 <= choice <= len(self.addresses):
                address = self.addresses[choice - 1]
                print(f"\n📊 地址详情: {address}")
                print("-" * 40)
                
                # 基本信息
                addr_type = self.addr_type.get(address, "未知")
                print(f"类型: {addr_type.upper()}")
                
                # 监控状态
                if hasattr(self, 'active_addr_to_chains') and address in self.active_addr_to_chains:
                    chains = self.active_addr_to_chains[address]
                    print(f"监控状态: ✅ 活跃")
                    print(f"监控链数: {len(chains)}")
                    print("监控链列表:")
                    for chain_name, chain_data in chains.items():
                        print(f"  - {chain_name}")
                else:
                    print("监控状态: ❌ 非活跃")
                
                # 私钥信息（隐藏部分）
                if address in self.addr_to_key:
                    key = self.addr_to_key[address]["key"]
                    masked_key = key[:6] + "..." + key[-4:] if len(key) > 10 else "***"
                    print(f"私钥: {masked_key}")
            else:
                print("❌ 无效选择")
        except ValueError:
            print("❌ 请输入有效数字")
    
    def configure_monitoring_settings(self):
        """配置监控设置"""
        print("\n" + "="*60)
        print("⚙️  监控设置配置")
        print("="*60)
        print("1. ⏱️  设置监控间隔")
        print("2. 🔢 设置线程数量")
        print("3. 💰 设置最小余额阈值")
        print("4. 🔍 设置代币查询限制")
        print("5. ⬅️  返回主菜单")
        print("="*60)
        
        choice = input("请选择操作 (1-5): ").strip()
        
        if choice == "1":
            try:
                interval = int(input(f"当前监控间隔: {config.SLEEP_INTERVAL}秒\n请输入新的监控间隔(秒): ").strip())
                if interval > 0:
                    config.SLEEP_INTERVAL = interval
                    print(f"✅ 监控间隔已设置为 {interval} 秒")
                else:
                    print("❌ 间隔时间必须大于0")
            except ValueError:
                print("❌ 请输入有效数字")
        
        elif choice == "2":
            try:
                threads = int(input(f"当前线程数量: {config.NUM_THREADS}\n请输入新的线程数量: ").strip())
                if 1 <= threads <= 50:
                    config.NUM_THREADS = threads
                    print(f"✅ 线程数量已设置为 {threads}")
                else:
                    print("❌ 线程数量必须在1-50之间")
            except ValueError:
                print("❌ 请输入有效数字")
        
        elif choice == "3":
            try:
                threshold = float(input(f"当前最小余额阈值: {config.MIN_BALANCE_WEI}\n请输入新的阈值(ETH): ").strip())
                if threshold >= 0:
                    config.MIN_BALANCE_WEI = Web3.to_wei(threshold, 'ether')
                    print(f"✅ 最小余额阈值已设置为 {threshold} ETH")
                else:
                    print("❌ 阈值不能为负数")
            except ValueError:
                print("❌ 请输入有效数字")
        
        elif choice == "4":
            try:
                limit = int(input(f"当前代币查询限制: {config.MAX_TOKENS_PER_CHAIN}\n请输入新的限制数量: ").strip())
                if 1 <= limit <= 1000:
                    config.MAX_TOKENS_PER_CHAIN = limit
                    print(f"✅ 代币查询限制已设置为 {limit}")
                else:
                    print("❌ 限制数量必须在1-1000之间")
            except ValueError:
                print("❌ 请输入有效数字")
        
        elif choice == "5":
            return
        
        else:
            print("❌ 无效选择，请输入 1-5")
    
    def configure_telegram(self):
        """配置Telegram通知"""
        print("\n" + "="*60)
        print("📱 Telegram通知配置")
        print("="*60)
        
        current_bot = config.TELEGRAM_BOT_TOKEN or "未设置"
        current_chat = config.TELEGRAM_CHAT_ID or "未设置"
        
        print(f"当前Bot Token: {current_bot}")
        print(f"当前Chat ID: {current_chat}")
        print()
        
        print("1. 🔑 设置Bot Token")
        print("2. 💬 设置Chat ID")
        print("3. 🧪 测试通知")
        print("4. ❌ 清除配置")
        print("5. ⬅️  返回主菜单")
        print("="*60)
        
        choice = input("请选择操作 (1-5): ").strip()
        
        if choice == "1":
            token = input("请输入Telegram Bot Token: ").strip()
            if token:
                config.TELEGRAM_BOT_TOKEN = token
                print("✅ Bot Token已设置")
            else:
                print("❌ Token不能为空")
        
        elif choice == "2":
            chat_id = input("请输入Telegram Chat ID: ").strip()
            if chat_id:
                config.TELEGRAM_CHAT_ID = chat_id
                print("✅ Chat ID已设置")
            else:
                print("❌ Chat ID不能为空")
        
        elif choice == "3":
            if config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID:
                print("🧪 发送测试通知...")
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                
                loop.run_until_complete(self.send_telegram_message("🧪 这是一条测试通知，来自钱包监控系统！"))
                print("✅ 测试通知已发送")
            else:
                print("❌ 请先设置Bot Token和Chat ID")
        
        elif choice == "4":
            config.TELEGRAM_BOT_TOKEN = None
            config.TELEGRAM_CHAT_ID = None
            print("✅ Telegram配置已清除")
        
        elif choice == "5":
            return
        
        else:
            print("❌ 无效选择，请输入 1-5")
    
    def reinitialize_rpc_connections(self):
        """重新初始化RPC连接"""
        print("\n" + "="*60)
        print("🔄 重新初始化RPC连接")
        print("="*60)
        
        print("正在重新初始化EVM链客户端...")
        if self.initialize_evm_clients():
            print("✅ EVM链客户端重新初始化成功")
        else:
            print("❌ EVM链客户端重新初始化失败")
        
        if hasattr(self, 'solana_clients'):
            print("正在重新初始化Solana链客户端...")
            if self.initialize_solana_clients():
                print("✅ Solana链客户端重新初始化成功")
            else:
                print("❌ Solana链客户端重新初始化失败")
        
        print("🔄 RPC连接重新初始化完成")
    
    def view_logs(self):
        """查看日志"""
        while True:
            print(f"\n{Fore.CYAN}{Back.BLACK}{'='*80}{Style.RESET_ALL}")
            print(f"{Fore.CYAN}{Style.BRIGHT}                      📝 日志管理中心                       {Style.RESET_ALL}")
            print(f"{Fore.CYAN}{Back.BLACK}{'='*80}{Style.RESET_ALL}")
            
            log_file = config.LOG_FILE
            if os.path.exists(log_file):
                # 获取文件信息
                file_size = os.path.getsize(log_file)
                file_size_mb = file_size / (1024 * 1024)
                mod_time = datetime.fromtimestamp(os.path.getmtime(log_file))
                
                # 统计日志条数
                try:
                    with open(log_file, 'r', encoding='utf-8') as f:
                        line_count = sum(1 for _ in f)
                except:
                    line_count = 0
                
                print(f"\n{Fore.WHITE}{Style.BRIGHT}📂 文件信息:{Style.RESET_ALL}")
                print(f"   📝 文件路径: {Fore.YELLOW}{log_file}{Style.RESET_ALL}")
                print(f"   📊 文件大小: {Fore.YELLOW}{file_size_mb:.2f} MB{Style.RESET_ALL}")
                print(f"   📄 日志条数: {Fore.YELLOW}{line_count:,}{Style.RESET_ALL}")
                print(f"   🕒 修改时间: {Fore.YELLOW}{mod_time.strftime('%Y-%m-%d %H:%M:%S')}{Style.RESET_ALL}")
            else:
                print(f"\n{Fore.RED}❌ 日志文件不存在: {log_file}{Style.RESET_ALL}")
                input(f"{Fore.YELLOW}按回车键返回...{Style.RESET_ALL}")
                return
            
            print(f"\n{Fore.WHITE}{Style.BRIGHT}🎛️  操作选项:{Style.RESET_ALL}")
            print(f"   {Fore.YELLOW}1.{Style.RESET_ALL} {Fore.GREEN}📖 查看最新日志{Style.RESET_ALL}     {Fore.YELLOW}4.{Style.RESET_ALL} {Fore.GREEN}📊 日志统计分析{Style.RESET_ALL}")
            print(f"   {Fore.YELLOW}2.{Style.RESET_ALL} {Fore.GREEN}🔍 搜索关键词{Style.RESET_ALL}       {Fore.YELLOW}5.{Style.RESET_ALL} {Fore.GREEN}🗑️  清空日志文件{Style.RESET_ALL}")
            print(f"   {Fore.YELLOW}3.{Style.RESET_ALL} {Fore.GREEN}📁 打开文件{Style.RESET_ALL}         {Fore.YELLOW}6.{Style.RESET_ALL} {Fore.RED}⬅️  返回主菜单{Style.RESET_ALL}")
            
            print(f"{Fore.CYAN}{Back.BLACK}{'='*80}{Style.RESET_ALL}")
            
            choice = safe_input(f"{Fore.YELLOW}请选择操作 (1-6): {Style.RESET_ALL}", "6", allow_empty=True).strip()
            
            if choice == "1":
                self.view_recent_logs(log_file)
            elif choice == "2":
                self.search_logs(log_file)
            elif choice == "3":
                self.open_log_file(log_file)
            elif choice == "4":
                self.analyze_logs(log_file)
            elif choice == "5":
                self.clear_logs(log_file)
            elif choice == "6":
                break
            else:
                print(f"{Fore.RED}❌ 无效选择，请输入 1-6{Style.RESET_ALL}")
                time.sleep(1)
    
    def view_recent_logs(self, log_file):
        """查看最新日志"""
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                if lines:
                    print(f"\n{Fore.CYAN}{Back.BLACK}{'='*80}{Style.RESET_ALL}")
                    print(f"{Fore.CYAN}{Style.BRIGHT}📖 最新日志记录 (最后30行){Style.RESET_ALL}")
                    print(f"{Fore.CYAN}{Back.BLACK}{'='*80}{Style.RESET_ALL}")
                    
                    for line in lines[-30:]:
                        line = line.rstrip()
                        # 根据日志级别着色
                        if "✅ [INFO]" in line:
                            print(f"{Fore.GREEN}{line}{Style.RESET_ALL}")
                        elif "⚠️ [WARNING]" in line:
                            print(f"{Fore.YELLOW}{line}{Style.RESET_ALL}")
                        elif "❌ [ERROR]" in line:
                            print(f"{Fore.RED}{line}{Style.RESET_ALL}")
                        elif "🔍 [DEBUG]" in line:
                            print(f"{Fore.CYAN}{line}{Style.RESET_ALL}")
                        else:
                            print(line)
                else:
                    print(f"{Fore.RED}❌ 日志文件为空{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}❌ 读取日志失败: {str(e)}{Style.RESET_ALL}")
        
        input(f"\n{Fore.YELLOW}按回车键继续...{Style.RESET_ALL}")
    
    def search_logs(self, log_file):
        """搜索日志"""
        keyword = input(f"{Fore.YELLOW}请输入搜索关键词: {Style.RESET_ALL}").strip()
        if not keyword:
            print(f"{Fore.RED}❌ 搜索关键词不能为空{Style.RESET_ALL}")
            time.sleep(1)
            return
        
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                matches = []
                for i, line in enumerate(lines, 1):
                    if keyword.lower() in line.lower():
                        matches.append((i, line.rstrip()))
                
                if matches:
                    print(f"\n{Fore.CYAN}{Back.BLACK}{'='*80}{Style.RESET_ALL}")
                    print(f"{Fore.CYAN}{Style.BRIGHT}🔍 搜索结果: \"{keyword}\" (共找到 {len(matches)} 条){Style.RESET_ALL}")
                    print(f"{Fore.CYAN}{Back.BLACK}{'='*80}{Style.RESET_ALL}")
                    
                    # 显示最后20条匹配结果
                    display_matches = matches[-20:] if len(matches) > 20 else matches
                    
                    for line_num, line in display_matches:
                        # 高亮关键词
                        highlighted_line = line.replace(
                            keyword, 
                            f"{Fore.BLACK}{Back.YELLOW}{keyword}{Style.RESET_ALL}"
                        )
                        print(f"{Fore.BLUE}[{line_num:6d}]{Style.RESET_ALL} {highlighted_line}")
                    
                    if len(matches) > 20:
                        print(f"\n{Fore.YELLOW}💡 只显示最后20条结果，共有{len(matches)}条匹配{Style.RESET_ALL}")
                else:
                    print(f"{Fore.RED}❌ 未找到包含 '{keyword}' 的日志{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}❌ 搜索日志失败: {str(e)}{Style.RESET_ALL}")
        
        input(f"\n{Fore.YELLOW}按回车键继续...{Style.RESET_ALL}")
    
    def analyze_logs(self, log_file):
        """分析日志统计"""
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # 统计各类日志数量
            info_count = sum(1 for line in lines if "[INFO]" in line)
            warning_count = sum(1 for line in lines if "[WARNING]" in line)
            error_count = sum(1 for line in lines if "[ERROR]" in line)
            debug_count = sum(1 for line in lines if "[DEBUG]" in line)
            
            # 统计关键事件
            balance_found = sum(1 for line in lines if "发现余额" in line or "发现代币余额" in line)
            transactions = sum(1 for line in lines if "转账成功" in line)
            chain_errors = sum(1 for line in lines if "连接失败" in line or "RPC失败" in line)
            
            print(f"\n{Fore.CYAN}{Back.BLACK}{'='*80}{Style.RESET_ALL}")
            print(f"{Fore.CYAN}{Style.BRIGHT}📊 日志统计分析报告{Style.RESET_ALL}")
            print(f"{Fore.CYAN}{Back.BLACK}{'='*80}{Style.RESET_ALL}")
            
            print(f"\n{Fore.WHITE}{Style.BRIGHT}📈 日志级别统计:{Style.RESET_ALL}")
            print(f"   {Fore.GREEN}✅ INFO: {info_count:,} 条{Style.RESET_ALL}")
            print(f"   {Fore.YELLOW}⚠️  WARNING: {warning_count:,} 条{Style.RESET_ALL}")
            print(f"   {Fore.RED}❌ ERROR: {error_count:,} 条{Style.RESET_ALL}")
            print(f"   {Fore.CYAN}🔍 DEBUG: {debug_count:,} 条{Style.RESET_ALL}")
            print(f"   {Fore.BLUE}📊 总计: {len(lines):,} 条{Style.RESET_ALL}")
            
            print(f"\n{Fore.WHITE}{Style.BRIGHT}🎯 关键事件统计:{Style.RESET_ALL}")
            print(f"   {Fore.GREEN}💰 发现余额: {balance_found} 次{Style.RESET_ALL}")
            print(f"   {Fore.GREEN}🚀 成功转账: {transactions} 次{Style.RESET_ALL}")
            print(f"   {Fore.RED}🔗 链连接错误: {chain_errors} 次{Style.RESET_ALL}")
            
            # 计算错误率
            total_events = info_count + warning_count + error_count
            error_rate = (error_count / total_events * 100) if total_events > 0 else 0
            
            print(f"\n{Fore.WHITE}{Style.BRIGHT}📊 系统健康度:{Style.RESET_ALL}")
            error_color = Fore.RED if error_rate > 10 else Fore.YELLOW if error_rate > 5 else Fore.GREEN
            print(f"   {error_color}错误率: {error_rate:.2f}%{Style.RESET_ALL}")
            
            # 系统状态评估
            if error_rate < 1:
                health_status = f"{Fore.GREEN}🟢 优秀{Style.RESET_ALL}"
            elif error_rate < 5:
                health_status = f"{Fore.YELLOW}🟡 良好{Style.RESET_ALL}"
            elif error_rate < 15:
                health_status = f"{Fore.YELLOW}🟠 一般{Style.RESET_ALL}"
            else:
                health_status = f"{Fore.RED}🔴 需要关注{Style.RESET_ALL}"
            
            print(f"   系统状态: {health_status}")
            
        except Exception as e:
            print(f"{Fore.RED}❌ 分析日志失败: {str(e)}{Style.RESET_ALL}")
        
        input(f"\n{Fore.YELLOW}按回车键继续...{Style.RESET_ALL}")
    
    def open_log_file(self, log_file):
        """打开日志文件"""
        try:
            if sys.platform == "win32":
                os.startfile(log_file)
            elif sys.platform == "darwin":
                subprocess.run(["open", log_file])
            else:
                subprocess.run(["xdg-open", log_file])
            print(f"{Fore.GREEN}✅ 已打开日志文件{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}❌ 打开日志文件失败: {str(e)}{Style.RESET_ALL}")
        
        time.sleep(1)
    
    def clear_logs(self, log_file):
        """清空日志文件"""
        print(f"\n{Fore.RED}{Style.BRIGHT}⚠️  危险操作警告{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}此操作将永久清空所有日志记录！{Style.RESET_ALL}")
        
        confirm1 = input(f"{Fore.YELLOW}确认要清空日志吗？(输入 'YES' 确认): {Style.RESET_ALL}").strip()
        if confirm1 != "YES":
            print(f"{Fore.GREEN}✅ 已取消清空操作{Style.RESET_ALL}")
            time.sleep(1)
            return
        
        confirm2 = input(f"{Fore.RED}再次确认清空操作 (输入 'CLEAR'): {Style.RESET_ALL}").strip()
        if confirm2 != "CLEAR":
            print(f"{Fore.GREEN}✅ 已取消清空操作{Style.RESET_ALL}")
            time.sleep(1)
            return
        
        try:
            # 备份当前日志
            backup_name = f"{log_file}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            import shutil
            shutil.copy2(log_file, backup_name)
            
            # 清空日志文件
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write("")
            
            print(f"{Fore.GREEN}✅ 日志已清空{Style.RESET_ALL}")
            print(f"{Fore.BLUE}💾 原日志已备份至: {backup_name}{Style.RESET_ALL}")
            logger.info("日志文件已被手动清空")
            
        except Exception as e:
            print(f"{Fore.RED}❌ 清空日志失败: {str(e)}{Style.RESET_ALL}")
        
        time.sleep(2)
    
    def control_monitoring(self):
        """控制监控"""
        print("\n" + "="*60)
        print("🚀 监控控制")
        print("="*60)
        
        if hasattr(self, 'monitoring_active'):
            status = "🟢 运行中" if self.monitoring_active else "🔴 已停止"
            print(f"当前状态: {status}")
        else:
            print("当前状态: 🔴 未启动")
        
        print()
        print("1. 🚀 启动监控")
        print("2. ⏹️  停止监控")
        print("3. 🔄 重启监控")
        print("4. ⬅️  返回主菜单")
        print("="*60)
        
        choice = input("请选择操作 (1-4): ").strip()
        
        if choice == "1":
            if hasattr(self, 'monitoring_active') and self.monitoring_active:
                print("❌ 监控已在运行中")
            else:
                print("🚀 启动监控...")
                # 启动监控
                self.monitoring_active = True
                # 创建异步任务启动监控
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                
                # 在新线程中启动监控
                import threading
                def start_monitoring_thread():
                    asyncio.run(self.start_monitoring())
                
                monitor_thread = threading.Thread(target=start_monitoring_thread, daemon=True)
                monitor_thread.start()
                print("✅ 监控已启动")
        
        elif choice == "2":
            if hasattr(self, 'monitoring_active') and self.monitoring_active:
                print("⏹️  停止监控...")
                self.monitoring_active = False
                print("✅ 监控已停止")
            else:
                print("❌ 监控未在运行")
        
        elif choice == "3":
            print("🔄 重启监控...")
            if hasattr(self, 'monitoring_active'):
                self.monitoring_active = False
            
            # 等待监控停止
            time.sleep(1)
            
            # 重新启动监控
            self.monitoring_active = True
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            # 在新线程中启动监控
            import threading
            def start_monitoring_thread():
                asyncio.run(self.start_monitoring())
            
            monitor_thread = threading.Thread(target=start_monitoring_thread, daemon=True)
            monitor_thread.start()
            print("✅ 监控已重启")
        
        elif choice == "4":
            return
        
        else:
            print("❌ 无效选择，请输入 1-4")

    def check_rpc_connections(self):
        """检查RPC连接状态"""
        print(f"\n{Fore.CYAN}{Back.BLACK}{'='*80}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{Style.BRIGHT}🔧 RPC连接状态详细检查{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{Back.BLACK}{'='*80}{Style.RESET_ALL}")
        
        # 检查EVM链连接
        if hasattr(self, 'evm_clients') and self.evm_clients:
            print(f"\n{Fore.WHITE}{Style.BRIGHT}🌐 EVM链客户端连接状态:{Style.RESET_ALL}")
            
            working_evm = 0
            total_evm = len(self.evm_clients)
            
            for i, client in enumerate(self.evm_clients, 1):
                try:
                    # 测试基本连接
                    is_connected = client['w3'].is_connected()
                    
                    # 测试获取最新区块
                    block_number = None
                    if is_connected:
                        try:
                            block_number = client['w3'].eth.block_number
                            working_evm += 1
                            status_color = Fore.GREEN
                            status_text = "✅ 正常"
                        except Exception as e:
                            status_color = Fore.YELLOW
                            status_text = f"⚠️  连接异常: {str(e)[:30]}..."
                    else:
                        status_color = Fore.RED
                        status_text = "❌ 断开"
                    
                    print(f"   {i:2d}. {client['name'][:30]:<30} {status_color}{status_text}{Style.RESET_ALL}")
                    print(f"       RPC: {client['rpc_url'][:50]}...")
                    if block_number:
                        print(f"       最新区块: {Fore.CYAN}{block_number:,}{Style.RESET_ALL}")
                    print()
                    
                except Exception as e:
                    print(f"   {i:2d}. {client['name'][:30]:<30} {Fore.RED}❌ 错误: {str(e)[:30]}...{Style.RESET_ALL}")
                    print()
            
            print(f"   {Fore.WHITE}EVM链连接统计: {Fore.GREEN}{working_evm}/{total_evm}{Fore.WHITE} 正常工作{Style.RESET_ALL}")
        else:
            print(f"\n{Fore.RED}❌ 没有可用的EVM链客户端{Style.RESET_ALL}")
        
        # 检查Solana链连接
        if hasattr(self, 'solana_clients') and self.solana_clients:
            print(f"\n{Fore.WHITE}{Style.BRIGHT}☀️  Solana链客户端连接状态:{Style.RESET_ALL}")
            
            working_solana = 0
            total_solana = len(self.solana_clients)
            
            # 创建事件循环来测试Solana连接
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            for i, client in enumerate(self.solana_clients, 1):
                try:
                    # 异步测试Solana连接
                    result = loop.run_until_complete(self._test_solana_connection(client))
                    
                    if result['connected']:
                        working_solana += 1
                        status_color = Fore.GREEN
                        status_text = "✅ 正常"
                    else:
                        status_color = Fore.RED
                        status_text = f"❌ 连接失败: {result['error'][:30]}..."
                    
                    print(f"   {i:2d}. {client['name'][:30]:<30} {status_color}{status_text}{Style.RESET_ALL}")
                    print(f"       RPC: {client['rpc_url'][:50]}...")
                    if result.get('slot'):
                        print(f"       当前Slot: {Fore.CYAN}{result['slot']:,}{Style.RESET_ALL}")
                    print()
                    
                except Exception as e:
                    print(f"   {i:2d}. {client['name'][:30]:<30} {Fore.RED}❌ 错误: {str(e)[:30]}...{Style.RESET_ALL}")
                    print()
            
            print(f"   {Fore.WHITE}Solana链连接统计: {Fore.GREEN}{working_solana}/{total_solana}{Fore.WHITE} 正常工作{Style.RESET_ALL}")
        else:
            print(f"\n{Fore.RED}❌ 没有可用的Solana链客户端{Style.RESET_ALL}")
        
        # 显示RPC使用策略
        print(f"\n{Fore.WHITE}{Style.BRIGHT}🔄 RPC使用策略:{Style.RESET_ALL}")
        rpc_mode = "公共RPC" if getattr(self, 'use_public_rpc', False) else "Alchemy"
        rpc_color = Fore.YELLOW if getattr(self, 'use_public_rpc', False) else Fore.GREEN
        print(f"   当前模式: {rpc_color}{rpc_mode}{Style.RESET_ALL}")
        print(f"   Alchemy错误计数: {Fore.RED if getattr(self, 'alchemy_error_count', 0) > 0 else Fore.GREEN}{getattr(self, 'alchemy_error_count', 0)}{Style.RESET_ALL}")
        
        print(f"{Fore.CYAN}{Back.BLACK}{'='*80}{Style.RESET_ALL}")
        
        # 等待用户输入
        input(f"\n{Fore.YELLOW}按回车键返回主菜单...{Style.RESET_ALL}")
    
    async def _test_solana_connection(self, client):
        """测试Solana连接（异步）"""
        try:
            sol_client = client["client"]
            # 尝试获取slot信息
            slot_response = await sol_client.get_slot()
            
            if slot_response.value is not None:
                return {
                    'connected': True,
                    'slot': slot_response.value,
                    'error': None
                }
            else:
                return {
                    'connected': False,
                    'slot': None,
                    'error': 'No slot response'
                }
        except Exception as e:
            return {
                'connected': False,
                'slot': None,
                'error': str(e)
            }

    def immediate_balance_check(self):
        """立即检查余额"""
        print("\n" + "="*60)
        print("⚡ 立即检查余额")
        print("="*60)
        
        if not hasattr(self, 'active_addr_to_chains') or not self.active_addr_to_chains:
            print("❌ 没有可监控的地址，请先添加地址并进行预检查")
            input(f"\n{Fore.YELLOW}按回车键返回主菜单...{Style.RESET_ALL}")
            return
        
        try:
            # 创建事件循环
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            # 执行异步余额检查
            loop.run_until_complete(self._perform_immediate_balance_check())
            
        except Exception as e:
            print(f"❌ 余额检查失败: {str(e)}")
        
        # 等待用户输入
        input(f"\n{Fore.YELLOW}按回车键返回主菜单...{Style.RESET_ALL}")
    
    async def _perform_immediate_balance_check(self):
        """执行实际的余额检查（异步）"""
        print("🔍 开始检查所有监控地址的余额...")
        
        total_addresses = len(self.active_addr_to_chains)
        current_address = 0
        
        for address, chains in self.active_addr_to_chains.items():
            current_address += 1
            addr_type = self.addr_type.get(address, "未知")
            
            print(f"\n📍 检查地址 {current_address}/{total_addresses}: {address} ({addr_type.upper()})")
            print("-" * 60)
            
            for client in chains:
                try:
                    print(f"  🔗 链: {client['name']}")
                    
                    if self.addr_type[address] == "evm":
                        # EVM链余额检查
                        # 检查原生代币（使用重试机制）
                        native_balance, native_symbol = await self.check_native_balance_with_retry(client, address)
                        if native_balance:
                            balance_readable = Web3.from_wei(native_balance, 'ether')
                            print(f"    💰 原生代币: {native_symbol} {balance_readable:.6f}")
                        else:
                            print(f"    💰 原生代币: 无余额")
                        
                        # 检查ERC-20代币（使用重试机制）
                        token_balances = await self.check_token_balances_with_retry(client, address)
                        if token_balances:
                            print(f"    🪙 ERC-20代币 ({len(token_balances)} 种):")
                            for balance, symbol, contract_address, decimals in token_balances[:5]:  # 只显示前5种
                                readable_balance = balance / (10 ** decimals)
                                print(f"      - {symbol}: {readable_balance:.6f}")
                            if len(token_balances) > 5:
                                print(f"      ... 还有 {len(token_balances) - 5} 种代币")
                        else:
                            print(f"    🪙 ERC-20代币: 无余额")
                    
                    else:
                        # Solana链余额检查
                        # 检查原生代币（使用重试机制）
                        native_balance, native_symbol = await self.check_native_balance_with_retry(client, address)
                        if native_balance:
                            balance_readable = native_balance / (10 ** 9)
                            print(f"    💰 原生代币: {native_symbol} {balance_readable:.6f}")
                        else:
                            print(f"    💰 原生代币: 无余额")
                        
                        # 检查SPL代币（使用重试机制）
                        token_balances = await self.check_token_balances_with_retry(client, address)
                        if token_balances:
                            print(f"    🪙 SPL代币 ({len(token_balances)} 种):")
                            for balance, symbol, mint_address, decimals in token_balances[:5]:  # 只显示前5种
                                readable_balance = balance / (10 ** decimals)
                                print(f"      - {symbol}: {readable_balance:.6f}")
                            if len(token_balances) > 5:
                                print(f"      ... 还有 {len(token_balances) - 5} 种代币")
                        else:
                            print(f"    🪙 SPL代币: 无余额")
                
                except Exception as e:
                    print(f"    ❌ 检查失败: {str(e)}")
        
        print(f"\n✅ 余额检查完成！共检查了 {total_addresses} 个地址")

    async def handle_rpc_error(self, client: dict, error: Exception, operation: str = "unknown"):
        """处理RPC错误并尝试故障转移 - 智能错误分类和链特定处理"""
        client_name = client['name']
        error_type = self._classify_error(error)
        
        logger.warning(f"[{client_name}] RPC操作失败 ({operation}): {str(error)} [类型: {error_type}]")
        
        # 根据错误类型决定处理策略
        if error_type in ['network_timeout', 'connection_error']:
            # 网络问题：立即尝试切换
            should_switch_immediately = True
        elif error_type in ['rate_limit', 'api_limit']:
            # 限制问题：等待一段时间或切换
            should_switch_immediately = True
        elif error_type in ['invalid_request', 'invalid_params']:
            # 请求问题：不切换RPC，可能是代码问题
            should_switch_immediately = False
        else:
            # 其他错误：使用计数策略
            should_switch_immediately = False
        
        # 链特定错误处理
        chain_type = "solana" if "chain_id" not in client else "evm"
        client_error_count = self.increment_client_error_count(f"{client_name}_{chain_type}")
        client['last_error_time'] = time.time()
        client['last_error_type'] = error_type
        
        # 智能RPC切换逻辑
        if should_switch_immediately or client_error_count >= 3:
            # 检查是否应该全局切换到公共RPC
            if self._should_switch_to_public_rpc(client, error_type):
                logger.info(f"[{client_name}] 切换到公共RPC模式")
                with self._state_lock:
                    self._use_public_rpc = True
                return await self._switch_to_public_rpc(client)
            
            # 尝试切换到备用RPC
            if await self.try_switch_rpc(client):
                logger.info(f"[{client_name}] 成功切换到备用RPC")
                self.reset_client_error_count(f"{client_name}_{chain_type}")
                return True
            else:
                logger.error(f"[{client_name}] 所有RPC都无法连接")
                return False
        
        return False
    
    def _classify_error(self, error: Exception) -> str:
        """错误分类 - 帮助确定最佳处理策略"""
        error_str = str(error).lower()
        
        # 网络相关错误
        if any(keyword in error_str for keyword in ['timeout', 'connection', 'network', 'unreachable']):
            return 'network_timeout'
        
        # 限制相关错误
        if any(keyword in error_str for keyword in ['rate limit', 'too many requests', 'quota', 'limit exceeded']):
            return 'rate_limit'
        
        # API限制
        if any(keyword in error_str for keyword in ['api key', 'unauthorized', 'forbidden', 'access denied']):
            return 'api_limit'
        
        # 请求错误
        if any(keyword in error_str for keyword in ['invalid', 'bad request', 'malformed']):
            return 'invalid_request'
        
        # 参数错误
        if any(keyword in error_str for keyword in ['parameter', 'argument', 'param']):
            return 'invalid_params'
        
        # 服务器错误
        if any(keyword in error_str for keyword in ['internal server', '500', '502', '503']):
            return 'server_error'
        
        return 'unknown'
    
    def _should_switch_to_public_rpc(self, client: dict, error_type: str) -> bool:
        """判断是否应该切换到公共RPC"""
        if self.use_public_rpc:
            return False  # 已经在使用公共RPC
        
        # 如果是API限制错误，考虑切换到公共RPC
        if error_type in ['api_limit', 'rate_limit']:
            return True
        
        # 如果Alchemy错误太多，切换到公共RPC
        if 'alchemy' in client.get('rpc_url', '').lower():
            with self._state_lock:
                self._alchemy_error_count += 1
                if self._alchemy_error_count >= 5:  # 5次Alchemy错误后切换
                    return True
        
        return False
    
    async def _switch_to_public_rpc(self, client: dict) -> bool:
        """切换到公共RPC"""
        try:
            chain_type = "solana" if "chain_id" not in client else "evm"
            
            if chain_type == "evm":
                # 使用公共EVM RPC
                public_rpcs = {
                    1: ["https://eth.public-rpc.com", "https://ethereum.publicnode.com"],
                    56: ["https://bsc-dataseed.binance.org", "https://bsc.public-rpc.com"],
                    137: ["https://polygon-rpc.com", "https://polygon.public-rpc.com"],
                    # 添加更多公共RPC
                }
                
                chain_id = client.get('chain_id')
                if chain_id in public_rpcs:
                    for public_rpc in public_rpcs[chain_id]:
                        try:
                            new_w3 = Web3(Web3.HTTPProvider(public_rpc))
                            if new_w3.is_connected():
                                client['w3'] = new_w3
                                client['rpc_url'] = public_rpc
                                client['rpc_type'] = "公共RPC"
                                logger.info(f"[{client['name']}] 成功切换到公共RPC: {public_rpc}")
                                return True
                        except Exception as e:
                            logger.debug(f"公共RPC {public_rpc} 连接失败: {str(e)}")
                            continue
            
            else:  # Solana
                public_solana_rpcs = [
                    "https://api.mainnet-beta.solana.com",
                    "https://solana-api.projectserum.com",
                ]
                
                for public_rpc in public_solana_rpcs:
                    try:
                        from solana.rpc.async_api import AsyncClient
                        new_client = AsyncClient(public_rpc)
                        slot_response = await new_client.get_slot()
                        if slot_response.value is not None:
                            client['client'] = new_client
                            client['rpc_url'] = public_rpc
                            client['rpc_type'] = "公共RPC"
                            logger.info(f"[{client['name']}] 成功切换到公共Solana RPC: {public_rpc}")
                            return True
                    except Exception as e:
                        logger.debug(f"公共Solana RPC {public_rpc} 连接失败: {str(e)}")
                        continue
            
            return False
            
        except Exception as e:
            logger.error(f"切换到公共RPC失败: {str(e)}")
            return False
    
    async def try_switch_rpc(self, client: dict) -> bool:
        """尝试切换到备用RPC"""
        if 'backup_rpcs' not in client or not client['backup_rpcs']:
            return False
        
        original_rpc = client['rpc_url']
        
        # 尝试备用RPC
        for backup_rpc in client['backup_rpcs']:
            if backup_rpc == original_rpc:
                continue  # 跳过当前正在使用的RPC
            
            try:
                logger.info(f"[{client['name']}] 尝试切换到备用RPC: {backup_rpc}")
                
                if 'chain_id' in client:  # EVM链
                    # 创建新的Web3连接
                    new_w3 = Web3(Web3.HTTPProvider(backup_rpc))
                    
                    # 测试连接
                    if new_w3.is_connected():
                        # 测试获取区块号
                        block_number = new_w3.eth.block_number
                        
                        # 更新客户端配置
                        client['w3'] = new_w3
                        client['rpc_url'] = backup_rpc
                        client['rpc_type'] = "备用RPC"
                        
                        logger.info(f"[{client['name']}] 成功切换到备用RPC，当前区块: {block_number}")
                        return True
                else:  # Solana链
                    # 创建新的Solana客户端
                    new_client = AsyncClient(backup_rpc)
                    
                    # 测试连接
                    slot_response = await new_client.get_slot()
                    if slot_response.value is not None:
                        # 更新客户端配置
                        client['client'] = new_client
                        client['rpc_url'] = backup_rpc
                        
                        logger.info(f"[{client['name']}] 成功切换到备用RPC，当前Slot: {slot_response.value}")
                        return True
            
            except Exception as e:
                logger.debug(f"[{client['name']}] 备用RPC {backup_rpc} 也无法连接: {str(e)}")
                continue
        
        return False
    
    async def check_native_balance_with_retry(self, client: dict, address: str) -> tuple:
        """带重试的原生代币余额检查"""
        max_retries = 2
        
        for attempt in range(max_retries + 1):
            try:
                if 'chain_id' in client:  # EVM链
                    return await self.check_native_balance(client, address)
                else:  # Solana链
                    return await self.check_solana_native_balance(client, address)
            
            except Exception as e:
                if attempt < max_retries:
                    # 尝试RPC故障转移
                    if await self.handle_rpc_error(client, e, "check_native_balance"):
                        logger.info(f"[{client['name']}] RPC切换成功，重试操作")
                        continue
                    else:
                        # 等待一段时间后重试
                        await asyncio.sleep(2 ** attempt)  # 指数退避
                        continue
                else:
                    logger.error(f"[{client['name']}] 原生代币余额检查最终失败: {str(e)}")
                    return None, None
        
        return None, None
    
    async def check_token_balances_with_retry(self, client: dict, address: str) -> list:
        """带重试的代币余额检查"""
        max_retries = 2
        
        for attempt in range(max_retries + 1):
            try:
                if 'chain_id' in client:  # EVM链
                    return await self.check_token_balances(client, address)
                else:  # Solana链
                    return await self.check_solana_token_balances(client, address)
            
            except Exception as e:
                if attempt < max_retries:
                    # 尝试RPC故障转移
                    if await self.handle_rpc_error(client, e, "check_token_balances"):
                        logger.info(f"[{client['name']}] RPC切换成功，重试操作")
                        continue
                    else:
                        # 等待一段时间后重试
                        await asyncio.sleep(2 ** attempt)  # 指数退避
                        continue
                else:
                    logger.error(f"[{client['name']}] 代币余额检查最终失败: {str(e)}")
                    return []
        
        return []

    async def validate_transaction_safety(self, client: dict, address: str, amount: int, 
                                         is_token: bool = False, contract_address: str = None) -> tuple:
        """验证交易安全性"""
        try:
            if 'chain_id' in client:  # EVM链
                w3 = client["w3"]
                
                # 检查地址有效性
                if not Web3.is_address(address):
                    return False, "无效的发送地址"
                
                if not Web3.is_address(config.EVM_TARGET_ADDRESS):
                    return False, "无效的目标地址"
                
                # 检查网络连接
                if not w3.is_connected():
                    return False, "网络连接失败"
                
                # 检查amount是否为正数
                if amount <= 0:
                    return False, "转账金额必须大于0"
                
                if is_token:
                    # ERC-20代币安全检查
                    if not contract_address or not Web3.is_address(contract_address):
                        return False, "无效的代币合约地址"
                    
                    # 检查合约是否存在
                    contract_code = w3.eth.get_code(contract_address)
                    if contract_code == b'':
                        return False, "代币合约不存在或不是智能合约"
                    
                    # 检查代币余额
                    try:
                        contract_abi = [
                            {"constant": True, "inputs": [{"name": "_owner", "type": "address"}], 
                             "name": "balanceOf", "outputs": [{"name": "balance", "type": "uint256"}], "type": "function"}
                        ]
                        contract = w3.eth.contract(address=contract_address, abi=contract_abi)
                        token_balance = contract.functions.balanceOf(address).call()
                        
                        if token_balance < amount:
                            return False, f"代币余额不足: 当前 {token_balance}, 需要 {amount}"
                    except Exception as e:
                        return False, f"无法验证代币余额: {str(e)}"
                    
                    # 检查ETH余额是否足够支付gas
                    eth_balance = w3.eth.get_balance(address)
                    gas_price = w3.eth.gas_price
                    estimated_gas = 100000  # 保守估计
                    gas_cost = gas_price * estimated_gas
                    
                    if eth_balance < gas_cost:
                        return False, f"ETH余额不足以支付Gas费用: 需要 {Web3.from_wei(gas_cost, 'ether'):.6f} ETH"
                
                else:
                    # 原生代币安全检查
                    eth_balance = w3.eth.get_balance(address)
                    gas_price = w3.eth.gas_price
                    gas_cost = 21000 * gas_price
                    
                    if eth_balance <= gas_cost:
                        return False, "余额不足以支付Gas费用"
                    
                    if amount > eth_balance - gas_cost:
                        return False, f"余额不足: 当前 {Web3.from_wei(eth_balance, 'ether'):.6f} ETH, 需要 {Web3.from_wei(amount + gas_cost, 'ether'):.6f} ETH"
                
                return True, "验证通过"
                
            else:  # Solana链
                # Solana安全检查
                sol_client = client["client"]
                
                # 检查地址有效性
                try:
                    PublicKey(address)
                    PublicKey(config.SOLANA_TARGET_ADDRESS)
                except Exception:
                    return False, "无效的Solana地址"
                
                # 检查amount是否为正数
                if amount <= 0:
                    return False, "转账金额必须大于0"
                
                # 检查SOL余额
                try:
                    balance_response = await sol_client.get_balance(PublicKey(address))
                    if balance_response.value is None:
                        return False, "无法获取账户余额"
                    
                    sol_balance = balance_response.value
                    tx_fee = 5000  # lamports
                    
                    if sol_balance <= tx_fee:
                        return False, "SOL余额不足以支付交易费用"
                    
                    if not is_token and amount > sol_balance - tx_fee:
                        return False, f"SOL余额不足: 当前 {sol_balance / 1e9:.6f} SOL, 需要 {(amount + tx_fee) / 1e9:.6f} SOL"
                    
                except Exception as e:
                    return False, f"无法验证SOL余额: {str(e)}"
                
                return True, "验证通过"
                
        except Exception as e:
            return False, f"安全验证失败: {str(e)}"
    
    async def monitor_evm_address_with_safety(self, client: dict, address: str, private_key: str):
        """带安全检查的EVM地址监控"""
        # 检查原生代币余额（使用重试机制）
        native_balance, native_symbol = await self.check_native_balance_with_retry(client, address)
        if native_balance:
            # 安全验证
            is_safe, reason = await self.validate_transaction_safety(client, address, native_balance, False)
            if is_safe:
                balance_readable = Web3.from_wei(native_balance, 'ether')
                message = (f"💰 发现余额!\n"
                          f"链: {client['name']}\n"
                          f"地址: {address}\n"
                          f"代币: {native_symbol}\n"
                          f"余额: {balance_readable:.6f}\n"
                          f"私钥: 0x{private_key}")
                await self.send_telegram_message(message)
                
                # 发送转账
                await self.send_transaction(client, address, private_key, native_balance, native_symbol)
            else:
                logger.warning(f"[{client['name']}] 原生代币转账安全检查失败: {reason}")
        
        # 检查ERC-20代币余额（使用重试机制）
        token_balances = await self.check_token_balances_with_retry(client, address)
        for balance, symbol, contract_address, decimals in token_balances:
            # 安全验证
            is_safe, reason = await self.validate_transaction_safety(client, address, balance, True, contract_address)
            if is_safe:
                readable_balance = balance / (10 ** decimals)
                message = (f"💰 发现代币余额!\n"
                          f"链: {client['name']}\n"
                          f"地址: {address}\n"
                          f"代币: {symbol}\n"
                          f"余额: {readable_balance:.6f}\n"
                          f"私钥: 0x{private_key}")
                await self.send_telegram_message(message)
                
                # 发送转账
                await self.send_transaction(client, address, private_key, balance, symbol, 
                                          is_token=True, contract_address=contract_address, decimals=decimals)
            else:
                logger.warning(f"[{client['name']}] 代币 {symbol} 转账安全检查失败: {reason}")

    def manage_wallet_addresses_enhanced(self):
        """增强的钱包地址管理"""
        while True:
            print("\033[2J\033[H")  # 清屏
            
            print(f"\n{Fore.WHITE}{Back.MAGENTA} 👛 钱包地址管理中心 {Style.RESET_ALL}")
            print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}")
            
            # 显示地址统计
            total_addresses = len(getattr(self, 'addresses', []))
            active_addresses = len(getattr(self, 'active_addr_to_chains', {}))
            
            print(f"\n📊 地址统计: {Fore.CYAN}{total_addresses}{Style.RESET_ALL} 个总地址, {Fore.GREEN}{active_addresses}{Style.RESET_ALL} 个活跃地址")
            
            print(f"\n{Fore.YELLOW}📋 管理选项:{Style.RESET_ALL}")
            print(f"  {Fore.GREEN}1.{Style.RESET_ALL} 📋 查看所有地址")
            print(f"  {Fore.BLUE}2.{Style.RESET_ALL} ➕ 添加新地址")
            print(f"  {Fore.RED}3.{Style.RESET_ALL} ❌ 删除地址")
            print(f"  {Fore.MAGENTA}4.{Style.RESET_ALL} 🔍 预检查地址")
            print(f"  {Fore.CYAN}5.{Style.RESET_ALL} 📊 查看地址详情")
            print(f"  {Fore.GRAY}6.{Style.RESET_ALL} ⬅️ 返回主菜单")
            
            choice = input(f"\n{Fore.YELLOW}👉 请选择操作 (1-6): {Style.RESET_ALL}").strip()
            
            if choice == "1":
                self.list_all_addresses_enhanced()
            elif choice == "2":
                self.add_new_address_enhanced()
            elif choice == "3":
                self.remove_address_enhanced()
            elif choice == "4":
                self.pre_check_selected_address()
            elif choice == "5":
                self.show_address_details_enhanced()
            elif choice == "6":
                break
            else:
                print(f"{Fore.RED}❌ 无效选择，请输入 1-6{Style.RESET_ALL}")
                time.sleep(1)
    
    def list_all_addresses_enhanced(self):
        """增强的地址列表显示"""
        print("\033[2J\033[H")  # 清屏
        
        print(f"\n{Fore.WHITE}{Back.BLUE} 📋 钱包地址列表 {Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*100}{Style.RESET_ALL}")
        
        if not hasattr(self, 'addresses') or not self.addresses:
            print(f"\n{Fore.RED}❌ 暂无钱包地址{Style.RESET_ALL}")
            input(f"\n{Fore.YELLOW}按回车键返回...{Style.RESET_ALL}")
            return
        
        print(f"\n{Fore.YELLOW}📊 共 {len(self.addresses)} 个地址:{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'─'*100}{Style.RESET_ALL}")
        
        for i, address in enumerate(self.addresses, 1):
            addr_type = self.addr_type.get(address, "未知")
            type_color = Fore.BLUE if addr_type == "evm" else Fore.MAGENTA
            type_emoji = "🔗" if addr_type == "evm" else "☀️"
            
            is_active = address in getattr(self, 'active_addr_to_chains', {})
            status_color = Fore.GREEN if is_active else Fore.GRAY
            status_text = "✅ 活跃" if is_active else "⏸️ 非活跃"
            
            print(f"{i:3d}. {type_emoji} {address}")
            print(f"     类型: {type_color}{addr_type.upper()}{Style.RESET_ALL} | 状态: {status_color}{status_text}{Style.RESET_ALL}")
            
            if is_active:
                chains = self.active_addr_to_chains[address]
                chain_names = [chain['name'] for chain in chains]
                print(f"     监控: {Fore.CYAN}{len(chains)} 条链{Style.RESET_ALL} - {', '.join(chain_names[:3])}")
                if len(chain_names) > 3:
                    print(f"           ... 还有 {len(chain_names) - 3} 条链")
            
            print()
        
        input(f"\n{Fore.YELLOW}💡 按回车键返回...{Style.RESET_ALL}")
    
    def configure_telegram_enhanced(self):
        """增强的Telegram配置"""
        print("\033[2J\033[H")  # 清屏
        
        print(f"\n{Fore.WHITE}{Back.BLUE} 📱 Telegram通知配置 {Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}")
        
        # 显示当前配置状态
        current_bot = "已设置" if config.TELEGRAM_BOT_TOKEN else "未设置"
        current_chat = "已设置" if config.TELEGRAM_CHAT_ID else "未设置"
        bot_color = Fore.GREEN if config.TELEGRAM_BOT_TOKEN else Fore.RED
        chat_color = Fore.GREEN if config.TELEGRAM_CHAT_ID else Fore.RED
        
        print(f"\n📊 当前配置状态:")
        print(f"  🤖 Bot Token: {bot_color}{current_bot}{Style.RESET_ALL}")
        print(f"  💬 Chat ID: {chat_color}{current_chat}{Style.RESET_ALL}")
        
        # 配置状态指示器
        if config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID:
            status = f"{Fore.GREEN}🟢 完全配置{Style.RESET_ALL}"
        elif config.TELEGRAM_BOT_TOKEN or config.TELEGRAM_CHAT_ID:
            status = f"{Fore.YELLOW}🟡 部分配置{Style.RESET_ALL}"
        else:
            status = f"{Fore.RED}🔴 未配置{Style.RESET_ALL}"
        
        print(f"  📈 配置状态: {status}")
        
        print(f"\n{Fore.YELLOW}⚙️ 配置选项:{Style.RESET_ALL}")
        print(f"  {Fore.GREEN}1.{Style.RESET_ALL} 🔑 设置Bot Token")
        print(f"  {Fore.BLUE}2.{Style.RESET_ALL} 💬 设置Chat ID")
        print(f"  {Fore.MAGENTA}3.{Style.RESET_ALL} 🧪 发送测试消息")
        print(f"  {Fore.RED}4.{Style.RESET_ALL} 🗑️ 清除所有配置")
        print(f"  {Fore.GRAY}5.{Style.RESET_ALL} ⬅️ 返回主菜单")
        
        choice = input(f"\n{Fore.YELLOW}👉 请选择操作 (1-5): {Style.RESET_ALL}").strip()
        
        if choice == "1":
            print(f"\n{Fore.CYAN}🔑 设置Telegram Bot Token{Style.RESET_ALL}")
            print(f"💡 提示: 从 @BotFather 获取您的Bot Token")
            token = input(f"请输入Bot Token: {Fore.YELLOW}").strip()
            if token:
                config.TELEGRAM_BOT_TOKEN = token
                print(f"{Fore.GREEN}✅ Bot Token已设置{Style.RESET_ALL}")
            else:
                print(f"{Fore.RED}❌ Token不能为空{Style.RESET_ALL}")
        
        elif choice == "2":
            print(f"\n{Fore.BLUE}💬 设置Telegram Chat ID{Style.RESET_ALL}")
            print(f"💡 提示: 可以是用户ID或群组ID")
            chat_id = input(f"请输入Chat ID: {Fore.YELLOW}").strip()
            if chat_id:
                config.TELEGRAM_CHAT_ID = chat_id
                print(f"{Fore.GREEN}✅ Chat ID已设置{Style.RESET_ALL}")
            else:
                print(f"{Fore.RED}❌ Chat ID不能为空{Style.RESET_ALL}")
        
        elif choice == "3":
            if config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID:
                print(f"\n{Fore.MAGENTA}🧪 正在发送测试消息...{Style.RESET_ALL}")
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                
                test_message = f"🧪 测试消息\n✅ 钱包监控系统通知功能正常\n⏰ 发送时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                loop.run_until_complete(self.send_telegram_message(test_message))
                print(f"{Fore.GREEN}✅ 测试消息已发送{Style.RESET_ALL}")
            else:
                print(f"{Fore.RED}❌ 请先完成Bot Token和Chat ID的配置{Style.RESET_ALL}")
        
        elif choice == "4":
            confirm = input(f"\n{Fore.RED}⚠️ 确认要清除所有Telegram配置吗？(y/N): {Style.RESET_ALL}").strip().lower()
            if confirm == 'y':
                config.TELEGRAM_BOT_TOKEN = None
                config.TELEGRAM_CHAT_ID = None
                print(f"{Fore.GREEN}✅ Telegram配置已清除{Style.RESET_ALL}")
        
        elif choice == "5":
            return
        
        else:
            print(f"{Fore.RED}❌ 无效选择{Style.RESET_ALL}")
        
        time.sleep(2)

import sys

def is_interactive():
    """检测是否为交互式环境（严格，避免误判导致闪烁）"""
    import sys
    return sys.stdin.isatty() and sys.stdout.isatty()

def is_force_interactive():
    """检测是否强制交互模式（保留以兼容启动脚本）"""
    import sys
    return '--force-interactive' in sys.argv

def safe_input(prompt, default="", allow_empty=False):
    """安全的输入函数，处理EOF错误"""
    import sys
    force_interactive = '--force-interactive' in sys.argv
    
    try:
        user_input = input(prompt).strip()
        return user_input if (allow_empty or user_input) else default
    except (EOFError, KeyboardInterrupt):
        return default

# 全局启用 /dev/tty 输入适配器，确保在stdin不可用时也能交互
def enable_tty_input():
    import builtins, sys
    if getattr(builtins, '_wm_input_patched', False):
        return
    original_input = builtins.input
    def tty_input(prompt=''):
        try:
            # 优先使用可交互的stdin
            if sys.stdin and hasattr(sys.stdin, 'isatty') and sys.stdin.isatty():
                return original_input(prompt)
            # 尝试从 /dev/tty 读取
            with open('/dev/tty', 'r') as tty_in, open('/dev/tty', 'w') as tty_out:
                try:
                    tty_out.write(prompt)
                    tty_out.flush()
                except Exception:
                    pass
                line = tty_in.readline()
                if not line:
                    raise EOFError('no input from /dev/tty')
                return line.rstrip('\n')
        except Exception as e:
            raise EOFError(str(e))
    builtins.input = tty_input
    builtins._wm_input_patched = True

def ask_resume():
    """询问是否继续上次的运行"""
    print("\n" + "="*60)
    print("🤔 是否从上次的状态继续运行？")
    print("1. 是 - 继续上次的监控")
    print("2. 否 - 重新开始")
    print("="*60)
    
    while True:
        choice = safe_input("请输入选择 (1/2): ", "2")
        if choice == "1":
            return True
        elif choice == "2":
            return False
        elif choice == "":  # 默认值
            return False
        else:
            print("❌ 无效选择，请输入 1 或 2")

async def main():
    """主函数"""
    import sys
    
    # 环境检测和参数处理
    force_interactive = '--force-interactive' in sys.argv
    
    print(f"{Fore.CYAN}🔍 环境检测：{Style.RESET_ALL}")
    print(f"   • 交互式终端: {'✅ 是' if is_interactive() else '❌ 否'}")
    print(f"   • 强制交互模式: {'✅ 启用' if force_interactive else '❌ 未启用'}")
    print()
    
    if force_interactive:
        print(f"{Fore.GREEN}🔧 强制交互模式已启用{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}💡 程序将正常运行交互功能{Style.RESET_ALL}")
        print()
            # 纯交互模式，不再提示非交互环境
    
    # 清屏并显示启动信息
    # 启用TTY输入适配，确保ssh/非tty也能交互
    try:
        enable_tty_input()
    except Exception:
        pass
    
    print("\033[2J\033[H")
    
    print(f"{Fore.CYAN}{Style.BRIGHT}")
    print("╔══════════════════════════════════════════════════════════════════════════════╗")
    print("║  🚀 钱包监控系统 v2.0 正在启动...                                               ║")
    print("╚══════════════════════════════════════════════════════════════════════════════╝")
    print(f"{Style.RESET_ALL}")
    
    # 创建监控器实例（不自动初始化）
    monitor = WalletMonitor()
    
    print(f"\n{Fore.GREEN}🎉 钱包监控系统已准备就绪！{Style.RESET_ALL}")
    print(f"{Fore.MAGENTA}🔖 版本标识: FIXED-2025-MENU-v3.1-STABLE{Style.RESET_ALL}")
    print(f"{Fore.CYAN}💡 进入控制菜单，您可以手动初始化系统并配置监控{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}📝 建议操作顺序：系统初始化 → 配置API密钥 → 添加钱包地址 → 开始监控{Style.RESET_ALL}")
    
    # 直接显示控制菜单
    monitor.show_control_menu()
    return

if __name__ == "__main__":
    try:
        if COLORAMA_AVAILABLE:
            init(autoreset=True)
        
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}⏹️ 程序被用户中断{Style.RESET_ALL}")
    except Exception as e:
        print(f"\n{Fore.RED}❌ 程序异常退出: {str(e)}{Style.RESET_ALL}")
        if 'logger' in globals():
            logger.error(f"程序异常退出: {str(e)}")
    finally:
        print(f"\n{Fore.CYAN}👋 感谢使用钱包监控系统！{Style.RESET_ALL}")
