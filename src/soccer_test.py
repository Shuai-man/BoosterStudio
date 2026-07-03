# coding: utf-8
"""足球识别测试模块 - 用于在不同距离下测试足球识别精度。

功能：
1. 单独运行足球识别，不依赖Agent框架
2. 输出详细的检测结果和位置信息
3. 支持不同距离下的测试验证
"""

import numpy as np
import cv2
import time
from typing import Optional

from boosteros.robots.booster import BoosterRobot

# 从独立模块导入足球检测功能
try:
    from .soccer_detector import (
        get_camera_focal_length,
        estimate_distance_combined,
        detect_soccer_ball_rgb,
    )
except ImportError:
    from soccer_detector import (
        get_camera_focal_length,
        estimate_distance_combined,
        detect_soccer_ball_rgb,
    )


class SoccerTest:
    """足球识别测试器 - 用于测试不同距离下的识别精度。"""
    
    def __init__(self):
        self.robot = BoosterRobot()
        self.fx = 0.0
        self.fy = 0.0
        self._initialized = False
    
    def initialize(self):
        """初始化机器人连接和相机参数。"""
        if self._initialized:
            return True
        
        try:
            # 获取相机参数
            self.fx, self.fy = get_camera_focal_length(self.robot)
            print(f"[初始化] 相机焦距: fx={self.fx:.1f}, fy={self.fy:.1f}")
            self._initialized = True
            return True
        except Exception as e:
            print(f"[初始化] 失败: {e}")
            return False
    
    def test_single_frame(self) -> Optional[dict]:
        """单帧测试 - 捕获一帧图像并检测足球。
        
        返回:
            检测结果字典，包含位置、距离等信息；未检测到返回None
        """
        if not self._initialized:
            if not self.initialize():
                return None
        
        try:
            # 捕获RGB图像
            image = self.robot.get_image(img_type="rgb")
            if image is None:
                print("[测试] 未获取到图像")
                return None
            
            image_np = image.to_numpy()
            img_w, img_h = image.width, image.height
            
            # 执行足球检测
            result = detect_soccer_ball_rgb(image_np)
            
            if result is None:
                print("[测试] 未检测到足球")
                return None
            
            # 计算距离和位置
            center_x = result["center_x"]
            center_y = result["center_y"]
            radius = result["radius"]
            area_ratio = result["area_ratio"]
            
            # 归一化坐标到[-1, 1]
            norm_x = (center_x / img_w - 0.5) * 2.0
            norm_y = (center_y / img_h - 0.5) * 2.0
            
            # 估算距离
            distance = estimate_distance_combined(radius, center_y, img_h, self.fx)
            
            # 计算横向偏移
            lateral_offset = norm_x * distance * 0.5
            
            return {
                "center_x": center_x,
                "center_y": center_y,
                "radius": radius,
                "area_ratio": area_ratio,
                "distance": distance,
                "lateral_offset": lateral_offset,
                "norm_x": norm_x,
                "norm_y": norm_y,
                "image_size": (img_w, img_h),
            }
            
        except Exception as e:
            print(f"[测试] 检测异常: {e}")
            return None
    
    def test_continuous(self, duration: float = 10.0, interval: float = 0.5):
        """连续测试 - 在指定时间内持续检测足球。
        
        参数:
            duration: 测试持续时间（秒）
            interval: 检测间隔（秒）
        """
        if not self._initialized:
            if not self.initialize():
                return
        
        print(f"\n{'='*60}")
        print(f"[连续测试] 开始，持续 {duration} 秒，间隔 {interval} 秒")
        print(f"{'='*60}\n")
        
        start_time = time.time()
        frame_count = 0
        detect_count = 0
        distances = []
        
        while time.time() - start_time < duration:
            frame_count += 1
            result = self.test_single_frame()
            
            if result:
                detect_count += 1
                distances.append(result["distance"])
                print(f"[帧 {frame_count}] ✓ 足球检测到!")
                print(f"  位置: ({result['center_x']:.0f}, {result['center_y']:.0f})")
                print(f"  半径: {result['radius']:.0f} 像素")
                print(f"  面积占比: {result['area_ratio']:.3%}")
                print(f"  估算距离: {result['distance']:.2f} 米")
                print(f"  横向偏移: {result['lateral_offset']:.2f} 米")
            else:
                print(f"[帧 {frame_count}] ✗ 未检测到足球")
            
            time.sleep(interval)
        
        # 统计结果
        print(f"\n{'='*60}")
        print(f"[测试统计]")
        print(f"  总帧数: {frame_count}")
        print(f"  检测到: {detect_count}")
        print(f"  检测率: {detect_count/frame_count*100:.1f}%")
        if distances:
            print(f"  平均距离: {np.mean(distances):.2f} 米")
            print(f"  距离范围: {min(distances):.2f} - {max(distances):.2f} 米")
        print(f"{'='*60}\n")
    
    def test_distance_calibration(self):
        """距离校准测试 - 帮助用户了解不同距离下的像素表现。
        
        此功能帮助用户建立距离与像素大小的对应关系。
        """
        if not self._initialized:
            if not self.initialize():
                return
        
        print(f"\n{'='*60}")
        print(f"[距离校准测试]")
        print(f"请将足球放置在不同距离，按回车键记录当前帧")
        print(f"输入 'q' 退出测试")
        print(f"{'='*60}\n")
        
        test_count = 0
        
        while True:
            try:
                # 捕获图像
                image = self.robot.get_image(img_type="rgb")
                if image is None:
                    print("[校准] 未获取到图像")
                    time.sleep(0.5)
                    continue
                
                image_np = image.to_numpy()
                img_w, img_h = image.width, image.height
                
                # 检测足球
                result = detect_soccer_ball_rgb(image_np)
                
                test_count += 1
                print(f"\n[采样 {test_count}]")
                
                if result:
                    center_x = result["center_x"]
                    center_y = result["center_y"]
                    radius = result["radius"]
                    area = result["area"]
                    
                    distance = estimate_distance_combined(radius, center_y, img_h, self.fx)
                    
                    print(f"  ✓ 检测到足球")
                    print(f"  位置: ({center_x:.0f}, {center_y:.0f})")
                    print(f"  半径: {radius:.0f} 像素")
                    print(f"  面积: {area:.0f} 像素²")
                    print(f"  估算距离: {distance:.2f} 米")
                    print(f"  提示: 请记录实际距离以便校准")
                else:
                    print(f"  ✗ 未检测到足球")
                    print(f"  提示: 请确保足球在视野内，或调整距离")
                
                # 等待用户输入
                user_input = input("\n按回车继续，输入 'q' 退出: ").strip().lower()
                if user_input == 'q':
                    break
                    
            except KeyboardInterrupt:
                print("\n[校准] 用户中断")
                break
            except Exception as e:
                print(f"[校准] 异常: {e}")
                time.sleep(1)
        
        print(f"\n[校准] 测试结束，共采样 {test_count} 次\n")
    
    def close(self):
        """关闭连接，释放资源。"""
        try:
            self.robot.close()
        except Exception:
            pass
        self._initialized = False


