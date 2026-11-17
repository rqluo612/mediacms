# 本地转码诊断与修复（2026-11-17）

环境：feature/upload-metadata；docker-compose-dev.yaml；数据库 HOST=db、NAME=mediacms。
web 和 celery_worker 均将本项目目录挂载到 /home/mediacms.io/mediacms，媒体根目录为其 media_files/。

## 根因与证据

- Supervisor 显示 celery_short/long EXITED，但启动命令是 celery multi start：启动器派生后台 worker 后正常退出0。实际有 short1、short2、long1 和 prefork 子进程；beat 正常运行。这次不能将 EXITED 等同于 worker 崩溃。
- worker 使用 /home/mediacms.io/bin/python3（虚拟环境），Celery inspect 三个节点响应正常；short1/2 订阅 short_tasks，long1 订阅 long_tasks，与 media_init/chunkize_media 和 encode_media/create_hls 的路由一致。Redis ping 正常。
- 测试媒体66（upload-b5a5a23f24b35fab9837d5f92c194f01）在01:26:49 UTC发出的七个 encode_media 任务全部记录 encoding id not found 并返回False。对应 Encoding 251–257随后存在于数据库，状态pending且task_id为空。
- 上传事务内保存Media，post_save同步初始化并创建Encoding、立即发布任务；worker先于事务提交读库，查不到记录后直接结束。这是转码一直未开始的直接原因。媒体65日志也呈现相同模式，本次未重试65。
- FFmpeg/FFprobe均为7.0.2-static。web及www-data身份worker可读同一原文件，SHA-256均为8efbf4e7336e1ddf0421da28d6c56977c3a9d94a92d489f0d95ec3a2e108ad3b；输出目录可写。

## 最小修复

files/models/media.py：Media.encode中的普通/GIF转码发布和长视频chunkize发布改用transaction.on_commit；使用partial绑定每次循环的参数。回滚不发布，自动提交模式保持即时发布。未变更Supervisor、镜像或目录权限，未清理任何队列。
tests/uploader/test_transcoding.py：新增提交前不发布、循环参数独立、回滚不发布回归测试；容器隔离内存数据库12项全部通过。

## 单视频恢复

仅选择媒体66，提交前检查三节点active/reserved/scheduled以及Redis列表、unacked记录，确认无该媒体任务；七条记录均pending且无task_id。
复用现有Encoding 251–257，force=False发送七个必要任务；没有调用Media.encode重新创建记录，没有批量重转码。
任务在02:37:42 UTC被实际worker接收，随后进入处理；媒体状态已从pending变为success。

播放页：http://localhost/view?m=upload-b5a5a23f24b35fab9837d5f92c194f01

已完成MP4输出经web/worker读取、FFprobe检查及FFmpeg完整解码验证；33秒H.264视频。用户已反馈浏览器试用正常；未取得逐分辨率及音轨专项检查记录。

## 其他发现

日志存在SMTP邮件连接错误及媒体67精灵图权限警告；它们不解释媒体66的encoding id not found。本次未改邮件或其他媒体权限。
Supervisor未直接监管后台worker是现有运维不足，但实际worker在线，本次不扩大修改范围。

最终结果：Encoding 251–257全部success；六个MP4（144至1080分辨率）均通过完整FFmpeg解码，返回码0。MP4 HTTP响应200，实际读取3111924字节；播放页HTTP响应200。没有触及其他媒体的重试。
