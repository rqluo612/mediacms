# 上传信息本地验收

上传页面为每个文件保存独立的标题、标签和简介，在点击“开始上传”前统一校验。
标签按现有 Tag 模型规则保留文字、数字和空格，合并空白并转为小写；创建时复用同名历史标签。
上传接口的 tags 参数是 JSON 字符串数组，例如 `["science", "nature"]`。
新建媒体 API 同样要求上传信息；历史媒体浏览及编辑接口没有增加限制。
视频标签至少1个、最多5个，建议填写2～3个；按清理去重后的数量校验。图片、音频、PDF不要求新增信息，不受视频字段校验限制，通过开始上传按钮提交。

Fine Uploader 使用用户 ID 和文件 UUID 生成稳定的唯一媒体标识，事务内锁定上传用户，
重复请求直接返回已有媒体。不同文件仍有独立请求参数；同一用户的服务器写入会短暂排队。
分片重发覆盖原分片，合并后的分片在事务提交后清理。
无需数据库迁移。直接媒体 API 不提供 Fine Uploader 的 UUID 重试协议。

## 本地启动

先确认 `.env`、本地设置、Compose 数据卷和端口均指向开发资源，然后按项目开发文档运行：

```sh
docker compose -f docker-compose-dev.yaml up
```

浏览 http://localhost ，登录具有上传权限的本地账号，打开上传页面。
此功能使用 Django 模板和静态 JS，不要求构建 React。
不要在连接生产数据库的环境中执行上述命令。

## 自动检查

```sh
node tests/uploader/metadata.test.cjs
docker compose -f docker-compose-dev.yaml exec -e TESTING=1 -e USE_SQLITE_TEST_DB=1 web /home/mediacms.io/bin/python manage.py test tests.uploader.test_metadata
```

后端测试仅使用隔离的内存数据库。实际 PostgreSQL 并发锁需在本地 PostgreSQL 上验收。

## 人工验收

1. 选择两个标题不同的视频，确认默认标题去掉最后的扩展名；修改各自标题和简介。
2. 输入两个共同标签并批量添加，再分别添加、删除标签，确认两行内容彼此独立。
3. 输入标签关键词，从提示中选择已有标签；也输入新标签。上传后确认媒体详情保存正确。
4. 分别测试空标题、101字标题、0个或6个标签、21字标签、301字简介；错误应明确显示且内容保留。
5. 输入 `Science, science, 自然`，确认去重为两个标签；检查不会新建已有标签的英文大小写变体。
6. 上传大于分片阈值的视频，同时上传另一视频；暂停、继续、断网恢复和手动重试，确认信息对应正确。
7. 用浏览器网络工具重放成功的分片完成请求，确认返回相同媒体 URL、媒体数量不增加。
8. 打开历史视频并编辑，确认没有新增必填标签限制。检查普通模式、深色主题和 LMS 嵌入模式。

## 已验证（2026-11-17）

- 用户浏览器验收：两个视频分别填写信息、共同标签追加不覆盖、上传信息对应正确且刷新保留；上传脚本修复后浏览器试用正常；转码修复后浏览器试用正常。
- JavaScript归一化和边界校验测试通过；jsdom加载真实Fine Uploader和模板脚本，确认浏览器导出、源码/static一致、无效表单不发请求，点击开始上传实际发送multipart HTTP请求。
- Django隔离内存数据库测试：上传相关10项、转码提交/回滚相关2项通过。
- localhost实际脚本响应包含isVideo。模板用静态脚本SHA-256内容版本更新URL，缓存版本变更测试通过。
- 本地测试媒体66的七条编码全部成功，六个MP4通过FFprobe及FFmpeg完整解码；播放页和MP4返回HTTP 200。详见[转码诊断](transcoding-local-diagnosis.md)。

## 尚未逐项验证及限制

- PostgreSQL并发上传/重复完成请求的竞争测试；自动测试仅覆盖重复完成返回已有媒体及分片覆盖合并，尚无真实并发压力验证。
- 浏览器断网恢复、暂停继续、手动重试的完整组合；标签搜索/创建、所有长度边界、历史媒体编辑、图片/音频/PDF上传未收到逐项人工验收记录。
- 深色主题、LMS嵌入模式、长视频分片转码全链路尚未专项验收。
- 视频规则当前按文件名扩展名区分；已知图片/音频/PDF扩展名豁免，未知扩展名按视频校验，未测试伪装扩展名或完整格式矩阵。
- 所有文件通过“开始上传”提交，非视频不显示新增字段且无需标签；与原有选择文件后自动上传的交互有差异。
- HTTP点击回归接收端是临时本地测试服务，不替代业务数据库持久化验收。直接媒体API没有Fine Uploader UUID重试协议。

## 浏览器回归测试

需已有frontend开发依赖（jsdom），从项目根目录运行：

```sh
node tests/uploader/browser.test.cjs
docker compose -f docker-compose-dev.yaml exec -e TESTING=1 -e USE_SQLITE_TEST_DB=1 web /home/mediacms.io/bin/python manage.py test tests.uploader.test_metadata tests.uploader.test_transcoding
```

## 提交范围检查

本次只纳入功能源码、对应static副本、回归测试及验收/诊断文档。frontend/yarn.lock的无关依赖重排保留工作区，不纳入提交；测试媒体、日志、数据库、.env及临时诊断脚本均不纳入。
