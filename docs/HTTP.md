# 阶段接口

`POST /api/stages/<stage>` 接收 `multipart/form-data`。字段 `sample=dirty`、`sample=clean` 或 `file=<CSV>` 三选一。阶段为 `intake`、`prepare`、`calculate`、`policy`、`balance`。预览不入库。

`POST /api/runs` 接收同样的输入，执行全批并返回运行报告。`GET /api/runs` 返回最近 50 批。`GET /api/runs/<id>` 查询一批和当前复核状态。

`PATCH /api/runs/<id>` 接收 `revision`、`status` 和 `note`。状态使用 `APPROVED` 或 `HELD`。冲突返回 409，客户端读取新版本后重试。

`GET /api/runs/<id>/evidence` 下载内含运行清单、行号隔离、业务证据和复核信息的 JSON。

`POST /api/monthly` 接收 JSON `{"runs": ["批次id", ...]}`，所选批次必须全部已签发，否则返回 409；批次不存在返回 404。同一批组合重复提交返回同一份月报，不会新增。`GET /api/monthly` 返回最近 50 份月报。`GET /api/monthly/<id>` 查询月报成稿：含合并后的分组滞留估计、被剔除冲突件的来源批次，以及只剩分组估计的缺证批次。
