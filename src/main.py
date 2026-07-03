# coding: utf-8
<<<<<<< HEAD
"""Soccer Agent - 足球识别 Agent。

功能：
1. 使用 RGB 颜色识别经典白底黑纹足球
2. 输出足球位置、距离等信息
=======
"""Soccer Agent - 足球识别与搜索 Agent。

功能：
1. 使用 RGB 颜色识别经典白底黑纹足球
2. 当视野内没有足球时，自动转动头部搜索
3. 找到足球后持续跟踪并输出位置信息
>>>>>>> b5ca688 (首次完成较为准确的足球识别)
"""

import time
import threading
from typing import cast

from booster_agent_framework import (
    AgentBase,
    AgentFeatures,
    Component,
    ComponentStatePageProxy,
    DefaultStateIconComponent,
    LocaleString,
)

from boosteros.robots.booster import BoosterRobot

# 从独立模块导入足球检测功能
try:
    from .soccer_detector import (
        get_camera_focal_length,
        estimate_distance_combined,
        detect_soccer_ball_rgb,
        BallTracker,
    )
except ImportError:
    from soccer_detector import (
        get_camera_focal_length,
        estimate_distance_combined,
        detect_soccer_ball_rgb,
        BallTracker,
    )


# ---------------------------------------------------------------------------
# Component IDs
# ---------------------------------------------------------------------------
<<<<<<< HEAD
=======
COMPONENT_START_SEARCH: str = "start_search"
COMPONENT_STOP_SEARCH: str = "stop_search"
>>>>>>> b5ca688 (首次完成较为准确的足球识别)
COMPONENT_TEST_SOCCER: str = "test_soccer"

WALK_PAGE_ID: str = "walk_page"


<<<<<<< HEAD

class SoccerAgent(AgentBase):
    """Agent that detects a soccer ball."""
=======
class SoccerAgent(AgentBase):
    """Agent that detects a soccer ball and searches for it by moving head."""
>>>>>>> b5ca688 (首次完成较为准确的足球识别)

    def __init__(self):
        super().__init__(AgentFeatures(enable_auto_getup=True))
        self.robot: BoosterRobot = BoosterRobot()
        self._running = False
<<<<<<< HEAD
        self._test_thread: threading.Thread | None = None
        self._ball_tracker = BallTracker(history_size=5)
=======
        self._search_thread: threading.Thread | None = None
        self._ball_tracker = BallTracker(history_size=5)  # 时间滤波
        self._search_direction = 1  # 搜索方向：1=向右，-1=向左
        self._search_angle = 0.0  # 当前头部搜索角度
>>>>>>> b5ca688 (首次完成较为准确的足球识别)
        self.setup_components()

    def on_agent_activated(self):
        """Called when the Agent is activated."""
        self.logger.info("SoccerAgent is activated")

    def on_agent_close(self):
        """Called when the Agent is closing."""
        self.logger.info("SoccerAgent is closing")
<<<<<<< HEAD
        self._stop_test()
=======
        self._stop_search_task()
>>>>>>> b5ca688 (首次完成较为准确的足球识别)

    def setup_components(self):
        """Set up the Agent's button components."""
        self.page_proxy = ComponentStatePageProxy(self)
        walk_page_id = WALK_PAGE_ID
        self.page_proxy.register_page(
            walk_page_id, lambda *_: True
        )

<<<<<<< HEAD
        # Test soccer button
=======
        # Start search button
        start_btn = DefaultStateIconComponent(
            COMPONENT_START_SEARCH,
            LocaleString({"en": "Start Search", "zh": "开始找球"}),
            "res/wave.png",
            False,
            self.on_start_search_click,
        )
        self.page_proxy.register_component(walk_page_id, start_btn)

        # Stop search button
        stop_btn = DefaultStateIconComponent(
            COMPONENT_STOP_SEARCH,
            LocaleString({"en": "Stop Search", "zh": "停止找球"}),
            "res/logo.png",
            False,
            self.on_stop_search_click,
        )
        self.page_proxy.register_component(walk_page_id, stop_btn)

        # Test soccer button - 单独测试足球识别
>>>>>>> b5ca688 (首次完成较为准确的足球识别)
        test_btn = DefaultStateIconComponent(
            COMPONENT_TEST_SOCCER,
            LocaleString({"en": "Test Soccer", "zh": "测试足球"}),
            "res/handshake.png",
            False,
            self.on_test_soccer_click,
        )
        self.page_proxy.register_component(walk_page_id, test_btn)

    # ------------------------------------------------------------------
    # Button callbacks
    # ------------------------------------------------------------------

<<<<<<< HEAD
    def on_test_soccer_click(
        self, component: Component
    ) -> LocaleString | None:
        """启动足球识别测试模式。"""
        self.logger.info("Test soccer clicked")

        if self._running:
            return LocaleString(
                {"en": "Test already running", "zh": "测试已在运行中"}
            )

        try:
            # 获取相机参数
