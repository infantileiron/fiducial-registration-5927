-- 点对数据集版本链：同一数据集的整批补测更正以不可变版本保存。
-- 旧版本永不更新或删除，datasets.payload 中的 current_version 指向当前版；
-- 配准研究快照锁定 dataset_version，历史运行/复核/报告始终可追溯到对应版本。
CREATE TABLE IF NOT EXISTS dataset_versions (id TEXT PRIMARY KEY,payload TEXT NOT NULL);
