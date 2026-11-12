import csv
import io
import os
import tempfile
import threading
import unittest

# 每个测试进程使用独立临时 SQLite，不触碰任何真实数据库。
_TMP = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
_TMP.close()
os.environ["DATABASE_URL"] = "sqlite:///" + _TMP.name
os.environ["TASK_MODE"] = "inline"
os.environ["SEED_DEMO"] = "false"

from pydantic import BaseModel  # noqa: E402
from src.utils import repository as repo  # noqa: E402
from src.services import dataset as ds_service  # noqa: E402
from src.services import study as study_service  # noqa: E402
from src.services import frame as frame_service  # noqa: E402
from src.services import run as run_service  # noqa: E402
from src.services.dataset import content_hash  # noqa: E402


def csv_text(rows):
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["id", "sx", "sy", "sz", "tx", "ty", "tz"])
    for r in rows:
        w.writerow(r)
    return out.getvalue()


GOOD_A = csv_text([
    ["P001", 0, 0, 0, 1, 0, 0],
    ["P002", 1, 0, 0, 1, 1, 0],
    ["P003", 0, 1, 0, 1, 0, 1],
    ["P004", 0, 0, 1, 2, 0, 0],
])
GOOD_B = csv_text([
    ["P001", 0, 0, 0, 1.5, 0, 0],
    ["P002", 1, 0, 0, 1.5, 1, 0],
    ["P003", 0, 1, 0, 1.5, 0, 1],
    ["P004", 0, 0, 1, 2.5, 0, 0],
])
BAD_ROW = csv_text([
    ["P001", 0, 0, 0, 1, 0, 0],
    ["P002", 1, 0, 0, 1, 1],  # 短行：缺坐标
    ["P003", 0, 1, 0, 1, 0, 1],
])
DUP_ID = csv_text([
    ["P001", 0, 0, 0, 1, 0, 0],
    ["P001", 1, 0, 0, 1, 1, 0],
    ["P003", 0, 1, 0, 1, 0, 1],
])


class DatasetInput(BaseModel):
    name: str = "测试点对集"
    source: str = "batch-a.csv"
    csv_text: str


class VersionInput(BaseModel):
    csv_text: str
    source: str = ""


class FrameInput(BaseModel):
    name: str = "测试轴系"
    dataset_id: str
    source_frame: str = "CAMERA-A"
    target_frame: str = "TABLE-B"
    unit: str = "mm"
    axes: str = "right-handed xyz"


class StudyInput(BaseModel):
    name: str = "测试研究"
    dataset_id: str
    frame_id: str
    threshold_mm: float = 0.5
    iterations: int = 100
    seed: int = 2405


class VersioningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        repo.init_db()

    def test_01_create_seeds_version_one(self):
        d = ds_service.create(DatasetInput(csv_text=GOOD_A))
        self.__class__.dataset_id = d["id"]
        self.assertEqual(d["current_version"], 1)
        versions = ds_service.list_versions(d["id"])
        self.assertEqual([v["version"] for v in versions], [1])
        self.assertEqual(versions[0]["point_count"], 4)
        self.assertEqual(versions[0]["content_hash"],
                         content_hash(d["points"], d["source"]))

    def test_02_identical_reupload_creates_no_version(self):
        did = self.__class__.dataset_id
        before = ds_service.list_versions(did)
        outcome = ds_service.update_points(did, VersionInput(csv_text=GOOD_A))
        self.assertFalse(outcome["changed"])
        after = ds_service.list_versions(did)
        self.assertEqual(len(before), len(after))
        self.assertEqual(ds_service.detail(did)["current_version"], 1)
        # 换文件名但点对内容相同：仍视为相同内容，不产生新版本。
        outcome2 = ds_service.update_points(
            did, VersionInput(csv_text=GOOD_A, source="batch-a-copy.csv"))
        self.assertFalse(outcome2["changed"])
        self.assertEqual(len(ds_service.list_versions(did)), 1)
        self.assertEqual(ds_service.detail(did)["source"], "batch-a.csv")

    def test_03_bad_batch_rejected_entirely(self):
        did = self.__class__.dataset_id
        snapshot_before = ds_service.detail(did)
        versions_before = ds_service.list_versions(did)
        for bad in (BAD_ROW, DUP_ID):
            with self.assertRaises(ValueError):
                ds_service.update_points(did, VersionInput(csv_text=bad))
        detail = ds_service.detail(did)
        self.assertEqual(detail["current_version"], snapshot_before["current_version"])
        self.assertEqual(detail["points"], snapshot_before["points"])
        self.assertEqual(
            [v["version"] for v in ds_service.list_versions(did)],
            [v["version"] for v in versions_before],
        )

    def test_04_valid_update_advances_version_and_keeps_history(self):
        did = self.__class__.dataset_id
        outcome = ds_service.update_points(
            did, VersionInput(csv_text=GOOD_B, source="batch-b.csv"))
        self.assertTrue(outcome["changed"])
        self.assertEqual(outcome["version"]["version"], 2)
        detail = ds_service.detail(did)
        self.assertEqual(detail["current_version"], 2)
        self.assertEqual(detail["source"], "batch-b.csv")
        versions = ds_service.list_versions(did)
        self.assertEqual([v["version"] for v in versions], [1, 2])
        v1 = ds_service.get_version(did, 1)
        v2 = ds_service.get_version(did, 2)
        self.assertNotEqual(v1["content_hash"], v2["content_hash"])
        # 历史版本不可变，且仍是旧点对。
        self.assertEqual(len(v1["points"]), 4)
        self.assertEqual(v1["points"][0]["target"], [1.0, 0.0, 0.0])
        self.assertEqual(v2["points"][0]["target"], [1.5, 0.0, 0.0])
        with self.assertRaises(Exception):
            ds_service.get_version(did, 99)

    def test_05_snapshot_binds_immutable_version(self):
        did = self.__class__.dataset_id
        f = frame_service.create(FrameInput(dataset_id=did))
        study_v2 = study_service.create(
            StudyInput(dataset_id=did, frame_id=f["id"], name="基于v2的研究"))
        self.assertEqual(study_v2["dataset_version"], 2)
        self.assertEqual(study_v2["snapshot"]["dataset_version"], 2)
        self.__class__.study_v2_id = study_v2["id"]
        # 再推一版，旧研究快照必须保持 v2 的点对不变。
        ds_service.update_points(did, VersionInput(csv_text=GOOD_A))
        self.assertEqual(ds_service.detail(did)["current_version"], 3)
        reloaded = repo.get("studies", study_v2["id"])
        self.assertEqual(reloaded["dataset_version"], 2)
        self.assertEqual(reloaded["snapshot"]["points"][0]["target"], [1.5, 0.0, 0.0])
        # 新研究锁定 v3。
        study_v3 = study_service.create(
            StudyInput(dataset_id=did, frame_id=f["id"], name="基于v3的研究"))
        self.assertEqual(study_v3["dataset_version"], 3)
        self.assertEqual(study_v3["snapshot"]["points"][0]["target"], [1.0, 0.0, 0.0])

    def test_06_historical_run_and_report_unchanged(self):
        sid = self.__class__.study_v2_id
        run = run_service.create(type("R", (), {"study_id": sid})())
        self.assertEqual(run["status"], "completed")
        result = run["result"]
        self.assertEqual(result["dataset_version"], 2)
        self.assertEqual(result["rows"][0]["target"], [1.5, 0.0, 0.0])
        # 数据集继续更新，已完成运行结果不受影响。
        did = self.__class__.dataset_id
        ds_service.update_points(did, VersionInput(csv_text=GOOD_B))
        run_again = repo.get("runs", run["id"])
        self.assertEqual(run_again["result"]["checksum"], result["checksum"])
        self.assertEqual(run_again["result"]["rows"], result["rows"])

    def test_07_concurrent_update_and_snapshot_see_complete_versions(self):
        # 另起一个数据集做并发压测，避免与前面的版本号假设耦合。
        d = ds_service.create(DatasetInput(csv_text=GOOD_A, name="并发数据集"))
        did = d["id"]
        f = frame_service.create(FrameInput(dataset_id=did, name="并发轴系"))
        errors = []
        seen_versions = []
        barrier = threading.Barrier(8)

        def worker(idx):
            try:
                barrier.wait()
                if idx % 2 == 0:
                    payload = csv_text([
                        ["P001", 0, 0, 0, 1 + idx, 0, 0],
                        ["P002", 1, 0, 0, 1 + idx, 1, 0],
                        ["P003", 0, 1, 0, 1 + idx, 0, 1],
                        ["P004", 0, 0, 1, 2 + idx, 0, 0],
                    ])
                    ds_service.update_points(did, VersionInput(csv_text=payload))
                else:
                    study = study_service.create(
                        StudyInput(dataset_id=did, frame_id=f["id"],
                                   name=f"并发研究{idx}"))
                    seen_versions.append(study["dataset_version"])
            except Exception as exc:  # 并发失败必须显式暴露
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        versions = ds_service.list_versions(did)
        version_nos = [v["version"] for v in versions]
        self.assertEqual(version_nos, list(range(1, len(versions) + 1)))
        # 版本号连续无空洞；每个版本内容完整且哈希自洽。
        for v in versions:
            self.assertEqual(len(v["points"]), 4)
            self.assertEqual(v["content_hash"],
                             content_hash(v["points"], v["source"]))
        # 每个快照引用的版本必须真实存在，且快照点对与该版本完全一致。
        stored = {v["version"]: v for v in versions}
        for no in seen_versions:
            self.assertIn(no, stored)
        for s in repo.all_rows("studies"):
            if s["dataset_id"] == did:
                no = s["snapshot"]["dataset_version"]
                self.assertEqual(s["snapshot"]["points"], stored[no]["points"])

    def test_08_repeated_same_content_after_many_versions(self):
        did = self.__class__.dataset_id
        current_no = ds_service.detail(did)["current_version"]
        outcome = ds_service.update_points(did, VersionInput(csv_text=GOOD_B))
        self.assertFalse(outcome["changed"])
        self.assertEqual(ds_service.detail(did)["current_version"], current_no)


if __name__ == "__main__":
    unittest.main(verbosity=2)