=======
    def on_start_search_click(
        self, component: Component
    ) -> LocaleString | None:
        """Start the search task: switch to walk mode, start detection loop."""
        self.logger.info("Start search clicked")

        if self._running:
            return LocaleString(
                {"en": "Search task already running", "zh": "找球任务已在运行中"}
            )

        try:
            # 1. Switch to walk mode with soccer gait
            current_mode = self.robot.get_mode()
            self.logger.info(f"Current mode: {current_mode}")

            if current_mode != "walk":
                self.logger.info("Switching to walk mode with soccer gait...")
                self.robot.set_gait("soccer")
                self.robot.set_mode("walk")
                self.logger.info(f"Mode after switch: {self.robot.get_mode()}")

            # 2. Get camera info for distance calculation
>>>>>>> b5ca688 (首次完成较为准确的足球识别)
            try:
                fx, fy = get_camera_focal_length(self.robot)
                self.logger.info(f"Camera focal length: fx={fx:.1f}, fy={fy:.1f}")
            except Exception as e:
                self.logger.warn(f"Failed to get camera info, using default: {e}")
<<<<<<< HEAD
                fx, fy = 216.5, 216.5

            # 启动测试模式
            self._running = True
            self._test_thread = threading.Thread(
                target=self._test_soccer_loop, daemon=True
            )
            self._test_thread.start()

            return LocaleString(
                {"en": "Soccer test mode started! Check logs for detection results.", "zh": "足球测试模式已启动！请查看日志获取检测结果"}
            )

        except Exception as e:
            self.logger.error(f"Failed to start soccer test: {e}")
            return LocaleString(
                {"en": f"Failed to start test: {e}", "zh": f"启动测试失败: {e}"}
            )

    def _test_soccer_loop(self):
        """足球识别测试循环 - 仅检测不移动。"""
        self.logger.info("Soccer test loop started - DETECTION ONLY, NO MOVEMENT")

        # 获取相机参数
        fx, fy = get_camera_focal_length(self.robot)

        frame_count = 0
        detect_count = 0
        no_detect_count = 0
=======

            # 3. Start the search loop in a background thread
            self._running = True
            self._search_direction = 1
            self._search_angle = 0.0
            self._search_thread = threading.Thread(
                target=self._search_loop, daemon=True
            )
            self._search_thread.start()

            return LocaleString(
                {"en": "Search task started! Looking for soccer ball.", "zh": "找球任务已启动！正在寻找足球"}
            )

        except Exception as e:
            self.logger.error(f"Failed to start search task: {e}")
            self._running = False
            return LocaleString(
                {"en": f"Failed to start: {e}", "zh": f"启动失败: {e}"}
            )

    def on_stop_search_click(
        self, component: Component
    ) -> LocaleString | None:
        """Stop the search task."""
        self.logger.info("Stop search clicked")
        self._stop_search_task()
        return LocaleString(
            {"en": "Search task stopped", "zh": "找球任务已停止"}
        )

    # ------------------------------------------------------------------
    # Search loop
    # ------------------------------------------------------------------

    def _search_loop(self):
        """Background loop: detect ball, move head to search when not found."""
        self.logger.info("Search loop started")
        
        # 获取相机参数
        fx, fy = get_camera_focal_length(self.robot)
        self.logger.info(f"Camera focal length: fx={fx:.1f}, fy={fy:.1f}")

        frame_count = 0
        detect_count = 0
        no_detect_frames = 0  # 连续未检测到球的帧数
        max_no_detect_frames = 3  # 超过此帧数未检测到球，开始搜索
        is_searching = False  # 是否正在搜索（摆动头部）
>>>>>>> b5ca688 (首次完成较为准确的足球识别)

        while self._running:
            try:
                frame_count += 1
<<<<<<< HEAD

                # 捕获RGB图像
=======
                
                # Capture RGB image for ball detection
>>>>>>> b5ca688 (首次完成较为准确的足球识别)
                try:
                    image = self.robot.get_image(img_type="rgb")
                except Exception as img_err:
                    self.logger.warn(f"Image capture error: {img_err}")
                    time.sleep(0.5)
                    continue

                if image is None:
                    self.logger.warn("No image received")
                    time.sleep(0.5)
                    continue

<<<<<<< HEAD
                # 检测足球
                image_np = image.to_numpy()
                img_w, img_h = image.width, image.height

                raw_detection = detect_soccer_ball_rgb(image_np, logger=self.logger)
                ball_info = self._ball_tracker.update(raw_detection)

