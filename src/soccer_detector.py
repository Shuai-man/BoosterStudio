<<<<<<< HEAD
# coding: utf-8
"""足球检测模块 - 专门用于足球识别和距离计算。

核心策略：
1. 足球必须有黑色特征点（R<30, G<30, B<30，跳动30）
2. 足球必须有白色特征点（R>225, G>225, B>225，跳动30）
3. 远处足球白色部分会呈现灰色，但一定有黑色斑点
4. 必须用形状验证：只有确定是球形或椭球形才能判断为足球
5. 剔除误判：三脚架结构（灰色聚集）、场外阴影（连片黑色）、球门阴影
"""

import numpy as np
import cv2
from typing import Optional
from collections import deque

# 足球实际半径（米）- 标准5号足球半径约0.11m
SOCCER_REAL_RADIUS = 0.11  # 单位：米

# 颜色阈值（跳动30）
BLACK_THRESHOLD = 30  # R,G,B都低于此值为黑色
WHITE_THRESHOLD = 225  # R,G,B都高于此值为白色
GRAY_LOW = 60  # 灰色下限（远处足球白色部分）
GRAY_HIGH = 120  # 灰色上限
GRAY_DIFF = 25  # 灰色RGB最大差异

# 相机内参缓存
_camera_info_cache = None


class BallTracker:
    """足球跟踪器 - 使用时间滤波稳定检测结果。"""
    
    def __init__(self, history_size: int = 5, lost_threshold: int = 3):
        self._history = deque(maxlen=history_size)
        self._last_valid = None
        self._lost_frames = 0  # 连续丢失帧数
        self._lost_threshold = lost_threshold  # 连续丢失多少帧后才认为球真的消失了
    
    def update(self, detection: Optional[dict]) -> Optional[dict]:
        """更新跟踪器并返回滤波后的检测结果。"""
        if detection is None:
            self._lost_frames += 1
            # 连续多帧未检测到，才认为球真的消失了
            if self._lost_frames >= self._lost_threshold:
                self._history.clear()
                self._last_valid = None
                return None
            # 短暂丢失时返回缓存值，避免闪烁
            return self._last_valid
        
        # 检测到球，重置丢失计数器
        self._lost_frames = 0
        self._history.append(detection)
        
        if len(self._history) < 2:
            self._last_valid = detection
            return detection
        
        # 计算历史平均值
        avg_cx = sum(d["center_x"] for d in self._history) / len(self._history)
        avg_cy = sum(d["center_y"] for d in self._history) / len(self._history)
        avg_r = sum(d["radius"] for d in self._history) / len(self._history)
        avg_area = sum(d["area"] for d in self._history) / len(self._history)
        
        # 检查一致性
        cx_dev = abs(detection["center_x"] - avg_cx) / max(1, avg_cx)
        cy_dev = abs(detection["center_y"] - avg_cy) / max(1, avg_cy)
        r_dev = abs(detection["radius"] - avg_r) / max(1, avg_r)
        
        if cx_dev > 0.5 or cy_dev > 0.5 or r_dev > 0.5:
            filtered = {
                "center_x": avg_cx,
                "center_y": avg_cy,
                "radius": avg_r,
                "area_ratio": avg_area / (320 * 240),
                "area": avg_area,
                "filtered": True,
            }
            self._last_valid = filtered
            return filtered
        
        smoothed = {
            "center_x": avg_cx,
            "center_y": avg_cy,
            "radius": avg_r,
            "area_ratio": avg_area / (320 * 240),
            "area": avg_area,
            "filtered": False,
        }
        self._last_valid = smoothed
        return smoothed


def get_camera_focal_length(robot) -> tuple[float, float]:
    """获取相机焦距（像素单位）。"""
    global _camera_info_cache
    if _camera_info_cache is None:
        try:
            _camera_info_cache = robot.get_camera_info()
            fx = _camera_info_cache.k[0, 0]
            fy = _camera_info_cache.k[1, 1]
            return fx, fy
        except Exception as e:
            return 216.5, 216.5
    
    fx = _camera_info_cache.k[0, 0]
    fy = _camera_info_cache.k[1, 1]
    return fx, fy


def estimate_distance_from_radius(radius_px: float, fx: float) -> float:
    """通过足球在图像中的像素半径估算距离。"""
    if radius_px <= 0:
        return 10.0
    
    distance = (SOCCER_REAL_RADIUS * fx) / radius_px
    return max(0.1, min(5.0, distance))


def estimate_distance_from_y_position(center_y: float, img_height: int, fx: float) -> float:
    """通过足球在画面中的Y坐标估算距离。"""
    if img_height <= 0:
        return 5.0
    
    norm_y = center_y / img_height
    
    if norm_y <= 0.1:
        return 5.0
    
    distance = 2.0 / (norm_y - 0.075)
    return max(0.3, min(5.0, distance))


