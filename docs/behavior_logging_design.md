# MediaCMS 用户行为日志技术设计

状态：可实施设计稿  
基线：`rqluo612/mediacms`，提交 `0ef6fc5c1912dcf2786b989af9e6dcd33cbbd80b`  
会话空闲阈值：300 秒（5 分钟）

## 1. 目标与边界

本设计记录“某用户在某次连续使用会话中，对某次视频推荐/曝光产生的一次播放与互动”。它不替换现有 `MediaAction`：

- `MediaAction` 继续承担 MediaCMS 原有点赞、踩、观看计数、举报和推荐输入。
- 新模型承担逐次曝光、有效观看时长、划走、完成率及实验行为的可追溯日志。
- 新日志是追加式事实与汇总快照的组合，不因同一用户再次观看同一视频而覆盖旧记录。
- 第一阶段只采集已登录用户。接口统一使用 `IsAuthenticated`，避免匿名浏览器会话被误当成被试。
- 生产密钥、IP、原始评论文本等敏感信息不得写入行为日志。

现有 `actions.models.MediaAction` 会在同一用户再次观看同一媒体时删除旧 `watch` 后再创建，因此不能直接扩展为实验日志表。

## 2. 已确认的数据口径

1. 会话连续 5 分钟没有有效播放、切换、播放控制或互动行为即结束。
2. 超时会话的 `session_end` 等于最后一次有效活动时间，不是最后活动时间加 5 分钟。
3. `skip_time` 是首次实际播放到用户主动划走之间的自然经过秒数，仅 `end_reason=swipe` 时有值。
4. `play_latency` 是曝光到首次实际播放之间的秒数。
5. `watch_duration` 是真正播放且页面可见时累计的有效秒数，不含暂停、后台和缓冲。
6. 同一视频再次曝光创建新的 `VideoInteractionLog`；暂停、继续、拖动和自动循环仍属于当前记录。
7. `completion_ratio=min(watch_duration/video_duration, 1)`；`watch_ratio_raw=watch_duration/video_duration`，不封顶。
8. 当前 MediaCMS 没有独立收藏夹，第一阶段“收藏”定义为加入任意播放列表。
9. 分享成功定义为成功复制链接、点击具体外部分享渠道或平台内分享接口成功；仅打开分享面板不算。
10. 可逆行为由汇总字段保存当前状态，`BehaviorEvent` 永久保存发生与撤销事件。

## 3. Django 数据模型

建议直接追加到 `actions/models.py`。为减少循环依赖，用户外键使用 `settings.AUTH_USER_MODEL`；`Media` 可沿用当前文件已有导入。

