# aim-py-cw
# -*- coding: utf-8 -*-
"""AIM 2627 Python Coursework —— 哨兵 Sentry 控制模块（学生骨架）。

你的全部作业都在本文件里：按题面（题面.pdf）各题的规范补全每个标有 TODO 的函数。
- 骨架已提供：Facing / SentryState 枚举、SentryGrid 的构造与只读属性、
  渲染函数 render_frame（demo 用，不进测试）。
- 你要实现：Q1-Q6 与 Bonus 的全部 TODO，以及 SentryGrid 的
  四个方法（current_pos 的 setter、move_forward、turn_left、turn_right）。
- `python main.py`（或 PYTHONPATH=src python -m main）可看 ASCII 演示。
"""
import json
from collections import deque
from enum import Enum


# ---------------------------------------------------------------------------
# 仿真世界基础（已提供，勿改）
# ---------------------------------------------------------------------------
class Facing(Enum):
    """朝向枚举。世界坐标 (x, y)：x 向右增长，y 向上增长（数学系）。"""

    UP = (0, 1)
    DOWN = (0, -1)
    LEFT = (-1, 0)
    RIGHT = (1, 0)

    @property
    def delta(self):
        """该朝向的单位位移向量 (dx, dy)。"""
        return self.value[0], self.value[1]


_LEFT_OF = {
    Facing.UP: Facing.LEFT,
    Facing.LEFT: Facing.DOWN,
    Facing.DOWN: Facing.RIGHT,
    Facing.RIGHT: Facing.UP,
}

_RIGHT_OF = {target: source for source, target in _LEFT_OF.items()}


def _manhattan(a, b):
    """两个格子之间的曼哈顿距离。"""
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


# ---------------------------------------------------------------------------
# Q1 机器人自检（题面 Q1·自检状态计算与报告生成）
# ---------------------------------------------------------------------------
def hp_ratio(hp, max_hp):
    """血量百分比：0-100 的 int，整数截断，超界夹紧。"""
    try:
        hp = int(hp)
        max_hp = int(max_hp)
    except (TypeError, ValueError):
        return 0
    if max_hp <= 0 or hp <= 0:
        return 0
    if hp >= max_hp:
        return 100
    return hp * 100 // max_hp


def status_report(name, robot_type, hp, max_hp, battery):
    """一行自检报告：名称左对齐、机型居中、百分比右对齐。"""
    ratio = hp_ratio(hp, max_hp)
    try:
        level = int(battery)
    except (TypeError, ValueError):
        level = 0
    level = max(0, min(100, level))
    if level >= 60:
        tier = "OK"
    elif level >= 20:
        tier = "WARNING"
    else:
        tier = "LOW"
    return "{:<10}|{:^10}|HP {:>3}%|BAT {:>3}%|{}".format(
        str(name), str(robot_type), ratio, level, tier)


# ---------------------------------------------------------------------------
# Q2 战斗日志分析（题面 Q2·多源日志解析与统计）
# ---------------------------------------------------------------------------
_ARMOR_BY_LETTER = {"F": "front", "L": "left", "R": "right"}
_ARMORS = ("front", "left", "right")


def _positive_int(text):
    """把字符串解析为正整数；非纯数字或 <= 0 返回 None。"""
    if not text or not text.isdigit():
        return None
    value = int(text)
    return value if value > 0 else None


def _parse_sensor_line(line):
    """解析 "F:32,L:5,R:12"；任何一段非法则整行视为脏行。"""
    events = []
    for chunk in line.split(","):
        chunk = chunk.strip()
        if chunk.count(":") != 1:
            return None
        letter, number = chunk.split(":")
        letter = letter.strip()
        if letter not in _ARMOR_BY_LETTER:
            return None
        amount = _positive_int(number.strip())
        if amount is None:
            return None
        events.append((_ARMOR_BY_LETTER[letter], amount))
    return events or None