def estimate_distance_combined(radius_px: float, center_y: float, img_height: int, fx: float) -> float:
    """结合半径和Y坐标估算距离。"""
    radius_dist = estimate_distance_from_radius(radius_px, fx)
    y_dist = estimate_distance_from_y_position(center_y, img_height, fx)
    
    if radius_px >= 15:
        return radius_dist
    elif radius_px <= 5:
        return radius_dist * 0.3 + y_dist * 0.7
    else:
        weight = (radius_px - 5) / 10.0
        return radius_dist * weight + y_dist * (1 - weight)


def _is_black_pixel(r, g, b):
    """判断是否为黑色像素：R,G,B都低于BLACK_THRESHOLD。"""
    return r < BLACK_THRESHOLD and g < BLACK_THRESHOLD and b < BLACK_THRESHOLD


def _is_white_pixel(r, g, b):
    """判断是否为白色像素：R,G,B都高于WHITE_THRESHOLD。"""
    return r > WHITE_THRESHOLD and g > WHITE_THRESHOLD and b > WHITE_THRESHOLD


def _is_gray_pixel(r, g, b):
    """判断是否为灰色像素（远处足球的白色部分）。"""
    # 灰色范围：GRAY_LOW ~ GRAY_HIGH
    if r < GRAY_LOW or r > GRAY_HIGH:
        return False
    if g < GRAY_LOW or g > GRAY_HIGH:
        return False
    if b < GRAY_LOW or b > GRAY_HIGH:
        return False
    # RGB差异小
    if abs(int(r) - int(g)) > GRAY_DIFF:
        return False
    if abs(int(g) - int(b)) > GRAY_DIFF:
        return False
    if abs(int(r) - int(b)) > GRAY_DIFF:
        return False
    return True


def _is_green_pixel(r, g, b):
    """判断是否为绿色像素（草地）。"""
    return g > r + 20 and g > b + 20


def _is_blue_pixel(r, g, b):
    """判断是否为蓝色像素（天空）。"""
    return b > r + 20 and b > g + 15


