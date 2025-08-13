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
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import logging
import signal
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor, as_completed

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

# 全局监控实例与信号处理，确保 Ctrl+C 随时强制退出
MONITOR_INSTANCE = None

def _global_signal_handler(signum, frame):
    try:
        print(f"\n{Fore.YELLOW}👋 收到退出信号，正在退出...{Style.RESET_ALL}")
        if MONITOR_INSTANCE is not None:
            try:
                MONITOR_INSTANCE.stop_monitoring()
                MONITOR_INSTANCE.save_state()
                MONITOR_INSTANCE.save_wallets()
            except Exception:
                pass
    finally:
        import os as _os
        code = 130 if signum == signal.SIGINT else 143
        _os._exit(code)

class EVMMonitor:
    def __init__(self):
        # 配置
        self.ALCHEMY_API_KEY = "S0hs4qoXIR1SMD8P7I6Wt"
        self.ANKR_API_KEY = "f3e8c3210c23fbe769ac9bb8b0a4eced8b67ec0e1e51f0497c92a648f821bb50"
        
        # ERC20 代币 ABI（标准接口）
        self.erc20_abi = [
            {
                "constant": True,
                "inputs": [{"name": "_owner", "type": "address"}],
                "name": "balanceOf",
                "outputs": [{"name": "balance", "type": "uint256"}],
                "type": "function"
            },
            {
                "constant": False,
                "inputs": [
                    {"name": "_to", "type": "address"},
                    {"name": "_value", "type": "uint256"}
                ],
                "name": "transfer",
                "outputs": [{"name": "", "type": "bool"}],
                "type": "function"
            },
            {
                "constant": True,
                "inputs": [],
                "name": "decimals",
                "outputs": [{"name": "", "type": "uint8"}],
                "type": "function"
            },
            {
                "constant": True,
                "inputs": [],
                "name": "symbol",
                "outputs": [{"name": "", "type": "string"}],
                "type": "function"
            },
            {
                "constant": True,
                "inputs": [],
                "name": "name",
                "outputs": [{"name": "", "type": "string"}],
                "type": "function"
            }
        ]
        
        # 支持的代币配置
        self.tokens = {
            # 主流稳定币
            'USDT': {
                'name': 'Tether USD',
                'symbol': 'USDT',
                'contracts': {
                    'ethereum': '0xdAC17F958D2ee523a2206206994597C13D831ec7',
                    'arbitrum': '0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9',
                    'optimism': '0x94b008aA00579c1307B0EF2c499aD98a8ce58e58',
                    'polygon': '0xc2132D05D31c914a87C6611C10748AEb04B58e8F',
                    'base': '0xfde4C96c8593536E31F229EA8f37b2ADa2699bb2'
                }
            },
            'USDC': {
                'name': 'USD Coin',
                'symbol': 'USDC',
                'contracts': {
                    'ethereum': '0xA0b86a33E6417aFD5BF27c23E2a7B0b9bE6C1e67',
                    'arbitrum': '0xaf88d065e77c8cC2239327C5EDb3A432268e5831',
                    'optimism': '0x0b2C639c533813f4Aa9D7837CAf62653d097Ff85',
                    'polygon': '0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174',
                    'base': '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913'
                }
            },
            'DAI': {
                'name': 'Dai Stablecoin',
                'symbol': 'DAI',
                'contracts': {
                    'ethereum': '0x6B175474E89094C44Da98b954EedeAC495271d0F',
                    'arbitrum': '0xDA10009cBd5D07dd0CeCc66161FC93D7c9000da1',
                    'optimism': '0xDA10009cBd5D07dd0CeCc66161FC93D7c9000da1',
                    'polygon': '0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063'
                }
            }
        }
        
        # 支持的全链网络配置（Alchemy + 公共RPC）
        self.networks = {
            # ==== 🌐 Layer 1 主网 ====
            'ethereum': {
                'name': '🔷 Ethereum Mainnet',
                'chain_id': 1,
                'rpc_urls': [
                    # 公共RPC (优先)
                    'https://ethereum.publicnode.com',
                    'https://ethereum.blockpi.network/v1/rpc/public',
                    'https://rpc.mevblocker.io',
                    'https://virginia.rpc.blxrbdn.com',
                    'https://uk.rpc.blxrbdn.com',
                    'https://singapore.rpc.blxrbdn.com',
                    'https://eth.drpc.org',
                    'https://endpoints.omniatech.io/v1/eth/mainnet/public',
                    # ALCHEMY (备用)
                    f'https://eth-mainnet.g.alchemy.com/v2/{self.ALCHEMY_API_KEY}',
                    # Ankr (最后备用)
                    f'https://rpc.ankr.com/eth/{self.ANKR_API_KEY}'
                ],
                'native_currency': 'ETH',
                'explorer': 'https://etherscan.io'
            },
            
            'bsc': {
                'name': '🟡 BNB Smart Chain',
                'chain_id': 56,
                'rpc_urls': [
                    # 公共RPC (优先)
                    'https://bsc.publicnode.com',
                    'https://bsc-dataseed1.binance.org',
                    'https://bsc-dataseed2.binance.org',
                    'https://bsc-dataseed3.binance.org',
                    'https://bsc.blockpi.network/v1/rpc/public',
                    'https://bsc.drpc.org',
                    'https://endpoints.omniatech.io/v1/bsc/mainnet/public',
                    'https://bsc-rpc.gateway.pokt.network',
                    # Ankr (备用)
                    f'https://rpc.ankr.com/bsc/{self.ANKR_API_KEY}'
                ],
                'native_currency': 'BNB',
                'explorer': 'https://bscscan.com'
            },
            
            'avalanche': {
                'name': '🏔️ Avalanche C-Chain',
                'chain_id': 43114,
                'rpc_urls': [
                    # 公共RPC (优先)
                    'https://avalanche.public-rpc.com',
                    'https://api.avax.network/ext/bc/C/rpc',
                    'https://avalanche.blockpi.network/v1/rpc/public',
                    'https://avax.meowrpc.com',
                    'https://avalanche.drpc.org',
                    'https://endpoints.omniatech.io/v1/avax/mainnet/public',
                    'https://1rpc.io/avax/c',
                    'https://avax-rpc.gateway.pokt.network',
                    # Ankr (备用)
                    f'https://rpc.ankr.com/avalanche/{self.ANKR_API_KEY}'
                ],
                'native_currency': 'AVAX',
                'explorer': 'https://snowtrace.io'
            },
            
            'fantom': {
                'name': '👻 Fantom Opera',
                'chain_id': 250,
                'rpc_urls': [
                    # 公共RPC (优先)
                    'https://fantom.publicnode.com',
                    'https://rpc.ftm.tools',
                    'https://fantom.blockpi.network/v1/rpc/public',
                    'https://rpc.fantom.network',
                    'https://fantom.drpc.org',
                    'https://endpoints.omniatech.io/v1/fantom/mainnet/public',
                    'https://1rpc.io/ftm',
                    'https://rpc2.fantom.network',
                    'https://rpc3.fantom.network',
                    # Ankr (备用)
                    f'https://rpc.ankr.com/fantom/{self.ANKR_API_KEY}'
                ],
                'native_currency': 'FTM',
                'explorer': 'https://ftmscan.com'
            },
            
            'cronos': {
                'name': '🦀 Cronos',
                'chain_id': 25,
                'rpc_urls': [
                    # 公共节点
                    'https://cronos.publicnode.com',
                    'https://evm.cronos.org',
                    'https://cronos.blockpi.network/v1/rpc/public',
                    'https://cronos.drpc.org',
                    'https://cronos-evm.publicnode.com',
                    'https://rpc.vvs.finance',
                    # Alchemy
                    f'https://cronos-mainnet.g.alchemy.com/v2/{self.ALCHEMY_API_KEY}',
                    # Ankr
                    f'https://rpc.ankr.com/cronos/{self.ANKR_API_KEY}'
                ],
                'native_currency': 'CRO',
                'explorer': 'https://cronoscan.com'
            },
            
            'gnosis': {
                'name': '🦉 Gnosis Chain',
                'chain_id': 100,
                'rpc_urls': [
                    # 公共RPC (优先)
                    'https://gnosis.publicnode.com',
                    'https://rpc.gnosischain.com',
                    'https://gnosis.blockpi.network/v1/rpc/public',
                    'https://gnosis.drpc.org',
                    'https://endpoints.omniatech.io/v1/gnosis/mainnet/public',
                    'https://1rpc.io/gnosis',
                    'https://gnosis-mainnet.public.blastapi.io',
                    'https://rpc.gnosis.gateway.fm',
                    # Ankr (备用)
                    f'https://rpc.ankr.com/gnosis/{self.ANKR_API_KEY}'
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
                    # 公共RPC (优先)
                    'https://arbitrum.publicnode.com',
                    'https://arbitrum.blockpi.network/v1/rpc/public',
                    'https://arb1.arbitrum.io/rpc',
                    'https://arbitrum.llamarpc.com',
                    'https://arbitrum.drpc.org',
                    'https://endpoints.omniatech.io/v1/arbitrum/one/public',
                    'https://1rpc.io/arb',
                    # ALCHEMY (备用)
                    f'https://arb-mainnet.g.alchemy.com/v2/{self.ALCHEMY_API_KEY}',
                    # Ankr (最后备用)
                    f'https://rpc.ankr.com/arbitrum/{self.ANKR_API_KEY}'
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
                    # 公共RPC (优先)
                    'https://optimism.publicnode.com',
                    'https://optimism.blockpi.network/v1/rpc/public',
                    'https://mainnet.optimism.io',
                    'https://optimism.llamarpc.com',
                    'https://optimism.drpc.org',
                    'https://endpoints.omniatech.io/v1/op/mainnet/public',
                    'https://1rpc.io/op',
                    # ALCHEMY (备用)
                    f'https://opt-mainnet.g.alchemy.com/v2/{self.ALCHEMY_API_KEY}',
                    # Ankr (最后备用)
                    f'https://rpc.ankr.com/optimism/{self.ANKR_API_KEY}'
                ],
                'native_currency': 'ETH',
                'explorer': 'https://optimistic.etherscan.io'
            },
            
            'base': {
                'name': '🟦 Base',
                'chain_id': 8453,
                'rpc_urls': [
                    # 公共RPC (优先)
                    'https://base.publicnode.com',
                    'https://base.blockpi.network/v1/rpc/public',
                    'https://mainnet.base.org',
                    'https://base.llamarpc.com',
                    'https://base.drpc.org',
                    'https://endpoints.omniatech.io/v1/base/mainnet/public',
                    'https://1rpc.io/base',
                    # ALCHEMY (备用)
                    f'https://base-mainnet.g.alchemy.com/v2/{self.ALCHEMY_API_KEY}',
                    # Ankr (最后备用)
                    f'https://rpc.ankr.com/base/{self.ANKR_API_KEY}'
                ],
                'native_currency': 'ETH',
                'explorer': 'https://basescan.org'
            },
            
            'zksync': {
                'name': '⚡ zkSync Era',
                'chain_id': 324,
                'rpc_urls': [
                    # 公共RPC (优先)
                    'https://mainnet.era.zksync.io',
                    'https://zksync.llamarpc.com',
                    'https://zksync.drpc.org',
                    'https://zksync-era.blockpi.network/v1/rpc/public',
                    'https://endpoints.omniatech.io/v1/zksync-era/mainnet/public',
                    'https://1rpc.io/zksync2-era',
                    'https://zksync.meowrpc.com',
                    # ALCHEMY (备用)
                    f'https://zksync-mainnet.g.alchemy.com/v2/{self.ALCHEMY_API_KEY}',
                    # Ankr (最后备用)
                    f'https://rpc.ankr.com/zksync_era/{self.ANKR_API_KEY}'
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
                    # 公共节点
                    'https://pacific-rpc.manta.network/http',
                    'https://manta-pacific.drpc.org',
                    'https://r1.pacific.manta.systems/http',
                    'https://manta.public-rpc.com',
                    # Ankr
                    f'https://rpc.ankr.com/manta/{self.ANKR_API_KEY}'
                ],
                'native_currency': 'ETH',
                'explorer': 'https://pacific-explorer.manta.network'
            },
            
            'blast': {
                'name': '💥 Blast',
                'chain_id': 81457,
                'rpc_urls': [
                    # 公共RPC (优先)
                    'https://rpc.blast.io',
                    'https://blast.llamarpc.com',
                    'https://blast.blockpi.network/v1/rpc/public',
                    'https://blast.drpc.org',
                    'https://endpoints.omniatech.io/v1/blast/mainnet/public',
                    'https://1rpc.io/blast',
                    'https://blast.gasswap.org',
                    # ALCHEMY (备用)
                    f'https://blast-mainnet.g.alchemy.com/v2/{self.ALCHEMY_API_KEY}',
                    # Ankr (最后备用)
                    f'https://rpc.ankr.com/blast/{self.ANKR_API_KEY}'
                ],
                'native_currency': 'ETH',
                'explorer': 'https://blastscan.io'
            },
            
            # ==== 🧪 测试网络 ====
            'ethereum_sepolia': {
                'name': '🧪 Ethereum Sepolia',
                'chain_id': 11155111,
                'rpc_urls': [
                    # 公共RPC (优先)
                    'https://sepolia.publicnode.com',
                    'https://rpc.sepolia.org',
                    'https://sepolia.blockpi.network/v1/rpc/public',
                    'https://ethereum-sepolia.blockpi.network/v1/rpc/public',
                    'https://sepolia.drpc.org',
                    'https://endpoints.omniatech.io/v1/eth/sepolia/public',
                    'https://1rpc.io/sepolia',
                    'https://rpc-sepolia.rockx.com',
                    # ALCHEMY (备用)
                    f'https://eth-sepolia.g.alchemy.com/v2/{self.ALCHEMY_API_KEY}',
                    # Ankr (最后备用)
                    f'https://rpc.ankr.com/eth_sepolia/{self.ANKR_API_KEY}'
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
            },
            
            # ==== 🌐 新增主流Layer 1 ====
            
            'polygon': {
                'name': '🟪 Polygon Mainnet',
                'chain_id': 137,
                'rpc_urls': [
                    # 公共节点
                    'https://polygon.publicnode.com',
                    'https://polygon-rpc.com',
                    'https://polygon.blockpi.network/v1/rpc/public',
                    'https://polygon.llamarpc.com',
                    'https://polygon.drpc.org',
                    'https://endpoints.omniatech.io/v1/matic/mainnet/public',
                    'https://1rpc.io/matic',
                    # Alchemy
                    f'https://polygon-mainnet.g.alchemy.com/v2/{self.ALCHEMY_API_KEY}',
                    # Ankr
                    f'https://rpc.ankr.com/polygon/{self.ANKR_API_KEY}'
                ],
                'native_currency': 'POL',
                'explorer': 'https://polygonscan.com'
            },
            
            'linea': {
                'name': '🟢 Linea',
                'chain_id': 59144,
                'rpc_urls': [
                    # 公共RPC (优先)
                    'https://rpc.linea.build',
                    'https://linea.blockpi.network/v1/rpc/public',
                    'https://linea.drpc.org',
                    'https://endpoints.omniatech.io/v1/linea/mainnet/public',
                    'https://1rpc.io/linea',
                    'https://linea-mainnet.infura.io/v3/9aa3d95b3bc440fa88ea12eaa4456161',
                    # ALCHEMY (备用)
                    f'https://linea-mainnet.g.alchemy.com/v2/{self.ALCHEMY_API_KEY}',
                    # Ankr (最后备用)
                    f'https://rpc.ankr.com/linea/{self.ANKR_API_KEY}'
                ],
                'native_currency': 'ETH',
                'explorer': 'https://lineascan.build'
            },
            
            'mode': {
                'name': '🟣 Mode',
                'chain_id': 34443,
                'rpc_urls': [
                    'https://mainnet.mode.network',
                    'https://mode.gateway.tenderly.co',
                    'https://1rpc.io/mode'
                ],
                'native_currency': 'ETH',
                'explorer': 'https://explorer.mode.network'
            },
            
            'unichain': {
                'name': '🦄 Unichain',
                'chain_id': 1301,
                'rpc_urls': [
                    'https://rpc.unichain.org',
                    'https://unichain-rpc.gateway.tenderly.co'
                ],
                'native_currency': 'ETH',
                'explorer': 'https://uniscan.xyz'
            },
            
            'sonic': {
                'name': '💙 Sonic Mainnet',
                'chain_id': 146,
                'rpc_urls': [
                    'https://rpc.sonic.mainnet.org',
                    'https://sonic.gateway.tenderly.co'
                ],
                'native_currency': 'S',
                'explorer': 'https://sonicscan.org'
            },
            
            'berachain': {
                'name': '🐻 Berachain',
                'chain_id': 80094,
                'rpc_urls': [
                    'https://rpc.berachain.com',
                    'https://berachain.gateway.tenderly.co'
                ],
                'native_currency': 'BERA',
                'explorer': 'https://berascan.com'
            },
            
            'merlin': {
                'name': '🧙 Merlin',
                'chain_id': 4200,
                'rpc_urls': [
                    'https://rpc.merlinchain.io',
                    'https://merlin.blockpi.network/v1/rpc/public'
                ],
                'native_currency': 'BTC',
                'explorer': 'https://scan.merlinchain.io'
            },
            
            'taproot': {
                'name': '🌿 TAPROOT',
                'chain_id': 8911,
                'rpc_urls': [
                    'https://rpc.taproot.network',
                    'https://taproot.blockpi.network/v1/rpc/public'
                ],
                'native_currency': 'BTC',
                'explorer': 'https://scan.taproot.network'
            },
            
            'zetachain': {
                'name': '⚡ ZetaChain',
                'chain_id': 7000,
                'rpc_urls': [
                    'https://zetachain-evm.blockpi.network/v1/rpc/public',
                    'https://zetachain-mainnet-archive.allthatnode.com:8545'
                ],
                'native_currency': 'ZETA',
                'explorer': 'https://zetachain.blockscout.com'
            },
            
            'mantle': {
                'name': '🟫 Mantle',
                'chain_id': 5000,
                'rpc_urls': [
                    'https://rpc.mantle.xyz',
                    'https://mantle.publicnode.com',
                    'https://rpc.ankr.com/mantle'
                ],
                'native_currency': 'MNT',
                'explorer': 'https://explorer.mantle.xyz'
            },
            
            'eos_evm': {
                'name': '🟡 EOS EVM',
                'chain_id': 17777,
                'rpc_urls': [
                    'https://api.evm.eosnetwork.com',
                    'https://eosevm.blockpi.network/v1/rpc/public'
                ],
                'native_currency': 'EOS',
                'explorer': 'https://explorer.evm.eosnetwork.com'
            },
            
            'kava': {
                'name': '🔴 Kava EVM',
                'chain_id': 2222,
                'rpc_urls': [
                    'https://evm.kava.io',
                    'https://evm2.kava.io',
                    'https://kava-evm.publicnode.com'
                ],
                'native_currency': 'KAVA',
                'explorer': 'https://kavascan.com'
            },
            
            'taiko': {
                'name': '🟡 Taiko',
                'chain_id': 167000,
                'rpc_urls': [
                    'https://rpc.mainnet.taiko.xyz',
                    'https://taiko.blockpi.network/v1/rpc/public'
                ],
                'native_currency': 'ETH',
                'explorer': 'https://taikoscan.io'
            },
            
            'story': {
                'name': '📖 Story',
                'chain_id': 1513,
                'rpc_urls': [
                    'https://rpc.story.foundation',
                    'https://story.blockpi.network/v1/rpc/public'
                ],
                'native_currency': 'IP',
                'explorer': 'https://storyscan.xyz'
            },
            
            'core': {
                'name': '🟠 Core',
                'chain_id': 1116,
                'rpc_urls': [
                    'https://rpc.coredao.org',
                    'https://core.public-rpc.com',
                    'https://rpc.ankr.com/core'
                ],
                'native_currency': 'CORE',
                'explorer': 'https://scan.coredao.org'
            },
            
            'chiliz': {
                'name': '🌶️ Chiliz',
                'chain_id': 88888,
                'rpc_urls': [
                    'https://rpc.chiliz.com',
                    'https://chiliz.publicnode.com'
                ],
                'native_currency': 'CHZ',
                'explorer': 'https://scan.chiliz.com'
            },
            
            'filecoin': {
                'name': '🗃️ Filecoin',
                'chain_id': 314,
                'rpc_urls': [
                    'https://api.node.glif.io',
                    'https://rpc.ankr.com/filecoin'
                ],
                'native_currency': 'FIL',
                'explorer': 'https://filfox.info'
            },
            
            'b2_network': {
                'name': '🅱️ B² Network',
                'chain_id': 223,
                'rpc_urls': [
                    'https://rpc.bsquared.network',
                    'https://b2-mainnet.alt.technology'
                ],
                'native_currency': 'BTC',
                'explorer': 'https://explorer.bsquared.network'
            },
            
            'abstract': {
                'name': '🎨 Abstract',
                'chain_id': 11124,
                'rpc_urls': [
                    'https://api.abstract.money',
                    'https://abstract.blockpi.network/v1/rpc/public'
                ],
                'native_currency': 'ETH',
                'explorer': 'https://explorer.abstract.money'
            },
            
            'vana': {
                'name': '🌐 VANA',
                'chain_id': 1480,
                'rpc_urls': [
                    'https://rpc.vana.org',
                    'https://vana.blockpi.network/v1/rpc/public'
                ],
                'native_currency': 'VANA',
                'explorer': 'https://explorer.vana.org'
            },
            
            'apechain': {
                'name': '🐵 ApeChain',
                'chain_id': 33139,
                'rpc_urls': [
                    'https://rpc.apechain.com',
                    'https://apechain.gateway.tenderly.co'
                ],
                'native_currency': 'APE',
                'explorer': 'https://apescan.io'
            },
            
            'cronos': {
                'name': '👑 Cronos',
                'chain_id': 25,
                'rpc_urls': [
                    'https://evm.cronos.org',
                    'https://cronos.blockpi.network/v1/rpc/public',
                    'https://rpc.ankr.com/cronos'
                ],
                'native_currency': 'CRO',
                'explorer': 'https://cronoscan.com'
            },
            
            'gnosis': {
                'name': '🟢 Gnosis',
                'chain_id': 100,
                'rpc_urls': [
                    'https://rpc.gnosischain.com',
                    'https://gnosis.publicnode.com',
                    'https://rpc.ankr.com/gnosis'
                ],
                'native_currency': 'xDAI',
                'explorer': 'https://gnosisscan.io'
            },
            
            'ethw': {
                'name': '⚡ EthereumPoW',
                'chain_id': 10001,
                'rpc_urls': [
                    'https://mainnet.ethereumpow.org',
                    'https://ethw.gateway.tenderly.co'
                ],
                'native_currency': 'ETHW',
                'explorer': 'https://www.oklink.com/ethw'
            },
            
            'heco': {
                'name': '🔥 HECO',
                'chain_id': 128,
                'rpc_urls': [
                    # 公共节点
                    'https://http-mainnet.hecochain.com',
                    'https://http-mainnet-node.huobichain.com',
                    'https://heco-mainnet.gateway.pokt.network/v1/lb/611ad8efd2ae6d0028b2c7dd',
                    'https://heco.drpc.org',
                    # Ankr
                    f'https://rpc.ankr.com/heco/{self.ANKR_API_KEY}'
                ],
                'native_currency': 'HT',
                'explorer': 'https://hecoinfo.com'
            },
            
            'kcc': {
                'name': '⚡ KCC Mainnet',
                'chain_id': 321,
                'rpc_urls': [
                    'https://rpc-mainnet.kcc.network',
                    'https://kcc.mytokenpocket.vip'
                ],
                'native_currency': 'KCS',
                'explorer': 'https://explorer.kcc.io'
            },
            
            'zkfair': {
                'name': '⚖️ zkFair',
                'chain_id': 42766,
                'rpc_urls': [
                    'https://rpc.zkfair.io',
                    'https://zkfair.blockpi.network/v1/rpc/public'
                ],
                'native_currency': 'USDC',
                'explorer': 'https://scan.zkfair.io'
            },
            
            'bevm': {
                'name': '🟠 BEVM',
                'chain_id': 11501,
                'rpc_urls': [
                    'https://rpc-mainnet-1.bevm.io',
                    'https://rpc-mainnet-2.bevm.io'
                ],
                'native_currency': 'BTC',
                'explorer': 'https://scan-mainnet.bevm.io'
            },
            
            'klaytn': {
                'name': '🟤 Klaytn',
                'chain_id': 8217,
                'rpc_urls': [
                    'https://public-node-api.klaytnapi.com/v1/cypress',
                    'https://klaytn.publicnode.com',
                    'https://rpc.ankr.com/klaytn'
                ],
                'native_currency': 'KLAY',
                'explorer': 'https://scope.klaytn.com'
            },
            
            'conflux': {
                'name': '🔷 Conflux eSpace',
                'chain_id': 1030,
                'rpc_urls': [
                    'https://evm.confluxrpc.com',
                    'https://conflux-espace.blockpi.network/v1/rpc/public'
                ],
                'native_currency': 'CFX',
                'explorer': 'https://evm.confluxscan.net'
            },
            
            # ==== ⚡ Layer 2 网络 ====
            
            'polygon_zkevm': {
                'name': '🔺 Polygon zkEVM',
                'chain_id': 1101,
                'rpc_urls': [
                    f'https://polygonzkevm-mainnet.g.alchemy.com/v2/{self.ALCHEMY_API_KEY}',
                    'https://zkevm-rpc.com',
                    'https://rpc.ankr.com/polygon_zkevm'
                ],
                'native_currency': 'ETH',
                'explorer': 'https://zkevm.polygonscan.com'
            },
            
            'x_layer': {
                'name': '❌ X Layer',
                'chain_id': 196,
                'rpc_urls': [
                    'https://rpc.xlayer.tech',
                    'https://xlayer.blockpi.network/v1/rpc/public'
                ],
                'native_currency': 'OKB',
                'explorer': 'https://www.oklink.com/xlayer'
            },
            
            'scroll': {
                'name': '📜 Scroll',
                'chain_id': 534352,
                'rpc_urls': [
                    'https://rpc.scroll.io',
                    'https://scroll.publicnode.com',
                    'https://rpc.ankr.com/scroll'
                ],
                'native_currency': 'ETH',
                'explorer': 'https://scrollscan.com'
            },
            
            'opbnb': {
                'name': '🟡 opBNB',
                'chain_id': 204,
                'rpc_urls': [
                    'https://opbnb-mainnet-rpc.bnbchain.org',
                    'https://opbnb.publicnode.com'
                ],
                'native_currency': 'BNB',
                'explorer': 'https://opbnbscan.com'
            },
            
            # ==== 🧪 新增测试网 ====
            
            'tea_testnet': {
                'name': '🧪 Tea Testnet',
                'chain_id': 1337,
                'rpc_urls': [
                    'https://rpc.testnet.tea.xyz',
                    'https://tea-testnet.blockpi.network/v1/rpc/public'
                ],
                'native_currency': 'TEA',
                'explorer': 'https://testnet.teascan.org'
            },
            
            'monad_testnet': {
                'name': '🧪 Monad Testnet',
                'chain_id': 10143,
                'rpc_urls': [
                    'https://testnet-rpc.monad.xyz',
                    'https://monad-testnet.blockpi.network/v1/rpc/public'
                ],
                'native_currency': 'MON',
                'explorer': 'https://testnet.monadscan.xyz'
            },
            
            'merlin_testnet': {
                'name': '🧪 Merlin Testnet',
                'chain_id': 686868,
                'rpc_urls': [
                    'https://testnet-rpc.merlinchain.io',
                    'https://merlin-testnet.blockpi.network/v1/rpc/public'
                ],
                'native_currency': 'BTC',
                'explorer': 'https://testnet-scan.merlinchain.io'
            },
            
            'bnb_testnet': {
                'name': '🧪 BNB Smart Chain Testnet',
                'chain_id': 97,
                'rpc_urls': [
                    'https://data-seed-prebsc-1-s1.binance.org:8545',
                    'https://bsc-testnet.publicnode.com'
                ],
                'native_currency': 'tBNB',
                'explorer': 'https://testnet.bscscan.com'
            },
            
            'unichain_sepolia': {
                'name': '🧪 Unichain Sepolia Testnet',
                'chain_id': 1301,
                'rpc_urls': [
                    'https://sepolia.unichain.org',
                    'https://unichain-sepolia.gateway.tenderly.co'
                ],
                'native_currency': 'ETH',
                'explorer': 'https://sepolia.uniscan.xyz'
            },
            
            # ==== 🌐 新增缺失的重要链条 ====
            
            'sei': {
                'name': '🔮 Sei Network',
                'chain_id': 1329,
                'rpc_urls': [
                    # 公共RPC (优先)
                    'https://evm-rpc.sei-apis.com',
                    'https://sei-evm.nirvanalabs.xyz',
                    'https://sei.drpc.org',
                    'https://sei-rpc.polkachu.com',
                    'https://sei-evm-rpc.publicnode.com',
                    # Ankr (备用)
                    f'https://rpc.ankr.com/sei/{self.ANKR_API_KEY}'
                ],
                'native_currency': 'SEI',
                'explorer': 'https://seistream.app'
            },
            
            'iota_evm': {
                'name': '🔷 IOTA EVM',
                'chain_id': 8822,
                'rpc_urls': [
                    # 公共RPC (优先)
                    'https://json-rpc.evm.iotaledger.net',
                    'https://iota-evm.gateway.tenderly.co',
                    'https://iota-evm.publicnode.com',
                    'https://iota.drpc.org',
                    # Ankr (备用)
                    f'https://rpc.ankr.com/iota_evm/{self.ANKR_API_KEY}'
                ],
                'native_currency': 'IOTA',
                'explorer': 'https://explorer.evm.iota.org'
            },
            
            'hyperliquid': {
                'name': '💧 Hyperliquid',
                'chain_id': 999,
                'rpc_urls': [
                    # 公共RPC (优先)
                    'https://api.hyperliquid.xyz/evm',
                    'https://hyperliquid-rpc.publicnode.com',
                    'https://hyperliquid.drpc.org',
                    # Ankr (备用)
                    f'https://rpc.ankr.com/hyperliquid/{self.ANKR_API_KEY}'
                ],
                'native_currency': 'USDC',
                'explorer': 'https://app.hyperliquid.xyz'
            },
            
            'crossfi': {
                'name': '❌ CrossFi',
                'chain_id': 4157,
                'rpc_urls': [
                    # 公共RPC (优先)
                    'https://rpc.crossfi.io',
                    'https://crossfi.blockpi.network/v1/rpc/public',
                    'https://crossfi.drpc.org',
                    'https://crossfi-rpc.publicnode.com',
                    # Ankr (备用)
                    f'https://rpc.ankr.com/crossfi/{self.ANKR_API_KEY}'
                ],
                'native_currency': 'XFI',
                'explorer': 'https://scan.crossfi.io'
            },
            
            'oasis_emerald': {
                'name': '💎 Oasis Emerald',
                'chain_id': 42262,
                'rpc_urls': [
                    # 公共RPC (优先)
                    'https://emerald.oasis.dev',
                    'https://1rpc.io/oasis/emerald',
                    'https://emerald.oasis.io',
                    'https://oasis-emerald.drpc.org',
                    # Ankr (备用)
                    f'https://rpc.ankr.com/oasis_emerald/{self.ANKR_API_KEY}'
                ],
                'native_currency': 'ROSE',
                'explorer': 'https://explorer.emerald.oasis.dev'
            },
            
            'velas': {
                'name': '🔥 Velas EVM',
                'chain_id': 106,
                'rpc_urls': [
                    # 公共RPC (优先)
                    'https://evmexplorer.velas.com/rpc',
                    'https://velas-evm.publicnode.com',
                    'https://velas.drpc.org',
                    'https://explorer.velas.com/rpc',
                    # Ankr (备用)
                    f'https://rpc.ankr.com/velas/{self.ANKR_API_KEY}'
                ],
                'native_currency': 'VLX',
                'explorer': 'https://evmexplorer.velas.com'
            },
            
            'rootstock': {
                'name': '🔶 Rootstock (RSK)',
                'chain_id': 30,
                'rpc_urls': [
                    # 公共RPC (优先)
                    'https://public-node.rsk.co',
                    'https://rsk.getblock.io/mainnet',
                    'https://rsk.drpc.org',
                    'https://rootstock.publicnode.com',
                    'https://mycrypto.rsk.co',
                    # Ankr (备用)
                    f'https://rpc.ankr.com/rootstock/{self.ANKR_API_KEY}'
                ],
                'native_currency': 'RBTC',
                'explorer': 'https://explorer.rsk.co'
            },
            
            'thundercore': {
                'name': '⚡ ThunderCore',
                'chain_id': 108,
                'rpc_urls': [
                    # 公共RPC (优先)
                    'https://mainnet-rpc.thundercore.com',
                    'https://thundercore.drpc.org',
                    'https://thundercore.publicnode.com',
                    'https://mainnet-rpc.thundertoken.net',
                    # Ankr (备用)
                    f'https://rpc.ankr.com/thundercore/{self.ANKR_API_KEY}'
                ],
                'native_currency': 'TT',
                'explorer': 'https://viewblock.io/thundercore'
            },
            
            'bitgert': {
                'name': '🔥 Bitgert',
                'chain_id': 32520,
                'rpc_urls': [
                    # 公共RPC (优先)
                    'https://mainnet-rpc.brisescan.com',
                    'https://chainrpc.com',
                    'https://rpc.icecreamswap.com',
                    'https://bitgert.drpc.org',
                    'https://bitgert.publicnode.com',
                    # Ankr (备用)
                    f'https://rpc.ankr.com/bitgert/{self.ANKR_API_KEY}'
                ],
                'native_currency': 'BRISE',
                'explorer': 'https://brisescan.com'
            },
            
            'wanchain': {
                'name': '🌊 Wanchain',
                'chain_id': 888,
                'rpc_urls': [
                    # 公共RPC (优先)
                    'https://gwan-ssl.wandevs.org:56891',
                    'https://wanchain.drpc.org',
                    'https://wanchain.publicnode.com',
                    'https://wanchain-mainnet.gateway.pokt.network',
                    # Ankr (备用)
                    f'https://rpc.ankr.com/wanchain/{self.ANKR_API_KEY}'
                ],
                'native_currency': 'WAN',
                'explorer': 'https://wanscan.org'
            },
            
            'tomochain': {
                'name': '🏮 TomoChain',
                'chain_id': 88,
                'rpc_urls': [
                    # 公共RPC (优先)
                    'https://rpc.tomochain.com',
                    'https://tomo.blockpi.network/v1/rpc/public',
                    'https://tomochain.drpc.org',
                    'https://tomochain.publicnode.com',
                    # Ankr (备用)
                    f'https://rpc.ankr.com/tomochain/{self.ANKR_API_KEY}'
                ],
                'native_currency': 'TOMO',
                'explorer': 'https://tomoscan.io'
            },
            
            'fusion': {
                'name': '⚛️ Fusion',
                'chain_id': 32659,
                'rpc_urls': [
                    # 公共RPC (优先)
                    'https://mainnet.fusionnetwork.io',
                    'https://mainway.freemoon.xyz/gate',
                    'https://fusion.drpc.org',
                    'https://fusion.publicnode.com',
                    # Ankr (备用)
                    f'https://rpc.ankr.com/fusion/{self.ANKR_API_KEY}'
                ],
                'native_currency': 'FSN',
                'explorer': 'https://fsnex.com'
            },
            
            'elastos': {
                'name': '🔗 Elastos EVM',
                'chain_id': 20,
                'rpc_urls': [
                    # 公共RPC (优先)
                    'https://api.elastos.io/eth',
                    'https://escrpc.elaphant.app',
                    'https://elastos.drpc.org',
                    'https://elastos.publicnode.com',
                    # Ankr (备用)
                    f'https://rpc.ankr.com/elastos/{self.ANKR_API_KEY}'
                ],
                'native_currency': 'ELA',
                'explorer': 'https://esc.elastos.io'
            },
            
            'cube': {
                'name': '🧊 Cube Chain',
                'chain_id': 1818,
                'rpc_urls': [
                    # 公共RPC (优先)
                    'https://http-mainnet.cube.network',
                    'https://cube.drpc.org',
                    'https://cube.publicnode.com',
                    'https://rpc.cube.network',
                    # Ankr (备用)
                    f'https://rpc.ankr.com/cube/{self.ANKR_API_KEY}'
                ],
                'native_currency': 'CUBE',
                'explorer': 'https://cubescan.network'
            },
            
            'energi': {
                'name': '⚡ Energi',
                'chain_id': 39797,
                'rpc_urls': [
                    # 公共RPC (优先)
                    'https://nodeapi.energi.network',
                    'https://energi.drpc.org',
                    'https://energi.publicnode.com',
                    'https://rpc.energi.network',
                    # Ankr (备用)
                    f'https://rpc.ankr.com/energi/{self.ANKR_API_KEY}'
                ],
                'native_currency': 'NRG',
                'explorer': 'https://explorer.energi.network'
            },
            
            'godwoken': {
                'name': '🏛️ Godwoken',
                'chain_id': 71402,
                'rpc_urls': [
                    # 公共RPC (优先)
                    'https://v1.mainnet.godwoken.io/rpc',
                    'https://godwoken.drpc.org',
                    'https://godwoken.publicnode.com',
                    'https://mainnet.godwoken.io/rpc',
                    # Ankr (备用)
                    f'https://rpc.ankr.com/godwoken/{self.ANKR_API_KEY}'
                ],
                'native_currency': 'CKB',
                'explorer': 'https://v1.gwscan.com'
            },
            
            'callisto': {
                'name': '🌙 Callisto Network',
                'chain_id': 820,
                'rpc_urls': [
                    # 公共RPC (优先)
                    'https://clo-geth.0xinfra.com',
                    'https://callisto.drpc.org',
                    'https://callisto.publicnode.com',
                    'https://rpc.callisto.network',
                    # Ankr (备用)
                    f'https://rpc.ankr.com/callisto/{self.ANKR_API_KEY}'
                ],
                'native_currency': 'CLO',
                'explorer': 'https://explorer.callisto.network'
            },
            
            'neon_evm': {
                'name': '🟢 Neon EVM',
                'chain_id': 245022934,
                'rpc_urls': [
                    # 公共RPC (优先)
                    'https://neon-proxy-mainnet.solana.p2p.org',
                    'https://neon-mainnet.everstake.one',
                    'https://neon.drpc.org',
                    'https://neon.publicnode.com',
                    # Ankr (备用)
                    f'https://rpc.ankr.com/neon/{self.ANKR_API_KEY}'
                ],
                'native_currency': 'NEON',
                'explorer': 'https://neonscan.org'
            },
            
            'xrpl_evm': {
                'name': '🌊 XRPL EVM Sidechain',
                'chain_id': 1440002,
                'rpc_urls': [
                    # 公共RPC (优先)
                    'https://rpc-evm-sidechain.xrpl.org',
                    'https://xrpl-evm.drpc.org',
                    'https://xrpl-evm.publicnode.com',
                    'https://evm-sidechain.xrpl.org',
                    # Ankr (备用)
                    f'https://rpc.ankr.com/xrpl_evm/{self.ANKR_API_KEY}'
                ],
                'native_currency': 'eXRP',
                'explorer': 'https://evm-sidechain.xrpl.org'
            },
            
            'bitfinity': {
                'name': '♾️ Bitfinity Network',
                'chain_id': 355113,
                'rpc_urls': [
                    # 公共RPC (优先)
                    'https://testnet.bitfinity.network',
                    'https://bitfinity.drpc.org',
                    'https://bitfinity.publicnode.com',
                    'https://rpc.bitfinity.network',
                    # Ankr (备用)
                    f'https://rpc.ankr.com/bitfinity/{self.ANKR_API_KEY}'
                ],
                'native_currency': 'BFT',
                'explorer': 'https://explorer.bitfinity.network'
            },
            
            'injective_evm': {
                'name': '💉 Injective EVM',
                'chain_id': 2192,
                'rpc_urls': [
                    # 公共RPC (优先)
                    'https://evm-rpc.injective.network',
                    'https://injective-evm.publicnode.com',
                    'https://injective.drpc.org',
                    'https://evm.injective.dev',
                    # Ankr (备用)
                    f'https://rpc.ankr.com/injective_evm/{self.ANKR_API_KEY}'
                ],
                'native_currency': 'INJ',
                'explorer': 'https://evm.injective.network'
            },
            
            'zilliqa_evm': {
                'name': '🏔️ Zilliqa EVM',
                'chain_id': 32769,
                'rpc_urls': [
                    # 公共RPC (优先)
                    'https://api.zilliqa.com',
                    'https://zilliqa-evm.drpc.org',
                    'https://zilliqa.publicnode.com',
                    'https://evm-api.zilliqa.com',
                    # Ankr (备用)
                    f'https://rpc.ankr.com/zilliqa/{self.ANKR_API_KEY}'
                ],
                'native_currency': 'ZIL',
                'explorer': 'https://evmx.zilliqa.com'
            },
            
            'mantra_chain': {
                'name': '🕉️ MANTRA Chain',
                'chain_id': 3370,
                'rpc_urls': [
                    # 公共RPC (优先)
                    'https://rpc.mantrachain.io',
                    'https://mantra.drpc.org',
                    'https://mantra.publicnode.com',
                    'https://evm-rpc.mantrachain.io',
                    # Ankr (备用)
                    f'https://rpc.ankr.com/mantra/{self.ANKR_API_KEY}'
                ],
                'native_currency': 'OM',
                'explorer': 'https://explorer.mantrachain.io'
            }

        }
        
        # 状态变量
        self.wallets: Dict[str, str] = {}  # address -> private_key
        self.target_wallet = ""  # 固定目标账户
        self.monitored_addresses: Dict[str, Dict] = {}  # address -> {networks: [...], last_check: timestamp}
        self.blocked_networks: Dict[str, List[str]] = {}  # address -> [被屏蔽的网络列表]
        self.monitoring = False
        self.monitor_thread = None
        
        # 守护进程和稳定性相关
        self.restart_count = 0  # 重启次数
        self.last_restart_time = 0  # 最后重启时间
        self.max_restarts = 10  # 最大重启次数
        self.restart_interval = 300  # 重启间隔（秒）
        self.memory_cleanup_interval = 3600  # 内存清理间隔（秒）
        self.last_memory_cleanup = time.time()  # 最后内存清理时间
        self.error_count = 0  # 错误计数
        self.max_errors = 50  # 最大错误数，超过后触发清理
        self.daemon_mode = False  # 是否为守护进程模式
        
        # 文件路径
        self.wallet_file = "wallets.json"
        self.state_file = "monitor_state.json"
        self.log_file = "monitor.log"
        
        # 配置参数
        self.monitor_interval = 30  # 监控间隔（秒）
        self.min_transfer_amount = 0.001  # 最小转账金额（ETH）
        self.gas_limit = 21000
        self.gas_price_gwei = 20
        
        # RPC延迟监控配置
        self.max_rpc_latency = 5.0  # 最大允许延迟（秒）
        self.rpc_latency_checks = 3  # 连续检查次数
        self.rpc_latency_history: Dict[str, List[float]] = {}  # URL -> [延迟历史]
        self.blocked_rpcs: Dict[str, Dict] = {}  # URL -> {reason, blocked_time, network}
        
        # Telegram通知配置
        self.telegram_bot_token = "7555291517:AAHJGZOs4RZ-QmZvHKVk-ws5zBNcFZHNmkU"
        self.telegram_chat_id = "5963704377"
        self.telegram_enabled = True
        
        # Telegram降噪与重试配置
        self.telegram_max_retries = 3
        self.telegram_base_backoff = 1.0  # 秒
        self.telegram_noise_cooldown = 30.0  # 相同内容在该窗口内仅发送一次
        self._telegram_last_sent: Dict[str, float] = {}
        
        # 安全配置
        self.redact_patterns = [
            r"0x[a-fA-F0-9]{64}",  # 可能的私钥/签名
            r"[a-fA-F0-9]{64}",    # 64位十六进制字符串（私钥等）
        ]

        # RPC评分与排序配置
        # 维护每网络的RPC统计，用于动态排序
        # 格式：self.rpc_stats[network_key][rpc_url] = {
        #   'success': int, 'fail': int, 'latencies': [float], 'last_fail': ts
        # }
        self.rpc_stats: Dict[str, Dict[str, Dict]] = {}
        self.rpc_score_window = 50  # 仅保留最近N次
        self.rpc_slow_threshold = 2.0  # 秒，计入慢请求
        self.rpc_p95_weight = 0.6
        self.rpc_success_weight = 0.4

        # 可运行时更新的私有RPC特征列表
        self.private_rpc_indicators: List[str] = [
            'alchemy.com', 'ankr.com', 'infura.io', 'moralis.io',
            'quicknode.com', 'getblock.io', 'nodereal.io'
        ]

        # 代币扫描与元数据缓存优化
        # 缓存每个网络-合约的元数据，避免重复链上读取
        # key: f"{network}:{contract_address.lower()}" -> { 'symbol': str, 'decimals': int }
        self.token_metadata_cache: Dict[str, Dict] = {}
        
        # 用户主动添加的代币符号（大写），用于优先扫描
        self.user_added_tokens: set = set()
        
        # 最近活跃代币记录：address -> network -> token_symbol -> last_seen_timestamp
        self.active_tokens: Dict[str, Dict[str, Dict[str, float]]] = {}
        
        # 活跃代币保留时长（小时），超过时长将不再参与优先扫描
        self.active_token_ttl_hours = 24
        
        # 按地址记录是否已经完成第一次全量扫描
        self.address_full_scan_done: Dict[str, bool] = {}
        self.last_full_scan_time = 0.0
        
        # 数据备份配置
        self.backup_max_files = 5  # 保留最近N个备份
        self.backup_interval_hours = 6  # 每N小时备份一次
        self.last_backup_time = 0.0

        # 转账统计
        self.transfer_stats = {
            'total_attempts': 0,
            'successful_transfers': 0,
            'failed_transfers': 0,
            'total_value_transferred': 0.0,
            'last_reset': time.time(),
            'by_network': {},
            'by_token': {}
        }
        
        # RPC检测结果缓存，避免重复检测
        self.rpc_test_cache = {}  # network_key -> {'last_test': timestamp, 'results': {rpc_url: bool}}
        self.rpc_cache_ttl = 300  # 缓存5分钟
        
        # 设置日志
        self.setup_logging()
        
        # Web3连接
        self.web3_connections: Dict[str, Web3] = {}
        # 不在初始化时自动连接网络，由用户手动管理
        # self.init_web3_connections()
        
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
    
    def cleanup_memory(self):
        """清理内存和缓存"""
        try:
            import gc
            
            # 清理过期的RPC测试缓存
            current_time = time.time()
            cache_ttl = 1800  # 30分钟
            
            for network_key in list(self.rpc_test_cache.keys()):
                cache_data = self.rpc_test_cache[network_key]
                if current_time - cache_data.get('last_test', 0) > cache_ttl:
                    del self.rpc_test_cache[network_key]
            
            # 清理过期的代币元数据缓存
            token_cache_ttl = 7200  # 2小时
            for cache_key in list(self.token_metadata_cache.keys()):
                # 简单的TTL实现，如果缓存太大就清理一半
                if len(self.token_metadata_cache) > 1000:
                    # 清理一半最旧的缓存
                    keys_to_remove = list(self.token_metadata_cache.keys())[:500]
                    for key in keys_to_remove:
                        del self.token_metadata_cache[key]
                    break
            
            # 清理活跃代币追踪器中的过期数据
            active_token_ttl = 86400  # 24小时
            for address_network in list(self.active_token_tracker.keys()):
                tracker_data = self.active_token_tracker[address_network]
                for token in list(tracker_data.keys()):
                    if current_time - tracker_data[token] > active_token_ttl:
                        del tracker_data[token]
                
                # 如果某个地址-网络组合下没有活跃代币了，删除整个条目
                if not tracker_data:
                    del self.active_token_tracker[address_network]
            
            # 清理过期的被拉黑RPC（超过24小时自动解封）
            blocked_rpc_ttl = 86400  # 24小时
            rpcs_to_unblock = []
            for rpc_url, rpc_info in self.blocked_rpcs.items():
                if current_time - rpc_info.get('blocked_time', 0) > blocked_rpc_ttl:
                    rpcs_to_unblock.append(rpc_url)
            
            for rpc_url in rpcs_to_unblock:
                del self.blocked_rpcs[rpc_url]
                self.logger.info(f"自动解封过期RPC: {rpc_url}")
            
            if rpcs_to_unblock:
                print(f"{Fore.GREEN}🔄 自动解封 {len(rpcs_to_unblock)} 个过期的被拉黑RPC{Style.RESET_ALL}")
            
            # 强制垃圾回收
            collected = gc.collect()
            
            self.last_memory_cleanup = current_time
            self.logger.info(f"内存清理完成，回收了 {collected} 个对象")
            
            # 重置错误计数
            self.error_count = 0
            
        except Exception as e:
            self.logger.error(f"内存清理失败: {e}")
    
    def handle_error(self, error: Exception, context: str = ""):
        """统一的错误处理"""
        self.error_count += 1
        error_msg = f"错误[{self.error_count}] {context}: {error}"
        self.logger.error(error_msg)
        
        # 如果错误数量过多，触发内存清理
        if self.error_count >= self.max_errors:
            print(f"{Fore.YELLOW}⚠️ 错误数量过多({self.error_count})，执行内存清理...{Style.RESET_ALL}")
            self.cleanup_memory()
        
        # 如果是严重错误且在守护进程模式，考虑重启
        if self.daemon_mode and self.error_count >= self.max_errors * 2:
            self.request_restart("错误数量过多")
    
    def request_restart(self, reason: str):
        """请求重启程序"""
        current_time = time.time()
        
        # 检查重启间隔
        if current_time - self.last_restart_time < self.restart_interval:
            self.logger.warning(f"重启请求被拒绝，间隔太短: {reason}")
            return False
        
        # 检查重启次数
        if self.restart_count >= self.max_restarts:
            self.logger.error(f"达到最大重启次数({self.max_restarts})，程序退出: {reason}")
            print(f"{Fore.RED}❌ 程序重启次数过多，自动退出{Style.RESET_ALL}")
            return False
        
        self.restart_count += 1
        self.last_restart_time = current_time
        
        self.logger.info(f"程序重启请求[{self.restart_count}/{self.max_restarts}]: {reason}")
        print(f"{Fore.YELLOW}🔄 程序将重启({self.restart_count}/{self.max_restarts}): {reason}{Style.RESET_ALL}")
        
        # 保存状态
        try:
            self.save_state()
            self.save_wallets()
        except Exception as e:
            self.logger.error(f"重启前保存状态失败: {e}")
        
        return True
    
    def start_daemon_mode(self):
        """启动守护进程模式"""
        self.daemon_mode = True
        print(f"{Fore.CYAN}🛡️ 启动守护进程模式{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}💡 守护进程特性：{Style.RESET_ALL}")
        print(f"   • 自动错误恢复和重启机制")
        print(f"   • 定期内存清理({self.memory_cleanup_interval//60}分钟)")
        print(f"   • 最大重启次数: {self.max_restarts}")
        print(f"   • 错误阈值: {self.max_errors}")
        
        # 初始化守护进程相关状态
        self.error_count = 0
        self.restart_count = 0
        self.last_restart_time = time.time()
        self.last_memory_cleanup = time.time()
        
        # 执行一次初始内存清理
        self.cleanup_memory()
        
        # 启动监控
        return self.start_monitoring()
    
    def create_daemon_wrapper(self):
        """创建守护进程包装器脚本"""
        wrapper_script = """#!/bin/bash
# EVM监控守护进程包装器

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

LOG_FILE="daemon.log"
PID_FILE="daemon.pid"

# 颜色定义
RED='\\033[0;31m'
GREEN='\\033[0;32m'
YELLOW='\\033[1;33m'
NC='\\033[0m'

case "$1" in
    start)
        if [ -f "$PID_FILE" ]; then
            PID=$(cat "$PID_FILE")
            if ps -p $PID > /dev/null 2>&1; then
                echo -e "${YELLOW}守护进程已在运行 (PID: $PID)${NC}"
                exit 1
            else
                rm -f "$PID_FILE"
            fi
        fi
        
        echo -e "${GREEN}启动EVM监控守护进程...${NC}"
        nohup python3 evm_monitor.py --daemon > "$LOG_FILE" 2>&1 &
        echo $! > "$PID_FILE"
        echo -e "${GREEN}守护进程已启动 (PID: $!)${NC}"
        echo -e "${YELLOW}日志文件: $LOG_FILE${NC}"
        ;;
    stop)
        if [ -f "$PID_FILE" ]; then
            PID=$(cat "$PID_FILE")
            if ps -p $PID > /dev/null 2>&1; then
                echo -e "${YELLOW}停止守护进程 (PID: $PID)...${NC}"
                kill $PID
                rm -f "$PID_FILE"
                echo -e "${GREEN}守护进程已停止${NC}"
            else
                echo -e "${RED}守护进程未运行${NC}"
                rm -f "$PID_FILE"
            fi
        else
            echo -e "${RED}守护进程未运行${NC}"
        fi
        ;;
    restart)
        $0 stop
        sleep 2
        $0 start
        ;;
    status)
        if [ -f "$PID_FILE" ]; then
            PID=$(cat "$PID_FILE")
            if ps -p $PID > /dev/null 2>&1; then
                echo -e "${GREEN}守护进程正在运行 (PID: $PID)${NC}"
                echo -e "${YELLOW}日志文件: $LOG_FILE${NC}"
                echo -e "${YELLOW}最后10行日志:${NC}"
                tail -10 "$LOG_FILE" 2>/dev/null || echo "无法读取日志文件"
            else
                echo -e "${RED}守护进程未运行${NC}"
                rm -f "$PID_FILE"
            fi
        else
            echo -e "${RED}守护进程未运行${NC}"
        fi
        ;;
    log)
        if [ -f "$LOG_FILE" ]; then
            tail -f "$LOG_FILE"
        else
            echo -e "${RED}日志文件不存在${NC}"
        fi
        ;;
    *)
        echo "用法: $0 {start|stop|restart|status|log}"
        echo "  start   - 启动守护进程"
        echo "  stop    - 停止守护进程"
        echo "  restart - 重启守护进程"
        echo "  status  - 查看守护进程状态"
        echo "  log     - 查看实时日志"
        exit 1
        ;;
esac
"""
        
        try:
            with open("daemon.sh", "w", encoding="utf-8") as f:
                f.write(wrapper_script)
            
            import os
            os.chmod("daemon.sh", 0o755)
            
            print(f"{Fore.GREEN}✅ 守护进程包装器已创建: daemon.sh{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}使用方法：{Style.RESET_ALL}")
            print(f"  ./daemon.sh start   - 启动守护进程")
            print(f"  ./daemon.sh stop    - 停止守护进程")
            print(f"  ./daemon.sh status  - 查看状态")
            print(f"  ./daemon.sh log     - 查看日志")
            
        except Exception as e:
            print(f"{Fore.RED}❌ 创建守护进程包装器失败: {e}{Style.RESET_ALL}")

    def safe_input(self, prompt: str = "") -> str:
        """安全的输入函数，处理EOF错误"""
        try:
            # 检查是否强制交互模式
            force_interactive = getattr(self, '_force_interactive', False)
            
            # 检查交互式环境
            import sys
            import os
            
            # 更严格的交互式检测，但如果强制交互模式则跳过检测
            is_interactive = (
                force_interactive or (
                    sys.stdin.isatty() and 
                    sys.stdout.isatty() and 
                    os.isatty(0) and 
                    os.isatty(1)
                )
            )
            
            if not is_interactive:
                # 非交互式环境，返回默认值
                if "选项" in prompt or "选择" in prompt:
                    print(f"{Fore.YELLOW}⚠️  非交互式环境，自动退出{Style.RESET_ALL}")
                    return "0"
                else:
                    print(f"{Fore.YELLOW}⚠️  非交互式环境，使用空值{Style.RESET_ALL}")
                    return ""
            
            # 交互式环境或强制交互模式，正常读取输入
            try:
                # 刷新输出缓冲区确保提示显示
                sys.stdout.flush()
                sys.stderr.flush()
                
                # 如果是强制交互模式，提供额外的提示
                if force_interactive and not sys.stdin.isatty():
                    print(f"{Fore.CYAN}💡 强制交互模式：请输入您的选择{Style.RESET_ALL}")
                
                user_input = input(prompt)
                return user_input
            except KeyboardInterrupt:
                print(f"\n{Fore.YELLOW}👋 用户中断{Style.RESET_ALL}")
                return "0"
                
        except EOFError:
            print(f"\n{Fore.YELLOW}⚠️  EOF错误，程序无法读取输入{Style.RESET_ALL}")
            print(f"{Fore.CYAN}💡 这通常发生在通过管道运行程序时{Style.RESET_ALL}")
            print(f"{Fore.CYAN}💡 建议：在新的终端窗口中运行程序{Style.RESET_ALL}")
            print(f"{Fore.GREEN}   cd ~/evm_monitor && python3 evm_monitor.py{Style.RESET_ALL}")
            if "选项" in prompt or "选择" in prompt:
                return "0"  # 退出菜单
            return ""
        except Exception as e:
            print(f"\n{Fore.RED}❌ 输入错误: {e}{Style.RESET_ALL}")
            if "选项" in prompt or "选择" in prompt:
                return "0"  # 退出菜单
            return ""

    def init_web3_connections(self):
        """初始化Web3连接，支持多RPC端点故障转移"""
        print(f"{Fore.CYAN}🔗 正在连接区块链网络...{Style.RESET_ALL}")
        successful_connections = 0
        
        for network_key, network_info in self.networks.items():
            connected = False
            
            # 尝试连接多个RPC端点
            for i, rpc_url in enumerate(network_info['rpc_urls']):
                # 跳过被屏蔽的RPC
                if rpc_url in self.blocked_rpcs:
                    continue
                    
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
                'blocked_networks': self.blocked_networks,
                'transfer_stats': self.transfer_stats,
                'rpc_latency_history': self.rpc_latency_history,
                'blocked_rpcs': self.blocked_rpcs,
                'token_metadata_cache': self.token_metadata_cache,
                'active_tokens': self.active_tokens,
                'user_added_tokens': list(self.user_added_tokens),
                'address_full_scan_done': self.address_full_scan_done,
                'last_full_scan_time': self.last_full_scan_time,
                'rpc_stats': self.rpc_stats,
                'rpc_test_cache': self.rpc_test_cache,
                'last_save': datetime.now().isoformat()
            }
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)
            
            # 检查是否需要备份
            self._maybe_backup_state()
        except Exception as e:
            self.logger.error(f"保存状态失败: {e}")

    def _maybe_backup_state(self):
        """如果需要则创建状态文件备份"""
        try:
            now_ts = time.time()
            if now_ts - self.last_backup_time > self.backup_interval_hours * 3600:
                backup_name = f"{self.state_file}.{datetime.now().strftime('%Y%m%d-%H%M%S')}"
                import shutil
                if os.path.exists(self.state_file):
                    shutil.copy2(self.state_file, backup_name)
                    self.last_backup_time = now_ts
                    # 清理旧备份
                    self._cleanup_old_backups()
        except Exception as e:
            self.logger.warning(f"备份状态失败: {e}")

    def _cleanup_old_backups(self):
        """清理过多的备份文件"""
        try:
            import glob
            pattern = f"{self.state_file}.*"
            backups = sorted(glob.glob(pattern), reverse=True)
            for old_backup in backups[self.backup_max_files:]:
                try:
                    os.remove(old_backup)
                except Exception:
                    pass
        except Exception:
            pass

    def load_state(self):
        """加载监控状态"""
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r') as f:
                    state = json.load(f)
                self.monitored_addresses = state.get('monitored_addresses', {})
                self.blocked_networks = state.get('blocked_networks', {})
                
                # 加载转账统计，保持兼容性
                saved_stats = state.get('transfer_stats', {})
                if saved_stats:
                    self.transfer_stats.update(saved_stats)
                
                # 加载RPC延迟历史和屏蔽数据
                self.rpc_latency_history = state.get('rpc_latency_history', {})
                self.blocked_rpcs = state.get('blocked_rpcs', {})
                self.token_metadata_cache = state.get('token_metadata_cache', {})
                self.active_tokens = state.get('active_tokens', {})
                self.user_added_tokens = set(state.get('user_added_tokens', []))
                self.address_full_scan_done = state.get('address_full_scan_done', {})
                # 兼容性：如果存在旧的full_scan_done，迁移到新格式
                if 'full_scan_done' in state and state['full_scan_done']:
                    for addr in self.monitored_addresses.keys():
                        self.address_full_scan_done[addr] = True
                self.last_full_scan_time = state.get('last_full_scan_time', 0.0)
                self.rpc_stats = state.get('rpc_stats', {})
                self.rpc_test_cache = state.get('rpc_test_cache', {})
                
                self.logger.info(f"恢复监控状态: {len(self.monitored_addresses)} 个地址")
                self.logger.info(f"恢复屏蔽网络: {sum(len(nets) for nets in self.blocked_networks.values())} 个")
                if self.blocked_rpcs:
                    self.logger.info(f"恢复屏蔽RPC: {len(self.blocked_rpcs)} 个")
                self.logger.info(f"恢复转账统计: 成功{self.transfer_stats['successful_transfers']}次 失败{self.transfer_stats['failed_transfers']}次")
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
                network_name = self.networks[network]['name']
                if '🧪' in network_name:  # 测试网
                    color = Fore.YELLOW
                elif '🔷' in network_name or '🔵' in network_name:  # 主网
                    color = Fore.BLUE
            else:
                color = Fore.GREEN
                
            print(f"{Fore.GREEN}✅ {address[:10]}... 在 {color}{network_name}{Style.RESET_ALL} 有 {Fore.CYAN}{tx_count}{Style.RESET_ALL} 笔交易")
            # 不显示无交易历史的提示，减少屏幕垃圾
            
            return has_history
        except Exception as e:
            # 不显示连接失败的错误，减少干扰
            return False

    def check_transaction_history_concurrent(self, address: str, network_key: str, timeout: float = 1.0) -> Tuple[str, bool, float, str]:
        """并发检查地址在指定网络上是否有交易历史"""
        start_time = time.time()
        try:
            # 获取网络信息
            network_info = self.networks.get(network_key)
            if not network_info:
                return network_key, False, time.time() - start_time, "网络不存在"
            
            # 获取可用的RPC列表（排除被屏蔽的）
            available_rpcs = [rpc for rpc in network_info['rpc_urls'] if rpc not in self.blocked_rpcs]
            if not available_rpcs:
                return network_key, False, time.time() - start_time, "无可用RPC"
            
            # 选择最多5个RPC进行并发测试
            test_rpcs = available_rpcs[:5]
            
            def test_single_rpc(rpc_url):
                rpc_start = time.time()
                try:
                    w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={'timeout': timeout}))
                    if w3.is_connected():
                        # 验证链ID
                        chain_id = w3.eth.chain_id
                        if chain_id == network_info['chain_id']:
                            # 获取交易计数
                            nonce = w3.eth.get_transaction_count(address)
                            rpc_time = time.time() - rpc_start
                            return True, nonce > 0, rpc_time, rpc_url
                    return False, False, time.time() - rpc_start, rpc_url
                except Exception as e:
                    return False, False, time.time() - rpc_start, rpc_url
            
            # 并发测试RPC
            with ThreadPoolExecutor(max_workers=5) as executor:
                future_to_rpc = {executor.submit(test_single_rpc, rpc): rpc for rpc in test_rpcs}
                
                try:
                    for future in as_completed(future_to_rpc, timeout=timeout):
                        try:
                            success, has_history, rpc_time, rpc_url = future.result()
                            if success:
                                elapsed = time.time() - start_time
                                return network_key, has_history, elapsed, f"成功({rpc_time:.2f}s)"
                        except Exception:
                            continue
                except concurrent.futures.TimeoutError:
                    pass
            
            # 如果所有RPC都失败或超时
            elapsed = time.time() - start_time
            return network_key, False, elapsed, "所有RPC超时"
            
        except Exception as e:
            elapsed = time.time() - start_time
            return network_key, False, elapsed, f"错误: {str(e)[:30]}"

    def get_balance(self, address: str, network: str) -> Tuple[float, str]:
        """获取地址原生代币余额，返回(余额, 币种符号)"""
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

    def get_token_balance(self, address: str, token_symbol: str, network: str) -> Tuple[float, str, str]:
        """获取ERC20代币余额，返回(余额, 代币符号, 代币合约地址)"""
        try:
            if network not in self.web3_connections:
                return 0.0, "?", "?"
            
            if token_symbol not in self.tokens:
                return 0.0, "?", "?"
            
            token_config = self.tokens[token_symbol]
            if network not in token_config['contracts']:
                return 0.0, "?", "?"
            
            contract_address = token_config['contracts'][network]
            w3 = self.web3_connections[network]
            
            # 创建合约实例
            checksum_contract = w3.to_checksum_address(contract_address)
            contract = w3.eth.contract(
                address=checksum_contract,
                abi=self.erc20_abi
            )
            
            # 获取代币余额
            balance_raw = contract.functions.balanceOf(w3.to_checksum_address(address)).call()
            
            # 获取代币元数据（缓存）
            cache_key = f"{network}:{checksum_contract.lower()}"
            cached = self.token_metadata_cache.get(cache_key)
            if cached and 'decimals' in cached and isinstance(cached['decimals'], int):
                decimals = cached['decimals']
                symbol_out = cached.get('symbol', token_config['symbol'])
            else:
                # 获取代币精度
                try:
                    decimals = contract.functions.decimals().call()
                except Exception:
                    decimals = 18  # 默认精度
                # 获取代币符号（优先链上，回退配置）
                try:
                    onchain_symbol = contract.functions.symbol().call()
                    symbol_out = onchain_symbol if isinstance(onchain_symbol, str) and onchain_symbol else token_config['symbol']
                except Exception:
                    symbol_out = token_config['symbol']
                # 写入缓存
                self.token_metadata_cache[cache_key] = {'decimals': int(decimals), 'symbol': symbol_out}
            
            # 转换为人类可读格式
            balance = balance_raw / (10 ** decimals)
            # 记录活跃代币
            if balance > 0:
                self._record_active_token(address, network, token_symbol)
            return float(balance), symbol_out, contract_address
            
        except Exception as e:
            self.logger.error(f"获取代币余额失败 {token_symbol} {address} on {network}: {e}")
            return 0.0, "?", "?"

    def get_all_balances(self, address: str, network: str) -> Dict:
        """获取地址在指定网络上的所有余额（原生代币 + ERC20代币）
        首次扫描：全量遍历 self.tokens
        后续扫描：仅扫描用户主动添加或最近活跃的代币（命中优先清单），降低链上调用压力
        """
        balances = {}
        
        # 获取原生代币余额
        native_balance, native_currency = self.get_balance(address, network)
        if native_balance > 0:
            balances['native'] = {
                'balance': native_balance,
                'symbol': native_currency,
                'type': 'native',
                'contract': 'native'
            }
        
        # 构建本轮需要扫描的代币列表
        token_symbols_to_scan: List[str] = []
        if not self.address_full_scan_done.get(address, False):
            # 首轮全量
            token_symbols_to_scan = list(self.tokens.keys())
        else:
            # 后续仅扫描：用户主动添加 + 最近活跃（地址/网络维度）
            recent_active = self._get_recent_active_tokens(address, network)
            # 去重并保持顺序：用户添加的优先，其次活跃
            seen = set()
            for sym in list(self.user_added_tokens) + recent_active:
                up = sym.upper()
                if up in self.tokens and up not in seen:
                    token_symbols_to_scan.append(up)
                    seen.add(up)
            # 若为空，退化为全量的一小部分（例如稳定币/热门代币），避免完全不查
            if not token_symbols_to_scan:
                for fallback in ['USDT','USDC','DAI']:
                    if fallback in self.tokens:
                        token_symbols_to_scan.append(fallback)
        
        # 扫描ERC20余额
        for token_symbol in token_symbols_to_scan:
            token_balance, token_sym, contract_addr = self.get_token_balance(address, token_symbol, network)
            if token_balance > 0:
                balances[token_symbol] = {
                    'balance': token_balance,
                    'symbol': token_sym,
                    'type': 'erc20',
                    'contract': contract_addr
                }
        
        # 统计逻辑：若是首轮扫描，标记该地址已完成并记时间
        if not self.address_full_scan_done.get(address, False):
            self.address_full_scan_done[address] = True
            self.last_full_scan_time = time.time()
        
        return balances

    def estimate_gas_cost(self, network: str, token_type: str = 'native') -> Tuple[float, str]:
        """智能估算Gas费用，返回(gas费用ETH, 币种符号)"""
        try:
            if network not in self.web3_connections:
                return 0.0, "?"
            
            w3 = self.web3_connections[network]
            
            # 获取当前Gas价格
            try:
                gas_price = w3.eth.gas_price
            except Exception as e:
                self.logger.warning(f"获取Gas价格失败 {network}: {e}，使用默认值")
                gas_price = w3.to_wei(self.gas_price_gwei, 'gwei')
            
            # 根据交易类型估算Gas限制
            if token_type == 'native':
                gas_limit = 21000  # 原生代币转账
            else:
                gas_limit = 65000  # ERC20代币转账（通常需要更多Gas）
            
            # 计算总Gas费用
            gas_cost = gas_limit * gas_price
            gas_cost_eth = w3.from_wei(gas_cost, 'ether')
            currency = self.networks[network]['native_currency']
            
            return float(gas_cost_eth), currency
            
        except Exception as e:
            self.logger.error(f"估算Gas费用失败 {network}: {e}")
            return 0.001, "ETH"  # 返回保守估算

    def can_transfer(self, address: str, network: str, token_type: str = 'native', token_balance: float = 0) -> Tuple[bool, str]:
        """智能判断是否可以转账，返回(是否可转账, 原因)"""
        try:
            # 估算Gas费用
            gas_cost, _ = self.estimate_gas_cost(network, token_type)
            
            # 获取原生代币余额（用于支付Gas）
            native_balance, _ = self.get_balance(address, network)
            
            if token_type == 'native':
                # 原生代币转账：需要余额 > Gas费用 + 最小转账金额
                if native_balance < gas_cost + self.min_transfer_amount:
                    return False, f"余额不足支付Gas费用 (需要 {gas_cost:.6f} ETH)"
                return True, "可以转账"
            else:
                # ERC20代币转账：需要有代币余额且原生代币足够支付Gas
                if token_balance <= 0:
                    return False, "代币余额为0"
                if native_balance < gas_cost:
                    return False, f"原生代币不足支付Gas费用 (需要 {gas_cost:.6f} ETH)"
                return True, "可以转账"
                
        except Exception as e:
            self.logger.error(f"判断转账可行性失败: {e}")
            return False, "判断失败"

    def send_telegram_notification(self, message: str) -> bool:
        """发送Telegram通知"""
        if not self.telegram_enabled or not self.telegram_bot_token or not self.telegram_chat_id:
            return False
        
        try:
            import requests
            # 降噪：在窗口期内去重
            key = str(hash(message))
            now_ts = time.time()
            last_ts = self._telegram_last_sent.get(key, 0.0)
            if now_ts - last_ts < self.telegram_noise_cooldown:
                return True
            # 过滤高风险字段
            redacted = message
            import re
            for pat in self.redact_patterns:
                redacted = re.sub(pat, "[REDACTED]", redacted)
            # 限制长度
            if len(redacted) > 3500:
                redacted = redacted[:3500] + "\n…(truncated)"
            # 简单Markdown转义
            def escape_md(s: str) -> str:
                return s.replace("_", r"\_").replace("*", r"\*").replace("[", r"\[").replace("`", r"\`")
            redacted = escape_md(redacted)
            url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
            data = {
                'chat_id': self.telegram_chat_id,
                'text': redacted,
                'parse_mode': 'Markdown'
            }
            # 带退避重试
            backoff = self.telegram_base_backoff
            for attempt in range(self.telegram_max_retries):
                try:
                    response = requests.post(url, data=data, timeout=10)
                    if response.status_code == 200:
                        self._telegram_last_sent[key] = now_ts
                        self.logger.info("Telegram通知发送成功")
                        return True
                    # 429/5xx做退避
                    if response.status_code in (429, 500, 502, 503, 504):
                        time.sleep(backoff)
                        backoff *= 2
                        continue
                    self.logger.error(f"Telegram通知发送失败: {response.status_code}")
                    return False
                except Exception:
                    time.sleep(backoff)
                    backoff *= 2
            return False
                
        except Exception as e:
            self.logger.error(f"发送Telegram通知失败: {e}")
            return False

    def update_transfer_stats(self, success: bool, network: str, token_symbol: str, amount: float = 0):
        """更新转账统计"""
        try:
            self.transfer_stats['total_attempts'] += 1
            
            if success:
                self.transfer_stats['successful_transfers'] += 1
                self.transfer_stats['total_value_transferred'] += amount
            else:
                self.transfer_stats['failed_transfers'] += 1
            
            # 按网络统计
            if network not in self.transfer_stats['by_network']:
                self.transfer_stats['by_network'][network] = {'success': 0, 'failed': 0}
            
            if success:
                self.transfer_stats['by_network'][network]['success'] += 1
            else:
                self.transfer_stats['by_network'][network]['failed'] += 1
            
            # 按代币统计
            if token_symbol not in self.transfer_stats['by_token']:
                self.transfer_stats['by_token'][token_symbol] = {'success': 0, 'failed': 0, 'amount': 0.0}
            
            if success:
                self.transfer_stats['by_token'][token_symbol]['success'] += 1
                self.transfer_stats['by_token'][token_symbol]['amount'] += amount
            else:
                self.transfer_stats['by_token'][token_symbol]['failed'] += 1
                
        except Exception as e:
            self.logger.error(f"更新转账统计失败: {e}")

    def get_stats_summary(self) -> str:
        """获取统计摘要"""
        try:
            stats = self.transfer_stats
            success_rate = (stats['successful_transfers'] / stats['total_attempts'] * 100) if stats['total_attempts'] > 0 else 0
            
            summary = f"""
📊 *转账统计摘要*
━━━━━━━━━━━━━━━━━━━━
📈 总尝试次数: {stats['total_attempts']}
✅ 成功转账: {stats['successful_transfers']}
❌ 失败转账: {stats['failed_transfers']}
📊 成功率: {success_rate:.1f}%
💰 总转账价值: {stats['total_value_transferred']:.6f} ETH等价值

🌐 *网络统计*:
"""
            
            for network, net_stats in stats['by_network'].items():
                network_name = self.networks.get(network, {}).get('name', network)
                summary += f"• {network_name}: ✅{net_stats['success']} ❌{net_stats['failed']}\n"
            
            summary += "\n🪙 *代币统计*:\n"
            for token, token_stats in stats['by_token'].items():
                summary += f"• {token}: ✅{token_stats['success']} ❌{token_stats['failed']}"
                if token_stats['amount'] > 0:
                    summary += f" (💰{token_stats['amount']:.6f})"
                summary += "\n"
            
            return summary
            
        except Exception as e:
            self.logger.error(f"获取统计摘要失败: {e}")
            return "统计数据获取失败"

    def test_rpc_connection(self, rpc_url: str, expected_chain_id: int, timeout: int = 5, quick_test: bool = False) -> bool:
        """测试单个RPC连接，支持HTTP(S)和WebSocket"""
        import signal
        import time
        
        # 如果是快速测试（用于ChainList批量导入），使用1秒超时
        if quick_test:
            timeout = 1
            
        def timeout_handler(signum, frame):
            raise TimeoutError(f"RPC连接超时 ({timeout}秒)")
        
        try:
            from web3 import Web3
            
            # 设置超时信号
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(timeout)
            
            start_time = time.time()
            
            # 根据URL类型选择提供者
            if rpc_url.startswith(('ws://', 'wss://')):
                provider = Web3.WebsocketProvider(rpc_url, websocket_kwargs={'timeout': timeout})
            else:
                provider = Web3.HTTPProvider(rpc_url, request_kwargs={'timeout': timeout})
            
            w3 = Web3(provider)
            
            # 测试连接
            if not w3.is_connected():
                return False
            
            # 验证链ID
            chain_id = w3.eth.chain_id
            elapsed = time.time() - start_time
            
            # 如果是快速测试且超过1秒，也视为失败
            if quick_test and elapsed > 1.0:
                return False
                
            return chain_id == expected_chain_id
            
        except (TimeoutError, Exception):
            return False
        finally:
            # 取消超时信号
            signal.alarm(0)

    def test_rpc_concurrent(self, rpc_url: str, expected_chain_id: int, timeout: int = 3) -> tuple:
        """并发测试单个RPC连接，返回(是否成功, 响应时间, RPC类型)"""
        import time
        start_time = time.time()
        
        try:
            from web3 import Web3
            w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={'timeout': timeout}))
            
            # 测试连接
            if not w3.is_connected():
                elapsed = time.time() - start_time
                return False, elapsed, self.get_rpc_type(rpc_url)
            
            # 验证链ID
            chain_id = w3.eth.chain_id
            success = chain_id == expected_chain_id
            response_time = time.time() - start_time
            # 记录RPC评分
            self._record_rpc_stat(expected_chain_id, rpc_url, success, response_time)
            return success, response_time, self.get_rpc_type(rpc_url)
            
        except Exception:
            elapsed = time.time() - start_time
            self._record_rpc_stat(expected_chain_id, rpc_url, False, elapsed)
            return False, elapsed, self.get_rpc_type(rpc_url)

    def get_rpc_type(self, rpc_url: str) -> str:
        """识别RPC类型"""
        if 'alchemy.com' in rpc_url:
            return 'Alchemy'
        elif 'ankr.com' in rpc_url:
            return 'Ankr'
        else:
            return '公共节点'
    
    def is_public_rpc(self, rpc_url: str) -> bool:
        """判断是否为公共RPC节点（可运行时更新的特征列表）"""
        for indicator in self.private_rpc_indicators:
            if indicator in rpc_url.lower():
                return False
        return True

    def update_private_rpc_indicators(self, indicators: List[str]) -> None:
        """运行时更新私有RPC特征列表"""
        cleaned = []
        for s in indicators:
            if isinstance(s, str) and s.strip():
                cleaned.append(s.strip().lower())
        if cleaned:
            self.private_rpc_indicators = cleaned

    def get_token_info(self, token_address: str, network_key: str) -> Optional[Dict]:
        """获取代币信息（名称、符号、精度）"""
        if network_key not in self.web3_connections:
            return None
        
        web3 = self.web3_connections[network_key]
        
        try:
            # 验证地址格式
            if not web3.is_address(token_address):
                return None
            
            # 将地址转换为校验和格式
            token_address = web3.to_checksum_address(token_address)
            
            # 创建代币合约实例
            token_contract = web3.eth.contract(
                address=token_address,
                abi=self.erc20_abi
            )
            
            # 获取代币信息
            try:
                name = token_contract.functions.name().call()
            except:
                name = "Unknown Token"
            
            try:
                symbol = token_contract.functions.symbol().call()
            except:
                symbol = "UNK"
            
            try:
                decimals = token_contract.functions.decimals().call()
            except:
                decimals = 18
            
            # 尝试获取余额来验证合约是否有效
            try:
                # 使用零地址测试
                zero_address = "0x0000000000000000000000000000000000000000"
                token_contract.functions.balanceOf(zero_address).call()
            except:
                return None
            
            return {
                'name': name,
                'symbol': symbol,
                'decimals': decimals,
                'address': token_address,
                'network': network_key
            }
            
        except Exception as e:
            print(f"{Fore.RED}❌ 获取代币信息失败: {e}{Style.RESET_ALL}")
            return None

    def add_custom_token(self, token_info: Dict) -> bool:
        """添加自定义代币到tokens配置"""
        try:
            symbol = token_info['symbol'].upper()
            network = token_info['network']
            address = token_info['address']
            
            # 检查是否已存在相同符号的代币
            if symbol in self.tokens:
                # 如果已存在，添加到该代币的网络配置中
                if network not in self.tokens[symbol]['contracts']:
                    self.tokens[symbol]['contracts'][network] = address
                    print(f"{Fore.GREEN}✅ 已将 {symbol} 添加到 {self.networks[network]['name']}{Style.RESET_ALL}")
                    # 标记为用户主动添加
                    self.user_added_tokens.add(symbol)
                    return True
                else:
                    print(f"{Fore.YELLOW}⚠️ {symbol} 在 {self.networks[network]['name']} 上已存在{Style.RESET_ALL}")
                    return False
            else:
                # 创建新的代币配置
                self.tokens[symbol] = {
                    'name': token_info['name'],
                    'symbol': symbol,
                    'contracts': {
                        network: address
                    }
                }
                # 标记为用户主动添加
                self.user_added_tokens.add(symbol)
                print(f"{Fore.GREEN}✅ 已添加新代币 {symbol} ({token_info['name']}){Style.RESET_ALL}")
                return True
                
        except Exception as e:
            print(f"{Fore.RED}❌ 添加自定义代币失败: {e}{Style.RESET_ALL}")
            return False

    def _record_active_token(self, address: str, network: str, token_symbol: str) -> None:
        """记录某地址在网络上的活跃代币（最近余额>0）"""
        try:
            now_ts = time.time()
            if address not in self.active_tokens:
                self.active_tokens[address] = {}
            if network not in self.active_tokens[address]:
                self.active_tokens[address][network] = {}
            self.active_tokens[address][network][token_symbol] = now_ts
        except Exception:
            pass

    def _get_recent_active_tokens(self, address: str, network: str) -> List[str]:
        """获取某地址-网络下最近活跃的代币（在TTL内）"""
        try:
            ttl_seconds = self.active_token_ttl_hours * 3600
            now_ts = time.time()
            result: List[str] = []
            if address in self.active_tokens and network in self.active_tokens[address]:
                entries = self.active_tokens[address][network]
                # 清理过期数据
                to_delete = []
                for token_symbol, last_seen in entries.items():
                    if now_ts - last_seen <= ttl_seconds:
                        result.append(token_symbol)
                    else:
                        to_delete.append(token_symbol)
                for sym in to_delete:
                    del entries[sym]
            return result
        except Exception:
            return []

    def _classify_web3_error(self, error: Exception) -> Tuple[str, str]:
        """分类Web3错误并返回(错误类型, 用户友好提示)"""
        error_str = str(error).lower()
        error_type = type(error).__name__
        
        # 网络连接错误
        if any(keyword in error_str for keyword in ['connection', 'timeout', 'network', 'unreachable']):
            return "network", "网络连接问题，请检查网络设置或尝试其他RPC节点"
        
        # Gas相关错误
        if any(keyword in error_str for keyword in ['gas', 'insufficient', 'out of gas']):
            return "gas", "Gas费用不足或Gas限制过低，请增加Gas费用"
        
        # 合约调用错误
        if any(keyword in error_str for keyword in ['revert', 'execution reverted', 'contract']):
            return "contract", "智能合约执行失败，可能代币合约有问题或余额不足"
        
        # 地址格式错误
        if any(keyword in error_str for keyword in ['invalid', 'address', 'checksum']):
            return "address", "地址格式错误，请检查地址是否正确"
        
        # RPC相关错误
        if any(keyword in error_str for keyword in ['rpc', 'json', 'method not found']):
            return "rpc", "RPC节点错误，尝试切换到其他节点"
        
        return "unknown", f"未知错误类型 ({error_type})，请查看详细日志"

    def record_rpc_latency(self, rpc_url: str, latency: float) -> bool:
        """记录RPC延迟并检查是否需要屏蔽"""
        if rpc_url not in self.rpc_latency_history:
            self.rpc_latency_history[rpc_url] = []
        
        # 添加延迟记录
        self.rpc_latency_history[rpc_url].append(latency)
        
        # 只保留最近的检查记录
        if len(self.rpc_latency_history[rpc_url]) > self.rpc_latency_checks:
            self.rpc_latency_history[rpc_url] = self.rpc_latency_history[rpc_url][-self.rpc_latency_checks:]
        
        # 检查是否连续高延迟
        recent_latencies = self.rpc_latency_history[rpc_url]
        if len(recent_latencies) >= self.rpc_latency_checks:
            high_latency_count = sum(1 for lat in recent_latencies if lat > self.max_rpc_latency)
            
            # 如果连续检查都是高延迟，则屏蔽
            if high_latency_count >= self.rpc_latency_checks:
                self.block_rpc(rpc_url, f"连续{self.rpc_latency_checks}次延迟超过{self.max_rpc_latency}s")
                return True
        
        return False

    def _record_rpc_stat(self, expected_chain_id: int, rpc_url: str, success: bool, latency: float) -> None:
        """记录RPC成功/失败与延迟，用于打分排序"""
        try:
            # 找到network_key
            network_key = None
            for nk, info in self.networks.items():
                if info.get('chain_id') == expected_chain_id and rpc_url in info.get('rpc_urls', []):
                    network_key = nk
                    break
            if network_key is None:
                return
            if network_key not in self.rpc_stats:
                self.rpc_stats[network_key] = {}
            stats = self.rpc_stats[network_key].setdefault(rpc_url, {'success': 0, 'fail': 0, 'latencies': [], 'last_fail': 0.0})
            if success:
                stats['success'] += 1
            else:
                stats['fail'] += 1
                stats['last_fail'] = time.time()
            stats['latencies'].append(float(latency))
            if len(stats['latencies']) > self.rpc_score_window:
                stats['latencies'] = stats['latencies'][-self.rpc_score_window:]
        except Exception:
            pass

    def _score_rpc(self, network_key: str, rpc_url: str) -> float:
        """根据成功率和P95延迟给RPC打分，分数越高越优"""
        try:
            s = self.rpc_stats.get(network_key, {}).get(rpc_url)
            if not s:
                return 0.0
            total = s['success'] + s['fail']
            success_rate = (s['success'] / total) if total > 0 else 0.0
            latencies = sorted(s['latencies'])
            if latencies:
                idx = max(0, int(len(latencies) * 0.95) - 1)
                p95 = latencies[idx]
            else:
                p95 = self.max_rpc_latency
            # 归一化延迟（越小越好），映射到0..1
            lat_norm = max(0.0, 1.0 - min(p95 / (self.max_rpc_latency * 2), 1.0))
            score = self.rpc_success_weight * success_rate + self.rpc_p95_weight * lat_norm
            return score
        except Exception:
            return 0.0

    def block_rpc(self, rpc_url: str, reason: str):
        """屏蔽指定的RPC节点"""
        # 找到该RPC所属的网络
        network_name = "未知网络"
        network_key = None
        for net_key, net_info in self.networks.items():
            if rpc_url in net_info['rpc_urls']:
                network_name = net_info['name']
                network_key = net_key
                
                # 检查是否为最后一个RPC，如果是则不屏蔽
                if len(net_info['rpc_urls']) <= 1:
                    print(f"{Fore.YELLOW}⚠️ 跳过屏蔽: {network_name} 只剩最后一个RPC{Style.RESET_ALL}")
                    return
                
                # 从网络的RPC列表中移除
                net_info['rpc_urls'].remove(rpc_url)
                break
        
        # 记录屏蔽信息
        self.blocked_rpcs[rpc_url] = {
            'reason': reason,
            'blocked_time': time.time(),
            'network': network_name
        }
        
        print(f"{Fore.RED}🚫 已屏蔽高延迟RPC: {network_name}{Style.RESET_ALL}")
        print(f"   URL: {rpc_url[:50]}...")
        print(f"   原因: {reason}")
        self.logger.warning(f"屏蔽RPC节点: {rpc_url} - {reason}")

    def unblock_rpc(self, rpc_url: str, network_key: str) -> bool:
        """解除RPC节点屏蔽"""
        if rpc_url not in self.blocked_rpcs:
            return False
        
        if network_key not in self.networks:
            return False
        
        # 重新测试RPC连接
        if self.test_rpc_connection(rpc_url, self.networks[network_key]['chain_id']):
            # 恢复到RPC列表
            self.networks[network_key]['rpc_urls'].append(rpc_url)
            
            # 移除屏蔽记录
            del self.blocked_rpcs[rpc_url]
            
            # 清除延迟历史
            if rpc_url in self.rpc_latency_history:
                del self.rpc_latency_history[rpc_url]
            
            print(f"{Fore.GREEN}✅ 已解除RPC屏蔽: {self.networks[network_key]['name']}{Style.RESET_ALL}")
            print(f"   URL: {rpc_url[:50]}...")
            return True
        
        return False

    def check_blocked_rpcs_recovery(self):
        """检查被屏蔽的RPC是否可以恢复"""
        if not self.blocked_rpcs:
            return
        
        current_time = time.time()
        recovery_interval = 3600  # 1小时后尝试恢复
        
        rpcs_to_check = []
        for rpc_url, block_info in self.blocked_rpcs.items():
            if current_time - block_info['blocked_time'] > recovery_interval:
                rpcs_to_check.append(rpc_url)
        
        for rpc_url in rpcs_to_check:
            # 检查RPC是否仍在屏蔽列表中（可能已被其他地方移除）
            if rpc_url not in self.blocked_rpcs:
                continue
                
            # 找到对应的网络
            for net_key, net_info in self.networks.items():
                if self.blocked_rpcs[rpc_url]['network'] == net_info['name']:
                    self.unblock_rpc(rpc_url, net_key)
                    break

    def test_network_concurrent(self, network_key: str, max_workers: int = 10) -> dict:
        """并发测试单个网络的所有RPC（只对公共节点并发）"""
        import concurrent.futures
        import threading
        
        if network_key not in self.networks:
            return {}
            
        network_info = self.networks[network_key]
        results = {
            'name': network_info['name'],
            'working_rpcs': [],
            'failed_rpcs': [],
            'rpc_details': [],
            'fastest_rpc': None,
            'success_rate': 0
        }
        
        def test_single_rpc(rpc_url):
            return self.test_rpc_concurrent(rpc_url, network_info['chain_id'])
        
        # 分离公共节点和私有节点
        public_rpcs = []
        private_rpcs = []
        
        for rpc_url in network_info['rpc_urls']:
            if self.is_public_rpc(rpc_url):
                public_rpcs.append(rpc_url)
            else:
                private_rpcs.append(rpc_url)
        
        # 并发测试公共节点（基于当前打分排序，优先测试高分）
        if public_rpcs:
            sorted_public = sorted(public_rpcs, key=lambda u: self._score_rpc(network_key, u), reverse=True)
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_rpc = {
                    executor.submit(test_single_rpc, rpc_url): rpc_url 
                    for rpc_url in sorted_public
                }
                for future in concurrent.futures.as_completed(future_to_rpc):
                    rpc_url = future_to_rpc[future]
                    try:
                        success, response_time, rpc_type = future.result()
                        if success:
                            blocked = self.record_rpc_latency(rpc_url, response_time)
                            if blocked:
                                continue
                        rpc_detail = {
                            'url': rpc_url,
                            'success': success,
                            'response_time': response_time,
                            'type': rpc_type,
                            'is_public': True
                        }
                        results['rpc_details'].append(rpc_detail)
                        if success:
                            results['working_rpcs'].append(rpc_url)
                        else:
                            results['failed_rpcs'].append(rpc_url)
                    except Exception:
                        results['failed_rpcs'].append(rpc_url)
        
        # 串行测试私有节点（避免频繁请求被限制），同样按打分排序
        for rpc_url in sorted(private_rpcs, key=lambda u: self._score_rpc(network_key, u), reverse=True):
            try:
                success, response_time, rpc_type = test_single_rpc(rpc_url)
                
                # 记录延迟并检查是否需要屏蔽
                if success:
                    blocked = self.record_rpc_latency(rpc_url, response_time)
                    if blocked:
                        continue  # 跳过已屏蔽的RPC
                
                rpc_detail = {
                    'url': rpc_url,
                    'success': success,
                    'response_time': response_time,
                    'type': rpc_type,
                    'is_public': False
                }
                
                results['rpc_details'].append(rpc_detail)
                
                if success:
                    results['working_rpcs'].append(rpc_url)
                else:
                    results['failed_rpcs'].append(rpc_url)
                    
                # 私有节点间添加短暂延迟
                time.sleep(0.1)
                    
            except Exception as e:
                results['failed_rpcs'].append(rpc_url)
        
        # 计算成功率
        total_rpcs = len(network_info['rpc_urls'])
        results['success_rate'] = len(results['working_rpcs']) / total_rpcs * 100 if total_rpcs > 0 else 0
        
        # 找出最快的RPC
        working_details = [r for r in results['rpc_details'] if r['success']]
        if working_details:
            results['fastest_rpc'] = min(working_details, key=lambda x: x['response_time'])
        
        return results

    def test_all_rpcs(self) -> Dict[str, Dict]:
        """测试所有网络的RPC连接状态（使用并发优化）"""
        print(f"\n{Back.BLUE}{Fore.WHITE} 🚀 高速并发RPC连接测试 🚀 {Style.RESET_ALL}")
        print(f"{Fore.YELLOW}📡 正在并发测试所有网络的RPC节点连接状态...{Style.RESET_ALL}\n")
        
        import concurrent.futures
        import time
        
        results = {}
        start_time = time.time()
        
        # 并发测试所有网络
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            future_to_network = {
                executor.submit(self.test_network_concurrent, network_key): network_key 
                for network_key in self.networks.keys()
            }
            
            completed_count = 0
            total_networks = len(self.networks)
            
            for future in concurrent.futures.as_completed(future_to_network):
                network_key = future_to_network[future]
                completed_count += 1
                
                try:
                    result = future.result()
                    if result:
                        results[network_key] = result
                        
                        # 显示测试结果
                        success_rate = result['success_rate']
                        if success_rate == 100:
                            status_color = Fore.GREEN
                            status_icon = "🟢"
                        elif success_rate >= 50:
                            status_color = Fore.YELLOW
                            status_icon = "🟡"
                        else:
                            status_color = Fore.RED
                            status_icon = "🔴"
                        
                        # 按RPC类型统计
                        rpc_stats = {'公共节点': 0, 'Alchemy': 0, 'Ankr': 0}
                        for detail in result['rpc_details']:
                            if detail['success']:
                                rpc_stats[detail['type']] += 1
                        
                        print(f"{status_icon} {Fore.CYAN}[{completed_count}/{total_networks}]{Style.RESET_ALL} {result['name']}")
                        print(f"   成功率: {status_color}{success_rate:.1f}%{Style.RESET_ALL} "
                              f"({len(result['working_rpcs'])}/{len(result['working_rpcs']) + len(result['failed_rpcs'])})")
                        print(f"   节点类型: 公共节点({rpc_stats['公共节点']}) Alchemy({rpc_stats['Alchemy']}) Ankr({rpc_stats['Ankr']})")
                        
                        # 显示最快RPC
                        if result['fastest_rpc']:
                            fastest = result['fastest_rpc']
                            print(f"   最快节点: {Fore.GREEN}{fastest['type']}{Style.RESET_ALL} "
                                  f"({fastest['response_time']:.3f}s)")
                        print()
                        
                except Exception as e:
                    print(f"{Fore.RED}❌ {self.networks[network_key]['name']} 测试失败: {e}{Style.RESET_ALL}")
        
        elapsed_time = time.time() - start_time
        print(f"{Fore.GREEN}🎉 并发测试完成！耗时: {elapsed_time:.2f}秒{Style.RESET_ALL}")
        
        return results

    def auto_disable_failed_rpcs(self) -> int:
        """自动屏蔽失效的RPC节点"""
        print(f"\n{Back.RED}{Fore.WHITE} 🛠️ 自动屏蔽失效RPC 🛠️ {Style.RESET_ALL}")
        
        disabled_count = 0
        
        for network_key, network_info in self.networks.items():
            working_rpcs = []
            
            for rpc_url in network_info['rpc_urls']:
                if self.test_rpc_connection(rpc_url, network_info['chain_id']):
                    working_rpcs.append(rpc_url)
                else:
                    disabled_count += 1
                    print(f"{Fore.RED}❌ 屏蔽失效RPC: {network_info['name']} - {rpc_url[:50]}...{Style.RESET_ALL}")
            
            if working_rpcs:
                self.networks[network_key]['rpc_urls'] = working_rpcs
                print(f"{Fore.GREEN}✅ {network_info['name']}: 保留 {len(working_rpcs)} 个可用RPC{Style.RESET_ALL}")
            else:
                print(f"{Fore.RED}⚠️ 警告: {network_info['name']} 没有可用的RPC节点！{Style.RESET_ALL}")
        
        print(f"\n{Fore.CYAN}📊 总计屏蔽了 {disabled_count} 个失效RPC节点{Style.RESET_ALL}")
        return disabled_count

    def add_custom_rpc(self, network_key: str, rpc_url: str) -> bool:
        """为指定网络添加自定义RPC"""
        if network_key not in self.networks:
            print(f"{Fore.RED}❌ 网络 {network_key} 不存在{Style.RESET_ALL}")
            return False
        
        network_info = self.networks[network_key]
        
        # 测试RPC连接
        print(f"{Fore.YELLOW}🔍 测试自定义RPC连接...{Style.RESET_ALL}")
        if not self.test_rpc_connection(rpc_url, network_info['chain_id']):
            print(f"{Fore.RED}❌ RPC连接测试失败: {rpc_url}{Style.RESET_ALL}")
            return False
        
        # 检查是否已存在
        if rpc_url in network_info['rpc_urls']:
            print(f"{Fore.YELLOW}⚠️ RPC已存在: {rpc_url}{Style.RESET_ALL}")
            return False
        
        # 添加到RPC列表开头（高优先级）
        self.networks[network_key]['rpc_urls'].insert(0, rpc_url)
        print(f"{Fore.GREEN}✅ 成功添加自定义RPC到 {network_info['name']}: {rpc_url}{Style.RESET_ALL}")
        
        return True

    def transfer_erc20_token(self, from_address: str, private_key: str, to_address: str, 
                           token_symbol: str, amount: float, network: str) -> bool:
        """ERC20代币转账函数 - 带详细过程显示"""
        print(f"      {Back.MAGENTA}{Fore.WHITE} 🚀 开始ERC20代币转账流程 🚀 {Style.RESET_ALL}")
        
        try:
            # 步骤1: 检查网络和代币支持
            print(f"      {Fore.CYAN}📡 [1/8] 检查网络和代币支持...{Style.RESET_ALL}", end="", flush=True)
            if network not in self.web3_connections:
                print(f" {Fore.RED}❌ 网络 {network} 未连接{Style.RESET_ALL}")
                return False
            
            if token_symbol not in self.tokens:
                print(f" {Fore.RED}❌ 不支持的代币: {token_symbol}{Style.RESET_ALL}")
                return False
            
            token_config = self.tokens[token_symbol]
            if network not in token_config['contracts']:
                print(f" {Fore.RED}❌ 代币 {token_symbol} 在 {network} 上不可用{Style.RESET_ALL}")
                return False
            
            w3 = self.web3_connections[network]
            contract_address = token_config['contracts'][network]
            network_name = self.networks[network]['name']
            print(f" {Fore.GREEN}✅ {token_symbol} 在 {network_name} 可用{Style.RESET_ALL}")
            
            # 步骤2: 验证地址格式
            print(f"      {Fore.CYAN}🔍 [2/8] 验证地址格式...{Style.RESET_ALL}", end="", flush=True)
            try:
                to_address = w3.to_checksum_address(to_address)
                from_address = w3.to_checksum_address(from_address)
                contract_address = w3.to_checksum_address(contract_address)
            except Exception as e:
                print(f" {Fore.RED}❌ 地址格式错误: {e}{Style.RESET_ALL}")
                return False
            
            if from_address.lower() == to_address.lower():
                print(f" {Fore.YELLOW}⚠️ 跳过自己转给自己的交易{Style.RESET_ALL}")
                return False
            print(f" {Fore.GREEN}✅ 地址格式有效{Style.RESET_ALL}")
            
            # 步骤3: 创建合约实例
            print(f"      {Fore.CYAN}📝 [3/8] 创建合约实例...{Style.RESET_ALL}", end="", flush=True)
            contract = w3.eth.contract(address=contract_address, abi=self.erc20_abi)
            print(f" {Fore.GREEN}✅ 合约: {contract_address[:10]}...{contract_address[-6:]}{Style.RESET_ALL}")
            
            # 步骤4: 获取代币精度
            print(f"      {Fore.CYAN}🔢 [4/8] 获取代币精度...{Style.RESET_ALL}", end="", flush=True)
            try:
                decimals = contract.functions.decimals().call()
            except:
                decimals = 18
            amount_wei = int(amount * (10 ** decimals))
            print(f" {Fore.GREEN}✅ 精度: {decimals}, 转换金额: {amount_wei}{Style.RESET_ALL}")
            
            # 步骤5: 检查Gas费用
            print(f"      {Fore.CYAN}⛽ [5/8] 检查Gas费用...{Style.RESET_ALL}", end="", flush=True)
            gas_cost, _ = self.estimate_gas_cost(network, 'erc20')
            native_balance, _ = self.get_balance(from_address, network)
            
            if native_balance < gas_cost:
                print(f" {Fore.RED}❌ 原生代币不足支付Gas费用: 需要 {gas_cost:.6f} ETH{Style.RESET_ALL}")
                return False
            print(f" {Fore.GREEN}✅ Gas费用充足: {gas_cost:.6f} ETH{Style.RESET_ALL}")
            
            # 步骤6: 获取Gas价格
            print(f"      {Fore.CYAN}💸 [6/8] 获取Gas价格...{Style.RESET_ALL}", end="", flush=True)
            try:
                gas_price = w3.eth.gas_price
                min_gas_price = w3.to_wei(self.gas_price_gwei, 'gwei')
                gas_price = max(gas_price, min_gas_price)
                gas_price_gwei = w3.from_wei(gas_price, 'gwei')
            except:
                gas_price = w3.to_wei(self.gas_price_gwei, 'gwei')
                gas_price_gwei = self.gas_price_gwei
            print(f" {Fore.GREEN}✅ {float(gas_price_gwei):.2f} Gwei{Style.RESET_ALL}")
            
            # 步骤7: 构建和签名交易
            print(f"      {Fore.CYAN}📝 [7/8] 构建和签名交易...{Style.RESET_ALL}", end="", flush=True)
            nonce = w3.eth.get_transaction_count(from_address)
            transfer_function = contract.functions.transfer(to_address, amount_wei)
            
            transaction = {
                'to': contract_address,
                'value': 0,
                'gas': 65000,
                'gasPrice': gas_price,
                'nonce': nonce,
                'data': transfer_function._encode_transaction_data(),
                'chainId': self.networks[network]['chain_id']
            }
            
            signed_txn = w3.eth.account.sign_transaction(transaction, private_key)
            print(f" {Fore.GREEN}✅ 交易已签名，Nonce: {nonce}{Style.RESET_ALL}")
            
            # 步骤8: 发送交易
            print(f"      {Fore.CYAN}📤 [8/8] 发送交易...{Style.RESET_ALL}", end="", flush=True)
            start_time = time.time()
            tx_hash = w3.eth.send_raw_transaction(signed_txn.rawTransaction)
            send_time = time.time() - start_time
            print(f" {Fore.GREEN}✅ 交易已发送 ({send_time:.2f}s){Style.RESET_ALL}")
            
            print(f"      {Back.GREEN}{Fore.WHITE} 🎉 ERC20转账完成！{Style.RESET_ALL}")
            print(f"      🪙 代币: {Fore.YELLOW}{token_symbol}{Style.RESET_ALL}")
            print(f"      💰 金额: {Fore.YELLOW}{amount:.6f} {token_symbol}{Style.RESET_ALL}")
            print(f"      📤 发送方: {Fore.CYAN}{from_address[:10]}...{from_address[-6:]}{Style.RESET_ALL}")
            print(f"      📥 接收方: {Fore.CYAN}{to_address[:10]}...{to_address[-6:]}{Style.RESET_ALL}")
            print(f"      📋 交易哈希: {Fore.GREEN}{tx_hash.hex()}{Style.RESET_ALL}")
            print(f"      ⛽ Gas费用: {Fore.YELLOW}{gas_cost:.6f} ETH{Style.RESET_ALL}")
            
            # 更新统计
            self.update_transfer_stats(True, network, token_symbol, amount)
            
            # 发送Telegram通知
            network_name = self.networks[network]['name']
            notification_msg = f"""
🎉 *ERC20转账成功!*

🪙 代币: {token_symbol}
💰 金额: {amount:.6f}
🌐 网络: {network_name}
📤 发送方: `{from_address[:10]}...{from_address[-6:]}`
📥 接收方: `{to_address[:10]}...{to_address[-6:]}`
📋 交易哈希: `{tx_hash.hex()}`

{self.get_stats_summary()}
"""
            self.send_telegram_notification(notification_msg)
            
            self.logger.info(f"ERC20转账成功: {amount} {token_symbol}, {from_address} -> {to_address}, tx: {tx_hash.hex()}")
            return True
            
        except KeyboardInterrupt:
            print(f"\n{Fore.YELLOW}⚠️ 用户取消ERC20转账操作{Style.RESET_ALL}")
            raise
        except Exception as e:
            print(f"{Fore.RED}❌ ERC20转账失败: {e}{Style.RESET_ALL}")
            
            # 更新统计
            self.update_transfer_stats(False, network, token_symbol, 0)
            
            # 发送失败通知
            network_name = self.networks[network]['name']
            failure_msg = f"""
❌ *ERC20转账失败!*

🪙 代币: {token_symbol}
💰 金额: {amount:.6f}
🌐 网络: {network_name}
📤 发送方: `{from_address[:10]}...{from_address[-6:]}`
📥 接收方: `{to_address[:10]}...{to_address[-6:]}`
❌ 错误: {str(e)[:100]}

{self.get_stats_summary()}
"""
            self.send_telegram_notification(failure_msg)
            
            self.logger.error(f"ERC20转账失败 {token_symbol} {from_address} -> {to_address}: {e}")
            return False

    def transfer_funds(self, from_address: str, private_key: str, to_address: str, amount: float, network: str) -> bool:
        """转账函数 - 带详细过程显示"""
        print(f"      {Back.CYAN}{Fore.WHITE} 🚀 开始原生代币转账流程 🚀 {Style.RESET_ALL}")
        
        try:
            # 步骤1: 检查网络连接
            print(f"      {Fore.CYAN}📡 [1/7] 检查网络连接...{Style.RESET_ALL}", end="", flush=True)
            if network not in self.web3_connections:
                print(f" {Fore.RED}❌ 网络 {network} 未连接{Style.RESET_ALL}")
                return False
            w3 = self.web3_connections[network]
            network_name = self.networks[network]['name']
            print(f" {Fore.GREEN}✅ {network_name} 连接正常{Style.RESET_ALL}")
            
            # 步骤2: 验证地址格式
            print(f"      {Fore.CYAN}🔍 [2/7] 验证地址格式...{Style.RESET_ALL}", end="", flush=True)
            try:
                to_address = w3.to_checksum_address(to_address)
                from_address = w3.to_checksum_address(from_address)
            except Exception as e:
                print(f" {Fore.RED}❌ 地址格式错误: {e}{Style.RESET_ALL}")
                return False
            
            # 检查是否是自己转给自己
            if from_address.lower() == to_address.lower():
                print(f" {Fore.YELLOW}⚠️ 跳过自己转给自己的交易{Style.RESET_ALL}")
                return False
            print(f" {Fore.GREEN}✅ 地址格式有效{Style.RESET_ALL}")
            
            # 步骤3: 获取Gas价格
            print(f"      {Fore.CYAN}⛽ [3/7] 获取Gas价格...{Style.RESET_ALL}", end="", flush=True)
            try:
                gas_price = w3.eth.gas_price
                min_gas_price = w3.to_wei(self.gas_price_gwei, 'gwei')
                gas_price = max(gas_price, min_gas_price)
                gas_price_gwei = w3.from_wei(gas_price, 'gwei')
            except:
                gas_price = w3.to_wei(self.gas_price_gwei, 'gwei')
                gas_price_gwei = self.gas_price_gwei
            print(f" {Fore.GREEN}✅ {float(gas_price_gwei):.2f} Gwei{Style.RESET_ALL}")
            
            # 步骤4: 计算费用和余额检查
            print(f"      {Fore.CYAN}💰 [4/7] 检查余额和计算费用...{Style.RESET_ALL}", end="", flush=True)
            gas_cost = self.gas_limit * gas_price
            gas_cost_eth = w3.from_wei(gas_cost, 'ether')
            current_balance, currency = self.get_balance(from_address, network)
            
            if amount + float(gas_cost_eth) > current_balance:
                amount = current_balance - float(gas_cost_eth) - 0.0001
                if amount <= 0:
                    print(f" {Fore.RED}❌ 余额不足以支付Gas费用{Style.RESET_ALL}")
                    return False
                print(f" {Fore.YELLOW}⚠️ 调整金额为 {amount:.6f} {currency}（扣除Gas费用）{Style.RESET_ALL}")
            else:
                print(f" {Fore.GREEN}✅ 余额充足，Gas费用: {float(gas_cost_eth):.6f} {currency}{Style.RESET_ALL}")
            
            # 步骤5: 构建交易
            print(f"      {Fore.CYAN}📝 [5/7] 构建交易...{Style.RESET_ALL}", end="", flush=True)
            nonce = w3.eth.get_transaction_count(from_address)
            transaction = {
                'to': to_address,
                'value': w3.to_wei(amount, 'ether'),
                'gas': self.gas_limit,
                'gasPrice': gas_price,
                'nonce': nonce,
                'chainId': self.networks[network]['chain_id']
            }
            print(f" {Fore.GREEN}✅ Nonce: {nonce}{Style.RESET_ALL}")
            
            # 步骤6: 签名交易
            print(f"      {Fore.CYAN}🔐 [6/7] 签名交易...{Style.RESET_ALL}", end="", flush=True)
            signed_txn = w3.eth.account.sign_transaction(transaction, private_key)
            print(f" {Fore.GREEN}✅ 交易已签名{Style.RESET_ALL}")
            
            # 步骤7: 发送交易
            print(f"      {Fore.CYAN}📤 [7/7] 发送交易...{Style.RESET_ALL}", end="", flush=True)
            start_time = time.time()
            tx_hash = w3.eth.send_raw_transaction(signed_txn.rawTransaction)
            send_time = time.time() - start_time
            print(f" {Fore.GREEN}✅ 交易已发送 ({send_time:.2f}s){Style.RESET_ALL}")
            
            print(f"      {Back.GREEN}{Fore.WHITE} 🎉 转账完成！{Style.RESET_ALL}")
            print(f"      💰 金额: {Fore.YELLOW}{amount:.6f} {currency}{Style.RESET_ALL}")
            print(f"      📤 发送方: {Fore.CYAN}{from_address[:10]}...{from_address[-6:]}{Style.RESET_ALL}")
            print(f"      📥 接收方: {Fore.CYAN}{to_address[:10]}...{to_address[-6:]}{Style.RESET_ALL}")
            print(f"      📋 交易哈希: {Fore.GREEN}{tx_hash.hex()}{Style.RESET_ALL}")
            print(f"      ⛽ Gas费用: {Fore.YELLOW}{float(gas_cost_eth):.6f} {currency}{Style.RESET_ALL}")
            
            # 更新统计
            self.update_transfer_stats(True, network, currency, amount)
            
            # 发送Telegram通知
            network_name = self.networks[network]['name']
            notification_msg = f"""
🎉 *原生代币转账成功!*

💎 代币: {currency}
💰 金额: {amount:.6f}
🌐 网络: {network_name}
📤 发送方: `{from_address[:10]}...{from_address[-6:]}`
📥 接收方: `{to_address[:10]}...{to_address[-6:]}`
📋 交易哈希: `{tx_hash.hex()}`

{self.get_stats_summary()}
"""
            self.send_telegram_notification(notification_msg)
            
            self.logger.info(f"转账成功: {amount} {currency}, {from_address} -> {to_address}, tx: {tx_hash.hex()}")
            return True
            
        except KeyboardInterrupt:
            print(f"\n{Fore.YELLOW}⚠️ 用户取消转账操作{Style.RESET_ALL}")
            raise  # 重新抛出以便上层函数处理
        except Exception as e:
            print(f"{Fore.RED}❌ 转账失败: {e}{Style.RESET_ALL}")
            
            # 更新统计
            currency = self.networks[network]['native_currency']
            self.update_transfer_stats(False, network, currency, 0)
            
            # 发送失败通知
            network_name = self.networks[network]['name']
            failure_msg = f"""
❌ *原生代币转账失败!*

💎 代币: {currency}
💰 金额: {amount:.6f}
🌐 网络: {network_name}
📤 发送方: `{from_address[:10]}...{from_address[-6:]}`
📥 接收方: `{to_address[:10]}...{to_address[-6:]}`
❌ 错误: {str(e)[:100]}

{self.get_stats_summary()}
"""
            self.send_telegram_notification(failure_msg)
            
            self.logger.error(f"转账失败 {from_address} -> {to_address}: {e}")
            # 详细错误信息
            if "invalid fields" in str(e).lower():
                print(f"{Fore.CYAN}💡 提示：地址格式可能有问题，正在检查...{Style.RESET_ALL}")
            return False

    def scan_addresses(self, only_new_addresses=False):
        """扫描所有地址，检查交易历史并建立监控列表"""
        addresses_to_scan = []
        
        if only_new_addresses:
            # 只扫描新添加的地址（不在监控列表和屏蔽列表中的）
            for address in self.wallets.keys():
                if (address not in self.monitored_addresses and 
                    address not in self.blocked_networks):
                    addresses_to_scan.append(address)
            
            if not addresses_to_scan:
                print(f"\n{Fore.GREEN}✅ 没有新地址需要扫描{Style.RESET_ALL}")
                return
            
            print(f"\n{Fore.CYAN}🔍 开始扫描新添加的地址交易历史...{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}📊 发现 {len(addresses_to_scan)} 个新地址需要扫描{Style.RESET_ALL}")
        else:
            # 扫描所有地址
            addresses_to_scan = list(self.wallets.keys())
            print(f"\n{Fore.CYAN}🔍 开始扫描地址交易历史...{Style.RESET_ALL}")
        
        start_ts = time.time()
        total_addresses = len(addresses_to_scan)
        scanned_count = 0
        
        for i, address in enumerate(addresses_to_scan, 1):
            print(f"\n{Back.BLUE}{Fore.WHITE} 🔍 检查地址 ({i}/{total_addresses}) {Style.RESET_ALL} {Fore.CYAN}{address}{Style.RESET_ALL}")
            address_networks = []
            blocked_networks = []
            
            network_count = 0
            total_networks = len(self.networks)
            found_networks = 0
            
            # 并发扫描网络 - 分批处理
            network_keys = list(self.networks.keys())
            batch_size = 5  # 每批并发5个网络
            
            for batch_start in range(0, len(network_keys), batch_size):
                batch_end = min(batch_start + batch_size, len(network_keys))
                batch_networks = network_keys[batch_start:batch_end]
                
                # 动态调整超时时间
                available_rpc_count = sum(1 for nk in batch_networks 
                                        if len([rpc for rpc in self.networks[nk]['rpc_urls'] 
                                               if rpc not in self.blocked_rpcs]) > 0)
                timeout = 1.0 if available_rpc_count >= 3 else 2.0
                
                print(f"  {Back.BLUE}{Fore.WHITE} 🚀 并发扫描批次 {batch_start//batch_size + 1} ({len(batch_networks)} 个网络, 超时:{timeout}s) {Style.RESET_ALL}")
                
                # 并发检查这一批网络
                with ThreadPoolExecutor(max_workers=5) as executor:
                    future_to_network = {
                        executor.submit(self.check_transaction_history_concurrent, address, nk, timeout): nk 
                        for nk in batch_networks
                    }
                    
                    # 收集结果
                    batch_results = {}
                    for future in as_completed(future_to_network, timeout=timeout + 0.5):
                        try:
                            network_key, has_history, elapsed, status = future.result()
                            batch_results[network_key] = (has_history, elapsed, status)
                        except Exception as e:
                            network_key = future_to_network[future]
                            batch_results[network_key] = (False, timeout, f"异常: {str(e)[:20]}")
                    
                    # 显示这一批的结果
                    for nk in batch_networks:
                        network_count += 1
                        network_name = self.networks[nk]['name']
                        
                        if nk in batch_results:
                            has_history, elapsed, status = batch_results[nk]
                            
                            if has_history:
                                address_networks.append(nk)
                                found_networks += 1
                                result_color = Fore.GREEN
                                result_icon = "✅"
                                result_text = f"有交易 ({status})"
                            else:
                                blocked_networks.append(nk)
                                result_color = Fore.RED
                                result_icon = "❌"
                                result_text = f"无交易 ({status})"
                        else:
                            # 超时的网络
                            blocked_networks.append(nk)
                            result_color = Fore.YELLOW
                            result_icon = "⏱️"
                            result_text = "超时"
                        
                        print(f"    {Fore.CYAN}🌐 [{network_count:2d}/{total_networks}] {network_name:<35}{Style.RESET_ALL} {result_color}{result_icon} {result_text}{Style.RESET_ALL}")
                
                # 每批显示进度总结
                print(f"    {Fore.MAGENTA}📊 批次完成: 已扫描 {network_count}/{total_networks} 个网络，发现 {found_networks} 个有交易历史{Style.RESET_ALL}")
                
                # 批次间短暂休息
                if batch_end < len(network_keys):
                    time.sleep(0.1)

            
            # 显示该地址的扫描总结
            print(f"\n  {Back.MAGENTA}{Fore.WHITE} 📋 地址扫描总结 {Style.RESET_ALL}")
            print(f"    🌐 总网络数: {total_networks}")
            print(f"    ✅ 有交易历史: {Fore.GREEN}{len(address_networks)}{Style.RESET_ALL} 个")
            print(f"    ❌ 无交易历史: {Fore.RED}{len(blocked_networks)}{Style.RESET_ALL} 个")
            
            # 更新监控列表
            if address_networks:
                self.monitored_addresses[address] = {
                    'networks': address_networks,
                    'last_check': time.time()
                }
                print(f"    {Fore.GREEN}🎯 该地址将被监控{Style.RESET_ALL}")
                
                # 显示监控的网络（显示更多）
                print(f"    {Fore.GREEN}📋 监控网络列表:{Style.RESET_ALL}")
                for net in address_networks[:5]:  # 显示前5个
                    network_name = self.networks[net]['name']
                    print(f"      • {network_name}")
                if len(address_networks) > 5:
                    print(f"      • ... 和其他 {len(address_networks) - 5} 个网络")
            else:
                print(f"    {Fore.YELLOW}⚠️ 该地址将被跳过（无交易历史）{Style.RESET_ALL}")
        
            # 保存被屏蔽的网络列表
            if blocked_networks:
                self.blocked_networks[address] = blocked_networks
            
            scanned_count += 1
            
            # 显示整体进度
            progress_percent = (scanned_count / total_addresses) * 100
            print(f"\n{Back.CYAN}{Fore.WHITE} 📈 整体进度: {scanned_count}/{total_addresses} ({progress_percent:.1f}%) {Style.RESET_ALL}")
        
        elapsed = time.time() - start_ts
        print(f"\n{Back.GREEN}{Fore.BLACK} ✨ 扫描完成 ✨ {Style.RESET_ALL}")
        print(f"{Fore.GREEN}✅ 监控地址: {len(self.monitored_addresses)} 个{Style.RESET_ALL}")
        print(f"{Fore.RED}❌ 屏蔽网络: {sum(len(nets) for nets in self.blocked_networks.values())} 个{Style.RESET_ALL}")
        print(f"{Fore.CYAN}⏱️ 用时: {elapsed:.2f}s{Style.RESET_ALL}")
        self.save_state()

    def monitor_loop(self):
        """监控循环"""
        
        print(f"\n{Fore.CYAN}🚀 开始监控...{Style.RESET_ALL}")
        print(f"{Fore.GREEN}🎉 监控已成功启动！{Style.RESET_ALL}")
        print(f"\n{Fore.YELLOW}📝 提示：按 Ctrl+C 可以优雅退出监控{Style.RESET_ALL}")
        print(f"{Fore.CYAN}🔄 系统将自动监控所有钱包余额并转账到目标账户{Style.RESET_ALL}")
        
        round_count = 0
        
        try:
            while self.monitoring:
                try:
                    round_count += 1
                    print(f"\n{Back.CYAN}{Fore.WHITE} 🔍 第 {round_count} 轮检查开始 {Style.RESET_ALL}")
                    
                    total_addresses = len(self.monitored_addresses)
                    current_address = 0
                    
                    for address, address_info in self.monitored_addresses.items():
                        if not self.monitoring:
                            break
                        
                        current_address += 1
                        private_key = self.wallets.get(address)
                        if not private_key:
                            continue
                        
                        print(f"\n{Fore.MAGENTA}📄 检查地址 ({current_address}/{total_addresses}): {Fore.CYAN}{address[:10]}...{address[-8:]}{Style.RESET_ALL}")
                        
                        total_networks = len(address_info['networks'])
                        current_network = 0
                        
                        for network in address_info['networks']:
                            if not self.monitoring:
                                break
                            
                            current_network += 1
                            network_name = self.networks[network]['name']
                            
                            print(f"  {Fore.CYAN}🌐 检查网络 ({current_network}/{total_networks}): {network_name}{Style.RESET_ALL}")
                            
                            try:
                                # 🚀 全链全代币监控 - 获取所有余额
                                all_balances = self.get_all_balances(address, network)
                                
                                if not all_balances:
                                    print(f"    {Fore.YELLOW}⚠️ 无余额或获取失败{Style.RESET_ALL}")
                                    continue
                                
                                # 网络名称颜色化
                                if '🧪' in network_name:  # 测试网
                                    network_color = f"{Back.YELLOW}{Fore.BLACK}{network_name}{Style.RESET_ALL}"
                                elif '🔷' in network_name or '🔵' in network_name:  # 主网
                                    network_color = f"{Back.BLUE}{Fore.WHITE}{network_name}{Style.RESET_ALL}"
                                else:  # 其他网络
                                    network_color = f"{Back.GREEN}{Fore.BLACK}{network_name}{Style.RESET_ALL}"
                                
                                # 显示发现的余额数量
                                balance_count = len([b for b in all_balances.values() if b['balance'] > 0])
                                if balance_count > 0:
                                    print(f"    {Fore.GREEN}💰 发现 {balance_count} 个代币有余额{Style.RESET_ALL}")
                                
                                # 处理每个代币余额
                                transferable_found = False
                                for token_key, token_info in all_balances.items():
                                    if not self.monitoring:
                                        break
                                    
                                    balance = token_info['balance']
                                    symbol = token_info['symbol']
                                    token_type = token_info['type']
                                    
                                    if balance <= 0:
                                        continue
                                    
                                    # 智能判断是否可以转账
                                    can_transfer, reason = self.can_transfer(address, network, token_type, balance)
                                    
                                    if token_type == 'native' and balance > self.min_transfer_amount and can_transfer:
                                        # 原生代币转账
                                        transferable_found = True
                                        print(f"\n    {Back.RED}{Fore.WHITE} 💰 原生代币 💰 {Style.RESET_ALL} {Fore.YELLOW}{balance:.6f} {symbol}{Style.RESET_ALL} in {Fore.CYAN}{address[:10]}...{Style.RESET_ALL} on {network_color}")
                                        
                                        if self.target_wallet:
                                            print(f"    {Fore.CYAN}🚀 开始转账到目标账户...{Style.RESET_ALL}")
                                            try:
                                                if self.transfer_funds(address, private_key, self.target_wallet, balance, network):
                                                    print(f"    {Fore.GREEN}✅ 转账成功！{Style.RESET_ALL}")
                                                    address_info['last_check'] = time.time()
                                                    self.save_state()
                                                else:
                                                    print(f"    {Fore.RED}❌ 转账失败{Style.RESET_ALL}")
                                            except KeyboardInterrupt:
                                                print(f"\n{Fore.YELLOW}⚠️ 用户取消转账，停止监控{Style.RESET_ALL}")
                                                self.monitoring = False
                                                return
                                        else:
                                            print(f"    {Fore.CYAN}💡 未设置目标账户，跳过转账{Style.RESET_ALL}")
                                    
                                    elif token_type == 'erc20' and balance > 0 and can_transfer:
                                        # ERC20代币转账
                                        transferable_found = True
                                        print(f"\n    {Back.MAGENTA}{Fore.WHITE} 🪙 ERC20代币 🪙 {Style.RESET_ALL} {Fore.GREEN}{balance:.6f} {symbol}{Style.RESET_ALL} in {Fore.CYAN}{address[:10]}...{Style.RESET_ALL} on {network_color}")
                                        
                                        if self.target_wallet:
                                            print(f"    {Fore.CYAN}🚀 开始转账ERC20代币...{Style.RESET_ALL}")
                                            try:
                                                if self.transfer_erc20_token(address, private_key, self.target_wallet, token_key, balance, network):
                                                    print(f"    {Fore.GREEN}✅ ERC20转账成功！{Style.RESET_ALL}")
                                                    address_info['last_check'] = time.time()
                                                    self.save_state()
                                                else:
                                                    print(f"    {Fore.RED}❌ ERC20转账失败{Style.RESET_ALL}")
                                            except KeyboardInterrupt:
                                                print(f"\n{Fore.YELLOW}⚠️ 用户取消转账，停止监控{Style.RESET_ALL}")
                                                self.monitoring = False
                                                return
                                        else:
                                            print(f"    {Fore.CYAN}💡 未设置目标账户，跳过转账{Style.RESET_ALL}")
                                    
                                    elif balance > 0 and not can_transfer:
                                        # 有余额但不能转账
                                        token_icon = "💎" if token_type == 'native' else "🪙"
                                        print(f"    {Fore.MAGENTA}{token_icon} {Fore.CYAN}{address[:10]}...{Style.RESET_ALL} on {network_color}: {Fore.YELLOW}{balance:.6f} {symbol}{Style.RESET_ALL} {Fore.RED}({reason}){Style.RESET_ALL}")
                                
                                if not transferable_found and balance_count == 0:
                                    print(f"    {Fore.YELLOW}⚠️ 未发现可转账的余额{Style.RESET_ALL}")
                                
                            except KeyboardInterrupt:
                                print(f"\n{Fore.YELLOW}⚠️ 监控被中断{Style.RESET_ALL}")
                                self.monitoring = False
                                return
                            except Exception as e:
                                error_type, user_hint = self._classify_web3_error(e)
                                print(f"{Fore.RED}❌ 检查余额失败 {address[:10]}... on {network}{Style.RESET_ALL}")
                                print(f"{Fore.YELLOW}💡 {user_hint}{Style.RESET_ALL}")
                                
                                # 使用统一错误处理
                                self.handle_error(e, f"余额检查 {address[:10]} {network}")
                                
                                if error_type in ["network", "rpc"]:
                                    # 网络/RPC错误时记录但继续
                                    continue
                                else:
                                    continue
                    
                    # 等待下一次检查（支持中断）
                    print(f"\n{Back.CYAN}{Fore.WHITE} ✨ 第 {round_count} 轮检查完成 ✨ {Style.RESET_ALL}")
                    print(f"{Fore.CYAN}🕒 等待 {self.monitor_interval} 秒后进行下一轮检查... (按Ctrl+C退出){Style.RESET_ALL}")
                
                    # 检查是否需要进行内存清理
                    current_time = time.time()
                    if current_time - self.last_memory_cleanup > self.memory_cleanup_interval:
                        print(f"{Fore.CYAN}🧹 执行定期内存清理...{Style.RESET_ALL}")
                        self.cleanup_memory()
                
                    # 检查被屏蔽的RPC是否可以恢复
                    self.check_blocked_rpcs_recovery()
                    
                    for i in range(self.monitor_interval):
                        if not self.monitoring:
                            break
                        time.sleep(1)
                        
                except KeyboardInterrupt:
                    print(f"\n{Fore.YELLOW}⚠️ 监控被中断{Style.RESET_ALL}")
                    self.monitoring = False
                    break
                except Exception as e:
                    # 使用统一错误处理
                    self.handle_error(e, "监控循环")
                    print(f"{Fore.RED}❌ 监控循环出错，5秒后重试: {e}{Style.RESET_ALL}")
                    
                    # 如果在守护进程模式且错误过多，考虑重启
                    if self.daemon_mode and self.error_count >= self.max_errors:
                        if self.request_restart("监控循环错误过多"):
                            break
                    
                    try:
                        time.sleep(5)
                    except KeyboardInterrupt:
                        print(f"\n{Fore.YELLOW}⚠️ 监控被中断{Style.RESET_ALL}")
                        break
        
        except KeyboardInterrupt:
            print(f"\n{Fore.YELLOW}⚠️ 监控被中断{Style.RESET_ALL}")
        except Exception as e:
            self.logger.error(f"监控循环严重错误: {e}")
            print(f"{Fore.RED}❌ 监控循环遇到严重错误，已记录日志{Style.RESET_ALL}")
        finally:
            self.monitoring = False
            print(f"\n{Fore.GREEN}✅ 监控已优雅停止{Style.RESET_ALL}")
            print(f"{Fore.CYAN}📊 总共完成 {round_count} 轮监控检查{Style.RESET_ALL}")
            # 异常退出时确保保存状态
            try:
                self.save_state()
                print(f"{Fore.CYAN}💾 状态已保存{Style.RESET_ALL}")
            except Exception as e:
                print(f"{Fore.RED}❌ 保存状态失败: {e}{Style.RESET_ALL}")

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
        
        # 检查是否有已监控的地址，如果没有或有新地址则扫描
        if not self.monitored_addresses:
            # 第一次启动，全量扫描
            self.scan_addresses(only_new_addresses=False)
        else:
            # 检查是否有新地址需要扫描
            new_addresses = [addr for addr in self.wallets.keys() 
                           if addr not in self.monitored_addresses and addr not in self.blocked_networks]
            if new_addresses:
                print(f"\n{Fore.YELLOW}🔍 发现 {len(new_addresses)} 个新地址，开始扫描...{Style.RESET_ALL}")
                self.scan_addresses(only_new_addresses=True)
            else:
                print(f"\n{Fore.GREEN}✅ 使用已缓存的扫描结果，跳过重复扫描{Style.RESET_ALL}")
                print(f"{Fore.CYAN}📊 监控地址: {len(self.monitored_addresses)} 个{Style.RESET_ALL}")
        
        if not self.monitored_addresses:
            print(f"{Fore.RED}❌ 没有符合条件的地址可监控{Style.RESET_ALL}")
            return False
        
        # 开始监控
        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self.monitor_loop)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()
        
        print(f"\n{Fore.GREEN}🎉 监控已成功启动！{Style.RESET_ALL}")
        
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
            print(f"{Fore.GREEN}9.{Style.RESET_ALL} 🔍 RPC节点检测")
            print(f"{Fore.GREEN}10.{Style.RESET_ALL} 🪙 添加自定义代币")
            print(f"{Fore.GREEN}11.{Style.RESET_ALL} 🛡️ 守护进程管理")
            
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
                elif choice == '9':
                    self.menu_rpc_testing()
                elif choice == '10':
                    self.menu_add_custom_token()
                elif choice == '11':
                    self.menu_daemon_management()
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
        blocked_count = sum(len(nets) for nets in self.blocked_networks.values())
        if blocked_count > 0:
            print(f"  🚫 屏蔽网络: {Fore.RED}{blocked_count}{Style.RESET_ALL} 个 {Fore.YELLOW}(无交易历史){Style.RESET_ALL}")
        
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
        
        # 支持的代币信息
        print(f"\n{Fore.YELLOW}🪙 支持的代币：{Style.RESET_ALL}")
        print(f"  {Fore.BLUE}💎 原生代币{Style.RESET_ALL}: ETH, BNB, MATIC, AVAX 等")
        print(f"  {Fore.GREEN}🪙 ERC20代币{Style.RESET_ALL}: {Fore.CYAN}{len(self.tokens)}{Style.RESET_ALL} 种")
        
        # 显示代币详情
        for token_symbol, token_config in self.tokens.items():
            networks_count = len(token_config['contracts'])
            print(f"    • {Fore.YELLOW}{token_symbol}{Style.RESET_ALL} ({token_config['name']}) - {Fore.CYAN}{networks_count}{Style.RESET_ALL} 个网络")
            
        # 智能Gas功能
        print(f"\n{Fore.YELLOW}⚡ 智能功能：{Style.RESET_ALL}")
        print(f"  {Fore.GREEN}✅{Style.RESET_ALL} 🧠 智能Gas估算")
        print(f"  {Fore.GREEN}✅{Style.RESET_ALL} 🔍 全链代币扫描")
        print(f"  {Fore.GREEN}✅{Style.RESET_ALL} 💰 自动转账判断")
        print(f"  {Fore.GREEN}✅{Style.RESET_ALL} 🚫 无效网络屏蔽")
        print(f"  {Fore.GREEN}✅{Style.RESET_ALL} 📱 Telegram实时通知")
        
        # Telegram通知配置
        print(f"\n{Fore.YELLOW}📱 Telegram通知：{Style.RESET_ALL}")
        tg_status = f"{Fore.GREEN}已启用{Style.RESET_ALL}" if self.telegram_enabled else f"{Fore.RED}已禁用{Style.RESET_ALL}"
        print(f"  📡 状态: {tg_status}")
        if self.telegram_enabled:
            print(f"  🤖 Bot ID: {self.telegram_bot_token.split(':')[0]}")
            print(f"  💬 Chat ID: {self.telegram_chat_id}")
        
        # 转账统计
        stats = self.transfer_stats
        success_rate = (stats['successful_transfers'] / stats['total_attempts'] * 100) if stats['total_attempts'] > 0 else 0
        print(f"\n{Fore.YELLOW}📊 转账统计：{Style.RESET_ALL}")
        print(f"  📈 总尝试: {Fore.CYAN}{stats['total_attempts']}{Style.RESET_ALL} 次")
        print(f"  ✅ 成功: {Fore.GREEN}{stats['successful_transfers']}{Style.RESET_ALL} 次")
        print(f"  ❌ 失败: {Fore.RED}{stats['failed_transfers']}{Style.RESET_ALL} 次")
        print(f"  📊 成功率: {Fore.YELLOW}{success_rate:.1f}%{Style.RESET_ALL}")
        print(f"  💰 总价值: {Fore.GREEN}{stats['total_value_transferred']:.6f}{Style.RESET_ALL} ETH等价值")
        
        if stats['by_network']:
            print(f"\n{Fore.YELLOW}🌐 网络统计：{Style.RESET_ALL}")
            for network, net_stats in list(stats['by_network'].items())[:5]:  # 只显示前5个
                network_name = self.networks.get(network, {}).get('name', network)[:20]
                print(f"  • {network_name}: {Fore.GREEN}✅{net_stats['success']}{Style.RESET_ALL} {Fore.RED}❌{net_stats['failed']}{Style.RESET_ALL}")
            
        if stats['by_token']:
            print(f"\n{Fore.YELLOW}🪙 代币统计：{Style.RESET_ALL}")
            for token, token_stats in list(stats['by_token'].items())[:5]:  # 只显示前5个
                print(f"  • {token}: {Fore.GREEN}✅{token_stats['success']}{Style.RESET_ALL} {Fore.RED}❌{token_stats['failed']}{Style.RESET_ALL}")
                if token_stats['amount'] > 0:
                    print(f"    💰 总额: {token_stats['amount']:.6f}")
        
        if self.monitored_addresses:
            print(f"\n{Fore.YELLOW}🔍 监控地址详情:{Style.RESET_ALL}")
            for addr, info in self.monitored_addresses.items():
                networks = ', '.join(info['networks'])
                last_check = datetime.fromtimestamp(info['last_check']).strftime('%Y-%m-%d %H:%M:%S')
                print(f"  {Fore.GREEN}✅{Style.RESET_ALL} {Fore.CYAN}{addr[:8]}...{addr[-6:]}{Style.RESET_ALL} | 🌐 {Fore.YELLOW}{len(info['networks'])}{Style.RESET_ALL} 个网络 | 🕒 {last_check}")
        
        if self.blocked_networks:
            print(f"\n{Fore.YELLOW}🚫 屏蔽网络详情:{Style.RESET_ALL}")
            for addr, networks in self.blocked_networks.items():
                print(f"  {Fore.RED}❌{Style.RESET_ALL} {Fore.CYAN}{addr[:8]}...{addr[-6:]}{Style.RESET_ALL} | 🚫 {Fore.RED}{len(networks)}{Style.RESET_ALL} 个网络 {Fore.YELLOW}(无交易历史){Style.RESET_ALL}")
        
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
        print(f"{Back.BLUE}{Fore.WHITE} 🔍 检查网络连接状态和RPC健康度... {Style.RESET_ALL}")
        
        # 获取RPC状态数据（使用缓存）
        print(f"\n{Fore.CYAN}📊 获取网络状态数据...{Style.RESET_ALL}")
        rpc_results = self.get_cached_rpc_results()
        
        # 显示所有网络状态
        connected_networks = []
        failed_networks = []
        
        print(f"\n{Fore.YELLOW}📈 网络连接状态：{Style.RESET_ALL}")
        print(f"{Fore.CYAN}─" * 80 + f"{Style.RESET_ALL}")
            
        for network_key, network_info in self.networks.items():
            # 获取RPC健康度信息
            rpc_info = rpc_results.get(network_key, {})
            available_rpcs = rpc_info.get('available_count', 0)
            total_rpcs = rpc_info.get('total_count', len(network_info['rpc_urls']))
            
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
            rpc_status = f"({Fore.CYAN}{available_rpcs}/{total_rpcs}{Style.RESET_ALL} RPC可用)"
            
            print(f"  {status_icon} {color}{network_name:<25}{Style.RESET_ALL} ({currency:<5}) - {color}{status_text}{Style.RESET_ALL} {rpc_status}")
        
        print(f"\n{Fore.CYAN}─" * 80 + f"{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}📊 连接统计：{Style.RESET_ALL}")
        print(f"  🟢 {Fore.GREEN}已连接: {len(connected_networks)} 个网络{Style.RESET_ALL}")
        print(f"  🔴 {Fore.RED}未连接: {len(failed_networks)} 个网络{Style.RESET_ALL}")
        
        # 显示RPC健康度统计
        if rpc_results:
            total_rpcs = sum(r['total_count'] for r in rpc_results.values())
            working_rpcs = sum(r['available_count'] for r in rpc_results.values())
            print(f"  📡 {Fore.CYAN}RPC健康度: {working_rpcs}/{total_rpcs} ({working_rpcs/total_rpcs*100:.1f}%){Style.RESET_ALL}")
        
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

    def menu_daemon_management(self):
        """菜单：守护进程管理"""
        print(f"\n{Fore.CYAN}✨ ====== 🛡️ 守护进程管理 🛡️ ====== ✨{Style.RESET_ALL}")
        print(f"{Back.BLUE}{Fore.WHITE} 🚀 管理程序的守护进程模式和稳定性功能 {Style.RESET_ALL}")
        
        print(f"\n{Fore.YELLOW}📊 当前状态：{Style.RESET_ALL}")
        print(f"  守护进程模式: {'🟢 启用' if self.daemon_mode else '🔴 禁用'}")
        print(f"  错误计数: {Fore.YELLOW}{self.error_count}/{self.max_errors}{Style.RESET_ALL}")
        print(f"  重启计数: {Fore.YELLOW}{self.restart_count}/{self.max_restarts}{Style.RESET_ALL}")
        
        # 显示内存清理状态
        import time
        time_since_cleanup = int(time.time() - self.last_memory_cleanup)
        cleanup_interval = self.memory_cleanup_interval
        print(f"  上次内存清理: {Fore.CYAN}{time_since_cleanup//60}分钟前{Style.RESET_ALL}")
        print(f"  下次内存清理: {Fore.CYAN}{(cleanup_interval - time_since_cleanup)//60}分钟后{Style.RESET_ALL}")
        
        print(f"\n{Fore.YELLOW}🔧 管理选项：{Style.RESET_ALL}")
        print(f"  {Fore.GREEN}1.{Style.RESET_ALL} 🧹 立即执行内存清理")
        print(f"  {Fore.GREEN}2.{Style.RESET_ALL} 📊 查看系统状态详情")
        print(f"  {Fore.GREEN}3.{Style.RESET_ALL} ⚙️  调整守护进程参数")
        print(f"  {Fore.GREEN}4.{Style.RESET_ALL} 📜 创建守护进程启动脚本")
        print(f"  {Fore.GREEN}5.{Style.RESET_ALL} 🔄 重置错误计数")
        print(f"  {Fore.RED}0.{Style.RESET_ALL} 🔙 返回主菜单")
        
        choice = self.safe_input(f"\n{Fore.YELLOW}🔢 请选择操作 (0-5): {Style.RESET_ALL}").strip()
        
        try:
            if choice == '1':
                # 立即执行内存清理
                print(f"\n{Fore.CYAN}🧹 正在执行内存清理...{Style.RESET_ALL}")
                self.cleanup_memory()
                print(f"{Fore.GREEN}✅ 内存清理完成！{Style.RESET_ALL}")
                
            elif choice == '2':
                # 查看系统状态详情
                self._show_system_status()
                
            elif choice == '3':
                # 调整守护进程参数
                self._adjust_daemon_params()
                
            elif choice == '4':
                # 创建守护进程启动脚本
                self.create_daemon_wrapper()
                
            elif choice == '5':
                # 重置错误计数
                self.error_count = 0
                self.restart_count = 0
                print(f"{Fore.GREEN}✅ 错误计数和重启计数已重置{Style.RESET_ALL}")
                
            elif choice == '0':
                return
            else:
                print(f"\n{Fore.RED}❌ 无效选择{Style.RESET_ALL}")
                
        except Exception as e:
            print(f"\n{Fore.RED}❌ 操作失败: {e}{Style.RESET_ALL}")
        
        self.safe_input(f"\n{Fore.MAGENTA}🔙 按回车键继续...{Style.RESET_ALL}")
    
    def _show_system_status(self):
        """显示系统状态详情"""
        print(f"\n{Back.CYAN}{Fore.BLACK} 📊 系统状态详情 📊 {Style.RESET_ALL}")
        
        import psutil
        import gc
        
        try:
            # 内存使用情况
            process = psutil.Process()
            memory_info = process.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024
            
            print(f"\n{Fore.YELLOW}💾 内存使用：{Style.RESET_ALL}")
            print(f"  当前内存: {Fore.CYAN}{memory_mb:.1f} MB{Style.RESET_ALL}")
            print(f"  虚拟内存: {Fore.CYAN}{memory_info.vms / 1024 / 1024:.1f} MB{Style.RESET_ALL}")
            
            # CPU使用情况
            cpu_percent = process.cpu_percent()
            print(f"\n{Fore.YELLOW}🖥️ CPU使用：{Style.RESET_ALL}")
            print(f"  CPU占用: {Fore.CYAN}{cpu_percent:.1f}%{Style.RESET_ALL}")
            
        except ImportError:
            print(f"{Fore.YELLOW}⚠️ 需要安装psutil来查看系统资源信息{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}❌ 获取系统信息失败: {e}{Style.RESET_ALL}")
        
        # 缓存状态
        print(f"\n{Fore.YELLOW}🗃️ 缓存状态：{Style.RESET_ALL}")
        print(f"  RPC测试缓存: {Fore.CYAN}{len(self.rpc_test_cache)}{Style.RESET_ALL} 个网络")
        print(f"  代币元数据缓存: {Fore.CYAN}{len(self.token_metadata_cache)}{Style.RESET_ALL} 个代币")
        print(f"  活跃代币追踪: {Fore.CYAN}{len(self.active_token_tracker)}{Style.RESET_ALL} 个地址")
        print(f"  被拉黑RPC: {Fore.CYAN}{len(self.blocked_rpcs)}{Style.RESET_ALL} 个")
        
        # 连接状态
        print(f"\n{Fore.YELLOW}🌐 网络连接：{Style.RESET_ALL}")
        print(f"  已连接网络: {Fore.CYAN}{len(self.web3_connections)}{Style.RESET_ALL} 个")
        print(f"  监控地址: {Fore.CYAN}{len(self.monitored_addresses)}{Style.RESET_ALL} 个")
        print(f"  钱包数量: {Fore.CYAN}{len(self.wallets)}{Style.RESET_ALL} 个")
        
        # 垃圾回收信息
        gc_stats = gc.get_stats()
        print(f"\n{Fore.YELLOW}🗑️ 垃圾回收：{Style.RESET_ALL}")
        print(f"  GC统计: {Fore.CYAN}{len(gc_stats)}{Style.RESET_ALL} 个世代")
        print(f"  可回收对象: {Fore.CYAN}{len(gc.garbage)}{Style.RESET_ALL} 个")
    
    def _adjust_daemon_params(self):
        """调整守护进程参数"""
        print(f"\n{Back.YELLOW}{Fore.BLACK} ⚙️ 守护进程参数调整 ⚙️ {Style.RESET_ALL}")
        
        print(f"\n{Fore.YELLOW}当前参数：{Style.RESET_ALL}")
        print(f"  1. 最大错误数: {Fore.CYAN}{self.max_errors}{Style.RESET_ALL}")
        print(f"  2. 最大重启次数: {Fore.CYAN}{self.max_restarts}{Style.RESET_ALL}")
        print(f"  3. 重启间隔: {Fore.CYAN}{self.restart_interval//60}分钟{Style.RESET_ALL}")
        print(f"  4. 内存清理间隔: {Fore.CYAN}{self.memory_cleanup_interval//60}分钟{Style.RESET_ALL}")
        
        param_choice = self.safe_input(f"\n{Fore.YELLOW}选择要调整的参数 (1-4, 0取消): {Style.RESET_ALL}").strip()
        
        try:
            if param_choice == '1':
                new_value = int(self.safe_input(f"输入新的最大错误数 (当前: {self.max_errors}): "))
                if 1 <= new_value <= 1000:
                    self.max_errors = new_value
                    print(f"{Fore.GREEN}✅ 最大错误数已设置为: {new_value}{Style.RESET_ALL}")
                else:
                    print(f"{Fore.RED}❌ 值必须在1-1000之间{Style.RESET_ALL}")
                    
            elif param_choice == '2':
                new_value = int(self.safe_input(f"输入新的最大重启次数 (当前: {self.max_restarts}): "))
                if 1 <= new_value <= 100:
                    self.max_restarts = new_value
                    print(f"{Fore.GREEN}✅ 最大重启次数已设置为: {new_value}{Style.RESET_ALL}")
                else:
                    print(f"{Fore.RED}❌ 值必须在1-100之间{Style.RESET_ALL}")
                    
            elif param_choice == '3':
                new_value = int(self.safe_input(f"输入新的重启间隔(分钟) (当前: {self.restart_interval//60}): "))
                if 1 <= new_value <= 1440:  # 最多24小时
                    self.restart_interval = new_value * 60
                    print(f"{Fore.GREEN}✅ 重启间隔已设置为: {new_value}分钟{Style.RESET_ALL}")
                else:
                    print(f"{Fore.RED}❌ 值必须在1-1440分钟之间{Style.RESET_ALL}")
                    
            elif param_choice == '4':
                new_value = int(self.safe_input(f"输入新的内存清理间隔(分钟) (当前: {self.memory_cleanup_interval//60}): "))
                if 10 <= new_value <= 1440:  # 10分钟到24小时
                    self.memory_cleanup_interval = new_value * 60
                    print(f"{Fore.GREEN}✅ 内存清理间隔已设置为: {new_value}分钟{Style.RESET_ALL}")
                else:
                    print(f"{Fore.RED}❌ 值必须在10-1440分钟之间{Style.RESET_ALL}")
                    
            elif param_choice == '0':
                return
            else:
                print(f"{Fore.RED}❌ 无效选择{Style.RESET_ALL}")
                
        except ValueError:
            print(f"{Fore.RED}❌ 请输入有效的数字{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}❌ 参数调整失败: {e}{Style.RESET_ALL}")

    def menu_rpc_testing(self):
        """菜单：RPC节点检测"""
        print(f"\n{Fore.CYAN}✨ ====== 🔍 RPC节点检测管理 🔍 ====== ✨{Style.RESET_ALL}")
        print(f"{Back.BLUE}{Fore.WHITE} 📡 检测所有网络的RPC节点连接状态 {Style.RESET_ALL}")
        
        print(f"\n{Fore.YELLOW}🔧 检测选项：{Style.RESET_ALL}")
        print(f"  {Fore.GREEN}1.{Style.RESET_ALL} 🛠️ 自动屏蔽失效RPC")
        print(f"  {Fore.GREEN}2.{Style.RESET_ALL} 📊 查看RPC状态报告")
        print(f"  {Fore.GREEN}3.{Style.RESET_ALL} ⚠️ 检查并管理RPC数量不足的链条")
        print(f"  {Fore.GREEN}4.{Style.RESET_ALL} 🌐 从ChainList数据批量导入RPC")
        print(f"  {Fore.GREEN}5.{Style.RESET_ALL} 🚫 管理被拉黑的RPC")
        print(f"  {Fore.RED}0.{Style.RESET_ALL} 🔙 返回主菜单")
        
        choice = self.safe_input(f"\n{Fore.YELLOW}🔢 请选择操作 (0-5): {Style.RESET_ALL}").strip()
        
        try:
            if choice == '1':
                # 自动屏蔽失效RPC
                confirm = self.safe_input(f"\n{Fore.YELLOW}⚠️ 确认自动屏蔽失效RPC？(y/N): {Style.RESET_ALL}").strip().lower()
                if confirm == 'y':
                    # 先进行全网络RPC检测并更新缓存
                    print(f"\n{Fore.CYAN}🔄 正在检测所有网络的RPC状态...{Style.RESET_ALL}")
                    rpc_results = self.get_cached_rpc_results(force_refresh=True)
                    
                    disabled_count = self.auto_disable_failed_rpcs()
                    print(f"\n{Fore.GREEN}✅ 操作完成！已屏蔽 {disabled_count} 个失效RPC节点{Style.RESET_ALL}")
                    
                    # 显示检测统计
                    print(f"\n{Back.CYAN}{Fore.BLACK} 📊 检测统计 📊 {Style.RESET_ALL}")
                    total_networks = len(rpc_results)
                    total_rpcs = sum(r['total_count'] for r in rpc_results.values())
                    working_rpcs = sum(r['available_count'] for r in rpc_results.values())
                    
                    print(f"🌐 检测网络: {Fore.CYAN}{total_networks}{Style.RESET_ALL} 个")
                    print(f"📡 总RPC数: {Fore.CYAN}{total_rpcs}{Style.RESET_ALL} 个")
                    print(f"✅ 可用RPC: {Fore.GREEN}{working_rpcs}{Style.RESET_ALL} 个")
                    print(f"❌ 失效RPC: {Fore.RED}{total_rpcs - working_rpcs}{Style.RESET_ALL} 个")
                    print(f"📊 总体成功率: {Fore.YELLOW}{working_rpcs/total_rpcs*100:.1f}%{Style.RESET_ALL}")
                    
                    print(f"\n{Fore.GREEN}💡 检测结果已缓存，其他功能将复用此数据{Style.RESET_ALL}")
                else:
                    print(f"\n{Fore.YELLOW}⚠️ 操作已取消{Style.RESET_ALL}")
                    
            elif choice == '2':
                # 查看RPC状态报告
                print(f"\n{Fore.CYAN}📋 获取RPC状态报告...{Style.RESET_ALL}")
                results = self.get_cached_rpc_results()
                
                print(f"\n{Back.CYAN}{Fore.BLACK} 📋 详细RPC状态报告 📋 {Style.RESET_ALL}")
                
                # 按成功率排序
                sorted_results = sorted(results.items(), key=lambda x: x[1]['success_rate'], reverse=True)
                
                for network_key, result in sorted_results:
                    success_rate = result['success_rate']
                    working_count = result['available_count']
                    total_count = result['total_count']
                    
                    if success_rate == 100:
                        status_icon = "🟢"
                        status_color = Fore.GREEN
                    elif success_rate >= 50:
                        status_icon = "🟡"
                        status_color = Fore.YELLOW
                    else:
                        status_icon = "🔴"
                        status_color = Fore.RED
                    
                    print(f"\n{status_icon} {Fore.CYAN}{result['name']}{Style.RESET_ALL}")
                    print(f"   成功率: {status_color}{success_rate:.1f}%{Style.RESET_ALL} ({working_count}/{total_count})")
                    
                    if result['failed_rpcs']:
                        print(f"   {Fore.RED}失效RPC:{Style.RESET_ALL}")
                        for failed_rpc in result['failed_rpcs'][:3]:  # 只显示前3个
                            print(f"     • {failed_rpc[:60]}...")
                        if len(result['failed_rpcs']) > 3:
                            print(f"     • ... 还有 {len(result['failed_rpcs']) - 3} 个")
                            
            elif choice == '3':
                # 检查并管理RPC数量不足的链条
                self.manage_insufficient_rpc_chains()
                
            elif choice == '4':
                # 从ChainList数据批量导入RPC
                self.import_rpcs_from_chainlist()
                
            elif choice == '5':
                # 管理被拉黑的RPC
                self.manage_blocked_rpcs()
                
            elif choice == '0':
                return
            else:
                print(f"\n{Fore.RED}❌ 无效选择{Style.RESET_ALL}")
                
        except Exception as e:
            print(f"\n{Fore.RED}❌ 操作失败: {e}{Style.RESET_ALL}")
        
        self.safe_input(f"\n{Fore.MAGENTA}🔙 按回车键继续...{Style.RESET_ALL}")

    def menu_add_custom_token(self):
        """菜单：添加自定义代币"""
        print(f"\n{Fore.CYAN}✨ ====== 🪙 添加自定义代币 🪙 ====== ✨{Style.RESET_ALL}")
        print(f"{Back.GREEN}{Fore.BLACK} 🌐 检测并添加ERC20代币到监控列表 {Style.RESET_ALL}")
        
        # 步骤1: 选择网络
        print(f"\n{Fore.YELLOW}📋 步骤1: 选择网络{Style.RESET_ALL}")
        print(f"{Fore.CYAN}可用网络列表：{Style.RESET_ALL}")
        
        network_list = list(self.networks.items())
        for i, (network_key, network_info) in enumerate(network_list):
            print(f"  {Fore.GREEN}{i+1:2d}.{Style.RESET_ALL} {network_info['name']}")
        
        print(f"\n{Fore.YELLOW}💡 提示：输入网络编号或网络名称{Style.RESET_ALL}")
        network_input = self.safe_input(f"\n{Fore.CYAN}➜ 请选择网络: {Style.RESET_ALL}").strip()
        
        if not network_input:
            print(f"\n{Fore.YELLOW}⚠️ 操作已取消{Style.RESET_ALL}")
            self.safe_input(f"\n{Fore.MAGENTA}🔙 按回车键返回...{Style.RESET_ALL}")
            return
        
        # 解析网络选择
        selected_network = None
        try:
            # 尝试解析为数字
            network_index = int(network_input) - 1
            if 0 <= network_index < len(network_list):
                selected_network = network_list[network_index][0]
        except ValueError:
            # 按名称搜索
            for network_key, network_info in self.networks.items():
                if network_input.lower() in network_info['name'].lower() or network_input.lower() == network_key.lower():
                    selected_network = network_key
                    break
        
        if not selected_network:
            print(f"\n{Fore.RED}❌ 未找到匹配的网络: {network_input}{Style.RESET_ALL}")
            self.safe_input(f"\n{Fore.MAGENTA}🔙 按回车键返回...{Style.RESET_ALL}")
            return
        
        network_info = self.networks[selected_network]
        print(f"\n{Fore.GREEN}✅ 已选择网络: {network_info['name']}{Style.RESET_ALL}")
        
        # 步骤2: 输入代币地址
        print(f"\n{Fore.YELLOW}📋 步骤2: 输入代币合约地址{Style.RESET_ALL}")
        print(f"{Fore.GREEN}示例：{Style.RESET_ALL}")
        print(f"  • USDC: 0xA0b86a33E6417aFD5BF27c23E2a7B0b9bE6C1e67")
        print(f"  • USDT: 0xdAC17F958D2ee523a2206206994597C13D831ec7") 
        
        token_address = self.safe_input(f"\n{Fore.CYAN}➜ 代币合约地址: {Style.RESET_ALL}").strip()
        
        if not token_address:
            print(f"\n{Fore.YELLOW}⚠️ 操作已取消{Style.RESET_ALL}")
            self.safe_input(f"\n{Fore.MAGENTA}🔙 按回车键返回...{Style.RESET_ALL}")
            return
        
        # 步骤3: 检测代币信息
        print(f"\n{Fore.CYAN}🔄 正在检测代币信息...{Style.RESET_ALL}")
        token_info = self.get_token_info(token_address, selected_network)
        
        if not token_info:
            print(f"\n{Fore.RED}❌ 无法获取代币信息{Style.RESET_ALL}")
            print(f"   可能原因：")
            print(f"   • 地址格式错误")
            print(f"   • 不是有效的ERC20代币合约")
            print(f"   • 网络连接问题")
            self.safe_input(f"\n{Fore.MAGENTA}🔙 按回车键返回...{Style.RESET_ALL}")
            return
        
        # 步骤4: 显示代币信息并确认
        print(f"\n{Fore.GREEN}🎉 成功检测到代币信息！{Style.RESET_ALL}")
        print(f"\n{Back.BLUE}{Fore.WHITE} 📋 代币详细信息 📋 {Style.RESET_ALL}")
        print(f"  {Fore.YELLOW}代币名称:{Style.RESET_ALL} {token_info['name']}")
        print(f"  {Fore.YELLOW}代币符号:{Style.RESET_ALL} {token_info['symbol']}")
        print(f"  {Fore.YELLOW}小数位数:{Style.RESET_ALL} {token_info['decimals']}")
        print(f"  {Fore.YELLOW}合约地址:{Style.RESET_ALL} {token_info['address']}")
        print(f"  {Fore.YELLOW}所在网络:{Style.RESET_ALL} {network_info['name']}")
        
        # 确认添加
        print(f"\n{Fore.YELLOW}❓ 确认添加此代币到监控列表？{Style.RESET_ALL}")
        confirm = self.safe_input(f"{Fore.CYAN}➜ 输入 'y' 确认添加，其他键取消: {Style.RESET_ALL}").strip().lower()
        
        if confirm == 'y':
            # 添加代币
            if self.add_custom_token(token_info):
                print(f"\n{Fore.GREEN}🎉 代币添加成功！{Style.RESET_ALL}")
                print(f"   现在可以监控 {token_info['symbol']} 在 {network_info['name']} 上的余额了")
                
                # 显示当前支持的代币总数
                print(f"\n{Fore.CYAN}📊 当前支持的代币数量: {len(self.tokens)} 个{Style.RESET_ALL}")
            else:
                print(f"\n{Fore.RED}❌ 代币添加失败{Style.RESET_ALL}")
        else:
            print(f"\n{Fore.YELLOW}⚠️ 操作已取消{Style.RESET_ALL}")
        
        self.safe_input(f"\n{Fore.MAGENTA}🔙 按回车键返回主菜单...{Style.RESET_ALL}")
    
    def add_custom_rpc(self, network_key: str, rpc_url: str, quick_test: bool = False) -> bool:
        """添加自定义RPC到指定网络，支持HTTP(S)和WebSocket，自动去重"""
        try:
            if network_key not in self.networks:
                print(f"{Fore.RED}❌ 网络不存在: {network_key}{Style.RESET_ALL}")
                return False
            
            # 标准化URL格式
            rpc_url = rpc_url.strip()
            
            # 自动去重：检查URL是否已存在
            existing_urls = self.networks[network_key]['rpc_urls']
            if rpc_url in existing_urls:
                if not quick_test:  # 只在非快速测试时显示消息
                    print(f"{Fore.YELLOW}⚠️ RPC已存在，跳过添加: {rpc_url[:50]}...{Style.RESET_ALL}")
                return True
            
            # 验证URL格式，支持HTTP(S)和WebSocket
            if not rpc_url.startswith(('http://', 'https://', 'ws://', 'wss://')):
                if not quick_test:
                    print(f"{Fore.RED}❌ 无效的RPC URL格式，支持: http(s)://、ws(s)://{Style.RESET_ALL}")
                return False
            
            # 测试RPC连接
            network_info = self.networks[network_key]
            if not quick_test:
                print(f"{Fore.CYAN}🔄 正在测试RPC连接...{Style.RESET_ALL}")
            
            # 根据是否快速测试选择超时时间
            timeout = 1 if quick_test else 10
            
            if self.test_rpc_connection(rpc_url, network_info['chain_id'], timeout=timeout, quick_test=quick_test):
                # 添加到RPC列表的开头（优先使用）
                self.networks[network_key]['rpc_urls'].insert(0, rpc_url)
                print(f"{Fore.GREEN}✅ RPC已添加到网络 {network_info['name']}{Style.RESET_ALL}")
                
                # 尝试重新连接该网络
                try:
                    from web3 import Web3
                    # 根据URL类型选择提供者
                    if rpc_url.startswith(('ws://', 'wss://')):
                        provider = Web3.WebsocketProvider(rpc_url, websocket_kwargs={'timeout': 10})
                    else:
                        provider = Web3.HTTPProvider(rpc_url, request_kwargs={'timeout': 10})
                    
                    w3 = Web3(provider)
                    if w3.is_connected():
                        self.web3_connections[network_key] = w3
                        print(f"{Fore.GREEN}✅ 网络连接成功，已设为该网络的主要连接{Style.RESET_ALL}")
                except Exception as e:
                    print(f"{Fore.YELLOW}⚠️ RPC已添加但网络连接失败: {e}{Style.RESET_ALL}")
                
                # 保存配置
                self.logger.info(f"已添加自定义RPC: {network_key} -> {rpc_url}")
                
                # 更新RPC缓存
                if network_key in self.rpc_test_cache:
                    self.rpc_test_cache[network_key]['results'][rpc_url] = True
                    # 更新缓存时间
                    self.rpc_test_cache[network_key]['last_test'] = time.time()
                
                return True
            else:
                print(f"{Fore.RED}❌ RPC连接测试失败，请检查URL是否正确{Style.RESET_ALL}")
                return False
                
        except Exception as e:
            print(f"{Fore.RED}❌ 添加RPC失败: {e}{Style.RESET_ALL}")
            self.logger.error(f"添加自定义RPC失败: {network_key} -> {rpc_url}: {e}")
            return False
    
    def get_cached_rpc_results(self, network_key: str = None, force_refresh: bool = False) -> Dict:
        """获取缓存的RPC检测结果，避免重复检测"""
        current_time = time.time()
        
        if force_refresh:
            # 强制刷新，清除缓存
            if network_key:
                self.rpc_test_cache.pop(network_key, None)
            else:
                self.rpc_test_cache.clear()
        
        results = {}
        networks_to_test = [network_key] if network_key else self.networks.keys()
        
        for net_key in networks_to_test:
            if net_key not in self.networks:
                continue
                
            network_info = self.networks[net_key]
            
            # 检查缓存是否有效
            cache_entry = self.rpc_test_cache.get(net_key)
            cache_valid = (cache_entry and 
                          current_time - cache_entry['last_test'] < self.rpc_cache_ttl)
            
            if cache_valid and not force_refresh:
                # 使用缓存数据
                cached_results = cache_entry['results']
                working_rpcs = [url for url, status in cached_results.items() if status]
                failed_rpcs = [url for url, status in cached_results.items() if not status]
                print(f"{Fore.GREEN}📋 使用缓存数据: {network_info['name']} ({len(working_rpcs)}/{len(cached_results)} 可用){Style.RESET_ALL}")
            else:
                # 需要重新测试
                print(f"{Fore.CYAN}🔄 检测网络 {network_info['name']} 的RPC状态...{Style.RESET_ALL}")
                
                working_rpcs = []
                failed_rpcs = []
                test_results = {}
                
                for rpc_url in network_info['rpc_urls']:
                    if rpc_url in self.blocked_rpcs:
                        failed_rpcs.append(rpc_url)
                        test_results[rpc_url] = False
                    else:
                        is_working = self.test_rpc_connection(rpc_url, network_info['chain_id'], timeout=3)
                        if is_working:
                            working_rpcs.append(rpc_url)
                        else:
                            failed_rpcs.append(rpc_url)
                        test_results[rpc_url] = is_working
                
                # 更新缓存
                self.rpc_test_cache[net_key] = {
                    'last_test': current_time,
                    'results': test_results
                }
            
            # 计算统计信息
            total_count = len(working_rpcs) + len(failed_rpcs)
            success_rate = (len(working_rpcs) / total_count * 100) if total_count > 0 else 0
            
            results[net_key] = {
                'name': network_info['name'],
                'working_rpcs': working_rpcs,
                'failed_rpcs': failed_rpcs,
                'success_rate': success_rate,
                'available_count': len(working_rpcs),
                'total_count': total_count,
                'chain_id': network_info['chain_id'],
                'currency': network_info['native_currency']
            }
        
        return results
    
    def import_rpcs_from_chainlist(self):
        """从ChainList数据批量导入RPC"""
        print(f"\n{Back.GREEN}{Fore.BLACK} 🌐 ChainList RPC批量导入 🌐 {Style.RESET_ALL}")
        print(f"{Fore.CYAN}从ChainList数据自动识别并导入RPC节点{Style.RESET_ALL}")
        
        # 1. 文件选择
        print(f"\n{Fore.YELLOW}📁 步骤1: 选择数据文件{Style.RESET_ALL}")
        print(f"  {Fore.GREEN}1.{Style.RESET_ALL} 输入自定义文件路径")
        print(f"  {Fore.GREEN}2.{Style.RESET_ALL} 从当前目录选择文件")
        
        file_choice = self.safe_input(f"\n{Fore.CYAN}➜ 请选择方式 (1-2): {Style.RESET_ALL}").strip()
        
        file_path = None
        if file_choice == '1':
            # 自定义文件名（智能搜索）
            default_filename = "1.txt"
            filename = self.safe_input(f"\n{Fore.CYAN}➜ 请输入文件名 [默认: {default_filename}]: {Style.RESET_ALL}").strip()
            if not filename:
                filename = default_filename
            
            # 智能搜索文件
            file_path = self._smart_find_file(filename)
        elif file_choice == '2':
            # 列出当前目录文件
            file_path = self._select_file_from_directory()
        else:
            print(f"\n{Fore.RED}❌ 无效选择{Style.RESET_ALL}")
            return
        
        if not file_path:
            print(f"\n{Fore.YELLOW}⚠️ 未选择文件，操作取消{Style.RESET_ALL}")
            return
        
        # 2. 读取和解析文件
        chainlist_data = self._read_chainlist_file(file_path)
        if not chainlist_data:
            return
        
        # 3. 匹配和导入RPC
        self._process_chainlist_data(chainlist_data)
    
    def _smart_find_file(self, filename: str) -> str:
        """智能搜索文件，支持多个可能的路径"""
        import os
        import glob
        
        print(f"\n{Fore.CYAN}🔍 智能搜索文件: {filename}{Style.RESET_ALL}")
        
        # 搜索路径列表（按优先级排序）
        search_paths = [
            # 1. 当前工作目录
            os.getcwd(),
            # 2. 脚本所在目录
            os.path.dirname(os.path.abspath(__file__)),
            # 3. 用户主目录
            os.path.expanduser("~"),
            # 4. 桌面目录
            os.path.expanduser("~/Desktop"),
            # 5. 下载目录
            os.path.expanduser("~/Downloads"),
            # 6. 文档目录
            os.path.expanduser("~/Documents"),
            # 7. 根目录（服务器场景）
            "/",
            # 8. /tmp目录
            "/tmp",
            # 9. /home/用户名 目录
            f"/home/{os.getenv('USER', 'root')}",
        ]
        
        found_files = []
        
        # 在每个路径中搜索
        for search_path in search_paths:
            if not os.path.exists(search_path):
                continue
                
            try:
                # 精确匹配
                exact_path = os.path.join(search_path, filename)
                if os.path.isfile(exact_path):
                    file_size = os.path.getsize(exact_path) // 1024  # KB
                    found_files.append({
                        'path': exact_path,
                        'size': file_size,
                        'location': search_path,
                        'match_type': 'exact'
                    })
                    print(f"  ✅ 找到精确匹配: {exact_path} ({file_size} KB)")
                
                # 模糊匹配（无扩展名的情况）
                if '.' not in filename:
                    for ext in ['.txt', '.json', '.data', '.log']:
                        fuzzy_path = os.path.join(search_path, filename + ext)
                        if os.path.isfile(fuzzy_path):
                            file_size = os.path.getsize(fuzzy_path) // 1024
                            found_files.append({
                                'path': fuzzy_path,
                                'size': file_size,
                                'location': search_path,
                                'match_type': 'fuzzy'
                            })
                            print(f"  🔍 找到模糊匹配: {fuzzy_path} ({file_size} KB)")
                
                # 通配符搜索
                pattern = os.path.join(search_path, f"*{filename}*")
                for wild_path in glob.glob(pattern):
                    if os.path.isfile(wild_path) and wild_path not in [f['path'] for f in found_files]:
                        file_size = os.path.getsize(wild_path) // 1024
                        found_files.append({
                            'path': wild_path,
                            'size': file_size,
                            'location': search_path,
                            'match_type': 'wildcard'
                        })
                        print(f"  🌟 找到通配符匹配: {wild_path} ({file_size} KB)")
                        
            except (PermissionError, OSError):
                # 跳过无权限访问的目录
                continue
        
        if not found_files:
            print(f"\n{Fore.RED}❌ 在所有可能的位置都没有找到文件: {filename}{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}💡 搜索的位置包括：{Style.RESET_ALL}")
            for path in search_paths[:5]:  # 只显示前5个
                if os.path.exists(path):
                    print(f"   • {path}")
            return None
        
        # 如果只找到一个文件，直接返回
        if len(found_files) == 1:
            selected_file = found_files[0]
            print(f"\n{Fore.GREEN}✅ 自动选择文件: {selected_file['path']}{Style.RESET_ALL}")
            return selected_file['path']
        
        # 多个文件时让用户选择
        print(f"\n{Fore.YELLOW}📋 找到多个匹配的文件，请选择：{Style.RESET_ALL}")
        for i, file_info in enumerate(found_files, 1):
            match_icon = {
                'exact': '🎯',
                'fuzzy': '🔍', 
                'wildcard': '🌟'
            }.get(file_info['match_type'], '📄')
            
            print(f"  {Fore.GREEN}{i:2d}.{Style.RESET_ALL} {match_icon} {os.path.basename(file_info['path'])} "
                  f"({file_info['size']} KB) - {file_info['location']}")
        
        choice = self.safe_input(f"\n{Fore.CYAN}➜ 请选择文件编号 (1-{len(found_files)}): {Style.RESET_ALL}").strip()
        
        if choice.isdigit():
            index = int(choice) - 1
            if 0 <= index < len(found_files):
                selected_file = found_files[index]
                print(f"\n{Fore.GREEN}✅ 已选择: {selected_file['path']}{Style.RESET_ALL}")
                return selected_file['path']
        
        print(f"\n{Fore.RED}❌ 无效选择{Style.RESET_ALL}")
        return None
    
    def _select_file_from_directory(self) -> str:
        """从当前目录选择文件"""
        try:
            import os
            import glob
            
            # 查找文本文件
            text_files = []
            for pattern in ['*.txt', '*.json', '*.data']:
                text_files.extend(glob.glob(pattern))
            
            if not text_files:
                print(f"\n{Fore.YELLOW}⚠️ 当前目录没有找到文本文件{Style.RESET_ALL}")
                return None
            
            print(f"\n{Fore.YELLOW}📋 当前目录的文件：{Style.RESET_ALL}")
            for i, file in enumerate(text_files, 1):
                file_size = os.path.getsize(file) // 1024  # KB
                print(f"  {Fore.GREEN}{i:2d}.{Style.RESET_ALL} {file} ({file_size} KB)")
            
            choice = self.safe_input(f"\n{Fore.CYAN}➜ 请选择文件编号: {Style.RESET_ALL}").strip()
            if choice.isdigit():
                index = int(choice) - 1
                if 0 <= index < len(text_files):
                    return text_files[index]
            
            print(f"\n{Fore.RED}❌ 无效选择{Style.RESET_ALL}")
            return None
            
        except Exception as e:
            print(f"\n{Fore.RED}❌ 读取目录失败: {e}{Style.RESET_ALL}")
            return None
    
    def _read_chainlist_file(self, file_path: str) -> list:
        """读取ChainList文件"""
        try:
            print(f"\n{Fore.CYAN}📖 正在读取文件: {file_path}{Style.RESET_ALL}")
            
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
            
            if not content:
                print(f"\n{Fore.RED}❌ 文件为空{Style.RESET_ALL}")
                return None
            
            print(f"{Fore.GREEN}✅ 文件读取成功，大小: {len(content)//1024} KB{Style.RESET_ALL}")
            
            # 尝试解析JSON
            import json
            try:
                # 如果是完整的JSON数组
                if content.strip().startswith('['):
                    data = json.loads(content)
                else:
                    # 如果是单个对象的集合，尝试修复
                    if content.strip().startswith('{'):
                        # 添加数组括号并分割对象
                        content = content.strip()
                        if not content.endswith(']'):
                            # 简单修复：假设对象之间用 }, { 分隔
                            content = '[' + content.replace('}\n{', '},\n{').replace('}\n  {', '},\n  {') + ']'
                        data = json.loads(content)
                    else:
                        print(f"\n{Fore.RED}❌ 无法识别的文件格式{Style.RESET_ALL}")
                        return None
                
                print(f"{Fore.GREEN}✅ JSON解析成功，找到 {len(data)} 条链条记录{Style.RESET_ALL}")
                return data
                
            except json.JSONDecodeError as e:
                print(f"\n{Fore.RED}❌ JSON格式错误: {e}{Style.RESET_ALL}")
                print(f"{Fore.YELLOW}💡 提示：请确保文件是有效的JSON格式{Style.RESET_ALL}")
                return None
                
        except FileNotFoundError:
            print(f"\n{Fore.RED}❌ 文件不存在: {file_path}{Style.RESET_ALL}")
            return None
        except Exception as e:
            print(f"\n{Fore.RED}❌ 读取文件失败: {e}{Style.RESET_ALL}")
            return None
    
    def _process_chainlist_data(self, chainlist_data: list):
        """处理ChainList数据并导入RPC"""
        print(f"\n{Fore.CYAN}🔄 正在分析ChainList数据...{Style.RESET_ALL}")
        
        matched_networks = {}  # network_key -> [rpc_urls]
        unmatched_chains = []
        total_rpcs_found = 0
        
        # 创建chain_id到network_key的映射
        chain_id_map = {}
        for network_key, network_info in self.networks.items():
            chain_id_map[network_info['chain_id']] = network_key
        
        for chain_data in chainlist_data:
            try:
                chain_id = chain_data.get('chainId')
                chain_name = chain_data.get('name', '')
                rpc_list = chain_data.get('rpc', [])
                
                if not chain_id or not rpc_list:
                    continue
                
                # 提取RPC URLs
                rpc_urls = []
                for rpc_entry in rpc_list:
                    if isinstance(rpc_entry, dict):
                        url = rpc_entry.get('url', '')
                    elif isinstance(rpc_entry, str):
                        url = rpc_entry
                    else:
                        continue
                    
                    # 验证RPC URL
                    if url and self._is_valid_rpc_url(url):
                        rpc_urls.append(url)
                
                total_rpcs_found += len(rpc_urls)
                
                # 尝试匹配到现有网络
                if chain_id in chain_id_map:
                    network_key = chain_id_map[chain_id]
                    if network_key not in matched_networks:
                        matched_networks[network_key] = []
                    matched_networks[network_key].extend(rpc_urls)
                else:
                    unmatched_chains.append({
                        'chainId': chain_id,
                        'name': chain_name,
                        'rpc_count': len(rpc_urls)
                    })
                    
            except Exception as e:
                self.logger.warning(f"解析链条数据失败: {e}")
                continue
        
        print(f"\n{Back.CYAN}{Fore.BLACK} 📊 分析结果 📊 {Style.RESET_ALL}")
        print(f"📡 总计发现RPC: {Fore.CYAN}{total_rpcs_found}{Style.RESET_ALL} 个")
        print(f"✅ 匹配的网络: {Fore.GREEN}{len(matched_networks)}{Style.RESET_ALL} 个")
        print(f"❓ 未匹配的链条: {Fore.YELLOW}{len(unmatched_chains)}{Style.RESET_ALL} 个")
        
        if not matched_networks:
            print(f"\n{Fore.YELLOW}⚠️ 没有找到匹配的网络，操作结束{Style.RESET_ALL}")
            return
        
        # 显示匹配的网络详情
        print(f"\n{Fore.YELLOW}🎯 匹配的网络详情：{Style.RESET_ALL}")
        for network_key, rpc_urls in matched_networks.items():
            network_name = self.networks[network_key]['name']
            print(f"  • {Fore.CYAN}{network_name}{Style.RESET_ALL}: 发现 {Fore.GREEN}{len(rpc_urls)}{Style.RESET_ALL} 个RPC")
        
        # 显示部分未匹配的链条
        if unmatched_chains:
            print(f"\n{Fore.YELLOW}❓ 部分未匹配的链条（前10个）：{Style.RESET_ALL}")
            for chain in unmatched_chains[:10]:
                print(f"  • ID {chain['chainId']}: {chain['name']} ({chain['rpc_count']} RPC)")
            if len(unmatched_chains) > 10:
                print(f"  • ... 还有 {len(unmatched_chains) - 10} 个")
        
        # 确认导入
        print(f"\n{Fore.YELLOW}🚀 准备导入操作：{Style.RESET_ALL}")
        total_import_rpcs = sum(len(rpcs) for rpcs in matched_networks.values())
        print(f"  📊 将为 {len(matched_networks)} 个网络导入 {total_import_rpcs} 个RPC")
        print(f"  🔍 每个RPC都会进行快速连接测试（1秒超时）")
        print(f"  ⚡ 超过1秒无响应的RPC将被自动拉黑")
        print(f"  ❌ 连接失败的RPC会自动屏蔽")
        
        confirm = self.safe_input(f"\n{Fore.YELLOW}➜ 确认开始导入？(y/N): {Style.RESET_ALL}").strip().lower()
        if confirm != 'y':
            print(f"\n{Fore.YELLOW}⚠️ 导入操作已取消{Style.RESET_ALL}")
            return
        
        # 开始批量导入
        self._batch_import_rpcs(matched_networks)
    
    def _batch_import_rpcs(self, matched_networks: dict):
        """批量导入RPC"""
        print(f"\n{Back.GREEN}{Fore.BLACK} 🚀 开始批量导入RPC 🚀 {Style.RESET_ALL}")
        
        total_success = 0
        total_failed = 0
        total_skipped = 0
        import_summary = {}
        
        for network_key, rpc_urls in matched_networks.items():
            network_name = self.networks[network_key]['name']
            print(f"\n{Fore.CYAN}🔄 处理网络: {network_name}{Style.RESET_ALL}")
            
            success_count = 0
            failed_count = 0
            skipped_count = 0
            
            for i, rpc_url in enumerate(rpc_urls, 1):
                print(f"  {i}/{len(rpc_urls)} 测试: {rpc_url[:60]}...", end=" ", flush=True)
                
                # 检查是否已存在
                if rpc_url in self.networks[network_key]['rpc_urls']:
                    print(f"{Fore.YELLOW}跳过(已存在){Style.RESET_ALL}")
                    skipped_count += 1
                    continue
                
                # 检查是否已被拉黑
                if rpc_url in self.blocked_rpcs:
                    print(f"{Fore.RED}跳过(已拉黑){Style.RESET_ALL}")
                    skipped_count += 1
                    continue
                
                # 使用快速测试模式（1秒超时）
                import time
                start_time = time.time()
                
                if self.add_custom_rpc(network_key, rpc_url, quick_test=True):
                    elapsed = time.time() - start_time
                    print(f"{Fore.GREEN}成功({elapsed:.2f}s){Style.RESET_ALL}")
                    success_count += 1
                else:
                    elapsed = time.time() - start_time
                    print(f"{Fore.RED}失败({elapsed:.2f}s){Style.RESET_ALL}")
                    
                    # 自动拉黑失败的RPC（包括超时的）
                    reason = "超过1秒超时" if elapsed >= 1.0 else "连接失败"
                    self.blocked_rpcs[rpc_url] = {
                        'reason': f'ChainList批量导入时{reason}',
                        'blocked_time': time.time(),
                        'network': network_key,
                        'test_duration': elapsed
                    }
                    failed_count += 1
            
            import_summary[network_key] = {
                'name': network_name,
                'success': success_count,
                'failed': failed_count,
                'skipped': skipped_count
            }
            
            total_success += success_count
            total_failed += failed_count
            total_skipped += skipped_count
            
            print(f"  📊 {network_name}: ✅{success_count} ❌{failed_count} ⏭️{skipped_count}")
        
        # 显示导入总结
        print(f"\n{Back.GREEN}{Fore.BLACK} 📋 导入完成总结 📋 {Style.RESET_ALL}")
        print(f"✅ 成功导入: {Fore.GREEN}{total_success}{Style.RESET_ALL} 个RPC")
        print(f"❌ 失败拉黑: {Fore.RED}{total_failed}{Style.RESET_ALL} 个RPC（包括超时）")
        print(f"⏭️ 跳过重复: {Fore.YELLOW}{total_skipped}{Style.RESET_ALL} 个RPC")
        
        # 显示被拉黑的RPC统计
        if total_failed > 0:
            timeout_count = sum(1 for rpc_url, info in self.blocked_rpcs.items() 
                              if '超过1秒超时' in info.get('reason', ''))
            if timeout_count > 0:
                print(f"⚡ 其中超时拉黑: {Fore.YELLOW}{timeout_count}{Style.RESET_ALL} 个RPC")
        print(f"📊 总处理量: {Fore.CYAN}{total_success + total_failed + total_skipped}{Style.RESET_ALL} 个RPC")
        
        # 显示详细结果
        if import_summary:
            print(f"\n{Fore.YELLOW}📋 各网络导入详情：{Style.RESET_ALL}")
            for network_key, summary in import_summary.items():
                if summary['success'] > 0:
                    print(f"  🟢 {summary['name']}: +{summary['success']} 个新RPC")
        
        # 更新缓存
        if total_success > 0:
            print(f"\n{Fore.GREEN}🔄 正在更新RPC状态缓存...{Style.RESET_ALL}")
            # 清除相关网络的缓存，强制重新检测
            for network_key in matched_networks.keys():
                self.rpc_test_cache.pop(network_key, None)
            print(f"{Fore.GREEN}✅ 缓存已清除，下次检测将使用新的RPC{Style.RESET_ALL}")
        
        # 保存状态
        self.save_state()
        print(f"\n{Fore.GREEN}🎉 ChainList RPC导入操作完成！{Style.RESET_ALL}")
    
    def manage_blocked_rpcs(self):
        """管理被拉黑的RPC"""
        print(f"\n{Back.RED}{Fore.WHITE} 🚫 被拉黑的RPC管理 🚫 {Style.RESET_ALL}")
        
        if not self.blocked_rpcs:
            print(f"\n{Fore.GREEN}✅ 目前没有被拉黑的RPC{Style.RESET_ALL}")
            return
        
        print(f"\n{Fore.CYAN}📊 被拉黑的RPC统计：{Style.RESET_ALL}")
        print(f"总数量: {Fore.YELLOW}{len(self.blocked_rpcs)}{Style.RESET_ALL} 个")
        
        # 按拉黑原因分类统计
        reason_stats = {}
        timeout_count = 0
        for rpc_url, info in self.blocked_rpcs.items():
            reason = info.get('reason', '未知原因')
            reason_stats[reason] = reason_stats.get(reason, 0) + 1
            if '超过1秒超时' in reason:
                timeout_count += 1
        
        print(f"\n{Fore.YELLOW}📋 拉黑原因分布：{Style.RESET_ALL}")
        for reason, count in reason_stats.items():
            print(f"  • {reason}: {Fore.CYAN}{count}{Style.RESET_ALL} 个")
        
        if timeout_count > 0:
            print(f"\n{Fore.YELLOW}⚡ 超时拉黑RPC: {timeout_count} 个{Style.RESET_ALL}")
        
        # 显示最近拉黑的RPC
        print(f"\n{Fore.YELLOW}🕒 最近拉黑的RPC（前10个）：{Style.RESET_ALL}")
        import time
        sorted_rpcs = sorted(self.blocked_rpcs.items(), 
                           key=lambda x: x[1].get('blocked_time', 0), reverse=True)
        
        for i, (rpc_url, info) in enumerate(sorted_rpcs[:10], 1):
            blocked_time = info.get('blocked_time', 0)
            reason = info.get('reason', '未知原因')
            network = info.get('network', '未知网络')
            test_duration = info.get('test_duration', 0)
            
            time_str = time.strftime('%H:%M:%S', time.localtime(blocked_time))
            duration_str = f"({test_duration:.2f}s)" if test_duration > 0 else ""
            
            print(f"  {i:2d}. {rpc_url[:50]}...")
            print(f"      网络: {Fore.CYAN}{network}{Style.RESET_ALL} | "
                  f"时间: {Fore.YELLOW}{time_str}{Style.RESET_ALL} | "
                  f"原因: {Fore.RED}{reason}{Style.RESET_ALL} {duration_str}")
        
        if len(sorted_rpcs) > 10:
            print(f"      ... 还有 {len(sorted_rpcs) - 10} 个")
        
        # 管理选项
        print(f"\n{Fore.YELLOW}🔧 管理选项：{Style.RESET_ALL}")
        print(f"  {Fore.GREEN}1.{Style.RESET_ALL} 🔄 重新测试所有被拉黑的RPC")
        print(f"  {Fore.GREEN}2.{Style.RESET_ALL} 🗑️  清空所有被拉黑的RPC")
        print(f"  {Fore.GREEN}3.{Style.RESET_ALL} ⚡ 只清空超时拉黑的RPC")
        print(f"  {Fore.GREEN}4.{Style.RESET_ALL} 📋 导出被拉黑的RPC列表")
        print(f"  {Fore.RED}0.{Style.RESET_ALL} 🔙 返回")
        
        choice = self.safe_input(f"\n{Fore.YELLOW}请选择操作 (0-4): {Style.RESET_ALL}").strip()
        
        if choice == '1':
            self._retest_blocked_rpcs()
        elif choice == '2':
            self._clear_all_blocked_rpcs()
        elif choice == '3':
            self._clear_timeout_blocked_rpcs()
        elif choice == '4':
            self._export_blocked_rpcs()
        elif choice == '0':
            return
        else:
            print(f"\n{Fore.RED}❌ 无效选择{Style.RESET_ALL}")
    
    def _retest_blocked_rpcs(self):
        """重新测试被拉黑的RPC"""
        print(f"\n{Fore.CYAN}🔄 重新测试被拉黑的RPC...{Style.RESET_ALL}")
        
        if not self.blocked_rpcs:
            print(f"{Fore.YELLOW}⚠️ 没有被拉黑的RPC需要测试{Style.RESET_ALL}")
            return
        
        unblocked_count = 0
        total_count = len(self.blocked_rpcs)
        rpcs_to_remove = []
        
        # 创建网络名称映射
        network_names = {key: info['name'] for key, info in self.networks.items()}
        
        print(f"📊 开始测试 {total_count} 个被拉黑的RPC...")
        
        for i, (rpc_url, info) in enumerate(self.blocked_rpcs.items(), 1):
            network_key = info.get('network', '')
            print(f"  {i}/{total_count} 测试: {rpc_url[:50]}...", end=" ", flush=True)
            
            if network_key in self.networks:
                network_info = self.networks[network_key]
                # 使用正常超时（不是快速测试）
                if self.test_rpc_connection(rpc_url, network_info['chain_id'], timeout=5):
                    print(f"{Fore.GREEN}恢复{Style.RESET_ALL}")
                    rpcs_to_remove.append(rpc_url)
                    unblocked_count += 1
                else:
                    print(f"{Fore.RED}仍失败{Style.RESET_ALL}")
            else:
                print(f"{Fore.YELLOW}网络不存在{Style.RESET_ALL}")
                rpcs_to_remove.append(rpc_url)
        
        # 移除恢复的RPC
        for rpc_url in rpcs_to_remove:
            del self.blocked_rpcs[rpc_url]
        
        print(f"\n{Fore.GREEN}✅ 重测完成！{Style.RESET_ALL}")
        print(f"恢复RPC: {Fore.GREEN}{unblocked_count}{Style.RESET_ALL} 个")
        print(f"仍被拉黑: {Fore.RED}{total_count - unblocked_count}{Style.RESET_ALL} 个")
    
    def _clear_all_blocked_rpcs(self):
        """清空所有被拉黑的RPC"""
        count = len(self.blocked_rpcs)
        confirm = self.safe_input(f"\n{Fore.YELLOW}⚠️ 确认清空所有 {count} 个被拉黑的RPC？(y/N): {Style.RESET_ALL}").strip().lower()
        
        if confirm == 'y':
            self.blocked_rpcs.clear()
            print(f"\n{Fore.GREEN}✅ 已清空所有被拉黑的RPC{Style.RESET_ALL}")
        else:
            print(f"\n{Fore.YELLOW}⚠️ 操作已取消{Style.RESET_ALL}")
    
    def _clear_timeout_blocked_rpcs(self):
        """只清空超时拉黑的RPC"""
        timeout_rpcs = [url for url, info in self.blocked_rpcs.items() 
                       if '超过1秒超时' in info.get('reason', '')]
        
        if not timeout_rpcs:
            print(f"\n{Fore.YELLOW}⚠️ 没有超时拉黑的RPC{Style.RESET_ALL}")
            return
        
        confirm = self.safe_input(f"\n{Fore.YELLOW}⚠️ 确认清空 {len(timeout_rpcs)} 个超时拉黑的RPC？(y/N): {Style.RESET_ALL}").strip().lower()
        
        if confirm == 'y':
            for url in timeout_rpcs:
                del self.blocked_rpcs[url]
            print(f"\n{Fore.GREEN}✅ 已清空 {len(timeout_rpcs)} 个超时拉黑的RPC{Style.RESET_ALL}")
        else:
            print(f"\n{Fore.YELLOW}⚠️ 操作已取消{Style.RESET_ALL}")
    
    def _export_blocked_rpcs(self):
        """导出被拉黑的RPC列表"""
        if not self.blocked_rpcs:
            print(f"\n{Fore.YELLOW}⚠️ 没有被拉黑的RPC可导出{Style.RESET_ALL}")
            return
        
        import json
        import os
        
        filename = f"blocked_rpcs_{int(time.time())}.json"
        filepath = os.path.join(os.getcwd(), filename)
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(self.blocked_rpcs, f, indent=2, ensure_ascii=False)
            
            print(f"\n{Fore.GREEN}✅ 被拉黑的RPC列表已导出到: {filepath}{Style.RESET_ALL}")
            print(f"📊 包含 {len(self.blocked_rpcs)} 个RPC记录")
        except Exception as e:
            print(f"\n{Fore.RED}❌ 导出失败: {e}{Style.RESET_ALL}")

    def manage_insufficient_rpc_chains(self):
        """检查并管理RPC数量不足的链条，支持直接添加RPC"""
        print(f"\n{Back.YELLOW}{Fore.BLACK} ⚠️ RPC数量管理 - 检查并添加RPC ⚠️ {Style.RESET_ALL}")
        print(f"{Fore.CYAN}🔄 获取网络RPC配置分析...{Style.RESET_ALL}")
        
        # 使用缓存的检测结果
        rpc_results = self.get_cached_rpc_results()
        
        insufficient_chains = []
        warning_chains = []  # 3-5个RPC的链条
        
        for network_key, result in rpc_results.items():
            available_count = result['available_count']
            
            if available_count < 3:
                insufficient_chains.append({
                    'network_key': network_key,
                    'name': result['name'],
                    'chain_id': result['chain_id'],
                    'total_rpcs': result['total_count'],
                    'available_rpcs': available_count,
                    'failed_rpcs': len(result['failed_rpcs']),
                    'currency': result['currency']
                })
            elif available_count <= 5:
                warning_chains.append({
                    'network_key': network_key,
                    'name': result['name'],
                    'available_rpcs': available_count,
                    'currency': result['currency']
                })
        
        # 显示结果
        print(f"\n{Back.RED}{Fore.WHITE} 🚨 RPC数量不足的链条（少于3个可用） 🚨 {Style.RESET_ALL}")
        
        if insufficient_chains:
            print(f"\n{Fore.RED}发现 {len(insufficient_chains)} 个链条RPC数量不足：{Style.RESET_ALL}")
            print(f"{Fore.CYAN}─" * 80 + f"{Style.RESET_ALL}")
            
            for i, chain in enumerate(insufficient_chains, 1):
                status_color = Fore.RED if chain['available_rpcs'] == 0 else Fore.YELLOW
                print(f"  {Fore.GREEN}{i:2d}.{Style.RESET_ALL} {status_color}⚠️ {chain['name']:<30}{Style.RESET_ALL} ({chain['currency']:<6}) "
                      f"- 可用: {Fore.GREEN}{chain['available_rpcs']}{Style.RESET_ALL}/"
                      f"{chain['total_rpcs']} 个RPC")
                print(f"      Chain ID: {Fore.CYAN}{chain['chain_id']}{Style.RESET_ALL}, Network Key: {Fore.MAGENTA}{chain['network_key']}{Style.RESET_ALL}")
            
            # 提供添加RPC的选项
            print(f"\n{Fore.YELLOW}🛠️ 管理选项：{Style.RESET_ALL}")
            print(f"  • 输入编号 (1-{len(insufficient_chains)}) 为对应链条添加RPC")
            print(f"  • 输入 'all' 为所有不足的链条批量添加RPC") 
            print(f"  • 直接按回车跳过")
            
            action = self.safe_input(f"\n{Fore.CYAN}➜ 请选择操作: {Style.RESET_ALL}").strip()
            
            if action.lower() == 'all':
                # 批量为所有不足的链条添加RPC
                for chain in insufficient_chains:
                    print(f"\n{Fore.CYAN}🔧 正在为 {chain['name']} 添加RPC...{Style.RESET_ALL}")
                    self._add_rpc_for_chain(chain['network_key'], chain['name'])
            elif action.isdigit():
                # 为指定链条添加RPC
                index = int(action) - 1
                if 0 <= index < len(insufficient_chains):
                    chain = insufficient_chains[index]
                    print(f"\n{Fore.CYAN}🔧 正在为 {chain['name']} 添加RPC...{Style.RESET_ALL}")
                    self._add_rpc_for_chain(chain['network_key'], chain['name'])
                else:
                    print(f"\n{Fore.RED}❌ 无效的编号{Style.RESET_ALL}")
        else:
            print(f"\n{Fore.GREEN}✅ 所有链条的RPC数量都充足（≥3个可用）{Style.RESET_ALL}")
        
        # 显示警告链条
        if warning_chains:
            print(f"\n{Back.YELLOW}{Fore.BLACK} ⚠️ RPC数量偏少的链条（3-5个可用） ⚠️ {Style.RESET_ALL}")
            for chain in warning_chains:
                print(f"  {Fore.YELLOW}⚠️{Style.RESET_ALL} {chain['name']} - "
                      f"可用: {Fore.YELLOW}{chain['available_rpcs']}{Style.RESET_ALL} 个RPC")
        
        # 显示总结和建议
        print(f"\n{Fore.CYAN}─" * 80 + f"{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}💡 支持的RPC格式：{Style.RESET_ALL}")
        print(f"  • HTTP(S): https://rpc.example.com")
        print(f"  • WebSocket: wss://ws.example.com")
        print(f"  • 自动去重：重复的RPC会被跳过")
        
        if insufficient_chains:
            print(f"\n{Fore.RED}需要补充RPC的链条总数: {len(insufficient_chains)}{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}建议每个链条至少保持3-5个可用RPC节点{Style.RESET_ALL}")
    
    def _add_rpc_for_chain(self, network_key: str, network_name: str):
        """为指定链条添加RPC，支持批量智能识别"""
        print(f"\n{Fore.GREEN}🌐 为网络 {network_name} 添加RPC节点{Style.RESET_ALL}")
        print(f"   Network Key: {Fore.MAGENTA}{network_key}{Style.RESET_ALL}")
        print(f"   当前RPC数量: {Fore.CYAN}{len(self.networks[network_key]['rpc_urls'])}{Style.RESET_ALL}")
        
        print(f"\n{Fore.YELLOW}📝 支持的输入方式：{Style.RESET_ALL}")
        print(f"  • 单条RPC: https://rpc.example.com")
        print(f"  • 批量粘贴: 支持从表格、列表等复制的内容")
        print(f"  • 智能识别: 自动提取有效的RPC地址")
        print(f"  • 格式支持: HTTP(S)、WebSocket (ws/wss)")
        print(f"\n{Fore.CYAN}💡 提示：支持粘贴包含表格、文本的混合内容，程序会自动识别RPC{Style.RESET_ALL}")
        print(f"{Fore.GREEN}✨ 输入完成后双击回车开始批量处理{Style.RESET_ALL}")
        
        print(f"\n{Fore.YELLOW}🔍 请输入RPC内容（支持多行粘贴）：{Style.RESET_ALL}")
        
        # 收集多行输入
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
        
        if not lines:
            print(f"{Fore.YELLOW}⚠️ 未输入任何内容，跳过为 {network_name} 添加RPC{Style.RESET_ALL}")
            return
        
        # 智能提取RPC地址
        extracted_rpcs = self._extract_rpcs_from_text(lines)
        
        if not extracted_rpcs:
            print(f"{Fore.RED}❌ 未识别到有效的RPC地址{Style.RESET_ALL}")
            return
        
        # 显示识别结果
        print(f"\n{Fore.CYAN}🔍 智能识别结果：{Style.RESET_ALL}")
        print(f"识别到 {Fore.GREEN}{len(extracted_rpcs)}{Style.RESET_ALL} 个RPC地址：")
        
        for i, rpc in enumerate(extracted_rpcs, 1):
            rpc_type = "WebSocket" if rpc.startswith(('ws://', 'wss://')) else "HTTP(S)"
            print(f"  {Fore.GREEN}{i:2d}.{Style.RESET_ALL} {Fore.CYAN}[{rpc_type}]{Style.RESET_ALL} {rpc}")
        
        # 确认添加
        confirm = self.safe_input(f"\n{Fore.YELLOW}确认批量添加这些RPC？(Y/n): {Style.RESET_ALL}").strip().lower()
        if confirm and confirm != 'y':
            print(f"{Fore.YELLOW}⚠️ 操作已取消{Style.RESET_ALL}")
            return
        
        # 批量添加和测试
        print(f"\n{Fore.CYAN}🚀 开始批量添加和测试RPC...{Style.RESET_ALL}")
        
        success_count = 0
        failed_count = 0
        skipped_count = 0
        
        for i, rpc_url in enumerate(extracted_rpcs, 1):
            print(f"\n{Fore.CYAN}[{i}/{len(extracted_rpcs)}]{Style.RESET_ALL} 处理: {rpc_url[:60]}...")
            
            # 检查是否已存在（去重）
            if rpc_url in self.networks[network_key]['rpc_urls']:
                print(f"  {Fore.YELLOW}⚠️ 已存在，跳过{Style.RESET_ALL}")
                skipped_count += 1
                continue
            
            # 添加RPC
            if self.add_custom_rpc(network_key, rpc_url):
                print(f"  {Fore.GREEN}✅ 添加成功{Style.RESET_ALL}")
                success_count += 1
            else:
                print(f"  {Fore.RED}❌ 添加失败，已自动屏蔽{Style.RESET_ALL}")
                # 自动屏蔽失效的RPC
                self.blocked_rpcs[rpc_url] = {
                    'reason': '批量添加时连接失败',
                    'blocked_time': time.time(),
                    'network': network_key
                }
                failed_count += 1
        
        # 显示批量处理结果
        print(f"\n{Back.GREEN}{Fore.BLACK} 📊 批量处理完成 📊 {Style.RESET_ALL}")
        print(f"  {Fore.GREEN}✅ 成功添加: {success_count} 个{Style.RESET_ALL}")
        print(f"  {Fore.YELLOW}⚠️ 跳过重复: {skipped_count} 个{Style.RESET_ALL}")
        print(f"  {Fore.RED}❌ 失败屏蔽: {failed_count} 个{Style.RESET_ALL}")
        print(f"  {Fore.CYAN}📊 网络 {network_name} 当前RPC总数: {len(self.networks[network_key]['rpc_urls'])} 个{Style.RESET_ALL}")
        
        if success_count > 0:
            print(f"\n{Fore.GREEN}🎉 成功为网络 {network_name} 添加了 {success_count} 个新的RPC节点！{Style.RESET_ALL}")
    
    def _extract_rpcs_from_text(self, lines: List[str]) -> List[str]:
        """从文本中智能提取RPC地址"""
        import re
        
        rpcs = []
        
        # RPC地址的正则表达式模式
        rpc_patterns = [
            r'(https?://[^\s\t]+)',  # HTTP(S) URLs
            r'(wss?://[^\s\t]+)',    # WebSocket URLs
        ]
        
        for line in lines:
            # 跳过明显的无关行
            if any(skip_word in line.lower() for skip_word in [
                '连接钱包', 'rpc 服务器', '高度', '延迟', '分数', '隐私',
                'height', 'latency', 'score', 'privacy', 'connect wallet'
            ]):
                continue
            
            # 提取所有可能的RPC地址
            for pattern in rpc_patterns:
                matches = re.findall(pattern, line, re.IGNORECASE)
                for match in matches:
                    # 清理URL（移除尾部的标点符号等）
                    cleaned_url = re.sub(r'[,;\s\t]+$', '', match.strip())
                    
                    # 验证URL格式
                    if self._is_valid_rpc_url(cleaned_url):
                        if cleaned_url not in rpcs:  # 去重
                            rpcs.append(cleaned_url)
        
        return rpcs
    
    def _is_valid_rpc_url(self, url: str) -> bool:
        """验证RPC URL是否有效"""
        import re
        
        # 基本格式检查
        if not url or len(url) < 10:
            return False
        
        # 必须以支持的协议开头
        if not url.startswith(('http://', 'https://', 'ws://', 'wss://')):
            return False
        
        # 不能包含空格或其他无效字符
        if re.search(r'[\s\t]', url):
            return False
        
        # 必须包含域名
        domain_pattern = r'://([a-zA-Z0-9.-]+)'
        match = re.search(domain_pattern, url)
        if not match:
            return False
        
        domain = match.group(1)
        
        # 域名不能为空或只包含点
        if not domain or domain.count('.') == len(domain):
            return False
        
        # 排除明显的无效域名
        invalid_domains = ['localhost', '127.0.0.1', '0.0.0.0']
        if domain in invalid_domains:
            return False
        
        return True

