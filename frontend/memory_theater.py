import asyncio
import builtins
import logging
import os
import sys
import threading
import time
import types

# ─── VTK DLL Policy Workaround ──────────────────────────────────────
# Windows Application Control policies block certain VTK DLLs.
# Strategy:
#   1. Hook builtins.__import__ to catch DLL load failures for any
#      vtkmodules.* import and return a harmless stub automatically.
#   2. Pre-stub pyvista.plotting.charts (which triggers vtkChartsCore)
#      to prevent cascade failures in PyVista's plotting init.
# The hook is removed after pyvista/pyvistaqt are fully loaded.

class _VTKStubModule(types.ModuleType):
    """Fake VTK module — returns a dummy class for any attribute."""
    class _Dummy:
        def __init__(self, *a, **kw): pass
        def __init_subclass__(cls, **kw): pass
    def __getattr__(self, name):
        return self._Dummy

# Pre-stub the entire pyvista.plotting.charts module so PyVista
# never tries to load vtkChartsCore.  The stub returns a smart class
# for ANY attribute (Charts, Chart2D, ChartMPL, Axis, etc.).

class _ChartsMeta(type):
    """Metaclass: returns a dummy function for any missing class attribute."""
    def __getattr__(cls, name):
        def _dummy(*a, **kw): pass
        _dummy.__name__ = name
        _dummy.__qualname__ = f"{cls.__name__}.{name}"
        return _dummy

class _ChartsBase(metaclass=_ChartsMeta):
    def __init__(self, *a, **kw): pass

class _ChartsStubModule(types.ModuleType):
    """Returns _ChartsBase for any name imported from this module."""
    def __getattr__(self, name):
        # Return a new class named after the requested attribute
        return _ChartsMeta(name, (_ChartsBase,), {})

sys.modules["pyvista.plotting.charts"] = _ChartsStubModule("pyvista.plotting.charts")

_real_import = builtins.__import__

def _vtk_safe_import(name, *args, **kwargs):
    try:
        return _real_import(name, *args, **kwargs)
    except ImportError as e:
        err_msg = str(e)
        if "vtk" in name.lower() and ("DLL" in err_msg or "Application Control" in err_msg):
            mod = _VTKStubModule(name)
            sys.modules[name] = mod
            return mod
        raise

builtins.__import__ = _vtk_safe_import

import numpy as np
import psutil
import pyvista as pv

# ─── pyvista 0.48 / pyvistaqt 0.11 compatibility shim ───────────────
# pyvistaqt 0.11 does `from pyvista import global_theme` but pyvista 0.48
# renamed it to `global_config`.  Alias it so the import succeeds.
if not hasattr(pv, "global_theme"):
    pv.global_theme = pv.global_config
from PyQt6.QtCore import QPoint, QRectF, Qt, QThread, QTimer, pyqtSignal, QEvent
from PyQt6.QtGui import (
    QPolygonF,
    QPainterPath,
    QBrush,
    QColor,
    QConicalGradient,
    QFont,
    QFontDatabase,
    QPainter,
    QPen,
)
from PyQt6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from pyvistaqt import QtInteractor

# Restore original import now that pyvista/pyvistaqt are fully loaded
builtins.__import__ = _real_import

from backend.core.router import process_command
from backend.modules import memory as mem_module
from backend.modules.spatial_memory.graph_builder import COLOR_MAP, build_graph_from_memory
from backend.modules.spatial_memory.graph_persistence import (
    load_positions,
    migrate_memory_table,
    save_positions,
)
from backend.modules.spatial_memory.graph_physics import GraphNode, PhysicsEngine
from shared.event_bus import poll_event, push_event
from shared.graph_schemas import NodeEvent
from shared.schemas import CommandResult, JarvisEvent, Severity

logger = logging.getLogger(__name__)