def _parse_json_line(line):
    """解析 JSON 行；返回 (events, ident)，非法返回 None。"""
    try:
        data = json.loads(line)
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    armor = data.get("armor")
    damage = data.get("damage")
    if armor not in _ARMORS:
        return None
    if isinstance(damage, bool) or not isinstance(damage, int):
        return None
    if damage <= 0:
        return None
    ident = data.get("id")
    if ident is not None:
        if isinstance(ident, bool) or not isinstance(ident, int):
            return None
    return [(armor, damage)], ident


def analyze_damage_log(lines):
    """解析混合格式伤害日志，跳过脏行，返回固定契约的统计字典。"""
    by_armor = {armor: 0 for armor in _ARMORS}
    total = 0
    events = 0
    seen_ids = set()
    try:
        raw_lines = list(lines)
    except TypeError:
        raw_lines = []
    for line in raw_lines:
        if not isinstance(line, str):
            continue
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        if text.startswith("{"):
            parsed = _parse_json_line(text)
            if parsed is None:
                continue
            entries, ident = parsed
            if ident is not None:
                if ident in seen_ids:
                    continue
                seen_ids.add(ident)
        else:
            entries = _parse_sensor_line(text)
            if not entries:
                continue
        for armor, damage in entries:
            by_armor[armor] += damage
            total += damage
            events += 1
    most_hit = None
    if events:
        peak = max(by_armor.values())
        for armor in _ARMORS:
            if by_armor[armor] == peak:
                most_hit = armor
                break
    average = round(total / events, 2) if events else 0.0
    return {
        "total": total,
        "by_armor": by_armor,
        "most_hit": most_hit,
        "avg": average,
    }


# ---------------------------------------------------------------------------
# Q3 SentryGrid（题面 Q3·载体物理规则）
# ---------------------------------------------------------------------------
class SentryGrid:
    """哨兵仿真载体（构造与只读属性已提供；四个 TODO 方法由你实现）。"""

    def __init__(self, width, height, obstacles, enemy_pos,
                 start_pos=(0, 0), facing=Facing.UP, fuel=100):
        self._width = int(width)
        self._height = int(height)
        if self._width <= 0 or self._height <= 0:
            raise ValueError("地图尺寸必须为正")
        # 障碍坐标存入 set，查询 O(1)——已有实现，勿改。
        self._obstacles = set()
        for ob in obstacles:
            x, y = ob
            self._obstacles.add((int(x), int(y)))
        if not isinstance(enemy_pos, (tuple, list)) or len(enemy_pos) != 2:
            raise TypeError("enemy_pos 需要长度为 2 的 tuple/list")
        self._enemy_pos = self._clamp_cell(enemy_pos)
        if self._enemy_pos in self._obstacles:
            raise ValueError("enemy_pos 不能位于障碍物上")
        if not isinstance(facing, Facing):
            facing = Facing.UP
        self._facing = facing
        self._fuel = int(fuel)
        self._collision_count = 0
        self._pos = self._clamp_cell(start_pos)
        if self._pos in self._obstacles:
            raise ValueError("start_pos 不能位于障碍物上")

    def _clamp_cell(self, cell):
        """已提供：元素转 int 并夹回地图范围（供 __init__ 使用）。"""
        x = int(cell[0])
        y = int(cell[1])
        x = max(0, min(self._width - 1, x))
        y = max(0, min(self._height - 1, y))
        return (x, y)

    # -- 只读属性（已提供，勿改） ------------------------------------------
    @property
    def width(self):
        return self._width

    @property
    def height(self):
        return self._height

    @property
    def enemy_pos(self):
        return self._enemy_pos

    @property
    def facing(self):
        return self._facing

    @property
    def fuel(self):
        return self._fuel

    @property
    def collision_count(self):
        return self._collision_count

    @property
    def obstacles(self):
        """障碍集合的只读视图（内部 set 引用，不要修改它）。"""
        return self._obstacles

    @property
    def found_enemy(self):
        return self._pos == self._enemy_pos

    def is_blocked(self, x, y):
        """已提供：坐标是否为障碍或越界（O(1)）。"""
        return ((x, y) in self._obstacles
                or not (0 <= x < self._width and 0 <= y < self._height))

    # -- 你要实现的部分 ------------------------------------------------------
    @property
    def current_pos(self):
        """当前位置 (x, y) 的 tuple。"""
        return self._pos

    @current_pos.setter
    def current_pos(self, value):
        """位置 setter：只接受长度 2 的 tuple/list，元素规范化后存 tuple。"""
        if not isinstance(value, (tuple, list)) or len(value) != 2:
            raise TypeError("current_pos 需要长度为 2 的 tuple/list")
        self._pos = self._clamp_cell(value)

    def move_forward(self):
        """朝当前 facing 前进一格，返回执行后的位置。"""
        if self._fuel <= 0:
            return self._pos
        self._fuel -= 1
        dx, dy = self._facing.delta
        nx, ny = self._pos[0] + dx, self._pos[1] + dy
        if self.is_blocked(nx, ny):
            self._collision_count += 1
            return self._pos
        self._pos = (nx, ny)
        return self._pos

    def turn_left(self):
        """原地左转 90°，返回新的 Facing（不耗电）。"""
        self._facing = _LEFT_OF[self._facing]
        return self._facing

    def turn_right(self):
        """原地右转 90°，返回新的 Facing（不耗电）。"""
        self._facing = _RIGHT_OF[self._facing]
        return self._facing