```python
import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


def new_session_id():
    return f"S{uuid.uuid4().hex.upper()}"


def new_interaction_id():
    return f"I{uuid.uuid4().hex.upper()}"


class UserViewingSession(models.Model):
    class EndReason(models.TextChoices):
        EXPLICIT = "explicit", "Explicit exit"
        IDLE_TIMEOUT = "idle_timeout", "Idle timeout"
        LOGOUT = "logout", "Logout"
        PAGE_CLOSE = "page_close", "Page close"
        SYSTEM = "system", "System cleanup"

    session_id = models.CharField(
        primary_key=True, max_length=33, default=new_session_id, editable=False
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="viewing_sessions",
    )
    # 快照字段。第一阶段取 request.user.username；导出时命名为 user_id。
    participant_code = models.CharField(max_length=64, db_index=True)
    django_session_key = models.CharField(max_length=40, blank=True, db_index=True)
    # 浏览器每次创建会话时生成；用于 POST 重试幂等，不跨超时复用。
    client_session_id = models.UUIDField(unique=True)
    session_start = models.DateTimeField(default=timezone.now, db_index=True)
    session_end = models.DateTimeField(null=True, blank=True, db_index=True)
    last_activity_at = models.DateTimeField(default=timezone.now, db_index=True)
    end_reason = models.CharField(max_length=20, choices=EndReason.choices, blank=True)
    client_info = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "-session_start"]),
            models.Index(fields=["participant_code", "-session_start"]),
            models.Index(fields=["session_end", "last_activity_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(session_end__isnull=True)
                | models.Q(session_end__gte=models.F("session_start")),
                name="behavior_session_end_after_start",
            )
        ]


class VideoInteractionLog(models.Model):
    class Algorithm(models.TextChoices):
        CF = "CF", "Collaborative filtering"
        CONTENT = "CONTENT", "Content based"
        KG = "KG", "Knowledge graph"
        LEGACY = "LEGACY", "MediaCMS legacy fallback"
        RELATED = "RELATED", "Related media"
        PLAYLIST = "PLAYLIST", "Playlist navigation"
        DIRECT = "DIRECT", "Direct page entry"
        SEARCH = "SEARCH", "Search result"
        UNKNOWN = "UNKNOWN", "Unknown"

    class EndReason(models.TextChoices):
        ENDED = "ended", "Played to end"
        SWIPE = "swipe", "User swiped away"
        NEXT = "next", "Next video"
        PREVIOUS = "previous", "Previous video"
        PAGE_CLOSE = "page_close", "Page closed"
        NAVIGATE = "navigate", "Page navigation"
        BACKGROUND_TIMEOUT = "background_timeout", "Background timeout"
        ERROR = "error", "Playback error"
        SESSION_TIMEOUT = "session_timeout", "Session timeout"

    interaction_id = models.CharField(
        primary_key=True, max_length=33, default=new_interaction_id, editable=False
    )
    session = models.ForeignKey(
        UserViewingSession, on_delete=models.CASCADE, related_name="interactions"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="video_interactions",
    )
    participant_code = models.CharField(max_length=64, db_index=True)
    media = models.ForeignKey(
        "files.Media",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="behavior_interactions",
    )
    # 即使媒体或用户被删除，快照仍支持研究数据解释。
    video_id = models.CharField(max_length=150, db_index=True)
    video_uid = models.UUIDField(null=True, blank=True)

    recommendation_request_id = models.UUIDField(null=True, blank=True, db_index=True)
    algorithm_id = models.CharField(
        max_length=20, choices=Algorithm.choices, default=Algorithm.UNKNOWN, db_index=True
    )
    algorithm_version = models.CharField(max_length=64, blank=True)
    recommendation_rank = models.PositiveIntegerField(null=True, blank=True)

    served_at = models.DateTimeField(default=timezone.now, db_index=True)
    exposure_time = models.DateTimeField(null=True, blank=True, db_index=True)
    play_start_time = models.DateTimeField(null=True, blank=True)
    play_end_time = models.DateTimeField(null=True, blank=True)
    last_heartbeat_at = models.DateTimeField(null=True, blank=True)
    end_reason = models.CharField(max_length=24, choices=EndReason.choices, blank=True)

    video_duration = models.DecimalField(
        max_digits=12, decimal_places=3, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )
    watch_duration = models.DecimalField(
        max_digits=12, decimal_places=3, default=0,
        validators=[MinValueValidator(Decimal("0"))],
    )
    skip_time = models.DecimalField(
        max_digits=12, decimal_places=3, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )
    play_latency = models.DecimalField(
        max_digits=12, decimal_places=3, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )
    completion_ratio = models.DecimalField(
        max_digits=6, decimal_places=5, default=0,
        validators=[MinValueValidator(Decimal("0"))],
    )
    watch_ratio_raw = models.DecimalField(
        max_digits=12, decimal_places=5, default=0,
        validators=[MinValueValidator(Decimal("0"))],
    )
    max_play_position = models.DecimalField(
        max_digits=12, decimal_places=3, default=0,
        validators=[MinValueValidator(Decimal("0"))],
    )
    replay_count = models.PositiveIntegerField(default=0)
    last_client_sequence = models.BigIntegerField(default=-1)

    # 当前/最终汇总状态；完整发生历史见 BehaviorEvent。
    liked = models.BooleanField(default=False)
    commented = models.BooleanField(default=False)
    shared = models.BooleanField(default=False)
    collected = models.BooleanField(default=False)
    followed = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["session", "served_at"]),
            models.Index(fields=["user", "-served_at"]),
            models.Index(fields=["participant_code", "-served_at"]),
            models.Index(fields=["video_id", "-served_at"]),
            models.Index(fields=["algorithm_id", "-served_at"]),
            models.Index(fields=["recommendation_request_id", "recommendation_rank"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(completion_ratio__gte=0)
                & models.Q(completion_ratio__lte=1),
                name="behavior_completion_ratio_0_1",
            ),
            models.CheckConstraint(
                condition=models.Q(play_end_time__isnull=True)
                | models.Q(play_start_time__isnull=True)
                | models.Q(play_end_time__gte=models.F("play_start_time")),
                name="behavior_play_end_after_start",
            ),
        ]


class BehaviorEvent(models.Model):
    class EventType(models.TextChoices):
        EXPOSURE = "exposure", "Exposure"
        PLAY = "play", "First play"
        RESUME = "resume", "Resume"
        PAUSE = "pause", "Pause"
        SEEK = "seek", "Seek"
        REPLAY = "replay", "Replay"
        END = "end", "Playback end"
        LIKE = "like", "Like"
        UNLIKE = "unlike", "Unlike"
        DISLIKE = "dislike", "Dislike"
        COMMENT = "comment", "Comment"
        COMMENT_DELETE = "comment_delete", "Comment deleted"
        SHARE = "share", "Share"
        COLLECT = "collect", "Added to playlist"
        UNCOLLECT = "uncollect", "Removed from playlist"
        FOLLOW = "follow", "Follow author"
        UNFOLLOW = "unfollow", "Unfollow author"

    class Source(models.TextChoices):
        CLIENT = "client", "Client"
        SERVER = "server", "Server"

    # 客户端为可重试事件生成 UUID；服务端业务事件也生成 UUID。
    event_id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    session = models.ForeignKey(
        UserViewingSession, on_delete=models.CASCADE, related_name="events"
    )
    interaction = models.ForeignKey(
        VideoInteractionLog,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="events",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="behavior_events",
    )
    event_type = models.CharField(max_length=24, choices=EventType.choices, db_index=True)
    source = models.CharField(max_length=10, choices=Source.choices)
    client_sequence = models.BigIntegerField(null=True, blank=True)
    client_time = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField(auto_now_add=True, db_index=True)
    payload = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["session", "received_at"]),
            models.Index(fields=["interaction", "received_at"]),
            models.Index(fields=["user", "event_type", "-received_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["interaction", "client_sequence"],
                condition=models.Q(
                    interaction__isnull=False, client_sequence__isnull=False
                ),
                name="behavior_unique_interaction_client_sequence",
            )
        ]
```