=======
                # Detect soccer ball
                image_np = image.to_numpy()
                img_w, img_h = image.width, image.height
                
                # 使用RGB颜色检测足球
                raw_detection = detect_soccer_ball_rgb(image_np, logger=self.logger)
                
                # 应用时间滤波稳定检测结果
                ball_info = self._ball_tracker.update(raw_detection)

                if ball_info is None:
                    no_detect_frames += 1
                    self.logger.info(
                        f"[Frame {frame_count}] No ball detected ({no_detect_frames}/{max_no_detect_frames})"
                    )
                    
                    # 连续多帧未检测到球，开始摆动头部搜索
                    if no_detect_frames >= max_no_detect_frames:
                        is_searching = True
                        self._search_for_ball()
                    
                    time.sleep(0.3)
                    continue

                # 检测到球，重置搜索状态
                no_detect_frames = 0
                detect_count += 1
                is_searching = False  # 找到球，停止搜索
                
                # Ball detected
                img_center_x = ball_info["center_x"]
                img_center_y = ball_info["center_y"]
                area_ratio = ball_info["area_ratio"]
                ball_radius_px = ball_info["radius"]
                is_filtered = ball_info.get("filtered", False)

                # Normalize to [-1, 1]
                norm_x = (img_center_x / img_w - 0.5) * 2.0
                norm_y = (img_center_y / img_h - 0.5) * 2.0

                # 使用结合半径和Y坐标的距离计算方法
                est_distance = estimate_distance_combined(ball_radius_px, img_center_y, img_h, fx)
                
                # 计算横向偏移
                est_y = norm_x * est_distance * 0.5

                filter_tag = " [filtered]" if is_filtered else ""
                self.logger.info(
                    f"[Frame {frame_count}]{filter_tag} Ball: ({img_center_x:.0f}, {img_center_y:.0f}), "
                    f"r={ball_radius_px:.0f}px, area={area_ratio:.3%}, "
                    f"dist={est_distance:.2f}m, y={est_y:.2f}m"
                )

                # 如果球在画面边缘（还没到中间），转动头部跟踪让球到中间
                if abs(norm_x) > 0.3:
                    self._track_ball(norm_x)
                else:
                    # 球已经在视野中间，停止搜索摆动
                    self.logger.info(f"[Frame {frame_count}] Ball centered, search stopped")

                time.sleep(0.3)  # Loop interval

            except Exception as e:
                self.logger.error(f"Error in search loop: {e}")
                time.sleep(1.0)

        self.logger.info(f"Search loop stopped. Total frames: {frame_count}, Detected: {detect_count}")

    def _search_for_ball(self):
        """转动头部搜索足球 - 缓慢连续转动。"""
        # 每次只转动很小的角度，实现缓慢连续搜索
        search_step = 0.02  # 每次转动角度（弧度），约1度，非常缓慢
        max_angle = 0.6  # 最大搜索角度
        
        # 更新搜索角度 - 小步连续转动
        self._search_angle += self._search_direction * search_step
        
        # 到达边界时平滑反转方向
        if self._search_angle > max_angle:
            self._search_angle = max_angle
            self._search_direction = -1  # 开始向左转
        elif self._search_angle < -max_angle:
            self._search_angle = -max_angle
            self._search_direction = 1  # 开始向右转
        
        self.logger.info(f"Searching: head angle={self._search_angle:.2f} rad, dir={self._search_direction}")
        
        # 控制头部转动
        try:
            self.robot.set_head_angle(pitch=0.0, yaw=self._search_angle)
        except Exception as e:
            self.logger.error(f"Failed to move head: {e}")

    def _track_ball(self, norm_x: float):
        """根据球的位置转动头部跟踪。"""
        # 将球在画面中的位置转换为头部目标角度
        target_yaw = norm_x * 0.5  # 缩放系数
        
        self.logger.info(f"Tracking ball: target_yaw={target_yaw:.2f} rad")
        
        try:
            self.robot.set_head_angle(pitch=0.0, yaw=target_yaw)
            self._search_angle = target_yaw  # 更新当前搜索角度
        except Exception as e:
            self.logger.error(f"Failed to track ball: {e}")

    def on_test_soccer_click(
        self, component: Component
    ) -> LocaleString | None:
        """启动单独足球识别测试模式。
        
        此模式不控制机器人移动，仅输出足球识别结果，
        方便用户在不同距离下测试识别精度。
        """
        self.logger.info("Test soccer clicked")
        
        try:
            # 获取相机参数
            try:
                fx, fy = get_camera_focal_length(self.robot)
                self.logger.info(f"Camera focal length: fx={fx:.1f}, fy={fy:.1f}")
            except Exception as e:
                self.logger.warn(f"Failed to get camera info, using default: {e}")
                fx, fy = 216.5, 216.5
            
            # 启动测试模式（不移动机器人）
            self._running = True
            self._search_thread = threading.Thread(
                target=self._test_soccer_loop, daemon=True
            )
            self._search_thread.start()
            
            return LocaleString(
                {"en": "Soccer test mode started! Check logs for detection results.", "zh": "足球测试模式已启动！请查看日志获取检测结果"}
            )
            
        except Exception as e:
            self.logger.error(f"Failed to start soccer test: {e}")
            return LocaleString(
                {"en": f"Failed to start test: {e}", "zh": f"启动测试失败: {e}"}
            )
    
    def _test_soccer_loop(self):
        """足球识别测试循环 - 仅检测不移动。
        
        用于在不同距离下测试足球识别精度。
        """
        self.logger.info("Soccer test loop started - DETECTION ONLY, NO MOVEMENT")
        
        # 获取相机参数
        fx, fy = get_camera_focal_length(self.robot)
        
        frame_count = 0
        detect_count = 0
        no_detect_count = 0
        
        while self._running:
            try:
                frame_count += 1
                
                # 捕获RGB图像
                try:
                    image = self.robot.get_image(img_type="rgb")
                except Exception as img_err:
                    self.logger.warn(f"Image capture error: {img_err}")
                    time.sleep(0.5)
                    continue
                
                if image is None:
                    self.logger.warn("No image received")
                    time.sleep(0.5)
                    continue
                
                # 检测足球
                image_np = image.to_numpy()
                img_w, img_h = image.width, image.height
                
                raw_detection = detect_soccer_ball_rgb(image_np, logger=self.logger)
                ball_info = self._ball_tracker.update(raw_detection)
                
