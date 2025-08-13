#!/usr/bin/env python3
"""
EVM监控软件主程序
功能：监控多个钱包地址余额，自动转账到目标地址
特性：交易历史检查、日志记录、状态恢复、交互式菜单
"""

import os
import sys
import json
import time
import threading
import hashlib
import base64
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import logging

# 第三方库导入
try:
    from web3 import Web3
    from eth_account import Account
    from Crypto.Cipher import AES
    from Crypto.Random import get_random_bytes
    from Crypto.Protocol.KDF import PBKDF2
    import colorama
    from colorama import Fore, Style, Back
    import requests
except ImportError as e:
    print(f"❌ 导入依赖失败: {e}")
    print("请运行 bootstrap.py 安装依赖")
    sys.exit(1)

# 初始化colorama
colorama.init()

class EVMMonitor:
    def __init__(self):
        # 配置
        self.ALCHEMY_API_KEY = "S0hs4qoXIR1SMD8P7I6Wt"
        
        # 支持的全链网络配置
        self.networks = {
            # 以太坊生态
            'ethereum': {
                'name': 'Ethereum Mainnet',
                'chain_id': 1,
                'rpc_urls': [
                    f'https://eth-mainnet.g.alchemy.com/v2/{self.ALCHEMY_API_KEY}',
                    'https://mainnet.infura.io/v3/9aa3d95b3bc440fa88ea12eaa4456161',
                    'https://rpc.ankr.com/eth',
                    'https://eth-mainnet.public.blastapi.io',
                    'https://ethereum.publicnode.com'
                ],
                'native_currency': 'ETH',
                'explorer': 'https://etherscan.io'
            },
            
            # BSC智能链
            'bsc': {
                'name': 'Binance Smart Chain',
                'chain_id': 56,
                'rpc_urls': [
                    'https://bsc-dataseed1.binance.org',
                    'https://bsc-dataseed2.binance.org', 
                    'https://bsc-dataseed3.binance.org',
                    'https://rpc.ankr.com/bsc',
                    'https://bsc.publicnode.com'
                ],
                'native_currency': 'BNB',
                'explorer': 'https://bscscan.com'
            },
            
            # Polygon
            'polygon': {
                'name': 'Polygon',
                'chain_id': 137,
                'rpc_urls': [
                    f'https://polygon-mainnet.g.alchemy.com/v2/{self.ALCHEMY_API_KEY}',
                    'https://polygon-rpc.com',
                    'https://rpc.ankr.com/polygon',
                    'https://polygon.publicnode.com',
                    'https://polygon-mainnet.public.blastapi.io'
                ],
                'native_currency': 'MATIC',
                'explorer': 'https://polygonscan.com'
            },
            
            # Arbitrum One
            'arbitrum': {
                'name': 'Arbitrum One',
                'chain_id': 42161,
                'rpc_urls': [
                    f'https://arb-mainnet.g.alchemy.com/v2/{self.ALCHEMY_API_KEY}',
                    'https://arbitrum-one.public.blastapi.io',
                    'https://rpc.ankr.com/arbitrum',
                    'https://arbitrum.publicnode.com'
                ],
                'native_currency': 'ETH',
                'explorer': 'https://arbiscan.io'
            },
            
            # Optimism
            'optimism': {
                'name': 'Optimism',
                'chain_id': 10,
                'rpc_urls': [
                    f'https://opt-mainnet.g.alchemy.com/v2/{self.ALCHEMY_API_KEY}',
                    'https://optimism.publicnode.com',
                    'https://rpc.ankr.com/optimism',
                    'https://optimism-mainnet.public.blastapi.io'
                ],
                'native_currency': 'ETH',
                'explorer': 'https://optimistic.etherscan.io'
            },
            
            # Avalanche C-Chain
            'avalanche': {
                'name': 'Avalanche C-Chain',
                'chain_id': 43114,
                'rpc_urls': [
                    'https://api.avax.network/ext/bc/C/rpc',
                    'https://rpc.ankr.com/avalanche',
                    'https://avalanche.publicnode.com',
                    'https://avalanche-c-chain.publicnode.com'
                ],
                'native_currency': 'AVAX',
                'explorer': 'https://snowtrace.io'
            },
            
            # Fantom
            'fantom': {
                'name': 'Fantom Opera',
                'chain_id': 250,
                'rpc_urls': [
                    'https://rpc.ftm.tools',
                    'https://rpc.ankr.com/fantom',
                    'https://fantom.publicnode.com',
                    'https://rpc.fantom.network'
                ],
                'native_currency': 'FTM',
                'explorer': 'https://ftmscan.com'
            },
            
            # Base
            'base': {
                'name': 'Base',
                'chain_id': 8453,
                'rpc_urls': [
                    'https://base.publicnode.com',
                    'https://rpc.ankr.com/base',
                    'https://base-mainnet.public.blastapi.io'
                ],
                'native_currency': 'ETH',
                'explorer': 'https://basescan.org'
            },
            
            # Cronos
            'cronos': {
                'name': 'Cronos',
                'chain_id': 25,
                'rpc_urls': [
                    'https://evm.cronos.org',
                    'https://cronos.publicnode.com',
                    'https://rpc.ankr.com/cronos'
                ],
                'native_currency': 'CRO',
                'explorer': 'https://cronoscan.com'
            },
            
            # Gnosis Chain
            'gnosis': {
                'name': 'Gnosis Chain',
                'chain_id': 100,
                'rpc_urls': [
                    'https://rpc.gnosischain.com',
                    'https://gnosis.publicnode.com',
                    'https://rpc.ankr.com/gnosis'
                ],
                'native_currency': 'xDAI',
                'explorer': 'https://gnosisscan.io'
            },
            
            # Celo
            'celo': {
                'name': 'Celo',
                'chain_id': 42220,
                'rpc_urls': [
                    'https://forno.celo.org',
                    'https://celo.publicnode.com',
                    'https://rpc.ankr.com/celo'
                ],
                'native_currency': 'CELO',
                'explorer': 'https://celoscan.io'
            },
            
            # Moonbeam
            'moonbeam': {
                'name': 'Moonbeam',
                'chain_id': 1284,
                'rpc_urls': [
                    'https://rpc.api.moonbeam.network',
                    'https://moonbeam.publicnode.com',
                    'https://rpc.ankr.com/moonbeam'
                ],
                'native_currency': 'GLMR',
                'explorer': 'https://moonscan.io'
            },
            
            # Aurora
            'aurora': {
                'name': 'Aurora',
                'chain_id': 1313161554,
                'rpc_urls': [
                    'https://mainnet.aurora.dev',
                    'https://aurora.publicnode.com'
                ],
                'native_currency': 'ETH',
                'explorer': 'https://aurorascan.dev'
            }
        }
        
        # 状态变量
        self.wallets: Dict[str, str] = {}  # address -> private_key
        self.target_wallet = ""
        self.monitored_addresses: Dict[str, Dict] = {}  # address -> {networks: [...], last_check: timestamp}
        self.monitoring = False
        self.monitor_thread = None
        self.password_hash = None
        
        # 文件路径
        self.wallet_file = "wallets.enc"
        self.state_file = "monitor_state.json"
        self.log_file = "monitor.log"
        
        # 配置参数
        self.monitor_interval = 30  # 监控间隔（秒）
        self.min_transfer_amount = 0.001  # 最小转账金额（ETH）
        self.gas_limit = 21000
        self.gas_price_gwei = 20
        
        # 设置日志
        self.setup_logging()
        
        # Web3连接
        self.web3_connections: Dict[str, Web3] = {}
        self.init_web3_connections()
        
        print(f"{Fore.CYAN}🔗 EVM监控软件已初始化{Style.RESET_ALL}")

    def setup_logging(self):
        """设置日志系统"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(self.log_file, encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)

    def init_web3_connections(self):
        """初始化Web3连接，支持多RPC端点故障转移"""
        print(f"{Fore.CYAN}🔗 正在连接区块链网络...{Style.RESET_ALL}")
        successful_connections = 0
        
        for network_key, network_info in self.networks.items():
            connected = False
            
            # 尝试连接多个RPC端点
            for i, rpc_url in enumerate(network_info['rpc_urls']):
                try:
                    w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={'timeout': 10}))
                    
                    # 测试连接并获取链ID验证
                    if w3.is_connected():
                        try:
                            chain_id = w3.eth.chain_id
                            if chain_id == network_info['chain_id']:
                                self.web3_connections[network_key] = w3
                                currency = network_info['native_currency']
                                print(f"{Fore.GREEN}✅ {network_info['name']} ({currency}) 连接成功 [RPC-{i+1}]{Style.RESET_ALL}")
                                connected = True
                                successful_connections += 1
                                break
                            else:
                                print(f"{Fore.YELLOW}⚠️ {network_info['name']} 链ID不匹配 (期望: {network_info['chain_id']}, 实际: {chain_id}){Style.RESET_ALL}")
                        except Exception as e:
                            print(f"{Fore.YELLOW}⚠️ {network_info['name']} 链ID验证失败: {e}{Style.RESET_ALL}")
                            continue
                    else:
                        continue
                        
                except Exception as e:
                    if i == len(network_info['rpc_urls']) - 1:  # 最后一个RPC也失败了
                        print(f"{Fore.RED}❌ {network_info['name']} 所有RPC连接失败{Style.RESET_ALL}")
                    continue
            
            if not connected:
                print(f"{Fore.RED}❌ {network_info['name']} 无法连接{Style.RESET_ALL}")
        
        print(f"\n{Fore.CYAN}🌐 网络连接总结: {successful_connections}/{len(self.networks)} 个网络连接成功{Style.RESET_ALL}")
        
        if successful_connections == 0:
            print(f"{Fore.RED}❌ 没有可用的网络连接，请检查网络设置{Style.RESET_ALL}")
        
        return successful_connections > 0

    def _derive_key(self, password: str, salt: bytes) -> bytes:
        """从密码派生加密密钥"""
        return PBKDF2(password, salt, 32, count=100000, hmac_hash_module=hashlib.sha256)

    def _encrypt_data(self, data: str, password: str) -> bytes:
        """加密数据"""
        salt = get_random_bytes(16)
        key = self._derive_key(password, salt)
        cipher = AES.new(key, AES.MODE_GCM)
        ciphertext, tag = cipher.encrypt_and_digest(data.encode())
        return salt + cipher.nonce + tag + ciphertext

    def _decrypt_data(self, encrypted_data: bytes, password: str) -> str:
        """解密数据"""
        salt = encrypted_data[:16]
        nonce = encrypted_data[16:32]
        tag = encrypted_data[32:48]
        ciphertext = encrypted_data[48:]
        
        key = self._derive_key(password, salt)
        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
        data = cipher.decrypt_and_verify(ciphertext, tag)
        return data.decode()

    def create_password(self, password: str) -> bool:
        """创建主密码"""
        try:
            self.password_hash = hashlib.sha256(password.encode()).hexdigest()
            return True
        except Exception as e:
            self.logger.error(f"创建密码失败: {e}")
            return False

    def verify_password(self, password: str) -> bool:
        """验证主密码"""
        if self.password_hash is None:
            return False
        return hashlib.sha256(password.encode()).hexdigest() == self.password_hash

    def add_private_key(self, private_key: str) -> Optional[str]:
        """添加私钥并返回对应的地址"""
        try:
            if not private_key.startswith('0x'):
                private_key = '0x' + private_key
            
            account = Account.from_key(private_key)
            address = account.address
            
            self.wallets[address] = private_key
            print(f"{Fore.GREEN}✅ 成功添加钱包地址: {address}{Style.RESET_ALL}")
            self.logger.info(f"添加钱包地址: {address}")
            return address
        except Exception as e:
            print(f"{Fore.RED}❌ 添加私钥失败: {e}{Style.RESET_ALL}")
            return None

    def save_wallets(self, password: str) -> bool:
        """保存钱包到加密文件"""
        try:
            data = json.dumps({
                'wallets': self.wallets,
                'password_hash': self.password_hash,
                'target_wallet': self.target_wallet
            })
            encrypted_data = self._encrypt_data(data, password)
            
            with open(self.wallet_file, 'wb') as f:
                f.write(encrypted_data)
            
            print(f"{Fore.GREEN}✅ 钱包已保存{Style.RESET_ALL}")
            return True
        except Exception as e:
            print(f"{Fore.RED}❌ 保存钱包失败: {e}{Style.RESET_ALL}")
            return False

    def load_wallets(self, password: str) -> bool:
        """从加密文件加载钱包"""
        try:
            if not os.path.exists(self.wallet_file):
                print(f"{Fore.YELLOW}⚠️ 钱包文件不存在，将创建新的钱包{Style.RESET_ALL}")
                return True
            
            with open(self.wallet_file, 'rb') as f:
                encrypted_data = f.read()
            
            decrypted_data = self._decrypt_data(encrypted_data, password)
            data = json.loads(decrypted_data)
            
            self.wallets = data.get('wallets', {})
            self.password_hash = data.get('password_hash')
            self.target_wallet = data.get('target_wallet', '')
            
            print(f"{Fore.GREEN}✅ 成功加载 {len(self.wallets)} 个钱包{Style.RESET_ALL}")
            return True
        except Exception as e:
            print(f"{Fore.RED}❌ 加载钱包失败: {e}{Style.RESET_ALL}")
            return False

    def save_state(self):
        """保存监控状态"""
        try:
            state = {
                'monitored_addresses': self.monitored_addresses,
                'last_save': datetime.now().isoformat()
            }
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            self.logger.error(f"保存状态失败: {e}")

    def load_state(self):
        """加载监控状态"""
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r') as f:
                    state = json.load(f)
                self.monitored_addresses = state.get('monitored_addresses', {})
                self.logger.info(f"恢复监控状态: {len(self.monitored_addresses)} 个地址")
        except Exception as e:
            self.logger.error(f"加载状态失败: {e}")

    def check_transaction_history(self, address: str, network: str) -> bool:
        """检查地址在指定网络上是否有交易历史"""
        try:
            if network not in self.web3_connections:
                return False
            
            w3 = self.web3_connections[network]
            
            # 检查交易数量
            tx_count = w3.eth.get_transaction_count(address)
            
            # 如果交易数量大于0，说明有交易历史
            has_history = tx_count > 0
            
            if has_history:
                print(f"{Fore.GREEN}✅ {address[:10]}... 在 {self.networks[network]['name']} 有 {tx_count} 笔交易{Style.RESET_ALL}")
            else:
                print(f"{Fore.YELLOW}⚠️ {address[:10]}... 在 {self.networks[network]['name']} 无交易历史{Style.RESET_ALL}")
            
            return has_history
        except Exception as e:
            self.logger.error(f"检查交易历史失败 {address} on {network}: {e}")
            return False

    def get_balance(self, address: str, network: str) -> Tuple[float, str]:
        """获取地址余额，返回(余额, 币种符号)"""
        try:
            if network not in self.web3_connections:
                return 0.0, "?"
            
            w3 = self.web3_connections[network]
            balance_wei = w3.eth.get_balance(address)
            balance = w3.from_wei(balance_wei, 'ether')
            currency = self.networks[network]['native_currency']
            
            return float(balance), currency
        except Exception as e:
            self.logger.error(f"获取余额失败 {address} on {network}: {e}")
            return 0.0, "?"

    def transfer_funds(self, from_address: str, private_key: str, to_address: str, amount: float, network: str) -> bool:
        """转账函数"""
        try:
            if network not in self.web3_connections:
                return False
            
            w3 = self.web3_connections[network]
            
            # 计算gas费用
            gas_price = w3.to_wei(self.gas_price_gwei, 'gwei')
            gas_cost = self.gas_limit * gas_price
            gas_cost_eth = w3.from_wei(gas_cost, 'ether')
            
            # 检查余额是否足够（包含gas费用）
            current_balance, currency = self.get_balance(from_address, network)
            if amount + float(gas_cost_eth) > current_balance:
                # 调整转账金额，留出gas费用
                amount = current_balance - float(gas_cost_eth) - 0.0001  # 多留一点余量
                if amount <= 0:
                    self.logger.warning(f"余额不足以支付gas费用: {from_address}")
                    return False
            
            # 构建交易
            nonce = w3.eth.get_transaction_count(from_address)
            
            transaction = {
                'to': to_address,
                'value': w3.to_wei(amount, 'ether'),
                'gas': self.gas_limit,
                'gasPrice': gas_price,
                'nonce': nonce,
                'chainId': self.networks[network]['chain_id']
            }
            
            # 签名交易
            signed_txn = w3.eth.account.sign_transaction(transaction, private_key)
            
            # 发送交易
            tx_hash = w3.eth.send_raw_transaction(signed_txn.rawTransaction)
            
            print(f"{Fore.GREEN}💸 转账成功: {amount:.6f} {currency} from {from_address[:10]}... to {to_address[:10]}...{Style.RESET_ALL}")
            print(f"{Fore.CYAN}📋 交易哈希: {tx_hash.hex()}{Style.RESET_ALL}")
            
            self.logger.info(f"转账成功: {amount} {currency}, {from_address} -> {to_address}, tx: {tx_hash.hex()}")
            return True
            
        except Exception as e:
            print(f"{Fore.RED}❌ 转账失败: {e}{Style.RESET_ALL}")
            self.logger.error(f"转账失败 {from_address} -> {to_address}: {e}")
            return False

    def scan_addresses(self):
        """扫描所有地址，检查交易历史并建立监控列表"""
        print(f"\n{Fore.CYAN}🔍 开始扫描地址交易历史...{Style.RESET_ALL}")
        
        for address in self.wallets.keys():
            print(f"\n检查地址: {address}")
            address_networks = []
            
            for network_key in self.networks.keys():
                if self.check_transaction_history(address, network_key):
                    address_networks.append(network_key)
            
            if address_networks:
                self.monitored_addresses[address] = {
                    'networks': address_networks,
                    'last_check': time.time()
                }
                print(f"{Fore.GREEN}✅ 添加到监控列表: {len(address_networks)} 个网络{Style.RESET_ALL}")
            else:
                print(f"{Fore.YELLOW}⚠️ 跳过监控（无交易历史）{Style.RESET_ALL}")
        
        print(f"\n{Fore.GREEN}✅ 扫描完成，将监控 {len(self.monitored_addresses)} 个地址{Style.RESET_ALL}")
        self.save_state()

    def monitor_loop(self):
        """监控循环"""
        print(f"\n{Fore.CYAN}🚀 开始监控...{Style.RESET_ALL}")
        
        while self.monitoring:
            try:
                for address, address_info in self.monitored_addresses.items():
                    if not self.monitoring:
                        break
                    
                    private_key = self.wallets.get(address)
                    if not private_key:
                        continue
                    
                    for network in address_info['networks']:
                        if not self.monitoring:
                            break
                        
                        balance, currency = self.get_balance(address, network)
                        
                        if balance > self.min_transfer_amount:
                            print(f"\n{Fore.YELLOW}💰 发现余额: {balance:.6f} {currency} in {address[:10]}... on {self.networks[network]['name']}{Style.RESET_ALL}")
                            
                            # 执行转账
                            if self.transfer_funds(address, private_key, self.target_wallet, balance, network):
                                # 更新最后检查时间
                                address_info['last_check'] = time.time()
                                self.save_state()
                        else:
                            # 显示余额状态
                            if balance > 0:
                                print(f"{Fore.BLUE}💎 {address[:10]}... on {self.networks[network]['name']}: {balance:.6f} {currency} (低于最小转账金额){Style.RESET_ALL}")
                
                # 等待下一次检查
                for i in range(self.monitor_interval):
                    if not self.monitoring:
                        break
                    time.sleep(1)
                    
            except KeyboardInterrupt:
                break
            except Exception as e:
                self.logger.error(f"监控循环错误: {e}")
                time.sleep(5)
        
        print(f"\n{Fore.RED}⏹️ 监控已停止{Style.RESET_ALL}")

    def start_monitoring(self):
        """开始监控"""
        if not self.target_wallet:
            print(f"{Fore.RED}❌ 请先设置目标钱包地址{Style.RESET_ALL}")
            return False
        
        if not self.wallets:
            print(f"{Fore.RED}❌ 没有钱包地址可监控{Style.RESET_ALL}")
            return False
        
        if self.monitoring:
            print(f"{Fore.YELLOW}⚠️ 监控已在运行中{Style.RESET_ALL}")
            return False
        
        # 扫描地址
        self.scan_addresses()
        
        if not self.monitored_addresses:
            print(f"{Fore.RED}❌ 没有符合条件的地址可监控{Style.RESET_ALL}")
            return False
        
        # 开始监控
        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self.monitor_loop)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()
        
        return True

    def stop_monitoring(self):
        """停止监控"""
        if not self.monitoring:
            print(f"{Fore.YELLOW}⚠️ 监控未在运行{Style.RESET_ALL}")
            return
        
        self.monitoring = False
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=5)
        
        print(f"{Fore.GREEN}✅ 监控已停止{Style.RESET_ALL}")

    def import_private_keys_from_file(self, file_path: str) -> int:
        """从文件批量导入私钥"""
        count = 0
        try:
            with open(file_path, 'r') as f:
                for line_num, line in enumerate(f, 1):
                    private_key = line.strip()
                    if private_key and self.add_private_key(private_key):
                        count += 1
                    
                    # 每100个显示一次进度
                    if line_num % 100 == 0:
                        print(f"已处理 {line_num} 行，成功导入 {count} 个钱包")
            
            print(f"{Fore.GREEN}✅ 批量导入完成: 成功导入 {count} 个钱包{Style.RESET_ALL}")
            return count
        except Exception as e:
            print(f"{Fore.RED}❌ 导入失败: {e}{Style.RESET_ALL}")
            return count

    def show_menu(self):
        """显示主菜单"""
        while True:
            print(f"\n{Fore.CYAN}{Back.BLACK} EVM监控软件主菜单 {Style.RESET_ALL}")
            print("=" * 50)
            print(f"{Fore.GREEN}1.{Style.RESET_ALL} 添加钱包私钥")
            print(f"{Fore.GREEN}2.{Style.RESET_ALL} 查看当前地址")
            print(f"{Fore.GREEN}3.{Style.RESET_ALL} 开始监控")
            print(f"{Fore.GREEN}4.{Style.RESET_ALL} 停止监控")
            print(f"{Fore.GREEN}5.{Style.RESET_ALL} 设置目标钱包地址")
            print(f"{Fore.GREEN}6.{Style.RESET_ALL} 批量导入私钥")
            print(f"{Fore.GREEN}7.{Style.RESET_ALL} 查看监控状态")
            print(f"{Fore.GREEN}8.{Style.RESET_ALL} 设置监控参数")
            print(f"{Fore.GREEN}9.{Style.RESET_ALL} 网络连接管理")
            print(f"{Fore.RED}0.{Style.RESET_ALL} 退出程序")
            print("=" * 50)
            
            # 显示状态信息
            status = f"{Fore.GREEN}运行中{Style.RESET_ALL}" if self.monitoring else f"{Fore.RED}已停止{Style.RESET_ALL}"
            print(f"当前状态: 监控 {status} | 钱包数量: {len(self.wallets)} | 监控地址: {len(self.monitored_addresses)}")
            if self.target_wallet:
                print(f"目标钱包: {self.target_wallet[:10]}...{self.target_wallet[-10:]}")
            
            try:
                choice = input(f"\n{Fore.YELLOW}请选择操作 (0-9): {Style.RESET_ALL}").strip()
                
                if choice == '1':
                    self.menu_add_private_key()
                elif choice == '2':
                    self.menu_show_addresses()
                elif choice == '3':
                    self.menu_start_monitoring()
                elif choice == '4':
                    self.menu_stop_monitoring()
                elif choice == '5':
                    self.menu_set_target_wallet()
                elif choice == '6':
                    self.menu_import_keys()
                elif choice == '7':
                    self.menu_show_status()
                elif choice == '8':
                    self.menu_settings()
                elif choice == '9':
                    self.menu_network_management()
                elif choice == '0':
                    self.menu_exit()
                    break
                else:
                    print(f"{Fore.RED}❌ 无效选择，请重试{Style.RESET_ALL}")
                    
            except KeyboardInterrupt:
                print(f"\n{Fore.YELLOW}👋 程序已退出{Style.RESET_ALL}")
                break
            except Exception as e:
                print(f"{Fore.RED}❌ 操作失败: {e}{Style.RESET_ALL}")

    def menu_add_private_key(self):
        """菜单：添加私钥"""
        print(f"\n{Fore.CYAN}📝 添加钱包私钥{Style.RESET_ALL}")
        private_key = input("请输入私钥: ").strip()
        if private_key:
            self.add_private_key(private_key)

    def menu_show_addresses(self):
        """菜单：显示地址"""
        print(f"\n{Fore.CYAN}📋 当前钱包地址列表{Style.RESET_ALL}")
        if not self.wallets:
            print(f"{Fore.YELLOW}⚠️ 暂无钱包地址{Style.RESET_ALL}")
            return
        
        for i, address in enumerate(self.wallets.keys(), 1):
            status = "🟢 监控中" if address in self.monitored_addresses else "🔴 未监控"
            print(f"{i:3d}. {address} {status}")

    def menu_start_monitoring(self):
        """菜单：开始监控"""
        print(f"\n{Fore.CYAN}🚀 开始监控{Style.RESET_ALL}")
        self.start_monitoring()

    def menu_stop_monitoring(self):
        """菜单：停止监控"""
        print(f"\n{Fore.CYAN}⏹️ 停止监控{Style.RESET_ALL}")
        self.stop_monitoring()

    def menu_set_target_wallet(self):
        """菜单：设置目标钱包"""
        print(f"\n{Fore.CYAN}🎯 设置目标钱包地址{Style.RESET_ALL}")
        if self.target_wallet:
            print(f"当前目标钱包: {self.target_wallet}")
        
        new_address = input("请输入新的目标钱包地址: ").strip()
        if new_address:
            if new_address.startswith('0x') and len(new_address) == 42:
                self.target_wallet = new_address
                print(f"{Fore.GREEN}✅ 目标钱包地址已设置{Style.RESET_ALL}")
            else:
                print(f"{Fore.RED}❌ 无效的钱包地址格式{Style.RESET_ALL}")

    def menu_import_keys(self):
        """菜单：批量导入私钥"""
        print(f"\n{Fore.CYAN}📁 批量导入私钥{Style.RESET_ALL}")
        file_path = input("请输入私钥文件路径: ").strip()
        if file_path and os.path.exists(file_path):
            self.import_private_keys_from_file(file_path)
        else:
            print(f"{Fore.RED}❌ 文件不存在{Style.RESET_ALL}")

    def menu_show_status(self):
        """菜单：显示监控状态"""
        print(f"\n{Fore.CYAN}📊 监控状态详情{Style.RESET_ALL}")
        print(f"总钱包数量: {len(self.wallets)}")
        print(f"监控地址数量: {len(self.monitored_addresses)}")
        print(f"监控状态: {'运行中' if self.monitoring else '已停止'}")
        print(f"目标钱包: {self.target_wallet}")
        print(f"监控间隔: {self.monitor_interval} 秒")
        print(f"最小转账金额: {self.min_transfer_amount} ETH")
        
        if self.monitored_addresses:
            print(f"\n{Fore.YELLOW}监控地址详情:{Style.RESET_ALL}")
            for addr, info in self.monitored_addresses.items():
                networks = ', '.join(info['networks'])
                last_check = datetime.fromtimestamp(info['last_check']).strftime('%Y-%m-%d %H:%M:%S')
                print(f"  {addr[:10]}... | 网络: {networks} | 最后检查: {last_check}")

    def menu_settings(self):
        """菜单：设置监控参数"""
        print(f"\n{Fore.CYAN}⚙️ 监控参数设置{Style.RESET_ALL}")
        print(f"1. 监控间隔: {self.monitor_interval} 秒")
        print(f"2. 最小转账金额: {self.min_transfer_amount} ETH")
        print(f"3. Gas价格: {self.gas_price_gwei} Gwei")
        
        choice = input("请选择要修改的参数 (1-3): ").strip()
        
        try:
            if choice == '1':
                new_interval = int(input("请输入新的监控间隔（秒）: "))
                if new_interval > 0:
                    self.monitor_interval = new_interval
                    print(f"{Fore.GREEN}✅ 监控间隔已设置为 {new_interval} 秒{Style.RESET_ALL}")
            elif choice == '2':
                new_amount = float(input("请输入新的最小转账金额（ETH）: "))
                if new_amount > 0:
                    self.min_transfer_amount = new_amount
                    print(f"{Fore.GREEN}✅ 最小转账金额已设置为 {new_amount} ETH{Style.RESET_ALL}")
            elif choice == '3':
                new_gas_price = int(input("请输入新的Gas价格（Gwei）: "))
                if new_gas_price > 0:
                    self.gas_price_gwei = new_gas_price
                    print(f"{Fore.GREEN}✅ Gas价格已设置为 {new_gas_price} Gwei{Style.RESET_ALL}")
        except ValueError:
            print(f"{Fore.RED}❌ 输入格式错误{Style.RESET_ALL}")

    def menu_network_management(self):
        """菜单：网络连接管理"""
        print(f"\n{Fore.CYAN}🌐 网络连接管理{Style.RESET_ALL}")
        print("=" * 50)
        
        # 显示所有网络状态
        connected_networks = []
        failed_networks = []
        
        for network_key, network_info in self.networks.items():
            status = "✅ 已连接" if network_key in self.web3_connections else "❌ 未连接"
            currency = network_info['native_currency']
            
            if network_key in self.web3_connections:
                connected_networks.append((network_key, network_info))
                color = Fore.GREEN
            else:
                failed_networks.append((network_key, network_info))
                color = Fore.RED
            
            print(f"{color}{network_info['name']} ({currency}) - {status}{Style.RESET_ALL}")
        
        print(f"\n{Fore.CYAN}连接统计:{Style.RESET_ALL}")
        print(f"✅ 已连接: {len(connected_networks)} 个网络")
        print(f"❌ 未连接: {len(failed_networks)} 个网络")
        
        if failed_networks:
            print(f"\n{Fore.YELLOW}重新连接失败的网络? (y/N): {Style.RESET_ALL}", end="")
            choice = input().strip().lower()
            if choice == 'y':
                print(f"{Fore.CYAN}正在重新连接...{Style.RESET_ALL}")
                self.init_web3_connections()
    
    def menu_exit(self):
        """菜单：退出程序"""
        print(f"\n{Fore.CYAN}👋 正在退出...{Style.RESET_ALL}")
        self.stop_monitoring()
        self.save_state()
        print(f"{Fore.GREEN}✅ 程序已安全退出{Style.RESET_ALL}")

def run_daemon_mode(monitor, password):
    """运行守护进程模式"""
    try:
        # 加载钱包和状态
        if not monitor.load_wallets(password):
            monitor.logger.error("加载钱包失败")
            return False
        
        monitor.load_state()
        monitor.logger.info(f"守护进程启动，已连接网络: {', '.join(monitor.web3_connections.keys())}")
        
        # 自动开始监控
        if monitor.start_monitoring():
            monitor.logger.info("监控已启动")
            
            # 保持程序运行
            try:
                while True:
                    time.sleep(60)
            except KeyboardInterrupt:
                monitor.logger.info("收到停止信号")
                monitor.stop_monitoring()
                monitor.save_state()
                return True
        else:
            monitor.logger.error("启动监控失败")
            return False
            
    except Exception as e:
        monitor.logger.error(f"守护进程错误: {e}")
        return False

def main():
    """主函数"""
    try:
        # 解析命令行参数
        import argparse
        parser = argparse.ArgumentParser(description='EVM钱包监控软件')
        parser.add_argument('--daemon', action='store_true', help='以守护进程模式运行')
        parser.add_argument('--password', type=str, help='钱包密码（仅用于守护进程模式）')
        args = parser.parse_args()
        
        # 创建监控实例
        monitor = EVMMonitor()
        
        # 守护进程模式
        if args.daemon:
            if not args.password:
                monitor.logger.error("守护进程模式需要提供密码参数")
                return
            return run_daemon_mode(monitor, args.password)
        
        # 交互模式
        while True:
            if os.path.exists(monitor.wallet_file):
                password = input(f"{Fore.YELLOW}请输入钱包密码: {Style.RESET_ALL}")
                if monitor.load_wallets(password):
                    break
                else:
                    print(f"{Fore.RED}❌ 密码错误或文件损坏{Style.RESET_ALL}")
            else:
                password = input(f"{Fore.YELLOW}创建新的钱包密码: {Style.RESET_ALL}")
                if monitor.create_password(password):
                    monitor.save_wallets(password)
                    break
        
        # 加载监控状态
        monitor.load_state()
        
        # 显示欢迎信息
        print(f"\n{Fore.GREEN}🎉 欢迎使用EVM监控软件！{Style.RESET_ALL}")
        print(f"已连接网络: {', '.join(monitor.web3_connections.keys())}")
        
        # 显示菜单
        monitor.show_menu()
        
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}👋 程序已退出{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}❌ 程序出错: {e}{Style.RESET_ALL}")

if __name__ == "__main__":
    main()