迁移文件建议为 `actions/migrations/0004_behavior_logging.py`，迁移只建表和索引，不回填历史 `MediaAction`。旧数据不具备逐次播放时长，强行回填会制造错误研究数据。

## 4. 完整字段字典

### 4.1 `UserViewingSession`

| 字段 | 类型 | 空值 | 来源 | 定义 |
|---|---|---:|---|---|
| `session_id` | `Char(33)` PK | 否 | 服务端 | `S` + UUID hex，一次连续使用会话 |
| `user` | FK User | 可 | 服务端 | MediaCMS 内部用户；删除用户后保留日志 |
| `participant_code` | `Char(64)` | 否 | 服务端 | 被试编号快照；第一阶段取用户名，如 `P001`；导出列名为 `user_id` |
| `django_session_key` | `Char(40)` | 是 | 服务端 | Django 登录会话键，不下发到导出数据 |
| `client_session_id` | UUID unique | 否 | 客户端 | 会话创建请求的幂等键 |
| `session_start` | aware datetime | 否 | 服务端 | 首次创建时间 |
| `session_end` | aware datetime | 是 | 服务端 | 显式结束或最后有效活动时间 |
| `last_activity_at` | aware datetime | 否 | 服务端 | 最近一次有效活动；心跳仅在有效播放时更新 |
| `end_reason` | choice | 是 | 服务端 | `explicit/idle_timeout/logout/page_close/system` |
| `client_info` | JSON | 否 | 客户端白名单 | `timezone`, `viewport`, `app_version`；不保存完整 UA/IP |
| `created_at/updated_at` | datetime | 否 | 服务端 | 审计字段 |

### 4.2 `VideoInteractionLog`

| 字段 | 类型 | 空值 | 来源 | 定义 |
|---|---|---:|---|---|
| `interaction_id` | `Char(33)` PK | 否 | 服务端 | 一次推荐/曝光的唯一编号 |
| `session` | FK | 否 | 服务端验证 | 所属观看会话 |
| `user` | FK | 可 | 服务端 | 内部用户；必须与会话用户一致 |
| `participant_code` | `Char(64)` | 否 | 服务端 | 被试编号快照 |
| `media` | FK Media | 可 | 服务端 | 媒体删除后置空 |
| `video_id` | `Char(150)` | 否 | 服务端 | `Media.friendly_token` 快照，如 `V1023` |
| `video_uid` | UUID | 是 | 服务端 | `Media.uid` 快照 |
| `recommendation_request_id` | UUID | 是 | 服务端 | 一次推荐列表请求编号；直接访问为空 |
| `algorithm_id` | choice | 否 | 服务端 | `CF/CONTENT/KG/LEGACY/RELATED/PLAYLIST/DIRECT/SEARCH/UNKNOWN` |
| `algorithm_version` | `Char(64)` | 是 | 服务端 | 如 `item_cf_v1` |
| `recommendation_rank` | positive int | 是 | 服务端 | 推荐列表从 1 开始的名次 |
| `served_at` | datetime | 否 | 服务端 | 推荐结果发给客户端的时间，不等于曝光 |
| `exposure_time` | datetime | 是 | 客户端事件、服务端校验 | 视频进入主要可视区域的时间 |
| `play_start_time` | datetime | 是 | 客户端事件、服务端校验 | 第一次成功触发 Video.js `playing` 的时间 |
| `play_end_time` | datetime | 是 | 客户端事件/超时补偿 | 本次播放结束时间 |
| `last_heartbeat_at` | datetime | 是 | 服务端 | 最近一次有效播放心跳接收时间 |
| `end_reason` | choice | 是 | 服务端验证 | `ended/swipe/next/previous/page_close/navigate/background_timeout/error/session_timeout` |
| `video_duration` | Decimal 秒 | 是 | 播放器 + Media 快照 | 视频总时长；优先 `player.duration()`，后端用 `Media.duration` 校验 |
| `watch_duration` | Decimal 秒 | 否 | 客户端累计、服务端单调合并 | 有效播放累计时长 |
| `skip_time` | Decimal 秒 | 是 | 服务端计算 | 仅划走：`play_end_time-play_start_time` |
| `play_latency` | Decimal 秒 | 是 | 服务端计算 | `play_start_time-exposure_time` |
| `completion_ratio` | Decimal | 否 | 服务端计算 | `min(watch_duration/video_duration, 1)` |
| `watch_ratio_raw` | Decimal | 否 | 服务端计算 | 未封顶观看比例 |
| `max_play_position` | Decimal 秒 | 否 | 客户端累计、服务端单调合并 | 本次到达过的最大播放位置 |
| `replay_count` | int | 否 | 客户端累计、服务端单调合并 | 自动循环/重新从头播放次数 |
| `last_client_sequence` | bigint | 否 | 客户端/服务端 | 防止乱序心跳回退汇总值 |
| `liked` | bool | 否 | 业务接口成功后 | 当前点赞状态 |
| `commented` | bool | 否 | 评论接口成功后 | 当前是否仍有本次交互产生的评论；事件保留删除历史 |
| `shared` | bool | 否 | 分享成功事件 | 本次交互是否发生至少一次成功分享 |
| `collected` | bool | 否 | 播放列表接口成功后 | 当前是否存在本次交互建立的播放列表收藏 |
| `followed` | bool | 否 | 未来关注接口成功后 | 当前是否关注作者；现阶段恒为 `false` |
| `created_at/updated_at` | datetime | 否 | 服务端 | 审计字段 |

