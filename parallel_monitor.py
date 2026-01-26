#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
并行监控模块 - 使用多浏览器实例并行监控多个门店
"""

import os
import time
import logging
import threading
from typing import List, Dict, Optional, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from queue import Queue

logger = logging.getLogger(__name__)


@dataclass
class WorkerResult:
    """单个worker的监控结果"""
    worker_id: int
    shop_name: str
    short_name: str
    success: bool
    off_sale: List = None
    sold_out: List = None
    duration: float = 0
    error: str = ""
    skipped: bool = False
    skip_reason: str = ""
    shop_status: str = "营业中"


class ParallelMonitor:
    """
    并行监控管理器
    
    使用多个浏览器实例并行监控不同门店，每个worker负责一部分门店。
    """
    
    def __init__(
        self,
        num_workers: int = 20,
        base_debug_port: int = 9222,
        config = None,
        profile_dir: str = None,
        log_callback: Callable = None,
    ):
        """
        初始化并行监控器
        
        Args:
            num_workers: 并行worker数量
            base_debug_port: 基础调试端口，每个worker使用 base_port + worker_id
            config: 应用配置
            profile_dir: 浏览器profile目录
            log_callback: 日志回调函数
        """
        self.num_workers = num_workers
        self.base_debug_port = base_debug_port
        self.config = config
        self.profile_dir = profile_dir
        self.log_callback = log_callback
        
        self.workers = []  # 存储所有worker的fetcher实例
        self.running = True
        self.results_queue = Queue()
        self._lock = threading.Lock()
        
    def log(self, msg: str):
        """输出日志"""
        logger.info(msg)
        if self.log_callback:
            try:
                self.log_callback(msg)
            except:
                pass
    
    def _create_fetcher(self, worker_id: int, use_main_browser: bool = False):
        """
        创建单个worker的fetcher实例
        
        Args:
            worker_id: worker编号
            use_main_browser: 是否使用主浏览器（worker_id=0时）
        """
        from selenium_fetcher import SeleniumGoodsFetcher
        import shutil
        
        # 计算该worker使用的端口
        debug_port = self.base_debug_port if use_main_browser else self.base_debug_port + worker_id
        
        # 每个worker使用独立的profile目录
        if use_main_browser:
            worker_profile_dir = self.profile_dir
        else:
            # 为worker创建独立的profile目录（复制主profile以复用登录状态）
            worker_profile_dir = f"{self.profile_dir}_worker_{worker_id}"
            
            # 如果worker的profile目录不存在，从主profile复制
            if not os.path.exists(worker_profile_dir) and os.path.exists(self.profile_dir):
                try:
                    # 只复制关键的登录文件，避免复制整个目录（太大）
                    os.makedirs(worker_profile_dir, exist_ok=True)
                    # 复制 Default 目录中的 Cookies 和 Login Data
                    default_src = os.path.join(self.profile_dir, 'Default')
                    default_dst = os.path.join(worker_profile_dir, 'Default')
                    if os.path.exists(default_src):
                        shutil.copytree(default_src, default_dst, 
                                       ignore=shutil.ignore_patterns('Cache*', 'Code Cache', 'GPUCache', 
                                                                    'Service Worker', 'blob_storage', 
                                                                    'IndexedDB', 'Local Storage'))
                    # 复制 Local State 文件
                    local_state_src = os.path.join(self.profile_dir, 'Local State')
                    if os.path.exists(local_state_src):
                        shutil.copy2(local_state_src, worker_profile_dir)
                except Exception as e:
                    logger.warning(f"Worker {worker_id} 复制profile失败: {e}")
                    # 如果复制失败，使用空目录（需要重新登录）
                    os.makedirs(worker_profile_dir, exist_ok=True)
        
        # 创建fetcher
        fetcher = SeleniumGoodsFetcher(
            shop_id=self.config.shop_id,
            chain_id=self.config.chain_id,
            base_url=self.config.base_url,
            headless=self.config.headless,
            debug_port=debug_port,
            user_data_dir=worker_profile_dir,  # 每个worker独立的profile目录
            browser_path=self.config.browser_path or None,
            auto_launch_browser=True,
        )
        
        return fetcher
    
    def _worker_task(
        self,
        worker_id: int,
        shops: List,
        main_fetcher = None,
        send_notification_callback: Callable = None,
    ) -> List[WorkerResult]:
        """
        单个worker的任务：监控分配给它的门店
        
        Args:
            worker_id: worker编号
            shops: 分配给该worker的门店列表
            main_fetcher: 主浏览器的fetcher实例（如果是worker 0）
            send_notification_callback: 发送通知的回调函数
        
        Returns:
            该worker的所有监控结果
        """
        results = []
        
        # Worker 0 使用主浏览器，其他worker创建新实例
        if worker_id == 0 and main_fetcher:
            fetcher = main_fetcher
            self.log(f"   [Worker-{worker_id}] 使用主浏览器实例")
        else:
            try:
                self.log(f"   [Worker-{worker_id}] 正在初始化浏览器... (端口:{self.base_debug_port + worker_id})")
                fetcher = self._create_fetcher(worker_id)
                
                # 启动浏览器
                open_url = f"{self.config.base_url}/app/shop/{self.config.shop_id}/food#app.shop.food?path=management"
                if not fetcher.ensure_debug_browser(open_url=open_url):
                    self.log(f"   [Worker-{worker_id}] ✗ 无法启动浏览器")
                    # 返回所有门店都失败的结果
                    for shop in shops:
                        results.append(WorkerResult(
                            worker_id=worker_id,
                            shop_name=shop.name,
                            short_name=self._simplify_shop_name(shop.name),
                            success=False,
                            error="无法启动浏览器",
                            skipped=True,
                            skip_reason="浏览器启动失败",
                        ))
                    return results
                
                # 初始化driver
                time.sleep(3)
                if not fetcher._init_driver():
                    self.log(f"   [Worker-{worker_id}] ✗ 驱动初始化失败")
                    for shop in shops:
                        results.append(WorkerResult(
                            worker_id=worker_id,
                            shop_name=shop.name,
                            short_name=self._simplify_shop_name(shop.name),
                            success=False,
                            error="驱动初始化失败",
                            skipped=True,
                            skip_reason="驱动初始化失败",
                        ))
                    return results
                
                self.log(f"   [Worker-{worker_id}] ✓ 浏览器就绪")
                
                # 导航到商品管理页面
                try:
                    goods_url = f"{fetcher.base_url}/app/shop/{fetcher.shop_id}/food#app.shop.food?path=management"
                    fetcher.driver.get(goods_url)
                    time.sleep(5)
                except Exception as e:
                    self.log(f"   [Worker-{worker_id}] ⚠ 导航失败: {e}")
                    
            except Exception as e:
                self.log(f"   [Worker-{worker_id}] ✗ 初始化失败: {e}")
                for shop in shops:
                    results.append(WorkerResult(
                        worker_id=worker_id,
                        shop_name=shop.name,
                        short_name=self._simplify_shop_name(shop.name),
                        success=False,
                        error=str(e),
                        skipped=True,
                        skip_reason="Worker初始化失败",
                    ))
                return results
        
        # 设置日志回调
        def worker_log(msg):
            # 添加worker标识
            self.log(f"[W{worker_id}] {msg}")
        
        fetcher._log_callback = worker_log
        
        # 依次监控分配的门店
        for idx, shop in enumerate(shops):
            if not self.running:
                break
            
            short_name = self._simplify_shop_name(shop.name)
            shop_start_time = time.time()
            
            self.log(f"[Worker-{worker_id}] [{idx+1}/{len(shops)}] 正在监控: {short_name}")
            
            try:
                # 切换门店
                switch_result = fetcher.switch_shop(shop.name)
                
                if not switch_result['success']:
                    shop_duration = time.time() - shop_start_time
                    reason = switch_result.get('message', '未知原因')
                    
                    results.append(WorkerResult(
                        worker_id=worker_id,
                        shop_name=shop.name,
                        short_name=short_name,
                        success=False,
                        duration=shop_duration,
                        skipped=True,
                        skip_reason=reason,
                    ))
                    continue
                
                # 获取营业状态
                shop_status = switch_result.get('shop_status', '营业中')
                
                # 抓取商品数据
                time.sleep(2)
                off_sale_list, sold_out_list = fetcher.fetch_abnormal_goods(use_current_page=True)
                
                shop_duration = time.time() - shop_start_time
                
                results.append(WorkerResult(
                    worker_id=worker_id,
                    shop_name=shop.name,
                    short_name=short_name,
                    success=True,
                    off_sale=off_sale_list or [],
                    sold_out=sold_out_list or [],
                    duration=shop_duration,
                    shop_status=shop_status,
                ))
                
                # 发送通知
                if send_notification_callback and (off_sale_list or sold_out_list):
                    try:
                        send_notification_callback(shop, off_sale_list, sold_out_list, shop_status)
                    except Exception as e:
                        self.log(f"[Worker-{worker_id}] 通知发送失败: {e}")
                        
            except Exception as e:
                shop_duration = time.time() - shop_start_time
                self.log(f"[Worker-{worker_id}] ✗ 监控出错: {e}")
                
                results.append(WorkerResult(
                    worker_id=worker_id,
                    shop_name=shop.name,
                    short_name=short_name,
                    success=False,
                    duration=shop_duration,
                    error=str(e),
                    skipped=True,
                    skip_reason=f"监控出错: {e}",
                ))
        
        # 清理：非主浏览器需要关闭
        if worker_id != 0 or not main_fetcher:
            try:
                if fetcher.driver:
                    fetcher.driver.quit()
            except:
                pass
        
        return results
    
    def _simplify_shop_name(self, full_name: str) -> str:
        """简化门店名称"""
        import re
        if not full_name:
            return "未知"
        
        # 去除前缀
        prefixes = ['阿狗手打·手作黑糖珍珠奶茶', '阿狗手打·手作', '阿狗手打·黑糖珍珠奶茶', '阿狗黑糖珍珠奶茶']
        name = full_name
        for prefix in prefixes:
            if name.startswith(prefix):
                name = name[len(prefix):]
                break
        
        # 去除括号
        name = re.sub(r'[（(](.*?)[）)]', r'\1', name)
        name = name.strip()
        
        return name if name else full_name
    
    def _split_shops(self, shops: List, num_chunks: int) -> List[List]:
        """
        将门店列表均匀分配给各个worker
        
        Args:
            shops: 所有门店列表
            num_chunks: 分组数量
        
        Returns:
            分组后的门店列表
        """
        if num_chunks <= 0:
            return [shops]
        
        # 计算每组大小
        chunk_size = len(shops) // num_chunks
        remainder = len(shops) % num_chunks
        
        chunks = []
        start = 0
        
        for i in range(num_chunks):
            # 前 remainder 个组多分配一个
            end = start + chunk_size + (1 if i < remainder else 0)
            if start < len(shops):
                chunks.append(shops[start:end])
            start = end
        
        # 过滤空组
        return [c for c in chunks if c]
    
    def run_parallel_monitor(
        self,
        shops: List,
        main_fetcher = None,
        send_notification_callback: Callable = None,
    ) -> Dict:
        """
        执行并行监控
        
        Args:
            shops: 所有门店列表
            main_fetcher: 主浏览器的fetcher实例（已登录）
            send_notification_callback: 发送通知的回调函数
        
        Returns:
            汇总的监控结果
        """
        total_shops = len(shops)
        
        # 根据门店数量和worker数量，计算实际使用的worker数
        actual_workers = min(self.num_workers, total_shops)
        
        self.log(f"")
        self.log(f"{'='*50}")
        self.log(f"🚀 启动并行监控")
        self.log(f"   门店总数: {total_shops}")
        self.log(f"   Worker数: {actual_workers}")
        self.log(f"{'='*50}")
        
        # 分配门店给各个worker
        shop_chunks = self._split_shops(shops, actual_workers)
        
        # 显示分配情况
        for i, chunk in enumerate(shop_chunks):
            self.log(f"   Worker-{i}: 负责 {len(chunk)} 个门店")
        
        self.log(f"")
        
        # 汇总结果
        all_results = {
            'shops_monitored': 0,
            'shops_skipped': 0,
            'total_off_sale': 0,
            'total_sold_out': 0,
            'shop_results': [],
            'skipped_shops': [],
            'total_duration': 0,
        }
        
        monitor_start_time = time.time()
        
        # 使用线程池并行执行
        with ThreadPoolExecutor(max_workers=actual_workers) as executor:
            futures = []
            
            for worker_id, shop_chunk in enumerate(shop_chunks):
                # Worker 0 使用主浏览器
                use_main = (worker_id == 0)
                
                future = executor.submit(
                    self._worker_task,
                    worker_id,
                    shop_chunk,
                    main_fetcher if use_main else None,
                    send_notification_callback,
                )
                futures.append((worker_id, future))
            
            # 等待所有worker完成
            for worker_id, future in futures:
                try:
                    worker_results = future.result(timeout=3600)  # 1小时超时
                    
                    # 汇总结果
                    for result in worker_results:
                        if result.success:
                            all_results['shops_monitored'] += 1
                            all_results['total_off_sale'] += len(result.off_sale or [])
                            all_results['total_sold_out'] += len(result.sold_out or [])
                            all_results['shop_results'].append({
                                'shop_name': result.shop_name,
                                'short_name': result.short_name,
                                'off_sale': result.off_sale or [],
                                'sold_out': result.sold_out or [],
                                'duration': result.duration,
                                'shop_status': result.shop_status,
                            })
                        else:
                            all_results['shops_skipped'] += 1
                            all_results['skipped_shops'].append({
                                'name': result.shop_name,
                                'short_name': result.short_name,
                                'reason': result.skip_reason or result.error,
                                'status': '未营业' if result.skipped else '错误',
                                'duration': result.duration,
                            })
                    
                    self.log(f"   [Worker-{worker_id}] ✓ 完成，处理了 {len(worker_results)} 个门店")
                    
                except Exception as e:
                    self.log(f"   [Worker-{worker_id}] ✗ 执行出错: {e}")
        
        all_results['total_duration'] = time.time() - monitor_start_time
        
        # 打印汇总
        duration = all_results['total_duration']
        if duration >= 60:
            duration_str = f"{int(duration // 60)}分{int(duration % 60)}秒"
        else:
            duration_str = f"{duration:.0f}秒"
        
        self.log(f"")
        self.log(f"{'='*50}")
        self.log(f"📊 并行监控完成！")
        self.log(f"   ⏱ 总耗时: {duration_str}")
        self.log(f"   ✓ 监控成功: {all_results['shops_monitored']} 个门店")
        self.log(f"   ⏸ 跳过: {all_results['shops_skipped']} 个门店")
        self.log(f"   🔻 总计下架: {all_results['total_off_sale']} 个商品")
        self.log(f"   🔴 总计售罄: {all_results['total_sold_out']} 个商品")
        self.log(f"{'='*50}")
        
        return all_results
    
    def stop(self):
        """停止监控"""
        self.running = False
