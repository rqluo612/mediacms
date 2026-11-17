# 本地 CONTENT 开发镜像

从项目根目录执行。此覆盖配置复用docker-compose-dev.yaml，只增加web的本地镜像构建定义；不设置策略、不包含.env、不更改数据库/worker/Redis/卷。

基础镜像需已有mediacms/mediacms-dev:latest。若缺少，可先执行`docker compose -f docker-compose-dev.yaml build migrations`，仅构建基础镜像，不启动迁移服务。

```sh
# 构建上下文只有本目录，.dockerignore仅允许Dockerfile。
docker compose -f docker-compose-dev.yaml -f docker-compose-content-dev.yaml build web
# 只做配置语法检查，不打印解析后的秘密环境变量。
docker compose -f docker-compose-dev.yaml -f docker-compose-content-dev.yaml config --quiet
```

Dockerfile仅在基础镜像上固定安装jieba==0.42.1。可通过build --build-arg BASE_IMAGE=具体基础镜像引用选择本地基础镜像；基础镜像latest不是不可变引用，如需跨机器逐字节重现需另行保存可取得的基础镜像digest/制品。项目不保存镜像tar或秘密文件。

本地.env的RECOMMENDATION_STRATEGY=content启用；cf切回CF；空值恢复ENABLE_COLLABORATIVE_FILTERING旧开关。修改.env后只重新创建web：

```sh
docker compose -f docker-compose-dev.yaml -f docker-compose-content-dev.yaml up -d --no-deps --force-recreate web
```

Python配置修改可以restart web（开发runserver通常自动重载）；.env修改必须重新创建，restart不会重新加载env_file。重建web会中断正在进行的浏览器验收，应在需要更改配置时执行。

当前容器仍是此前临时覆盖文件启动的同名派生镜像，保存这些文件不会重启它。项目内覆盖文件已验证除新增build声明外与原web配置相同；以后仅使用上述项目内路径，不依赖/tmp。

完整算法及验收记录见docs/tag-content-recommendations.md。本轮未执行再次构建、重启或旧测试重跑。