### 4.3 `BehaviorEvent`

| 字段 | 类型 | 空值 | 来源 | 定义 |
|---|---|---:|---|---|
| `event_id` | UUID PK | 否 | 客户端或服务端 | 全局幂等键 |
| `session` | FK | 否 | 服务端 | 所属会话 |
| `interaction` | FK | 是 | 服务端验证 | 视频行为必须填写；会话级事件可空 |
| `user` | FK | 是 | 服务端 | 从请求用户写入，客户端不可指定 |
| `event_type` | choice | 否 | 白名单 | 曝光、播放、暂停、seek、点赞、评论、分享、收藏等 |
| `source` | choice | 否 | 服务端 | `client/server` |
| `client_sequence` | bigint | 是 | 客户端 | 单次交互内严格递增；与 interaction 联合唯一 |
| `client_time` | datetime | 是 | 客户端 | 仅用于时序分析；可信时间仍为 `received_at` |
| `received_at` | datetime | 否 | 服务端 | 接收时间 |
| `payload` | JSON | 否 | 白名单 | 位置、渠道、评论 UID、播放列表 token 等；不得保存评论正文 |

建议的 payload：

- `seek`: `from_position`, `to_position`
- `share`: `channel=copy_link/email/system_share/internal`
- `comment`: `comment_uid`
- `collect/uncollect`: `playlist_friendly_token`
- `follow/unfollow`: `author_user_id`
- `end`: `end_reason`, `position`

## 5. 服务端计算与完整性规则

1. 所有请求必须满足 `request.user == session.user == interaction.user`，否则返回 403。
2. 客户端不能上传 `participant_code`、`algorithm_id`、`algorithm_version`、排名或媒体外键。
3. 客户端时间与服务器接收时间相差超过 5 分钟时，保留 `client_time` 供诊断，但计算使用服务器时间。
4. 心跳上报累计值而非增量值。服务端使用 `max(旧值, 新值)` 合并，重复和乱序请求不会重复累计。
5. `watch_duration` 只能在 `playing=true && visible=true` 的心跳中增长；单次增长不得超过距上次心跳的服务器经过时间加 2 秒容差。
6. `video_duration` 优先使用播放器 metadata；若与 `Media.duration` 差异超过 2 秒，记录诊断字段并使用播放器值。
7. `completion_ratio`、`watch_ratio_raw`、`skip_time`、`play_latency` 只由服务端计算。
8. `exposure_time` 只写第一次；`play_start_time` 只写第一次；结束字段只允许从空变为结束状态。
9. 已结束 interaction 再收到迟到心跳，返回当前汇总但不修改结束时间。
10. `BehaviorEvent.event_id` 重复时返回原事件（200），不再创建；同一 `client_sequence` 内容冲突返回 409。
11. 每个 JSON payload 序列化后限制为 4 KiB。
12. 不把高频心跳写入 `BehaviorEvent`，只更新汇总表；离散行为才追加事件，避免日志量失控。

