from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Position(BaseModel):
    center_x: float = 0
    center_y: float = 0
    base_z: float = 0


class ShaftStep(BaseModel):
    diameter: float = Field(gt=0)
    length: float = Field(gt=0)


class SketchPoint(BaseModel):
    x: float
    y: float


class LoftSection(BaseModel):
    z: float
    width: float = Field(gt=0)
    depth: float = Field(gt=0)
    center_x: float = 0
    center_y: float = 0
    rotation_deg: float = 0


class EdgeTreatment(BaseModel):
    type: Literal["fillet", "chamfer"]
    size: float = Field(gt=0)
    selector: Literal["all", "vertical", "horizontal"] = "vertical"


class ModelObject(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)
    primitive: Literal[
        "box", "cylinder", "sphere", "flange", "enclosure",
        "stepped_shaft", "sketch_extrusion", "loft_surface",
    ]
    dimensions: dict[str, float] = Field(default_factory=dict)
    position: Position = Field(default_factory=Position)
    steps: list[ShaftStep] = Field(default_factory=list)
    sketch: list[SketchPoint] = Field(default_factory=list)
    sections: list[LoftSection] = Field(default_factory=list)
    edge_treatment: EdgeTreatment | None = None
    layer: str = "AI_Demo"
    color: str = "blue"
    value_sources: dict[str, Literal["user", "default", "derived"]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def dimensions_match(self):
        required = {
            "box": {"width", "depth", "height"},
            "cylinder": {"diameter", "height"},
            "sphere": {"diameter"},
            "flange": {
                "outer_diameter",
                "thickness",
                "bore_diameter",
                "bolt_circle_diameter",
                "bolt_hole_diameter",
                "bolt_hole_count",
            },
            "enclosure": {"width", "depth", "height", "wall_thickness"},
            "stepped_shaft": set(),
            "sketch_extrusion": {"height"},
            "loft_surface": set(),
        }[self.primitive]
        missing = required.difference(self.dimensions)
        if missing:
            raise ValueError(f"{self.primitive} missing dimensions: {sorted(missing)}")
        if any(float(self.dimensions[k]) <= 0 for k in required):
            raise ValueError("dimensions must be positive")
        if self.primitive == "flange":
            d = self.dimensions
            count = float(d["bolt_hole_count"])
            if not count.is_integer() or not 2 <= int(count) <= 64:
                raise ValueError("flange bolt_hole_count must be an integer from 2 to 64")
            outer_radius = float(d["outer_diameter"]) / 2
            bore_radius = float(d["bore_diameter"]) / 2
            bolt_radius = float(d["bolt_hole_diameter"]) / 2
            pitch_radius = float(d["bolt_circle_diameter"]) / 2
            if bore_radius + bolt_radius >= pitch_radius:
                raise ValueError("flange bolt holes overlap the center bore")
            if pitch_radius + bolt_radius >= outer_radius:
                raise ValueError("flange bolt holes extend beyond the outer diameter")
        if self.primitive == "enclosure":
            d = self.dimensions
            wall = float(d["wall_thickness"])
            if wall * 2 >= min(float(d["width"]), float(d["depth"])):
                raise ValueError("enclosure wall_thickness leaves no interior cavity")
            if wall >= float(d["height"]):
                raise ValueError("enclosure wall_thickness must be less than height")
        if self.primitive == "stepped_shaft":
            if len(self.steps) < 2:
                raise ValueError("stepped_shaft requires at least two steps")
            self.dimensions["overall_length"] = sum(step.length for step in self.steps)
            self.dimensions["max_diameter"] = max(step.diameter for step in self.steps)
        elif self.steps:
            raise ValueError("steps are only valid for stepped_shaft")
        if self.primitive == "sketch_extrusion":
            if len(self.sketch) < 3:
                raise ValueError("sketch_extrusion requires at least three sketch points")
            area = sum(
                self.sketch[index].x * self.sketch[(index + 1) % len(self.sketch)].y
                - self.sketch[(index + 1) % len(self.sketch)].x * self.sketch[index].y
                for index in range(len(self.sketch))
            ) / 2
            if abs(area) <= 1e-9:
                raise ValueError("sketch_extrusion sketch must enclose nonzero area")
            self.dimensions["width"] = max(point.x for point in self.sketch) - min(point.x for point in self.sketch)
            self.dimensions["depth"] = max(point.y for point in self.sketch) - min(point.y for point in self.sketch)
        elif self.sketch:
            raise ValueError("sketch points are only valid for sketch_extrusion")
        if self.primitive == "loft_surface":
            if len(self.sections) < 3:
                raise ValueError("loft_surface requires at least three ordered sections")
            z_values = [section.z for section in self.sections]
            if z_values != sorted(z_values) or len(set(z_values)) != len(z_values):
                raise ValueError("loft_surface section z values must be strictly increasing")
            self.dimensions["height"] = max(z_values) - min(z_values)
            self.dimensions["section_count"] = float(len(self.sections))
        elif self.sections:
            raise ValueError("sections are only valid for loft_surface")
        if self.edge_treatment and self.primitive in {"sphere", "loft_surface"}:
            raise ValueError("edge_treatment is not supported for this primitive")
        return self


class Constraint(BaseModel):
    type: Literal[
        "bbox_dimensions",
        "closed_solid",
        "valid_geometry",
        "center_aligned_xy",
        "z_contact",
        "parallel",
        "perpendicular",
        "interference_free",
        "clearance",
    ]
    targets: list[str] = Field(min_length=1)
    tolerance: float | None = Field(default=None, ge=0)
    axis: str | None = None
    minimum: float | None = Field(default=None, ge=0)
    maximum: float | None = Field(default=None, ge=0)


class Acceptance(BaseModel):
    dimension_tolerance_mm: float = Field(0.1, gt=0)
    expected_object_count: int = Field(ge=1)
    require_valid_geometry: bool = True


class ModelingSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: str = Field(min_length=1, max_length=80)
    intent: Literal["create", "modify"]
    units: Literal["mm", "cm", "m", "inch"] = "mm"
    document_tolerance: float = Field(0.01, gt=0)
    objects: list[ModelObject] = Field(min_length=1)
    constraints: list[Constraint] = Field(default_factory=list)
    acceptance: Acceptance
    assumptions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def count_and_names(self):
        names = [obj.name for obj in self.objects]
        if len(names) != len(set(names)):
            raise ValueError("object names must be unique")
        if self.acceptance.expected_object_count != len(self.objects):
            raise ValueError("expected_object_count must equal objects length")
        known = set(names)
        for constraint in self.constraints:
            unknown = set(constraint.targets).difference(known)
            if unknown:
                raise ValueError(f"constraint targets unknown objects: {sorted(unknown)}")
        return self

    @classmethod
    def qwen_schema(cls) -> dict[str, Any]:
        schema = cls.model_json_schema()
        schema["additionalProperties"] = False
        return schema
