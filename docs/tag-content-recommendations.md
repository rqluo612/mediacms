# 标签＋文本内容推荐

## 接入与本地基线

开发分支：feature/tag-content-recommendations，基于c03c0e6，保留上传功能及frontend/yarn.lock既有改动。
核对GitHub配置远端origin（rqluo612/mediacms）的main引用为678f851，与本地origin/main一致；开始实现前，本地HEAD比它多30862e6和c03c0e6两个上传/转码提交。未将上游MediaCMS的实现假定为本地实现。

仍使用files/services/recommendations.py中的get_recommended_media作为唯一入口。推荐列表和媒体详情的autoplay_next均复用它；后者传入可选current_media_id，仅CONTENT在截取前使用。CF分支忽略此参数，保持原来的跳过当前视频与排名行为。
RELATED_MEDIA_STRATEGY、show_related_media、show_recommended_media、CF评分/汇总/补足/重复规则/缓存/定时任务及重建命令没有修改。

## 配置与依赖

加载顺序：cms/settings.py默认值 → cms/local_settings.py → DEVELOPMENT_MODE非空时的cms/dev_settings.py → 最终配置校验。dev_settings当前没有覆盖推荐配置。
仓库中cms/local_settings.py是实际挂载使用的配置；deploy/docker/local_settings.py是部署模板，两者均增加环境变量读取。不能只修改模板而忽略实际cms/local_settings.py。
.env.production.example提供配置示例。实现阶段未修改实际.env、未自动启用CONTENT；本次已按用户授权切换本地验收环境，当前策略content，详见末节。

| 环境变量 | 默认 | 说明 |
| --- | --- | --- |
| RECOMMENDATION_STRATEGY | 空 | 空/未设置沿用ENABLE_COLLABORATIVE_FILTERING；cf/content/legacy显式覆盖旧开关 |
| CONTENT_RECOMMENDATION_ALPHA | 0.5 | 标签通道权重，有限数值0～1 |
| CONTENT_RECOMMENDATION_WATCH_WEIGHT | 1 | 非负有限数值 |
| CONTENT_RECOMMENDATION_LIKE_WEIGHT | 3 | 非负有限数值 |
| CONTENT_RECOMMENDATION_PLAYLIST_WEIGHT | 4 | 非负有限数值 |

Python设置CONTENT_RECOMMENDATION_WEIGHTS是watch/like/playlist字典。非法策略、alpha或权重在最终配置加载时抛ImproperlyConfigured；运行时策略分发也检查策略。LEGACY继续使用空algorithm_version。

唯一新增依赖是jieba==0.42.1（requirements.txt），不引入sklearn、向量数据库或大模型。TF-IDF/稀疏向量计算使用标准库。实现阶段仅在本地web容器虚拟环境安装jieba用于测试；本次验收又构建仅增加jieba的本地派生镜像，详见末节；未安装宿主依赖。
持久使用时需构建包含新requirements的开发镜像。以下是供人工执行的命令，本轮没有执行构建或重建服务：

```sh
# migrations服务拥有Dockerfile base目标的构建定义，生成web使用的开发镜像。
docker compose -f docker-compose-dev.yaml build migrations
```

启用：手动在本地.env设置RECOMMENDATION_STRATEGY=content（alpha/权重可省略），然后：

```sh
docker compose -f docker-compose-dev.yaml up -d --no-deps --force-recreate web
```

切回CF：将同一.env配置改为RECOMMENDATION_STRATEGY=cf，再执行同一条force-recreate命令。恢复旧开关控制：设RECOMMENDATION_STRATEGY=，同样重建web容器。
.env通过env_file在创建容器时载入，docker compose restart不会重新读取.env；Python配置代码在本地bind mount中可见，runserver通常自动重载，如只修改Python配置可明确执行`docker compose -f docker-compose-dev.yaml restart web`。推荐在线计算只由web执行；本功能没有新增worker任务，也不需重建CF缓存。以上命令不启动migrations、不删除卷、不清空Redis。

## 算法与过滤