def detect_soccer_ball_rgb(image_np: np.ndarray, logger=None) -> Optional[dict]:
    """基于RGB颜色的足球检测。
    
    核心策略：
    1. 黑色检测：R<30, G<30, B<30（必要条件）
    2. 白色检测：R>225, G>225, B>225
    3. 灰色检测：远处足球白色部分呈现灰色
    4. 形状验证：必须是圆形或椭圆形
    5. 剔除误判：三脚架、阴影等
    """
    h, w = image_np.shape[:2]
    img_area = h * w
    
    # 分离RGB通道
    R = image_np[:, :, 0]
    G = image_np[:, :, 1]
    B = image_np[:, :, 2]
    
    # ========== 步骤1: 检测黑色像素（必要条件）==========
    black_mask = ((R < BLACK_THRESHOLD) & 
                  (G < BLACK_THRESHOLD) & 
                  (B < BLACK_THRESHOLD)).astype(np.uint8) * 255
    
    black_px = np.count_nonzero(black_mask)
    
    # 如果没有黑色像素，直接返回（足球必须有黑色）
    if black_px < 3:
        if logger:
            logger.info(f"[Detect] No black pixels ({black_px}), NOT a soccer ball")
        return None
    
    # ========== 步骤2: 检测白色像素 ==========
    white_mask = ((R > WHITE_THRESHOLD) & 
                  (G > WHITE_THRESHOLD) & 
                  (B > WHITE_THRESHOLD)).astype(np.uint8) * 255
    white_px = np.count_nonzero(white_mask)
    
    # ========== 步骤3: 检测灰色像素（远处足球）==========
    gray_mask = np.zeros((h, w), dtype=np.uint8)
    for y in range(h):
        for x in range(w):
            if _is_gray_pixel(R[y, x], G[y, x], B[y, x]):
                # 排除绿色和蓝色调
                if not _is_green_pixel(R[y, x], G[y, x], B[y, x]) and \
                   not _is_blue_pixel(R[y, x], G[y, x], B[y, x]):
                    gray_mask[y, x] = 255
    gray_px = np.count_nonzero(gray_mask)
    
    if logger:
        logger.info(f"[Detect] Black={black_px}, White={white_px}, Gray={gray_px}")
    
    # ========== 步骤4: 排除线条状黑色（场地阴影）==========
    if black_px > 10:
        black_coords = np.argwhere(black_mask > 0)
        y_min, x_min = black_coords.min(axis=0)
        y_max, x_max = black_coords.max(axis=0)
        black_h = y_max - y_min + 1
        black_w = x_max - x_min + 1
        black_aspect = min(black_h, black_w) / max(1, max(black_h, black_w))
        
        # 线条状黑色像素 = 场地阴影
        if black_aspect < 0.15 and max(black_h, black_w) > 30:
            if logger:
                logger.info(f"[Detect] Black pixels are linear (aspect={black_aspect:.2f}), field shadow - rejected")
            return None
    
    # ========== 步骤5: 合并黑白灰掩码，找候选区域 ==========
    # 策略：黑色 + (白色 或 灰色) 的组合才是足球候选
    white_or_gray = cv2.bitwise_or(white_mask, gray_mask)
    
    # 膨胀白色/灰色区域
    kernel3 = np.ones((5, 5), np.uint8)
    wg_dilated = cv2.dilate(white_or_gray, kernel3, iterations=2)
    
    # 检查黑色是否在白色/灰色附近
    black_near_wg = cv2.bitwise_and(black_mask, wg_dilated)
    black_near_wg_px = np.count_nonzero(black_near_wg)
    
    # 必须有黑色靠近白色/灰色
    if black_near_wg_px < 2:
        if logger:
            logger.info(f"[Detect] No black near white/gray, NOT a soccer ball")
        return None
    
    # 合并掩码
    ball_mask = cv2.bitwise_or(black_mask, white_or_gray)
    
    # 形态学操作
    kernel2 = np.ones((3, 3), np.uint8)
    ball_mask = cv2.morphologyEx(ball_mask, cv2.MORPH_CLOSE, kernel2, iterations=2)
    ball_mask = cv2.morphologyEx(ball_mask, cv2.MORPH_OPEN, kernel2, iterations=1)
    
    total_px = np.count_nonzero(ball_mask)
    if total_px < 8:
        if logger:
            logger.info(f"[Detect] Too few ball pixels ({total_px}), rejected")
        return None
    
    # ========== 步骤6: 查找轮廓 ==========
    contours, _ = cv2.findContours(ball_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if logger:
        logger.info(f"[Detect] Contours: {len(contours)}")
    
    best_ball = None
    best_score = 0
    
    # 足球半径范围：3-30像素
    min_radius = 3
    max_radius = 30
    
    for i, contour in enumerate(contours):
        area = cv2.contourArea(contour)
        if area < 10:
            continue
        
        (cx, cy), radius = cv2.minEnclosingCircle(contour)
        cx, cy, radius = int(cx), int(cy), int(radius)
        
        # 半径检查
        if radius < min_radius or radius > max_radius:
            continue
        
        # 位置检查：足球在地面上，不能在画面最顶部
        if cy < 60:
            continue
        
        # ========== 形状验证：必须是圆形或椭圆形 ==========
        
        # 1. 圆形度
        perimeter = cv2.arcLength(contour, True)
        if perimeter > 0:
            circularity = 4 * np.pi * area / (perimeter * perimeter)
        else:
            circularity = 0
        
        # 2. 椭圆拟合
        if len(contour) >= 5:
            ellipse = cv2.fitEllipse(contour)
            ellipse_center, ellipse_axes, ellipse_angle = ellipse
            major_axis = max(ellipse_axes)
            minor_axis = min(ellipse_axes)
            ellipse_aspect = minor_axis / max(1, major_axis)
        else:
            ellipse_aspect = 0
        
        # 3. 紧凑度
        hull = cv2.convexHull(contour)
        hull_area = cv2.contourArea(hull)
        solidity = area / max(1, hull_area)
        
        # 4. 矩形度（排除矩形物体）
        x, y, bw, bh = cv2.boundingRect(contour)
        bounding_box_area = bw * bh
        rectangularity = area / max(1, bounding_box_area)
        
        # 5. 宽高比
        aspect_ratio = min(bw, bh) / max(1, max(bw, bh))
        
        # 形状验证：必须满足以下条件
        # 圆形度 > 0.4（足球应该是圆的）
        # 椭圆宽高比 > 0.4（不能太扁）
        # 紧凑度 > 0.6（不能太不规则）
        # 不能是明显矩形（矩形度 < 0.7 或 宽高比 > 0.4）
        
        if circularity < 0.4:
            if logger:
                logger.info(f"[Detect] Contour {i} rejected: low circularity ({circularity:.2f})")
            continue
        
        if ellipse_aspect < 0.4:
            if logger:
                logger.info(f"[Detect] Contour {i} rejected: low ellipse aspect ({ellipse_aspect:.2f})")
            continue
        
        if solidity < 0.6:
            if logger:
                logger.info(f"[Detect] Contour {i} rejected: low solidity ({solidity:.2f})")
            continue
        
        # 排除矩形物体（球门等）
        if rectangularity > 0.7 and aspect_ratio < 0.4:
            if logger:
                logger.info(f"[Detect] Contour {i} rejected: rectangular shape")
            continue
        
        # 排除线条状物体（场地线、阴影）
        if aspect_ratio < 0.2:
            if logger:
                logger.info(f"[Detect] Contour {i} rejected: linear shape")
            continue
        
        # ========== 颜色验证 ==========
        roi_mask = np.zeros((h, w), dtype=np.uint8)
        cv2.drawContours(roi_mask, [contour], -1, 255, -1)
        
        black_in_roi = np.count_nonzero(black_mask & roi_mask)
        white_in_roi = np.count_nonzero(white_mask & roi_mask)
        gray_in_roi = np.count_nonzero(gray_mask & roi_mask)
        
        # 足球必须有黑色像素
        if black_in_roi < 2:
            if logger:
                logger.info(f"[Detect] Contour {i} rejected: no black pixels in ROI")
            continue
        
        # 足球必须有白色或灰色像素
        if white_in_roi < 3 and gray_in_roi < 3:
            if logger:
                logger.info(f"[Detect] Contour {i} rejected: no white/gray pixels in ROI")
            continue
        
        # 排除纯黑色区域（阴影）
        black_ratio = black_in_roi / max(1, area)
        if black_ratio > 0.8:
            if logger:
                logger.info(f"[Detect] Contour {i} rejected: too black ({black_ratio:.2f}), likely shadow")
            continue
        
        # 排除纯白色区域（场地线）
        white_ratio = white_in_roi / max(1, area)
        if white_ratio > 0.8:
            if logger:
                logger.info(f"[Detect] Contour {i} rejected: too white ({white_ratio:.2f}), likely field line")
            continue
        
        # 排除纯灰色区域（三脚架结构）
        gray_ratio = gray_in_roi / max(1, area)
        if gray_ratio > 0.7 and black_ratio < 0.05:
            if logger:
                logger.info(f"[Detect] Contour {i} rejected: too gray without black, likely tripod")
            continue
        
        # ========== 评分 ==========
        # 形状评分
        shape_score = (circularity * 0.35 + 
                       ellipse_aspect * 0.20 + 
                       solidity * 0.15)
        
        # 颜色评分：理想情况黑色10-30%，白色/灰色30-60%
        ideal_black = 0.10 <= black_ratio <= 0.35
        ideal_white_gray = 0.20 <= (white_ratio + gray_ratio) <= 0.70
        
        if ideal_black and ideal_white_gray:
            color_score = 1.0
        elif black_ratio >= 0.05:
            color_score = 0.6
        else:
            color_score = 0.2
        
        # 位置评分：足球在地面上
        norm_y = cy / h
        if 0.4 <= norm_y <= 0.9:
            position_score = 1.0
        elif norm_y > 0.9:
            position_score = 0.5
        else:
            position_score = 0.6
        
        # 大小评分
        if 5 <= radius <= 20:
            size_score = 1.0
        elif radius < 5:
            size_score = radius / 5.0
        else:
            size_score = 1.0 - (radius - 20) / 10.0
        size_score = max(0.0, min(1.0, size_score))
        
        # 综合评分
        score = (shape_score * 0.40 + 
                 color_score * 0.25 + 
                 position_score * 0.20 + 
                 size_score * 0.15)
        
        if logger:
            logger.info(f"[Detect] #{i}: circ={circularity:.2f}, ell={ellipse_aspect:.2f}, "
                       f"sol={solidity:.2f}, b={black_ratio:.2f}, w={white_ratio:.2f}, "
                       f"g={gray_ratio:.2f}, score={score:.2f}")
        
        if score > best_score:
            best_score = score
            best_ball = {
                "center_x": float(cx),
                "center_y": float(cy),
                "radius": float(radius),
                "area_ratio": float(area / img_area),
                "area": float(area),
            }
    
    # 最终验证
    MIN_SCORE = 0.40
    
    if best_ball is not None and best_score < MIN_SCORE:
        if logger:
            logger.info(f"[Detect] Best score {best_score:.2f} < threshold {MIN_SCORE}, rejected")
        best_ball = None
    
    if best_ball:
        if logger:
            logger.info(f"[Detect] BALL FOUND: ({best_ball['center_x']:.0f}, {best_ball['center_y']:.0f}), "
                       f"r={best_ball['radius']:.0f}, score={best_score:.2f}")
        return best_ball
    
    if logger:
        logger.info("[Detect] No ball detected")
    
=======
# coding: utf-8
"""足球检测模块 - 专门用于足球识别和距离计算。

核心策略：
1. 足球必须有黑色特征点（R<30, G<30, B<30，跳动30）
2. 足球必须有白色特征点（R>225, G>225, B>225，跳动30）
3. 远处足球白色部分会呈现灰色，但一定有黑色斑点
4. 必须用形状验证：只有确定是球形或椭球形才能判断为足球
5. 剔除误判：三脚架结构（灰色聚集）、场外阴影（连片黑色）、球门阴影
"""

import numpy as np
import cv2
from typing import Optional
from collections import deque

# 足球实际半径（米）- 标准5号足球半径约0.11m
SOCCER_REAL_RADIUS = 0.11  # 单位：米

# 颜色阈值（跳动30）
BLACK_THRESHOLD = 30  # R,G,B都低于此值为黑色
WHITE_THRESHOLD = 225  # R,G,B都高于此值为白色
GRAY_LOW = 60  # 灰色下限（远处足球白色部分）
GRAY_HIGH = 120  # 灰色上限
GRAY_DIFF = 25  # 灰色RGB最大差异

# 相机内参缓存
_camera_info_cache = None


class BallTracker:
    """足球跟踪器 - 使用时间滤波稳定检测结果。"""
    
    def __init__(self, history_size: int = 5, lost_threshold: int = 3):
        self._history = deque(maxlen=history_size)
        self._last_valid = None
        self._lost_frames = 0  # 连续丢失帧数
        self._lost_threshold = lost_threshold  # 连续丢失多少帧后才认为球真的消失了
    
    def update(self, detection: Optional[dict]) -> Optional[dict]:
        """更新跟踪器并返回滤波后的检测结果。"""
        if detection is None:
            self._lost_frames += 1
            # 连续多帧未检测到，才认为球真的消失了
            if self._lost_frames >= self._lost_threshold:
                self._history.clear()
                self._last_valid = None
                return None
            # 短暂丢失时返回缓存值，避免闪烁
            return self._last_valid
        
        # 检测到球，重置丢失计数器
        self._lost_frames = 0
        self._history.append(detection)
        
        if len(self._history) < 2:
            self._last_valid = detection
            return detection
        
        # 计算历史平均值
        avg_cx = sum(d["center_x"] for d in self._history) / len(self._history)
        avg_cy = sum(d["center_y"] for d in self._history) / len(self._history)
        avg_r = sum(d["radius"] for d in self._history) / len(self._history)
        avg_area = sum(d["area"] for d in self._history) / len(self._history)
        
        # 检查一致性
        cx_dev = abs(detection["center_x"] - avg_cx) / max(1, avg_cx)
        cy_dev = abs(detection["center_y"] - avg_cy) / max(1, avg_cy)
        r_dev = abs(detection["radius"] - avg_r) / max(1, avg_r)
        
        if cx_dev > 0.5 or cy_dev > 0.5 or r_dev > 0.5:
            filtered = {
                "center_x": avg_cx,
                "center_y": avg_cy,
                "radius": avg_r,
                "area_ratio": avg_area / (320 * 240),
                "area": avg_area,
                "filtered": True,
            }
            self._last_valid = filtered
            return filtered
        
        smoothed = {
            "center_x": avg_cx,
            "center_y": avg_cy,
            "radius": avg_r,
            "area_ratio": avg_area / (320 * 240),
            "area": avg_area,
            "filtered": False,
        }
        self._last_valid = smoothed
        return smoothed


def get_camera_focal_length(robot) -> tuple[float, float]:
    """获取相机焦距（像素单位）。"""
    global _camera_info_cache
    if _camera_info_cache is None:
        try:
            _camera_info_cache = robot.get_camera_info()
            fx = _camera_info_cache.k[0, 0]
            fy = _camera_info_cache.k[1, 1]
            return fx, fy
        except Exception as e:
            return 216.5, 216.5
    
    fx = _camera_info_cache.k[0, 0]
    fy = _camera_info_cache.k[1, 1]
    return fx, fy


def estimate_distance_from_radius(radius_px: float, fx: float) -> float:
    """通过足球在图像中的像素半径估算距离。"""
    if radius_px <= 0:
        return 10.0
    
    distance = (SOCCER_REAL_RADIUS * fx) / radius_px
    return max(0.1, min(5.0, distance))


def estimate_distance_from_y_position(center_y: float, img_height: int, fx: float) -> float:
    """通过足球在画面中的Y坐标估算距离。"""
    if img_height <= 0:
        return 5.0
    
    norm_y = center_y / img_height
    
    if norm_y <= 0.1:
        return 5.0
    
    distance = 2.0 / (norm_y - 0.075)
    return max(0.3, min(5.0, distance))


def estimate_distance_combined(radius_px: float, center_y: float, img_height: int, fx: float) -> float:
    """结合半径和Y坐标估算距离。"""
    radius_dist = estimate_distance_from_radius(radius_px, fx)
    y_dist = estimate_distance_from_y_position(center_y, img_height, fx)
    
    if radius_px >= 15:
        return radius_dist
    elif radius_px <= 5:
        return radius_dist * 0.3 + y_dist * 0.7
    else:
        weight = (radius_px - 5) / 10.0
        return radius_dist * weight + y_dist * (1 - weight)


def _is_black_pixel(r, g, b):
    """判断是否为黑色像素：R,G,B都低于BLACK_THRESHOLD。"""
    return r < BLACK_THRESHOLD and g < BLACK_THRESHOLD and b < BLACK_THRESHOLD


def _is_white_pixel(r, g, b):
    """判断是否为白色像素：R,G,B都高于WHITE_THRESHOLD。"""
    return r > WHITE_THRESHOLD and g > WHITE_THRESHOLD and b > WHITE_THRESHOLD


def _is_gray_pixel(r, g, b):
    """判断是否为灰色像素（远处足球的白色部分）。"""
    # 灰色范围：GRAY_LOW ~ GRAY_HIGH
    if r < GRAY_LOW or r > GRAY_HIGH:
        return False
    if g < GRAY_LOW or g > GRAY_HIGH:
        return False
    if b < GRAY_LOW or b > GRAY_HIGH:
        return False
    # RGB差异小
    if abs(int(r) - int(g)) > GRAY_DIFF:
        return False
    if abs(int(g) - int(b)) > GRAY_DIFF:
        return False
    if abs(int(r) - int(b)) > GRAY_DIFF:
        return False
    return True


def _is_green_pixel(r, g, b):
    """判断是否为绿色像素（草地）。"""
    return g > r + 20 and g > b + 20


def _is_blue_pixel(r, g, b):
    """判断是否为蓝色像素（天空）。"""
    return b > r + 20 and b > g + 15


def detect_soccer_ball_rgb(image_np: np.ndarray, logger=None) -> Optional[dict]:
    """基于RGB颜色的足球检测。
    
    核心策略：
    1. 黑色检测：R<30, G<30, B<30（必要条件）
    2. 白色检测：R>225, G>225, B>225
    3. 灰色检测：远处足球白色部分呈现灰色
    4. 形状验证：必须是圆形或椭圆形
    5. 剔除误判：三脚架、阴影等
    """
    h, w = image_np.shape[:2]
    img_area = h * w
    
    # 分离RGB通道
    R = image_np[:, :, 0]
    G = image_np[:, :, 1]
    B = image_np[:, :, 2]
    
    # ========== 步骤1: 检测黑色像素（必要条件）==========
    black_mask = ((R < BLACK_THRESHOLD) & 
                  (G < BLACK_THRESHOLD) & 
                  (B < BLACK_THRESHOLD)).astype(np.uint8) * 255
    
    black_px = np.count_nonzero(black_mask)
    
    # 如果没有黑色像素，直接返回（足球必须有黑色）
    if black_px < 3:
        if logger:
            logger.info(f"[Detect] No black pixels ({black_px}), NOT a soccer ball")
        return None
    
    # ========== 步骤2: 检测白色像素 ==========
    white_mask = ((R > WHITE_THRESHOLD) & 
                  (G > WHITE_THRESHOLD) & 
                  (B > WHITE_THRESHOLD)).astype(np.uint8) * 255
    white_px = np.count_nonzero(white_mask)
    
    # ========== 步骤3: 检测灰色像素（远处足球）==========
    gray_mask = np.zeros((h, w), dtype=np.uint8)
    for y in range(h):
        for x in range(w):
            if _is_gray_pixel(R[y, x], G[y, x], B[y, x]):
                # 排除绿色和蓝色调
                if not _is_green_pixel(R[y, x], G[y, x], B[y, x]) and \
                   not _is_blue_pixel(R[y, x], G[y, x], B[y, x]):
                    gray_mask[y, x] = 255
    gray_px = np.count_nonzero(gray_mask)
    
    if logger:
        logger.info(f"[Detect] Black={black_px}, White={white_px}, Gray={gray_px}")
    
    # ========== 步骤4: 排除线条状黑色（场地阴影）==========
    if black_px > 10:
        black_coords = np.argwhere(black_mask > 0)
        y_min, x_min = black_coords.min(axis=0)
        y_max, x_max = black_coords.max(axis=0)
        black_h = y_max - y_min + 1
        black_w = x_max - x_min + 1
        black_aspect = min(black_h, black_w) / max(1, max(black_h, black_w))
        
        # 线条状黑色像素 = 场地阴影
        if black_aspect < 0.15 and max(black_h, black_w) > 30:
            if logger:
                logger.info(f"[Detect] Black pixels are linear (aspect={black_aspect:.2f}), field shadow - rejected")
            return None
    
    # ========== 步骤5: 合并黑白灰掩码，找候选区域 ==========
    # 策略：黑色 + (白色 或 灰色) 的组合才是足球候选
    white_or_gray = cv2.bitwise_or(white_mask, gray_mask)
    
    # 膨胀白色/灰色区域
    kernel3 = np.ones((5, 5), np.uint8)
    wg_dilated = cv2.dilate(white_or_gray, kernel3, iterations=2)
    
    # 检查黑色是否在白色/灰色附近
    black_near_wg = cv2.bitwise_and(black_mask, wg_dilated)
    black_near_wg_px = np.count_nonzero(black_near_wg)
    
    # 必须有黑色靠近白色/灰色
    if black_near_wg_px < 2:
        if logger:
            logger.info(f"[Detect] No black near white/gray, NOT a soccer ball")
        return None
    
    # 合并掩码
    ball_mask = cv2.bitwise_or(black_mask, white_or_gray)
    
    # 形态学操作
    kernel2 = np.ones((3, 3), np.uint8)
    ball_mask = cv2.morphologyEx(ball_mask, cv2.MORPH_CLOSE, kernel2, iterations=2)
    ball_mask = cv2.morphologyEx(ball_mask, cv2.MORPH_OPEN, kernel2, iterations=1)
    
    total_px = np.count_nonzero(ball_mask)
    if total_px < 8:
        if logger:
            logger.info(f"[Detect] Too few ball pixels ({total_px}), rejected")
        return None
    
    # ========== 步骤6: 查找轮廓 ==========
    contours, _ = cv2.findContours(ball_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if logger:
        logger.info(f"[Detect] Contours: {len(contours)}")
    
    best_ball = None
    best_score = 0
    
    # 足球半径范围：3-30像素
    min_radius = 3
    max_radius = 30
    
    for i, contour in enumerate(contours):
        area = cv2.contourArea(contour)
        if area < 10:
            continue
        
        (cx, cy), radius = cv2.minEnclosingCircle(contour)
        cx, cy, radius = int(cx), int(cy), int(radius)
        
        # 半径检查
        if radius < min_radius or radius > max_radius:
            continue
        
        # 位置检查：足球在地面上，不能在画面最顶部
        if cy < 60:
            continue
        
        # ========== 形状验证：必须是圆形或椭圆形 ==========
        
        # 1. 圆形度
        perimeter = cv2.arcLength(contour, True)
        if perimeter > 0:
            circularity = 4 * np.pi * area / (perimeter * perimeter)
        else:
            circularity = 0
        
        # 2. 椭圆拟合
        if len(contour) >= 5:
            ellipse = cv2.fitEllipse(contour)
            ellipse_center, ellipse_axes, ellipse_angle = ellipse
            major_axis = max(ellipse_axes)
            minor_axis = min(ellipse_axes)
            ellipse_aspect = minor_axis / max(1, major_axis)
        else:
            ellipse_aspect = 0
        
        # 3. 紧凑度
        hull = cv2.convexHull(contour)
        hull_area = cv2.contourArea(hull)
        solidity = area / max(1, hull_area)
        
        # 4. 矩形度（排除矩形物体）
        x, y, bw, bh = cv2.boundingRect(contour)
        bounding_box_area = bw * bh
        rectangularity = area / max(1, bounding_box_area)
        
        # 5. 宽高比
        aspect_ratio = min(bw, bh) / max(1, max(bw, bh))
        
        # 形状验证：必须满足以下条件
        # 圆形度 > 0.4（足球应该是圆的）
        # 椭圆宽高比 > 0.4（不能太扁）
        # 紧凑度 > 0.6（不能太不规则）
        # 不能是明显矩形（矩形度 < 0.7 或 宽高比 > 0.4）
        
        if circularity < 0.4:
            if logger:
                logger.info(f"[Detect] Contour {i} rejected: low circularity ({circularity:.2f})")
            continue
        
        if ellipse_aspect < 0.4:
            if logger:
                logger.info(f"[Detect] Contour {i} rejected: low ellipse aspect ({ellipse_aspect:.2f})")
            continue
        
        if solidity < 0.6:
            if logger:
                logger.info(f"[Detect] Contour {i} rejected: low solidity ({solidity:.2f})")
            continue
        
        # 排除矩形物体（球门等）
        if rectangularity > 0.7 and aspect_ratio < 0.4:
            if logger:
                logger.info(f"[Detect] Contour {i} rejected: rectangular shape")
            continue
        
        # 排除线条状物体（场地线、阴影）
        if aspect_ratio < 0.2:
            if logger:
                logger.info(f"[Detect] Contour {i} rejected: linear shape")
            continue
        
        # ========== 颜色验证 ==========
        roi_mask = np.zeros((h, w), dtype=np.uint8)
        cv2.drawContours(roi_mask, [contour], -1, 255, -1)
        
        black_in_roi = np.count_nonzero(black_mask & roi_mask)
        white_in_roi = np.count_nonzero(white_mask & roi_mask)
        gray_in_roi = np.count_nonzero(gray_mask & roi_mask)
        
        # 足球必须有黑色像素
        if black_in_roi < 2:
            if logger:
                logger.info(f"[Detect] Contour {i} rejected: no black pixels in ROI")
            continue
        
        # 足球必须有白色或灰色像素
        if white_in_roi < 3 and gray_in_roi < 3:
            if logger:
                logger.info(f"[Detect] Contour {i} rejected: no white/gray pixels in ROI")
            continue
        
        # 排除纯黑色区域（阴影）
        black_ratio = black_in_roi / max(1, area)
        if black_ratio > 0.8:
            if logger:
                logger.info(f"[Detect] Contour {i} rejected: too black ({black_ratio:.2f}), likely shadow")
            continue
        
        # 排除纯白色区域（场地线）
        white_ratio = white_in_roi / max(1, area)
        if white_ratio > 0.8:
            if logger:
                logger.info(f"[Detect] Contour {i} rejected: too white ({white_ratio:.2f}), likely field line")
            continue
        
        # 排除纯灰色区域（三脚架结构）
        gray_ratio = gray_in_roi / max(1, area)
        if gray_ratio > 0.7 and black_ratio < 0.05:
            if logger:
                logger.info(f"[Detect] Contour {i} rejected: too gray without black, likely tripod")
            continue
        
        # ========== 评分 ==========
        # 形状评分
        shape_score = (circularity * 0.35 + 
                       ellipse_aspect * 0.20 + 
                       solidity * 0.15)
        
        # 颜色评分：理想情况黑色10-30%，白色/灰色30-60%
        ideal_black = 0.10 <= black_ratio <= 0.35
        ideal_white_gray = 0.20 <= (white_ratio + gray_ratio) <= 0.70
        
        if ideal_black and ideal_white_gray:
            color_score = 1.0
        elif black_ratio >= 0.05:
            color_score = 0.6
        else:
            color_score = 0.2
        
        # 位置评分：足球在地面上
        norm_y = cy / h
        if 0.4 <= norm_y <= 0.9:
            position_score = 1.0
        elif norm_y > 0.9:
            position_score = 0.5
        else:
            position_score = 0.6
        
        # 大小评分
        if 5 <= radius <= 20:
            size_score = 1.0
        elif radius < 5:
            size_score = radius / 5.0
        else:
            size_score = 1.0 - (radius - 20) / 10.0
        size_score = max(0.0, min(1.0, size_score))
        
        # 综合评分
        score = (shape_score * 0.40 + 
                 color_score * 0.25 + 
                 position_score * 0.20 + 
                 size_score * 0.15)
        
        if logger:
            logger.info(f"[Detect] #{i}: circ={circularity:.2f}, ell={ellipse_aspect:.2f}, "
                       f"sol={solidity:.2f}, b={black_ratio:.2f}, w={white_ratio:.2f}, "
                       f"g={gray_ratio:.2f}, score={score:.2f}")
        
        if score > best_score:
            best_score = score
            best_ball = {
                "center_x": float(cx),
                "center_y": float(cy),
                "radius": float(radius),
                "area_ratio": float(area / img_area),
                "area": float(area),
            }
    
    # 最终验证
    MIN_SCORE = 0.40
    
    if best_ball is not None and best_score < MIN_SCORE:
        if logger:
            logger.info(f"[Detect] Best score {best_score:.2f} < threshold {MIN_SCORE}, rejected")
        best_ball = None
    
    if best_ball:
        if logger:
            logger.info(f"[Detect] BALL FOUND: ({best_ball['center_x']:.0f}, {best_ball['center_y']:.0f}), "
                       f"r={best_ball['radius']:.0f}, score={best_score:.2f}")
        return best_ball
    
    if logger:
        logger.info("[Detect] No ball detected")
    
>>>>>>> b5ca688 (首次完成较为准确的足球识别)
    return None