### 会话超时

每个行为请求先执行：

```text
if now - session.last_activity_at >= 300 seconds:
    session.session_end = session.last_activity_at
    session.end_reason = idle_timeout
    结束该会话所有未结束 interaction（end_reason=session_timeout）
    返回 409 SESSION_EXPIRED
```

另设 Celery Beat 每分钟关闭超时会话，作为没有后续请求时的补偿。任务建议放在 `files/tasks.py`，名称为 `close_idle_viewing_sessions`。

## 6. API 契约

统一前缀：`/api/v1/behavior/`  
统一权限：`IsAuthenticated`  
统一格式：JSON + Django CSRF  
客户端保存当前 `session_id` 和 `interaction_id`，业务请求通过 JSON 字段携带，不依赖可伪造的全局变量。

### 6.1 创建或幂等获取会话

`POST /api/v1/behavior/sessions`

请求：

```json
{
  "client_session_id": "a677cc08-2aa8-4ddc-83db-264d603ca379",
  "client_info": {
    "timezone": "Asia/Shanghai",
    "viewport": "390x844",
    "app_version": "web-2026.08.24"
  }
}
```

响应：新建为 201，幂等重试为 200。

```json
{
  "session_id": "S0D85D0B3DA754BD5B6A3ED77A026E45A",
  "user_id": "P001",
  "session_start": "2026-08-24T10:20:02.123+08:00",
  "last_activity_at": "2026-08-24T10:20:02.123+08:00",
  "idle_timeout_seconds": 300
}
```

同一个 `client_session_id` 已结束时返回 409：

```json
{
  "code": "SESSION_EXPIRED",
  "detail": "Create a new client_session_id."
}
```

### 6.2 显式结束会话

`POST /api/v1/behavior/sessions/{session_id}/end`

```json
{
  "reason": "page_close",
  "client_time": "2026-08-24T10:58:31.000+08:00"
}
```

响应 200：

```json
{
  "session_id": "S0D85D0B3DA754BD5B6A3ED77A026E45A",
  "session_end": "2026-08-24T10:58:31.000+08:00",
  "end_reason": "page_close"
}
```

### 6.3 推荐列表返回交互上下文

保持现有地址：

`GET /api/v1/media?show=recommended&behavior_session_id={session_id}`

每次请求由服务端生成一个 `recommendation_request_id`，并为本页每个候选创建尚未曝光的 `VideoInteractionLog`。现有媒体字段不变，增加：

```json
{
  "friendly_token": "V1023",
  "title": "Example",
  "duration": 30,
  "behavior_context": {
    "interaction_id": "I9D58B34CF6264A4AA84B80769E306115",
    "recommendation_request_id": "73959a34-318a-46d9-b043-88471b9c57d1",
    "algorithm_id": "CF",
    "algorithm_version": "item_cf_v1",
    "recommendation_rank": 1
  }
}
```

只有视频真正进入主要可视区域后才调用曝光事件，因此“已下发”和“已曝光”可区分。

### 6.4 为直接访问创建交互记录

`POST /api/v1/behavior/interactions`

用于直接打开视频详情、相关视频、播放列表或搜索结果；推荐列表不调用此接口。

```json
{
  "session_id": "S0D85D0B3DA754BD5B6A3ED77A026E45A",
  "video_id": "V1023",
  "entry_context": "DIRECT"
}
```

`entry_context` 仅允许 `DIRECT/RELATED/PLAYLIST/SEARCH`。服务端读取媒体并生成来源，响应 201：

```json
{
  "interaction_id": "I9D58B34CF6264A4AA84B80769E306115",
  "session_id": "S0D85D0B3DA754BD5B6A3ED77A026E45A",
  "video_id": "V1023",
  "algorithm_id": "DIRECT",
  "served_at": "2026-08-24T10:23:13.000+08:00"
}
```

### 6.5 追加客户端播放事件

`POST /api/v1/behavior/interactions/{interaction_id}/events`

客户端允许上传的事件类型仅为：`exposure/play/resume/pause/seek/replay/end/share`。点赞、评论和收藏必须由对应业务接口成功后在服务端写事件。

```json
{
  "event_id": "8279d70b-bb14-4534-83e4-6b59ca55e467",
  "client_sequence": 3,
  "event_type": "play",
  "client_time": "2026-08-24T10:23:15.300+08:00",
  "payload": {
    "position": 0.0,
    "visible": true
  }
}
```

响应 201；幂等重试 200：

```json
{
  "event_id": "8279d70b-bb14-4534-83e4-6b59ca55e467",
  "accepted": true,
  "interaction_id": "I9D58B34CF6264A4AA84B80769E306115"
}
```

分享事件额外要求：

```json
{
  "event_type": "share",
  "payload": {"channel": "copy_link"}
}
```

