"""
GUI Agent 实现

继承 BaseAgent，实现 act() 方法。
基于多模态大模型（doubao-seed-1-6-vision-250815）分析手机截图，
输出下一步操作动作和参数。

核心策略：
- 单轮对话架构：每步只发当前截图 + 文本历史
- PNG 无损传输：给模型最清晰的图像，不因压缩丢失细节
- 中文系统提示：适配豆包模型中文优势
- 三条强制业务规则：TYPE前必CLICK、TYPE后必CLICK搜索、坐标指向元素正中心
- 多策略输出解析：3层 fallback 确保程序不崩溃
"""

import io
import os
import re
import json
import base64
import logging
from typing import Dict, Any, List, Optional, Tuple

from PIL import Image, ImageDraw

# 抑制 httpx 的 HTTP Request 日志噪声（基类使用 httpx）
logging.getLogger("httpx").setLevel(logging.WARNING)

from agent_base import (
    BaseAgent, AgentInput, AgentOutput, UsageInfo,
    ACTION_CLICK, ACTION_TYPE, ACTION_SCROLL, ACTION_OPEN, ACTION_COMPLETE
)
from utils.output_parser import OutputParser

logger = logging.getLogger(__name__)


# ==========================================
#       应用名规范化映射
# ==========================================

APP_NAME_MAP = {
    "美团": "美团",
    "美团外卖": "美团",
    "大众点评": "大众点评",
    "百度地图": "百度地图",
    "抖音": "抖音",
    "哔哩哔哩": "哔哩哔哩",
    "b站": "哔哩哔哩",
    "B站": "哔哩哔哩",
    "去哪儿": "去哪儿旅行",
    "去哪旅行": "去哪儿旅行",
    "去哪儿旅行": "去哪儿旅行",
    "爱奇艺": "爱奇艺",
    "喜马拉雅": "喜马拉雅",
    "快手": "快手",
    "腾讯视频": "腾讯视频",
    "芒果TV": "芒果TV",
    "芒果": "芒果TV",
    "淘宝": "淘宝",
    "京东": "京东",
    "拼多多": "拼多多",
    "铁路12306": "铁路12306",
    "12306": "铁路12306",
    "高德地图": "高德地图",
    "支付宝": "支付宝",
    "微信": "微信",
    "微博": "微博",
    "网易云音乐": "网易云音乐",
    "携程旅行": "携程旅行",
    "携程": "携程旅行",
    "飞猪旅行": "飞猪旅行",
    "飞猪": "飞猪旅行",
}


# ==========================================
#       系统提示（从文件动态加载）
# ==========================================

