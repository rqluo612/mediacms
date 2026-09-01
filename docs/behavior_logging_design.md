# MediaCMS 单表用户行为日志

## 数据模型

系统仅使用 `UserBehaviorLog` 一张行为日志表。每行表示一个用户在一次会话中对一个视频的一次观看；同一视频再次打开时新增一行，不覆盖历史观看。

核心研究字段：

| 字段 | 定义 | 示例 |
|---|---|---|
| `user_id` | 用户/被试唯一编号 | `P001` |
| `session_id` | 一次连续使用平台的会话编号 | `S20260811001` |
| `video_id` | 当前视频唯一编号 | `V1023` |
| `algorithm_id` | 当前视频的推荐算法来源 | `CF`、`CONTENT`、`KG`、`DIRECT` |
| `play_start_time` | 视频首次开始播放时间 | `2026-08-11 19:23:15.3` |
| `play_end_time` | 本次播放结束或用户提前离开的时间 | `2026-08-11 19:23:38.7` |
| `video_duration` | 视频总时长，单位为秒 | `30.000` |
| `watch_duration` | 页面可见且实际播放的有效观看时长，单位为秒 | `23.400` |
| `skip_time` | 从视频曝光到用户提前离开当前视频所经历的时间，单位为秒 | `12.500` |
| `completion_ratio` | `watch_duration / video_duration`，限制在 0—1 | `0.78000` |
| `session_start` | 本次会话开始时间 | `2026-08-11 19:20:02` |
| `session_end` | 本次会话结束时间 | `2026-08-11 19:58:31` |
| `liked` | 本次观看是否点赞 | `0/1` |
| `commented` | 本次观看是否评论 | `0/1` |
| `shared` | 本次观看是否成功分享 | `0/1` |
| `collected` | 本次观看是否加入播放列表 | `0/1` |
| `followed` | 是否因该视频关注作者 | `0/1` |

系统辅助字段包括 `interaction_id`、`auth_user`、`media`、推荐请求信息、`end_reason`、最后活动时间、最后心跳、客户端顺序号及创建/更新时间。

## 记录规则

- 视频初始化时创建一行，曝光时间同时写入。
- 首次播放写入 `play_start_time`；心跳持续更新有效观看时长和完成率。
- 点赞、评论、复制分享链接、加入播放列表成功后更新对应布尔字段。
- 自然播放结束时 `skip_time` 为空。
- 页面关闭、导航、切换视频或会话超时时，`skip_time = play_end_time - exposure_time`。
- 同一会话空闲 5 分钟后结束，`session_end` 取最后活动时间，并更新该会话的所有日志行。
- 当前没有关注作者功能，`followed` 默认为 `False`。

## API

为兼容现有播放器，保留原行为接口路径：

- `POST /api/v1/behavior/sessions`：创建或恢复会话编号。
- `POST /api/v1/behavior/sessions/{session_id}/end`：结束会话并更新同会话全部日志。
- `POST /api/v1/behavior/interactions`：创建一条用户行为日志。
- `POST /api/v1/behavior/interactions/{interaction_id}/events`：根据播放或分享事件更新该行。
- `PATCH /api/v1/behavior/interactions/{interaction_id}/heartbeat`：更新观看时长、完成率及心跳。
- `POST /api/v1/behavior/interactions/{interaction_id}/end`：结束本次观看并计算 `skip_time`。

事件接口不再保存追加式事件明细，只更新单表中的汇总字段。
