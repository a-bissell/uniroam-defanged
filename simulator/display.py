"""
Terminal visualization for the virtual swarm simulator.

Renders a live-updating display showing robot positions, infection
spread, propagation chain, and timing. Uses ANSI escape codes only,
no external dependencies.
"""

import time
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class InfectionEvent:
    timestamp: float
    parent_id: str
    child_id: str
    rssi: Optional[int] = None


@dataclass
class RobotState:
    robot_id: str
    label: str
    x: float
    y: float
    infected: bool = False
    parent_id: Optional[str] = None


class SwarmDisplay:
    """Live terminal display for swarm propagation."""

    GRID_W = 62
    GRID_H = 20

    RED = "\033[91m"
    GREEN = "\033[92m"
    DIM = "\033[2m"
    BOLD = "\033[1m"
    RESET = "\033[0m"
    CLEAR = "\033[2J\033[H"

    def __init__(self, spread_radius: float = 50.0):
        self.spread_radius = spread_radius
        self.robots: Dict[str, RobotState] = {}
        self.events: List[InfectionEvent] = []
        self.start_time = time.time()

    def add_robot(self, robot_id: str, label: str, x: float, y: float):
        self.robots[robot_id] = RobotState(
            robot_id=robot_id, label=label, x=x, y=y
        )

    def record_infection(self, parent_id: str, child_id: str,
                         rssi: Optional[int] = None):
        self.events.append(InfectionEvent(
            timestamp=time.time() - self.start_time,
            parent_id=parent_id,
            child_id=child_id,
            rssi=rssi,
        ))
        if child_id in self.robots:
            self.robots[child_id].infected = True
            self.robots[child_id].parent_id = parent_id

    def _map_to_grid(self, x: float, y: float) -> tuple[int, int]:
        r = self.spread_radius
        gx = int((x + r) / (2 * r) * (self.GRID_W - 2)) + 1
        gy = int((y + r) / (2 * r) * (self.GRID_H - 2)) + 1
        gx = max(1, min(self.GRID_W - 2, gx))
        gy = max(1, min(self.GRID_H - 2, gy))
        return gx, gy

    def _render_grid(self) -> List[str]:
        grid = [[" "] * self.GRID_W for _ in range(self.GRID_H)]

        # Border
        for x in range(self.GRID_W):
            grid[0][x] = "-"
            grid[self.GRID_H - 1][x] = "-"
        for y in range(self.GRID_H):
            grid[y][0] = "|"
            grid[y][self.GRID_W - 1] = "|"
        grid[0][0] = "+"
        grid[0][self.GRID_W - 1] = "+"
        grid[self.GRID_H - 1][0] = "+"
        grid[self.GRID_H - 1][self.GRID_W - 1] = "+"

        # Place robots
        placements = []
        for r in self.robots.values():
            gx, gy = self._map_to_grid(r.x, r.y)
            placements.append((gx, gy, r))

        lines = []
        for y in range(self.GRID_H):
            row = ""
            x = 0
            while x < self.GRID_W:
                placed = False
                for gx, gy, r in placements:
                    if gy == y and gx == x:
                        idx = r.robot_id.replace("SIM_", "")
                        if r.infected:
                            token = f"{self.RED}{self.BOLD}*{idx}{self.RESET}"
                        else:
                            token = f"{self.GREEN}o{idx}{self.RESET}"
                        row += token
                        x += len(idx) + 1
                        placed = True
                        break
                if not placed:
                    row += grid[y][x]
                    x += 1
            lines.append(row)

        return lines

    def _render_tree(self) -> List[str]:
        children: Dict[str, List[str]] = {}
        for e in self.events:
            children.setdefault(e.parent_id, []).append(e.child_id)

        lines = []
        roots = []
        for e in self.events:
            if e.parent_id not in self.robots:
                if e.parent_id not in roots:
                    roots.append(e.parent_id)

        def walk(node: str, prefix: str, is_last: bool, depth: int):
            if depth == 0:
                connector = ""
            else:
                connector = "`-- " if is_last else "|-- "

            label = node
            if node in self.robots and self.robots[node].infected:
                label = f"{self.RED}{node}{self.RESET}"
            elif node not in self.robots:
                label = f"{self.DIM}{node}{self.RESET}"

            lines.append(f"{prefix}{connector}{label}")

            kids = children.get(node, [])
            for i, child in enumerate(kids):
                if depth == 0:
                    child_prefix = prefix + "    "
                else:
                    child_prefix = prefix + ("     " if is_last else "|    ")
                walk(child, child_prefix, i == len(kids) - 1, depth + 1)

        for root in roots:
            walk(root, "  ", True, 0)

        return lines

    def render(self):
        elapsed = time.time() - self.start_time
        infected = sum(1 for r in self.robots.values() if r.infected)
        total = len(self.robots)
        pct = (infected / total * 100) if total > 0 else 0

        out = []
        out.append(self.CLEAR)
        out.append(f"  {self.BOLD}UniRoam (Defanged) - Virtual Swarm Simulator{self.RESET}")
        out.append(f"  Elapsed: {elapsed:.1f}s")
        out.append("")

        for line in self._render_grid():
            out.append(f"  {line}")

        out.append("")
        bar_full = int(pct / 100 * 30)
        bar = f"{self.RED}{'#' * bar_full}{self.RESET}{self.DIM}{'.' * (30 - bar_full)}{self.RESET}"
        out.append(f"  [{bar}] {self.RED}*{self.RESET} {infected} infected  "
                    f"{self.GREEN}o{self.RESET} {total - infected} clean  ({pct:.0f}%)")
        out.append("")

        out.append(f"  {self.BOLD}Propagation log:{self.RESET}")
        display_events = self.events[-8:]
        if not display_events:
            out.append(f"  {self.DIM}  (waiting for patient zero){self.RESET}")
        for e in display_events:
            rssi_str = f"  RSSI {e.rssi}" if e.rssi is not None else ""
            out.append(
                f"  {self.DIM}{e.timestamp:6.1f}s{self.RESET}  "
                f"{e.parent_id} -> {self.RED}{e.child_id}{self.RESET}{rssi_str}"
            )
        out.append("")

        out.append(f"  {self.BOLD}Infection chain:{self.RESET}")
        tree_lines = self._render_tree()
        for line in tree_lines[:12]:
            out.append(line)
        if len(tree_lines) > 12:
            out.append(f"  {self.DIM}  ... ({len(tree_lines) - 12} more){self.RESET}")

        if infected >= total:
            out.append("")
            out.append(f"  {self.RED}{self.BOLD}Propagation complete: "
                        f"{total}/{total} infected in {elapsed:.1f}s{self.RESET}")

        print("\n".join(out), flush=True)