# ---------------------------------------------------------------------------
# Q4 贪心导航（题面 Q4·单步贪心导航策略）
# ---------------------------------------------------------------------------
def _greedy_candidates(pos, target, obstacles):
    """返回让曼哈顿距离严格减小的合法方向。"""
    x, y = pos
    tx, ty = target
    dx, dy = tx - x, ty - y
    base = abs(dx) + abs(dy)
    horizontal = []
    if dx > 0:
        horizontal.append(Facing.RIGHT)
    elif dx < 0:
        horizontal.append(Facing.LEFT)
    vertical = []
    if dy > 0:
        vertical.append(Facing.UP)
    elif dy < 0:
        vertical.append(Facing.DOWN)
    if base == 0:
        return [], horizontal, vertical
    if abs(dx) >= abs(dy):
        ordered = horizontal + vertical
    else:
        ordered = vertical + horizontal
    candidates = []
    for direction in ordered:
        ddx, ddy = direction.delta
        nxt = (x + ddx, y + ddy)
        if nxt in obstacles:
            continue
        if abs(nxt[0] - tx) + abs(nxt[1] - ty) < base:
            candidates.append(direction)
    return candidates, horizontal, vertical


def next_step_toward(pos, target, obstacles, current_facing=Facing.UP):
    """返回下一步应朝向的 Facing；无候选时回退到 current_facing。"""
    obstacles = obstacles or ()
    candidates, _, _ = _greedy_candidates(pos, target, obstacles)
    if not candidates:
        return current_facing
    return candidates[0]


# ---------------------------------------------------------------------------
# Q5 哨兵决策机（题面 Q5·裁判系统决策规则表）
# ---------------------------------------------------------------------------
class SentryState(Enum):
    """哨兵状态机（已提供，勿改）。"""

    PATROL = "PATROL"
    SUSPECT = "SUSPECT"
    ENGAGE = "ENGAGE"
    RETREAT = "RETREAT"
    RETURN = "RETURN"


_DECIDE_FIELDS = ("enemy_frames", "enemy_dist", "robot_type", "max_hp")


def _engage_target(dist, robot_type):
    """R4/R6 共用的交火判定：近距离射击，远距离按机型横移。"""
    if dist is not None and dist <= 3:
        return ("SHOOT", SentryState.ENGAGE)
    if robot_type == "HERO":
        return ("MOVE_RIGHT", SentryState.ENGAGE)
    return ("MOVE_LEFT", SentryState.ENGAGE)