- 行为只取当前用户MediaAction的watch/like，以及PlaylistMedia；按用户/视频/行为类型去重，跨列表收藏只计一次。点踩排除该视频并移除其全部正向贡献；不把UserBehaviorLog的时长或曝光计作额外权重。
- 种子和候选使用当前公开、已审核、encoding_status=success、listable的视频集合。私有或已失去候选资格的历史视频不进入画像/IDF语料。
- 标签使用上传和Tag.save同一个字母/数字/空格清理函数，合并空白、lower，规范化去重后二值化、L2归一化；历史标签不强制执行新上传长度限制。
- 文本只拼标题和简介（不重复拼标签），去HTML并解码实体、小写化，jieba精确模式分词，保留文字数字词项。使用原始词频，平滑IDF为log((1+N)/(1+df))+1，再L2归一化。
- 每次请求在全部合格公开视频上拟合一套词表/IDF，包括已看种子和候选；历史和候选从同一批向量中取值。未使用私有视频或独立拟合历史词表。空词表生成空向量。
- 各通道对有非零向量的历史视频按行为总权重求加权平均，画像再L2归一化，用点积计算余弦。分数为alpha*标签余弦+(1-alpha)*文本余弦。
- 某通道画像或候选向量为零则缺失，仅在向量有效且通道权重大于0的通道内重新归一化权重。有效向量的相似度为0仍计入分母；alpha为0/1不会偷偷启用被关闭的通道。
- 排除已看、已点赞、已收藏、点踩及当前视频后再截取；正分结果按分数降序、发布时间降序、ID升序，允许短列表，不混入热门或CF。
- 无画像/无正分匹配时，用同样过滤口径按views、likes、发布时间降序和ID升序回退热门；耗尽返回空列表，不补回已看。正分结果标记CONTENT/tag_text_content_v2，回退标记LEGACY/空版本。
- 实时批量读取（用户行为、收藏、视频+user、tags共至多4次服务查询），没有CONTENT持久索引、排序缓存、缓存失效机制或CF缓存访问。内容编辑后下一次请求重算。原有签名归因缓存继续用于日志归因，不是CONTENT排序缓存。
- 签名、请求UUID、分页后排名、自动下一条及UserBehaviorLog写入均复用已有实现；不新增表，不改变分页排名含义。

## 测试与验收

自动测试使用独立PostgreSQL测试库（随机唯一名称）、临时媒体目录、内存缓存，不写真实视频、标签、用户行为或Redis。无需重建CF缓存：

```sh
docker compose -f docker-compose-dev.yaml exec -T web /home/mediacms.io/bin/python tests/run_recommendation_tests.py
# 只跑新增测试
docker compose -f docker-compose-dev.yaml exec -T web /home/mediacms.io/bin/python tests/run_recommendation_tests.py tests.services.test_content_recommendations
```

原CF接口测试使用to_tsvector，因此完整测试不能使用SQLite。测试中的随机密码和合成视频路径不是真实凭据或测试媒体文件。

浏览器验收（本地现已获授权启用CONTENT，具体当前状态见末节）：

1. 登录本地账号访问http://localhost，打开推荐列表；检查Network响应中的behavior_context是否为CONTENT/tag_text_content_v2，正分不足时允许短列表。
2. 在独立测试数据中准备同标签不同文本、同文本不同标签、仅一个通道的候选；分别设置alpha=0/0.5/1并重建web容器，比较排序。
3. 播放并点赞/收藏视频，再请求列表，确认排除；修改候选标题/简介/标签后刷新确认重新计算。
4. 在媒体详情检查autoplay_next排除当前视频；播放推荐项后核对行为日志CONTENT、版本、请求编号和排名。无匹配时应是LEGACY且版本为空。
5. 设置cf并重建web，确认原CF行为；设置空值确认旧开关仍控制算法。related_media应保持原行为。

## 局限

当前标签覆盖低、标题可能仍是文件名，不能据此声称推荐效果好。jieba词典分词可能把短语视为一个词，不提供同义词或语义推理；未增加停用词或时间衰减。实时拟合适合当前小规模，全库增长后需单独测量CPU/内存和延迟。浏览器逐项切换alpha、冷启动与断网场景尚未人工验收。

## 本轮验证结果（2026-11-17）