### 6.6 播放心跳

`PATCH /api/v1/behavior/interactions/{interaction_id}/heartbeat`

默认每 10 秒发送；暂停、隐藏页面时立即发送一次最终心跳。

```json
{
  "client_sequence": 8,
  "client_time": "2026-08-24T10:23:35.300+08:00",
  "playing": true,
  "visible": true,
  "current_position": 20.0,
  "watch_duration": 20.0,
  "video_duration": 30.0,
  "max_play_position": 20.0,
  "replay_count": 0
}
```

响应返回服务端规范化值：

```json
{
  "interaction_id": "I9D58B34CF6264A4AA84B80769E306115",
  "watch_duration": 20.0,
  "completion_ratio": 0.66667,
  "watch_ratio_raw": 0.66667,
  "last_heartbeat_at": "2026-08-24T10:23:35.420+08:00"
}
```

### 6.7 结束一次视频交互

`POST /api/v1/behavior/interactions/{interaction_id}/end`

```json
{
  "event_id": "f3b10b61-8ac2-401d-99fe-c10c276e8923",
  "client_sequence": 9,
  "client_time": "2026-08-24T10:23:38.700+08:00",
  "end_reason": "swipe",
  "current_position": 23.4,
  "watch_duration": 23.4,
  "video_duration": 30.0,
  "max_play_position": 23.4,
  "replay_count": 0
}
```

响应：

```json
{
  "interaction_id": "I9D58B34CF6264A4AA84B80769E306115",
  "play_start_time": "2026-08-24T10:23:15.300+08:00",
  "play_end_time": "2026-08-24T10:23:38.700+08:00",
  "video_duration": 30.0,
  "watch_duration": 23.4,
  "skip_time": 23.4,
  "play_latency": 2.3,
  "completion_ratio": 0.78,
  "watch_ratio_raw": 0.78,
  "end_reason": "swipe"
}
```

页面关闭使用 `navigator.sendBeacon` 调用 end；若未送达，由最后心跳和超时任务补偿。

### 6.8 现有业务接口的兼容扩展

以下字段均为可选，缺失时原 MediaCMS 行为完全不变：

**点赞/踩**  
`POST /api/v1/media/{video_id}/actions`

```json
{
  "type": "like",
  "interaction_id": "I9D58B34CF6264A4AA84B80769E306115"
}
```

**评论**  
`POST /api/v1/media/{video_id}/comments`

```json
{
  "text": "...",
  "interaction_id": "I9D58B34CF6264A4AA84B80769E306115"
}
```

**收藏/取消收藏**  
`PUT /api/v1/playlists/{playlist_id}`

```json
{
  "type": "add",
  "media_friendly_token": "V1023",
  "interaction_id": "I9D58B34CF6264A4AA84B80769E306115"
}
```

业务操作成功后，服务端在同一事务或 `transaction.on_commit()` 中追加事件并更新汇总字段。业务操作失败时不得写行为成功事件。

## 7. 推荐算法来源改造

### 当前问题

`files/services/recommendations.py` 的 `get_recommended_media()` 最终只返回 `Media` 列表；`_fill_with_fallback()` 把 CF 结果与 `show_recommended_media()` 兜底混合后丢失来源。缓存也只保存媒体 ID。因此不能在序列化阶段可靠反推 `algorithm_id`。

### 建议结构

增加不可变结果对象：

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class RecommendationCandidate:
    media: Media
    algorithm_id: str
    algorithm_version: str
    score: float | None = None
