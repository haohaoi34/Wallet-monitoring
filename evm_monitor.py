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
    import colorama
    from colorama import Fore, Style, Back
    import requests
except ImportError as e:
    print(f"❌ 导入依赖失败: {e}")
    print("请运行 start.sh 安装依赖")
    sys.exit(1)

# 初始化colorama
colorama.init()

class EVMMonitor:
    def __init__(self):
        # 配置
        self.ALCHEMY_API_KEY = "S0hs4qoXIR1SMD8P7I6Wt"
        
        # 支持的全链网络配置（Alchemy支持的所有EVM兼容链）
        self.networks = {
            # ==== 🌐 Layer 1 主网 ====
            'ethereum': {
                'name': '🔷 Ethereum Mainnet',
                'chain_id': 1,
                'rpc_urls': [
                    f'https://eth-mainnet.g.alchemy.com/v2/{self.ALCHEMY_API_KEY}',
                    'https://ethereum.publicnode.com',
                    'https://rpc.ankr.com/eth'
                ],
                'native_currency': 'ETH',
                'explorer': 'https://etherscan.io'
            },
            
            'bsc': {
                'name': '🟡 BNB Smart Chain',
                'chain_id': 56,
                'rpc_urls': [
                    'https://bsc-dataseed1.binance.org',
                    'https://bsc.publicnode.com',
                    'https://rpc.ankr.com/bsc'
                ],
                'native_currency': 'BNB',
                'explorer': 'https://bscscan.com'
            },
            
            'avalanche': {
                'name': '🏔️ Avalanche C-Chain',
                'chain_id': 43114,
                'rpc_urls': [
                    'https://api.avax.network/ext/bc/C/rpc',
                    'https://avalanche.public-rpc.com',
                    'https://rpc.ankr.com/avalanche'
                ],
                'native_currency': 'AVAX',
                'explorer': 'https://snowtrace.io'
            },
            
            'fantom': {
                'name': '👻 Fantom Opera',
                'chain_id': 250,
                'rpc_urls': [
                    'https://rpc.ftm.tools',
                    'https://fantom.publicnode.com',
                    'https://rpc.ankr.com/fantom'
                ],
                'native_currency': 'FTM',
                'explorer': 'https://ftmscan.com'
            },
            
            'cronos': {
                'name': '🦀 Cronos',
                'chain_id': 25,
                'rpc_urls': [
                    'https://evm.cronos.org',
                    'https://cronos.publicnode.com',
                    'https://rpc.ankr.com/cronos'
                ],
                'native_currency': 'CRO',
                'explorer': 'https://cronoscan.com'
            },
            
            'solana': {
                'name': '☀️ Solana',
                'chain_id': 792703809,
                'rpc_urls': [
                    f'https://solana-mainnet.g.alchemy.com/v2/{self.ALCHEMY_API_KEY}',
                    'https://api.mainnet-beta.solana.com'
                ],
                'native_currency': 'SOL',
                'explorer': 'https://explorer.solana.com'
            },
            
            'aptos': {
                'name': '🍎 Aptos',
                'chain_id': 1,
                'rpc_urls': [
                    f'https://aptos-mainnet.g.alchemy.com/v2/{self.ALCHEMY_API_KEY}',
                    'https://fullnode.mainnet.aptoslabs.com/v1'
                ],
                'native_currency': 'APT',
                'explorer': 'https://explorer.aptoslabs.com'
            },
            
            'gnosis': {
                'name': '🦉 Gnosis Chain',
                'chain_id': 100,
                'rpc_urls': [
                    'https://rpc.gnosischain.com',
                    'https://gnosis.publicnode.com',
                    'https://rpc.ankr.com/gnosis'
                ],
                'native_currency': 'xDAI',
                'explorer': 'https://gnosisscan.io'
            },
            
            'celo': {
                'name': 'Celo',
                'chain_id': 42220,
                'rpc_urls': [
                    'https://forno.celo.org',
                    'https://celo.publicnode.com',
                    'https://rpc.ankr.com/celo',
                    'https://celo.llamarpc.com'
                ],
                'native_currency': 'CELO',
                'explorer': 'https://celoscan.io'
            },
            
            'harmony': {
                'name': 'Harmony',
                'chain_id': 1666600000,
                'rpc_urls': [
                    'https://api.harmony.one',
                    'https://harmony.publicnode.com',
                    'https://rpc.ankr.com/harmony',
                    'https://harmony.llamarpc.com'
                ],
                'native_currency': 'ONE',
                'explorer': 'https://explorer.harmony.one'
            },
            
            'moonbeam': {
                'name': 'Moonbeam',
                'chain_id': 1284,
                'rpc_urls': [
                    'https://rpc.api.moonbeam.network',
                    'https://moonbeam.publicnode.com',
                    'https://rpc.ankr.com/moonbeam',
                    'https://moonbeam.llamarpc.com'
                ],
                'native_currency': 'GLMR',
                'explorer': 'https://moonscan.io'
            },
            
            'moonriver': {
                'name': 'Moonriver',
                'chain_id': 1285,
                'rpc_urls': [
                    'https://rpc.api.moonriver.moonbeam.network',
                    'https://moonriver.publicnode.com',
                    'https://rpc.ankr.com/moonriver',
                    'https://moonriver.llamarpc.com'
                ],
                'native_currency': 'MOVR',
                'explorer': 'https://moonriver.moonscan.io'
            },
            
            'klaytn': {
                'name': 'Klaytn',
                'chain_id': 8217,
                'rpc_urls': [
                    'https://public-node-api.klaytnapi.com/v1/cypress',
                    'https://klaytn.publicnode.com',
                    'https://rpc.ankr.com/klaytn',
                    'https://klaytn.llamarpc.com'
                ],
                'native_currency': 'KLAY',
                'explorer': 'https://scope.klaytn.com'
            },
            
            'aurora': {
                'name': 'Aurora',
                'chain_id': 1313161554,
                'rpc_urls': [
                    'https://mainnet.aurora.dev',
                    'https://aurora.publicnode.com',
                    'https://rpc.ankr.com/aurora',
                    'https://aurora.llamarpc.com'
                ],
                'native_currency': 'ETH',
                'explorer': 'https://aurorascan.dev'
            },
            
            'okx': {
                'name': 'OKX Chain',
                'chain_id': 66,
                'rpc_urls': [
                    'https://exchainrpc.okex.org',
                    'https://okx.publicnode.com',
                    'https://rpc.ankr.com/okx',
                    'https://okx.llamarpc.com'
                ],
                'native_currency': 'OKT',
                'explorer': 'https://www.oklink.com/okc'
            },
            
            'heco': {
                'name': 'Huobi ECO Chain',
                'chain_id': 128,
                'rpc_urls': [
                    'https://http-mainnet.hecochain.com',
                    'https://heco.publicnode.com',
                    'https://rpc.ankr.com/heco',
                    'https://heco.llamarpc.com'
                ],
                'native_currency': 'HT',
                'explorer': 'https://hecoinfo.com'
            },
            
            'metis': {
                'name': 'Metis Andromeda',
                'chain_id': 1088,
                'rpc_urls': [
                    'https://andromeda.metis.io/?owner=1088',
                    'https://metis.publicnode.com',
                    'https://rpc.ankr.com/metis',
                    'https://metis.llamarpc.com'
                ],
                'native_currency': 'METIS',
                'explorer': 'https://andromeda-explorer.metis.io'
            },
            
            'evmos': {
                'name': 'Evmos',
                'chain_id': 9001,
                'rpc_urls': [
                    'https://evmos-evm.publicnode.com',
                    'https://evmos.lava.build',
                    'https://rpc.ankr.com/evmos',
                    'https://evmos.llamarpc.com'
                ],
                'native_currency': 'EVMOS',
                'explorer': 'https://escan.live'
            },
            
            'kava': {
                'name': 'Kava EVM',
                'chain_id': 2222,
                'rpc_urls': [
                    'https://evm.kava.io',
                    'https://kava.publicnode.com',
                    'https://rpc.ankr.com/kava',
                    'https://kava.llamarpc.com'
                ],
                'native_currency': 'KAVA',
                'explorer': 'https://explorer.kava.io'
            },
            
            'telos': {
                'name': 'Telos EVM',
                'chain_id': 40,
                'rpc_urls': [
                    'https://mainnet.telos.net/evm',
                    'https://telos.publicnode.com',
                    'https://rpc.ankr.com/telos',
                    'https://telos.llamarpc.com'
                ],
                'native_currency': 'TLOS',
                'explorer': 'https://teloscan.io'
            },
            
            'astar': {
                'name': 'Astar',
                'chain_id': 592,
                'rpc_urls': [
                    'https://evm.astar.network',
                    'https://astar.publicnode.com',
                    'https://rpc.ankr.com/astar',
                    'https://astar.llamarpc.com'
                ],
                'native_currency': 'ASTR',
                'explorer': 'https://blockscout.com/astar'
            },
            
            'shiden': {
                'name': 'Shiden',
                'chain_id': 336,
                'rpc_urls': [
                    'https://shiden.public.blastapi.io',
                    'https://shiden.publicnode.com',
                    'https://rpc.ankr.com/shiden',
                    'https://shiden.llamarpc.com'
                ],
                'native_currency': 'SDN',
                'explorer': 'https://blockscout.com/shiden'
            },
            
            'boba': {
                'name': 'Boba Network',
                'chain_id': 288,
                'rpc_urls': [
                    'https://mainnet.boba.network',
                    'https://boba.publicnode.com',
                    'https://rpc.ankr.com/boba',
                    'https://boba.llamarpc.com'
                ],
                'native_currency': 'ETH',
                'explorer': 'https://bobascan.com'
            },
            
            'fuse': {
                'name': 'Fuse',
                'chain_id': 122,
                'rpc_urls': [
                    'https://rpc.fuse.io',
                    'https://fuse.publicnode.com',
                    'https://rpc.ankr.com/fuse',
                    'https://fuse.llamarpc.com'
                ],
                'native_currency': 'FUSE',
                'explorer': 'https://explorer.fuse.io'
            },
            
            # ==== 🌈 Layer 2 网络 ====
            'polygon': {
                'name': '🟣 Polygon PoS',
                'chain_id': 137,
                'rpc_urls': [
                    f'https://polygon-mainnet.g.alchemy.com/v2/{self.ALCHEMY_API_KEY}',
                    'https://polygon.llamarpc.com',
                    'https://polygon.publicnode.com'
                ],
                'native_currency': 'MATIC',
                'explorer': 'https://polygonscan.com'
            },
            
            'polygon_zkevm': {
                'name': '🟣 Polygon zkEVM',
                'chain_id': 1101,
                'rpc_urls': [
                    f'https://polygonzkevm-mainnet.g.alchemy.com/v2/{self.ALCHEMY_API_KEY}',
                    'https://zkevm-rpc.com'
                ],
                'native_currency': 'ETH',
                'explorer': 'https://zkevm.polygonscan.com'
            },
            
            'arbitrum': {
                'name': '🟦 Arbitrum One',
                'chain_id': 42161,
                'rpc_urls': [
                    f'https://arb-mainnet.g.alchemy.com/v2/{self.ALCHEMY_API_KEY}',
                    'https://arbitrum.llamarpc.com',
                    'https://arbitrum.publicnode.com'
                ],
                'native_currency': 'ETH',
                'explorer': 'https://arbiscan.io'
            },
            
            'arbitrum_nova': {
                'name': '🟦 Arbitrum Nova',
                'chain_id': 42170,
                'rpc_urls': [
                    f'https://arbnova-mainnet.g.alchemy.com/v2/{self.ALCHEMY_API_KEY}',
                    'https://nova.arbitrum.io/rpc'
                ],
                'native_currency': 'ETH',
                'explorer': 'https://nova.arbiscan.io'
            },
            
            'optimism': {
                'name': '🔴 Optimism',
                'chain_id': 10,
                'rpc_urls': [
                    f'https://opt-mainnet.g.alchemy.com/v2/{self.ALCHEMY_API_KEY}',
                    'https://optimism.llamarpc.com',
                    'https://optimism.publicnode.com'
                ],
                'native_currency': 'ETH',
                'explorer': 'https://optimistic.etherscan.io'
            },
            
            'base': {
                'name': '🟦 Base',
                'chain_id': 8453,
                'rpc_urls': [
                    f'https://base-mainnet.g.alchemy.com/v2/{self.ALCHEMY_API_KEY}',
                    'https://base.llamarpc.com',
                    'https://base.publicnode.com'
                ],
                'native_currency': 'ETH',
                'explorer': 'https://basescan.org'
            },
            
            'zksync': {
                'name': '⚡ zkSync Era',
                'chain_id': 324,
                'rpc_urls': [
                    f'https://zksync-mainnet.g.alchemy.com/v2/{self.ALCHEMY_API_KEY}',
                    'https://mainnet.era.zksync.io',
                    'https://zksync.llamarpc.com'
                ],
                'native_currency': 'ETH',
                'explorer': 'https://explorer.zksync.io'
            },
            
            'linea': {
                'name': '🟢 Linea',
                'chain_id': 59144,
                'rpc_urls': [
                    'https://linea.drpc.org',
                    'https://linea.llamarpc.com',
                    'https://linea.publicnode.com'
                ],
                'native_currency': 'ETH',
                'explorer': 'https://lineascan.build'
            },
            
            'mantle': {
                'name': '🧥 Mantle',
                'chain_id': 5000,
                'rpc_urls': [
                    'https://rpc.mantle.xyz',
                    'https://mantle.llamarpc.com',
                    'https://mantle.publicnode.com'
                ],
                'native_currency': 'MNT',
                'explorer': 'https://explorer.mantle.xyz'
            },
            
            'scroll': {
                'name': '📜 Scroll',
                'chain_id': 534352,
                'rpc_urls': [
                    'https://rpc.scroll.io',
                    'https://scroll.llamarpc.com',
                    'https://scroll.publicnode.com'
                ],
                'native_currency': 'ETH',
                'explorer': 'https://scrollscan.com'
            },
            
            'manta': {
                'name': '🦈 Manta Pacific',
                'chain_id': 169,
                'rpc_urls': [
                    'https://pacific.manta.network/http',
                    'https://manta.llamarpc.com',
                    'https://manta.publicnode.com'
                ],
                'native_currency': 'ETH',
                'explorer': 'https://pacific-explorer.manta.network'
            },
            
            'blast': {
                'name': '💥 Blast',
                'chain_id': 81457,
                'rpc_urls': [
                    f'https://blast-mainnet.g.alchemy.com/v2/{self.ALCHEMY_API_KEY}',
                    'https://rpc.blast.io',
                    'https://blast.llamarpc.com'
                ],
                'native_currency': 'ETH',
                'explorer': 'https://blastscan.io'
            },
            
            # ==== 🧪 测试网络 ====
            'ethereum_sepolia': {
                'name': '🧪 Ethereum Sepolia',
                'chain_id': 11155111,
                'rpc_urls': [
                    f'https://eth-sepolia.g.alchemy.com/v2/{self.ALCHEMY_API_KEY}',
                    'https://rpc.sepolia.org',
                    'https://sepolia.publicnode.com'
                ],
                'native_currency': 'ETH',
                'explorer': 'https://sepolia.etherscan.io'
            },
            
            'ethereum_holesky': {
                'name': '🧪 Ethereum Holesky',
                'chain_id': 17000,
                'rpc_urls': [
                    f'https://eth-holesky.g.alchemy.com/v2/{self.ALCHEMY_API_KEY}',
                    'https://holesky.drpc.org'
                ],
                'native_currency': 'ETH',
                'explorer': 'https://holesky.etherscan.io'
            },
            
            'polygon_amoy': {
                'name': '🧪 Polygon Amoy',
                'chain_id': 80002,
                'rpc_urls': [
                    f'https://polygon-amoy.g.alchemy.com/v2/{self.ALCHEMY_API_KEY}',
                    'https://rpc-amoy.polygon.technology'
                ],
                'native_currency': 'MATIC',
                'explorer': 'https://amoy.polygonscan.com'
            },
            
            'arbitrum_sepolia': {
                'name': '🧪 Arbitrum Sepolia',
                'chain_id': 421614,
                'rpc_urls': [
                    f'https://arb-sepolia.g.alchemy.com/v2/{self.ALCHEMY_API_KEY}',
                    'https://sepolia-rollup.arbitrum.io/rpc'
                ],
                'native_currency': 'ETH',
                'explorer': 'https://sepolia.arbiscan.io'
            },
            
            'optimism_sepolia': {
                'name': '🧪 Optimism Sepolia',
                'chain_id': 11155420,
                'rpc_urls': [
                    f'https://opt-sepolia.g.alchemy.com/v2/{self.ALCHEMY_API_KEY}',
                    'https://sepolia.optimism.io'
                ],
                'native_currency': 'ETH',
                'explorer': 'https://sepolia-optimistic.etherscan.io'
            },
            
            'base_sepolia': {
                'name': '🧪 Base Sepolia',
                'chain_id': 84532,
                'rpc_urls': [
                    f'https://base-sepolia.g.alchemy.com/v2/{self.ALCHEMY_API_KEY}',
                    'https://sepolia.base.org'
                ],
                'native_currency': 'ETH',
                'explorer': 'https://sepolia.basescan.org'
            },
            
            'blast_sepolia': {
                'name': '🧪 Blast Sepolia',
                'chain_id': 168587773,
                'rpc_urls': [
                    f'https://blast-sepolia.g.alchemy.com/v2/{self.ALCHEMY_API_KEY}',
                    'https://sepolia.blast.io'
                ],
                'native_currency': 'ETH',
                'explorer': 'https://testnet.blastscan.io'
            },
            
            'zksync_sepolia': {
                'name': '🧪 zkSync Sepolia',
                'chain_id': 300,
                'rpc_urls': [
                    f'https://zksync-sepolia.g.alchemy.com/v2/{self.ALCHEMY_API_KEY}',
                    'https://sepolia.era.zksync.dev'
                ],
                'native_currency': 'ETH',
                'explorer': 'https://sepolia.explorer.zksync.io'
            },
            
            'polygon_zkevm_testnet': {
                'name': '🧪 Polygon zkEVM Testnet',
                'chain_id': 1442,
                'rpc_urls': [
                    f'https://polygonzkevm-testnet.g.alchemy.com/v2/{self.ALCHEMY_API_KEY}',
                    'https://rpc.public.zkevm-test.net'
                ],
                'native_currency': 'ETH',
                'explorer': 'https://testnet-zkevm.polygonscan.com'
            }

        }
        
        # 状态变量
        self.wallets: Dict[str, str] = {}  # address -> private_key
        self.target_wallet = ""  # 固定目标账户
        self.monitored_addresses: Dict[str, Dict] = {}  # address -> {networks: [...], last_check: timestamp}
        self.monitoring = False
        self.monitor_thread = None
        
        # 文件路径
        self.wallet_file = "wallets.json"
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
    
    def safe_input(self, prompt: str = "") -> str:
        """安全的输入函数，处理EOF错误"""
        try:
            # 强制使用交互式模式
            import sys
            if not sys.stdin.isatty():
                # 非交互式环境，返回默认值
                if "选项" in prompt or "选择" in prompt:
                    print(f"{Fore.YELLOW}⚠️  非交互式环境，自动退出{Style.RESET_ALL}")
                    return "0"
                else:
                    print(f"{Fore.YELLOW}⚠️  非交互式环境，使用空值{Style.RESET_ALL}")
                    return ""
            
            # 交互式环境，正常读取输入
            return input(prompt)
        except EOFError:
            print(f"\n{Fore.YELLOW}⚠️  EOF错误，自动退出{Style.RESET_ALL}")
            if "选项" in prompt or "选择" in prompt:
                return "0"  # 退出菜单
            return ""
        except KeyboardInterrupt:
            print(f"\n{Fore.YELLOW}👋 用户取消操作{Style.RESET_ALL}")
            return "0"  # 返回退出选项

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
                            # 跳过特殊链ID（如非EVM链）
                            if network_info['chain_id'] == 0:
                                print(f"{Fore.YELLOW}⚠️ {network_info['name']} 暂不支持 (非标准EVM链){Style.RESET_ALL}")
                                continue
                                
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



    def add_private_key(self, private_key: str) -> Optional[str]:
        """添加私钥并返回对应的地址（自动去重）"""
        try:
            if not private_key.startswith('0x'):
                private_key = '0x' + private_key
            
            account = Account.from_key(private_key)
            address = account.address
            
            # 检查是否已存在（去重）
            if address in self.wallets:
                print(f"{Fore.YELLOW}⚠️ 钱包地址已存在: {address}{Style.RESET_ALL}")
                return address
            
            self.wallets[address] = private_key
            print(f"{Fore.GREEN}✅ 成功添加钱包地址: {address}{Style.RESET_ALL}")
            self.logger.info(f"添加钱包地址: {address}")
            
            # 自动保存钱包
            self.save_wallets()
            
            return address
        except Exception as e:
            print(f"{Fore.RED}❌ 添加私钥失败: {e}{Style.RESET_ALL}")
            return None

    def save_wallets(self) -> bool:
        """保存钱包到JSON文件"""
        try:
            data = {
                'wallets': self.wallets,
                'target_wallet': self.target_wallet
            }
            
            with open(self.wallet_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            self.logger.info(f"钱包已保存: {len(self.wallets)} 个地址")
            return True
        except Exception as e:
            print(f"{Fore.RED}❌ 保存钱包失败: {e}{Style.RESET_ALL}")
            return False

    def load_wallets(self) -> bool:
        """从JSON文件加载钱包"""
        try:
            if not os.path.exists(self.wallet_file):
                print(f"{Fore.YELLOW}⚠️ 钱包文件不存在，将创建新的钱包{Style.RESET_ALL}")
                return True
            
            with open(self.wallet_file, 'r') as f:
                data = json.load(f)
            
            self.wallets = data.get('wallets', {})
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
                print(f"{Fore.RED}❌ 网络 {network} 未连接{Style.RESET_ALL}")
                return False
            
            w3 = self.web3_connections[network]
            
            # 验证地址格式
            try:
                to_address = w3.to_checksum_address(to_address)
                from_address = w3.to_checksum_address(from_address)
            except Exception as e:
                print(f"{Fore.RED}❌ 地址格式错误: {e}{Style.RESET_ALL}")
                return False
            
            # 检查是否是自己转给自己
            if from_address.lower() == to_address.lower():
                print(f"{Fore.YELLOW}⚠️ 跳过自己转给自己的交易{Style.RESET_ALL}")
                return False
            
            # 获取最新gas价格
            try:
                gas_price = w3.eth.gas_price
                # 如果网络返回的gas价格太低，使用我们设置的最小gas价格
                min_gas_price = w3.to_wei(self.gas_price_gwei, 'gwei')
                gas_price = max(gas_price, min_gas_price)
            except:
                gas_price = w3.to_wei(self.gas_price_gwei, 'gwei')
            
            # 计算gas费用
            gas_cost = self.gas_limit * gas_price
            gas_cost_eth = w3.from_wei(gas_cost, 'ether')
            
            # 检查余额是否足够（包含gas费用）
            current_balance, currency = self.get_balance(from_address, network)
            if amount + float(gas_cost_eth) > current_balance:
                # 调整转账金额，留出gas费用
                amount = current_balance - float(gas_cost_eth) - 0.0001  # 多留一点余量
                if amount <= 0:
                    print(f"{Fore.YELLOW}⚠️ 余额不足以支付gas费用: {from_address[:10]}...{Style.RESET_ALL}")
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
            
        except KeyboardInterrupt:
            print(f"\n{Fore.YELLOW}⚠️ 用户取消转账操作{Style.RESET_ALL}")
            raise  # 重新抛出以便上层函数处理
        except Exception as e:
            print(f"{Fore.RED}❌ 转账失败: {e}{Style.RESET_ALL}")
            self.logger.error(f"转账失败 {from_address} -> {to_address}: {e}")
            # 详细错误信息
            if "invalid fields" in str(e).lower():
                print(f"{Fore.CYAN}💡 提示：地址格式可能有问题，正在检查...{Style.RESET_ALL}")
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
        print(f"{Fore.YELLOW}📝 提示：按 Ctrl+C 可以优雅退出监控{Style.RESET_ALL}")
        
        try:
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
                            
                            try:
                                balance, currency = self.get_balance(address, network)
                                
                                if balance > self.min_transfer_amount:
                                    print(f"\n{Fore.YELLOW}💰 发现余额: {balance:.6f} {currency} in {address[:10]}... on {self.networks[network]['name']}{Style.RESET_ALL}")
                                    
                                    # 转账到固定目标账户
                                    if self.target_wallet:
                                        try:
                                            if self.transfer_funds(address, private_key, self.target_wallet, balance, network):
                                                # 更新最后检查时间
                                                address_info['last_check'] = time.time()
                                                self.save_state()
                                        except KeyboardInterrupt:
                                            print(f"\n{Fore.YELLOW}⚠️ 用户取消转账，停止监控{Style.RESET_ALL}")
                                            self.monitoring = False
                                            return
                                    else:
                                        print(f"{Fore.CYAN}💡 未设置目标账户，跳过转账{Style.RESET_ALL}")
                                else:
                                    # 显示余额状态
                                    if balance > 0:
                                        print(f"{Fore.BLUE}💎 {address[:10]}... on {self.networks[network]['name']}: {balance:.6f} {currency} (低于最小转账金额){Style.RESET_ALL}")
                            except KeyboardInterrupt:
                                print(f"\n{Fore.YELLOW}⚠️ 监控被中断{Style.RESET_ALL}")
                                self.monitoring = False
                                return
                            except Exception as e:
                                print(f"{Fore.RED}❌ 检查余额失败 {address[:10]}... on {network}: {e}{Style.RESET_ALL}")
                                continue
                    
                    # 等待下一次检查（支持中断）
                    for i in range(self.monitor_interval):
                        if not self.monitoring:
                            break
                        try:
                            time.sleep(1)
                        except KeyboardInterrupt:
                            print(f"\n{Fore.YELLOW}⚠️ 监控被中断{Style.RESET_ALL}")
                            self.monitoring = False
                            return
                        
                except KeyboardInterrupt:
                    print(f"\n{Fore.YELLOW}⚠️ 监控被中断{Style.RESET_ALL}")
                    break
                except Exception as e:
                    self.logger.error(f"监控循环错误: {e}")
                    print(f"{Fore.RED}❌ 监控循环出错，5秒后重试: {e}{Style.RESET_ALL}")
                    try:
                        time.sleep(5)
                    except KeyboardInterrupt:
                        print(f"\n{Fore.YELLOW}⚠️ 监控被中断{Style.RESET_ALL}")
                        break
        
        except KeyboardInterrupt:
            print(f"\n{Fore.YELLOW}⚠️ 监控被中断{Style.RESET_ALL}")
        finally:
            self.monitoring = False
            print(f"\n{Fore.GREEN}✅ 监控已优雅停止{Style.RESET_ALL}")
            self.save_state()  # 保存状态

    def start_monitoring(self):
        """开始监控"""
        if not self.wallets:
            print(f"{Fore.RED}❌ 没有钱包地址可监控{Style.RESET_ALL}")
            return False
        
        if self.monitoring:
            print(f"{Fore.YELLOW}⚠️ 监控已在运行中{Style.RESET_ALL}")
            return False
        
        if not self.target_wallet:
            print(f"{Fore.YELLOW}⚠️ 未设置目标账户，请先设置目标账户{Style.RESET_ALL}")
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
        
        print(f"{Fore.CYAN}🔄 正在停止监控...{Style.RESET_ALL}")
        self.monitoring = False
        
        if self.monitor_thread and self.monitor_thread.is_alive():
            print(f"{Fore.YELLOW}⏳ 等待监控线程结束...{Style.RESET_ALL}")
            self.monitor_thread.join(timeout=10)  # 增加等待时间
            
            if self.monitor_thread.is_alive():
                print(f"{Fore.YELLOW}⚠️ 监控线程未能正常结束，强制停止{Style.RESET_ALL}")
        
        self.save_state()  # 保存状态
        print(f"{Fore.GREEN}✅ 监控已安全停止{Style.RESET_ALL}")

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
            # 清屏
            os.system('clear' if os.name != 'nt' else 'cls')
            
            print(f"{Fore.CYAN}╔══════════════════════════════════════════════╗{Style.RESET_ALL}")
            print(f"{Fore.CYAN}║           🚀 EVM钱包监控软件                   ║{Style.RESET_ALL}")
            print(f"{Fore.CYAN}╚══════════════════════════════════════════════╝{Style.RESET_ALL}")
            
            # 显示当前状态
            status_color = Fore.GREEN if self.monitoring else Fore.RED
            status_text = "🟢 监控中" if self.monitoring else "🔴 已停止"
            
            print(f"\n📊 {Fore.CYAN}当前状态:{Style.RESET_ALL}")
            print(f"   监控状态: {status_color}{status_text}{Style.RESET_ALL}")
            print(f"   钱包数量: {Fore.YELLOW}{len(self.wallets)}{Style.RESET_ALL} 个")
            print(f"   监控地址: {Fore.YELLOW}{len(self.monitored_addresses)}{Style.RESET_ALL} 个")
            print(f"   网络连接: {Fore.YELLOW}{len(self.web3_connections)}{Style.RESET_ALL} 个")
            
            if self.target_wallet:
                print(f"   🎯 目标账户: {Fore.GREEN}{self.target_wallet[:10]}...{self.target_wallet[-8:]}{Style.RESET_ALL}")
            else:
                print(f"   🎯 目标账户: {Fore.RED}未设置{Style.RESET_ALL}")
            
            print(f"\n{Fore.CYAN}━━━━━━━━━━━━━━ 主要功能 ━━━━━━━━━━━━━━{Style.RESET_ALL}")
            
            if len(self.wallets) == 0:
                print(f"{Fore.YELLOW}💡 新手指南: 先添加钱包私钥，然后开始监控{Style.RESET_ALL}")
            
            print(f"{Fore.GREEN}1.{Style.RESET_ALL} 🔑 添加钱包私钥 {Fore.BLUE}(支持批量粘贴){Style.RESET_ALL}")
            print(f"{Fore.GREEN}2.{Style.RESET_ALL} 📋 查看钱包列表")
            
            if not self.monitoring:
                print(f"{Fore.GREEN}3.{Style.RESET_ALL} ▶️  开始监控")
            else:
                print(f"{Fore.YELLOW}3.{Style.RESET_ALL} ⏸️  停止监控")
            
            print(f"{Fore.GREEN}4.{Style.RESET_ALL} 🎯 设置目标账户")
            print(f"{Fore.GREEN}5.{Style.RESET_ALL} 📁 从文件导入")
            
            print(f"\n{Fore.CYAN}━━━━━━━━━━━━━━ 🔧 高级功能 ━━━━━━━━━━━━━━{Style.RESET_ALL}")
            print(f"{Fore.GREEN}6.{Style.RESET_ALL} 📊 监控状态详情")
            print(f"{Fore.GREEN}7.{Style.RESET_ALL} ⚙️  监控参数设置")
            print(f"{Fore.GREEN}8.{Style.RESET_ALL} 🌐 网络连接管理")
            
            print(f"\n{Fore.RED}0.{Style.RESET_ALL} 🚪 退出程序")
            print(f"{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}")
            
            try:
                choice = self.safe_input(f"\n{Fore.YELLOW}请输入选项数字: {Style.RESET_ALL}").strip()
                
                # 如果返回空值或默认退出，直接退出
                if choice == "" or choice == "0":
                    print(f"\n{Fore.YELLOW}👋 程序退出{Style.RESET_ALL}")
                    break
                
                if choice == '1':
                    self.menu_add_private_key()
                elif choice == '2':
                    self.menu_show_addresses()
                elif choice == '3':
                    if self.monitoring:
                        self.menu_stop_monitoring()
                    else:
                        self.menu_start_monitoring()
                elif choice == '4':
                    self.menu_set_target_wallet()
                elif choice == '5':
                    self.menu_import_keys()
                elif choice == '6':
                    self.menu_show_status()
                elif choice == '7':
                    self.menu_settings()
                elif choice == '8':
                    self.menu_network_management()
                elif choice == '0':
                    self.menu_exit()
                    break
                else:
                    print(f"{Fore.RED}❌ 无效选择，请重试{Style.RESET_ALL}")
                    input(f"{Fore.YELLOW}按回车键继续...{Style.RESET_ALL}")
                    
            except KeyboardInterrupt:
                print(f"\n{Fore.YELLOW}👋 程序已退出{Style.RESET_ALL}")
                break
            except EOFError:
                print(f"\n{Fore.YELLOW}👋 检测到EOF，程序退出{Style.RESET_ALL}")
                break
            except Exception as e:
                print(f"{Fore.RED}❌ 操作失败: {e}{Style.RESET_ALL}")
                print(f"{Fore.YELLOW}⚠️  按任意键继续或稍后重试...{Style.RESET_ALL}")
                try:
                    self.safe_input()
                except:
                    print(f"{Fore.YELLOW}继续运行...{Style.RESET_ALL}")
                    pass

    def menu_add_private_key(self):
        """菜单：添加私钥"""
        print(f"\n{Fore.CYAN}✨ ====== 🔑 添加钱包私钥 🔑 ====== ✨{Style.RESET_ALL}")
        print(f"{Back.YELLOW}{Fore.BLACK} 📝 支持单个私钥或批量粘贴多个私钥（每行一个） {Style.RESET_ALL}")
        print(f"{Back.GREEN}{Fore.BLACK} ✨ 输入完成后双击回车确认 ✨ {Style.RESET_ALL}")
        print(f"\n{Fore.GREEN}🔍 请输入私钥：{Style.RESET_ALL}")
        
        lines = []
        empty_line_count = 0
        
        while True:
            try:
                line = self.safe_input().strip()
                if line:
                    lines.append(line)
                    empty_line_count = 0
                else:
                    empty_line_count += 1
                    if empty_line_count >= 2:  # 双击回车
                        break
            except EOFError:
                break
        
        if lines:
            success_count = 0
            for private_key in lines:
                if self.add_private_key(private_key):
                    success_count += 1
            
            print(f"\n{Fore.GREEN}🎉 批量导入完成：成功添加 {success_count}/{len(lines)} 个钱包！{Style.RESET_ALL}")
            if success_count > 0:
                print(f"{Fore.CYAN}✨ 已自动去重，跳过 {len(lines) - success_count} 个重复地址{Style.RESET_ALL}")
            else:
                print(f"{Fore.YELLOW}⚠️  未成功添加任何新钱包（可能都是重复或无效的）{Style.RESET_ALL}")
        else:
            print(f"\n{Fore.YELLOW}⚠️  未输入任何私钥{Style.RESET_ALL}")
        
        self.safe_input(f"\n{Fore.MAGENTA}🔙 按回车键返回主菜单...{Style.RESET_ALL}")

    def menu_show_addresses(self):
        """菜单：显示地址"""
        print(f"\n{Fore.CYAN}✨ ====== 📋 钱包地址列表 📋 ====== ✨{Style.RESET_ALL}")
        
        if not self.wallets:
            print(f"\n{Fore.YELLOW}😭 暂无钱包地址，请先添加钱包{Style.RESET_ALL}")
            print(f"{Fore.CYAN}💡 提示：使用菜单选项 1 添加私钥{Style.RESET_ALL}")
        else:
            print(f"\n{Fore.GREEN}💼 共有 {len(self.wallets)} 个钱包地址：{Style.RESET_ALL}")
            print(f"{Fore.CYAN}─" * 80 + f"{Style.RESET_ALL}")
            
            for i, address in enumerate(self.wallets.keys(), 1):
                status = f"{Fore.GREEN}🟢 监控中{Style.RESET_ALL}" if address in self.monitored_addresses else f"{Fore.RED}🔴 未监控{Style.RESET_ALL}"
                
                # 显示缩短的地址
                short_address = f"{address[:8]}...{address[-6:]}"
                print(f"{Fore.YELLOW}{i:2d}.{Style.RESET_ALL} {Fore.WHITE}{short_address}{Style.RESET_ALL} {status}")
                
                # 每5个地址显示一次分割线
                if i % 5 == 0 and i < len(self.wallets):
                    print(f"{Fore.CYAN}─" * 40 + f"{Style.RESET_ALL}")
        
        self.safe_input(f"\n{Fore.MAGENTA}🔙 按回车键返回主菜单...{Style.RESET_ALL}")

    def menu_start_monitoring(self):
        """菜单：开始监控"""
        print(f"\n{Fore.CYAN}✨ ====== 🚀 开始监控 🚀 ====== ✨{Style.RESET_ALL}")
        print(f"{Back.GREEN}{Fore.BLACK} 🔍 正在检查系统状态... {Style.RESET_ALL}")
        
        if self.start_monitoring():
            print(f"\n{Fore.GREEN}🎉 监控已成功启动！{Style.RESET_ALL}")
            print(f"{Fore.CYAN}🔄 系统将自动监控所有钱包余额并转账到目标账户{Style.RESET_ALL}")
        else:
            print(f"\n{Fore.RED}❌ 监控启动失败！{Style.RESET_ALL}")
        
        self.safe_input(f"\n{Fore.MAGENTA}🔙 按回车键返回主菜单...{Style.RESET_ALL}")

    def menu_stop_monitoring(self):
        """菜单：停止监控"""
        print(f"\n{Fore.CYAN}✨ ====== ⏹️ 停止监控 ⏹️ ====== ✨{Style.RESET_ALL}")
        print(f"{Back.RED}{Fore.WHITE} ⚠️ 正在安全停止监控系统... {Style.RESET_ALL}")
        
        self.stop_monitoring()
        print(f"\n{Fore.GREEN}✅ 监控已安全停止{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}💾 所有数据已保存{Style.RESET_ALL}")
        
        self.safe_input(f"\n{Fore.MAGENTA}🔙 按回车键返回主菜单...{Style.RESET_ALL}")



    def menu_set_target_wallet(self):
        """菜单：设置目标账户"""
        print(f"\n{Fore.CYAN}✨ ====== 🎯 设置目标账户 🎯 ====== ✨{Style.RESET_ALL}")
        print(f"{Back.BLUE}{Fore.WHITE} 📝 提示：所有监控到的余额将自动转账到这个地址 {Style.RESET_ALL}")
        
        if self.target_wallet:
            print(f"\n💼 当前目标账户: {Fore.GREEN}{self.target_wallet}{Style.RESET_ALL}")
        else:
            print(f"\n⚠️  当前状态: {Fore.RED}未设置目标账户{Style.RESET_ALL}")
        
        print(f"\n{Fore.YELLOW}🔍 请输入新的目标钱包地址：{Style.RESET_ALL}")
        new_address = self.safe_input(f"{Fore.CYAN}➜ {Style.RESET_ALL}").strip()
        
        if new_address:
            if new_address.startswith('0x') and len(new_address) == 42:
                self.target_wallet = new_address
                self.save_wallets()  # 保存更新
                print(f"\n{Fore.GREEN}✅ 成功！目标账户已设置为: {new_address}{Style.RESET_ALL}")
                print(f"{Fore.CYAN}🚀 现在就可以开始监控转账了！{Style.RESET_ALL}")
            else:
                print(f"\n{Fore.RED}❌ 错误！无效的钱包地址格式{Style.RESET_ALL}")
                print(f"{Fore.YELLOW}📝 正确格式示例: 0x1234567890abcdef1234567890abcdef12345678{Style.RESET_ALL}")
        else:
            print(f"\n{Fore.YELLOW}⚠️  取消设置{Style.RESET_ALL}")
        
        self.safe_input(f"\n{Fore.MAGENTA}🔙 按回车键返回主菜单...{Style.RESET_ALL}")
    
    def menu_import_keys(self):
        """菜单：批量导入私钥"""
        print(f"\n{Fore.CYAN}✨ ====== 📁 批量导入私钥 📁 ====== ✨{Style.RESET_ALL}")
        print(f"{Back.GREEN}{Fore.BLACK} 📝 支持的文件格式：每行一个私钥 (.txt文件) {Style.RESET_ALL}")
        
        print(f"\n{Fore.YELLOW}📂 请输入私钥文件路径：{Style.RESET_ALL}")
        file_path = self.safe_input(f"{Fore.CYAN}➜ {Style.RESET_ALL}").strip()
        
        if file_path and os.path.exists(file_path):
            print(f"\n{Fore.BLUE}🔄 正在导入私钥...{Style.RESET_ALL}")
            count = self.import_private_keys_from_file(file_path)
            if count > 0:
                print(f"\n{Fore.GREEN}🎉 导入成功！共添加 {count} 个钱包{Style.RESET_ALL}")
            else:
                print(f"\n{Fore.YELLOW}⚠️  未成功导入任何钱包{Style.RESET_ALL}")
        else:
            print(f"\n{Fore.RED}❌ 错误！文件不存在 或 路径无效{Style.RESET_ALL}")
        
        self.safe_input(f"\n{Fore.MAGENTA}🔙 按回车键返回主菜单...{Style.RESET_ALL}")

    def menu_show_status(self):
        """菜单：显示监控状态"""
        print(f"\n{Fore.CYAN}✨ ====== 📊 系统状态详情 📊 ====== ✨{Style.RESET_ALL}")
        
        # 基本信息
        print(f"\n{Fore.YELLOW}💼 基本信息：{Style.RESET_ALL}")
        print(f"  🔑 总钱包数量: {Fore.GREEN}{len(self.wallets)}{Style.RESET_ALL} 个")
        print(f"  🔍 监控地址: {Fore.GREEN}{len(self.monitored_addresses)}{Style.RESET_ALL} 个")
        print(f"  🌐 网络连接: {Fore.GREEN}{len(self.web3_connections)}{Style.RESET_ALL} 个")
        
        # 监控状态
        status_color = Fore.GREEN if self.monitoring else Fore.RED
        status_icon = "🟢" if self.monitoring else "🔴"
        status_text = "运行中" if self.monitoring else "已停止"
        print(f"\n{Fore.YELLOW}🔄 监控状态：{Style.RESET_ALL}")
        print(f"  {status_icon} 状态: {status_color}{status_text}{Style.RESET_ALL}")
        
        # 转账配置
        print(f"\n{Fore.YELLOW}💸 转账配置：{Style.RESET_ALL}")
        if self.target_wallet:
            print(f"  🎯 目标账户: {Fore.GREEN}{self.target_wallet[:10]}...{self.target_wallet[-8:]}{Style.RESET_ALL}")
        else:
            print(f"  🎯 目标账户: {Fore.RED}未设置{Style.RESET_ALL}")
        print(f"  ⏱️ 监控间隔: {Fore.GREEN}{self.monitor_interval}{Style.RESET_ALL} 秒")
        print(f"  💰 最小转账: {Fore.GREEN}{self.min_transfer_amount}{Style.RESET_ALL} ETH")
        
        if self.monitored_addresses:
            print(f"\n{Fore.YELLOW}监控地址详情:{Style.RESET_ALL}")
            for addr, info in self.monitored_addresses.items():
                networks = ', '.join(info['networks'])
                last_check = datetime.fromtimestamp(info['last_check']).strftime('%Y-%m-%d %H:%M:%S')
                print(f"  💵 {addr[:8]}...{addr[-6:]} | 🌐 {networks} | 🕒 {last_check}")
        
        self.safe_input(f"\n{Fore.MAGENTA}🔙 按回车键返回主菜单...{Style.RESET_ALL}")

    def menu_settings(self):
        """菜单：设置监控参数"""
        print(f"\n{Fore.CYAN}✨ ====== ⚙️ 监控参数设置 ⚙️ ====== ✨{Style.RESET_ALL}")
        print(f"{Back.BLUE}{Fore.WHITE} 📝 当前配置参数如下，可按需要修改 {Style.RESET_ALL}")
        
        print(f"\n{Fore.YELLOW}🔧 可修改的参数：{Style.RESET_ALL}")
        print(f"  {Fore.GREEN}1.{Style.RESET_ALL} ⏱️ 监控间隔: {Fore.CYAN}{self.monitor_interval}{Style.RESET_ALL} 秒")
        print(f"  {Fore.GREEN}2.{Style.RESET_ALL} 💰 最小转账金额: {Fore.CYAN}{self.min_transfer_amount}{Style.RESET_ALL} ETH")
        print(f"  {Fore.GREEN}3.{Style.RESET_ALL} ⛽ Gas价格: {Fore.CYAN}{self.gas_price_gwei}{Style.RESET_ALL} Gwei")
        
        choice = self.safe_input(f"\n{Fore.YELLOW}🔢 请选择要修改的参数 (1-3): {Style.RESET_ALL}").strip()
        
        try:
            if choice == '1':
                new_interval = int(self.safe_input(f"{Fore.CYAN}⏱️ 请输入新的监控间隔（秒）: {Style.RESET_ALL}") or "30")
                if new_interval > 0:
                    self.monitor_interval = new_interval
                    print(f"\n{Fore.GREEN}✅ 成功！监控间隔已设置为 {new_interval} 秒{Style.RESET_ALL}")
                else:
                    print(f"\n{Fore.RED}❌ 错误！间隔必须大于0{Style.RESET_ALL}")
            elif choice == '2':
                new_amount = float(self.safe_input(f"{Fore.CYAN}💰 请输入新的最小转账金额（ETH）: {Style.RESET_ALL}") or "0.001")
                if new_amount > 0:
                    self.min_transfer_amount = new_amount
                    print(f"\n{Fore.GREEN}✅ 成功！最小转账金额已设置为 {new_amount} ETH{Style.RESET_ALL}")
                else:
                    print(f"\n{Fore.RED}❌ 错误！金额必须大于0{Style.RESET_ALL}")
            elif choice == '3':
                new_gas_price = int(self.safe_input(f"{Fore.CYAN}⛽ 请输入新的Gas价格（Gwei）: {Style.RESET_ALL}") or "20")
                if new_gas_price > 0:
                    self.gas_price_gwei = new_gas_price
                    print(f"\n{Fore.GREEN}✅ 成功！Gas价格已设置为 {new_gas_price} Gwei{Style.RESET_ALL}")
                else:
                    print(f"\n{Fore.RED}❌ 错误！Gas价格必须大于0{Style.RESET_ALL}")
            else:
                print(f"\n{Fore.YELLOW}⚠️ 取消修改{Style.RESET_ALL}")
        except ValueError:
            print(f"\n{Fore.RED}❌ 输入格式错误！请输入有效数字{Style.RESET_ALL}")
        
        self.safe_input(f"\n{Fore.MAGENTA}🔙 按回车键返回主菜单...{Style.RESET_ALL}")

    def menu_network_management(self):
        """菜单：网络连接管理"""
        print(f"\n{Fore.CYAN}✨ ====== 🌐 网络连接管理 🌐 ====== ✨{Style.RESET_ALL}")
        print(f"{Back.BLUE}{Fore.WHITE} 🔍 正在检查所有网络连接状态... {Style.RESET_ALL}")
        
        # 显示所有网络状态
        connected_networks = []
        failed_networks = []
        
        print(f"\n{Fore.YELLOW}📈 网络连接状态：{Style.RESET_ALL}")
        print(f"{Fore.CYAN}─" * 80 + f"{Style.RESET_ALL}")
        
        for network_key, network_info in self.networks.items():
            if network_key in self.web3_connections:
                connected_networks.append((network_key, network_info))
                status_icon = "🟢"
                status_text = "已连接"
                color = Fore.GREEN
            else:
                failed_networks.append((network_key, network_info))
                status_icon = "🔴"
                status_text = "未连接"
                color = Fore.RED
            
            currency = network_info['native_currency']
            network_name = network_info['name']
            print(f"  {status_icon} {color}{network_name:<25}{Style.RESET_ALL} ({currency:<5}) - {color}{status_text}{Style.RESET_ALL}")
        
        print(f"\n{Fore.CYAN}─" * 80 + f"{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}📊 连接统计：{Style.RESET_ALL}")
        print(f"  🟢 {Fore.GREEN}已连接: {len(connected_networks)} 个网络{Style.RESET_ALL}")
        print(f"  🔴 {Fore.RED}未连接: {len(failed_networks)} 个网络{Style.RESET_ALL}")
        
        if failed_networks:
            print(f"\n{Fore.YELLOW}🔄 是否重新连接失败的网络? (y/N): {Style.RESET_ALL}", end="")
            choice = self.safe_input().strip().lower()
            if choice == 'y':
                print(f"\n{Fore.BLUE}🔄 正在重新连接失败的网络...{Style.RESET_ALL}")
                self.init_web3_connections()
                print(f"{Fore.GREEN}✅ 重新连接完成！{Style.RESET_ALL}")
            else:
                print(f"\n{Fore.YELLOW}⚠️  已取消重新连接{Style.RESET_ALL}")
        else:
            print(f"\n{Fore.GREEN}🎉 所有网络都已成功连接！{Style.RESET_ALL}")
        
        self.safe_input(f"\n{Fore.MAGENTA}🔙 按回车键返回主菜单...{Style.RESET_ALL}")
    
    def menu_exit(self):
        """菜单：退出程序"""
        print(f"\n{Fore.CYAN}👋 正在退出...{Style.RESET_ALL}")
        self.stop_monitoring()
        self.save_state()
        # 保存钱包
        self.save_wallets()
        print(f"{Fore.GREEN}✅ 程序已安全退出{Style.RESET_ALL}")

def run_daemon_mode(monitor, password):
    """运行守护进程模式"""
    try:
        # 加载钱包和状态
        if not monitor.load_wallets():
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
                monitor.save_wallets()
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
        # 检查是否在交互式环境中
        import sys
        is_interactive = sys.stdin.isatty() and sys.stdout.isatty()
        
        # 解析命令行参数
        import argparse
        parser = argparse.ArgumentParser(description='EVM钱包监控软件')
        parser.add_argument('--daemon', action='store_true', help='以守护进程模式运行')
        parser.add_argument('--password', type=str, help='钱包密码（仅用于守护进程模式）')
        parser.add_argument('--auto-start', action='store_true', help='自动开始监控（非交互式模式）')
        parser.add_argument('--force-interactive', action='store_true', help='强制交互式模式（默认）')
        args = parser.parse_args()
        
        # 创建监控实例
        monitor = EVMMonitor()
        
        # 守护进程模式
        if args.daemon:
            return run_daemon_mode(monitor, args.password)
        
        # 除非明确指定其他模式，否则强制交互式
        if args.auto_start and not args.force_interactive:
            print(f"{Fore.YELLOW}⚠️  检测到非交互式环境，将自动开始监控{Style.RESET_ALL}")
            if monitor.wallets and monitor.target_wallet:
                monitor.start_monitoring()
                try:
                    while monitor.monitoring:
                        time.sleep(60)
                except KeyboardInterrupt:
                    print(f"\n{Fore.YELLOW}👋 收到停止信号，程序退出{Style.RESET_ALL}")
                    monitor.stop_monitoring()
                return True
            else:
                print(f"{Fore.RED}❌ 缺少必要配置（钱包或目标账户），无法自动开始{Style.RESET_ALL}")
                return False
        
        # 交互模式（默认模式）
        print(f"{Fore.CYAN}🚀 进入交互式菜单模式{Style.RESET_ALL}")
        
        # 加载钱包
        monitor.load_wallets()
        
        # 加载监控状态
        monitor.load_state()
        
        # 显示欢迎信息
        print(f"\n{Fore.GREEN}🎉 欢迎使用EVM监控软件！{Style.RESET_ALL}")
        print(f"已连接网络: {', '.join(monitor.web3_connections.keys())}")
        print(f"{Fore.YELLOW}📝 提示：如果遇到输入问题，请直接按回车键或输入0退出{Style.RESET_ALL}")
        print(f"{Fore.GREEN}✨ 如果运行在SSH或脚本中，请使用: python3 evm_monitor.py --auto-start{Style.RESET_ALL}")
        
        # 显示菜单
        try:
            monitor.show_menu()
        except KeyboardInterrupt:
            print(f"\n{Fore.YELLOW}👋 用户中断程序{Style.RESET_ALL}")
        finally:
            # 确保监控停止
            if monitor.monitoring:
                print(f"{Fore.CYAN}🔄 正在安全停止监控...{Style.RESET_ALL}")
                monitor.stop_monitoring()
            monitor.save_wallets()
            print(f"{Fore.GREEN}✅ 程序已安全退出{Style.RESET_ALL}")
        
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}👋 程序被中断{Style.RESET_ALL}")
        # 确保监控停止
        if 'monitor' in locals() and monitor.monitoring:
            print(f"{Fore.CYAN}🔄 正在安全停止监控...{Style.RESET_ALL}")
            monitor.stop_monitoring()
            monitor.save_wallets()
    except EOFError:
        print(f"\n{Fore.YELLOW}👋 检测到EOF错误，程序退出{Style.RESET_ALL}")
        print(f"{Fore.CYAN}💡 建议使用: python3 evm_monitor.py --auto-start{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}❌ 程序出错: {e}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}💡 如果是EOF错误，请使用: python3 evm_monitor.py --auto-start{Style.RESET_ALL}")
        # 确保监控停止
        if 'monitor' in locals() and monitor.monitoring:
            monitor.stop_monitoring()
            monitor.save_wallets()

if __name__ == "__main__":
    main()