- 新增26项测试全部通过，涵盖真实环境配置加载、缺失配置兼容、策略分发、CF缓存隔离、中文英文分词/TF-IDF、双通道/alpha端点、去重/点踩、过滤/回退/耗尽、实时编辑、查询次数、列表/下一条/CONTENT签名落库。
- 初轮联合回归57项中有1项旧CF测试与现行规则不一致：它要求始终不出现已交互媒体，而最新产品规则明确允许未看候选耗尽后补回已看。该项不是CF业务缺陷。
- 已用未修改的c03c0e6推荐服务复现旧断言冲突。本轮按用户确认的产品规则更新测试：候选充足时不补已看；候选耗尽时先用完未看，再补已看，且继续排除点踩、私有/不可列出媒体并保证单次结果唯一。保留原CF归因、版本、排名、签名和HTTP缓存断言。CF业务实现未修改；CONTENT仍耗尽返回空列表。
- 逐字比较确认：扣除原入口函数包装名及显式enable参数后，原CF模块与c03c0e6一致。related链路、任务、缓存命令、日志模型和归因代码无修改。
- git diff --check通过；.env未修改，运行配置读取为strategy空、effective=cf。GitHub main引用已远程核对。
- 未在浏览器启用CONTENT，因此浏览器专项验收仍待按上文步骤进行；未做大规模性能或推荐效果评估。
- 未提交、推送、合并、部署、重建镜像或清空Redis。原frontend/yarn.lock改动保留。

## CF产品规则确认与测试更新（2026-11-17）

用户明确确认：未看候选耗尽后允许补回已看，是现行CF产品规则，不属于缺陷。旧测试“无论候选数量都禁止已交互媒体”与该规则不一致，现按场景更新：

- 未看候选充足：在测试数据库构造50条额外未看候选覆盖完整请求数量，保留排除已交互/私有媒体、结果唯一、CF版本/请求编号/排名/签名及HTTP缓存断言。
- 未看候选耗尽：验证先用完两个未看候选，再补回两个已交互媒体；即使点踩项也曾观看/点赞，仍不得出现；私有、不可列出媒体始终排除；单次结果按媒体ID去重，补回项保持LEGACY及空版本归因。
- CONTENT继续沿用独立规则，耗尽返回空列表，不补已看；对应测试未放宽。

使用隔离PostgreSQL测试库、临时媒体目录和内存缓存执行tests/run_recommendation_tests.py：最终58项全部通过（含26项CONTENT测试、现有CF/行为归因/上传/转码回归）；git diff --check通过。前述初轮57项中的旧断言冲突已由本次测试更新解决，当前联合回归返回0。
本轮仅修改tests/api/test_media_recommendations.py及本文档，未改CF或CONTENT业务实现、运行配置、真实行为/标签或Redis；未提交、推送或部署。

## 本地CONTENT浏览器验收已启用（2026-11-17）

此次切换已获用户明确授权，验收期间保持运行，不提交或推送。

### 切换前记录

- 原.env不存在RECOMMENDATION_STRATEGY条目；容器有效策略字符串为空，ENABLE_COLLABORATIVE_FILTERING=True，最终选择cf。
- 配置来源是Compose env_file=.env → cms/local_settings.py环境读取；DEVELOPMENT_MODE=true加载dev_settings，但它不覆盖推荐策略。
- 旧运行容器有jieba 0.42.1，原镜像mediacms/mediacms-dev:latest没有。仅重建容器会丢失旧容器中临时安装的依赖。

### 实际切换

基于原镜像构建mediacms/mediacms-dev:content-local，仅新增jieba==0.42.1。构建上下文为/tmp/mediacms-content-local，不包含项目.env或媒体。临时Compose覆盖文件/tmp/mediacms-content-local/compose.yaml只覆盖web.image：

```yaml
services:
  web:
    image: mediacms/mediacms-dev:content-local
```

仅给.env增加RECOMMENDATION_STRATEGY=content，使用下列命令重新创建web；没有启动migrations、重启worker/db/redis或清理CF缓存：

```sh
docker compose -f docker-compose-dev.yaml -f docker-compose-content-dev.yaml up -d --no-deps --force-recreate web
```

切换时：运行策略content、当时版本tag_text_content_v1、jieba0.42.1、alpha0.5。web使用上述派生镜像，首页http://localhost/返回HTTP200。
临时覆盖文件现已持久化为项目根目录docker-compose-content-dev.yaml，Dockerfile保存在deploy/docker/content-dev/。后续命令改用项目内覆盖文件，不再依赖/tmp。不要在CONTENT启用时无意改回缺少jieba的原镜像。

### 现有数据只读验证