```

规则：

- `_rank_candidates()` 产生 `CF + _algorithm_version()`。
- `_fill_with_fallback()` 为补位项明确标记 `LEGACY + mediacms_legacy_v1`。
- 功能开关关闭、匿名用户或异常降级全部标记 `LEGACY`，不能标成 CF。
- 用户缓存由 `[media_id]` 改为包含来源的字典列表；缓存 key 已含算法版本，但单项来源仍必须保存。
- `files/views/media.py::MediaList.get()` 在推荐分支分页后，为实际返回页创建交互记录，再把 `behavior_context` 注入序列化结果。
- 当前推荐列表后仍执行 `.filter()` 的通用代码，而推荐结果是 Python list；改造时应把推荐分支与 queryset 过滤分支分开，避免带筛选参数时调用 list `.filter()`。

推荐日志只信任服务端候选对象；客户端提交的算法标识一律忽略。

## 8. 与现有代码的具体接入位置

### 8.1 后端

| 文件/位置 | 当前行为 | 修改方案 |
|---|---|---|
| `actions/models.py` | 仅 `MediaAction` | 追加三个新模型和 ID 生成器；保留原模型不变 |
| `actions/migrations/` | 3 个旧迁移 | 新建 `0004_behavior_logging.py` |
| `actions/services.py`（新增） | 不存在 | 会话校验、事件幂等、心跳合并、指标计算、业务事件写入 |
| `actions/serializers.py`（新增） | 不存在 | 六类行为接口 serializer；字段白名单和跨对象校验 |
| `actions/views.py` | 当前为空壳 | 实现 Session、Interaction、Event、Heartbeat、End APIView |
| `actions/urls.py`（新增） | 不存在 | 定义 `/api/v1/behavior/` 子路由 |
| `files/urls.py` | 所有 API 集中定义 | 增加 `path("api/v1/behavior/", include("actions.urls"))` |
| `files/services/recommendations.py` | CF 与 legacy 返回普通 Media 并混合 | 返回带来源的候选对象；缓存来源；标记降级项 |
| `files/views/media.py::MediaList.get` | 推荐结果直接序列化 | 接收 session ID；分页后创建 interaction；注入 behavior context |
| `files/serializers.py::MediaSerializer` | 无行为上下文 | 增加只读 `behavior_context`，非推荐列表为 `null` |
| `files/views/pages.py::view_media` | 打开页面即异步写 `watch` | 暂时保留旧 views 计数兼容；研究观看以播放器 `playing` 为准，后续可将旧 watch 延迟到首次 play |
| `files/views/media.py::MediaActions.post` | 异步 `save_user_action` | 接收 interaction ID 并传入 Celery；只有 `MediaAction` 成功保存后写 like/dislike 事件 |
| `files/tasks.py::save_user_action` | 写 MediaAction 与计数 | 新增可选 `interaction_id`；验证归属；成功后 `record_business_event()` |
| `files/views/comments.py::CommentDetail.post` | 保存评论 | serializer 成功后追加 comment 事件并更新 `commented` |
| `files/views/comments.py::CommentDetail.delete` | 删除评论 | 删除成功后追加 `comment_delete`；重新计算本 interaction 是否仍有评论 |
| `files/views/playlists.py::PlaylistDetail.put` | 添加/移除 PlaylistMedia | `get_or_create/delete` 成功后追加 `collect/uncollect`；当前任意列表均算收藏 |
| `files/tasks.py` | Celery 任务集合 | 增加每分钟关闭空闲会话的任务，并配置 Beat |
| `cms/settings.py` | 无行为配置 | 增加开关、300 秒超时、10 秒心跳和 payload 限制配置 |

建议配置：

```python
ENABLE_BEHAVIOR_LOGGING = False
BEHAVIOR_SESSION_IDLE_TIMEOUT_SECONDS = 300
BEHAVIOR_HEARTBEAT_INTERVAL_SECONDS = 10
BEHAVIOR_CLIENT_CLOCK_TOLERANCE_SECONDS = 300
BEHAVIOR_MAX_EVENT_PAYLOAD_BYTES = 4096
```

先默认关闭，迁移和前端部署完成后再启用。

### 8.2 前端播放器

真实播放器链路为：

```text
frontend/src/.../VideoViewer/index.js
  -> frontend/src/.../VideoJS/VideoJSEmbed.jsx
  -> 构建后的 /static/video_js/video-js.js