>>>>>>> b5ca688 (首次完成较为准确的足球识别)
                if ball_info is None:
                    no_detect_count += 1
                    self.logger.info(
                        f"[测试帧 {frame_count}] ✗ 未检测到足球 "
                        f"(连续未检测: {no_detect_count})"
                    )
                else:
                    no_detect_count = 0
                    detect_count += 1
<<<<<<< HEAD

=======
                    
>>>>>>> b5ca688 (首次完成较为准确的足球识别)
                    center_x = ball_info["center_x"]
                    center_y = ball_info["center_y"]
                    radius = ball_info["radius"]
                    area_ratio = ball_info["area_ratio"]
<<<<<<< HEAD

                    # 归一化坐标
                    norm_x = (center_x / img_w - 0.5) * 2.0
                    norm_y = (center_y / img_h - 0.5) * 2.0

                    # 估算距离
                    distance = estimate_distance_combined(radius, center_y, img_h, fx)
                    lateral_offset = norm_x * distance * 0.5

=======
                    
                    # 归一化坐标
                    norm_x = (center_x / img_w - 0.5) * 2.0
                    norm_y = (center_y / img_h - 0.5) * 2.0
                    
                    # 估算距离
                    distance = estimate_distance_combined(radius, center_y, img_h, fx)
                    lateral_offset = norm_x * distance * 0.5
                    
>>>>>>> b5ca688 (首次完成较为准确的足球识别)
                    self.logger.info(
                        f"[测试帧 {frame_count}] ✓ 足球检测到! "
                        f"位置=({center_x:.0f}, {center_y:.0f}), "
                        f"半径={radius:.0f}px, "
                        f"面积占比={area_ratio:.3%}, "
                        f"距离={distance:.2f}m, "
                        f"横向偏移={lateral_offset:.2f}m"
                    )
<<<<<<< HEAD

                time.sleep(0.5)

            except Exception as e:
                self.logger.error(f"Error in test loop: {e}")
                time.sleep(1.0)

=======
                
                time.sleep(0.5)  # 测试模式间隔稍长
                
            except Exception as e:
                self.logger.error(f"Error in test loop: {e}")
                time.sleep(1.0)
        
>>>>>>> b5ca688 (首次完成较为准确的足球识别)
        self.logger.info(
            f"Soccer test loop stopped. "
            f"总帧数: {frame_count}, 检测到: {detect_count}, "
            f"检测率: {detect_count/max(1,frame_count)*100:.1f}%"
        )
<<<<<<< HEAD

    def _stop_test(self):
        """停止测试并清理资源。"""
        self._running = False

        if self._test_thread is not None:
            self._test_thread.join(timeout=3.0)
            self._test_thread = None

        self.logger.info("Test cleanup complete")
=======
    
    def _stop_search_task(self):
        """Stop the search task and clean up resources."""
        self._running = False

        # 恢复头部位置
        try:
            self.robot.set_head_angle(pitch=0.0, yaw=0.0)
        except Exception as e:
            self.logger.error(f"Error resetting head: {e}")

        if self._search_thread is not None:
            self._search_thread.join(timeout=3.0)
            self._search_thread = None

        self.logger.info("Search task cleanup complete")
>>>>>>> b5ca688 (首次完成较为准确的足球识别)