通过APIRequestFactory认证现有用户，调用实际MediaList/MediaDetail视图，数据库事务设置READ ONLY；没有创建登录会话、观看日志或修改标签。列表/详情正常返回，原签名归因缓存照常写入独立的归因键，未清理或改写CF排序/相似度缓存。

- 账号1111：推荐列表1项，为视频67「落日背影」，归因CONTENT/tag_text_content_v1，排名1；视频66详情autoplay_next同为67，归因也为CONTENT。67的标签余弦0，文本余弦约0.619385，alpha0.5后的正分约0.309693。因此验证了真实文本匹配，而不是热门回退；本例不证明标签通道也有正分命中。
- 账号abcde：推荐列表为视频66、68、67，均为LEGACY/空版本；视频66详情自动下一条为68「落日」，也为LEGACY。属于无正分匹配的热门回退，不能当作内容匹配成功证据。
- 上述是接口视图验收；本轮未代用户完成已登录浏览器点击或播放。实时行为变化会改变后续列表，不能保证一直保留同一推荐结果。

### 浏览器步骤

1. 访问http://localhost/，建议使用已有账号1111，使用自己已知的密码登录。
2. 打开推荐列表，并在开发者工具Network中查看/api/v1/media?show=recommended响应；检查正分命中是否标记CONTENT/tag_text_content_v2。历史行为会影响当前候选，不固定预期标题；无正分匹配时应标记LEGACY/空版本。
3. 打开http://localhost/view?m=upload-b5a5a23f24b35fab9837d5f92c194f01（视频66），在详情API响应中检查autoplay_next及其CONTENT归因，再测试自动下一条。
4. 可用已有账号abcde对照回退：algorithm_id应为LEGACY，algorithm_version为空。不要将这组结果当成内容匹配。
5. 播放会按原业务产生观看行为；67一旦被观看，下一次请求可能排除它而变为回退或空列表，这是CONTENT耗尽规则。

### 准确切回CF（本轮不执行）

将本地.env中的RECOMMENDATION_STRATEGY=content改为RECOMMENDATION_STRATEGY=cf，再执行：

```sh
docker compose -f docker-compose-dev.yaml -f docker-compose-content-dev.yaml up -d --no-deps --force-recreate web
```

若需恢复切换前的旧开关控制，删除此次新增的RECOMMENDATION_STRATEGY行（或设为空），再执行同一命令。旧ENABLE_COLLABORATIVE_FILTERING=True保持未改，因此结果仍是cf。单纯restart不会重新读取.env；无需重建或清空CF缓存。

## 端到端验收与启动依赖整理（2026-11-17）

本轮没有清除或伪造行为，没有反复运行已有测试；只读数据库事务用于日志核对和推荐计算，读取既有归因签名缓存，不写日志或标签。

### 已核对的真实播放记录

以下时间为北京时间，日志发生于本次CONTENT启用后、13:15:03基线采样之前。它们可核实各自的播放归因，但不能单独证明用户是从哪个页面或控件进入。尤其两条日志时间相邻，不作为第二条由自动下一条触发的证据；浏览器操作来源仍未确认。

| 视频 | 播放开始 | 算法 / 版本 | 推荐请求编号 | 排名 |
| --- | --- | --- | --- | --- |
| 67 落日背影 | 13:13:47 | CONTENT / tag_text_content_v1 | 54331358-6f2d-4062-a0e4-e5f21dfa619b | 1 |
| 8 unlisted.mp4 | 13:14:15 | LEGACY / 空 | 504e6476-1c88-42ee-ad1d-61b2ada7827d | 1 |

- 两条日志各自对应的既有签名均验证有效，绑定账号1111及对应视频；算法、版本、请求编号、排名逐项与日志一致。没有输出或持久化完整签名令牌。
- 分类：视频67的日志是CONTENT归因；此前接口只读检查确认该账号的推荐列表和视频66的autoplay_next均返回67且为正分文本匹配（标签相似度为0），所以67具备CONTENT匹配证据。视频8的播放日志是LEGACY/空版本，属于历史请求归因；它本身不是CONTENT匹配，也不能据此断言发生了热门回退或自动下一条。之前对账号abcde的只读接口结果（列表66/68/67及下一条68）是LEGACY热门回退，与账号1111这两条播放日志分开记录。
- 视频67观看15.067秒，end_reason=ended；视频8已累计1.606秒，采样时尚无结束时间。
- 两个视频都有此次真实播放产生的MediaAction watch记录。只读重新计算时二者均不再出现在推荐列表及视频67的后续候选中，已看排除生效。
- 播放视频8后用户画像更新，当前列表重新出现其他CONTENT正分结果，不能继续沿用“账号1111仅返回视频67”的旧快照。视频8的历史播放归因仍为LEGACY，不能因为下一次请求成为CONTENT而更改它。
- 列表中新出现的标题private.mp4不能用于判断权限；候选按数据库state=public等规则过滤。文件名噪声（例如mp4）可能造成文本正分泛化，属于效果评估局限，本轮不改评分或数据。