def decide(sensor, state, hp, heat):
    """纯函数决策：按 R1-R7 顺序求值，首条命中即返回。"""
    if not isinstance(sensor, dict):
        raise ValueError("sensor 必须是字典")
    for field in _DECIDE_FIELDS:
        if field not in sensor:
            raise ValueError("sensor 缺少字段: {}".format(field))
    if not isinstance(state, SentryState):
        raise ValueError("state 必须是 SentryState 成员")

    frames = sensor["enemy_frames"]
    if isinstance(frames, (str, bytes)) or not isinstance(frames, (tuple, list)):
        raise ValueError("enemy_frames 必须是序列")
    if not 1 <= len(frames) <= 6:
        raise ValueError("enemy_frames 长度必须在 1..6")

    visible = bool(frames[-1])
    previous_visible = bool(frames[-2]) if len(frames) >= 2 else False
    recent_seen = visible or previous_visible

    distance = sensor["enemy_dist"]
    if isinstance(distance, bool) or not isinstance(distance, int):
        distance = None

    robot_type = sensor["robot_type"]
    if robot_type not in ("INFANTRY", "HERO"):
        robot_type = "INFANTRY"

    max_hp = sensor["max_hp"]
    if isinstance(max_hp, bool) or not isinstance(max_hp, int) or max_hp <= 0:
        max_hp = 100

    hp_pct = hp_ratio(hp, max_hp)

    # R1 保命优先
    if hp_pct <= 30:
        return ("RETREAT", SentryState.RETREAT)
    # R2 撤退保持：R1 已拦截低血量，到达这里即已恢复到安全血量
    if state is SentryState.RETREAT:
        return ("RETURN", SentryState.RETURN)
    # R3 返航单帧
    if state is SentryState.RETURN:
        return ("MOVE_BASE", SentryState.PATROL)
    # R4 交火决策
    if state is SentryState.ENGAGE:
        if visible:
            return _engage_target(distance, robot_type)
        # R5 交火保持：最近两帧都没看到才算持续丢失
        if recent_seen:
            return ("HOLD_FIRE", SentryState.ENGAGE)
        return ("SCAN", SentryState.SUSPECT)
    # R6 敌情确认 / R7 默认行为
    if visible:
        if len(frames) >= 2 and previous_visible:
            return _engage_target(distance, robot_type)
        return ("SCAN", SentryState.SUSPECT)
    if state is SentryState.PATROL:
        return ("PATROL_MOVE", SentryState.PATROL)
    return ("SCAN", SentryState.SUSPECT)


# ---------------------------------------------------------------------------
# Q6 巡逻任务（题面 Q6·巡逻契约与验收阈值）
# ---------------------------------------------------------------------------
def _has_greedy_step(grid):
    """当前位置是否还能朝目标严格靠近一步。"""
    pos = grid.current_pos
    target = grid.enemy_pos
    base = _manhattan(pos, target)
    if base == 0:
        return True
    for direction in (Facing.UP, Facing.DOWN, Facing.LEFT, Facing.RIGHT):
        dx, dy = direction.delta
        nxt = (pos[0] + dx, pos[1] + dy)
        if nxt in grid.obstacles:
            continue
        if _manhattan(nxt, target) < base:
            return True
    return False


def _face(grid, direction):
    """把朝向转到 direction（转 90° 的倍数，取较短的一侧）。"""
    order = [Facing.UP, Facing.RIGHT, Facing.DOWN, Facing.LEFT]
    diff = (order.index(direction) - order.index(grid.facing)) % 4
    if diff == 3:
        grid.turn_left()
    else:
        for _ in range(diff):
            grid.turn_right()