def _load_prompt() -> str:
    """加载通用 Prompt（prompt_general.txt）"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    general_path = os.path.join(current_dir, "utils", "prompt_general.txt")
    if os.path.exists(general_path):
        with open(general_path, "r", encoding="utf-8") as f:
            return f.read().strip()
    logger.warning("[Prompt] 未找到通用Prompt文件，使用兜底Prompt")
    return "你是安卓手机GUI自动化专家，分析截图输出下一步操作。"


SYSTEM_PROMPT = _load_prompt()


class Agent(BaseAgent):
    """GUI Agent 实现"""

    _MODEL_ID = "doubao-seed-1-6-vision-250815"

    def _initialize(self):
        """初始化 Agent"""
        self._parser = OutputParser()
        self._step_history = []
        self._step_thoughts = []  # 存储过去3步的Thought精简版
        self._instruction_info = {}

        logger.info(f"[Agent] 初始化完成 | Model: {self._MODEL_ID}")

    def reset(self):
        """重置 Agent 状态（每个测试用例开始前调用）"""
        self._step_history = []
        self._step_thoughts = []
        self._instruction_info = {}

    def _call_api(self, messages: List[Dict[str, Any]], **kwargs):
        """使用基类的 _call_api（云端测试必须用这个）"""
        return super()._call_api(messages)

    # ==========================================
    #       图片预处理（网格辅助线）
    # ==========================================

    def _preprocess_image(self, image: Image.Image) -> Image.Image:
        """
        在截图上绘制10x10半透明网格，辅助大模型定位

        设计原则：
        1. 网格线按图片宽高的百分比（10%~90%）绘制，完美对应归一化坐标100~900
        2. 使用RGBA半透明线（约35%透明度），不遮挡UI元素
        3. 动态线宽：根据分辨率自适应，防止线太细或太粗
        4. 网格交叉点画小十字准星，增强定位感
        5. 不写文字刻度，避免引入.ttf字体文件（会撑爆20MB限制）
        6. 在System Prompt中告知模型网格含义，让模型"数格子"定位

        Args:
            image: 原始截图

        Returns:
            绘制了网格的截图（RGB模式，兼容PNG编码）
        """
        if image.mode != 'RGBA':
            image = image.convert('RGBA')

        width, height = image.size

        overlay = Image.new('RGBA', image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        grid_color = (0, 180, 255, 90)
        line_width = max(2, min(4, int(min(width, height) * 0.003)))

        for i in range(1, 10):
            x = int(width * i / 10)
            y = int(height * i / 10)
            draw.line([(x, 0), (x, height)], fill=grid_color, width=line_width)
            draw.line([(0, y), (width, y)], fill=grid_color, width=line_width)
            cross_size = line_width * 3
            cross_color = (0, 255, 100, 180)
            draw.line([(x - cross_size, y), (x + cross_size, y)], fill=cross_color, width=line_width)
            draw.line([(x, y - cross_size), (x, y + cross_size)], fill=cross_color, width=line_width)

        combined = Image.alpha_composite(image, overlay)
        return combined.convert('RGB')

    # ==========================================
    #       图片处理
    # ==========================================

    def _encode_image_png(self, image: Image.Image) -> str:
        """
        将图片编码为 PNG Base64 URL（无损传输）

        PNG 无损，给模型最清晰的图像。VLM 的 token 消耗由分辨率决定，
        与图片格式/文件大小无关，因此无需 JPEG 压缩。

        Args:
            image: PIL Image 对象

        Returns:
            Base64 编码的 PNG 图片 URL
        """
        if image.mode == 'RGBA':
            background = Image.new('RGB', image.size, (255, 255, 255))
            background.paste(image, mask=image.split()[3])
            image = background
        elif image.mode != 'RGB':
            image = image.convert('RGB')

        buffered = io.BytesIO()
        image.save(buffered, format="PNG")
        base64_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
        return f"data:image/png;base64,{base64_str}"

    # ==========================================
    #       指令预处理
    # ==========================================

    def _extract_instruction_info(self, instruction: str) -> Dict[str, Any]:
        """
        从用户指令中提取关键信息

        提取：目标应用名、搜索关键词、目标操作等
        """
        info = {}

        # 提取应用名
        app_name = self._extract_app_name(instruction)
        if app_name:
            info["app_name"] = app_name

        # 提取搜索关键词（"搜索XXX"、"搜XXX"、"查找XXX"）
        search_match = re.search(r'(?:搜索|搜|查找|查询|搜索一下)([^\s,，。、的]+)', instruction)
        if search_match:
            info["search_query"] = search_match.group(1).strip()

        # 提取 TYPE 文本（"输入XXX"、"发布评论：XXX"、"购买XXX"）
        type_match = re.search(r'(?:输入|评论|发表评论[：:])([^\s,，。]+)', instruction)
        if type_match:
            info["type_text"] = type_match.group(1).strip()

        return info

    def _extract_app_name(self, instruction: str) -> Optional[str]:
        """
        从指令中提取并规范化应用名
        """
        # 按名称长度降序排列，优先匹配更长的名称
        sorted_apps = sorted(APP_NAME_MAP.keys(), key=len, reverse=True)

        for app_key in sorted_apps:
            # 匹配 "去XXX"、"在XXX"、"打开XXX" 等模式
            patterns = [
                rf'(?:去|在|打开|进入|使用){re.escape(app_key)}',
                rf'{re.escape(app_key)}(?:上|里|中|里面|内|App|app|APP)',
            ]
            for pattern in patterns:
                match = re.search(pattern, instruction)
                if match:
                    return APP_NAME_MAP[app_key]

        # 直接匹配应用名
        for app_key in sorted_apps:
            if app_key in instruction:
                return APP_NAME_MAP[app_key]

        return None

    # ==========================================
    #       历史格式化
    # ==========================================

    def _format_history(self, history_actions: List[Dict[str, Any]]) -> str:
        """
        将历史操作格式化为可读文本（合并 Thought + Action）

        每一步都是完整的叙述：[想]怎么想的 → [做]怎么干的
        让模型一眼理解"之前怎么想的、怎么干的，现在要干什么"
        """
        if not history_actions:
            return "（无，这是第一步）"

        lines = []
        recent_thoughts = getattr(self, '_step_thoughts', [])
        thought_map = {t.get("step"): t.get("thought", "") for t in recent_thoughts}

        for record in history_actions:
            step = record.get("step", "?")
            action = record.get("action", "")
            params = record.get("parameters", {})

            # 格式化动作
            if action == "CLICK":
                point = params.get("point", [])
                action_str = f"CLICK 坐标{point}" if point else "CLICK"
            elif action == "TYPE":
                text = params.get("text", "")
                action_str = f'TYPE "{text}"'
            elif action == "OPEN":
                app = params.get("app_name", "")
                action_str = f'OPEN "{app}"'
            elif action == "SCROLL":
                start = params.get("start_point", [])
                end = params.get("end_point", [])
                action_str = f"SCROLL 从{start}到{end}"
            elif action == "COMPLETE":
                action_str = "COMPLETE"
            else:
                action_str = f"{action} {json.dumps(params, ensure_ascii=False)}"

            # 合并 Thought + Action
            thought = thought_map.get(step, "")
            if thought:
                lines.append(f"第{step}步: [想]{thought} → [做]{action_str}")
            else:
                lines.append(f"第{step}步: [做]{action_str}")

        return "\n".join(lines)

    # ==========================================
    #       消息构造
    # ==========================================

    def _build_messages(self, input_data: AgentInput) -> List[Dict[str, Any]]:
        """
        构造发送给大模型的 messages

        单轮对话架构：system prompt + user(文本+当前图片)
        """
        # 1. 指令预处理（首次调用时提取）
        if not self._instruction_info and input_data.step_count == 1:
            self._instruction_info = self._extract_instruction_info(input_data.instruction)

        # 2. 构造 system prompt
        system_msg = {
            "role": "system",
            "content": SYSTEM_PROMPT
        }

        # 3. 构造 user 文本内容
        user_text_parts = []

        # 用户指令
        user_text_parts.append(f"## 用户指令\n{input_data.instruction}")

        # 指令解析（如果有提取到信息）
        if self._instruction_info:
            parse_lines = []
            if "app_name" in self._instruction_info:
                parse_lines.append(f"- 目标应用：{self._instruction_info['app_name']}")
            if "search_query" in self._instruction_info:
                parse_lines.append(f"- 需要搜索：{self._instruction_info['search_query']}")
            if "type_text" in self._instruction_info:
                parse_lines.append(f"- 需要输入：{self._instruction_info['type_text']}")
            if parse_lines:
                user_text_parts.append("## 指令解析\n" + "\n".join(parse_lines))

        # 当前步骤
        user_text_parts.append(f"## 当前步骤\n第 {input_data.step_count} 步")

        # 操作历史
        history_text = self._format_history(input_data.history_actions)
        user_text_parts.append(f"## 已执行操作历史\n{history_text}")

        # 步骤特定提示
        step_hints = []
        if input_data.step_count == 1:
            step_hints.append("这是第一步，通常需要先 OPEN 打开目标应用。")

        # 基于指令解析的动态提示
        if self._instruction_info:
            app_name = self._instruction_info.get("app_name", "")
            if app_name and input_data.step_count <= 2:
                step_hints.append(f"目标应用【{app_name}】搜索图标右上角，返回键左上角，底部导航栏")

        # 历史动作中有失败的步骤时，提醒注意坐标
        failed_actions = [h for h in input_data.history_actions if not h.get("is_valid", True)]
        if failed_actions:
            step_hints.append("上步坐标偏移！必须在Thought中估算元素x/y范围再算中心点")

        # TYPE后必须搜索的提醒
        recent_actions = input_data.history_actions[-2:] if input_data.history_actions else []
        if any(a.get("action") == "TYPE" for a in recent_actions):
            step_hints.append("刚TYPE完，下一步必须CLICK搜索按钮提交")

        if step_hints:
            user_text_parts.append("⚠️ 提示：" + " | ".join(step_hints))

        user_text_parts.append("请分析截图输出下一步，CLICK前必须在Thought中估算坐标。")

        user_text = "\n\n".join(user_text_parts)

        # 4. 预处理图片（绘制10x10网格辅助线）后编码为PNG
        processed_image = self._preprocess_image(input_data.current_image)
        image_url = self._encode_image_png(processed_image)

        # 5. 构造 user message（文本 + 图片）
        user_msg = {
            "role": "user",
            "content": [
                {"type": "text", "text": user_text},
                {"type": "image_url", "image_url": {"url": image_url}}
            ]
        }

        return [system_msg, user_msg]

    # ==========================================
    #       坐标后处理
    # ==========================================

    @staticmethod
    def _is_coordinate_suspicious(action: str, parameters: Dict[str, Any]) -> bool:
        """
        检测坐标是否可疑：模型倾向于输出"安全中心点"
        如果 CLICK 坐标落在屏幕正中央的很小区域内，标记为可疑
        """
        if action != "CLICK":
            return False
        point = parameters.get("point")
        if not point or len(point) != 2:
            return False
        x, y = point
        # 模型最常输出的"安全点"：x在400-600, y在150-250
        if 400 <= x <= 600 and 150 <= y <= 250:
            return True
        return False

    @staticmethod
    def _extract_thought_coordinates(raw_output: str) -> Optional[Dict[str, Any]]:
        """
        从模型输出的 Thought 中提取坐标估算信息
        模型可能输出类似 "中心点约为 x=850, y=45" 或 "point=[850, 45]" 的信息
        """
        # 匹配 "x=数字" 和 "y=数字" 模式
        x_match = re.search(r'[xX]\s*[=≈]\s*(\d+)', raw_output)
        y_match = re.search(r'[yY]\s*[=≈]\s*(\d+)', raw_output)
        if x_match and y_match:
            x_val = int(x_match.group(1))
            y_val = int(y_match.group(1))
            if 0 <= x_val <= 1000 and 0 <= y_val <= 1000:
                return {"x": x_val, "y": y_val}

        # 匹配 [x, y] 模式在 Thought 部分
        thought_match = re.search(r'Thought:.*?\[(\d+)\s*,\s*(\d+)\]', raw_output, re.DOTALL)
        if thought_match:
            x_val = int(thought_match.group(1))
            y_val = int(thought_match.group(2))
            if 0 <= x_val <= 1000 and 0 <= y_val <= 1000:
                return {"x": x_val, "y": y_val}

        return None

    def _post_process_coordinates(self, action: str, parameters: Dict[str, Any],
                                   raw_output: str) -> Tuple[str, Dict[str, Any]]:
        """
        坐标后处理：检测并修正可疑坐标

        策略：
        1. 如果 Action 中的坐标是"安全中心点"且 Thought 中估算了不同的坐标，使用 Thought 中的坐标
        2. 坐标边界修正：如果坐标接近但超出合法边界，向内修正（应对checker严格不等式）
        3. 记录日志供调试
        """
        if action != "CLICK":
            return action, parameters

        point = parameters.get("point")
        if not point or len(point) != 2:
            return action, parameters

        action_x, action_y = point
        original_x, original_y = action_x, action_y
        modified = False

        # 策略1：检测并修正"安全中心点"
        if self._is_coordinate_suspicious(action, parameters):
            thought_coords = self._extract_thought_coordinates(raw_output)
            if thought_coords:
                thought_x = thought_coords["x"]
                thought_y = thought_coords["y"]
                thought_dist_from_center = abs(thought_x - 500) + abs(thought_y - 500)
                action_dist_from_center = abs(action_x - 500) + abs(action_y - 500)
                if thought_dist_from_center > action_dist_from_center + 100:
                    logger.info(
                        f"[坐标校正] 检测到安全中心点({action_x}, {action_y})，"
                        f"使用Thought中估算坐标({thought_x}, {thought_y})"
                    )
                    parameters = dict(parameters)
                    parameters["point"] = [thought_x, thought_y]
                    return action, parameters

            logger.warning(
                f"[坐标警告] CLICK坐标({action_x}, {action_y})位于屏幕中心区域，"
                f"可能不是目标元素的真实位置"
            )

        # 策略2：坐标边界修正（应对checker严格不等式 x_min < x < x_max）
        # 从 Thought 中提取坐标范围信息，如果模型输出了 x1,y1,x2,y2，可以用来修正
        bounds = self._extract_thought_bounds(raw_output)
        if bounds:
            x_min, x_max, y_min, y_max = bounds
            # 严格不等式要求：x_min < x < x_max，即 x 必须在 (x_min+1, x_max-1) 范围内
            safe_x_min = x_min + 1
            safe_x_max = x_max - 1
            safe_y_min = y_min + 1
            safe_y_max = y_max - 1

            # 修正x坐标
            if action_x <= safe_x_min:
                new_x = safe_x_min + 2  # 向内偏移2个点
                logger.info(f"[边界修正] x={action_x} <= {safe_x_min}，修正为 {new_x}")
                action_x = new_x
                modified = True
            elif action_x >= safe_x_max:
                new_x = safe_x_max - 2
                logger.info(f"[边界修正] x={action_x} >= {safe_x_max}，修正为 {new_x}")
                action_x = new_x
                modified = True

            # 修正y坐标
            if action_y <= safe_y_min:
                new_y = safe_y_min + 2
                logger.info(f"[边界修正] y={action_y} <= {safe_y_min}，修正为 {new_y}")
                action_y = new_y
                modified = True
            elif action_y >= safe_y_max:
                new_y = safe_y_max - 2
                logger.info(f"[边界修正] y={action_y} >= {safe_y_max}，修正为 {new_y}")
                action_y = new_y
                modified = True

        # 策略3：边缘坐标保护（Y<30或Y>970极易溢出）
        if action_y < 30:
            logger.info(f"[边缘保护] y={action_y} < 30，修正为 30")
            action_y = 30
            modified = True
        elif action_y > 970:
            logger.info(f"[边缘保护] y={action_y} > 970，修正为 970")
            action_y = 970
            modified = True

        if modified:
            parameters = dict(parameters)
            parameters["point"] = [action_x, action_y]

        return action, parameters

    @staticmethod
    def _extract_thought_bounds(raw_output: str) -> Optional[Tuple[int, int, int, int]]:
        """
        从模型输出的 Thought 中提取坐标边界 (x1, x2, y1, y2)

        匹配模式：
        - "左上角(x1=780,y1=25)右下角(x2=960,y2=75)"
        - "x1=780,y1=25,x2=960,y2=75"
        - "(x1=780,y1=25)(x2=960,y2=75)"
        """
        # 匹配 x1=N,y1=N,x2=N,y2=N 或带括号的变体
        pattern = r'[\(（]?\s*x1\s*[=:]\s*(\d+)\s*,\s*y1\s*[=:]\s*(\d+)\s*\)?\s*[\(（]?x2\s*[=:]\s*(\d+)\s*,\s*y2\s*[=:]\s*(\d+)'
        match = re.search(pattern, raw_output)
        if match:
            x1, y1, x2, y2 = int(match.group(1)), int(match.group(2)), int(match.group(3)), int(match.group(4))
            # 确保 x1 < x2, y1 < y2
            if x1 <= x2 and y1 <= y2 and 0 <= x1 <= 1000 and 0 <= y1 <= 1000:
                return (x1, x2, y1, y2)
            elif x2 <= x1 and y2 <= y1:
                return (x2, x1, y2, y1)

        return None

    @staticmethod
    def _extract_thought_summary(raw_output: str) -> str:
        """
        从模型输出的 raw_output 中提取 Thought 精简版（语义记忆）

        策略：
        1. 提取 Thought: 到 Action: 之间的内容
        2. 截取前200个字符，保留关键信息
        """
        # 匹配 Thought: 到 Action: 之间的内容
        thought_match = re.search(r'Thought:\s*(.*?)Action:', raw_output, re.DOTALL)
        if thought_match:
            thought = thought_match.group(1).strip()
            # 截取前200字符，避免过长
            if len(thought) > 200:
                thought = thought[:200] + "..."
            return thought

        # 如果没匹配到，返回空字符串
        return ""

    # ==========================================
    #       核心方法
    # ==========================================

    def act(self, input_data: AgentInput) -> AgentOutput:
        """
        Agent 核心方法：根据输入生成动作

        Args:
            input_data: AgentInput 包含当前轮所有信息

        Returns:
            AgentOutput 包含动作和参数
        """
        raw_output = ""
        usage = None

        try:
            # 1. 构造 messages
            messages = self._build_messages(input_data)

            # 2. 调用大模型（注意：_call_api 不转发 temperature 等 kwargs）
            response = self._call_api(messages)

            # 3. 提取响应内容
            if response and response.choices and len(response.choices) > 0:
                raw_output = response.choices[0].message.content or ""

            # 4. 提取 token 使用信息（仅记录，不做预算管理）
            usage = self.extract_usage_info(response) if response else None

            # 5. 解析输出
            action, parameters = self._parser.parse(raw_output)

            # 5.5 坐标后处理：检测并修正可疑坐标
            action, parameters = self._post_process_coordinates(action, parameters, raw_output)

            # 6. 记录步骤（Action）
            self._step_history.append({
                "step": input_data.step_count,
                "action": action,
                "parameters": parameters
            })

            # 6.5 记录Thought精简版（语义记忆）
            thought_summary = self._extract_thought_summary(raw_output)
            self._step_thoughts.append({
                "step": input_data.step_count,
                "thought": thought_summary
            })

            return AgentOutput(
                action=action,
                parameters=parameters,
                raw_output=raw_output,
                usage=usage
            )

        except Exception as e:
            logger.error(f"[Agent] 执行异常: {e}")

            # 异常时返回 COMPLETE，让流程安全结束
            return AgentOutput(
                action=ACTION_COMPLETE,
                parameters={},
                raw_output=f"Error: {str(e)}",
                usage=usage
            )
