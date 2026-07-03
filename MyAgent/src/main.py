# coding: utf-8
"""Soccer Agent - 足球识别 Agent。

功能：
1. 使用 RGB 颜色识别经典白底黑纹足球
2. 输出足球位置、距离等信息
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
COMPONENT_TEST_SOCCER: str = "test_soccer"

WALK_PAGE_ID: str = "walk_page"



class SoccerAgent(AgentBase):
    """Agent that detects a soccer ball."""

    def __init__(self):
        super().__init__(AgentFeatures(enable_auto_getup=True))
        self.robot: BoosterRobot = BoosterRobot()
        self._running = False
        self._test_thread: threading.Thread | None = None
        self._ball_tracker = BallTracker(history_size=5)
        self.setup_components()

    def on_agent_activated(self):
        """Called when the Agent is activated."""
        self.logger.info("SoccerAgent is activated")

    def on_agent_close(self):
        """Called when the Agent is closing."""
        self.logger.info("SoccerAgent is closing")
        self._stop_test()

    def setup_components(self):
        """Set up the Agent's button components."""
        self.page_proxy = ComponentStatePageProxy(self)
        walk_page_id = WALK_PAGE_ID
        self.page_proxy.register_page(
            walk_page_id, lambda *_: True
        )

        # Test soccer button
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
            try:
                fx, fy = get_camera_focal_length(self.robot)
                self.logger.info(f"Camera focal length: fx={fx:.1f}, fy={fy:.1f}")
            except Exception as e:
                self.logger.warn(f"Failed to get camera info, using default: {e}")
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

                if ball_info is None:
                    no_detect_count += 1
                    self.logger.info(
                        f"[测试帧 {frame_count}] ✗ 未检测到足球 "
                        f"(连续未检测: {no_detect_count})"
                    )
                else:
                    no_detect_count = 0
                    detect_count += 1

                    center_x = ball_info["center_x"]
                    center_y = ball_info["center_y"]
                    radius = ball_info["radius"]
                    area_ratio = ball_info["area_ratio"]

                    # 归一化坐标
                    norm_x = (center_x / img_w - 0.5) * 2.0
                    norm_y = (center_y / img_h - 0.5) * 2.0

                    # 估算距离
                    distance = estimate_distance_combined(radius, center_y, img_h, fx)
                    lateral_offset = norm_x * distance * 0.5

                    self.logger.info(
                        f"[测试帧 {frame_count}] ✓ 足球检测到! "
                        f"位置=({center_x:.0f}, {center_y:.0f}), "
                        f"半径={radius:.0f}px, "
                        f"面积占比={area_ratio:.3%}, "
                        f"距离={distance:.2f}m, "
                        f"横向偏移={lateral_offset:.2f}m"
                    )

                time.sleep(0.5)

            except Exception as e:
                self.logger.error(f"Error in test loop: {e}")
                time.sleep(1.0)

        self.logger.info(
            f"Soccer test loop stopped. "
            f"总帧数: {frame_count}, 检测到: {detect_count}, "
            f"检测率: {detect_count/max(1,frame_count)*100:.1f}%"
        )

    def _stop_test(self):
        """停止测试并清理资源。"""
        self._running = False

        if self._test_thread is not None:
            self._test_thread.join(timeout=3.0)
            self._test_thread = None

        self.logger.info("Test cleanup complete")