def run_patrol(grid, max_steps=500):
    """巡逻主循环：贪心前进，贪心失速时用沿墙脱困绕出死角。"""
    target = grid.enemy_pos
    trail = {grid.current_pos}
    steps = 0
    wall_mode = False
    hand = "L"
    wall_steps = 0
    entry_distance = _manhattan(grid.current_pos, target)
    limit = grid.width + grid.height
    seen = {}

    while steps < max_steps and grid.fuel > 0 and not grid.found_enemy:
        pos = grid.current_pos
        distance = _manhattan(pos, target)

        if not wall_mode and not _has_greedy_step(grid):
            wall_mode = True
            hand = "L"
            wall_steps = 0
            entry_distance = distance
            seen = {pos: 1}

        if wall_mode:
            side = _LEFT_OF[grid.facing] if hand == "L" else _RIGHT_OF[grid.facing]
            opposite = (_RIGHT_OF[grid.facing] if hand == "L"
                        else _LEFT_OF[grid.facing])
            dx, dy = side.delta
            side_free = not grid.is_blocked(pos[0] + dx, pos[1] + dy)
            dx, dy = grid.facing.delta
            ahead_free = not grid.is_blocked(pos[0] + dx, pos[1] + dy)
            dx, dy = opposite.delta
            opposite_free = not grid.is_blocked(pos[0] + dx, pos[1] + dy)
            if side_free:
                if hand == "L":
                    grid.turn_left()
                else:
                    grid.turn_right()
            elif not ahead_free:
                if opposite_free:
                    if hand == "L":
                        grid.turn_right()
                    else:
                        grid.turn_left()
                else:
                    grid.turn_right()
                    grid.turn_right()
        else:
            _face(grid, next_step_toward(pos, target, grid.obstacles,
                                         grid.facing))

        grid.move_forward()
        steps += 1
        trail.add(grid.current_pos)

        if wall_mode:
            wall_steps += 1
            current = grid.current_pos
            seen[current] = seen.get(current, 0) + 1
            if seen[current] >= 2 and hand == "L":
                # 左手规则绕回原格说明前方是环：换右手再试，避免死循环
                hand = "R"
                wall_steps = 0
                seen = {current: 1}
            if wall_steps > limit and hand == "L":
                hand = "R"
                wall_steps = 0
            elif wall_steps > 2 * limit:
                wall_mode = False
            elif (_has_greedy_step(grid)
                  and _manhattan(grid.current_pos, target) <= entry_distance):
                wall_mode = False

    found = grid.found_enemy
    return {
        "steps": steps,
        "collisions": grid.collision_count,
        "visited_count": len(trail),
        "found_enemy": found,
        "success": found,
    }


def report_to_json(stats):
    """把巡逻统计序列化为确定性的 JSON 字符串。"""
    return json.dumps(stats, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)


# ---------------------------------------------------------------------------
# Bonus：BFS 全局最短路（题面 Bonus·BFS 语义与排行榜）
# ---------------------------------------------------------------------------
def bfs_path_length(start, target, obstacles):
    """TODO(Bonus)：BFS 全局最短路步数；返回语义与边界职责见题面 Bonus 规范。"""
    raise NotImplementedError("Bonus bfs_path_length")


# ---------------------------------------------------------------------------
# 渲染（已提供，demo 专用，不进测试）
# ---------------------------------------------------------------------------
def render_frame(grid, trail=()):
    """ASCII 渲染一帧战场；trail 为走过的格子集合。返回 list[str]。"""
    trail = set(trail)
    rows = []
    for y in range(grid.height - 1, -1, -1):
        row = []
        for x in range(grid.width):
            if (x, y) == grid.current_pos:
                row.append("◉")
            elif (x, y) == grid.enemy_pos:
                row.append("▲")
            elif (x, y) in grid.obstacles:
                row.append("█")
            elif (x, y) in trail:
                row.append("·")
            else:
                row.append(".")
        rows.append("".join(row))
    return rows
