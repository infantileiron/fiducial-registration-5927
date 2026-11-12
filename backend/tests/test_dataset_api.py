import csv
import io
import os
import tempfile

_TMP = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
_TMP.close()
os.environ["DATABASE_URL"] = "sqlite:///" + _TMP.name
os.environ["TASK_MODE"] = "inline"
os.environ["SEED_DEMO"] = "true"

import unittest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from src.main import app  # noqa: E402


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
    ["P001", 0, 0, 0, 9, 0, 0],
    ["P002", 1, 0, 0, 9, 1, 0],
    ["P003", 0, 1, 0, 9, 0, 1],
    ["P004", 0, 0, 1, 9, 0, 0],
])
BAD = csv_text([
    ["P001", 0, 0, 0, 1],
    ["P002", 1, 0, 0, 1, 1, 0],
    ["P003", 0, 1, 0, 1, 0, 1],
])


class DatasetApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client_ctx = TestClient(app)
        cls.client = cls.client_ctx.__enter__()
        r = cls.client.post("/auth/login", json={
            "email": "analyst@haochuan.test", "password": "Fiducial2026!"})
        cls.token = r.json()["access_token"]
        cls.auth = {"Authorization": "Bearer " + cls.token}
        rv = cls.client.post("/auth/login", json={
            "email": "viewer@haochuan.test", "password": "Fiducial2026!"})
        cls.viewer_auth = {"Authorization": "Bearer " + rv.json()["access_token"]}

    @classmethod
    def tearDownClass(cls):
        cls.client_ctx.__exit__(None, None, None)

    def test_01_seeded_dataset_has_version_chain(self):
        r = self.client.get("/datasets", headers=self.auth)
        self.assertEqual(r.status_code, 200)
        seeded = next(d for d in r.json() if d["id"] == "ds-fiducials")
        self.assertEqual(seeded["current_version"], 1)
        rv = self.client.get("/datasets/ds-fiducials/versions", headers=self.auth)
        self.assertEqual([v["version"] for v in rv.json()], [1])
        # 历史版本详情包含完整点对。
        rv1 = self.client.get("/datasets/ds-fiducials/versions/1", headers=self.auth)
        self.assertEqual(rv1.status_code, 200)
        self.assertEqual(len(rv1.json()["points"]), 60)
        rv404 = self.client.get("/datasets/ds-fiducials/versions/9", headers=self.auth)
        self.assertEqual(rv404.status_code, 404)

    def test_02_full_update_lifecycle_over_http(self):
        created = self.client.post("/datasets", headers=self.auth, json={
            "name": "API版本化数据集", "source": "a.csv", "csv_text": GOOD_A})
        self.assertEqual(created.status_code, 201)
        did = created.json()["id"]

        # 重复内容：200 且 changed=false，无新版本。
        same = self.client.put(f"/datasets/{did}/points", headers=self.auth,
                               json={"csv_text": GOOD_A})
        self.assertEqual(same.status_code, 200)
        self.assertFalse(same.json()["changed"])

        # 坏行整批退回：422 且原数据不变。
        bad = self.client.put(f"/datasets/{did}/points", headers=self.auth,
                              json={"csv_text": BAD})
        self.assertEqual(bad.status_code, 422)
        detail = self.client.get(f"/datasets/{did}", headers=self.auth).json()
        self.assertEqual(detail["current_version"], 1)
        self.assertEqual(detail["points"][0]["target"], [1.0, 0.0, 0.0])

        # 有效更新：201 且 changed=true，产生 v2。
        ok = self.client.put(f"/datasets/{did}/points", headers=self.auth,
                             json={"csv_text": GOOD_B, "source": "b.csv"})
        self.assertEqual(ok.status_code, 201)
        body = ok.json()
        self.assertTrue(body["changed"])
        self.assertEqual(body["version"]["version"], 2)
        versions = self.client.get(f"/datasets/{did}/versions",
                                   headers=self.auth).json()
        self.assertEqual([v["version"] for v in versions], [1, 2])

    def test_03_viewer_cannot_update(self):
        r = self.client.put("/datasets/ds-fiducials/points",
                            headers=self.viewer_auth, json={"csv_text": GOOD_A})
        self.assertEqual(r.status_code, 403)

    def test_04_anonymous_rejected(self):
        r = self.client.put("/datasets/ds-fiducials/points",
                            json={"csv_text": GOOD_A})
        self.assertEqual(r.status_code, 401)


if __name__ == "__main__":
    unittest.main(verbosity=2)