def run_single_test():
    """运行单次足球识别测试。"""
    tester = SoccerTest()
    if tester.initialize():
        print("\n[单次测试] 开始检测...")
        result = tester.test_single_frame()
        if result:
            print(f"\n检测结果:")
            print(f"  位置: ({result['center_x']:.0f}, {result['center_y']:.0f})")
            print(f"  半径: {result['radius']:.0f} 像素")
            print(f"  面积占比: {result['area_ratio']:.3%}")
            print(f"  估算距离: {result['distance']:.2f} 米")
            print(f"  横向偏移: {result['lateral_offset']:.2f} 米")
        else:
            print("\n未检测到足球")
    tester.close()


def run_continuous_test(duration: float = 10.0):
    """运行连续足球识别测试。
    
    参数:
        duration: 测试持续时间（秒）
    """
    tester = SoccerTest()
    if tester.initialize():
        tester.test_continuous(duration=duration)
    tester.close()


def run_calibration_test():
    """运行距离校准测试。"""
    tester = SoccerTest()
    if tester.initialize():
        tester.test_distance_calibration()
    tester.close()


if __name__ == "__main__":
    import sys
    
    print("足球识别测试工具")
    print("=" * 40)
    print("1. 单次测试 - 检测一帧图像中的足球")
    print("2. 连续测试 - 持续检测10秒")
    print("3. 距离校准 - 测试不同距离下的识别效果")
    print("=" * 40)
    
    choice = input("请选择测试模式 (1/2/3): ").strip()
    
    if choice == "1":
        run_single_test()
    elif choice == "2":
        duration = input("请输入测试时长（秒，默认10）: ").strip()
        try:
            duration = float(duration) if duration else 10.0
        except ValueError:
            duration = 10.0
        run_continuous_test(duration)
    elif choice == "3":
        run_calibration_test()
    else:
        print("无效选择，运行单次测试")
        run_single_test()