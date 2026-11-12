from fastapi.responses import JSONResponse
from src.services import dataset as service
def list_items(): return service.list_datasets()
def detail(id): return service.detail(id)
def versions(id): return service.list_versions(id)
def version_detail(id, version): return service.get_version(id, version)
def create(data): return service.create(data)
def update_points(id, data):
    # changed=true（新版本写入）返回 201；内容相同未产生新版本返回 200。
    outcome = service.update_points(id, data)
    status = 201 if outcome["changed"] else 200
    return JSONResponse(
        status_code=status,
        content={"changed": outcome["changed"],
                 "dataset": outcome["dataset"],
                 "version": {k: v for k, v in outcome["version"].items() if k != "points"} |
                            {"point_count": len(outcome["version"]["points"])}},
    )