# ---------------------------------------------------------
# Memory Theater Core
# ---------------------------------------------------------
class MemoryTheater:
    def __init__(self, plotter: pv.Plotter):
        self.plotter = plotter
        self.nodes: dict[str, GraphNode] = {}
        self.edges: list[tuple[str, str, float]] = []
        self.node_actors: dict[str, pv.Actor] = {}
        self.edge_actors: dict[str, pv.Actor] = {}
        self.physics: PhysicsEngine | None = None
        self._active = False
        self._lock = threading.Lock()

        # Picking is now handled globally by JarvisNativeUI
        pass

    def activate(self) -> None:
        if self._active:
            return

        engine = mem_module.get_engine()
        migrate_memory_table(engine.conn)

        self.nodes_list, self.edges = build_graph_from_memory(engine)
        self.nodes = {n.node_id: n for n in self.nodes_list}

        saved_positions = load_positions(engine.conn)
        for node in self.nodes.values():
            if node.memory_id in saved_positions:
                node.pos = saved_positions[node.memory_id]

        self.physics = PhysicsEngine(self.nodes_list, self.edges)

        self._render_all_nodes()
        self._render_all_edges()

        self.physics.start()
        self._active = True
        self.plotter.set_background(color=(0, 0, 0), top=(0, 0, 0))

    def deactivate(self) -> None:
        if not self._active:
            return

        if self.physics:
            # Trigger final save
            engine = mem_module.get_engine()
            with self.physics._lock:
                save_positions(engine.conn, list(self.physics.nodes.values()))
            self.physics.stop()
            self.physics = None

        with self._lock:
            for actor in self.node_actors.values():
                self.plotter.remove_actor(actor)
            for actor in self.edge_actors.values():
                self.plotter.remove_actor(actor)
            self.node_actors.clear()
            self.edge_actors.clear()

        self._active = False

    def _render_all_nodes(self) -> None:
        for node in self.nodes.values():
            mesh = pv.Sphere(radius=0.4 + node.mass * 0.15, center=node.pos.tolist())
            color = COLOR_MAP.get(node.category, (0.8, 0.8, 0.8))
            actor = self.plotter.add_mesh(
                mesh,
                color=color,
                opacity=0.85,
                smooth_shading=True,
                name=f"node_{node.node_id}",
            )
            self.node_actors[node.node_id] = actor

    def _render_all_edges(self) -> None:
        for id_a, id_b, weight in self.edges:
            node_a = self.nodes.get(id_a)
            node_b = self.nodes.get(id_b)
            if not node_a or not node_b:
                continue

            if weight < 0.3:
                opacity = 0.15
                color = (0.3, 0.3, 0.3)
            elif weight < 0.6:
                opacity = 0.35
                color = (0.0, 0.5, 0.8)
            else:
                opacity = 0.65
                color = (0.0, 0.9, 1.0)

            line = pv.Line(node_a.pos.tolist(), node_b.pos.tolist())
            tube = line.tube(radius=0.04)
            actor = self.plotter.add_mesh(
                tube, color=color, opacity=opacity, name=f"edge_{id_a}_{id_b}"
            )
            self.edge_actors[f"{id_a}_{id_b}"] = actor

    def on_tick(self, positions: dict[str, list]) -> None:
        if not self._active:
            return

        with self._lock:
            for node_id, pos_list in positions.items():
                node = self.nodes.get(node_id)
                if node:
                    new_pos = np.array(pos_list)
                    node.pos = new_pos
                    mesh = pv.Sphere(
                        radius=0.4 + node.mass * 0.15, center=new_pos.tolist()
                    )
                    color = COLOR_MAP.get(node.category, (0.8, 0.8, 0.8))

                    # Instead of add_mesh replacing everything natively, we just update it
                    # But the prompt says "PyVista replaces actor with same name automatically"
                    self.plotter.add_mesh(
                        mesh,
                        color=color,
                        opacity=0.85,
                        smooth_shading=True,
                        name=f"node_{node_id}",
                    )

            # Update edges
            for id_a, id_b, weight in self.edges:
                node_a = self.nodes.get(id_a)
                node_b = self.nodes.get(id_b)
                if node_a and node_b:
                    line = pv.Line(node_a.pos.tolist(), node_b.pos.tolist())
                    tube = line.tube(radius=0.04)

                    if weight < 0.3:
                        opacity, color = 0.15, (0.3, 0.3, 0.3)
                    elif weight < 0.6:
                        opacity, color = 0.35, (0.0, 0.5, 0.8)
                    else:
                        opacity, color = 0.65, (0.0, 0.9, 1.0)

                    self.plotter.add_mesh(
                        tube, color=color, opacity=opacity, name=f"edge_{id_a}_{id_b}"
                    )

        # self.plotter.interactor.Render() is handled by main timer if needed

    def on_node_event(self, event: NodeEvent) -> None:
        if not self._active:
            return

        # Stub for node spawn/pulse events
        if event.event_type == "spawn":
            # Add to memory if not there
            pass

    def on_pick(self, point):
        """Called by PyVista ray picking"""
        if not self._active:
            return

        # Find closest node to the picked point
        min_dist = float("inf")
        closest_node = None
        for node in self.nodes.values():
            dist = np.linalg.norm(node.pos - np.array(point))
            if dist < min_dist:
                min_dist = dist
                closest_node = node

        if closest_node and min_dist < 1.5:
            self.on_click(closest_node.node_id)

    def on_click(self, node_id: str) -> None:
        node = self.nodes.get(node_id)
        if not node:
            return

        # Highlight node
        mesh = pv.Sphere(
            radius=(0.4 + node.mass * 0.15) * 1.5, center=node.pos.tolist()
        )
        self.plotter.add_mesh(mesh, color="white", opacity=1.0, name=f"node_{node_id}")

        # Highlight edges
        for id_a, id_b, weight in self.edges:
            if id_a == node_id or id_b == node_id:
                node_a = self.nodes[id_a]
                node_b = self.nodes[id_b]
                line = pv.Line(node_a.pos.tolist(), node_b.pos.tolist())
                tube = line.tube(radius=0.08)
                self.plotter.add_mesh(
                    tube, color="cyan", opacity=1.0, name=f"edge_{id_a}_{id_b}"
                )

        push_event(
            JarvisEvent(
                message=f"Recall requested for {node_id}",
                severity=Severity.INFO,
                source="theater",
                data={
                    "type": "recall_request",
                    "node_id": node_id,
                    "memory_id": node.memory_id,
                },
            )
        )


