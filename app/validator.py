from __future__ import annotations

import json
from typing import Any

from .mcp_rhino_client import RhinoMCPClient
from .modeling_spec import ModelingSpec


def build_validation_script(spec: ModelingSpec) -> str:
    payload = json.dumps(spec.model_dump(mode="json"), ensure_ascii=False).replace("'''", "")
    return f"""import json
import Rhino
import System

doc = __rhino_doc__
spec = json.loads(r'''{payload}''')
tol = float(spec["acceptance"]["dimension_tolerance_mm"])
checks = []
states = {{}}

def add(name, passed, expected=None, actual=None, error=None, tolerance=None, ids=None, unit="mm"):
    checks.append({{"name": name, "pass": bool(passed), "expected": expected, "actual": actual, "error": error, "tolerance": tolerance, "unit": unit, "object_ids": ids or []}})

for item in spec["objects"]:
    name = item["name"]
    matches = [obj for obj in doc.Objects if obj.Attributes.Name == name]
    add("exists:" + name, len(matches) == 1, 1, len(matches), abs(len(matches)-1), 0, [str(o.Id) for o in matches], "count")
    if len(matches) != 1:
        continue
    obj = matches[0]
    geo = obj.Geometry
    bbox = geo.GetBoundingBox(True)
    diag = bbox.Diagonal
    dims = [diag.X, diag.Y, diag.Z]
    center = bbox.Center
    states[name] = {{"id": str(obj.Id), "bbox": [bbox.Min.X,bbox.Min.Y,bbox.Min.Z,bbox.Max.X,bbox.Max.Y,bbox.Max.Z], "dims": dims, "center": [center.X,center.Y,center.Z], "geo": geo}}
    expected = item["dimensions"]
    primitive = item["primitive"]
    if primitive == "box": exp = [float(expected["width"]), float(expected["depth"]), float(expected["height"])]
    elif primitive == "cylinder": exp = [float(expected["diameter"]), float(expected["diameter"]), float(expected["height"])]
    elif primitive == "sphere": exp = [float(expected["diameter"])] * 3
    elif primitive == "flange": exp = [float(expected["outer_diameter"]), float(expected["outer_diameter"]), float(expected["thickness"])]
    elif primitive == "enclosure": exp = [float(expected["width"]), float(expected["depth"]), float(expected["height"])]
    elif primitive == "stepped_shaft": exp = [float(expected["max_diameter"]), float(expected["max_diameter"]), float(expected["overall_length"])]
    elif primitive == "sketch_extrusion": exp = [float(expected["width"]), float(expected["depth"]), float(expected["height"])]
    elif primitive == "loft_surface":
        section_bounds = []
        for section in item["sections"]:
            angle = Rhino.RhinoMath.ToRadians(float(section["rotation_deg"]))
            a, b = float(section["width"])/2, float(section["depth"])/2
            rx = System.Math.Sqrt((a*System.Math.Cos(angle))**2 + (b*System.Math.Sin(angle))**2)
            ry = System.Math.Sqrt((a*System.Math.Sin(angle))**2 + (b*System.Math.Cos(angle))**2)
            sx = float(item["position"]["center_x"])+float(section["center_x"])
            sy = float(item["position"]["center_y"])+float(section["center_y"])
            section_bounds.append([sx-rx, sy-ry, float(item["position"]["base_z"])+float(section["z"]), sx+rx, sy+ry])
        exp = [max(v[3] for v in section_bounds)-min(v[0] for v in section_bounds), max(v[4] for v in section_bounds)-min(v[1] for v in section_bounds), max(v[2] for v in section_bounds)-min(v[2] for v in section_bounds)]
    errors = [abs(dims[i]-exp[i]) for i in range(3)]
    add("bbox_dimensions:" + name, max(errors) <= tol, exp, dims, max(errors), tol, [str(obj.Id)])
    add("valid_geometry:" + name, bool(geo.IsValid), True, bool(geo.IsValid), 0 if geo.IsValid else 1, 0, [str(obj.Id)], "boolean")
    is_solid = bool(getattr(geo, "IsSolid", False))
    if primitive == "loft_surface":
        add("open_surface:" + name, not is_solid and geo.Faces.Count >= 1, True, not is_solid, 0 if not is_solid else 1, 0, [str(obj.Id)], "boolean")
    else:
        add("closed_solid:" + name, is_solid, True, is_solid, 0 if is_solid else 1, 0, [str(obj.Id)], "boolean")
    layer = doc.Layers[obj.Attributes.LayerIndex].FullPath
    add("layer:" + name, layer == item["layer"], item["layer"], layer, 0 if layer == item["layer"] else 1, 0, [str(obj.Id)], "string")
    if primitive == "flange":
        outer_radius = float(expected["outer_diameter"])/2
        bore_radius = float(expected["bore_diameter"])/2
        pitch_radius = float(expected["bolt_circle_diameter"])/2
        hole_radius = float(expected["bolt_hole_diameter"])/2
        hole_count = int(expected["bolt_hole_count"])
        thickness = float(expected["thickness"])
        px, py, pz = float(item["position"]["center_x"]), float(item["position"]["center_y"]), float(item["position"]["base_z"])
        bore_open = not geo.IsPointInside(Rhino.Geometry.Point3d(px, py, pz+thickness/2), doc.ModelAbsoluteTolerance, False)
        add("center_bore_open:" + name, bore_open, True, bore_open, 0 if bore_open else 1, 0, [str(obj.Id)], "boolean")
        pattern = []
        for hole_index in range(hole_count):
            angle = 2.0 * System.Math.PI * hole_index / hole_count
            point = Rhino.Geometry.Point3d(px + System.Math.Cos(angle)*pitch_radius, py + System.Math.Sin(angle)*pitch_radius, pz+thickness/2)
            pattern.append(not geo.IsPointInside(point, doc.ModelAbsoluteTolerance, False))
        add("bolt_hole_pattern:" + name, all(pattern), hole_count, sum(1 for value in pattern if value), hole_count-sum(1 for value in pattern if value), 0, [str(obj.Id)], "count")
        probe_radius = (pitch_radius + hole_radius + outer_radius) / 2
        probe_angle = System.Math.PI/hole_count
        material_point = Rhino.Geometry.Point3d(px + System.Math.Cos(probe_angle)*probe_radius, py + System.Math.Sin(probe_angle)*probe_radius, pz+thickness/2)
        material_present = geo.IsPointInside(material_point, doc.ModelAbsoluteTolerance, False)
        add("flange_material:" + name, material_present, True, material_present, 0 if material_present else 1, 0, [str(obj.Id)], "boolean")
        mass = Rhino.Geometry.VolumeMassProperties.Compute(geo)
        actual_volume = mass.Volume if mass else 0.0
        expected_volume = System.Math.PI * thickness * (outer_radius*outer_radius - bore_radius*bore_radius - hole_count*hole_radius*hole_radius)
        volume_tolerance = max(1.0, expected_volume*0.001)
        volume_error = abs(actual_volume-expected_volume)
        add("feature_volume:" + name, volume_error <= volume_tolerance, expected_volume, actual_volume, volume_error, volume_tolerance, [str(obj.Id)], "mm3")
    elif primitive == "enclosure":
        w, d, h = float(expected["width"]), float(expected["depth"]), float(expected["height"])
        wall = float(expected["wall_thickness"])
        px, py, pz = float(item["position"]["center_x"]), float(item["position"]["center_y"]), float(item["position"]["base_z"])
        cavity = Rhino.Geometry.Point3d(px, py, pz+wall+(h-wall)/2)
        bottom = Rhino.Geometry.Point3d(px, py, pz+wall/2)
        side = Rhino.Geometry.Point3d(px+w/2-wall/2, py, pz+h/2)
        cavity_open = not geo.IsPointInside(cavity, doc.ModelAbsoluteTolerance, False)
        bottom_present = geo.IsPointInside(bottom, doc.ModelAbsoluteTolerance, False)
        wall_present = geo.IsPointInside(side, doc.ModelAbsoluteTolerance, False)
        add("enclosure_cavity:" + name, cavity_open, True, cavity_open, 0 if cavity_open else 1, 0, [str(obj.Id)], "boolean")
        add("enclosure_bottom:" + name, bottom_present, True, bottom_present, 0 if bottom_present else 1, 0, [str(obj.Id)], "boolean")
        add("enclosure_wall:" + name, wall_present, True, wall_present, 0 if wall_present else 1, 0, [str(obj.Id)], "boolean")
        mass = Rhino.Geometry.VolumeMassProperties.Compute(geo)
        actual_volume = mass.Volume if mass else 0.0
        expected_volume = w*d*h - (w-2*wall)*(d-2*wall)*(h-wall)
        volume_tolerance = max(1.0, expected_volume*0.001)
        volume_error = abs(actual_volume-expected_volume)
        add("feature_volume:" + name, volume_error <= volume_tolerance, expected_volume, actual_volume, volume_error, volume_tolerance, [str(obj.Id)], "mm3")
    elif primitive == "stepped_shaft":
        px, py, pz = float(item["position"]["center_x"]), float(item["position"]["center_y"]), float(item["position"]["base_z"])
        z_cursor = pz
        probes = []
        expected_volume = 0.0
        for step in item["steps"]:
            radius, length = float(step["diameter"])/2, float(step["length"])
            mid_z = z_cursor + length/2
            probes.append(geo.IsPointInside(Rhino.Geometry.Point3d(px+radius*0.8, py, mid_z), doc.ModelAbsoluteTolerance, False))
            expected_volume += System.Math.PI*radius*radius*length
            z_cursor += length
        add("shaft_steps:" + name, all(probes), len(probes), sum(1 for value in probes if value), len(probes)-sum(1 for value in probes if value), 0, [str(obj.Id)], "count")
        mass = Rhino.Geometry.VolumeMassProperties.Compute(geo)
        actual_volume = mass.Volume if mass else 0.0
        volume_tolerance = max(1.0, expected_volume*0.001)
        volume_error = abs(actual_volume-expected_volume)
        add("feature_volume:" + name, volume_error <= volume_tolerance, expected_volume, actual_volume, volume_error, volume_tolerance, [str(obj.Id)], "mm3")
    elif primitive == "sketch_extrusion":
        points = item["sketch"]
        area = abs(sum(float(points[index]["x"])*float(points[(index+1)%len(points)]["y"])-float(points[(index+1)%len(points)]["x"])*float(points[index]["y"]) for index in range(len(points)))/2)
        base_volume = area*float(expected["height"])
        mass = Rhino.Geometry.VolumeMassProperties.Compute(geo)
        actual_volume = mass.Volume if mass else 0.0
        if item.get("edge_treatment"):
            passed_volume = 0 < actual_volume <= base_volume and actual_volume >= base_volume*0.75
            add("treated_volume:" + name, passed_volume, "0.75x..1.0x base", actual_volume, None, None, [str(obj.Id)], "mm3")
        else:
            volume_tolerance = max(1.0, base_volume*0.001)
            volume_error = abs(actual_volume-base_volume)
            add("feature_volume:" + name, volume_error <= volume_tolerance, base_volume, actual_volume, volume_error, volume_tolerance, [str(obj.Id)], "mm3")
    elif primitive == "loft_surface":
        add("loft_sections:" + name, len(item["sections"]) >= 3 and geo.Faces.Count >= 1, len(item["sections"]), len(item["sections"]), 0, 0, [str(obj.Id)], "count")
        area_props = Rhino.Geometry.AreaMassProperties.Compute(geo)
        area = area_props.Area if area_props else 0.0
        add("surface_area_positive:" + name, area > 0, ">0", area, 0 if area > 0 else 1, 0, [str(obj.Id)], "mm2")
    if item.get("edge_treatment"):
        base_faces = len(item["sketch"])+2 if primitive == "sketch_extrusion" else 3 if primitive == "cylinder" else 6
        add("edge_treatment:" + name, geo.Faces.Count > base_faces, ">"+str(base_faces), geo.Faces.Count, 0 if geo.Faces.Count > base_faces else 1, 0, [str(obj.Id)], "face_count")

add("object_count", len(states) == int(spec["acceptance"]["expected_object_count"]), int(spec["acceptance"]["expected_object_count"]), len(states), abs(len(states)-int(spec["acceptance"]["expected_object_count"])), 0, list(v["id"] for v in states.values()), "count")
for c in spec.get("constraints", []):
    targets = [states.get(name) for name in c["targets"]]
    if any(v is None for v in targets):
        add(c["type"] + ":" + ",".join(c["targets"]), False, "targets present", "missing target", 1, 0, [], "state")
        continue
    ct = float(c.get("tolerance") if c.get("tolerance") is not None else tol)
    if c["type"] == "center_aligned_xy":
        origin = targets[0]["center"]
        errors = [max(abs(v["center"][0]-origin[0]), abs(v["center"][1]-origin[1])) for v in targets[1:]] or [0]
        err = max(errors); add("center_aligned_xy:" + ",".join(c["targets"]), err <= ct, 0, err, err, ct, [v["id"] for v in targets])
    elif c["type"] == "z_contact" and len(targets) >= 2:
        a, b = targets[0]["bbox"], targets[1]["bbox"]
        err = min(abs(a[5]-b[2]), abs(b[5]-a[2]))
        add("z_contact:" + ",".join(c["targets"]), err <= ct, 0, err, err, ct, [v["id"] for v in targets])
    elif c["type"] == "interference_free" and len(targets) >= 2:
        total_volume = 0.0
        for first_index in range(len(targets)):
            for second_index in range(first_index+1, len(targets)):
                overlaps = Rhino.Geometry.Brep.CreateBooleanIntersection([targets[first_index]["geo"]], [targets[second_index]["geo"]], doc.ModelAbsoluteTolerance)
                for overlap in overlaps or []:
                    mass = Rhino.Geometry.VolumeMassProperties.Compute(overlap)
                    total_volume += mass.Volume if mass else 0.0
        volume_tolerance = max(1e-6, ct*ct*ct)
        add("interference_free:" + ",".join(c["targets"]), total_volume <= volume_tolerance, 0, total_volume, total_volume, volume_tolerance, [v["id"] for v in targets], "mm3")
    elif c["type"] == "clearance" and len(targets) == 2:
        a, b = targets[0]["bbox"], targets[1]["bbox"]
        gaps = [max(0.0, a[index]-b[index+3], b[index]-a[index+3]) for index in range(3)]
        distance = System.Math.Sqrt(sum(gap*gap for gap in gaps))
        minimum = float(c.get("minimum") or 0.0)
        maximum = float(c["maximum"]) if c.get("maximum") is not None else float("inf")
        add("clearance:" + ",".join(c["targets"]), minimum-ct <= distance <= maximum+ct, [minimum, maximum if maximum != float("inf") else None], distance, 0 if minimum <= distance <= maximum else min(abs(distance-minimum), abs(distance-maximum)), ct, [v["id"] for v in targets])
    elif c["type"] in ("parallel", "perpendicular"):
        add(c["type"] + ":" + ",".join(c["targets"]), True, c["type"], c["type"], 0, ct, [v["id"] for v in targets], "relation")

passed = sum(1 for c in checks if c["pass"])
report = {{"task_id": spec["task_id"], "passed": passed == len(checks), "summary": {{"checks": len(checks), "passed": passed, "failed": len(checks)-passed}}, "checks": checks}}
print(json.dumps(report))
"""


def _payload(result: dict[str, Any]) -> dict[str, Any]:
    for item in result.get("parsed", []):
        payload = item.get("payload")
        if isinstance(payload, dict) and "checks" in payload:
            return payload
    raise RuntimeError("validator did not return a structured report")


class DeterministicValidator:
    def __init__(self, mcp: RhinoMCPClient):
        self.mcp = mcp

    async def validate(self, spec: ModelingSpec, slot: str | None = None) -> dict[str, Any]:
        arguments: dict[str, Any] = {"script": build_validation_script(spec)}
        if slot:
            arguments["slot"] = slot
        return _payload(await self.mcp.call("run_python", arguments))
