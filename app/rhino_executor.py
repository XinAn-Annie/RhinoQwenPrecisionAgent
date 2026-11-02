from __future__ import annotations

import json
from typing import Any

from .mcp_rhino_client import RhinoMCPClient
from .modeling_spec import ModelingSpec


COLORS = {"blue": "Blue", "red": "Red", "green": "Green", "yellow": "Yellow", "gray": "Gray", "grey": "Gray", "white": "White"}


def _safe_json(spec: ModelingSpec) -> str:
    return json.dumps(spec.model_dump(mode="json"), ensure_ascii=False).replace("'''", "")


def build_creation_script(spec: ModelingSpec, intentional_error: str | None = None) -> str:
    payload = _safe_json(spec)
    error = repr(intentional_error)
    return f"""import json
import Rhino
import System
import System.Drawing

doc = __rhino_doc__
spec = json.loads(r'''{payload}''')
intentional_error = {error}
undo_id = doc.BeginUndoRecord("Rhino Qwen: " + spec["task_id"])
created = []
try:
    doc.ModelUnitSystem = Rhino.UnitSystem.Millimeters
    doc.ModelAbsoluteTolerance = float(spec["document_tolerance"])
    for index, item in enumerate(spec["objects"]):
        name = item["name"]
        layer_name = item.get("layer") or "AI_Demo"
        layer_index = doc.Layers.FindByFullPath(layer_name, -1)
        if layer_index < 0:
            layer = Rhino.DocObjects.Layer()
            layer.Name = layer_name
            layer_index = doc.Layers.Add(layer)
        p = item["position"]
        cx, cy, bz = float(p["center_x"]), float(p["center_y"]), float(p["base_z"])
        if intentional_error == "offset_second" and index == 1:
            cx += 25.0
        dims = item["dimensions"]
        primitive = item["primitive"]
        if primitive == "box":
            w, d, h = float(dims["width"]), float(dims["depth"]), float(dims["height"])
            box = Rhino.Geometry.Box(Rhino.Geometry.Plane.WorldXY,
                Rhino.Geometry.Interval(cx-w/2, cx+w/2), Rhino.Geometry.Interval(cy-d/2, cy+d/2), Rhino.Geometry.Interval(bz, bz+h))
            geometry = box.ToBrep()
        elif primitive == "cylinder":
            diameter, height = float(dims["diameter"]), float(dims["height"])
            circle = Rhino.Geometry.Circle(Rhino.Geometry.Plane(Rhino.Geometry.Point3d(cx, cy, bz), Rhino.Geometry.Vector3d.ZAxis), diameter/2)
            geometry = Rhino.Geometry.Cylinder(circle, height).ToBrep(True, True)
        elif primitive == "sphere":
            diameter = float(dims["diameter"])
            geometry = Rhino.Geometry.Sphere(Rhino.Geometry.Point3d(cx, cy, bz + diameter/2), diameter/2).ToBrep()
        elif primitive == "flange":
            outer_diameter = float(dims["outer_diameter"])
            thickness = float(dims["thickness"])
            bore_diameter = float(dims["bore_diameter"])
            pitch_diameter = float(dims["bolt_circle_diameter"])
            hole_diameter = float(dims["bolt_hole_diameter"])
            hole_count = int(dims["bolt_hole_count"])
            plane = Rhino.Geometry.Plane(Rhino.Geometry.Point3d(cx, cy, bz), Rhino.Geometry.Vector3d.ZAxis)
            body = Rhino.Geometry.Cylinder(Rhino.Geometry.Circle(plane, outer_diameter/2), thickness).ToBrep(True, True)
            cutter_plane = Rhino.Geometry.Plane(Rhino.Geometry.Point3d(cx, cy, bz-doc.ModelAbsoluteTolerance*2), Rhino.Geometry.Vector3d.ZAxis)
            cutters = [Rhino.Geometry.Cylinder(Rhino.Geometry.Circle(cutter_plane, bore_diameter/2), thickness+doc.ModelAbsoluteTolerance*4).ToBrep(True, True)]
            for hole_index in range(hole_count):
                angle = 2.0 * System.Math.PI * hole_index / hole_count
                hx = cx + System.Math.Cos(angle) * pitch_diameter/2
                hy = cy + System.Math.Sin(angle) * pitch_diameter/2
                hp = Rhino.Geometry.Plane(Rhino.Geometry.Point3d(hx, hy, bz-doc.ModelAbsoluteTolerance*2), Rhino.Geometry.Vector3d.ZAxis)
                cutters.append(Rhino.Geometry.Cylinder(Rhino.Geometry.Circle(hp, hole_diameter/2), thickness+doc.ModelAbsoluteTolerance*4).ToBrep(True, True))
            difference = Rhino.Geometry.Brep.CreateBooleanDifference([body], cutters, doc.ModelAbsoluteTolerance)
            if not difference or len(difference) != 1:
                raise RuntimeError("flange boolean difference failed")
            geometry = difference[0]
        elif primitive == "enclosure":
            w, d, h = float(dims["width"]), float(dims["depth"]), float(dims["height"])
            wall = float(dims["wall_thickness"])
            outer = Rhino.Geometry.Box(Rhino.Geometry.Plane.WorldXY,
                Rhino.Geometry.Interval(cx-w/2, cx+w/2), Rhino.Geometry.Interval(cy-d/2, cy+d/2), Rhino.Geometry.Interval(bz, bz+h)).ToBrep()
            inner = Rhino.Geometry.Box(Rhino.Geometry.Plane.WorldXY,
                Rhino.Geometry.Interval(cx-w/2+wall, cx+w/2-wall), Rhino.Geometry.Interval(cy-d/2+wall, cy+d/2-wall),
                Rhino.Geometry.Interval(bz+wall, bz+h+doc.ModelAbsoluteTolerance*2)).ToBrep()
            difference = Rhino.Geometry.Brep.CreateBooleanDifference([outer], [inner], doc.ModelAbsoluteTolerance)
            if not difference or len(difference) != 1:
                raise RuntimeError("enclosure shell boolean difference failed")
            geometry = difference[0]
        elif primitive == "stepped_shaft":
            steps = item["steps"]
            z = bz
            points = [Rhino.Geometry.Point3d(cx, cy, z), Rhino.Geometry.Point3d(cx+float(steps[0]["diameter"])/2, cy, z)]
            for step_index, step in enumerate(steps):
                radius = float(step["diameter"])/2
                z += float(step["length"])
                points.append(Rhino.Geometry.Point3d(cx+radius, cy, z))
                if step_index + 1 < len(steps):
                    next_radius = float(steps[step_index+1]["diameter"])/2
                    points.append(Rhino.Geometry.Point3d(cx+next_radius, cy, z))
            points.extend([Rhino.Geometry.Point3d(cx, cy, z), Rhino.Geometry.Point3d(cx, cy, bz)])
            profile = Rhino.Geometry.PolylineCurve(points)
            axis = Rhino.Geometry.Line(Rhino.Geometry.Point3d(cx, cy, bz), Rhino.Geometry.Point3d(cx, cy, z))
            revolved = Rhino.Geometry.RevSurface.Create(profile, axis, 0.0, 2.0*System.Math.PI)
            geometry = Rhino.Geometry.Brep.CreateFromRevSurface(revolved, True, True)
            if geometry is None:
                raise RuntimeError("stepped shaft revolve failed")
        elif primitive == "sketch_extrusion":
            points = [Rhino.Geometry.Point3d(cx+float(point["x"]), cy+float(point["y"]), bz) for point in item["sketch"]]
            points.append(points[0])
            profile = Rhino.Geometry.PolylineCurve(points)
            extrusion = Rhino.Geometry.Extrusion.Create(profile, float(dims["height"]), True)
            geometry = extrusion.ToBrep() if extrusion else None
            if geometry is None or not geometry.IsSolid:
                raise RuntimeError("closed sketch extrusion failed")
        elif primitive == "loft_surface":
            curves = []
            for section in item["sections"]:
                plane = Rhino.Geometry.Plane(Rhino.Geometry.Point3d(cx+float(section["center_x"]), cy+float(section["center_y"]), bz+float(section["z"])), Rhino.Geometry.Vector3d.ZAxis)
                plane.Rotate(Rhino.RhinoMath.ToRadians(float(section["rotation_deg"])), Rhino.Geometry.Vector3d.ZAxis)
                curves.append(Rhino.Geometry.Ellipse(plane, float(section["width"])/2, float(section["depth"])/2).ToNurbsCurve())
            lofts = Rhino.Geometry.Brep.CreateFromLoft(curves, Rhino.Geometry.Point3d.Unset, Rhino.Geometry.Point3d.Unset, Rhino.Geometry.LoftType.Normal, False)
            if not lofts or len(lofts) != 1:
                raise RuntimeError("loft surface creation failed")
            geometry = lofts[0]
        else:
            raise ValueError("unsupported primitive: " + primitive)
        treatment = item.get("edge_treatment")
        if treatment:
            selector = treatment["selector"]
            edge_indices = []
            for edge in geometry.Edges:
                tangent = edge.TangentAt(edge.Domain.Mid)
                is_vertical = abs(tangent.Z) >= 0.8
                is_horizontal = abs(tangent.Z) <= 0.2
                if selector == "all" or (selector == "vertical" and is_vertical) or (selector == "horizontal" and is_horizontal):
                    edge_indices.append(edge.EdgeIndex)
            if not edge_indices:
                raise RuntimeError("edge treatment selector matched no edges")
            radii = [float(treatment["size"])] * len(edge_indices)
            blend = Rhino.Geometry.BlendType.Fillet if treatment["type"] == "fillet" else Rhino.Geometry.BlendType.Chamfer
            treated = Rhino.Geometry.Brep.CreateFilletEdges(geometry, edge_indices, radii, radii, blend, Rhino.Geometry.RailType.RollingBall, False, doc.ModelAbsoluteTolerance, System.Math.PI/180.0)
            if not treated or len(treated) != 1 or not treated[0].IsValid:
                raise RuntimeError("edge treatment failed")
            geometry = treated[0]
        attrs = Rhino.DocObjects.ObjectAttributes()
        attrs.Name = name
        attrs.LayerIndex = layer_index
        color_name = {json.dumps(COLORS)}.get(str(item.get("color", "blue")).lower(), "Blue")
        attrs.ObjectColor = getattr(System.Drawing.Color, color_name)
        attrs.ColorSource = Rhino.DocObjects.ObjectColorSource.ColorFromObject
        attrs.SetUserString("rqpa_task_id", spec["task_id"])
        object_id = doc.Objects.AddBrep(geometry, attrs)
        if object_id == System.Guid.Empty:
            raise RuntimeError("failed to add " + name)
        created.append({{"id": str(object_id), "name": name, "layer": layer_name, "primitive": primitive}})
    doc.Views.Redraw()
    print(json.dumps({{"task_id": spec["task_id"], "created": created, "undo_record": undo_id}}))
finally:
    doc.EndUndoRecord(undo_id)
"""


class RhinoExecutor:
    def __init__(self, mcp: RhinoMCPClient):
        self.mcp = mcp

    async def execute(self, spec: ModelingSpec, slot: str | None = None, intentional_error: str | None = None) -> dict[str, Any]:
        arguments = {"script": build_creation_script(spec, intentional_error)}
        if slot:
            arguments["slot"] = slot
        return await self.mcp.call("run_python", arguments)

    async def undo(self, slot: str | None = None) -> dict[str, Any]:
        arguments = {"command": "_Undo"}
        if slot:
            arguments["slot"] = slot
        return await self.mcp.call("run_command", arguments)