源代码来自 frontend-tools/video-js/src/components/video-player/VideoJSPlayer.jsx
```

`frontend-tools/video-js/src/utils/PlaybackEventHandler.js` 已集中监听 `play/pause`，是扩展埋点的首选位置。建议扩展为 `BehaviorPlaybackTracker`，监听：

- `loadedmetadata`
- `playing`（首次实际出帧，不能只监听 `play`）
- `pause`
- `waiting`
- `seeking/seeked`
- `ended`
- `error`
- `timeupdate`（只在内存累计，不逐次请求）
- `dispose`
- `document.visibilitychange`
- `window.pagehide`

累计规则：只有 `!paused && !seeking && !waiting && document.visibilityState === "visible"` 的区间进入 `watch_duration`。10 秒心跳发送累计值。`pagehide` 使用 `sendBeacon` 发 end。

需要在 `VideoJSEmbed.jsx` 注入：

```text
behaviorSessionId
behaviorInteractionId
behaviorApiBase
csrfToken
```

当前详情页是单视频页面，并没有短视频上下滑 feed。现有 `onClickNext/onClickPrevious` 通过页面跳转切换视频，因此第一阶段：

- Next 按钮：前一条 `end_reason=next`
- Previous 按钮：`end_reason=previous`
- 普通链接离开：`navigate`
- 页面关闭：`page_close`

未来新增真正的竖向滑动推荐流时，只有滑动离开才使用 `swipe`。

### 8.3 点赞、评论、收藏和分享

- 点赞：`frontend/src/static/js/utils/stores/MediaPageStore.js::requestMediaLike()` 在现有 body 中加入 `interaction_id`。事件最终由 Celery 成功写入后产生，不能在按钮点击时提前记成功。
- 评论：同文件 `SUBMIT_COMMENT` body 加入 `interaction_id`；以 201 响应为成功。
- 收藏：`ADD_MEDIA_TO_PLAYLIST/REMOVE_MEDIA_FROM_PLAYLIST` body 加入 `interaction_id`；以后端创建/删除 `PlaylistMedia` 成功为准。
- 分享复制：当前 `COPY_SHARE_LINK` 使用 `document.execCommand("copy")` 后无条件提示成功。应检查返回值，优先改用 `navigator.clipboard.writeText()`；成功后调用行为事件 API。
- Email/外部分享：`MediaShareOptions.jsx` 在具体渠道链接点击时写 `share`，仅打开 `MediaShareButton` 弹窗不写。
- `files/views/media.py::media_share` 是 LTI 课程嵌入权限接口，不是用户向外分享，不能复用为普通 `shared` 指标。

### 8.4 关注作者

当前 `users`、`files` 和前端中不存在 follow/follower 数据模型或关注 API。因此：

- 第一阶段保留 `followed` 字段和 `FOLLOW/UNFOLLOW` 事件类型，但始终为 `false`。
- 不提供一个“只写日志但不真正关注”的伪关注接口。
- 后续实现关注业务时，必须在关注事务成功后由服务端写事件，并携带来源 interaction ID，才能表达“因为该视频关注作者”。

## 9. 错误响应

统一结构：

```json
{
  "code": "SESSION_EXPIRED",
  "detail": "The viewing session has expired.",
  "field_errors": {}
}
```

| HTTP | code | 场景 |
|---:|---|---|
| 400 | `INVALID_EVENT` | 事件类型、序号或 payload 非法 |
| 401 | `AUTHENTICATION_REQUIRED` | 未登录 |
| 403 | `SESSION_OWNERSHIP_MISMATCH` | 会话或 interaction 不属于当前用户 |
| 404 | `INTERACTION_NOT_FOUND` | 编号不存在或媒体不可访问 |
| 409 | `SESSION_EXPIRED` | 5 分钟空闲后继续使用旧会话 |
| 409 | `EVENT_SEQUENCE_CONFLICT` | 相同序号对应不同内容 |
| 413 | `EVENT_PAYLOAD_TOO_LARGE` | payload 超过 4 KiB |
| 429 | `HEARTBEAT_RATE_LIMITED` | 心跳频率异常 |

## 10. 导出字段映射

最终科研数据按一条 interaction 一行导出：

| 导出列 | 数据来源 |
|---|---|
| `user_id` | `participant_code` |
| `session_id` | `session.session_id` |
| `video_id` | `video_id` 快照 |
| `algorithm_id` | `algorithm_id` |
| `play_start_time` | `play_start_time` |
| `play_end_time` | `play_end_time` |
| `video_duration` | `video_duration` |
| `watch_duration` | `watch_duration` |
| `skip_time` | `skip_time` |
| `play_latency` | `play_latency` |
| `completion_ratio` | `completion_ratio` |
| `watch_ratio_raw` | `watch_ratio_raw` |
| `session_start` | `session.session_start` |
| `session_end` | `session.session_end` |
| `liked/commented/shared/collected/followed` | 汇总布尔字段 |
| `replay_count` | `replay_count` |
| `end_reason` | `end_reason` |

时间导出为带时区 ISO 8601，不导出只有时分秒的字符串。原始事件另行导出，便于复核最终状态和计算新指标。

## 11. 实施顺序与验收

1. 新模型、迁移、Admin 只读页和配置开关。
2. 会话、直接 interaction、事件、心跳和结束 API。
3. 推荐候选来源结构与推荐 API behavior context。
4. 播放器 tracker、心跳、可见性和退出补偿。
5. 点赞、评论、播放列表和分享接入。
6. Celery 超时收尾任务。
7. CSV 导出命令与数据质量报表。
8. 小流量打开 `ENABLE_BEHAVIOR_LOGGING`。

最低验收场景：

- 观看 23.4/30 秒后离开：`watch_duration=23.4`、`completion_ratio=0.78`。
- 曝光后 2.3 秒首次播放：`play_latency=2.3`。
- 暂停 5 秒再继续：暂停时间不进入 `watch_duration`。
- 切后台 6 分钟后回来：旧会话在最后活动时间结束，创建新会话。
- 快速连续切换：每条视频有独立 interaction，前一条有明确结束原因。
- 同一心跳或事件重试：汇总不重复增加，事件不重复创建。
- CF 列表混入 legacy 兜底：每一项算法来源正确，不按整页统一标 CF。
- 点赞/评论/收藏业务失败：不得写成功事件。
- 收藏后取消：汇总为 false，同时保留 collect 与 uncollect 两个事件。
- 页面异常关闭：最多损失一个心跳间隔，服务端能关闭悬空 interaction。