def run_daemon_mode(monitor, password):
    """运行守护进程模式"""
    try:
        print(f"{Fore.CYAN}🛡️ 启动守护进程模式{Style.RESET_ALL}")
        
        # 加载钱包和状态
        if not monitor.load_wallets():
            monitor.logger.error("加载钱包失败")
            return False
        
        monitor.load_state()
        monitor.logger.info(f"守护进程启动，已连接网络: {', '.join(monitor.web3_connections.keys())}")
        
        # 启动守护进程模式（包含自动重启和内存清理）
        return monitor.start_daemon_mode()
            
    except Exception as e:
        monitor.logger.error(f"守护进程错误: {e}")
        monitor.handle_error(e, "守护进程启动")
        return False

def main():
    """主函数"""
    try:
        # 注册全局信号处理，确保 Ctrl+C/TERM 立即退出
        signal.signal(signal.SIGINT, _global_signal_handler)
        signal.signal(signal.SIGTERM, _global_signal_handler)
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
        global MONITOR_INSTANCE
        MONITOR_INSTANCE = monitor
        
        # 守护进程模式
        if args.daemon:
            return run_daemon_mode(monitor, args.password)
        
        # 强制交互模式
        if args.force_interactive:
            print(f"{Fore.CYAN}🚀 强制交互式菜单模式 (--force-interactive){Style.RESET_ALL}")
            # 设置全局标志，强制所有输入函数使用交互模式
            monitor._force_interactive = True
        elif args.auto_start:
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
        else:
            # 交互模式（默认模式）
            print(f"{Fore.CYAN}🚀 进入交互式菜单模式{Style.RESET_ALL}")
        
        # 加载钱包
        monitor.load_wallets()
        
        # 加载监控状态
        monitor.load_state()
        
        # 显示欢迎信息
        print(f"\n{Fore.GREEN}🎉 欢迎使用EVM监控软件！{Style.RESET_ALL}")
        print(f"{Fore.CYAN}💡 使用菜单选项 8 (网络连接管理) 来连接区块链网络{Style.RESET_ALL}")
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
