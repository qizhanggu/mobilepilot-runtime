"""
多策略输出解析器

将大模型的原始输出解析为标准 (action, parameters) 格式。
采用3层降级策略，确保程序不崩溃，最终兜底返回 COMPLETE。
"""

import json
import re
import logging
from typing import Tuple, Dict, Any, Optional

logger = logging.getLogger(__name__)

# 合法动作集合
VALID_ACTIONS = {"CLICK", "TYPE", "SCROLL", "OPEN", "COMPLETE"}


class OutputParser:
    """多策略输出解析器"""

    def parse(self, raw_text: str) -> Tuple[str, Dict[str, Any]]:
        """
        解析模型原始输出为 (action, parameters)

        按3层策略依次尝试：
        1. 标准格式解析：Action: CLICK | {"point": [x, y]}
        2. 基类格式解析：click(point='<point>x y</point>')
        3. 兜底：返回 COMPLETE | {}

        Args:
            raw_text: 模型原始输出文本

        Returns:
            (action, parameters) 元组
        """
        if not raw_text or not raw_text.strip():
            logger.warning("[Parser] 空输出，返回 COMPLETE 兜底")
            return "COMPLETE", {}

        text = raw_text.strip()

        # 策略1：标准格式解析
        result = self._strategy_standard_format(text)
        if result:
            return result

        # 策略2：基类格式解析
        result = self._strategy_base_class_format(text)
        if result:
            return result

        # 策略3：兜底 COMPLETE
        logger.warning(f"[Parser] 所有策略解析失败，返回 COMPLETE 兜底。原始输出: {text[:200]}")
        return "COMPLETE", {}

    # ==========================================
    #       策略1：标准格式解析
    # ==========================================

    def _strategy_standard_format(self, text: str) -> Optional[Tuple[str, Dict[str, Any]]]:
        """
        解析标准格式：Action: CLICK | {"point": [x, y]}
        也兼容：Action: CLICK|{"point": [x, y]}
        """
        # 匹配 Action: ACTION_TYPE | {json}
        pattern = r'Action:\s*(CLICK|TYPE|SCROLL|OPEN|COMPLETE)\s*\|\s*(\{.*?\})'
        match = re.search(pattern, text, re.DOTALL)
        if not match:
            # 尝试不带 "Action:" 前缀的格式
            pattern2 = r'(CLICK|TYPE|SCROLL|OPEN|COMPLETE)\s*\|\s*(\{.*?\})'
            match = re.search(pattern2, text, re.DOTALL)

        if not match:
            return None

        action = match.group(1).upper()
        json_str = match.group(2)

        # 尝试解析 JSON
        params = self._parse_json_with_repair(json_str)
        if params is not None:
            params = self._validate_and_fix_params(action, params)
            if self._is_valid_output(action, params):
                return action, params

        return None

    # ==========================================
    #       策略2：基类格式解析
    # ==========================================

    def _strategy_base_class_format(self, text: str) -> Optional[Tuple[str, Dict[str, Any]]]:
        """
        解析基类格式：click(point='<point>x y</point>')
        以及 TYPE(content='xxx'), scroll(start_point='<point>x1 y1</point>', end_point='<point>x2 y2</point>')
        open(app_name='xxx'), complete(content='xxx')
        """
        # 匹配 click(...)
        click_match = re.search(
            r"click\s*\(\s*point\s*=\s*['\"]<point>\s*(\d+)\s+(\d+)\s*</point>['\"]\s*\)",
            text, re.IGNORECASE
        )
        if click_match:
            x, y = int(click_match.group(1)), int(click_match.group(2))
            return "CLICK", self._validate_and_fix_params("CLICK", {"point": [x, y]})

        # 匹配 type(content='xxx')
        type_match = re.search(
            r"type\s*\(\s*content\s*=\s*['\"](.+?)['\"]\s*\)",
            text, re.IGNORECASE
        )
        if type_match:
            content = type_match.group(1)
            return "TYPE", {"text": content}

        # 匹配 scroll(start_point='<point>x1 y1</point>', end_point='<point>x2 y2</point>')
        scroll_match = re.search(
            r"scroll\s*\(\s*start_point\s*=\s*['\"]<point>\s*(\d+)\s+(\d+)\s*</point>['\"]\s*,\s*"
            r"end_point\s*=\s*['\"]<point>\s*(\d+)\s+(\d+)\s*</point>['\"]\s*\)",
            text, re.IGNORECASE
        )
        if scroll_match:
            sx, sy = int(scroll_match.group(1)), int(scroll_match.group(2))
            ex, ey = int(scroll_match.group(3)), int(scroll_match.group(4))
            return "SCROLL", self._validate_and_fix_params(
                "SCROLL", {"start_point": [sx, sy], "end_point": [ex, ey]}
            )

        # 匹配 open(app_name='xxx')
        open_match = re.search(
            r"open\s*\(\s*app_name\s*=\s*['\"](.+?)['\"]\s*\)",
            text, re.IGNORECASE
        )
        if open_match:
            app_name = open_match.group(1)
            return "OPEN", {"app_name": app_name}

        # 匹配 complete(content='xxx') 或 complete()
        complete_match = re.search(
            r"complete\s*\(.*?\)",
            text, re.IGNORECASE
        )
        if complete_match:
            return "COMPLETE", {}

        return None

    # ==========================================
    #       JSON 工具方法
    # ==========================================

    def _parse_json_with_repair(self, json_str: str) -> Optional[Dict[str, Any]]:
        """
        尝试解析 JSON，失败时尝试修复常见问题
        """
        # 直接解析
        try:
            result = json.loads(json_str)
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

        # 修复尝试1：单引号替换为双引号
        try:
            fixed = json_str.replace("'", '"')
            result = json.loads(fixed)
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

        # 修复尝试2：补全缺失的闭合括号
        try:
            fixed = json_str
            open_braces = fixed.count('{') - fixed.count('}')
            open_brackets = fixed.count('[') - fixed.count(']')
            if open_braces > 0:
                fixed += '}' * open_braces
            if open_brackets > 0:
                fixed += ']' * open_brackets
            result = json.loads(fixed)
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

        # 修复尝试3：移除尾逗号
        try:
            fixed = re.sub(r',\s*([}\]])', r'\1', json_str)
            result = json.loads(fixed)
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

        # 修复尝试4：提取第一个完整的 JSON 对象
        try:
            depth = 0
            start = -1
            for i, ch in enumerate(json_str):
                if ch == '{':
                    if depth == 0:
                        start = i
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0 and start >= 0:
                        candidate = json_str[start:i + 1]
                        result = json.loads(candidate)
                        if isinstance(result, dict):
                            return result
        except (json.JSONDecodeError, ValueError):
            pass

        return None

    # ==========================================
    #       验证与修复方法
    # ==========================================

    def _validate_and_fix_params(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        验证并修复参数，确保坐标在 [0, 1000] 范围内
        """
        if action == "CLICK":
            point = params.get("point")
            if point and isinstance(point, list) and len(point) == 2:
                params["point"] = [
                    self._clamp_coord(point[0]),
                    self._clamp_coord(point[1])
                ]
            elif not point:
                # 尝试从其他 key 提取坐标
                for key in ["x", "coord", "position"]:
                    if key in params:
                        val = params[key]
                        if isinstance(val, list) and len(val) == 2:
                            params["point"] = [self._clamp_coord(val[0]), self._clamp_coord(val[1])]
                            break
                # 最后兜底
                if "point" not in params:
                    params["point"] = [500, 500]

        elif action == "SCROLL":
            for key in ["start_point", "end_point"]:
                pt = params.get(key)
                if pt and isinstance(pt, list) and len(pt) == 2:
                    params[key] = [self._clamp_coord(pt[0]), self._clamp_coord(pt[1])]
                elif not pt:
                    if key == "start_point":
                        params[key] = [500, 500]
                    else:
                        params[key] = [500, 700]

        elif action == "TYPE":
            if "text" not in params:
                # 尝试从 content 或 value 提取
                for key in ["content", "value", "query"]:
                    if key in params:
                        params["text"] = str(params[key])
                        break
                if "text" not in params:
                    params["text"] = ""

        elif action == "OPEN":
            if "app_name" not in params:
                for key in ["app", "name", "application"]:
                    if key in params:
                        params["app_name"] = str(params[key])
                        break
                if "app_name" not in params:
                    params["app_name"] = ""

        elif action == "COMPLETE":
            params = {}

        return params

    def _clamp_coord(self, value) -> int:
        """
        将坐标钳位到 [0, 1000] 范围
        如果值看起来是像素坐标（>1000），尝试转换
        """
        try:
            val = int(float(value))
        except (ValueError, TypeError):
            return 500

        # 如果值明显超出归一化范围，尝试从像素空间转换
        # 常见手机分辨率宽度约 480-1440，高度约 800-3200
        if val > 1000:
            # 可能是像素坐标，按 1080 为基准转换（常见宽度）
            # 保守处理：不转换，直接钳位到 999
            val = 999

        return max(0, min(1000, val))

    def _is_valid_output(self, action: str, params: Dict[str, Any]) -> bool:
        """
        检查解析结果是否有效
        """
        if action not in VALID_ACTIONS:
            return False

        if action == "CLICK":
            point = params.get("point")
            return isinstance(point, list) and len(point) == 2

        if action == "SCROLL":
            sp = params.get("start_point")
            ep = params.get("end_point")
            return (isinstance(sp, list) and len(sp) == 2 and
                    isinstance(ep, list) and len(ep) == 2)

        if action == "TYPE":
            return "text" in params and isinstance(params["text"], str)

        if action == "OPEN":
            return "app_name" in params and isinstance(params["app_name"], str)

        if action == "COMPLETE":
            return True

        return False
