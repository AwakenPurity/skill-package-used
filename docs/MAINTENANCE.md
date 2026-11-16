# 版本维护

## 获取已记录的版本

```bash
git pull --ff-only
git submodule update --init --recursive
git submodule status
```

不要手工把子模块目录复制到别处后误以为依赖仍然完整。保留每个项目原有的目录结构、许可、资源和脚本。

## 主动升级一个项目

下面以 frontend-slides 为例；先确认子模块没有自己的未提交改动，再操作。

```bash
git -C skills/frontend-slides status --short
git -C skills/frontend-slides fetch origin main
git -C skills/frontend-slides log --oneline HEAD..origin/main
```

阅读上游变更和许可证后，将该项目更新至确认过的提交：

```bash
git -C skills/frontend-slides checkout --detach origin/main
git -C skills/frontend-slides rev-parse HEAD
```

将完整提交 SHA 同步写入根目录的 `skills.lock.json`，更新 `recorded_on`，并检查 README 的版本链接与能力说明。运行项目适用的校验后，只提交本次需要的文件：

```bash
git add skills/frontend-slides skills.lock.json README.md
git diff --cached --submodule=log
git commit -m "Update frontend-slides to reviewed upstream revision"
git push origin main
```

其余三个项目同理。不要只改 lock 文件而不更新 gitlink，也不要只更新 gitlink 而保留过期清单。

## 新增项目

先核对来源、许可、Skill 入口和实际输出格式，再通过 `git submodule add <upstream-url> skills/<name>` 添加。随后更新 README、`skills.lock.json` 与 `THIRD_PARTY_NOTICES.md`。

## 常见情况

- **目录是空的**：执行 `git submodule update --init --recursive`。
- **下载 ZIP 没有 Skill 源码**：使用 README 中的递归克隆命令。
- **想在 Agent 里自动发现 Skill**：按上游的安装方式操作；本集合的克隆不是安装动作。
- **子模块提示 detached HEAD**：这是固定版本的正常状态；不需要为了使用而切换分支。
- **无法访问 GitHub**：检查自己的网络和 Git 连接配置，不要把访问凭据写进仓库。
