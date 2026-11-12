import hashlib
import json
from src.models.entities import FiducialDataset, DatasetVersion
from src.services.points import parse_points
from src.utils import repository as repo
from src.utils.identity import new_id, now

def content_hash(points, source=None):
    # 规范化 JSON 哈希，只绑定点对内容（点对已按 ID 稳定排序）：
    # 相同点对重复上传（即使文件名不同）必然同哈希，不产生新版本。
    body = json.dumps(points,
                      sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(body.encode()).hexdigest()

def _summary(d):
    return {k: v for k, v in d.items() if k != "points"} | {"point_count": len(d["points"])}

def list_datasets():
    return [_summary(d) for d in repo.all_rows("datasets")]

def detail(id):
    return repo.get("datasets", id)

def list_versions(dataset_id):
    repo.get("datasets", dataset_id)
    rows = [v for v in repo.all_rows("dataset_versions") if v["dataset_id"] == dataset_id]
    return [dict(v, point_count=len(v["points"])) for v in sorted(rows, key=lambda v: v["version"])]

def get_version(dataset_id, version):
    repo.get("datasets", dataset_id)
    for v in repo.all_rows("dataset_versions"):
        if v["dataset_id"] == dataset_id and v["version"] == version:
            return v
    from fastapi import HTTPException
    raise HTTPException(404, "该数据集版本不存在")

def create(data):
    # 先全量解析：坏行在此抛错，尚未写任何数据。
    points = parse_points(data.csv_text)
    ts = now()
    dataset = FiducialDataset(new_id("ds"), data.name, data.source, points, 1, ts)
    with repo.transaction() as (conn, _):
        saved = repo.put("datasets", dataset, conn=conn)
        repo.put("dataset_versions",
                 DatasetVersion(new_id("dsv"), saved["id"], 1, points, data.source,
                                content_hash(points, data.source), ts),
                 conn=conn)
    return saved

def rename(id, data):
    d = repo.get("datasets", id)
    d["name"] = data.name
    return repo.put("datasets", d)

def update_points(id, data):
    """整批替换点对并推进版本。

    - 先全量解析校验，任一坏行即抛错，事务不开启，原数据保持不变；
    - 与当前版本内容哈希相同则原样返回，不产生新版本；
    - 新版本与当前指针切换在同一事务提交，并发快照只能看到完整的某一版；
    - 历史版本 append-only，永不修改，旧研究/运行/报告不受影响。
    """
    source = (data.source or "").strip() or None
    points = parse_points(data.csv_text)
    with repo.transaction() as (conn, _):
        # 行锁串行化同一数据集的并发更新，保证版本号连续且两个事务不会算出同一版本号；
        # 快照创建读取同一行的已提交版本，要么完整取到旧版、要么完整取到新版。
        dataset = repo.get("datasets", id, conn=conn, for_update=True)
        current_no = dataset.get("current_version", 1)
        current = None
        for v in repo.all_rows("dataset_versions", conn=conn):
            if v["dataset_id"] == id and v["version"] == current_no:
                current = v
                break
        if current is None:
            raise RuntimeError("当前版本记录缺失，拒绝更新以保护版本链")
        effective_source = source or current["source"]
        digest = content_hash(points, effective_source)
        if current.get("content_hash") == digest:
            # 重复上传相同内容：不产生新版本，原数据不变。
            return {"changed": False, "dataset": dataset, "version": current}
        next_no = max(v["version"] for v in repo.all_rows("dataset_versions", conn=conn)
                      if v["dataset_id"] == id) + 1
        ts = now()
        version = repo.put("dataset_versions",
                           DatasetVersion(new_id("dsv"), id, next_no, points,
                                          effective_source, digest, ts),
                           conn=conn)
        dataset["points"] = points
        dataset["source"] = effective_source
        dataset["current_version"] = next_no
        saved = repo.put("datasets", dataset, conn=conn)
        return {"changed": True, "dataset": saved, "version": version}
