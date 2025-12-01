import sys
import os
import subprocess
import yaml
import shlex
import shutil
import json
import re
import time
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QGridLayout, QLabel,
    QLineEdit, QSpinBox, QDoubleSpinBox, QCheckBox, QPushButton, QFileDialog,
    QTextEdit, QComboBox, QHBoxLayout, QListWidget, QDockWidget, QProgressBar,
    QSystemTrayIcon, QStyle, QSlider
)
from PySide6.QtCore import Qt, QTimer, QRectF, QPointF
from PySide6.QtGui import QColor, QPainter, QPen, QBrush

import numpy as np


def parse_value(x):
    if isinstance(x, (int, float, bool)):
        return x
    if isinstance(x, str) and ".." in x:
        a = x.split("..")[0]
        return float(a) if "." in a else int(a)
    return x


def safe_disconnect(signal):
    """Safely disconnect a Qt signal without crashes on Linux."""
    try:
        signal.disconnect()
    except (TypeError, RuntimeError):
        pass


class DebugDock(QWidget):
    BACKGROUND = "#181818"
    TEXT = "#cccccc"
    YELLOW = "#d7d5a3"
    GREEN = "#4ec9b0"
    GRAY = "#6e7681"
    STRING = "#ce9178"
    GEM_TTL = 300

    def __init__(self):
        super().__init__()
        self.debug = None
        self.path = ""
        
        main_layout = QHBoxLayout(self)
        left_layout = QVBoxLayout()
        right_layout = QVBoxLayout()
        
        self.open_button = QPushButton("Open JSON")
        self.reload_button = QPushButton("Reload")
        self.open_button.clicked.connect(self.open)
        self.reload_button.clicked.connect(self.reload)
        
        left_layout.addWidget(self.open_button)
        left_layout.addWidget(self.reload_button)
        
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self.on_selection_changed)
        left_layout.addWidget(self.list)
        
        self.text = QTextEdit()
        self.text.setReadOnly(True)
        self.text.setStyleSheet(
            f"background:{self.BACKGROUND};color:{self.TEXT};font-family:Consolas;"
        )
        right_layout.addWidget(self.text)
        
        main_layout.addLayout(left_layout)
        main_layout.addLayout(right_layout)

    def span(self, text, color):
        return f'<span style="color:{color}">{text}</span>'
    def open(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open JSON", "", "JSON (*.json);;All (*.*)"
        )
        if path:
            self.load(path)

    def reload(self):
        if self.path:
            self.load(self.path)

    def load(self, path):
        try:
            data = json.load(open(path, "r", encoding="utf-8"))
            self.debug = data[0] if isinstance(data, list) else data
            self.path = path
            self.populate()
        except:
            pass

    def populate(self):
        self.list.clear()
        if not self.debug:
            return
        
        rounds = self.debug.get("rounds", [])
        self.list.addItem("Overview")
        for i in range(len(rounds)):
            self.list.addItem(f"Round {i+1}")
        self.list.addItem("Analytics")
        self.list.setCurrentRow(0)
        self.show_overview()

    def on_selection_changed(self, index):
        if not self.debug:
            return
        
        num_rounds = len(self.debug.get("rounds", []))
        if index == 0:
            self.show_overview()
        elif 1 <= index <= num_rounds:
            self.show_round(index - 1)
        elif index == num_rounds + 1:
            self.show_analytics()
    def show_overview(self):
        d = self.debug
        html_parts = []
        
        timestamp = time.asctime(time.gmtime(d.get("timestamp", 0)))
        html_parts.append(self.span(timestamp, self.GRAY) + "<br>")
        
        stage_key = self.span(d.get("stage_key", ""), self.GRAY)
        stage_title = self.span(d.get("stage_title", ""), self.GRAY)
        html_parts.append(f"{stage_key} {stage_title}<br><br>")
        
        html_parts.append(
            self.span("Seed: ", self.YELLOW) + 
            self.span(str(d.get("seed", "")), self.STRING) + "<br>"
        )
        html_parts.append(
            self.span("Name: ", self.YELLOW) + 
            self.span(f"{d.get('name', '')} [{d.get('emoji', '')}]", self.GREEN) + "<br>"
        )
        html_parts.append(
            self.span("Score: ", self.YELLOW) + str(d.get("total_score", "")) + "<br>"
        )
        
        if d.get("gem_utilization_cv") is not None:
            gu_mean = round(d.get("gem_utilization_mean"), 2)
            gu_cv = round(d.get("gem_utilization_cv"), 2)
            floor_cov = round(d.get("floor_coverage_mean"), 2)
            html_parts.append(self.span("GU mean: ", self.YELLOW) + f"{gu_mean}%<br>")
            html_parts.append(self.span("GU cv: ", self.YELLOW) + f"{gu_cv}<br>")
            html_parts.append(self.span("Floor Coverage: ", self.YELLOW) + f"{floor_cov}%<br>")
        
        html_parts.append(
            self.span("Git Hash: ", self.YELLOW) + 
            self.span(d.get("git_hash", ""), self.STRING)
        )
        
        self.text.setHtml("<html><body>" + "".join(html_parts) + "</body></html>")
    def show_round(self, round_index):
        r = self.debug["rounds"][round_index]
        rt = r.get("response_time_stats", {})
        html_parts = []
        
        html_parts.append(self.span(f"Round {round_index + 1}", self.GRAY) + "<br><br>")
        html_parts.append(
            self.span("Seed: ", self.YELLOW) + 
            self.span(str(r.get("seed", "")), self.STRING) + "<br>"
        )
        html_parts.append(
            self.span("Score: ", self.YELLOW) + str(r.get("score", "")) + "<br>"
        )
        
        if r.get("gem_utilization") is not None:
            html_parts.append(
                self.span("GU: ", self.YELLOW) + f"{r['gem_utilization']}%<br>"
            )
            html_parts.append(
                self.span("Floor Coverage: ", self.YELLOW) + f"{r['floor_coverage']}%<br>"
            )
        
        first_capture = r.get("ticks_to_first_capture")
        html_parts.append(
            self.span("First capture: ", self.YELLOW) + 
            self.span(f"tick {first_capture}", self.GRAY) + "<br>"
        )
        
        if r.get("disqualified_for") is not None:
            html_parts.append(
                self.span("Disqualified for: ", self.YELLOW) + 
                self.span(str(r["disqualified_for"]), self.STRING) + "<br>"
            )
        
        html_parts.append("<br>" + self.span("Response times:", self.YELLOW) + "<br>")
        for key in ["first", "min", "median", "max"]:
            ns_value = rt.get(key, 0)
            ms = round(ns_value / 1_000_000, 2) if ns_value is not None else 0
            html_parts.append(
                self.span(f"{key}: ", self.YELLOW) + 
                self.span(f"{ms} ms", self.GRAY) + "<br>"
            )
        
        if r.get("gem_utilization"):
            gu = r["gem_utilization"]
            estimated_gems = round(r["score"] / gu * 100 / self.GEM_TTL) if gu else 0
            avg_score = round(r["score"] / estimated_gems, 2) if estimated_gems else 0
            html_parts.append("<br>" + self.span("Gems spawned: ", self.YELLOW) + str(estimated_gems) + "<br>")
            html_parts.append(self.span("Mean gem score: ", self.YELLOW) + str(avg_score) + "<br>")
            html_parts.append(
                self.span("Capture mean: ", self.YELLOW) + 
                self.span(f"{round(self.GEM_TTL - avg_score, 2)} ticks", self.GRAY)
            )
        
        self.text.setHtml("<html><body>" + "".join(html_parts) + "</body></html>")
    def show_analytics(self):
        d = self.debug
        total = d.get("total_score", 0)
        rounds = d.get("rounds", [])
        html_parts = []
        
        html_parts.append(self.span("Score: ", self.YELLOW) + str(total) + "<br>")
        
        if len(rounds) > 1:
            avg = total / len(rounds)
            scores = sorted([x["score"] for x in rounds])
            median = (scores[(len(scores) - 1) // 2] + scores[len(scores) // 2]) / 2
            
            gu_mean = d.get("gem_utilization_mean", 1)
            total_gems_value = total / gu_mean * 100
            estimated_gems = int(round(total_gems_value / self.GEM_TTL)) if gu_mean else 0
            avg_gem_score = round(total / estimated_gems, 2) if estimated_gems else 0
            
            html_parts.append("<br>" + self.span("Mean: ", self.YELLOW) + str(avg) + "<br>")
            html_parts.append(self.span("Median: ", self.YELLOW) + str(median) + "<br>")
            html_parts.append(self.span("Total gems: ", self.YELLOW) + str(estimated_gems) + "<br>")
            html_parts.append(self.span("Mean gem score: ", self.YELLOW) + str(avg_gem_score) + "<br>")
            html_parts.append(
                self.span("Capture mean: ", self.YELLOW) + 
                self.span(f"{round(self.GEM_TTL - avg_gem_score, 2)} ticks", self.GRAY)
            )
        
        self.text.setHtml("<html><body>" + "".join(html_parts) + "</body></html>")

class MazeView(QWidget):
    def __init__(self, model, parent=None):
        super().__init__(parent)
        self.model = model
        self.show_heatmap = False
        self.setMinimumSize(400, 400)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        
        width = self.model.width or 1
        height = self.model.height or 1
        cell_width = self.width() / width
        cell_height = self.height() / height
        
        tick_data = self.model.current_tick_data()
        walls = self.model.walls
        visits = self.model.visits
        
        painter.fillRect(self.rect(), QColor(20, 20, 20))
        
        for y in range(height):
            for x in range(width):
                rect = QRectF(x * cell_width, y * cell_height, cell_width, cell_height)
                pos_key = (x, y)
                
                if pos_key in walls:
                    painter.fillRect(rect, QColor(70, 70, 70))
                else:
                    if self.show_heatmap:
                        visit_count = visits.get(pos_key, 0)
                        if visit_count > 0:
                            max_visits = max(visits.values()) if visits else 1
                            intensity = int(255 * min(1.0, visit_count / max_visits))
                            painter.fillRect(rect, QColor(intensity, 0, 0, 180))
                        else:
                            painter.fillRect(rect, QColor(30, 30, 30))
                    else:
                        painter.fillRect(rect, QColor(30, 30, 30))
        if tick_data:
            fov = tick_data.get("fov") or []
            for tile in fov:
                if len(tile) >= 2:
                    x, y = tile[0], tile[1]
                    rect = QRectF(x * cell_width, y * cell_height, cell_width, cell_height)
                    painter.fillRect(rect, QColor(255, 255, 100, 40))
            
            debug_extra = tick_data.get("debug_extra") or {}
            highlights = debug_extra.get("highlight") or []
            for item in highlights:
                if len(item) >= 3:
                    x, y, color = item[0], item[1], item[2]
                    rect = QRectF(x * cell_width, y * cell_height, cell_width, cell_height)
                    try:
                        qcolor = QColor(color)
                        if not qcolor.isValid():
                            qcolor = QColor(255, 0, 255, 120)
                    except:
                        qcolor = QColor(255, 0, 255, 120)
                    painter.fillRect(rect, qcolor)
            
            for gem in tick_data.get("gems", []):
                gx, gy = gem
                center_x = gx * cell_width + cell_width / 2
                center_y = gy * cell_height + cell_height / 2
                size = min(cell_width, cell_height) * 0.4
                diamond = [
                    QPointF(center_x, center_y - size),
                    QPointF(center_x + size, center_y),
                    QPointF(center_x, center_y + size),
                    QPointF(center_x - size, center_y)
                ]
                painter.setBrush(QBrush(QColor(0, 220, 255)))
                painter.setPen(QPen(QColor(255, 255, 255), 2))
                painter.drawPolygon(diamond)
            
            trail = self.model.trail
            if trail:
                pen = QPen(QColor(200, 200, 200))
                pen.setWidthF(max(1.0, min(cell_width, cell_height) * 0.15))
                painter.setPen(pen)
                last_pos = None
                for pos in trail:
                    x, y = pos
                    center_x = x * cell_width + cell_width / 2
                    center_y = y * cell_height + cell_height / 2
                    if last_pos is not None:
                        painter.drawLine(last_pos[0], last_pos[1], center_x, center_y)
                    last_pos = (center_x, center_y)
            
            bot_pos = tick_data.get("bot_pos")
            if bot_pos:
                bx, by = bot_pos
                rect = QRectF(bx * cell_width, by * cell_height, cell_width, cell_height)
                painter.setBrush(QBrush(QColor(255, 220, 100)))
                painter.setPen(QPen(QColor(0, 0, 0)))
                painter.drawEllipse(
                    rect.adjusted(
                        cell_width * 0.2, cell_height * 0.2,
                        -cell_width * 0.2, -cell_height * 0.2
                    )
                )
            
            state_delta = debug_extra.get("state_delta") or {}
            for tile in state_delta.get("added", []):
                if len(tile) >= 2:
                    x, y = tile[0], tile[1]
                    rect = QRectF(x * cell_width, y * cell_height, cell_width, cell_height)
                    painter.fillRect(rect, QColor(0, 180, 0, 120))
            
            for tile in state_delta.get("removed", []):
                if len(tile) >= 2:
                    x, y = tile[0], tile[1]
                    rect = QRectF(x * cell_width, y * cell_height, cell_width, cell_height)
                    painter.fillRect(rect, QColor(180, 0, 0, 120))
            
            path = debug_extra.get("path") or []
            if path:
                pen = QPen(QColor(0, 255, 180))
                pen.setWidthF(max(1.0, min(cell_width, cell_height) * 0.25))
                painter.setPen(pen)
                last_pos = None
                for pos in path:
                    if len(pos) < 2:
                        continue
                    x, y = pos[0], pos[1]
                    center_x = x * cell_width + cell_width / 2
                    center_y = y * cell_height + cell_height / 2
                    if last_pos is not None:
                        painter.drawLine(last_pos[0], last_pos[1], center_x, center_y)
                    last_pos = (center_x, center_y)
        
        painter.end()

class DebugModel:
    def __init__(self, debug_data):
        self.debug_data = debug_data
        self.round_index = 0
        self.tick_index = 0
        self.width = None
        self.height = None
        self.rounds = debug_data.get("rounds", [])
        self.ticks = []
        self.walls = set()
        self.visits = {}
        self.trail = []
        self.rebuild_round()
    def rebuild_round(self):
        self.ticks = []
        self.walls = set()
        self.visits = {}
        self.trail = []
        
        if not self.rounds:
            return
        
        round_data = self.rounds[self.round_index]
        protocol = round_data.get("debug_protocol") or []
        
        if not protocol:
            return
        
        temp_ticks = {}
        
        for entry in protocol:
            tick = entry.get("tick", 0)
            bots = entry.get("bots") or {}
            data = bots.get("data") or {}
            debug_json_raw = bots.get("debug_json")
            
            debug_json = None
            if debug_json_raw:
                try:
                    debug_json = json.loads(debug_json_raw)
                except:
                    pass
            
            config = data.get("config") or {}
            if self.width is None:
                self.width = config.get("width", self.width)
            if self.height is None:
                self.height = config.get("height", self.height)
            
            bot_pos = data.get("bot")
            walls = data.get("wall") or []
            all_gems_data = entry.get("all_gems") or []
            gems = [tuple(g.get("position")) for g in all_gems_data if g.get("position")]
            
            for wall in walls:
                if len(wall) >= 2:
                    self.walls.add((wall[0], wall[1]))
            
            if tick not in temp_ticks:
                temp_ticks[tick] = {
                    "tick": tick,
                    "bot_pos": None,
                    "gems": [],
                    "debug_extra": None
                }
            
            if bot_pos:
                temp_ticks[tick]["bot_pos"] = tuple(bot_pos)
                pos_key = tuple(bot_pos)
                self.visits[pos_key] = self.visits.get(pos_key, 0) + 1
            
            if gems:
                temp_ticks[tick]["gems"] = gems
            
            if debug_json is not None:
                temp_ticks[tick]["debug_extra"] = {
                    "highlight": debug_json.get("highlight"),
                    "state_delta": debug_json.get("state_delta"),
                    "decision": debug_json.get("decision"),
                    "path": debug_json.get("path"),
                    "memory": debug_json.get("memory")
                }
            
            fov_data = entry.get("fov")
            if fov_data:
                temp_ticks[tick]["fov"] = fov_data
            
            influence = entry.get("influence")
            if influence:
                temp_ticks[tick]["influence"] = influence
            
            gem_prediction = entry.get("gem_prediction")
            if gem_prediction:
                temp_ticks[tick]["gem_prediction"] = gem_prediction
        
        self.ticks = [temp_ticks[k] for k in sorted(temp_ticks.keys())]
        self.tick_index = 0
        self.rebuild_trail()
    def set_round(self, index):
        if index < 0 or index >= len(self.rounds):
            return
        self.round_index = index
        self.rebuild_round()

    def set_tick(self, index):
        if not self.ticks:
            self.tick_index = 0
            return
        self.tick_index = max(0, min(index, len(self.ticks) - 1))
        self.rebuild_trail()

    def current_tick_data(self):
        if not self.ticks:
            return None
        return self.ticks[self.tick_index]

    def rebuild_trail(self):
        self.trail = []
        for i in range(0, self.tick_index + 1):
            bot_pos = self.ticks[i].get("bot_pos")
            if bot_pos:
                self.trail.append(bot_pos)

class DebugVisualizerWindow(QWidget):
    def __init__(self, debug_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Hidden Gems Debug Visualizer")
        self.model = DebugModel(debug_data)
        
        main_layout = QVBoxLayout(self)
        top_layout = QHBoxLayout()
        
        self.round_combo = QComboBox()
        rounds = self.model.rounds
        if rounds:
            for i, _ in enumerate(rounds):
                self.round_combo.addItem(f"Round {i+1}")
        else:
            self.round_combo.addItem("No rounds")
        self.round_combo.currentIndexChanged.connect(self.change_round)
        
        self.tick_slider = QSlider(Qt.Horizontal)
        self.tick_slider.setMinimum(0)
        max_ticks = max(0, len(self.model.ticks) - 1)
        self.tick_slider.setMaximum(max_ticks)
        safe_disconnect(self.tick_slider.valueChanged)
        self.tick_slider.valueChanged.connect(self.change_tick)
        
        tick_info = "Tick: 0" if max_ticks > 0 else "No debug data - run with patched runner"
        self.tick_label = QLabel(tick_info)
        
        top_layout.addWidget(QLabel("Round"))
        top_layout.addWidget(self.round_combo)
        top_layout.addWidget(QLabel("Tick"))
        top_layout.addWidget(self.tick_slider)
        top_layout.addWidget(self.tick_label)
        
        self.heatmap_toggle = QCheckBox("Show Heatmap")
        self.heatmap_toggle.stateChanged.connect(self.toggle_heatmap)
        top_layout.addWidget(self.heatmap_toggle)
        
        main_layout.addLayout(top_layout)
        
        self.maze_view = MazeView(self.model)
        main_layout.addWidget(self.maze_view)
        
        self.resize(800, 600)

    def toggle_heatmap(self, state):
        self.maze_view.show_heatmap = (state == 2)
        self.maze_view.update()

    def change_round(self, index):
        self.model.set_round(index)
        safe_disconnect(self.tick_slider.valueChanged)
        self.tick_slider.setMaximum(max(0, len(self.model.ticks) - 1))
        self.tick_slider.setValue(0)
        self.tick_slider.valueChanged.connect(self.change_tick)
        self.maze_view.update()

    def change_tick(self, index):
        self.model.set_tick(index)
        tick_data = self.model.current_tick_data()
        tick_num = tick_data.get("tick", 0) if tick_data else 0
        self.tick_label.setText(f"Tick: {tick_num}")
        self.maze_view.update()

class UI(QWidget):
    def __init__(self,main,debug):
        super().__init__()
        self.main=main
        self.debug=debug
        self.conf=os.path.join(os.path.expanduser("~"),".hidden_gems_launcher.json")
        self.last=os.path.expanduser("~")
        self.base=os.path.dirname(os.path.abspath(__file__))
        self.stages=yaml.safe_load(open(os.path.join(self.base,"stages.yaml")))
        self.customstages_path=os.path.join(self.base,"customstages.yaml")
        if os.path.exists(self.customstages_path):
            self.customstages=yaml.safe_load(open(self.customstages_path))
        else:
            self.customstages={}
        self.profile=os.path.join(self.base,"last_profile.json")
        self.m=None
        self.t=QTimer(self);self.t.timeout.connect(self.watch)
        L=QVBoxLayout(self);g=QGridLayout();r=0
        def tbox(n,d=""):
            nonlocal r; l=QLabel(n);b=QLineEdit(str(d));g.addWidget(l,r,0);g.addWidget(b,r,1);r+=1;return b
        def ibox(n,d):
            nonlocal r; l=QLabel(n);b=QSpinBox();b.setRange(0,999999);b.setValue(d);g.addWidget(l,r,0);g.addWidget(b,r,1);r+=1;return b
        def fbox(n,d):
            nonlocal r; l=QLabel(n);b=QDoubleSpinBox();b.setRange(0,999999);b.setDecimals(4);b.setValue(d);g.addWidget(l,r,0);g.addWidget(b,r,1);r+=1;return b
        def cbox(n,d):
            nonlocal r; b=QCheckBox(n);b.setChecked(d);g.addWidget(b,r,0,1,2);r+=1;return b
        self.stage=QComboBox()
        self.stage.addItem("Custom")
        for s in self.stages: self.stage.addItem(s)
        for s in self.customstages: self.stage.addItem(s)
        g.addWidget(QLabel("Stage"),r,0)
        hb=QHBoxLayout()
        hb.addWidget(self.stage)
        self.loadpreset=QPushButton("Load Preset")
        hb.addWidget(self.loadpreset)
        g.addLayout(hb,r,1)
        self.loadpreset.clicked.connect(self.apply)
        r+=1
        self.savepreset=QPushButton("Save Preset")
        g.addWidget(self.savepreset,r,1)
        self.savepreset.clicked.connect(self.save_preset)
        r+=1
        self.seed=tbox("Seed")
        self.width=ibox("Width",19)
        self.height=ibox("Height",19)
        self.gen=tbox("Generator","arena")
        self.ticks=ibox("Ticks",1000)
        self.vis=ibox("Vis Radius",10)
        self.gsr=fbox("Gem Spawn Rate",0.05)
        self.gttl=ibox("Gem TTL",300)
        self.gmax=ibox("Max Gems",1)
        self.emit=cbox("Emit Signals",False)
        self.swap=cbox("Swap Bots",False)
        self.cache=cbox("Cache",False)
        self.prof=cbox("Profile",False)
        self.det=cbox("Check Determinism",False)
        self.docker=cbox("Use Docker",False)
        self.rounds=ibox("Rounds",1)
        self.rseeds=tbox("Round Seeds")
        self.verb=ibox("Verbose",2)
        self.tps=ibox("Max TPS",15)
        self.ann=cbox("Announcer",True)
        self.tim=cbox("Show Timings",False)
        self.pause=cbox("Start Paused",False)
        self.hcol=tbox("Highlight Color","#ffffff")
        self.dbg=cbox("Enable Debug",True)
        row=QHBoxLayout()
        self.bots=QListWidget()
        col=QVBoxLayout()
        self.addb=QPushButton("Add Bot Folder")
        self.remb=QPushButton("Remove")
        col.addWidget(self.addb);col.addWidget(self.remb)
        self.addb.clicked.connect(self.add_bot)
        self.remb.clicked.connect(self.rem_bot)
        row.addWidget(self.bots);row.addLayout(col)
        g.addWidget(QLabel("Bots"),r,0);g.addLayout(row,r,1);r+=1
        L.addLayout(g)
        rr=QHBoxLayout()
        self.runb=QPushButton("Run")
        self.showd=QPushButton("Debug")
        self.showviz=QPushButton("Visualizer")
        self.patchrunner=QPushButton("Patch Runner")
        rr.addWidget(self.runb)
        rr.addWidget(self.showd)
        rr.addWidget(self.showviz)
        rr.addWidget(self.patchrunner)
        self.runb.clicked.connect(self.run)
        self.showd.clicked.connect(self.main.show_debug)
        self.showviz.clicked.connect(self.main.show_visualizer)
        self.patchrunner.clicked.connect(self.patch_runner)
        L.addLayout(rr)
        self.prog=QProgressBar();self.prog.setVisible(False)
        L.addWidget(self.prog)
        self.out=QTextEdit();self.out.setReadOnly(True)
        L.addWidget(self.out)
        self.load_conf()

    def patch_runner(self):
        try:
            runner = os.path.join(self.base, "runner.rb")
            out = os.path.join(self.base, "runner_patched.rb")
            code = open(runner, "r", encoding="utf-8").read()

            if not re.search(r'@round_debug_protocol\s*=', code):
                code = re.sub(
                    r'(@protocol\s*=\s*@bots\.map\s+\{\s*\|b\|\s*\[\]\s*\})',
                    r'\1\n@round_debug_protocol = @bots.map { |b| [] }',
                    code
                )
            if 'def compute_state_delta' not in code:
                helper_funcs = '\n\ndef compute_state_delta(prev_state, current_state)\n  delta = {added: [], removed: [], changed: []}\n  delta\nend\n\ndef compute_influence_map(width, height, bot_pos, gems)\n  map = Array.new(height) { Array.new(width, 0.0) }\n  gems.each do |gem|\n    gx, gy = gem[:position]\n    (0...height).each do |y|\n      (0...width).each do |x|\n        dist = Math.sqrt((x - gx)**2 + (y - gy)**2)\n        map[y][x] += 1.0 / (1.0 + dist) if dist > 0\n      end\n    end\n  end\n  map\nend\n\ndef compute_gem_probability_map(width, height, floor_tiles, gems, bot_pos)\n  map = Array.new(height) { Array.new(width, 0.0) }\n  base_rate = 0.05\n  floor_tiles.each do |offset|\n    x = offset & 0xFFFF\n    y = offset >> 16\n    next unless y < height && x < width\n    prob = base_rate\n    bot_dist = Math.sqrt((x - bot_pos[0])**2 + (y - bot_pos[1])**2)\n    prob *= (1.0 + bot_dist * 0.15)\n    gems.each do |gem|\n      gx, gy = gem[:position]\n      gem_dist = Math.sqrt((x - gx)**2 + (y - gy)**2)\n      prob *= (0.2 + gem_dist * 0.1) if gem_dist < 8\n    end\n    map[y][x] = prob\n  end\n  max_val = map.flatten.max\n  if max_val > 0\n    map.each_with_index do |row, y|\n      row.each_with_index do |val, x|\n        map[y][x] = val / max_val if val > 0\n      end\n    end\n  end\n  map\nend\n'
                code = code.replace('class Runner', helper_funcs + '\nclass Runner')

            if not re.search(r'@round_debug_protocol\[i\]\s*<<\s*debug_entry', code):
                enhanced_entry = '\n\nbot_pos_for_debug = @bots[i][:position]\nstate_delta = compute_state_delta(nil, nil)\nvisible_tiles = @visibility[(bot_pos_for_debug[1] << 16) | bot_pos_for_debug[0]].to_a.map { |offset| [offset & 0xFFFF, offset >> 16] }\ninfluence_map = compute_influence_map(@width, @height, bot_pos_for_debug, @gems)\ngem_spawn_probability_map = compute_gem_probability_map(@width, @height, @floor_tiles, @gems, bot_pos_for_debug)\nall_gems = @gems.map { |g| {position: g[:position], ttl: g[:ttl]} }\n\ndebug_entry = {\n  tick: @tick,\n  bots: @protocol[i].last[:bots],\n  state_delta: state_delta,\n  fov: visible_tiles,\n  influence: influence_map,\n  gem_prediction: gem_spawn_probability_map,\n  all_gems: all_gems\n}\n@round_debug_protocol[i] << debug_entry'
                code = re.sub(
                    r'(@protocol\[i\]\.last\[:bots\]\[:debug_json\]\s*=\s*debug_json)',
                    r'\1' + enhanced_entry,
                    code
                )
            if not re.search(r'results\[i\]\[:debug_protocol\]\s*=\s*@round_debug_protocol', code):
                code = re.sub(
                    r'(results\[i\]\[:stderr_log\]\s*=\s*bot\[:stderr_log\])',
                    r'\1\nresults[i][:debug_protocol] = @round_debug_protocol[i]',
                    code
                )
            if not re.search(r'round_entry\[:debug_protocol\]', code):
                code = re.sub(
                    r'(round_entry\s*=\s*\{[^}]*:response_time_stats\s*=>\s*rts,)',
                    r'\1\n:debug_protocol => results[i][:debug_protocol],',
                    code
                )

            open(out, "w", encoding="utf-8").write(code)
            self.out.append("✔ runner_patched.rb generated with enhanced debug protocol.")
        except Exception as e:
            self.out.append("Patch failed: " + str(e))
    def apply(self):
        s=self.stage.currentText()
        if s=="Custom": return
        if s in self.stages:
            st=self.stages[s]
        else:
            st=self.customstages[s]
        def setv(w,k):
            if k not in st: return
            val=parse_value(st[k])
            if isinstance(w,QLineEdit): w.setText(str(val))
            elif isinstance(w,QSpinBox): w.setValue(int(val))
            elif isinstance(w,QDoubleSpinBox): w.setValue(float(val))
            elif isinstance(w,QCheckBox): w.setChecked(bool(val))
        setv(self.width,"width")
        setv(self.height,"height")
        setv(self.gen,"generator")
        setv(self.emit,"emit_signals")
        setv(self.vis,"vis_radius")
        setv(self.gsr,"gem_spawn_rate")
        setv(self.gttl,"gem_ttl")
        setv(self.gmax,"max_gems")
        setv(self.seed,"seed")
        setv(self.ticks,"ticks")
        setv(self.rounds,"rounds")
        setv(self.rseeds,"round_seeds")
        setv(self.verb,"verbose")
        setv(self.tps,"max_tps")
    def save_preset(self):
        name=self.stage.currentText()
        if not name: return
        d={}
        d["width"]=self.width.value()
        d["height"]=self.height.value()
        d["generator"]=self.gen.text()
        d["emit_signals"]=self.emit.isChecked()
        d["vis_radius"]=self.vis.value()
        d["gem_spawn_rate"]=self.gsr.value()
        d["gem_ttl"]=self.gttl.value()
        d["max_gems"]=self.gmax.value()
        d["seed"]=self.seed.text()
        d["ticks"]=self.ticks.value()
        d["rounds"]=self.rounds.value()
        d["round_seeds"]=self.rseeds.text()
        d["verbose"]=self.verb.value()
        d["max_tps"]=self.tps.value()
        self.customstages[name]=d
        yaml.safe_dump(self.customstages,open(self.customstages_path,"w"))
    def sanitize(self,x):
        return str(x).replace("\\","/").replace("–","-").replace("—","-")
    def add_bot(self):
        p=QFileDialog.getExistingDirectory(self,"Bot Folder",self.last)
        if not p: return
        p=self.sanitize(p)
        self.last=p
        ex=[self.bots.item(i).text() for i in range(self.bots.count())]
        if p not in ex: self.bots.addItem(p)
    def rem_bot(self):
        for it in self.bots.selectedItems():
            self.bots.takeItem(self.bots.row(it))
    def load_conf(self):
        if not os.path.exists(self.conf): return
        try: c=json.load(open(self.conf,"r",encoding="utf-8"))
        except: return
        for b in c.get("bots",[]): self.bots.addItem(b)
    def save_conf(self):
        bs=[self.bots.item(i).text() for i in range(self.bots.count())]
        json.dump({"bots":bs},open(self.conf,"w",encoding="utf-8"))
    def normalize_file(self,path):
        try:
            data=open(path,"rb").read()
            if b"\r" in data:
                data=data.replace(b"\r\n",b"\n").replace(b"\r",b"\n")
                open(path,"wb").write(data)
        except: pass
    def normalize_tree(self,root,exts):
        for d,_,files in os.walk(root):
            for f in files:
                if any(f.endswith(e) for e in exts):
                    self.normalize_file(os.path.join(d,f))
    def ensure_python_flush(self,bot_py):
        if not os.path.exists(bot_py): return
        try:
            txt=open(bot_py,"r",encoding="utf-8").read()
        except: return
        if "sys.stdout.reconfigure" in txt: return
        lines=txt.splitlines()
        out=[];has_sys=False
        i=0
        while i<len(lines) and (lines[i].startswith("#!") or (lines[i].startswith("#") and "coding" in lines[i])):
            out.append(lines[i]);i+=1
        while i<len(lines) and lines[i].startswith("import"):
            line=lines[i]
            if "import sys" in line: has_sys=True
            out.append(line);i+=1
        if not has_sys:
            out.append("import sys")
        out.append("sys.stdout.reconfigure(line_buffering=True)")
        while i<len(lines):
            out.append(lines[i]);i+=1
        open(bot_py,"w",encoding="utf-8",newline="\n").write("\n".join(out)+"\n")
    def ensure_start_sh(self,bot_dir):
        start=os.path.join(bot_dir,"start.sh")
        if not os.path.exists(start):
            cmd=None
            if os.path.exists(os.path.join(bot_dir,"bot.py")): cmd="python3 bot.py"
            elif os.path.exists(os.path.join(bot_dir,"bot.rb")): cmd="ruby bot.rb"
            elif os.path.exists(os.path.join(bot_dir,"bot.js")): cmd="node bot.js"
            if cmd:
                open(start,"w",encoding="utf-8",newline="\n").write("#!/usr/bin/env bash\n"+cmd+"\n")
        self.normalize_file(start)
    def prepare_bot_folder(self,win_dir):
        win_dir=self.sanitize(win_dir)
        self.normalize_tree(win_dir,(".py",".sh"))
        bot_py=os.path.join(win_dir,"bot.py")
        self.ensure_python_flush(bot_py)
        self.ensure_start_sh(win_dir)
    def build_args(self):
        a=[]
        def add(f,v):
            if v not in("","None",None):
                a.append("--"+self.sanitize(f));a.append(self.sanitize(v))
        add("seed",self.seed.text())
        add("width",self.width.value())
        add("height",self.height.value())
        add("generator",self.gen.text())
        add("ticks",self.ticks.value())
        add("vis-radius",self.vis.value())
        add("gem-spawn",self.gsr.value())
        add("gem-ttl",self.gttl.value())
        add("max-gems",self.gmax.value())
        if self.emit.isChecked(): a.append("--emit-signals")
        if self.swap.isChecked(): a.append("--swap-bots")
        if self.cache.isChecked(): a.append("--cache")
        if self.prof.isChecked(): a.append("--profile")
        if self.det.isChecked(): a.append("--check-determinism")
        if self.docker.isChecked(): a.append("--use-docker")
        add("rounds",self.rounds.value())
        add("round-seeds",self.rseeds.text())
        add("verbose",self.verb.value())
        add("max-tps",self.tps.value())
        if self.ann.isChecked(): a.append("--announcer")
        if self.tim.isChecked(): a.append("--show-timings")
        if self.pause.isChecked(): a.append("--start-paused")
        add("highlight-color",self.hcol.text())
        if self.dbg.isChecked(): a.append("--enable-debug")
        return a
    def convert_bot_paths(self):
        out = []
        for i in range(self.bots.count()):
            path = self.sanitize(self.bots.item(i).text())
            self.prepare_bot_folder(path)
            
            if sys.platform.startswith("win"):
                wsl_path = subprocess.run(
                    ["wsl", "wslpath", path],
                    capture_output=True, text=True
                ).stdout.strip()
                if wsl_path:
                    out.append(wsl_path)
            else:
                out.append(path)
        
        return out
    def prepare_project(self):
        self.normalize_tree(self.base,(".rb",".sh"))
    def run(self):
        self.prepare_project()
        args = self.build_args()
        bots = self.convert_bot_paths()
        self.save_conf()
        
        if os.path.exists(self.profile):
            try:
                os.remove(self.profile)
            except:
                pass
        
        args += ["--write-profile-json", "last_profile.json"]
        arg = " ".join(shlex.quote(x) for x in args)
        bts = " ".join(shlex.quote(x) for x in bots)
        
        runner_file = "runner_patched.rb" if os.path.exists(
            os.path.join(self.base, "runner_patched.rb")
        ) else "runner.rb"
        
        if runner_file == "runner_patched.rb":
            self.out.append("🔧 Using PATCHED runner (debug protocol enabled)")
        else:
            self.out.append("⚠️ Using ORIGINAL runner (no debug protocol - click 'Patch Runner' first!)")
        
        if sys.platform.startswith("win"):
            runner_win = self.sanitize(os.path.join(self.base, "runner.rb"))
            runner_wsl = subprocess.run(
                ["wsl", "wslpath", runner_win],
                capture_output=True, text=True
            ).stdout.strip()
            run_dir = os.path.dirname(runner_wsl)
            cmd = f'cd "{run_dir}" && ruby {runner_file} {arg} {bts}'
            self.out.append(cmd)
            self.prog.setRange(0, 0)
            self.prog.setVisible(True)
            
            if shutil.which("wt"):
                subprocess.Popen(["wt", "-w", "0", "new-tab", "wsl", "bash", "-lc", cmd])
            else:
                subprocess.Popen(
                    ["wsl.exe", "bash", "-lc", cmd],
                    creationflags=subprocess.CREATE_NEW_CONSOLE
                )
        else:
            run_dir = self.base
            cmd = f'cd "{run_dir}" && ruby {runner_file} {arg} {bts}'
            self.out.append(cmd)
            self.prog.setRange(0, 0)
            self.prog.setVisible(True)
            
            term = None
            for candidate in ["gnome-terminal", "konsole", "xfce4-terminal", "xterm"]:
                if shutil.which(candidate):
                    term = candidate
                    break
            
            if term:
                if term == "gnome-terminal":
                    subprocess.Popen([term, "--", "bash", "-c", cmd])
                elif term in ["konsole", "xfce4-terminal"]:
                    subprocess.Popen([term, "-e", f"bash -c '{cmd}'"])
                else:
                    subprocess.Popen([term, "-e", f"bash -c '{cmd}'"])
            else:
                subprocess.Popen(cmd, shell=True)
        
        self.m = None
        self.t.start(800)
    def watch(self):
        if not os.path.exists(self.profile): return
        m=os.path.getmtime(self.profile)
        if self.m is None or m!=self.m:
            self.m=m
            self.debug.load(self.profile)
            self.main.show_debug()
            self.prog.setVisible(False)
            self.main.notify("Run Finished","Profile Loaded")
            self.t.stop()

class Main(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Hidden Gems Runner")
        self.debug=DebugDock()
        self.ui=UI(self,self.debug)
        self.setCentralWidget(self.ui)
        self.dock=QDockWidget("Debug",self)
        self.dock.setWidget(self.debug)
        self.addDockWidget(Qt.RightDockWidgetArea,self.dock)
        self.dock.hide()
        self.tray=QSystemTrayIcon(self)
        self.tray.setIcon(self.style().standardIcon(QStyle.SP_ComputerIcon))
        self.tray.show()
        self.visualizer=None
    def show_debug(self):
        self.dock.show();self.dock.raise_()
    def show_visualizer(self):
        path=None
        if self.debug.path and os.path.exists(self.debug.path):
            path=self.debug.path
        elif os.path.exists(self.ui.profile):
            path=self.ui.profile
        if not path:
            self.ui.out.append("❌ No profile data found. Run your bot first to generate data.")
            return
        self.ui.out.append(f"📊 Loading visualizer from: {path}")
        try:
            raw=json.load(open(path,"r",encoding="utf-8"))
        except Exception as e:
            self.ui.out.append(f"❌ Failed to load profile: {e}")
            return
        if isinstance(raw,list) and raw:
            data=raw[0]
        else:
            data=raw
        try:
            self.ui.out.append("🔧 Creating visualizer window...")
            if self.visualizer is not None:
                self.visualizer.setParent(None)
                self.visualizer.deleteLater()
                self.visualizer = None
            self.visualizer=DebugVisualizerWindow(data,None)
            self.visualizer.setWindowFlags(Qt.Window)
            self.visualizer.show()
            self.visualizer.raise_()
            self.visualizer.activateWindow()
            self.ui.out.append("✅ Visualizer opened!")
        except Exception as e:
            self.ui.out.append(f"❌ Visualizer error: {e}")
            import traceback
            self.ui.out.append(traceback.format_exc())
    def notify(self,t,m):
        self.tray.showMessage(t,m,QSystemTrayIcon.Information,3000)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = Main()
    window.show()
    sys.exit(app.exec())