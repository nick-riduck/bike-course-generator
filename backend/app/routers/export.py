from fastapi import APIRouter, HTTPException, Response
from app.models.route import GpxExportRequest
from gpx_export import GpxExporter, TcxExporter

router = APIRouter(prefix="/api/export", tags=["export"])

@router.post("/gpx")
async def export_gpx(request: GpxExportRequest):
    try:
        data = request.dict()
        export_format = request.format.lower() if request.format else "gpx"
        
        if export_format == "tcx":
            exporter = TcxExporter(data)
            xml_content = exporter.to_xml_string()
            media_type = "application/vnd.garmin.tcx+xml"
            ext = "tcx"
        else:
            exporter = GpxExporter(data)
            xml_content = exporter.to_xml_string()
            media_type = "application/gpx+xml"
            ext = "gpx"
        
        # Sanitize filename
        safe_title = "".join([c for c in request.title if c.isalnum() or c in (' ', '-', '_')]).strip()
        if not safe_title: safe_title = "route"
        filename = f"{safe_title.replace(' ', '_')}.{ext}"
        
        return Response(
            content=xml_content, 
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
    except Exception as e:
        print(f"GPX Export Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
