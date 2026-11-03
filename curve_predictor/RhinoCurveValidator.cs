using System;
using System.Collections.Generic;
using System.Linq;
using Rhino.Geometry;

public static class RhinoCurveValidator
{
    public static object ValidatePreview(IReadOnlyList<double[]> points, int degree, bool expectedClosed,
        double expectedWidth, double expectedHeight, double expectedDepth, double toleranceMm = 0.1)
    {
        if (points == null || points.Count != 8) return new { passed=false, reason="exactly_8_points_required" };
        if (degree < 1 || degree >= points.Count) return new { passed=false, reason="invalid_degree" };
        if (points.Any(p => p == null || p.Length != 3 || p.Any(v => double.IsNaN(v) || double.IsInfinity(v))))
            return new { passed=false, reason="non_finite_point" };
        var pts=points.Select(p=>new Point3d(p[0],p[1],p[2])).ToList();
        var curve=Curve.CreateControlPointCurve(pts,degree);
        if (curve == null || !curve.IsValid) return new { passed=false, reason="rhinocommon_invalid" };
        var box=curve.GetBoundingBox(true); var size=new[]{box.Diagonal.X,box.Diagonal.Y,box.Diagonal.Z};
        var target=new[]{expectedWidth,expectedHeight,expectedDepth}; var errors=size.Zip(target,(a,b)=>Math.Abs(a-b)).ToArray();
        var closed=curve.IsClosed; var curvatureOk=true;
        for(int i=0;i<=32;i++) { var t=curve.Domain.ParameterAt(i/32.0); var k=curve.CurvatureAt(t); if(!k.IsValid){curvatureOk=false;break;} }
        var passed=errors.Max()<=toleranceMm && closed==expectedClosed && curvatureOk;
        return new { passed, isValid=curve.IsValid, isClosed=closed, length=curve.GetLength(), bboxSize=size,
            bboxErrorsMm=errors, curvatureOk, writeAllowed=false,
            reason=passed?"await_user_confirmation":"validation_failed" };
    }
}
