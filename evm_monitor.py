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
                self.blocked_networks = state.get('blocked_networks', {})
                
                # 加载转账统计，保持兼容性
                saved_stats = state.get('transfer_stats', {})
                if saved_stats:
                    self.transfer_stats.update(saved_stats)
                
                # 加载RPC延迟历史和屏蔽数据
                self.rpc_latency_history = state.get('rpc_latency_history', {})
                self.blocked_rpcs = state.get('blocked_rpcs', {})
                
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
            contract = w3.eth.contract(
                address=w3.to_checksum_address(contract_address),
                abi=self.erc20_abi
            )
            
            # 获取代币余额
            balance_raw = contract.functions.balanceOf(w3.to_checksum_address(address)).call()
            
            # 获取代币精度
            try:
                decimals = contract.functions.decimals().call()
            except:
                decimals = 18  # 默认精度
            
            # 转换为人类可读格式
            balance = balance_raw / (10 ** decimals)
            
            return float(balance), token_config['symbol'], contract_address
            
        except Exception as e:
            self.logger.error(f"获取代币余额失败 {token_symbol} {address} on {network}: {e}")
            return 0.0, "?", "?"

    def get_all_balances(self, address: str, network: str) -> Dict:
        """获取地址在指定网络上的所有余额（原生代币 + ERC20代币）"""
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
        
        # 获取ERC20代币余额
        for token_symbol in self.tokens:
            token_balance, token_sym, contract_addr = self.get_token_balance(address, token_symbol, network)
            if token_balance > 0:
                balances[token_symbol] = {
                    'balance': token_balance,
                    'symbol': token_sym,
                    'type': 'erc20',
                    'contract': contract_addr
                }
        
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
            except:
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
            url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
            data = {
                'chat_id': self.telegram_chat_id,
                'text': message,
                'parse_mode': 'Markdown'
            }
            
            response = requests.post(url, data=data, timeout=10)
            if response.status_code == 200:
                self.logger.info("Telegram通知发送成功")
                return True
            else:
                self.logger.error(f"Telegram通知发送失败: {response.status_code}")
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

    def test_rpc_connection(self, rpc_url: str, expected_chain_id: int, timeout: int = 5) -> bool:
        """测试单个RPC连接"""
        try:
            from web3 import Web3
            w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={'timeout': timeout}))
            
            # 测试连接
            if not w3.is_connected():
                return False
            
            # 验证链ID
            chain_id = w3.eth.chain_id
            return chain_id == expected_chain_id
            
        except Exception:
            return False

    def test_rpc_concurrent(self, rpc_url: str, expected_chain_id: int, timeout: int = 3) -> tuple:
        """并发测试单个RPC连接，返回(是否成功, 响应时间, RPC类型)"""
        import time
        start_time = time.time()
        
        try:
            from web3 import Web3
            w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={'timeout': timeout}))
            
            # 测试连接
            if not w3.is_connected():
                return False, time.time() - start_time, self.get_rpc_type(rpc_url)
            
            # 验证链ID
            chain_id = w3.eth.chain_id
            success = chain_id == expected_chain_id
            response_time = time.time() - start_time
            
            return success, response_time, self.get_rpc_type(rpc_url)
            
        except Exception:
            return False, time.time() - start_time, self.get_rpc_type(rpc_url)

    def get_rpc_type(self, rpc_url: str) -> str:
        """识别RPC类型"""
        if 'alchemy.com' in rpc_url:
            return 'Alchemy'
        elif 'ankr.com' in rpc_url:
            return 'Ankr'
        else:
            return '公共节点'
    
    def is_public_rpc(self, rpc_url: str) -> bool:
        """判断是否为公共RPC节点"""
        # 私有/付费节点标识
        private_indicators = [
            'alchemy.com', 'ankr.com', 'infura.io', 'moralis.io',
            'quicknode.com', 'getblock.io', 'nodereal.io'
        ]
        
        for indicator in private_indicators:
            if indicator in rpc_url.lower():
                return False
        
        return True

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
                print(f"{Fore.GREEN}✅ 已添加新代币 {symbol} ({token_info['name']}){Style.RESET_ALL}")
                return True
                
        except Exception as e:
            print(f"{Fore.RED}❌ 添加自定义代币失败: {e}{Style.RESET_ALL}")
            return False

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
        
        # 并发测试公共节点
        if public_rpcs:
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_rpc = {
                    executor.submit(test_single_rpc, rpc_url): rpc_url 
                    for rpc_url in public_rpcs
                }
                
                for future in concurrent.futures.as_completed(future_to_rpc):
                    rpc_url = future_to_rpc[future]
                    try:
                        success, response_time, rpc_type = future.result()
                        
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
                            'is_public': True
                        }
                        
                        results['rpc_details'].append(rpc_detail)
                        
                        if success:
                            results['working_rpcs'].append(rpc_url)
                        else:
                            results['failed_rpcs'].append(rpc_url)
                            
                    except Exception as e:
                        results['failed_rpcs'].append(rpc_url)
        
        # 串行测试私有节点（避免频繁请求被限制）
        for rpc_url in private_rpcs:
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
        """ERC20代币转账函数"""
        try:
            if network not in self.web3_connections:
                print(f"{Fore.RED}❌ 网络 {network} 未连接{Style.RESET_ALL}")
                return False
            
            if token_symbol not in self.tokens:
                print(f"{Fore.RED}❌ 不支持的代币: {token_symbol}{Style.RESET_ALL}")
                return False
            
            token_config = self.tokens[token_symbol]
            if network not in token_config['contracts']:
                print(f"{Fore.RED}❌ 代币 {token_symbol} 在 {network} 上不可用{Style.RESET_ALL}")
                return False
            
            w3 = self.web3_connections[network]
            contract_address = token_config['contracts'][network]
            
            # 验证地址格式
            try:
                to_address = w3.to_checksum_address(to_address)
                from_address = w3.to_checksum_address(from_address)
                contract_address = w3.to_checksum_address(contract_address)
            except Exception as e:
                print(f"{Fore.RED}❌ 地址格式错误: {e}{Style.RESET_ALL}")
                return False
            
            # 检查是否是自己转给自己
            if from_address.lower() == to_address.lower():
                print(f"{Fore.YELLOW}⚠️ 跳过自己转给自己的交易{Style.RESET_ALL}")
                return False
            
            # 创建合约实例
            contract = w3.eth.contract(address=contract_address, abi=self.erc20_abi)
            
            # 获取代币精度
            try:
                decimals = contract.functions.decimals().call()
            except:
                decimals = 18
            
            # 转换为合约单位
            amount_wei = int(amount * (10 ** decimals))
            
            # 智能Gas估算
            gas_cost, _ = self.estimate_gas_cost(network, 'erc20')
            native_balance, _ = self.get_balance(from_address, network)
            
            if native_balance < gas_cost:
                print(f"{Fore.RED}❌ 原生代币不足支付Gas费用: 需要 {gas_cost:.6f} ETH{Style.RESET_ALL}")
                return False
            
            # 获取当前Gas价格
            try:
                gas_price = w3.eth.gas_price
                min_gas_price = w3.to_wei(self.gas_price_gwei, 'gwei')
                gas_price = max(gas_price, min_gas_price)
            except:
                gas_price = w3.to_wei(self.gas_price_gwei, 'gwei')
            
            # 构建交易
            nonce = w3.eth.get_transaction_count(from_address)
            
            # 构建transfer函数调用数据
            transfer_function = contract.functions.transfer(to_address, amount_wei)
            
            transaction = {
                'to': contract_address,
                'value': 0,  # ERC20转账不需要发送ETH
                'gas': 65000,  # ERC20转账通常需要更多gas
                'gasPrice': gas_price,
                'nonce': nonce,
                'data': transfer_function._encode_transaction_data(),
                'chainId': self.networks[network]['chain_id']
            }
            
            # 签名交易
            signed_txn = w3.eth.account.sign_transaction(transaction, private_key)
            
            # 发送交易
            tx_hash = w3.eth.send_raw_transaction(signed_txn.rawTransaction)
            
            print(f"{Fore.GREEN}💸 ERC20转账成功: {amount:.6f} {token_symbol} from {from_address[:10]}... to {to_address[:10]}...{Style.RESET_ALL}")
            print(f"{Fore.CYAN}📋 交易哈希: {tx_hash.hex()}{Style.RESET_ALL}")
            
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

    def scan_addresses(self):
        """扫描所有地址，检查交易历史并建立监控列表"""
        print(f"\n{Fore.CYAN}🔍 开始扫描地址交易历史...{Style.RESET_ALL}")
        
        for address in self.wallets.keys():
            print(f"\n{Back.BLUE}{Fore.WHITE} 🔍 检查地址 {Style.RESET_ALL} {Fore.CYAN}{address}{Style.RESET_ALL}")
            address_networks = []
            blocked_networks = []
            
            for network_key in self.networks.keys():
                if self.check_transaction_history(address, network_key):
                    address_networks.append(network_key)
                else:
                    blocked_networks.append(network_key)
            
            # 更新监控列表
            if address_networks:
                self.monitored_addresses[address] = {
                    'networks': address_networks,
                    'last_check': time.time()
                }
                print(f"{Fore.GREEN}✅ 监控网络: {len(address_networks)} 个{Style.RESET_ALL}")
                
                # 显示监控的网络
                for net in address_networks[:5]:  # 只显示前5个
                    network_name = self.networks[net]['name']
                    print(f"  {Fore.GREEN}✓{Style.RESET_ALL} {network_name}")
                if len(address_networks) > 5:
                    print(f"  {Fore.GREEN}... 和其他 {len(address_networks) - 5} 个网络{Style.RESET_ALL}")
            else:
                print(f"{Fore.YELLOW}⚠️ 跳过监控（无交易历史）{Style.RESET_ALL}")
        
            # 保存被屏蔽的网络列表
            if blocked_networks:
                self.blocked_networks[address] = blocked_networks
                print(f"{Fore.RED}❌ 屏蔽网络: {len(blocked_networks)} 个{Style.RESET_ALL} {Fore.YELLOW}(无交易历史){Style.RESET_ALL}")
        
        print(f"\n{Back.GREEN}{Fore.BLACK} ✨ 扫描完成 ✨ {Style.RESET_ALL}")
        print(f"{Fore.GREEN}✅ 监控地址: {len(self.monitored_addresses)} 个{Style.RESET_ALL}")
        print(f"{Fore.RED}❌ 屏蔽网络: {sum(len(nets) for nets in self.blocked_networks.values())} 个{Style.RESET_ALL}")
        self.save_state()

    def monitor_loop(self):
        """监控循环"""
        import signal
        
        # 设置信号处理器
        def signal_handler(signum, frame):
            print(f"\n{Fore.YELLOW}⚠️ 收到中断信号，正在停止监控...{Style.RESET_ALL}")
            self.monitoring = False
        
        signal.signal(signal.SIGINT, signal_handler)
        
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
                                # 🚀 全链全代币监控 - 获取所有余额
                                all_balances = self.get_all_balances(address, network)
                                
                                if not all_balances:
                                    continue
                                
                                # 网络名称颜色化
                                network_name = self.networks[network]['name']
                                if '🧪' in network_name:  # 测试网
                                    network_color = f"{Back.YELLOW}{Fore.BLACK}{network_name}{Style.RESET_ALL}"
                                elif '🔷' in network_name or '🔵' in network_name:  # 主网
                                    network_color = f"{Back.BLUE}{Fore.WHITE}{network_name}{Style.RESET_ALL}"
                                else:  # 其他网络
                                    network_color = f"{Back.GREEN}{Fore.BLACK}{network_name}{Style.RESET_ALL}"
                                
                                # 处理每个代币余额
                                for token_key, token_info in all_balances.items():
                                    if not self.monitoring:
                                        break
                                    
                                    balance = token_info['balance']
                                    symbol = token_info['symbol']
                                    token_type = token_info['type']
                                    
                                    # 智能判断是否可以转账
                                    can_transfer, reason = self.can_transfer(address, network, token_type, balance)
                                    
                                    if token_type == 'native' and balance > self.min_transfer_amount and can_transfer:
                                        # 原生代币转账
                                        print(f"\n{Back.RED}{Fore.WHITE} 💰 原生代币 💰 {Style.RESET_ALL} {Fore.YELLOW}{balance:.6f} {symbol}{Style.RESET_ALL} in {Fore.CYAN}{address[:10]}...{Style.RESET_ALL} on {network_color}")
                                        
                                        if self.target_wallet:
                                            try:
                                                if self.transfer_funds(address, private_key, self.target_wallet, balance, network):
                                                    address_info['last_check'] = time.time()
                                                    self.save_state()
                                            except KeyboardInterrupt:
                                                print(f"\n{Fore.YELLOW}⚠️ 用户取消转账，停止监控{Style.RESET_ALL}")
                                                self.monitoring = False
                                                return
                                        else:
                                            print(f"{Fore.CYAN}💡 未设置目标账户，跳过转账{Style.RESET_ALL}")
                                    
                                    elif token_type == 'erc20' and balance > 0 and can_transfer:
                                        # ERC20代币转账
                                        print(f"\n{Back.MAGENTA}{Fore.WHITE} 🪙 ERC20代币 🪙 {Style.RESET_ALL} {Fore.GREEN}{balance:.6f} {symbol}{Style.RESET_ALL} in {Fore.CYAN}{address[:10]}...{Style.RESET_ALL} on {network_color}")
                                        
                                        if self.target_wallet:
                                            try:
                                                if self.transfer_erc20_token(address, private_key, self.target_wallet, token_key, balance, network):
                                                    address_info['last_check'] = time.time()
                                                    self.save_state()
                                            except KeyboardInterrupt:
                                                print(f"\n{Fore.YELLOW}⚠️ 用户取消转账，停止监控{Style.RESET_ALL}")
                                                self.monitoring = False
                                                return
                                        else:
                                            print(f"{Fore.CYAN}💡 未设置目标账户，跳过转账{Style.RESET_ALL}")
                                    
                                    elif balance > 0 and not can_transfer:
                                        # 有余额但不能转账
                                        token_icon = "💎" if token_type == 'native' else "🪙"
                                        print(f"{Fore.MAGENTA}{token_icon} {Fore.CYAN}{address[:10]}...{Style.RESET_ALL} on {network_color}: {Fore.YELLOW}{balance:.6f} {symbol}{Style.RESET_ALL} {Fore.RED}({reason}){Style.RESET_ALL}")
                                
                            except KeyboardInterrupt:
                                print(f"\n{Fore.YELLOW}⚠️ 监控被中断{Style.RESET_ALL}")
                                self.monitoring = False
                                return
                            except Exception as e:
                                print(f"{Fore.RED}❌ 检查余额失败 {address[:10]}... on {network}: {e}{Style.RESET_ALL}")
                                continue
                    
                    # 等待下一次检查（支持中断）
                    print(f"\n{Fore.CYAN}🕒 等待 {self.monitor_interval} 秒后进行下一轮检查... (按Ctrl+C退出){Style.RESET_ALL}")
                
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
            print(f"{Fore.GREEN}9.{Style.RESET_ALL} 🔍 RPC节点检测")
            print(f"{Fore.GREEN}10.{Style.RESET_ALL} ➕ 添加自定义RPC")
            print(f"{Fore.GREEN}11.{Style.RESET_ALL} 🪙 添加自定义代币")
            
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
                    self.menu_add_custom_rpc()
                elif choice == '11':
                    self.menu_add_custom_token()
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

    def menu_rpc_testing(self):
        """菜单：RPC节点检测"""
        print(f"\n{Fore.CYAN}✨ ====== 🔍 RPC节点检测管理 🔍 ====== ✨{Style.RESET_ALL}")
        print(f"{Back.BLUE}{Fore.WHITE} 📡 检测所有网络的RPC节点连接状态 {Style.RESET_ALL}")
        
        print(f"\n{Fore.YELLOW}🔧 检测选项：{Style.RESET_ALL}")
        print(f"  {Fore.GREEN}1.{Style.RESET_ALL} 🔍 测试所有RPC连接")
        print(f"  {Fore.GREEN}2.{Style.RESET_ALL} 🛠️ 自动屏蔽失效RPC")
        print(f"  {Fore.GREEN}3.{Style.RESET_ALL} 📊 查看RPC状态报告")
        print(f"  {Fore.RED}0.{Style.RESET_ALL} 🔙 返回主菜单")
        
        choice = self.safe_input(f"\n{Fore.YELLOW}🔢 请选择操作 (0-3): {Style.RESET_ALL}").strip()
        
        try:
            if choice == '1':
                # 测试所有RPC连接
                results = self.test_all_rpcs()
                
                # 显示汇总报告
                print(f"\n{Back.GREEN}{Fore.BLACK} 📊 RPC检测汇总报告 📊 {Style.RESET_ALL}")
                
                total_networks = len(results)
                total_rpcs = sum(len(r['working_rpcs']) + len(r['failed_rpcs']) for r in results.values())
                working_rpcs = sum(len(r['working_rpcs']) for r in results.values())
                
                print(f"🌐 总网络数: {Fore.CYAN}{total_networks}{Style.RESET_ALL}")
                print(f"📡 总RPC数: {Fore.CYAN}{total_rpcs}{Style.RESET_ALL}")
                print(f"✅ 可用RPC: {Fore.GREEN}{working_rpcs}{Style.RESET_ALL}")
                print(f"❌ 失效RPC: {Fore.RED}{total_rpcs - working_rpcs}{Style.RESET_ALL}")
                print(f"📊 总体成功率: {Fore.YELLOW}{working_rpcs/total_rpcs*100:.1f}%{Style.RESET_ALL}")
                
            elif choice == '2':
                # 自动屏蔽失效RPC
                confirm = self.safe_input(f"\n{Fore.YELLOW}⚠️ 确认自动屏蔽失效RPC？(y/N): {Style.RESET_ALL}").strip().lower()
                if confirm == 'y':
                    disabled_count = self.auto_disable_failed_rpcs()
                    print(f"\n{Fore.GREEN}✅ 操作完成！已屏蔽 {disabled_count} 个失效RPC节点{Style.RESET_ALL}")
                else:
                    print(f"\n{Fore.YELLOW}⚠️ 操作已取消{Style.RESET_ALL}")
                    
            elif choice == '3':
                # 查看RPC状态报告
                results = self.test_all_rpcs()
                
                print(f"\n{Back.CYAN}{Fore.BLACK} 📋 详细RPC状态报告 📋 {Style.RESET_ALL}")
                
                # 按成功率排序
                sorted_results = sorted(results.items(), key=lambda x: x[1]['success_rate'], reverse=True)
                
                for network_key, result in sorted_results:
                    success_rate = result['success_rate']
                    working_count = len(result['working_rpcs'])
                    total_count = working_count + len(result['failed_rpcs'])
                    
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
                            
            elif choice == '0':
                return
            else:
                print(f"\n{Fore.RED}❌ 无效选择{Style.RESET_ALL}")
                
        except Exception as e:
            print(f"\n{Fore.RED}❌ 操作失败: {e}{Style.RESET_ALL}")
        
        self.safe_input(f"\n{Fore.MAGENTA}🔙 按回车键继续...{Style.RESET_ALL}")

    def menu_add_custom_rpc(self):
        """菜单：添加自定义RPC"""
        print(f"\n{Fore.CYAN}✨ ====== ➕ 添加自定义RPC ➕ ====== ✨{Style.RESET_ALL}")
        print(f"{Back.GREEN}{Fore.BLACK} 🌐 为指定网络添加自定义RPC节点 {Style.RESET_ALL}")
        
        # 显示可用网络列表
        print(f"\n{Fore.YELLOW}📋 可用网络列表：{Style.RESET_ALL}")
        
        network_list = list(self.networks.items())
        for i, (network_key, network_info) in enumerate(network_list[:10]):  # 只显示前10个
            rpc_count = len(network_info['rpc_urls'])
            print(f"  {Fore.GREEN}{i+1:2d}.{Style.RESET_ALL} {network_info['name']} ({Fore.CYAN}{rpc_count}{Style.RESET_ALL} 个RPC)")
        
        if len(network_list) > 10:
            print(f"  ... 还有 {len(network_list) - 10} 个网络")
        
        print(f"\n{Fore.YELLOW}💡 提示：您可以输入网络编号、网络名称或network_key{Style.RESET_ALL}")
        print(f"{Fore.GREEN}示例：{Style.RESET_ALL}")
        print(f"  • 输入编号: 1")
        print(f"  • 输入名称: ethereum")
        print(f"  • 直接输入: ethereum")
        
        # 选择网络
        network_input = self.safe_input(f"\n{Fore.YELLOW}🔢 请选择要添加RPC的网络: {Style.RESET_ALL}").strip()
        
        if not network_input:
            print(f"\n{Fore.YELLOW}⚠️ 操作已取消{Style.RESET_ALL}")
            self.safe_input(f"\n{Fore.MAGENTA}🔙 按回车键返回...{Style.RESET_ALL}")
            return
        
        # 解析网络选择
        selected_network = None
        
        # 尝试数字索引
        try:
            index = int(network_input) - 1
            if 0 <= index < len(network_list):
                selected_network = network_list[index][0]
        except ValueError:
            pass
        
        # 尝试网络key匹配
        if not selected_network:
            network_input_lower = network_input.lower()
            for network_key in self.networks:
                if network_key.lower() == network_input_lower:
                    selected_network = network_key
                    break
        
        # 尝试网络名称匹配
        if not selected_network:
            for network_key, network_info in self.networks.items():
                if network_input_lower in network_info['name'].lower():
                    selected_network = network_key
                    break
        
        if not selected_network:
            print(f"\n{Fore.RED}❌ 未找到匹配的网络: {network_input}{Style.RESET_ALL}")
            self.safe_input(f"\n{Fore.MAGENTA}🔙 按回车键返回...{Style.RESET_ALL}")
            return
        
        network_info = self.networks[selected_network]
        print(f"\n{Fore.GREEN}✅ 已选择网络: {network_info['name']}{Style.RESET_ALL}")
        print(f"   当前RPC数量: {Fore.CYAN}{len(network_info['rpc_urls'])}{Style.RESET_ALL} 个")
        print(f"   链ID: {Fore.YELLOW}{network_info['chain_id']}{Style.RESET_ALL}")
        
        # 输入RPC URL
        print(f"\n{Fore.YELLOW}🔗 请输入要添加的RPC URL：{Style.RESET_ALL}")
        print(f"{Fore.GREEN}示例：{Style.RESET_ALL}")
        print(f"  • https://eth.llamarpc.com")
        print(f"  • https://rpc.flashbots.net")
        print(f"  • https://ethereum.publicnode.com")
        
        rpc_url = self.safe_input(f"\n{Fore.CYAN}➜ RPC URL: {Style.RESET_ALL}").strip()
        
        if not rpc_url:
            print(f"\n{Fore.YELLOW}⚠️ 操作已取消{Style.RESET_ALL}")
            self.safe_input(f"\n{Fore.MAGENTA}🔙 按回车键返回...{Style.RESET_ALL}")
            return
        
        # 验证URL格式
        if not rpc_url.startswith(('http://', 'https://')):
            print(f"\n{Fore.RED}❌ 无效的RPC URL格式{Style.RESET_ALL}")
            self.safe_input(f"\n{Fore.MAGENTA}🔙 按回车键返回...{Style.RESET_ALL}")
            return
        
        # 添加RPC
        print(f"\n{Fore.CYAN}🔄 正在添加自定义RPC...{Style.RESET_ALL}")
        
        if self.add_custom_rpc(selected_network, rpc_url):
            print(f"\n{Fore.GREEN}🎉 自定义RPC添加成功！{Style.RESET_ALL}")
            print(f"   网络: {network_info['name']}")
            print(f"   RPC: {rpc_url}")
            print(f"   新RPC数量: {Fore.CYAN}{len(self.networks[selected_network]['rpc_urls'])}{Style.RESET_ALL} 个")
        else:
            print(f"\n{Fore.RED}❌ 自定义RPC添加失败{Style.RESET_ALL}")
        
        self.safe_input(f"\n{Fore.MAGENTA}🔙 按回车键返回主菜单...{Style.RESET_ALL}")

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