### 项目内启动配置

新增docker-compose-content-dev.yaml、deploy/docker/content-dev/Dockerfile、.dockerignore和README.md；不包含秘密信息、镜像文件或媒体。
现有容器继续运行，无须为了迁移配置文件而重启。Compose语法检查通过，解析后的web环境/命令/端口/挂载/镜像与原临时配置一致，唯一新增build定义；比较过程中不输出环境变量。

从项目根目录执行：

```sh
# 需要重建派生镜像时
docker compose -f docker-compose-dev.yaml -f docker-compose-content-dev.yaml build web
# .env更改后只重新创建web
docker compose -f docker-compose-dev.yaml -f docker-compose-content-dev.yaml up -d --no-deps --force-recreate web
```

切回CF：将.env中RECOMMENDATION_STRATEGY改为cf后执行上述up命令；留空可恢复旧开关控制。此次不切回，CONTENT继续运行。

### 尚未验证 / 尚待人工确认

尚未在浏览器Network面板将用户操作与具体推荐响应逐项对应，也尚未确认是否从推荐列表点击了67、视频8是否由自动下一条触发。不得把相邻播放日志当作自动播放证据。已通过只读记录确认签名字段与各自播放日志一致、两条已看视频在后续推荐计算中被排除；接口层也验证了67曾作为CONTENT正分结果进入列表和autoplay_next。没有新增第二轮播放、没有改写已有日志补全结束时间.
## 文本噪声清理（tag_text_content_v2）

第一轮只读评分发现，旧标题中的`mp4`、长资源编号、URL导出文件名以及`public.mp4`/`private.mp4`/`unlisted.mp4`等文件占位标题可造成弱文本匹配。v2仅调整文本通道，标签向量、候选过滤、CF实现、策略配置和当前运行开关均保持不变。

- 标题仅在以明确媒体扩展名结尾时按文件名处理：移除扩展名；清理独立的7位以上资源编号或24位以上十六进制哈希前缀；把下划线还原为空格；过滤`https_...`类URL文件名部分。保留扩展名之前的普通文本和人名。
- 完全等于`public.mp4`、`private.mp4`、`unlisted.mp4`或`video<数字>.mp4`的占位标题视为空文本；这些词在普通标题、简介和复合标题中保留。
- 文本中的明确点分媒体扩展名（如`.mp4`、`.mp3`、`.pdf`）不进入词表；扩展名文件标题里的7位以上纯编号前缀会清理。普通文本中的数字（包括较长数字）、英文、人名、年份，以及`public`/`private`等普通词不作为通用停用词删除。
- IDF拟合范围与双路评分公式不变；不从文件路径引入新特征。正分归因版本升为`tag_text_content_v2`，以区别旧清理规则下的评分。已有v1行为日志保持原版本记录。

噪声清理相关测试覆盖扩展名、长编号、哈希/URL文件名结构、占位文件标题，以及人名、正常英文、public/private与短数字保留。最新具体测试结果以本轮交付说明为准；第一轮评分CSV是v1历史快照，v2启用后排序可能改变，应在新的只读快照下重新生成。


本轮验证（2026-11-17）：`docker compose -f docker-compose-dev.yaml -f docker-compose-content-dev.yaml exec -T web /home/mediacms.io/bin/python tests/run_recommendation_tests.py tests.services.test_content_recommendations` 通过，29项测试全部成功；包含原内容推荐服务/API归因测试和新增文本噪声清理用例。`git diff --check`通过。未重复运行未受文本通道影响的CF测试。容器运行策略仍为CONTENT；新请求使用`tag_text_content_v2`。第一轮CSV保留为v1历史快照。
